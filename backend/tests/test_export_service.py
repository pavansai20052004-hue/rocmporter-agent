from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.export_service import ARTIFACT_ROOT, _export_block_reason, export_service  # noqa: E402


class ExportServiceTests(unittest.TestCase):
    def test_download_exposed_file_items_use_relative_display_paths(self) -> None:
        scan_id = "scan_path_safety"
        export_id = "export_path_safety"
        export_root = ARTIFACT_ROOT / scan_id / export_id
        report_path = export_root / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("{}", encoding="utf-8")

        item = export_service._file_item(  # noqa: SLF001 - targeted regression test for API path safety.
            scan_id,
            export_id,
            "report_json",
            "Report JSON",
            report_path,
            expose_downloads=True,
        )

        self.assertEqual(item.path, "report.json")
        self.assertEqual(item.downloadPath, "/api/scans/scan_path_safety/exports/export_path_safety/download/report.json")
        self.assertNotIn(str(ARTIFACT_ROOT), item.path)

    def test_export_block_reason_prefers_specific_failed_or_warning_checks(self) -> None:
        receipt = {
            "summary": "Verification failed.",
            "checks": [
                {
                    "code": "syntax_validation",
                    "state": "warning",
                    "message": "No local syntax validator is configured for this file type. Manual review is required.",
                },
                {
                    "code": "apply_precheck",
                    "state": "failed",
                    "message": "Patch is not ready to apply without review or regeneration.",
                },
                {
                    "code": "export_precheck",
                    "state": "failed",
                    "message": "Patch is missing clean artifacts for export.",
                },
            ],
        }

        reason = _export_block_reason(receipt)

        self.assertEqual(reason, "No local syntax validator is configured for this file type. Manual review is required.")


if __name__ == "__main__":
    unittest.main()
