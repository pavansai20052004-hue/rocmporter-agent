from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import PatchApplyResult
from .patch_service import patch_service
from .service import REPO_ROOT, WORK_ROOT


APPLY_ROOT = WORK_ROOT / "applied-patches"


@dataclass
class ApplyRecord:
    apply_id: str
    scan_id: str
    patch_id: str
    status: str
    target_file_path: str
    workspace_root: str
    backup_file_path: str
    applied_file_path: str
    created_at: datetime
    updated_at: datetime
    rollback_available: bool = True
    rollback_reason: str | None = None
    error: str | None = None

    def as_result(self) -> PatchApplyResult:
        return PatchApplyResult(
            applyId=self.apply_id,
            scanId=self.scan_id,
            patchId=self.patch_id,
            status=self.status,
            targetFilePath=self.target_file_path,
            workspaceRoot=self.workspace_root,
            backupFilePath=self.backup_file_path,
            appliedFilePath=self.applied_file_path,
            createdAt=self.created_at,
            updatedAt=self.updated_at,
            rollbackAvailable=self.rollback_available,
            rollbackReason=self.rollback_reason,
            error=self.error,
        )


class ApplyService:
    def __init__(self) -> None:
        self._records: dict[str, ApplyRecord] = {}
        self._lock = threading.Lock()
        APPLY_ROOT.mkdir(parents=True, exist_ok=True)
        self._load_records()

    def apply_patch(self, scan_id: str, patch_id: str) -> PatchApplyResult:
        patch = patch_service.get_patch(patch_id)
        if patch is None or patch.scanId != scan_id:
            raise ValueError("Patch artifact was not found for this scan.")
        receipt = patch_service.verify_patch(scan_id, patch_id)
        if not receipt.applyReady:
            failed = [check for check in receipt.checks if check.state == "failed"]
            reason = failed[0].message if failed else receipt.summary
            raise ValueError(f"Patch verification is not apply-ready: {reason}")
        if patch.status != "completed":
            raise ValueError("Only completed patch artifacts can be applied.")
        if not patch.savedPatchedFilePath:
            raise ValueError("This patch does not include a saved patched file. Regenerate it before applying.")
        if patch.validation and patch.validation.state == "failed":
            raise ValueError("This patch failed local syntax validation. Regenerate or review it before applying.")
        if any(warning.code == "response_artifact_leak" for warning in patch.warnings):
            raise ValueError(
                "This patch still contains model response artifacts. Regenerate or clean it before applying."
            )

        workspace_root = (REPO_ROOT / scan_id).resolve()
        if not workspace_root.exists():
            raise ValueError("The scanned workspace is no longer available. Run the scan again first.")

        patched_file_path = Path(patch.savedPatchedFilePath)
        if not patched_file_path.exists():
            raise ValueError("The saved patched file is missing from disk. Regenerate the patch first.")

        target_file = _resolve_workspace_file(workspace_root, patch.evidencePath)
        if not target_file.exists():
            raise ValueError("The target file is missing from the scanned workspace.")

        current_text = target_file.read_text(encoding="utf-8", errors="ignore")
        if patch.sourceFileSha256:
            current_hash = _sha256_text(current_text)
            if current_hash != patch.sourceFileSha256:
                raise ValueError(
                    "The workspace file has changed since this patch was generated. Regenerate the patch before applying it."
                )

        apply_id = f"apply_{uuid.uuid4().hex[:10]}"
        apply_dir = APPLY_ROOT / scan_id / apply_id
        backup_path = apply_dir / "backup" / patch.evidencePath
        applied_copy_path = apply_dir / "applied" / patch.evidencePath
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        applied_copy_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path.write_text(current_text, encoding="utf-8")
        patched_text = patched_file_path.read_text(encoding="utf-8", errors="ignore")
        applied_copy_path.write_text(patched_text, encoding="utf-8")
        target_file.write_text(patched_text, encoding="utf-8")

        now = datetime.now(UTC)
        record = ApplyRecord(
            apply_id=apply_id,
            scan_id=scan_id,
            patch_id=patch_id,
            status="applied",
            target_file_path=str(target_file),
            workspace_root=str(workspace_root),
            backup_file_path=str(backup_path),
            applied_file_path=str(applied_copy_path),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._records[apply_id] = record
            self._persist_record(record)
        return record.as_result()

    def rollback_patch(self, apply_id: str) -> PatchApplyResult:
        with self._lock:
            record = self._records.get(apply_id)
        if record is None:
            raise ValueError("Applied patch record not found.")
        if record.status == "rolled_back":
            return record.as_result()
        if not record.rollback_available:
            raise ValueError(record.rollback_reason or "Rollback is not available for this apply record.")

        target_file = Path(record.target_file_path)
        backup_file = Path(record.backup_file_path)
        if not backup_file.exists():
            raise ValueError("Backup file is missing, so rollback cannot proceed.")

        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(backup_file.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")

        with self._lock:
            record.status = "rolled_back"
            record.updated_at = datetime.now(UTC)
            self._persist_record(record)
            return record.as_result()

    def get_apply(self, apply_id: str) -> PatchApplyResult | None:
        with self._lock:
            record = self._records.get(apply_id)
            return None if record is None else record.as_result()

    def _load_records(self) -> None:
        for path in APPLY_ROOT.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                result = PatchApplyResult.model_validate(payload)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            record = ApplyRecord(
                apply_id=result.applyId,
                scan_id=result.scanId,
                patch_id=result.patchId,
                status=result.status,
                target_file_path=result.targetFilePath,
                workspace_root=result.workspaceRoot,
                backup_file_path=result.backupFilePath,
                applied_file_path=result.appliedFilePath,
                created_at=result.createdAt,
                updated_at=result.updatedAt,
                rollback_available=result.rollbackAvailable,
                rollback_reason=result.rollbackReason,
                error=result.error,
            )
            self._records[record.apply_id] = record

    def _persist_record(self, record: ApplyRecord) -> None:
        root = APPLY_ROOT / record.scan_id / record.apply_id
        root.mkdir(parents=True, exist_ok=True)
        (root / "apply-result.json").write_text(record.as_result().model_dump_json(indent=2), encoding="utf-8")


def _resolve_workspace_file(workspace_root: Path, relative_path: str) -> Path:
    candidate = (workspace_root / relative_path).resolve()
    if workspace_root not in candidate.parents and candidate != workspace_root:
        raise ValueError("Resolved file path escapes the scanned workspace.")
    return candidate


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


apply_service = ApplyService()
