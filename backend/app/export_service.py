from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from .github_review_service import build_review_payload, generate_inline_comments, infer_repository_slug, render_review_comment
from .models import ExportFile, ExportResult, PatchResult, ScanReport, ScanStatus
from .patch_service import patch_service
from .service import REPO_ROOT, WORK_ROOT, scan_service


ARTIFACT_ROOT = WORK_ROOT / "exports"
EXPORTER_VERSION = "0.5.0"
DEFAULT_EXPORT_FORMATS = {"json", "markdown", "diff", "html", "zip", "github"}

REPORT_CSS = """
:root {
  color-scheme: dark;
  font-family: Inter, "Segoe UI", sans-serif;
  --bg: #0d1014;
  --panel: #171b21;
  --panel-soft: #1f252d;
  --text: #eef2f8;
  --muted: #b3bcc8;
  --line: rgba(255, 255, 255, 0.08);
  --accent: #ff6a3d;
  --warn: #f3b56a;
  --high: #ff9f86;
  --low: #89e6dd;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); }
.page { max-width: 1240px; margin: 0 auto; padding: 28px; display: grid; gap: 20px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 20px; }
.hero { display: grid; gap: 10px; }
.eyebrow, .mini, .badge, .pill { text-transform: uppercase; letter-spacing: 0.08em; font-size: 12px; color: var(--muted); }
.title-row, .meta-row, .score-row, .split { display: grid; gap: 16px; }
.title-row { grid-template-columns: minmax(0, 1fr) 140px; align-items: center; }
.score-box { border-radius: 18px; border: 1px solid var(--line); background: var(--panel-soft); min-height: 120px; display: grid; place-items: center; font-size: 40px; font-weight: 800; }
.meta-row, .score-row { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.metric, .finding, .evidence, .patch-card, .file-card { background: var(--panel-soft); border: 1px solid var(--line); border-radius: 14px; padding: 16px; }
.finding-list, .evidence-list, .patch-list, .file-list, .warning-list { display: grid; gap: 14px; }
.severity { display: inline-flex; padding: 6px 10px; border-radius: 999px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
.severity.high, .severity.critical { background: rgba(255, 106, 61, 0.18); color: var(--high); }
.severity.medium { background: rgba(243, 181, 106, 0.16); color: #ffd9a0; }
.severity.low { background: rgba(137, 230, 221, 0.14); color: var(--low); }
.pill { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 999px; background: rgba(255,255,255,0.04); }
.warning { border-left: 4px solid var(--warn); padding-left: 12px; }
pre { margin: 12px 0 0; padding: 14px; border-radius: 12px; background: #0a0d11; color: #dff8ff; overflow: auto; white-space: pre-wrap; }
code, .path { font-family: "Cascadia Code", Consolas, monospace; }
a { color: #ffd1bf; }
.banner { background: rgba(255, 106, 61, 0.12); border: 1px solid rgba(255, 106, 61, 0.28); border-radius: 14px; padding: 14px; }
.hidden { display: none; }
.controls { display: flex; gap: 8px; flex-wrap: wrap; }
button { border: 1px solid var(--line); background: rgba(255,255,255,0.04); color: var(--text); border-radius: 999px; padding: 8px 12px; cursor: pointer; }
@media (max-width: 960px) {
  .title-row, .meta-row, .score-row, .split { grid-template-columns: 1fr; }
}
""".strip()

REPORT_JS = """
const dataNode = document.getElementById('rocmporter-data')
if (dataNode) {
  const data = JSON.parse(dataNode.textContent)
  const buttons = Array.from(document.querySelectorAll('[data-filter]'))
  const cards = Array.from(document.querySelectorAll('[data-severity]'))
  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      const filter = button.dataset.filter
      buttons.forEach((item) => item.classList.toggle('active', item === button))
      cards.forEach((card) => {
        const visible = filter === 'all' || card.dataset.severity === filter
        card.classList.toggle('hidden', !visible)
      })
    })
  })
  const updated = document.getElementById('generated-at')
  if (updated && data.generatedAt) {
    updated.textContent = new Date(data.generatedAt).toLocaleString()
  }
}
""".strip()


