from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import ReportSummary, RepositoryInfo, ScanReport  # noqa: E402
from app.service import ScanRecord, ScanService  # noqa: E402


class ScanServiceCacheFallbackTests(unittest.TestCase):
    def test_find_cached_repo_snapshot_prefers_latest_matching_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            temp_root = Path(raw_dir)
            repo_root = temp_root / "repos"
            scan_root = temp_root / "scans"
            repo_root.mkdir()
            scan_root.mkdir()

            report = ScanReport(
                repo=RepositoryInfo(url="https://github.com/example/repo", name="repo", defaultBranch="main"),
                summary=ReportSummary(
                    portabilityScore=50,
                    riskLevel="medium",
                    estimatedEffort="2-4 days",
                    scanCompletedAt=datetime.now(UTC),
                ),
                findings=[],
                build={"languages": ["Python"], "buildSystems": ["Python Packaging"], "gpuSignals": []},
                nextSteps=["Review build assumptions."],
            )

            with patch("app.service.REPO_ROOT", repo_root), patch("app.service.SCAN_ROOT", scan_root):
                service = ScanService()
                service._records = {
                    "scan_old": ScanRecord(scan_id="scan_old", repo_url="https://github.com/example/repo", report=report),
                    "scan_new": ScanRecord(scan_id="scan_new", repo_url="https://github.com/example/repo", report=report),
                    "scan_other": ScanRecord(scan_id="scan_other", repo_url="https://github.com/example/other", report=report),
                }

                (repo_root / "scan_old").mkdir()
                (repo_root / "scan_new").mkdir()
                old_report = scan_root / "scan_old.report.json"
                new_report = scan_root / "scan_new.report.json"
                old_report.write_text("{}", encoding="utf-8")
                new_report.write_text("{}", encoding="utf-8")
                __import__("os").utime(old_report, (1000, 1000))
                __import__("os").utime(new_report, (2000, 2000))

                result = service._find_cached_repo_snapshot("https://github.com/example/repo", "scan_current")  # noqa: SLF001

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "scan_new")
        self.assertEqual(result[1], "main")

    def test_restore_cached_repo_snapshot_accepts_clone_timeout_message(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            temp_root = Path(raw_dir)
            repo_root = temp_root / "repos"
            scan_root = temp_root / "scans"
            repo_root.mkdir()
            scan_root.mkdir()

            report = ScanReport(
                repo=RepositoryInfo(url="https://github.com/example/repo", name="repo", defaultBranch="main"),
                summary=ReportSummary(
                    portabilityScore=50,
                    riskLevel="medium",
                    estimatedEffort="2-4 days",
                    scanCompletedAt=datetime.now(UTC),
                ),
                findings=[],
                build={"languages": ["Python"], "buildSystems": ["Python Packaging"], "gpuSignals": []},
                nextSteps=["Review build assumptions."],
            )

            cached_repo = repo_root / "scan_cached"
            cached_repo.mkdir()
            (cached_repo / "README.md").write_text("cached", encoding="utf-8")
            (scan_root / "scan_cached.report.json").write_text("{}", encoding="utf-8")

            with patch("app.service.REPO_ROOT", repo_root), patch("app.service.SCAN_ROOT", scan_root):
                service = ScanService()
                service._records = {
                    "scan_cached": ScanRecord(scan_id="scan_cached", repo_url="https://github.com/example/repo", report=report),
                    "scan_current": ScanRecord(scan_id="scan_current", repo_url="https://github.com/example/repo"),
                }

                target = repo_root / "scan_current"
                target.mkdir()
                (target / "partial.tmp").write_text("partial clone", encoding="utf-8")
                with patch("app.service.shutil.rmtree"):
                    branch = service._restore_cached_repo_snapshot(  # noqa: SLF001 - targeted cache fallback regression test.
                        "https://github.com/example/repo",
                        "scan_current",
                        target,
                        "Command '['git', 'clone']' timed out after 120 seconds",
                    )

                self.assertEqual(branch, "main")
                self.assertTrue((target / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
