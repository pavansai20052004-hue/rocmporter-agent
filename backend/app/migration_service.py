"""Full-repo migration PRs.

Takes a completed scan, generates ROCm patches for every flagged evidence file
(capped), pushes them to a new branch on the user's repository using their
GitHub OAuth token, and opens a pull request.

The GitHub token is held in memory for the lifetime of the job only — it is
never persisted to disk and never echoed back through the API.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .hipify_service import build_hybrid_note, hipify_text
from .knowledge_base import build_knowledge_block
from .llm_service import default_model, generate_structured, resolve_model_name
from .models import MigrationFileStatus, MigrationStatus
from .service import REPO_ROOT, scan_service

GITHUB_API = "https://api.github.com"
MAX_FILES = max(1, int(os.getenv("MIGRATION_MAX_FILES", "10")))
MAX_FILE_CHARS = 18_000
MAX_CONTEXT_HEADERS = 2
MAX_CONTEXT_HEADER_CHARS = 2_000

MIGRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "patchedContent": {"type": "string"},
        "needsMoreContext": {"type": "boolean"},
    },
    "required": ["rationale", "patchedContent", "needsMoreContext"],
}

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class MigrationRecord:
    migration_id: str
    scan_id: str
    repo_url: str
    model: str
    token: str  # in-memory only
    status: str = "queued"
    stage: str = "queued"
    percent: int = 0
    error: str | None = None
    pr_url: str | None = None
    branch: str | None = None
    files: list[MigrationFileStatus] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_status(self) -> MigrationStatus:
        return MigrationStatus(
            migrationId=self.migration_id,
            scanId=self.scan_id,
            status=self.status,
            stage=self.stage,
            percent=self.percent,
            error=self.error,
            prUrl=self.pr_url,
            branch=self.branch,
            files=list(self.files),
        )


class MigrationService:
    def __init__(self) -> None:
        self._records: dict[str, MigrationRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="migration")

    def start(self, scan_id: str, token: str, model: str | None) -> MigrationStatus:
        report = scan_service.get_report(scan_id)
        if report is None:
            raise ValueError("Run a scan first — no completed report found for this scan id.")
        if not token:
            raise ValueError("A GitHub authorization is required. Sign in with GitHub, then retry.")
        if not (REPO_ROOT / scan_id).exists():
            raise ValueError("The scan workspace has expired. Re-scan the repository and try again.")

        scan = scan_service.get_scan(scan_id)
        record = MigrationRecord(
            migration_id=f"mig_{uuid.uuid4().hex[:10]}",
            scan_id=scan_id,
            repo_url=scan.repoUrl if scan else report.repo.url,
            model=resolve_model_name(model or default_model()),
            token=token.strip(),
        )
        with self._lock:
            self._records[record.migration_id] = record
        self._executor.submit(self._run, record.migration_id)
        return record.as_status()

    def get(self, migration_id: str) -> MigrationStatus | None:
        with self._lock:
            record = self._records.get(migration_id)
            return None if record is None else record.as_status()

    # ------------------------------------------------------------------ #

    def _update(self, record: MigrationRecord, *, status: str | None = None, stage: str | None = None, percent: int | None = None, error: str | None = None) -> None:
        with self._lock:
            if status is not None:
                record.status = status
            if stage is not None:
                record.stage = stage
            if percent is not None:
                record.percent = percent
            if error is not None:
                record.error = error

    def _run(self, migration_id: str) -> None:
        record = self._records[migration_id]
        try:
            self._execute(record)
        except Exception as exc:  # noqa: BLE001 - job boundary
            self._update(record, status="failed", stage="failed", percent=100, error=str(exc))
        finally:
            record.token = ""  # drop the token as soon as the job ends

    def _execute(self, record: MigrationRecord) -> None:
        report = scan_service.get_report(record.scan_id)
        owner_repo = _owner_repo(record.repo_url)
        workspace = REPO_ROOT / record.scan_id

        targets = _pick_targets(report)
        if not targets:
            raise RuntimeError("No patchable evidence files were found in this report.")

        # 1) Generate patched content for each target file.
        self._update(record, status="running", stage="generating", percent=5)
        patched: list[tuple[str, str, str]] = []  # (path, content, rationale)
        for index, path in enumerate(targets):
            file_path = workspace / Path(path)
            entry = MigrationFileStatus(path=path, status="generating", note=None)
            record.files.append(entry)
            self._update(record, percent=5 + int(55 * index / len(targets)))

            if not file_path.exists():
                entry.status = "skipped"
                entry.note = "file missing from scan workspace"
                continue
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            if len(source) > MAX_FILE_CHARS:
                entry.status = "skipped"
                entry.note = "file too large for reliable single-pass migration"
                continue

            # Hybrid engine, stage 1: deterministic hipify pass (no model).
            hip = hipify_text(source, path)
            if hip.fully_converted:
                # Every CUDA token was mechanically mapped — commit as-is,
                # no LLM involved. This is the highest-trust path.
                entry.status = "patched"
                entry.note = f"deterministic hipify — {hip.total_replacements} mechanical replacement(s), no AI needed"
                content = hip.converted
                patched.append((path, content if content.endswith("\n") else content + "\n", entry.note))
                continue

            # Stage 2: LLM finishes only what the mechanical pass couldn't.
            base = hip.converted if hip.total_replacements else source
            try:
                payload = generate_structured(
                    record.model,
                    _migration_prompt(path, base, build_hybrid_note(hip), _local_header_context(workspace, path, source)),
                    MIGRATION_SCHEMA,
                    system=(
                        "You are an AMD ROCm migration engineer. Convert CUDA/NVIDIA-specific code to "
                        "portable ROCm/HIP equivalents. Keep changes minimal and preserve behavior. "
                        "Return strict JSON only."
                    ),
                    options={"temperature": 0.1, "num_predict": 4000},
                )
            except RuntimeError as exc:
                entry.status = "skipped"
                entry.note = f"generation failed: {exc}"[:180]
                continue
            content = (payload.get("patchedContent") or "").strip()
            if payload.get("needsMoreContext") or not content or content == source.strip():
                entry.status = "skipped"
                entry.note = "needs manual attention (insufficient single-file context)"
                continue
            entry.status = "patched"
            rationale = (payload.get("rationale") or "").strip()[:200]
            hybrid_tag = (
                f"hybrid: {hip.total_replacements} deterministic + AI remainder"
                if hip.total_replacements
                else "AI-generated"
            )
            entry.note = f"{hybrid_tag}. {rationale}"[:240] or None
            patched.append((path, content if content.endswith("\n") else content + "\n", entry.note or ""))

        if not patched:
            raise RuntimeError(
                "No files could be migrated automatically — every candidate needs manual attention. "
                "Use single-file patch generation to work through them individually."
            )

        # 2) Create a branch off the default branch.
        self._update(record, stage="branching", percent=65)
        repo_info = self._gh(record, "GET", f"/repos/{owner_repo}")
        default_branch = repo_info.get("default_branch", "main")
        head = self._gh(record, "GET", f"/repos/{owner_repo}/git/ref/{urllib.parse.quote(f'heads/{default_branch}')}")
        base_sha = head["object"]["sha"]
        branch = f"rocmporter/migration-{uuid.uuid4().hex[:6]}"
        self._gh(record, "POST", f"/repos/{owner_repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": base_sha})
        record.branch = branch

        # 3) Commit each patched file to the branch.
        self._update(record, stage="committing", percent=72)
        for index, (path, content, _rationale) in enumerate(patched):
            encoded_path = "/".join(urllib.parse.quote(part) for part in path.split("/"))
            existing_sha = None
            try:
                current = self._gh(record, "GET", f"/repos/{owner_repo}/contents/{encoded_path}?ref={branch}")
                existing_sha = current.get("sha")
            except RuntimeError:
                existing_sha = None  # new file
            body = {
                "message": f"ROCmPorter: migrate {path} to ROCm/HIP",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
            }
            if existing_sha:
                body["sha"] = existing_sha
            self._gh(record, "PUT", f"/repos/{owner_repo}/contents/{encoded_path}", body)
            self._update(record, percent=72 + int(18 * (index + 1) / len(patched)))

        # 4) Open the pull request.
        self._update(record, stage="opening_pr", percent=92)
        pr = self._gh(
            record,
            "POST",
            f"/repos/{owner_repo}/pulls",
            {
                "title": f"ROCmPorter: CUDA → ROCm migration ({len(patched)} file{'s' if len(patched) != 1 else ''})",
                "head": branch,
                "base": default_branch,
                "body": _pr_body(report, record.files),
            },
        )
        record.pr_url = pr.get("html_url")
        self._update(record, status="completed", stage="completed", percent=100)

    def _gh(self, record: MigrationRecord, method: str, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            f"{GITHUB_API}{path}",
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={
                "Authorization": f"Bearer {record.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "rocmporter-agent",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("message", "")
            except Exception:  # pragma: no cover
                pass
            if exc.code in (401, 403):
                raise RuntimeError(
                    "GitHub rejected the authorization. Reconnect GitHub (sign out and back in) and "
                    "make sure you have push access to this repository."
                ) from exc
            if exc.code == 404 and method != "GET":
                raise RuntimeError(
                    "Repository not writable with your GitHub account — migration PRs work on repositories "
                    "you have push access to."
                ) from exc
            raise RuntimeError(f"GitHub API {method} {path} failed ({exc.code}): {detail[:200]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach GitHub: {getattr(exc, 'reason', exc)}") from exc


def _owner_repo(repo_url: str) -> str:
    match = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", repo_url.strip())
    if not match:
        raise RuntimeError("Only GitHub repositories are supported for migration PRs.")
    return match.group(1)


def _pick_targets(report) -> list[str]:
    """Unique evidence file paths, most severe findings first, capped."""
    seen: set[str] = set()
    ordered: list[str] = []
    findings = sorted(report.findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))
    for finding in findings:
        for entry in finding.evidence:
            path = entry.path
            if path in seen:
                continue
            # Only migrate real source/build files (skip lockfiles, binaries, workflows).
            if any(path.endswith(ext) for ext in (".png", ".jpg", ".gif", ".bin", ".so", ".lock")):
                continue
            seen.add(path)
            ordered.append(path)
            if len(ordered) >= MAX_FILES:
                return ordered
    return ordered


def _local_header_context(workspace: Path, file_rel_path: str, source: str) -> str:
    """Read-only excerpts of repo-local headers the file includes.

    Gives the model cross-file context (types, macros, declarations) without
    letting it edit those files — reduces needsMoreContext bailouts.
    """
    file_dir = (workspace / Path(file_rel_path)).parent
    blocks: list[str] = []
    for match in re.finditer(r'#include\s*"([^"]+)"', source):
        if len(blocks) >= MAX_CONTEXT_HEADERS:
            break
        header_rel = match.group(1)
        candidates = [file_dir / header_rel, workspace / header_rel]
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                if not str(resolved).startswith(str(workspace.resolve())):
                    break  # never read outside the scan workspace
                if resolved.is_file():
                    text = resolved.read_text(encoding="utf-8", errors="ignore")[:MAX_CONTEXT_HEADER_CHARS]
                    blocks.append(f'--- {header_rel} (read-only reference) ---\n{text}')
                    break
            except OSError:
                break
    if not blocks:
        return ""
    return (
        "Local headers included by this file, for reference ONLY — do not rewrite them, "
        "just keep this file consistent with them:\n" + "\n".join(blocks)
    )


def _migration_prompt(path: str, source: str, hybrid_note: str = "", context_block: str = "") -> str:
    note_block = f"\nMechanical pass report:\n{hybrid_note}\n" if hybrid_note else ""
    knowledge = build_knowledge_block(source)
    knowledge_block = f"\n{knowledge}\n" if knowledge else ""
    extra_context = f"\n{context_block}\n" if context_block else ""
    return (
        f"Migrate this file from CUDA/NVIDIA-specific code to AMD ROCm/HIP.\n"
        f"File path: {path}\n"
        f"{note_block}{knowledge_block}{extra_context}\n"
        "Rules:\n"
        "- Replace remaining CUDA APIs/headers with HIP equivalents (cuda.h -> hip/hip_runtime.h, cudaMalloc -> hipMalloc, etc.).\n"
        "- Do NOT undo or re-translate anything the mechanical pass already converted to hip*.\n"
        "- In build files, replace nvcc/CUDA toolchain assumptions with ROCm/hipcc equivalents while keeping the build working.\n"
        "- Keep everything else byte-for-byte identical: comments, formatting, unrelated logic.\n"
        "- If a correct migration is impossible without seeing other files, set needsMoreContext=true.\n\n"
        f"File content:\n```\n{source}\n```"
    )


def _pr_body(report, files: list[MigrationFileStatus]) -> str:
    patched = [f for f in files if f.status == "patched"]
    skipped = [f for f in files if f.status == "skipped"]
    lines = [
        "## ⚡ ROCmPorter — automated CUDA → ROCm migration",
        "",
        f"ROCm readiness before migration: **{report.summary.portabilityScore}/100** ({report.summary.riskLevel} risk).",
        "",
        "### Migrated files",
    ]
    for f in patched:
        lines.append(f"- `{f.path}`" + (f" — {f.note}" if f.note else ""))
    if skipped:
        lines += ["", "### Needs manual attention"]
        for f in skipped:
            lines.append(f"- `{f.path}` — {f.note or 'skipped'}")
    deterministic = sum(1 for f in patched if f.note and "deterministic hipify" in f.note)
    lines += [
        "",
        "### How these patches were made (hybrid engine)",
        f"- 🔩 **{deterministic}** file(s) fully converted by the **deterministic hipify pass** (mechanical CUDA→HIP API mapping, no AI)",
        f"- 🤖 **{len(patched) - deterministic}** file(s) finished by AI for the parts the mechanical pass can't do (per-file notes above)",
        "",
        "### Validate this PR on the real ROCm toolchain",
        "Add ROCmPorter's [ROCm compile-validation workflow](https://github.com/pavansai20052004-hue/rocmporter-agent/blob/main/.github/workflows/rocm-compile-validate.yml) "
        "to this repository and this PR gets `hipcc` compile checks in AMD's official ROCm container — no GPU required. "
        "[Full validation guide →](https://github.com/pavansai20052004-hue/rocmporter-agent/blob/main/docs/rocm-validation.md)",
        "",
        "> ⚠️ Review, build, and test on ROCm hardware before merging.",
        "",
        "_Opened by [ROCmPorter](https://rocmporter-agent.vercel.app) — evidence-backed CUDA → ROCm migration._",
    ]
    return "\n".join(lines)


migration_service = MigrationService()