class ExportService:
    def __init__(self) -> None:
        ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

    def create_export(
        self,
        scan_id: str,
        *,
        patch_id: str | None = None,
        formats: set[str] | None = None,
        output_dir: Path | None = None,
        expose_downloads: bool = False,
    ) -> ExportResult:
        scan = scan_service.get_scan(scan_id)
        report = scan_service.get_report(scan_id)
        if scan is None or report is None:
            raise ValueError("Scan report is not ready for export yet.")

        selected_formats = formats or {"json", "markdown", "html", "zip", "github"}
        selected_formats &= DEFAULT_EXPORT_FORMATS
        if not selected_formats:
            selected_formats = {"json", "markdown", "html", "zip", "github"}

        export_id = output_dir.name if output_dir is not None else f"export_{uuid.uuid4().hex[:10]}"
        root_dir = output_dir or (ARTIFACT_ROOT / scan_id / export_id)
        patches = self._select_patches(scan_id, patch_id)
        verification_receipts = self._verify_patches(patches)
        if patch_id and verification_receipts:
            not_ready = next((receipt for receipt in verification_receipts if not receipt.get("exportReady")), None)
            if not_ready is not None:
                failed = [check for check in not_ready.get("checks", []) if check.get("state") == "failed"]
                reason = failed[0]["message"] if failed else not_ready.get("summary", "Patch is not export-ready.")
                raise ValueError(f"Patch verification is not export-ready: {reason}")

        data_dir = root_dir / "data"
        assets_dir = root_dir / "assets"
        patches_dir = root_dir / "patches"
        verification_dir = root_dir / "verification"
        for path in (root_dir, data_dir, assets_dir, patches_dir, verification_dir):
            path.mkdir(parents=True, exist_ok=True)

        export_patches = self._export_patches(root_dir, patches_dir, patches)
        verification_receipts = self._export_verifications(root_dir, verification_dir, verification_receipts)
        warnings = self._export_notes(report, patches)
        files: list[ExportFile] = []

        self._write_json(root_dir / "report.json", report.model_dump(mode="json"))
        files.append(self._file_item(scan_id, export_id, "report_json", "Report JSON", root_dir / "report.json", expose_downloads))

        summary_text = build_report_markdown(report)
        (root_dir / "summary.md").write_text(summary_text, encoding="utf-8")
        files.append(self._file_item(scan_id, export_id, "summary_markdown", "Summary Markdown", root_dir / "summary.md", expose_downloads))

        self._write_json(data_dir / "scan.json", scan.model_dump(mode="json"))
        self._write_json(data_dir / "report.json", report.model_dump(mode="json"))
        self._write_json(data_dir / "coverage.json", _coverage_payload(report))
        self._write_json(data_dir / "evidence.json", _evidence_rows(report))
        self._write_json(data_dir / "patches.json", export_patches)
        self._write_json(data_dir / "verifications.json", verification_receipts)

        if patch_id and len(export_patches) == 1:
            self._write_json(root_dir / "patch-result.json", export_patches[0])
            files.append(self._file_item(scan_id, export_id, "patch_json", "Patch JSON", root_dir / "patch-result.json", expose_downloads))
        if patch_id and len(verification_receipts) == 1:
            self._write_json(root_dir / "patch-verification.json", verification_receipts[0])
            files.append(
                self._file_item(
                    scan_id,
                    export_id,
                    "patch_verification_json",
                    "Patch Verification Receipt",
                    root_dir / "patch-verification.json",
                    expose_downloads,
                )
            )

        for receipt in verification_receipts:
            receipt_relative = receipt.get("savedReceiptPath")
            if not receipt_relative:
                continue
            receipt_path = root_dir / receipt_relative
            if receipt_path.exists():
                files.append(
                    self._file_item(
                        scan_id,
                        export_id,
                        "verification_receipt",
                        f"Verification Receipt: {receipt['patchId']}",
                        receipt_path,
                        expose_downloads,
                    )
                )

        if export_patches:
            for patch_payload in export_patches:
                diff_relative = patch_payload.get("savedPatchPath")
                if diff_relative and "diff" in selected_formats:
                    diff_path = root_dir / diff_relative
                    if diff_path.exists():
                        files.append(
                            self._file_item(
                                scan_id,
                                export_id,
                                "patch_diff",
                                f"Patch Diff: {diff_path.name}",
                                diff_path,
                                expose_downloads,
                            )
                        )

                patched_relative = patch_payload.get("savedPatchedFilePath")
                if patched_relative:
                    patched_path = root_dir / patched_relative
                    if patched_path.exists():
                        files.append(
                            self._file_item(
                                scan_id,
                                export_id,
                                "patch_snapshot",
                                f"Patched File Snapshot: {patch_payload['evidencePath']}",
                                patched_path,
                                expose_downloads,
                            )
                        )

                source_relative = patch_payload.get("sourceFilePath")
                if source_relative:
                    source_path = root_dir / source_relative
                    if source_path.exists():
                        files.append(
                            self._file_item(
                                scan_id,
                                export_id,
                                "source_snapshot",
                                f"Source File Snapshot: {patch_payload['evidencePath']}",
                                source_path,
                                expose_downloads,
                            )
                        )

        if patches and "github" in selected_formats:
            repository_slug = None
            try:
                repository_slug = infer_repository_slug(report.repo.url)
            except ValueError:
                repository_slug = report.repo.name

            for patch in patches:
                inline_comments = generate_inline_comments(report, patch)
                comment_body = render_review_comment(report, patch, repository_slug, None, inline_comments)
                review_payload = build_review_payload(
                    report,
                    patch,
                    repository_slug,
                    None,
                    comment_body,
                    inline_comments,
                    inline_comments,
                    None,
                )
                stem = "github-review" if len(patches) == 1 else f"github-review_{patch.patchId}"
                markdown_path = root_dir / f"{stem}.md"
                json_path = root_dir / f"{stem}.json"
                inline_path = root_dir / f"{stem}-inline-comments.json"
                markdown_path.write_text(comment_body, encoding="utf-8")
                self._write_json(json_path, review_payload)
                self._write_json(inline_path, [item.model_dump(mode="json") for item in inline_comments])
                files.append(self._file_item(scan_id, export_id, "github_review_markdown", f"GitHub Review: {markdown_path.name}", markdown_path, expose_downloads))
                files.append(self._file_item(scan_id, export_id, "github_review_json", f"GitHub Review JSON: {json_path.name}", json_path, expose_downloads))
                files.append(self._file_item(scan_id, export_id, "github_inline_comments_json", f"GitHub Inline Comments: {inline_path.name}", inline_path, expose_downloads))

        if "html" in selected_formats:
            (assets_dir / "report.css").write_text(REPORT_CSS, encoding="utf-8")
            (assets_dir / "report.js").write_text(REPORT_JS, encoding="utf-8")
            (root_dir / "index.html").write_text(
                _build_report_html(scan, report, export_patches, verification_receipts, warnings, export_id),
                encoding="utf-8",
            )
            files.append(self._file_item(scan_id, export_id, "html_report", "Offline HTML Report", root_dir / "index.html", expose_downloads))

        manifest = _build_manifest(scan, report, patches, verification_receipts, root_dir)
        self._write_json(root_dir / "manifest.json", manifest)
        files.append(self._file_item(scan_id, export_id, "manifest", "Manifest", root_dir / "manifest.json", expose_downloads))

        checksums_path = root_dir / "SHA256SUMS.txt"
        checksums_path.write_text(_build_checksums(root_dir), encoding="utf-8")
        files.append(self._file_item(scan_id, export_id, "checksums", "Checksums", checksums_path, expose_downloads))

        if "zip" in selected_formats:
            zip_base = root_dir / "bundle"
            zip_path = Path(shutil.make_archive(str(zip_base), "zip", root_dir))
            files.append(self._file_item(scan_id, export_id, "zip_bundle", "Zip Bundle", zip_path, expose_downloads))

        return ExportResult(
            exportId=export_id,
            scanId=scan_id,
            patchId=patch_id,
            createdAt=datetime.now(UTC),
            rootPath=str(root_dir.resolve()),
            files=files,
            warnings=warnings,
        )

    def resolve_export_file(self, scan_id: str, export_id: str, relative_path: str) -> Path:
        root_dir = ARTIFACT_ROOT / scan_id / export_id
        target = (root_dir / relative_path).resolve()
        if not target.exists():
            raise ValueError("Requested export file was not found.")
        if root_dir.resolve() not in target.parents and target != root_dir.resolve():
            raise ValueError("Requested export file is outside the allowed export directory.")
        return target

    def _select_patches(self, scan_id: str, patch_id: str | None) -> list[PatchResult]:
        if patch_id:
            patch = patch_service.get_patch(patch_id)
            if patch is None or patch.scanId != scan_id:
                raise ValueError("Patch artifact was not found for this scan.")
            return [patch]
        return []

    def _export_notes(self, report: ScanReport, patches: list[PatchResult]) -> list[str]:
        notes = [
            "Deterministic static scan. Patch suggestions are model-generated and require review.",
            "This bundle does not include runtime compilation or execution validation.",
        ]
        if patches:
            notes.append("Patch verification receipts are included and should be reviewed with the diff.")
        if patches and any(patch.validation and patch.validation.state != "passed" for patch in patches):
            notes.append("At least one patch did not pass local syntax validation and should be reviewed before use.")
        if report.coverage and report.coverage.skippedLargeFiles:
            notes.append(f"{report.coverage.skippedLargeFiles} large files were skipped by the scanner size guard.")
        return notes

    def _file_item(
        self,
        scan_id: str,
        export_id: str,
        kind: str,
        label: str,
        path: Path,
        expose_downloads: bool,
    ) -> ExportFile:
        download_path = None
        if expose_downloads:
            relative = path.relative_to(ARTIFACT_ROOT / scan_id / export_id).as_posix()
            download_path = f"/api/scans/{scan_id}/exports/{export_id}/download/{relative}"
        return ExportFile(kind=kind, label=label, path=str(path.resolve()), downloadPath=download_path)

    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _export_patches(self, root_dir: Path, patches_dir: Path, patches: list[PatchResult]) -> list[dict]:
        payloads: list[dict] = []
        for patch in patches:
            artifacts = _copy_patch_bundle_artifacts(root_dir, patches_dir, patch)
            payloads.append(_build_export_patch_payload(patch, artifacts))
        return payloads

    def _verify_patches(self, patches: list[PatchResult]) -> list[dict]:
        return [
            patch_service.verify_patch(patch.scanId, patch.patchId).model_dump(mode="json")
            for patch in patches
        ]

    def _export_verifications(self, root_dir: Path, verification_dir: Path, receipts: list[dict]) -> list[dict]:
        payloads: list[dict] = []
        for receipt in receipts:
            target = verification_dir / f"{receipt['patchId']}-verification.json"
            payload = dict(receipt)
            payload["savedReceiptPath"] = target.relative_to(root_dir).as_posix()
            self._write_json(target, payload)
            payloads.append(payload)
        return payloads


