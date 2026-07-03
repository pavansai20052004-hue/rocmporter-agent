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

from app.github_review_service import GitHubReviewService  # noqa: E402
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
    ScanReport,
)


class GitHubReviewServiceTests(unittest.TestCase):
    def test_review_generation_blocks_non_export_ready_patch_before_writing_or_posting(self) -> None:
        report = _make_report()
        patch_result = _make_patch()
        verification = _make_verification(export_ready=False, apply_ready=False, state="failed")

        with tempfile.TemporaryDirectory() as raw_dir:
            output_dir = Path(raw_dir) / "blocked_review"
            service = GitHubReviewService()

            with (
                patch("app.github_review_service.scan_service.get_report", return_value=report),
                patch("app.github_review_service.patch_service.get_patch", return_value=patch_result),
                patch("app.github_review_service.patch_service.verify_patch", return_value=verification),
                patch("app.github_review_service._post_review") as post_review,
            ):
                with self.assertRaisesRegex(ValueError, "not export-ready"):
                    service.create_review(
                        report.repo.name,
                        patch_result.patchId,
                        repository="example/repo",
                        pull_request_number=12,
                        post_comment=True,
                        output_dir=output_dir,
                    )

        self.assertFalse(output_dir.exists())
        post_review.assert_not_called()

    def test_review_generation_allows_export_ready_patch_when_apply_is_blocked(self) -> None:
        report = _make_report()
        patch_result = _make_patch()
        verification = _make_verification(export_ready=True, apply_ready=False, state="warning")

        with tempfile.TemporaryDirectory() as raw_dir:
            output_dir = Path(raw_dir) / "review_ready"
            service = GitHubReviewService()

            with (
                patch("app.github_review_service.scan_service.get_report", return_value=report),
                patch("app.github_review_service.patch_service.get_patch", return_value=patch_result),
                patch("app.github_review_service.patch_service.verify_patch", return_value=verification),
            ):
                result = service.create_review(
                    report.repo.name,
                    patch_result.patchId,
                    repository="example/repo",
                    output_dir=output_dir,
                )

            payload = json.loads((output_dir / "github-review.json").read_text(encoding="utf-8"))

        self.assertTrue(result.exportReady)
        self.assertFalse(result.applyReady)
        self.assertTrue(result.reviewReady)
        self.assertFalse(result.draftOnly)
        self.assertIn("workspace apply remains blocked", result.commentBody)
        self.assertTrue(payload["exportReady"])
        self.assertFalse(payload["applyReady"])
        self.assertTrue(payload["reviewReady"])
        self.assertFalse(payload["draftOnly"])


def _make_report() -> ScanReport:
    now = datetime.now(UTC)
    finding = Finding(
        id="cuda_build_config",
        severity="high",
        title="CUDA build configuration",
        recommendation="Make the build configuration ROCm-aware.",
        details="setup.py uses CUDAExtension and CUDA_HOME.",
        confidence="high",
        evidence=[
            EvidenceItem(
                path="extension_cpp/setup.py",
                lineStart=3,
                lineEnd=8,
                snippet="from torch.utils.cpp_extension import CUDAExtension, CUDA_HOME",
                matchText="CUDAExtension",
            )
        ],
    )
    return ScanReport(
        repo=RepositoryInfo(url="https://github.com/example/repo", name="scan_review_gate", defaultBranch="main"),
        summary=ReportSummary(
            portabilityScore=68,
            riskLevel="medium",
            estimatedEffort="2-4 days",
            scanCompletedAt=now,
        ),
        findings=[finding],
        build={"languages": ["Python"], "buildSystems": ["Python Packaging"], "gpuSignals": ["setup.py"]},
        nextSteps=["Review generated patch artifacts."],
    )


def _make_patch() -> PatchResult:
    now = datetime.now(UTC)
    return PatchResult(
        patchId="patch_review_gate",
        scanId="scan_review_gate",
        findingId="cuda_build_config",
        evidencePath="extension_cpp/setup.py",
        model="qwen2.5-coder:latest",
        status="completed",
        stage="completed",
        createdAt=now,
        updatedAt=now,
        rationale="Add a ROCm-aware guard while preserving reviewable PyTorch extension wiring.",
        diff=(
            "--- a/extension_cpp/setup.py\n"
            "+++ b/extension_cpp/setup.py\n"
            "@@ -1,3 +1,5 @@\n"
            " from torch.utils.cpp_extension import CUDAExtension, CUDA_HOME\n"
            "+IS_ROCM = torch.version.hip is not None\n"
            "+build_backend = 'rocm' if IS_ROCM else 'cuda'\n"
        ),
        validation=PatchValidation(state="passed", tool="py_compile", summary="Python syntax validation passed."),
        riskAssessment=PatchRiskAssessment(
            score=42,
            level="medium",
            summary="Conservative build-path guard generated for review.",
            reasons=["Hardware validation still needs an AMD/ROCm runner."],
            checklist=["Run ROCm hardware validation before merge."],
            factors=[],
        ),
        changedLineCount=2,
        changedHunkCount=1,
    )


def _make_verification(*, export_ready: bool, apply_ready: bool, state: str) -> PatchVerificationReceipt:
    return PatchVerificationReceipt(
        receiptId=f"receipt_{state}",
        scanId="scan_review_gate",
        patchId="patch_review_gate",
        generatedAt=datetime.now(UTC),
        state=state,
        summary=(
            "Patch artifacts are export-ready, but workspace apply remains blocked."
            if export_ready
            else "Patch artifacts failed export verification."
        ),
        applyReady=apply_ready,
        exportReady=export_ready,
        checks=[
            PatchVerificationCheck(
                code="export_precheck",
                label="Export Precheck",
                state="passed" if export_ready else "failed",
                message="Export artifacts are complete." if export_ready else "Patch is missing clean export artifacts.",
            ),
            PatchVerificationCheck(
                code="apply_precheck",
                label="Apply Precheck",
                state="passed" if apply_ready else "warning",
                message="Apply is ready." if apply_ready else "Workspace apply remains blocked for review.",
            ),
        ],
        savedReceiptPath="work/patches/patch_review_gate/patch-verification.json",
    )


if __name__ == "__main__":
    unittest.main()
