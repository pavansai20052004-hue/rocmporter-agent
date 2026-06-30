from __future__ import annotations

import difflib
import hashlib
import json
import py_compile
import re
import shutil
import subprocess
import threading
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .models import (
    EvidenceItem,
    Finding,
    PatchResult,
    PatchRiskAssessment,
    PatchRiskFactor,
    PatchValidation,
    PatchVerificationCheck,
    PatchVerificationReceipt,
    PatchWarning,
)
from .ollama_service import DEFAULT_OLLAMA_MODEL, OLLAMA_REQUEST_TIMEOUT_SECONDS, generate_structured, resolve_model_name
from .service import REPO_ROOT, SCAN_ROOT, scan_service


PATCH_ROOT = Path(__file__).resolve().parents[2] / "work" / "patches"
VERIFICATION_ROOT = Path(__file__).resolve().parents[2] / "work" / "verifications"
FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
DEFAULT_MODEL = DEFAULT_OLLAMA_MODEL
MAX_FILE_CHARS = 18_000
PATCH_TIMEOUT_SECONDS = OLLAMA_REQUEST_TIMEOUT_SECONDS
REPAIR_MODEL_SUFFIX = "+repair"
PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "patchedContent": {"type": "string"},
        "needsMoreContext": {"type": "boolean"},
    },
    "required": ["rationale", "patchedContent", "needsMoreContext"],
}


@dataclass
class PatchRecord:
    patch_id: str
    scan_id: str
    finding_id: str
    evidence_path: str
    model: str
    status: str
    stage: str | None
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    rationale: str | None = None
    diff: str | None = None
    saved_patch_path: str | None = None
    saved_patched_file_path: str | None = None
    review_required: bool = True
    warnings: list[PatchWarning] = field(default_factory=list)
    validation: PatchValidation | None = None
    risk_assessment: PatchRiskAssessment | None = None
    changed_line_count: int | None = None
    changed_hunk_count: int | None = None
    source_file_path: str | None = None
    source_file_sha256: str | None = None

    def as_result(self) -> PatchResult:
        return PatchResult(
            patchId=self.patch_id,
            scanId=self.scan_id,
            findingId=self.finding_id,
            evidencePath=self.evidence_path,
            model=self.model,
            status=self.status,
            stage=self.stage,
            createdAt=self.created_at,
            updatedAt=self.updated_at,
            error=self.error,
            rationale=self.rationale,
            diff=self.diff,
            savedPatchPath=self.saved_patch_path,
            savedPatchedFilePath=self.saved_patched_file_path,
            reviewRequired=self.review_required,
            warnings=self.warnings,
            validation=self.validation,
            riskAssessment=self.risk_assessment,
            changedLineCount=self.changed_line_count,
            changedHunkCount=self.changed_hunk_count,
            sourceFilePath=self.source_file_path,
            sourceFileSha256=self.source_file_sha256,
        )


@dataclass
class DiffMetrics:
    changed_lines: int
    changed_hunks: int
    added_lines: int
    removed_lines: int
    changed_ranges: list[tuple[int, int]]
    total_original_lines: int


@dataclass(frozen=True)
class ArtifactCleanupResult:
    cleaned_text: str
    removed_lines: list[str]


