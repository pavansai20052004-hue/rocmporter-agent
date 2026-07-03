from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.benchmark_service import BenchmarkService, _build_summary, _build_summary_markdown, _primary_failure_from_receipt, _quality_lane, _select_evidence  # noqa: E402
from app.models import (  # noqa: E402
    EvidenceItem,
    Finding,
    PatchResult,
    PatchRiskAssessment,
    PatchValidation,
    PatchVerificationCheck,
    PatchVerificationReceipt,
    ReportSummary,
    RepositoryInfo,
    ScanProgress,
    ScanReport,
    ScanStatus,
)


class BenchmarkServiceTests(unittest.TestCase):
    def test_select_evidence_prefers_python_file_for_patchability(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build config",
            recommendation="Update build settings.",
            details="Build path is CUDA-specific.",
            confidence="high",
            evidence=[
                EvidenceItem(path="src/kernel.cu", lineStart=1, lineEnd=8),
                EvidenceItem(path="setup.py", lineStart=10, lineEnd=18),
            ],
        )

        selected = _select_evidence(finding, None)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.path, "setup.py")

    def test_select_evidence_prefers_root_setup_when_rocm_context_exists(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build config",
            recommendation="Update build settings.",
            details="Build path is CUDA-specific.",
            confidence="high",
            evidence=[
                EvidenceItem(path="csrc/fused_dense_lib/setup.py", lineStart=10, lineEnd=18, matchText="nvcc"),
                EvidenceItem(path="setup.py", lineStart=70, lineEnd=72, snippet="if IS_ROCM:\n    ROCM_BACKEND = \"ck\"", matchText="NVCC"),
            ],
        )

        selected = _select_evidence(finding, None)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.path, "setup.py")

    def test_select_evidence_prefers_root_cmakelists_for_cuda_build_config(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build config",
            recommendation="Update build settings.",
            details="Build path is CUDA-specific.",
            confidence="high",
            evidence=[
                EvidenceItem(path="cpp/7_libNVVM/CMakeLists.txt", lineStart=47, lineEnd=49, matchText="find_package(CUDA"),
                EvidenceItem(path="CMakeLists.txt", lineStart=5, lineEnd=7, matchText="find_package(CUDA"),
            ],
        )

        selected = _select_evidence(finding, None)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.path, "CMakeLists.txt")

    def test_run_case_file_keeps_export_block_as_benchmark_signal(self) -> None:
        service = BenchmarkService()
        now = datetime.now(UTC)

        scan_status = ScanStatus(
            scanId="scan_bench_case",
            status="completed",
            progress=ScanProgress(stage="completed", percent=100),
            repoUrl="https://github.com/example/repo",
        )
        report = ScanReport(
            repo=RepositoryInfo(url="https://github.com/example/repo", name="repo", defaultBranch="main"),
            summary=ReportSummary(
                portabilityScore=55,
                riskLevel="medium",
                estimatedEffort="2-4 days",
                scanCompletedAt=now,
            ),
            findings=[
                Finding(
                    id="cuda_build_config",
                    severity="high",
                    title="CUDA build config",
                    recommendation="Make the build config ROCm-aware.",
                    details="setup.py uses CUDA-specific helpers.",
                    confidence="high",
                    evidence=[EvidenceItem(path="setup.py", lineStart=12, lineEnd=18)],
                )
            ],
            build={"languages": ["Python"], "buildSystems": ["Python Packaging"], "gpuSignals": ["setup.py"]},
            nextSteps=["Review build assumptions."],
        )
        patch_result = PatchResult(
            patchId="patch_bench_case",
            scanId="scan_bench_case",
            findingId="cuda_build_config",
            evidencePath="setup.py",
            model="qwen2.5-coder:latest",
            status="completed",
            stage="completed",
            createdAt=now,
            updatedAt=now,
            validation=PatchValidation(state="passed", tool="py_compile", summary="Python syntax validation passed."),
            riskAssessment=PatchRiskAssessment(
                score=74,
                level="high",
                summary="High risk review artifact.",
                reasons=["Unsafe build-system rewrite."],
                checklist=["Manual review required."],
                factors=[],
            ),
        )
        verification = PatchVerificationReceipt(
            receiptId="verify_bench_case",
            scanId="scan_bench_case",
            patchId="patch_bench_case",
            generatedAt=now,
            state="failed",
            summary="Patch is not export-ready.",
            applyReady=False,
            exportReady=False,
            checks=[
                PatchVerificationCheck(
                    code="semantic_sanity",
                    label="ROCm Semantic Sanity",
                    state="failed",
                    message="Patch removed the CUDA build path.",
                )
            ],
            savedReceiptPath="receipt.json",
        )

        with tempfile.TemporaryDirectory() as raw_dir:
            temp_dir = Path(raw_dir)
            case_file = temp_dir / "cases.json"
            case_file.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "name": "repo-case",
                                "repoUrl": "https://github.com/example/repo",
                                "findingId": "cuda_build_config",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.benchmark_service.scan_service.run_scan_blocking", return_value=(scan_status, report)),
                patch("app.benchmark_service.patch_service.run_patch_blocking", return_value=patch_result),
                patch("app.benchmark_service.patch_service.verify_patch", return_value=verification),
                patch("app.benchmark_service.export_service.create_export", side_effect=ValueError("Patch verification is not export-ready")),
            ):
                summary = service.run_case_file(
                    case_file,
                    model="qwen2.5-coder:latest",
                    export_formats={"json", "markdown"},
                    output_dir=temp_dir / "artifacts",
                )

        self.assertEqual(summary["totals"]["caseCount"], 1)
        self.assertEqual(summary["totals"]["exportBlocked"], 1)
        case = summary["cases"][0]
        self.assertEqual(case["status"], "export_blocked")
        self.assertEqual(case["qualityLane"], "blocked")
        self.assertIn("Verification blocked", case["judgeSignal"])
        self.assertEqual(case["verificationState"], "failed")
        self.assertIn("not export-ready", case["exportError"])
        self.assertEqual(case["primaryFailure"]["code"], "semantic_sanity")
        self.assertIn("CUDA build path", case["primaryFailure"]["message"])
        self.assertEqual(summary["totals"]["blockedCases"], 1)
        self.assertEqual(summary["totals"]["reviewReadyCases"], 0)

    def test_export_ready_partial_receipt_has_no_primary_failure_for_apply_gate(self) -> None:
        now = datetime.now(UTC)
        verification = PatchVerificationReceipt(
            receiptId="verify_partial",
            scanId="scan_partial",
            patchId="patch_partial",
            generatedAt=now,
            state="warning",
            summary="Export-ready review artifact; workspace apply is blocked by design.",
            applyReady=False,
            exportReady=True,
            checks=[
                PatchVerificationCheck(
                    code="patch_scope",
                    label="Patch Scope",
                    state="warning",
                    message="This is a partial patch for review/export.",
                ),
                PatchVerificationCheck(
                    code="apply_precheck",
                    label="Apply Precheck",
                    state="warning",
                    message="Workspace apply is blocked by design.",
                ),
                PatchVerificationCheck(
                    code="export_precheck",
                    label="Export Precheck",
                    state="passed",
                    message="Patch has the artifacts needed for a portable export.",
                ),
            ],
            savedReceiptPath="receipt.json",
        )

        self.assertIsNone(_primary_failure_from_receipt(verification))

    def test_export_ready_partial_receipt_allows_manual_syntax_warning(self) -> None:
        now = datetime.now(UTC)
        verification = PatchVerificationReceipt(
            receiptId="verify_manual_syntax",
            scanId="scan_manual_syntax",
            patchId="patch_manual_syntax",
            generatedAt=now,
            state="warning",
            summary="Export-ready review artifact; syntax requires manual review.",
            applyReady=False,
            exportReady=True,
            checks=[
                PatchVerificationCheck(
                    code="syntax_validation",
                    label="Syntax Validation",
                    state="warning",
                    message="No local syntax validator is configured for .txt. Manual review is required.",
                ),
                PatchVerificationCheck(
                    code="export_precheck",
                    label="Export Precheck",
                    state="passed",
                    message="Patch has the artifacts needed for a portable export.",
                ),
            ],
            savedReceiptPath="receipt.json",
        )

        self.assertIsNone(_primary_failure_from_receipt(verification))

    def test_run_case_file_surfaces_patch_generation_failure_without_export_step(self) -> None:
        service = BenchmarkService()
        now = datetime.now(UTC)

        scan_status = ScanStatus(
            scanId="scan_patch_fail",
            status="completed",
            progress=ScanProgress(stage="completed", percent=100),
            repoUrl="https://github.com/example/repo",
        )
        report = ScanReport(
            repo=RepositoryInfo(url="https://github.com/example/repo", name="repo", defaultBranch="main"),
            summary=ReportSummary(
                portabilityScore=55,
                riskLevel="medium",
                estimatedEffort="2-4 days",
                scanCompletedAt=now,
            ),
            findings=[
                Finding(
                    id="cuda_build_config",
                    severity="high",
                    title="CUDA build config",
                    recommendation="Make the build config ROCm-aware.",
                    details="setup.py uses CUDA-specific helpers.",
                    confidence="high",
                    evidence=[EvidenceItem(path="setup.py", lineStart=12, lineEnd=18)],
                )
            ],
            build={"languages": ["Python"], "buildSystems": ["Python Packaging"], "gpuSignals": ["setup.py"]},
            nextSteps=["Review build assumptions."],
        )
        patch_result = PatchResult(
            patchId="patch_fail_case",
            scanId="scan_patch_fail",
            findingId="cuda_build_config",
            evidencePath="setup.py",
            model="qwen2.5-coder:latest",
            status="failed",
            stage="failed",
            createdAt=now,
            updatedAt=now,
            error="Single-file patch is not safe for this target.",
        )

        with tempfile.TemporaryDirectory() as raw_dir:
            temp_dir = Path(raw_dir)
            case_file = temp_dir / "cases.json"
            case_file.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "name": "repo-case",
                                "repoUrl": "https://github.com/example/repo",
                                "findingId": "cuda_build_config",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.benchmark_service.scan_service.run_scan_blocking", return_value=(scan_status, report)),
                patch("app.benchmark_service.patch_service.run_patch_blocking", return_value=patch_result),
                patch("app.benchmark_service.patch_service.verify_patch") as verify_mock,
                patch("app.benchmark_service.export_service.create_export") as export_mock,
            ):
                summary = service.run_case_file(
                    case_file,
                    model="qwen2.5-coder:latest",
                    export_formats={"json", "markdown"},
                    output_dir=temp_dir / "artifacts",
                )

        case = summary["cases"][0]
        self.assertEqual(case["status"], "failed")
        self.assertEqual(case["qualityLane"], "generation-failed")
        self.assertIn("not safe", case["judgeSignal"])
        self.assertEqual(case["primaryFailure"]["code"], "patch_generation_failed")
        self.assertIn("not safe", case["primaryFailure"]["message"])
        self.assertEqual(summary["totals"]["generationFailedCases"], 1)
        verify_mock.assert_not_called()
        export_mock.assert_not_called()

    def test_quality_lane_marks_export_ready_apply_blocked_case_as_review_ready(self) -> None:
        result = {
            "status": "completed",
            "applyReady": False,
            "exportReady": True,
            "patchRiskLevel": "medium",
        }

        self.assertEqual(_quality_lane(result), "review-ready")

    def test_quality_lane_separates_infrastructure_failure_from_generation_failure(self) -> None:
        result = {
            "status": "failed",
            "primaryFailure": {
                "code": "benchmark_error",
                "message": "git clone timed out after 120 seconds",
            },
        }

        self.assertEqual(_quality_lane(result), "infrastructure-failed")

    def test_running_summary_tracks_planned_and_remaining_cases(self) -> None:
        now = datetime.now(UTC)
        summary = _build_summary(
            Path("cases.json"),
            "qwen2.5-coder:latest",
            {"json", "markdown"},
            Path("work/benchmark-runs/partial"),
            now,
            [
                {
                    "name": "case-one",
                    "status": "completed",
                    "qualityLane": "review-ready",
                    "applyReady": False,
                    "exportReady": True,
                    "patchRiskLevel": "low",
                    "judgeSignal": "Export-ready review artifact.",
                }
            ],
            total_cases=3,
            run_status="running",
        )
        markdown = _build_summary_markdown(summary)

        self.assertEqual(summary["runStatus"], "running")
        self.assertEqual(summary["totals"]["caseCount"], 1)
        self.assertEqual(summary["totals"]["plannedCaseCount"], 3)
        self.assertEqual(summary["totals"]["remainingCaseCount"], 2)
        self.assertIn("Run status: running", markdown)
        self.assertIn("Cases completed: 1 / 3", markdown)


if __name__ == "__main__":
    unittest.main()