@dataclass(frozen=True)
class PatchBundleArtifacts:
    diff_path: str | None = None
    patched_file_path: str | None = None
    source_file_path: str | None = None


def build_report_markdown(report: ScanReport) -> str:
    lines = [
        f"# ROCmPorter Report: {report.repo.name}",
        "",
        f"- Repo: {report.repo.url}",
        f"- Default branch: {report.repo.defaultBranch}",
        f"- Portability score: {report.summary.portabilityScore}",
        f"- Risk level: {report.summary.riskLevel}",
        f"- Estimated effort: {report.summary.estimatedEffort}",
        f"- Ruleset version: {report.rulesetVersion}",
        "",
        "## Findings",
    ]
    for finding in report.findings:
        lines.append(f"- [{finding.severity}] {finding.title}")
        for evidence in finding.evidence[:3]:
            line_suffix = f":{evidence.lineStart}" if evidence.lineStart is not None else ""
            lines.append(f"  - {evidence.path}{line_suffix}")
    lines.append("")
    lines.append("## Next Steps")
    for step in report.nextSteps:
        lines.append(f"- {step}")
    if report.coverage:
        lines.extend(
            [
                "",
                "## Coverage",
                f"- Files discovered: {report.coverage.totalFiles}",
                f"- Files scanned: {report.coverage.scannedFiles}",
                f"- Large files skipped: {report.coverage.skippedLargeFiles}",
            ]
        )
    return "\n".join(lines) + "\n"