class PatchService:
    def __init__(self) -> None:
        self._records: dict[str, PatchRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rocmporter-patch")
        PATCH_ROOT.mkdir(parents=True, exist_ok=True)
        VERIFICATION_ROOT.mkdir(parents=True, exist_ok=True)
        self._load_records()

    def create_patch(self, scan_id: str, finding_id: str, evidence_path: str, model: str | None) -> PatchResult:
        resolved_model = resolve_model_name(model or DEFAULT_MODEL)
        existing = self._find_active_patch(scan_id, finding_id, evidence_path, resolved_model)
        if existing is not None:
            return existing.as_result()

        patch_id = self._create_patch_record(scan_id, finding_id, evidence_path, resolved_model)
        self._executor.submit(self._run_patch, patch_id)
        result = self.get_patch(patch_id)
        if result is None:
            raise RuntimeError("Patch job was not persisted correctly")
        return result

    def run_patch_blocking(self, scan_id: str, finding_id: str, evidence_path: str, model: str | None) -> PatchResult:
        patch_id = self._create_patch_record(scan_id, finding_id, evidence_path, resolve_model_name(model or DEFAULT_MODEL))
        self._run_patch(patch_id)
        result = self.get_patch(patch_id)
        if result is None:
            raise RuntimeError("Patch job was not persisted correctly")
        return result

    def repair_patch(self, scan_id: str, patch_id: str) -> PatchResult:
        original = self.get_patch(patch_id)
        if original is None or original.scanId != scan_id:
            raise ValueError("Patch artifact was not found for this scan.")
        if original.status != "completed":
            raise ValueError("Only completed patch artifacts can be repaired.")
        if not original.savedPatchedFilePath:
            raise ValueError("This patch does not include a saved patched file snapshot.")

        report = scan_service.get_report(scan_id)
        if report is None:
            raise ValueError("Scan report is not ready for this patch.")
        finding = next((item for item in report.findings if item.id == original.findingId), None)
        if finding is None:
            raise ValueError("Finding not found for this patch.")
        evidence = next((item for item in finding.evidence if item.path == original.evidencePath), None)
        if evidence is None:
            raise ValueError("Evidence file not found for this patch.")

        source_text = _read_patch_source_text(scan_id, original)
        patched_file = Path(original.savedPatchedFilePath)
        if not patched_file.exists():
            raise ValueError("The saved patched file snapshot is missing from disk.")

        patched_text = patched_file.read_text(encoding="utf-8", errors="ignore")
        cleanup = _remove_model_artifacts(source_text, patched_text)
        if cleanup.cleaned_text == patched_text:
            raise ValueError("No repairable model response artifacts were found in this patch.")

        validation = _validate_patched_content(cleanup.cleaned_text, evidence.path)
        metrics = _measure_diff(source_text, cleanup.cleaned_text)
        diff = _build_unified_diff(source_text, cleanup.cleaned_text, evidence.path)
        if not diff.strip():
            raise ValueError("Repair removed all meaningful file changes.")

        warnings = _build_patch_warnings(validation, evidence, metrics, source_text, cleanup.cleaned_text)
        warnings = [
            warning
            for warning in warnings
            if warning.code != "response_artifact_leak"
        ]
        warnings.append(
            PatchWarning(
                code="auto_repaired_model_artifacts",
                severity="low",
                message=f"Removed {len(cleanup.removed_lines)} model response artifact line(s) from the generated patch.",
            )
        )
        risk_assessment = _assess_patch_risk(
            finding,
            evidence,
            validation,
            warnings,
            metrics,
            source_text,
            cleanup.cleaned_text,
        )

        repaired_patch_id = f"patch_{uuid.uuid4().hex[:10]}"
        now = datetime.now(UTC)
        patch_path = PATCH_ROOT / f"{repaired_patch_id}.diff"
        patch_path.write_text(diff, encoding="utf-8")
        repaired_file_path = _patched_file_output_path(repaired_patch_id, evidence.path)
        repaired_file_path.parent.mkdir(parents=True, exist_ok=True)
        repaired_file_path.write_text(cleanup.cleaned_text, encoding="utf-8")
        repaired_source_file_path = _write_source_snapshot(repaired_patch_id, evidence.path, source_text)

        record = PatchRecord(
            patch_id=repaired_patch_id,
            scan_id=scan_id,
            finding_id=original.findingId,
            evidence_path=original.evidencePath,
            model=f"{original.model}{REPAIR_MODEL_SUFFIX}",
            status="completed",
            stage="repaired",
            created_at=now,
            updated_at=now,
            rationale=_repair_rationale(original, cleanup.removed_lines),
            diff=diff,
            saved_patch_path=str(patch_path),
            saved_patched_file_path=str(repaired_file_path),
            review_required=True,
            warnings=warnings,
            validation=validation,
            risk_assessment=risk_assessment,
            changed_line_count=metrics.changed_lines,
            changed_hunk_count=metrics.changed_hunks,
            source_file_path=str(repaired_source_file_path),
            source_file_sha256=original.sourceFileSha256 or _sha256_text(source_text),
        )
        with self._lock:
            self._records[repaired_patch_id] = record
            self._persist_record(record)
        return record.as_result()

    def verify_patch(self, scan_id: str, patch_id: str) -> PatchVerificationReceipt:
        patch = self.get_patch(patch_id)
        if patch is None or patch.scanId != scan_id:
            raise ValueError("Patch artifact was not found for this scan.")

        checks: list[PatchVerificationCheck] = []
        checks.append(
            _verification_check(
                "patch_status",
                "Patch Status",
                "passed" if patch.status == "completed" else "failed",
                "Patch generation completed." if patch.status == "completed" else f"Patch is {patch.status}, not completed.",
            )
        )

        patch_file = Path(patch.savedPatchPath) if patch.savedPatchPath else None
        patched_file = Path(patch.savedPatchedFilePath) if patch.savedPatchedFilePath else None
        artifact_hashes: dict[str, str] = {}
        if patch.sourceFileSha256:
            artifact_hashes["recordedSourceFileSha256"] = patch.sourceFileSha256
        current_source_path = REPO_ROOT / scan_id / Path(patch.evidencePath)
        if current_source_path.exists():
            artifact_hashes["currentSourceFileSha256"] = _sha256_text(
                current_source_path.read_text(encoding="utf-8", errors="ignore")
            )
        if patch.sourceFilePath and Path(patch.sourceFilePath).exists():
            artifact_hashes["sourceSnapshotSha256"] = _sha256_file(Path(patch.sourceFilePath))
        if patch_file and patch_file.exists():
            artifact_hashes["patchDiffSha256"] = _sha256_file(patch_file)
        if patched_file and patched_file.exists():
            artifact_hashes["patchedFileSha256"] = _sha256_file(patched_file)

        checks.append(_file_exists_check("patch_file", "Saved Patch File", patch_file))
        checks.append(_file_exists_check("patched_snapshot", "Patched File Snapshot", patched_file))

        patched_text = ""
        if patched_file and patched_file.exists():
            patched_text = patched_file.read_text(encoding="utf-8", errors="ignore")
            validation = _validate_patched_content(patched_text, patch.evidencePath)
            checks.append(
                _verification_check(
                    "syntax_validation",
                    "Syntax Validation",
                    _validation_to_receipt_state(validation),
                    validation.summary,
                )
            )
        else:
            checks.append(
                _verification_check(
                    "syntax_validation",
                    "Syntax Validation",
                    "failed",
                    "Syntax validation could not run because the patched file snapshot is missing.",
                )
            )

        artifact_hits = _artifact_tokens_found("\n".join([patched_text, patch.diff or "", patch.rationale or ""]))
        checks.append(
            _verification_check(
                "artifact_scan",
                "Model Artifact Scan",
                "failed" if artifact_hits else "passed",
                (
                    f"Found model response artifact token(s): {', '.join(artifact_hits)}."
                    if artifact_hits
                    else "No model response artifact tokens were found in the patch content, diff, or rationale."
                ),
            )
        )

        leak_warning = any(warning.code == "response_artifact_leak" for warning in patch.warnings)
        blocking_warnings = [warning for warning in patch.warnings if warning.severity in {"critical", "high"}]
        if leak_warning:
            warning_state = "failed"
            warning_message = "Patch still carries a response artifact leak warning."
        elif blocking_warnings:
            warning_state = "warning"
            warning_message = f"Patch has {len(blocking_warnings)} high-severity warning(s) requiring review."
        else:
            warning_state = "passed"
            warning_message = "No blocking patch warnings are present."
        checks.append(_verification_check("warning_scan", "Warning Scan", warning_state, warning_message))

        checks.append(_source_drift_check(scan_id, patch))
        checks.append(_diff_portability_check(patch))
        checks.append(_diff_reconstruction_check(scan_id, patch, patched_text))

        apply_ready = _all_checks_ok(
            checks,
            required={
                "patch_status",
                "patched_snapshot",
                "syntax_validation",
                "artifact_scan",
                "source_drift",
                "warning_scan",
                "diff_reconstruction",
            },
        )
        checks.append(
            _verification_check(
                "apply_precheck",
                "Apply Precheck",
                "passed" if apply_ready else "failed",
                "Patch meets non-writing apply preconditions." if apply_ready else "Patch is not ready to apply without review or regeneration.",
            )
        )

        export_ready = _all_checks_ok(
            checks,
            required={
                "patch_status",
                "patch_file",
                "patched_snapshot",
                "syntax_validation",
                "artifact_scan",
                "source_drift",
                "warning_scan",
                "diff_portability",
                "diff_reconstruction",
            },
        )
        checks.append(
            _verification_check(
                "export_precheck",
                "Export Precheck",
                "passed" if export_ready else "failed",
                "Patch has the artifacts needed for a portable export." if export_ready else "Patch is missing clean artifacts for export.",
            )
        )

        state = _receipt_state(checks)
        receipt_id = f"verify_{uuid.uuid4().hex[:10]}"
        receipt_path = VERIFICATION_ROOT / scan_id / f"{receipt_id}.json"
        receipt = PatchVerificationReceipt(
            receiptId=receipt_id,
            scanId=scan_id,
            patchId=patch_id,
            generatedAt=datetime.now(UTC),
            state=state,
            summary=_verification_summary(state, checks, apply_ready, export_ready),
            applyReady=apply_ready,
            exportReady=export_ready,
            artifactHashes=artifact_hashes,
            checks=checks,
            savedReceiptPath=str(receipt_path),
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
        return receipt

    def _create_patch_record(self, scan_id: str, finding_id: str, evidence_path: str, model: str) -> str:
        report = scan_service.get_report(scan_id)
        if report is None:
            raise ValueError("Scan report is not ready yet")

        finding = next((item for item in report.findings if item.id == finding_id), None)
        if finding is None:
            raise ValueError("Finding not found in the selected scan")

        evidence = next((item for item in finding.evidence if item.path == evidence_path), None)
        if evidence is None:
            raise ValueError("Evidence file not found for the selected finding")

        repo_path = REPO_ROOT / scan_id
        if not repo_path.exists():
            raise ValueError("Repository context is no longer available for this scan. Run the scan again.")

        patch_id = f"patch_{uuid.uuid4().hex[:10]}"
        now = datetime.now(UTC)
        record = PatchRecord(
            patch_id=patch_id,
            scan_id=scan_id,
            finding_id=finding_id,
            evidence_path=evidence_path,
            model=model,
            status="queued",
            stage="queued",
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            self._records[patch_id] = record
            self._persist_record(record)

        return patch_id

    def get_patch(self, patch_id: str) -> PatchResult | None:
        with self._lock:
            record = self._records.get(patch_id)
        if record is None:
            record = self._load_record_from_disk(patch_id)
            if record is None:
                return None
        self._expire_if_timed_out(record)
        self._ensure_record_source_snapshot(record)
        return record.as_result()

    def list_patches(self, scan_id: str) -> list[PatchResult]:
        self._load_scan_records_from_disk(scan_id)
        with self._lock:
            records = [record for record in self._records.values() if record.scan_id == scan_id]
        for record in records:
            self._expire_if_timed_out(record)
            self._ensure_record_source_snapshot(record)
        items = [record.as_result() for record in records]
        return sorted(items, key=lambda item: item.createdAt)

    def _run_patch(self, patch_id: str) -> None:
        record = self._records[patch_id]
        report = scan_service.get_report(record.scan_id)
        if report is None:
            self._update(record, status="failed", error="Scan report is no longer available for this patch job.")
            return

        finding = next((item for item in report.findings if item.id == record.finding_id), None)
        if finding is None:
            self._update(record, status="failed", error="Finding not found for this patch job.")
            return

        evidence = next((item for item in finding.evidence if item.path == record.evidence_path), None)
        if evidence is None:
            self._update(record, status="failed", error="Evidence file not found for this patch job.")
            return

        repo_path = REPO_ROOT / record.scan_id
        target_file = repo_path / Path(evidence.path)

        try:
            self._update(record, status="running", stage="loading_source")
            if not target_file.exists():
                raise RuntimeError("The selected evidence file is missing from the cloned repository context.")

            file_text = target_file.read_text(encoding="utf-8", errors="ignore")
            if len(file_text) > MAX_FILE_CHARS:
                raise RuntimeError("The selected file is too large for reliable local patch generation right now.")

            prompt = _build_patch_prompt(finding, evidence, file_text)
            self._update(record, status="running", stage="generating")
            payload = generate_structured(
                record.model,
                prompt,
                PATCH_SCHEMA,
                system=(
                    "You are an AMD ROCm migration engineer. Modify exactly one file, keep changes minimal, "
                    "and return strict JSON only."
                ),
                options={
                    "temperature": 0.1,
                    "num_predict": 1800,
                },
            )

            if payload.get("needsMoreContext"):
                raise RuntimeError("The model reported that this fix needs more context than a single-file patch can safely provide.")

            patched_content = payload.get("patchedContent", "")
            if not patched_content.strip():
                raise RuntimeError("The local model returned empty patched content.")

            self._update(record, status="running", stage="validating")
            validation = _validate_patched_content(patched_content, evidence.path)
            metrics = _measure_diff(file_text, patched_content)
            diff = _build_unified_diff(file_text, patched_content, evidence.path)
            if not diff.strip():
                raise RuntimeError("The local model did not make a meaningful single-file change.")

            self._update(record, status="running", stage="saving")
            patch_path = PATCH_ROOT / f"{record.patch_id}.diff"
            patch_path.write_text(diff, encoding="utf-8")
            patched_file_path = _patched_file_output_path(record.patch_id, evidence.path)
            patched_file_path.parent.mkdir(parents=True, exist_ok=True)
            patched_file_path.write_text(patched_content, encoding="utf-8")
            source_file_path = _write_source_snapshot(record.patch_id, evidence.path, file_text)
            warnings = _build_patch_warnings(validation, evidence, metrics, file_text, patched_content)
            risk_assessment = _assess_patch_risk(
                finding,
                evidence,
                validation,
                warnings,
                metrics,
                file_text,
                patched_content,
            )

            self._update(
                record,
                status="completed",
                stage="completed",
                rationale=payload.get("rationale", "").strip(),
                diff=diff,
                saved_patch_path=str(patch_path),
                saved_patched_file_path=str(patched_file_path),
                warnings=warnings,
                validation=validation,
                risk_assessment=risk_assessment,
                changed_line_count=metrics.changed_lines,
                changed_hunk_count=metrics.changed_hunks,
                source_file_path=str(source_file_path),
                source_file_sha256=_sha256_text(file_text),
            )
        except Exception as exc:  # pragma: no cover - hackathon robustness path
            self._update(record, status="failed", stage="failed", error=_normalize_patch_error(exc))

    def _update(
        self,
        record: PatchRecord,
        *,
        status: str,
        stage: str | None = None,
        error: str | None = None,
        rationale: str | None = None,
        diff: str | None = None,
        saved_patch_path: str | None = None,
        saved_patched_file_path: str | None = None,
        warnings: list[PatchWarning] | None = None,
        validation: PatchValidation | None = None,
        risk_assessment: PatchRiskAssessment | None = None,
        changed_line_count: int | None = None,
        changed_hunk_count: int | None = None,
        source_file_path: str | None = None,
        source_file_sha256: str | None = None,
    ) -> None:
        with self._lock:
            if _is_timeout_error(record.error) and status != "failed":
                return
            record.status = status
            if stage is not None:
                record.stage = stage
            record.updated_at = datetime.now(UTC)
            record.error = error
            if rationale is not None:
                record.rationale = rationale
            if diff is not None:
                record.diff = diff
            if saved_patch_path is not None:
                record.saved_patch_path = saved_patch_path
            if saved_patched_file_path is not None:
                record.saved_patched_file_path = saved_patched_file_path
            if warnings is not None:
                record.warnings = warnings
            if validation is not None:
                record.validation = validation
            if risk_assessment is not None:
                record.risk_assessment = risk_assessment
            if changed_line_count is not None:
                record.changed_line_count = changed_line_count
            if changed_hunk_count is not None:
                record.changed_hunk_count = changed_hunk_count
            if source_file_path is not None:
                record.source_file_path = source_file_path
            if source_file_sha256 is not None:
                record.source_file_sha256 = source_file_sha256
            self._persist_record(record)

    def _load_records(self) -> None:
        for status_file in PATCH_ROOT.glob("*.json"):
            try:
                payload = json.loads(status_file.read_text(encoding="utf-8"))
                result = PatchResult.model_validate(payload)
            except (OSError, ValueError, json.JSONDecodeError):
                continue

            status = result.status
            error = result.error
            if status in {"queued", "running"}:
                status = "failed"
                error = "Patch generation was interrupted during a previous server session. Please retry."

            record = PatchRecord(
                patch_id=result.patchId,
                scan_id=result.scanId,
                finding_id=result.findingId,
                evidence_path=result.evidencePath,
                model=result.model,
                status=status,
                stage=result.stage or ("failed" if status == "failed" else status),
                created_at=result.createdAt,
                updated_at=result.updatedAt,
                error=error,
                rationale=result.rationale,
                diff=result.diff,
                saved_patch_path=result.savedPatchPath,
                saved_patched_file_path=result.savedPatchedFilePath,
                review_required=result.reviewRequired,
                warnings=result.warnings,
                validation=result.validation,
                risk_assessment=result.riskAssessment,
                changed_line_count=result.changedLineCount,
                changed_hunk_count=result.changedHunkCount,
                source_file_path=result.sourceFilePath,
                source_file_sha256=result.sourceFileSha256,
            )
            self._records[record.patch_id] = record

    def _persist_record(self, record: PatchRecord) -> None:
        payload = record.as_result().model_dump_json(indent=2)
        (PATCH_ROOT / f"{record.patch_id}.json").write_text(payload, encoding="utf-8")

    def _find_active_patch(self, scan_id: str, finding_id: str, evidence_path: str, model: str) -> PatchRecord | None:
        with self._lock:
            for record in self._records.values():
                if (
                    record.scan_id == scan_id
                    and record.finding_id == finding_id
                    and record.evidence_path == evidence_path
                    and record.model == model
                    and record.status in {"queued", "running"}
                ):
                    return record
        return None

    def _load_record_from_disk(self, patch_id: str) -> PatchRecord | None:
        status_file = PATCH_ROOT / f"{patch_id}.json"
        if not status_file.exists():
            return None

        try:
            payload = json.loads(status_file.read_text(encoding="utf-8"))
            result = PatchResult.model_validate(payload)
        except (OSError, ValueError, json.JSONDecodeError):
            return None

        record = PatchRecord(
            patch_id=result.patchId,
            scan_id=result.scanId,
            finding_id=result.findingId,
            evidence_path=result.evidencePath,
            model=result.model,
            status=result.status,
            stage=result.stage,
            created_at=result.createdAt,
            updated_at=result.updatedAt,
            error=result.error,
            rationale=result.rationale,
            diff=result.diff,
            saved_patch_path=result.savedPatchPath,
            saved_patched_file_path=result.savedPatchedFilePath,
            review_required=result.reviewRequired,
            warnings=result.warnings,
            validation=result.validation,
            risk_assessment=result.riskAssessment,
            changed_line_count=result.changedLineCount,
            changed_hunk_count=result.changedHunkCount,
            source_file_path=result.sourceFilePath,
            source_file_sha256=result.sourceFileSha256,
        )
        with self._lock:
            self._records[patch_id] = record
        return record

    def _ensure_record_source_snapshot(self, record: PatchRecord) -> None:
        if record.status != "completed" or not record.source_file_sha256:
            return

        current_source_path = Path(record.source_file_path) if record.source_file_path else None
        if current_source_path and _is_source_snapshot_path(current_source_path) and current_source_path.exists():
            return

        candidates: list[Path] = []
        if current_source_path is not None:
            candidates.append(current_source_path)
        candidates.append(REPO_ROOT / record.scan_id / Path(record.evidence_path))

        for candidate in candidates:
            if not candidate.exists():
                continue
            source_text = candidate.read_text(encoding="utf-8", errors="ignore")
            if _sha256_text(source_text) != record.source_file_sha256:
                continue
            snapshot_path = _write_source_snapshot(record.patch_id, record.evidence_path, source_text)
            with self._lock:
                record.source_file_path = str(snapshot_path)
                record.updated_at = datetime.now(UTC)
                self._persist_record(record)
            return

    def _load_scan_records_from_disk(self, scan_id: str) -> None:
        for status_file in PATCH_ROOT.glob("*.json"):
            try:
                payload = json.loads(status_file.read_text(encoding="utf-8"))
                if payload.get("scanId") != scan_id:
                    continue
                patch_id = payload.get("patchId")
                if not isinstance(patch_id, str) or not patch_id:
                    continue
            except (OSError, json.JSONDecodeError):
                continue

            with self._lock:
                if patch_id in self._records:
                    continue
            self._load_record_from_disk(patch_id)

    def _expire_if_timed_out(self, record: PatchRecord) -> None:
        if record.status not in {"queued", "running"}:
            return

        runtime_seconds = (datetime.now(UTC) - record.created_at).total_seconds()
        if runtime_seconds < PATCH_TIMEOUT_SECONDS:
            return

        self._update(
            record,
            status="failed",
            stage="failed",
            error=(
                f"Local model generation exceeded {PATCH_TIMEOUT_SECONDS} seconds. "
                "Retry with a smaller or faster Ollama model, or choose a simpler evidence file."
            ),
        )


def _build_patch_prompt(finding: Finding, evidence: EvidenceItem, file_text: str) -> str:
    snippet = evidence.snippet or "No focused snippet was captured."
    line_info = "unknown lines"
    if evidence.lineStart is not None:
        line_info = (
            f"lines {evidence.lineStart}-{evidence.lineEnd}"
            if evidence.lineEnd is not None
            else f"line {evidence.lineStart}"
        )

    return f"""
Generate a single-file ROCm migration fix.

Target file: {evidence.path}
Finding id: {finding.id}
Finding title: {finding.title}
Severity: {finding.severity}
Recommendation: {finding.recommendation}
Evidence location: {line_info}
Matched text: {evidence.matchText or "n/a"}

Relevant snippet:
{snippet}

Current file content:
{file_text}

Rules:
- Modify only {evidence.path}
- Return the full revised content of {evidence.path}
- Keep changes minimal and practical
- If a safe fix requires touching other files, set needsMoreContext=true
""".strip()


def _build_unified_diff(original_text: str, patched_text: str, evidence_path: str) -> str:
    diff = difflib.unified_diff(
        original_text.splitlines(keepends=True),
        patched_text.splitlines(keepends=True),
        fromfile=evidence_path,
        tofile=evidence_path,
    )
    return "".join(diff)


def _read_patch_source_text(scan_id: str, patch: PatchResult) -> str:
    candidates: list[Path] = []
    if patch.sourceFilePath:
        candidates.append(Path(patch.sourceFilePath))
    candidates.append(REPO_ROOT / scan_id / Path(patch.evidencePath))

    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="ignore")
    raise ValueError("The source file for this patch is missing. Run the scan again before repairing.")


def _remove_model_artifacts(original_text: str, patched_text: str) -> ArtifactCleanupResult:
    original_lines = set(original_text.splitlines())
    kept_lines: list[str] = []
    removed_lines: list[str] = []

    for line in patched_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped not in original_lines and _is_model_artifact_line(stripped):
            removed_lines.append(stripped)
            continue
        kept_lines.append(line)

    return ArtifactCleanupResult(cleaned_text="".join(kept_lines), removed_lines=removed_lines)


def _is_model_artifact_line(stripped_line: str) -> bool:
    patterns = [
        r'^"?needsMoreContext"?\s*[:=]\s*(true|false)\s*,?$',
        r'^"?patchedContent"?\s*:\s*"?$',
        r'^"?rationale"?\s*:\s*".*"?\s*,?$',
    ]
    return any(re.match(pattern, stripped_line, flags=re.IGNORECASE) for pattern in patterns)


def _repair_rationale(original: PatchResult, removed_lines: list[str]) -> str:
    base = original.rationale or "Repaired generated patch."
    suffix = f" Auto-repair removed {len(removed_lines)} model response artifact line(s)."
    return f"{base}{suffix}"


def _verification_check(code: str, label: str, state: str, message: str) -> PatchVerificationCheck:
    return PatchVerificationCheck(code=code, label=label, state=state, message=message)


def _file_exists_check(code: str, label: str, path: Path | None) -> PatchVerificationCheck:
    if path is None:
        return _verification_check(code, label, "failed", f"{label} is not recorded for this patch.")
    if path.exists():
        return _verification_check(code, label, "passed", f"{label} exists at {path}.")
    return _verification_check(code, label, "failed", f"{label} is missing from disk.")


def _validation_to_receipt_state(validation: PatchValidation) -> str:
    if validation.state == "passed":
        return "passed"
    if validation.state == "unsupported":
        return "warning"
    return "failed"


def _artifact_tokens_found(text: str) -> list[str]:
    tokens = ["needsMoreContext", "patchedContent", '"rationale"']
    return [token for token in tokens if token in text]


def _source_drift_check(scan_id: str, patch: PatchResult) -> PatchVerificationCheck:
    target_file = REPO_ROOT / scan_id / Path(patch.evidencePath)
    if not target_file.exists():
        return _verification_check("source_drift", "Source Drift", "failed", "The scanned workspace target file is missing.")
    if not patch.sourceFileSha256:
        return _verification_check("source_drift", "Source Drift", "warning", "No source hash was recorded for this patch.")

    current_hash = _sha256_text(target_file.read_text(encoding="utf-8", errors="ignore"))
    if current_hash == patch.sourceFileSha256:
        return _verification_check("source_drift", "Source Drift", "passed", "Workspace file matches the source hash used to generate the patch.")
    return _verification_check(
        "source_drift",
        "Source Drift",
        "failed",
        "Workspace file changed since this patch was generated. Regenerate or repair against the current scan state.",
    )


def _diff_portability_check(patch: PatchResult) -> PatchVerificationCheck:
    diff = patch.diff or ""
    drive_path_pattern = re.compile(r"^[+-]{3}\s+[A-Za-z]:\\", re.MULTILINE)
    if drive_path_pattern.search(diff):
        return _verification_check("diff_portability", "Diff Portability", "failed", "Diff headers contain machine-local Windows paths.")
    if patch.evidencePath not in diff:
        return _verification_check("diff_portability", "Diff Portability", "warning", "Diff does not clearly reference the repo-relative evidence path.")
    return _verification_check("diff_portability", "Diff Portability", "passed", "Diff headers use repo-relative paths.")


def _diff_reconstruction_check(scan_id: str, patch: PatchResult, patched_text: str) -> PatchVerificationCheck:
    if not patch.diff:
        return _verification_check("diff_reconstruction", "Diff Reconstruction", "failed", "Patch does not include a unified diff.")
    if not patched_text:
        return _verification_check("diff_reconstruction", "Diff Reconstruction", "failed", "Patched file snapshot is unavailable.")

    try:
        source_text = _read_patch_source_text(scan_id, patch)
    except ValueError as exc:
        return _verification_check("diff_reconstruction", "Diff Reconstruction", "failed", str(exc))

    git_binary = shutil.which("git")
    if git_binary is None:
        return _verification_check("diff_reconstruction", "Diff Reconstruction", "failed", "Git is unavailable, so the unified diff could not be replayed.")

    with tempfile.TemporaryDirectory(prefix="rocmporter_diffcheck_") as temp_dir:
        temp_root = Path(temp_dir)
        target_file = temp_root / Path(patch.evidencePath)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(source_text, encoding="utf-8")
        diff_file = temp_root / "candidate.patch"
        diff_file.write_text(patch.diff, encoding="utf-8")

        check_result = subprocess.run(
            [git_binary, "apply", "--check", "-p0", str(diff_file)],
            cwd=temp_root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if check_result.returncode != 0:
            return _verification_check(
                "diff_reconstruction",
                "Diff Reconstruction",
                "failed",
                _first_stderr_line(check_result) or "Unified diff did not apply cleanly to the recorded source file.",
            )

        apply_result = subprocess.run(
            [git_binary, "apply", "-p0", str(diff_file)],
            cwd=temp_root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if apply_result.returncode != 0:
            return _verification_check(
                "diff_reconstruction",
                "Diff Reconstruction",
                "failed",
                _first_stderr_line(apply_result) or "Unified diff failed during replay.",
            )

        reconstructed_text = target_file.read_text(encoding="utf-8", errors="ignore")
        if reconstructed_text == patched_text:
            return _verification_check(
                "diff_reconstruction",
                "Diff Reconstruction",
                "passed",
                "Unified diff replays cleanly and reconstructs the saved patched snapshot.",
            )
        return _verification_check(
            "diff_reconstruction",
            "Diff Reconstruction",
            "failed",
            "Unified diff replay did not match the saved patched file snapshot.",
        )


def _first_stderr_line(result: subprocess.CompletedProcess[str]) -> str | None:
    return next((line.strip() for line in result.stderr.splitlines() if line.strip()), None)


def _all_checks_ok(checks: list[PatchVerificationCheck], required: set[str]) -> bool:
    states = {check.code: check.state for check in checks}
    return all(states.get(code) == "passed" for code in required)


def _receipt_state(checks: list[PatchVerificationCheck]) -> str:
    if any(check.state == "failed" for check in checks):
        return "failed"
    if any(check.state == "warning" for check in checks):
        return "warning"
    return "passed"


def _verification_summary(
    state: str,
    checks: list[PatchVerificationCheck],
    apply_ready: bool,
    export_ready: bool,
) -> str:
    failed = sum(1 for check in checks if check.state == "failed")
    warnings = sum(1 for check in checks if check.state == "warning")
    if state == "passed":
        return "Verification passed. Patch is ready for workspace apply and portable export review."
    if failed:
        return f"Verification failed with {failed} failed check(s) and {warnings} warning(s). Apply ready: {apply_ready}. Export ready: {export_ready}."
    return f"Verification completed with {warnings} warning(s). Apply ready: {apply_ready}. Export ready: {export_ready}."


def _patched_file_output_path(patch_id: str, evidence_path: str) -> Path:
    relative = Path(evidence_path)
    safe_parent = relative.parent
    safe_name = relative.name or "patched_file"
    return PATCH_ROOT / "generated" / patch_id / safe_parent / safe_name


def _source_file_snapshot_output_path(patch_id: str, evidence_path: str) -> Path:
    relative = Path(evidence_path)
    safe_parent = relative.parent
    safe_name = relative.name or "source_file"
    return PATCH_ROOT / "source" / patch_id / safe_parent / safe_name


def _write_source_snapshot(patch_id: str, evidence_path: str, source_text: str) -> Path:
    source_file_path = _source_file_snapshot_output_path(patch_id, evidence_path)
    source_file_path.parent.mkdir(parents=True, exist_ok=True)
    source_file_path.write_text(source_text, encoding="utf-8")
    return source_file_path


def _is_source_snapshot_path(path: Path) -> bool:
    try:
        path.resolve().relative_to((PATCH_ROOT / "source").resolve())
    except ValueError:
        return False
    return True


def _measure_diff(original_text: str, patched_text: str) -> DiffMetrics:
    original_lines = original_text.splitlines()
    patched_lines = patched_text.splitlines()
    matcher = difflib.SequenceMatcher(a=original_lines, b=patched_lines)
    changed_lines = 0
    changed_hunks = 0
    added_lines = 0
    removed_lines = 0
    changed_ranges: list[tuple[int, int]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_hunks += 1
        changed_lines += max(i2 - i1, j2 - j1)
        added_lines += j2 - j1
        removed_lines += i2 - i1
        start_line = i1 + 1
        end_line = max(i1 + 1, i2)
        changed_ranges.append((start_line, end_line))

    return DiffMetrics(
        changed_lines=changed_lines,
        changed_hunks=changed_hunks,
        added_lines=added_lines,
        removed_lines=removed_lines,
        changed_ranges=changed_ranges,
        total_original_lines=len(original_lines),
    )


def _build_patch_warnings(
    validation: PatchValidation,
    evidence: EvidenceItem,
    metrics: DiffMetrics,
    original_text: str,
    patched_text: str,
) -> list[PatchWarning]:
    warnings: list[PatchWarning] = []

    if validation.state == "failed":
        warnings.append(
            PatchWarning(
                code="syntax_validation_failed",
                severity="high",
                message=validation.summary,
            )
        )
    elif validation.state == "unsupported":
        warnings.append(
            PatchWarning(
                code="syntax_validation_unsupported",
                severity="low",
                message=validation.summary,
            )
        )

    total_lines = max(metrics.total_original_lines, 1)
    if metrics.changed_lines > max(80, int(total_lines * 0.35)):
        warnings.append(
            PatchWarning(
                code="large_single_file_edit",
                severity="medium",
                message=(
                    f"This patch changes about {metrics.changed_lines} lines in one file. "
                    "Review carefully before applying it."
                ),
            )
        )

    if metrics.removed_lines >= 20 and metrics.removed_lines > metrics.added_lines * 2:
        warnings.append(
            PatchWarning(
                code="destructive_line_removal",
                severity="high",
                message="This patch removes substantially more lines than it adds.",
            )
        )

    if evidence.lineStart is not None and metrics.changed_ranges:
        focus_start = max(1, evidence.lineStart - 10)
        focus_end = (evidence.lineEnd or evidence.lineStart) + 10
        overlaps_focus = any(not (end < focus_start or start > focus_end) for start, end in metrics.changed_ranges)
        if not overlaps_focus:
            warnings.append(
                PatchWarning(
                    code="change_outside_evidence_window",
                    severity="high",
                    message="The patch edits lines well outside the evidence window that triggered this finding.",
                )
            )

    suspicious_tokens = ["needsMoreContext=", "\"patchedContent\"", "\"rationale\""]
    leaked_token = next((token for token in suspicious_tokens if token in patched_text and token not in original_text), None)
    if leaked_token is not None:
        warnings.append(
            PatchWarning(
                code="response_artifact_leak",
                severity="high",
                message=f"The generated file appears to contain model control text ({leaked_token}).",
            )
        )

    return warnings


def _assess_patch_risk(
    finding: Finding,
    evidence: EvidenceItem,
    validation: PatchValidation,
    warnings: list[PatchWarning],
    metrics: DiffMetrics,
    original_text: str,
    patched_text: str,
) -> PatchRiskAssessment:
    factors: list[PatchRiskFactor] = []
    score = 8

    if validation.state == "failed":
        factors.append(
            PatchRiskFactor(
                code="syntax_failed",
                label="Syntax validation failed",
                points=40,
                detail="The generated file does not pass the available local syntax validator.",
            )
        )
    elif validation.state == "unsupported":
        factors.append(
            PatchRiskFactor(
                code="syntax_unsupported",
                label="Syntax validation unavailable",
                points=14,
                detail="This file type does not have a trustworthy local syntax validator in the current workspace.",
            )
        )

    warning_points = {
        "response_artifact_leak": 32,
        "change_outside_evidence_window": 22,
        "destructive_line_removal": 22,
        "large_single_file_edit": 14,
        "syntax_validation_failed": 30,
        "syntax_validation_unsupported": 12,
    }
    for warning in warnings:
        points = warning_points.get(warning.code, 10)
        factors.append(
            PatchRiskFactor(
                code=warning.code,
                label=warning.code.replace("_", " ").title(),
                points=points,
                detail=warning.message,
            )
        )

    for factor in _cuda_semantic_risk_factors(finding, evidence, original_text, patched_text):
        factors.append(factor)

    if metrics.changed_hunks >= 4:
        factors.append(
            PatchRiskFactor(
                code="multi_hunk_edit",
                label="Multiple edit regions",
                points=8,
                detail="The patch touches several separate parts of the file, which increases review complexity.",
            )
        )

    if metrics.changed_lines <= 6 and not warnings:
        score -= 4

    score += sum(factor.points for factor in factors)
    score = max(0, min(score, 100))

    level = "low" if score < 35 else "medium" if score < 65 else "high"
    reasons = [factor.detail for factor in sorted(factors, key=lambda item: item.points, reverse=True)[:4]]
    if not reasons:
        reasons = ["The patch is compact and aligned with the evidence window, but it still requires human review."]

    summary = (
        f"{level.title()} review risk for {finding.id}: "
        + (reasons[0] if reasons else "manual verification is still required.")
    )

    return PatchRiskAssessment(
        score=score,
        level=level,
        summary=summary,
        reasons=reasons,
        checklist=_build_review_checklist(finding, evidence, validation, warnings, patched_text),
        factors=sorted(factors, key=lambda item: item.points, reverse=True),
    )


def _cuda_semantic_risk_factors(
    finding: Finding,
    evidence: EvidenceItem,
    original_text: str,
    patched_text: str,
) -> list[PatchRiskFactor]:
    lowered = patched_text.lower()
    original_lowered = original_text.lower()
    factors: list[PatchRiskFactor] = []

    def add_factor(code: str, label: str, points: int, detail: str) -> None:
        factors.append(PatchRiskFactor(code=code, label=label, points=points, detail=detail))

    if finding.id == "cuda_build_config":
        residual_tokens = [token for token in ["nvcc", "cudaextension", "cuda_home", "cmake_cuda", "find_package(cuda"] if token in lowered]
        if residual_tokens:
            add_factor(
                "residual_cuda_build_markers",
                "Residual CUDA build markers",
                20,
                f"The file still contains CUDA-specific build markers after the patch: {', '.join(residual_tokens)}.",
            )
        if "hipcc" in lowered and "cudaextension" in lowered:
            add_factor(
                "mixed_build_toolchain",
                "Mixed CUDA and HIP build flow",
                16,
                "The patch introduces HIP compiler references while CUDA extension wiring still appears in the same file.",
            )

    if finding.id == "cuda_runtime_headers":
        runtime_tokens = [token for token in ["cuda_runtime.h", "cuda.h", "aten/cuda", "c10::cuda"] if token in lowered]
        if runtime_tokens:
            add_factor(
                "residual_cuda_runtime",
                "Residual CUDA runtime usage",
                22,
                f"The file still references CUDA runtime symbols: {', '.join(runtime_tokens)}.",
            )

    if finding.id == "pytorch_cuda_api":
        api_tokens = [token for token in ["torch.cuda", "\"cuda\"", "'cuda'", "cuda.is_available"] if token in lowered]
        if api_tokens:
            add_factor(
                "residual_cuda_api",
                "Residual CUDA runtime assumptions",
                16,
                f"The patch still leaves CUDA-specific runtime checks or device strings: {', '.join(api_tokens)}.",
            )

    if finding.id == "cuda_source_files":
        if Path(evidence.path).suffix.lower() in {".cu", ".cuh", ".cpp", ".hpp", ".h"} and "hip" not in lowered:
            add_factor(
                "no_hip_signal",
                "No HIP migration signal",
                12,
                "The file still looks CUDA-shaped and does not show any HIP or ROCm-specific migration markers.",
            )

    if lowered.count("hip") > original_lowered.count("hip") and "rocm" not in lowered and "amd" not in lowered:
        add_factor(
            "narrow_hip_swap",
            "Narrow compiler-token swap",
            10,
            "The patch adds HIP terminology but may not add the broader ROCm migration context needed for a reliable fix.",
        )

    return factors


def _build_review_checklist(
    finding: Finding,
    evidence: EvidenceItem,
    validation: PatchValidation,
    warnings: list[PatchWarning],
    patched_text: str,
) -> list[str]:
    checklist = [
        f"Confirm the edits around {evidence.path} actually address the {finding.id} finding and nothing unrelated.",
        "Run the relevant build or test path on a ROCm-capable environment before applying this patch broadly.",
        "Verify the unified diff does not remove project logic outside the intended migration scope.",
    ]

    if validation.state != "passed":
        checklist.append("Run an additional syntax or compile check locally because the available validation was not fully conclusive.")

    if any(item.code == "response_artifact_leak" for item in warnings):
        checklist.append("Remove any model control text or prompt artifacts before using this patch.")

    if finding.id in {"cuda_build_config", "cuda_runtime_headers", "cuda_source_files", "pytorch_cuda_api"}:
        checklist.append("Check for remaining CUDA-only symbols, includes, device strings, or toolchain references in the same file.")

    if Path(evidence.path).suffix.lower() in {".cu", ".cuh", ".cpp", ".cc", ".cxx", ".hpp", ".h"}:
        checklist.append("Review the patch against your HIP or ROCm translation plan because C++ and CUDA migrations are rarely complete in one file.")

    if "hipcc" in patched_text.lower():
        checklist.append("Verify that the surrounding build system, extension type, and dependency wiring are also HIP-compatible.")

    return checklist[:6]


def _validate_patched_content(patched_content: str, evidence_path: str) -> PatchValidation:
    suffix = Path(evidence_path).suffix.lower()

    if suffix == ".py":
        return _validate_python(patched_content, suffix)

    if suffix == ".json":
        try:
            json.loads(patched_content)
            return PatchValidation(
                state="passed",
                tool="json",
                summary="JSON syntax validation passed.",
            )
        except json.JSONDecodeError as exc:
            return PatchValidation(
                state="failed",
                tool="json",
                summary="JSON syntax validation failed.",
                details=[str(exc)],
            )

    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        return _validate_javascript_family(patched_content, suffix)

    return PatchValidation(
        state="unsupported",
        tool="review",
        summary=f"No local syntax validator is configured for {suffix or 'this file type'}. Manual review is required.",
    )


def _validate_python(patched_content: str, suffix: str) -> PatchValidation:
    with tempfile.TemporaryDirectory(prefix="rocmporter_pycheck_") as temp_dir:
        temp_path = Path(temp_dir) / f"candidate{suffix}"
        temp_path.write_text(patched_content, encoding="utf-8")
        try:
            py_compile.compile(str(temp_path), doraise=True)
            return PatchValidation(
                state="passed",
                tool="py_compile",
                summary="Python syntax validation passed.",
            )
        except py_compile.PyCompileError as exc:
            return PatchValidation(
                state="failed",
                tool="py_compile",
                summary="Python syntax validation failed.",
                details=[str(exc)],
            )


def _validate_javascript_family(patched_content: str, suffix: str) -> PatchValidation:
    with tempfile.TemporaryDirectory(prefix="rocmporter_jscheck_") as temp_dir:
        temp_path = Path(temp_dir) / f"candidate{suffix}"
        temp_path.write_text(patched_content, encoding="utf-8")

        oxlint_binary = _resolve_oxlint_binary()
        if oxlint_binary is not None:
            try:
                result = subprocess.run(
                    [str(oxlint_binary), str(temp_path), "--silent"],
                    cwd=FRONTEND_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
            except OSError as exc:
                return PatchValidation(
                    state="unsupported",
                    tool="oxlint",
                    summary="The local JavaScript or TypeScript validator could not be launched.",
                    details=[str(exc)],
                )

            details = _stderr_details(result)
            if result.returncode == 0:
                return PatchValidation(
                    state="passed",
                    tool="oxlint",
                    summary="JavaScript or TypeScript syntax validation passed.",
                )
            return PatchValidation(
                state="failed",
                tool="oxlint",
                summary="JavaScript or TypeScript syntax validation failed.",
                details=details or ["oxlint reported a parse error."],
            )

        node_binary = shutil.which("node")
        if node_binary and suffix in {".js", ".mjs", ".cjs"}:
            try:
                result = subprocess.run(
                    [node_binary, "--check", str(temp_path)],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
            except OSError as exc:
                return PatchValidation(
                    state="unsupported",
                    tool="node --check",
                    summary="The local JavaScript validator could not be launched.",
                    details=[str(exc)],
                )

            details = _stderr_details(result)
            if result.returncode == 0:
                return PatchValidation(
                    state="passed",
                    tool="node --check",
                    summary="JavaScript syntax validation passed.",
                )
            return PatchValidation(
                state="failed",
                tool="node --check",
                summary="JavaScript syntax validation failed.",
                details=details or ["node --check reported a parse error."],
            )

    return PatchValidation(
        state="unsupported",
        tool="review",
        summary="No local JavaScript or TypeScript syntax validator is available. Manual review is required.",
    )


def _resolve_oxlint_binary() -> Path | None:
    candidate_names = ["oxlint.cmd", "oxlint.exe", "oxlint"]
    for name in candidate_names:
        path = FRONTEND_ROOT / "node_modules" / ".bin" / name
        if path.exists():
            return path
    return None


def _stderr_details(result: subprocess.CompletedProcess[str]) -> list[str]:
    details = [line.strip() for line in result.stderr.splitlines() if line.strip()]
    if not details:
        details = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return details[:6]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_patch_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if "timed out" in message.lower():
        return (
            f"Local model generation exceeded {PATCH_TIMEOUT_SECONDS} seconds. "
            "Retry with a smaller or faster Ollama model, or choose a simpler evidence file."
        )
    return message


def _is_timeout_error(message: str | None) -> bool:
    if not message:
        return False
    return "exceeded" in message.lower() and "seconds" in message.lower()


patch_service = PatchService()
