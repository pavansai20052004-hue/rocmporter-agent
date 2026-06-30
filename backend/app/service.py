from __future__ import annotations

import shutil
import threading
import uuid
import json
from dataclasses import dataclass
from pathlib import Path

from .analyzer import build_report
from .models import ScanProgress, ScanReport, ScanStatus
from .repo_fetcher import clone_repo, repo_name_from_url, validate_repo_url


WORK_ROOT = Path(__file__).resolve().parents[2] / "work"
REPO_ROOT = WORK_ROOT / "temp-repos"
SCAN_ROOT = WORK_ROOT / "scans"


@dataclass
class ScanRecord:
    scan_id: str
    repo_url: str
    status: str = "queued"
    stage: str = "queued"
    percent: int = 0
    error: str | None = None
    report: ScanReport | None = None

    def as_status(self) -> ScanStatus:
        return ScanStatus(
            scanId=self.scan_id,
            status=self.status,
            progress=ScanProgress(stage=self.stage, percent=self.percent),
            repoUrl=self.repo_url,
            error=self.error,
        )


class ScanService:
    def __init__(self) -> None:
        self._records: dict[str, ScanRecord] = {}
        self._lock = threading.Lock()
        REPO_ROOT.mkdir(parents=True, exist_ok=True)
        SCAN_ROOT.mkdir(parents=True, exist_ok=True)
        self._load_records()

    def create_scan(self, repo_url: str) -> ScanStatus:
        normalized_url = validate_repo_url(repo_url)
        record = self._create_record(normalized_url)

        thread = threading.Thread(target=self._run_scan, args=(record.scan_id,), daemon=True)
        thread.start()
        self._persist_record(record)
        return record.as_status()

    def run_scan_blocking(self, repo_url: str) -> tuple[ScanStatus, ScanReport]:
        normalized_url = validate_repo_url(repo_url)
        record = self._create_record(normalized_url)
        self._run_scan(record.scan_id)
        report = self.get_report(record.scan_id)
        if report is None:
            raise RuntimeError(self.get_scan(record.scan_id).error or "Scan did not produce a report")
        return self.get_scan(record.scan_id), report

    def get_scan(self, scan_id: str) -> ScanStatus | None:
        with self._lock:
            record = self._records.get(scan_id)
            return None if record is None else record.as_status()

    def get_report(self, scan_id: str) -> ScanReport | None:
        with self._lock:
            record = self._records.get(scan_id)
            return None if record is None else record.report

    def _run_scan(self, scan_id: str) -> None:
        record = self._records[scan_id]
        repo_path = REPO_ROOT / scan_id

        try:
            self._update(record, status="running", stage="cloning", percent=12)
            default_branch = clone_repo(record.repo_url, repo_path)

            self._update(record, status="running", stage="detecting", percent=42)
            repo_name = repo_name_from_url(record.repo_url)

            self._update(record, status="running", stage="analyzing", percent=72)
            report = build_report(record.repo_url, repo_name, default_branch, repo_path)

            self._update(record, status="running", stage="reporting", percent=94)
            with self._lock:
                record.report = report
                self._persist_record(record)

            self._update(record, status="completed", stage="completed", percent=100)
        except Exception as exc:  # pragma: no cover - defensive path for hackathon robustness
            self._update(record, status="failed", stage="failed", percent=100, error=str(exc))
            shutil.rmtree(repo_path, ignore_errors=True)
        else:
            self._cleanup_previous_repo_versions(scan_id, repo_path)

    def _cleanup_previous_repo_versions(self, scan_id: str, current_repo_path: Path) -> None:
        for path in REPO_ROOT.iterdir():
            if path.name == scan_id or path == current_repo_path:
                continue
            if not path.is_dir():
                continue
            # Retain other scan repos; lifecycle cleanup can be expanded later.
            continue

    def _create_record(self, normalized_url: str) -> ScanRecord:
        scan_id = f"scan_{uuid.uuid4().hex[:10]}"
        record = ScanRecord(scan_id=scan_id, repo_url=normalized_url)
        with self._lock:
            self._records[scan_id] = record
        return record

    def _update(
        self,
        record: ScanRecord,
        *,
        status: str,
        stage: str,
        percent: int,
        error: str | None = None,
    ) -> None:
        with self._lock:
            record.status = status
            record.stage = stage
            record.percent = percent
            record.error = error
            self._persist_record(record)

    def _load_records(self) -> None:
        for status_file in SCAN_ROOT.glob("*.status.json"):
            try:
                payload = json.loads(status_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            report_file = status_file.with_name(status_file.name.replace(".status.json", ".report.json"))
            report = None
            if report_file.exists():
                try:
                    report = ScanReport.model_validate_json(report_file.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    report = None

            status = payload.get("status", "failed")
            stage = payload.get("progress", {}).get("stage", "failed")
            percent = payload.get("progress", {}).get("percent", 100)
            error = payload.get("error")

            if status in {"queued", "running"}:
                status = "failed"
                stage = "failed"
                percent = 100
                error = "Scan interrupted during a previous server session. Please rerun the scan."

            record = ScanRecord(
                scan_id=payload["scanId"],
                repo_url=payload["repoUrl"],
                status=status,
                stage=stage,
                percent=percent,
                error=error,
                report=report,
            )
            self._records[record.scan_id] = record

    def _persist_record(self, record: ScanRecord) -> None:
        status_path = SCAN_ROOT / f"{record.scan_id}.status.json"
        status_path.write_text(record.as_status().model_dump_json(indent=2), encoding="utf-8")

        if record.report is not None:
            report_path = SCAN_ROOT / f"{record.scan_id}.report.json"
            report_path.write_text(record.report.model_dump_json(indent=2), encoding="utf-8")


scan_service = ScanService()