def _coverage_payload(report: ScanReport) -> dict:
    if report.coverage is None:
        return {}
    return report.coverage.model_dump(mode="json")


def _evidence_rows(report: ScanReport) -> list[dict]:
    rows: list[dict] = []
    for finding in report.findings:
        for evidence in finding.evidence:
            rows.append(
                {
                    "findingId": finding.id,
                    "severity": finding.severity,
                    "title": finding.title,
                    "confidence": finding.confidence,
                    "path": evidence.path,
                    "lineStart": evidence.lineStart,
                    "lineEnd": evidence.lineEnd,
                    "matchText": evidence.matchText,
                    "snippet": evidence.snippet,
                    "recommendation": finding.recommendation,
                }
            )
    return rows


def _build_manifest(
    scan: ScanStatus,
    report: ScanReport,
    patches: list[PatchResult],
    verification_receipts: list[dict],
    root_dir: Path,
) -> dict:
    repo_path = REPO_ROOT / scan.scanId
    return {
        "schemaVersion": "1.0",
        "exporterVersion": EXPORTER_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(),
        "scanId": scan.scanId,
        "repoUrl": report.repo.url,
        "repoName": report.repo.name,
        "defaultBranch": report.repo.defaultBranch,
        "commitSha": _git_value(repo_path, ["rev-parse", "HEAD"]),
        "rulesetVersion": report.rulesetVersion,
        "patchModels": sorted({patch.model for patch in patches}) or [],
        "verificationReceipts": [
            {
                "receiptId": receipt["receiptId"],
                "patchId": receipt["patchId"],
                "state": receipt["state"],
                "applyReady": receipt["applyReady"],
                "exportReady": receipt["exportReady"],
                "path": receipt.get("savedReceiptPath"),
            }
            for receipt in verification_receipts
        ],
        "fileInventory": _file_inventory(root_dir),
    }


def _file_inventory(root_dir: Path) -> list[dict]:
    inventory: list[dict] = []
    for path in sorted(root_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {"manifest.json", "SHA256SUMS.txt", "bundle.zip"}:
            continue
        inventory.append(
            {
                "path": path.relative_to(root_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return inventory


def _build_checksums(root_dir: Path) -> str:
    lines: list[str] = []
    for path in sorted(root_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {"SHA256SUMS.txt", "bundle.zip"}:
            continue
        lines.append(f"{_sha256(path)}  {path.relative_to(root_dir).as_posix()}")
    return "\n".join(lines) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(repo_path: Path, args: list[str]) -> str | None:
    if not repo_path.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _build_report_html(
    scan: ScanStatus,
    report: ScanReport,
    patches: list[dict],
    verification_receipts: list[dict],
    warnings: list[str],
    export_id: str,
) -> str:
    summary_cards = [
        ("Risk Level", report.summary.riskLevel),
        ("Estimated Effort", report.summary.estimatedEffort),
        ("Languages", ", ".join(report.build.languages)),
        ("Build Systems", ", ".join(report.build.buildSystems)),
    ]
    coverage = report.coverage
    trust_banner = "".join(f"<li>{escape(note)}</li>" for note in warnings)
    finding_cards = "".join(_finding_html(finding) for finding in report.findings)
    patch_cards = "".join(_patch_html(patch) for patch in patches) or "<p>No patch artifacts were exported.</p>"
    verification_cards = "".join(_verification_html(receipt) for receipt in verification_receipts) or "<p>No patch verification receipts were exported.</p>"
    file_cards = "".join(_file_link_html(path) for path in sorted((Path("report.json"), Path("summary.md"), Path("manifest.json"))))
    score_cards = "".join(
        f"<div class='metric'><span class='mini'>{escape(label)}</span><strong>{escape(value)}</strong></div>"
        for label, value in summary_cards
    )
    checklist = "".join(f"<li>{escape(step)}</li>" for step in report.nextSteps)
    coverage_block = ""
    if coverage is not None:
        coverage_block = (
            "<div class='metric'><span class='mini'>Files Discovered</span><strong>"
            f"{coverage.totalFiles}</strong></div>"
            "<div class='metric'><span class='mini'>Files Scanned</span><strong>"
            f"{coverage.scannedFiles}</strong></div>"
            "<div class='metric'><span class='mini'>Large Files Skipped</span><strong>"
            f"{coverage.skippedLargeFiles}</strong></div>"
            "<div class='metric'><span class='mini'>Ruleset</span><strong>"
            f"{escape(report.rulesetVersion)}</strong></div>"
        )

    payload = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "scanId": scan.scanId,
        "repoUrl": report.repo.url,
        "exportId": export_id,
    }

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ROCmPorter Report - {escape(report.repo.name)}</title>
    <link rel="stylesheet" href="assets/report.css">
  </head>
  <body>
    <div class="page">
      <section class="panel hero">
        <div class="title-row">
          <div>
            <p class="eyebrow">ROCmPorter Export Bundle</p>
            <h1>{escape(report.repo.name)}</h1>
            <p class="path">{escape(report.repo.url)}</p>
          </div>
          <div class="score-box">{report.summary.portabilityScore}</div>
        </div>
        <div class="meta-row">
          <div class="metric"><span class="mini">Scan ID</span><strong>{escape(scan.scanId)}</strong></div>
          <div class="metric"><span class="mini">Branch</span><strong>{escape(report.repo.defaultBranch)}</strong></div>
          <div class="metric"><span class="mini">Generated</span><strong id="generated-at">{escape(report.summary.scanCompletedAt.isoformat())}</strong></div>
          <div class="metric"><span class="mini">Status</span><strong>{escape(scan.status)}</strong></div>
        </div>
      </section>

      <section class="panel banner">
        <strong>Review Required</strong>
        <ul class="warning-list">{trust_banner}</ul>
      </section>

      <section class="panel">
        <div class="score-row">{score_cards}</div>
      </section>

      <section class="panel">
        <div class="split">
          <div>
            <p class="eyebrow">Score Breakdown</p>
            <p>Base score 100. Penalties: critical -24, high -16, medium -8, low -4 per finding.</p>
          </div>
          <div class="controls">
            <button data-filter="all">All</button>
            <button data-filter="critical">Critical</button>
            <button data-filter="high">High</button>
            <button data-filter="medium">Medium</button>
            <button data-filter="low">Low</button>
          </div>
        </div>
      </section>

      <section class="panel">
        <p class="eyebrow">Findings</p>
        <div class="finding-list">{finding_cards}</div>
      </section>

      <section class="panel">
        <p class="eyebrow">Patch Review</p>
        <div class="patch-list">{patch_cards}</div>
      </section>

      <section class="panel">
        <p class="eyebrow">Verification Receipts</p>
        <div class="patch-list">{verification_cards}</div>
      </section>

      <section class="panel">
        <p class="eyebrow">Migration Runbook</p>
        <ol>{checklist}</ol>
      </section>

      <section class="panel">
        <p class="eyebrow">Coverage and Limits</p>
        <div class="score-row">{coverage_block}</div>
      </section>

      <section class="panel">
        <p class="eyebrow">Bundle Files</p>
        <div class="file-list">{file_cards}</div>
      </section>
    </div>
    <script id="rocmporter-data" type="application/json">{json.dumps(payload)}</script>
    <script src="assets/report.js"></script>
  </body>
</html>
"""


def _finding_html(finding) -> str:
    evidence_markup = "".join(
        (
            "<div class='evidence'>"
            f"<div class='path'>{escape(item.path)}</div>"
            f"{_line_label(item.lineStart, item.lineEnd)}"
            f"{f'<div class=\"warning\">Match: {escape(item.matchText)}</div>' if item.matchText else ''}"
            f"{f'<pre>{escape(item.snippet)}</pre>' if item.snippet else ''}"
            "</div>"
        )
        for item in finding.evidence
    )
    return (
        f"<article class='finding' data-severity='{escape(finding.severity)}'>"
        f"<div class='pill'><span class='severity {escape(finding.severity)}'>{escape(finding.severity)}</span>"
        f"<span>{escape(finding.confidence)} confidence</span></div>"
        f"<h3>{escape(finding.title)}</h3>"
        f"<p>{escape(finding.details)}</p>"
        f"<p><strong>Recommendation:</strong> {escape(finding.recommendation)}</p>"
        f"<div class='evidence-list'>{evidence_markup}</div>"
        "</article>"
    )


def _patch_html(patch: dict) -> str:
    warnings = patch.get("warnings") or []
    warning_markup = "".join(
        f"<li class='warning'><strong>{escape(item['severity'])}:</strong> {escape(item['message'])}</li>"
        for item in warnings
    )
    risk = patch.get("riskAssessment")
    risk_markup = ""
    if risk is not None:
        reason_markup = "".join(f"<li>{escape(reason)}</li>" for reason in risk.get("reasons", []))
        risk_markup = (
            f"<p><strong>Risk:</strong> {risk['score']}/100 ({escape(risk['level'])})</p>"
            f"<p>{escape(risk['summary'])}</p>"
            f"{f'<ul>{reason_markup}</ul>' if reason_markup else ''}"
        )
    validation = patch.get("validation")
    validation_markup = ""
    if validation is not None:
        detail_markup = "".join(f"<li>{escape(detail)}</li>" for detail in validation.get("details", []))
        validation_markup = (
            f"<p><strong>Validation:</strong> {escape(validation['state'])} via {escape(validation['tool'])}</p>"
            f"<p>{escape(validation['summary'])}</p>"
            f"{f'<ul>{detail_markup}</ul>' if detail_markup else ''}"
        )
    diff_markup = f"<pre>{escape(patch['diff'])}</pre>" if patch.get("diff") else ""
    saved_path = f"<p class='path'>{escape(patch['savedPatchPath'])}</p>" if patch.get("savedPatchPath") else ""
    patched_snapshot = (
        f"<p class='path'>patched: {escape(patch['savedPatchedFilePath'])}</p>"
        if patch.get("savedPatchedFilePath")
        else ""
    )
    source_snapshot = (
        f"<p class='path'>source: {escape(patch['sourceFilePath'])}</p>"
        if patch.get("sourceFilePath")
        else ""
    )
    return (
        "<article class='patch-card'>"
        f"<div class='pill'><span>{escape(patch['status'])}</span><span>{escape(patch['model'])}</span></div>"
        f"<h3>{escape(patch['evidencePath'])}</h3>"
        f"{f'<p>{escape(patch['rationale'])}</p>' if patch.get('rationale') else ''}"
        f"{risk_markup}"
        f"{validation_markup}"
        f"{saved_path}"
        f"{patched_snapshot}"
        f"{source_snapshot}"
        f"{f'<ul>{warning_markup}</ul>' if warning_markup else ''}"
        f"{diff_markup}"
        "</article>"
    )


def _verification_html(receipt: dict) -> str:
    checks = receipt.get("checks") or []
    check_markup = "".join(
        (
            "<li>"
            f"<strong>{escape(check['state'])}</strong> "
            f"{escape(check['label'])}: {escape(check['message'])}"
            "</li>"
        )
        for check in checks
    )
    receipt_path = receipt.get("savedReceiptPath")
    receipt_link = f"<p class='path'>{escape(receipt_path)}</p>" if receipt_path else ""
    return (
        "<article class='patch-card'>"
        f"<div class='pill'><span>{escape(receipt['state'])}</span><span>{escape(receipt['patchId'])}</span></div>"
        f"<h3>{escape(receipt['receiptId'])}</h3>"
        f"<p>{escape(receipt['summary'])}</p>"
        f"<p><strong>Apply ready:</strong> {escape(str(receipt['applyReady']).lower())}</p>"
        f"<p><strong>Export ready:</strong> {escape(str(receipt['exportReady']).lower())}</p>"
        f"{receipt_link}"
        f"{f'<ul>{check_markup}</ul>' if check_markup else ''}"
        "</article>"
    )


def _file_link_html(path: Path) -> str:
    label = path.name
    return f"<div class='file-card'><a href='{escape(path.as_posix())}'>{escape(label)}</a></div>"


def _line_label(line_start: int | None, line_end: int | None) -> str:
    if line_start is None:
        return "<p class='mini'>Path-level signal</p>"
    if line_end is None or line_end == line_start:
        return f"<p class='mini'>Line {line_start}</p>"
    return f"<p class='mini'>Lines {line_start}-{line_end}</p>"


def _copy_patch_bundle_artifacts(root_dir: Path, patches_dir: Path, patch: PatchResult) -> PatchBundleArtifacts:
    diff_relative = _copy_bundle_file(root_dir, Path(patch.savedPatchPath), patches_dir / Path(patch.savedPatchPath).name) if patch.savedPatchPath else None

    patched_relative = None
    if patch.savedPatchedFilePath:
        patched_relative = _copy_bundle_file(
            root_dir,
            Path(patch.savedPatchedFilePath),
            patches_dir / "generated" / patch.patchId / Path(patch.evidencePath),
        )

    source_relative = None
    if patch.sourceFilePath:
        source_relative = _copy_bundle_file(
            root_dir,
            Path(patch.sourceFilePath),
            patches_dir / "source" / patch.patchId / Path(patch.evidencePath),
        )

    return PatchBundleArtifacts(
        diff_path=diff_relative,
        patched_file_path=patched_relative,
        source_file_path=source_relative,
    )


def _copy_bundle_file(root_dir: Path, source: Path, target: Path) -> str | None:
    if not source.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target.relative_to(root_dir).as_posix()


def _build_export_patch_payload(patch: PatchResult, artifacts: PatchBundleArtifacts) -> dict:
    payload = patch.model_dump(mode="json")
    payload["savedPatchPath"] = artifacts.diff_path
    payload["savedPatchedFilePath"] = artifacts.patched_file_path
    payload["sourceFilePath"] = artifacts.source_file_path
    return payload


export_service = ExportService()
