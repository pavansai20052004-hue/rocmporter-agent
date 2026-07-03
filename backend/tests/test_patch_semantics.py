from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import EvidenceItem, Finding, PatchResult, PatchVerificationCheck  # noqa: E402
from app.patch_service import (  # noqa: E402
    _all_checks_ok,
    _apply_precheck_message,
    _apply_precheck_state,
    _assess_patch_risk,
    _build_conservative_partial_patch,
    _build_patch_scope_prompt,
    _build_unified_diff,
    _build_patch_prompt,
    _build_patch_warnings,
    _measure_diff,
    _patch_scope_check,
    _semantic_sanity_check,
    _texts_match_for_replay,
    _validate_patched_content,
    _verification_summary,
)


class PatchSemanticGuardTests(unittest.TestCase):
    def test_pytorch_rocm_api_hallucination_blocks_apply_readiness(self) -> None:
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
                    lineStart=13,
                    lineEnd=22,
                    snippet="from torch.utils.cpp_extension import CUDAExtension, CUDA_HOME",
                    matchText="CUDAExtension",
                )
            ],
        )
        evidence = finding.evidence[0]
        original_text = (
            "from torch.utils.cpp_extension import CppExtension, CUDAExtension, BuildExtension, CUDA_HOME\n"
            "\n"
            "extra_compile_args = {'cxx': ['-O3'], 'nvcc': ['-O3']}\n"
            "extensions_cuda_dir = os.path.join(extensions_dir, 'cuda')\n"
        )
        patched_text = (
            "from torch.utils.cpp_extension import CppExtension, ROCmExtension, BuildExtension, ROCm_HOME\n"
            "\n"
            "extra_compile_args = {'cxx': ['-O3'], 'rocm': ['-O3']}\n"
            "extensions_rocm_dir = os.path.join(extensions_dir, 'rocm')\n"
        )

        validation = _validate_patched_content(patched_text, evidence.path)
        metrics = _measure_diff(original_text, patched_text)
        warnings = _build_patch_warnings(validation, evidence, metrics, original_text, patched_text)
        warning_codes = {warning.code for warning in warnings}

        self.assertEqual(validation.state, "passed")
        self.assertIn("invented_pytorch_extension_api", warning_codes)
        self.assertIn("unsupported_pytorch_compile_arg_key", warning_codes)
        self.assertIn("assumed_rocm_source_directory", warning_codes)

        risk = _assess_patch_risk(finding, evidence, validation, warnings, metrics, original_text, patched_text)
        self.assertEqual(risk.level, "high")
        self.assertGreaterEqual(risk.score, 65)

        patch = PatchResult(
            patchId="patch_test",
            scanId="scan_test",
            findingId=finding.id,
            evidencePath=evidence.path,
            model="qwen2.5-coder:latest",
            status="completed",
            stage="completed",
            createdAt=datetime.now(UTC),
            updatedAt=datetime.now(UTC),
            riskAssessment=risk,
        )
        semantic_check = _semantic_sanity_check(patch, patched_text)
        self.assertEqual(semantic_check.state, "failed")
        self.assertEqual(semantic_check.code, "semantic_sanity")

    def test_patch_prompt_warns_model_not_to_invent_pytorch_rocm_extension(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build configuration",
            recommendation="Make setup.py ROCm-aware.",
            details="setup.py imports CUDAExtension.",
            confidence="high",
            evidence=[],
        )
        evidence = EvidenceItem(path="setup.py", matchText="CUDAExtension")

        prompt = _build_patch_prompt(
            finding,
            evidence,
            "from torch.utils.cpp_extension import CUDAExtension\n",
            patch_mode="partial",
            strategy_hint="Preserve the current extension class and add only conservative ROCm-aware guards.",
            triage_rationale="A small single-file patch is realistic.",
        )

        self.assertIn("do not invent torch.utils.cpp_extension APIs", prompt)
        self.assertIn("ROCmExtension", prompt)
        self.assertIn("Patch mode:", prompt)
        self.assertIn("produce a conservative review artifact", prompt)
        self.assertIn("Preserve the current extension class", prompt)
        self.assertNotIn("needsMoreContext=true", prompt)

    def test_patch_scope_prompt_keeps_single_file_safety_decision_separate(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build configuration",
            recommendation="Make setup.py ROCm-aware.",
            details="setup.py imports CUDAExtension.",
            confidence="high",
            evidence=[],
        )
        evidence = EvidenceItem(path="setup.py", matchText="CUDAExtension")

        prompt = _build_patch_scope_prompt(finding, evidence, "from torch.utils.cpp_extension import CUDAExtension\n")

        self.assertIn("single-file patch", prompt)
        self.assertIn("patchMode", prompt)
        self.assertIn("partial", prompt)
        self.assertIn("strategyHint", prompt)

    def test_cuda_build_deletion_is_high_risk_not_a_rocm_migration(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build configuration",
            recommendation="Make the build configuration ROCm-aware.",
            details="setup.py includes CUDAExtension and CUDA sources.",
            confidence="high",
            evidence=[
                EvidenceItem(
                    path="extension_cpp/setup.py",
                    lineStart=20,
                    lineEnd=40,
                    snippet="CUDAExtension if use_cuda else CppExtension",
                    matchText="CUDAExtension",
                )
            ],
        )
        evidence = finding.evidence[0]
        original_text = (
            "from torch.utils.cpp_extension import CppExtension, CUDAExtension, BuildExtension, CUDA_HOME\n"
            "use_cuda = torch.cuda.is_available() and CUDA_HOME is not None\n"
            "extension = CUDAExtension if use_cuda else CppExtension\n"
            "cuda_sources = list(glob.glob(os.path.join(extensions_dir, 'cuda', '*.cu')))\n"
            "if use_cuda:\n"
            "    sources += cuda_sources\n"
        )
        patched_text = (
            "from torch.utils.cpp_extension import CppExtension, BuildExtension\n"
            "use_rocm = torch.cuda.is_available()\n"
            "extension = CppExtension\n"
            "extra_compile_args = {'cxx': ['-DROCM']}\n"
        )

        validation = _validate_patched_content(patched_text, evidence.path)
        metrics = _measure_diff(original_text, patched_text)
        warnings = _build_patch_warnings(validation, evidence, metrics, original_text, patched_text)
        warning_codes = {warning.code for warning in warnings}

        self.assertIn("cuda_build_path_removed", warning_codes)
        self.assertIn("cuda_sources_removed_without_rocm_equivalent", warning_codes)

        risk = _assess_patch_risk(finding, evidence, validation, warnings, metrics, original_text, patched_text)
        self.assertEqual(risk.level, "high")

    def test_unified_diff_is_newline_terminated_for_git_apply(self) -> None:
        diff = _build_unified_diff("alpha\nbeta", "alpha\ngamma", "example.txt")

        self.assertTrue(diff.endswith("\n"))

    def test_replay_match_ignores_final_newline_only(self) -> None:
        self.assertTrue(_texts_match_for_replay("alpha\nbeta\n", "alpha\nbeta"))
        self.assertFalse(_texts_match_for_replay("alpha\nbeta\n", "alpha\ngamma"))

    def test_partial_patch_scope_is_exportable_but_not_apply_ready(self) -> None:
        patch = PatchResult(
            patchId="patch_partial",
            scanId="scan_test",
            findingId="cuda_build_config",
            evidencePath="setup.py",
            model="qwen2.5-coder:latest",
            status="completed",
            stage="completed",
            patchMode="partial",
            createdAt=datetime.now(UTC),
            updatedAt=datetime.now(UTC),
        )

        check = _patch_scope_check(patch)

        self.assertEqual(check.state, "warning")
        self.assertIn("partial patch", check.message.lower())

    def test_partial_apply_gate_is_warning_not_failed_receipt_state(self) -> None:
        patch = PatchResult(
            patchId="patch_partial",
            scanId="scan_test",
            findingId="cuda_build_config",
            evidencePath="setup.py",
            model="qwen2.5-coder:latest",
            status="completed",
            stage="completed",
            patchMode="partial",
            createdAt=datetime.now(UTC),
            updatedAt=datetime.now(UTC),
        )
        checks = [
            PatchVerificationCheck(
                code="apply_precheck",
                label="Apply Precheck",
                state=_apply_precheck_state(patch, apply_ready=False),
                message=_apply_precheck_message(patch, apply_ready=False),
            ),
            PatchVerificationCheck(
                code="export_precheck",
                label="Export Precheck",
                state="passed",
                message="Patch has the artifacts needed for a portable export.",
            ),
        ]

        self.assertEqual(checks[0].state, "warning")
        self.assertIn("blocked by design", checks[0].message)
        summary = _verification_summary("warning", checks, apply_ready=False, export_ready=True)
        self.assertIn("Export-ready review artifact", summary)
        self.assertIn("blocked by design", summary)

    def test_conservative_partial_patch_for_extension_cpp_preserves_cuda_path(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build configuration",
            recommendation="Make setup.py ROCm-aware.",
            details="setup.py imports CUDAExtension.",
            confidence="high",
            evidence=[EvidenceItem(path="extension_cpp/setup.py", lineStart=27, lineEnd=30, matchText="CUDA_HOME")],
        )
        source = (
            "def get_extensions():\n"
            "    debug_mode = os.getenv(\"DEBUG\", \"0\") == \"1\"\n"
            "    use_cuda = os.getenv(\"USE_CUDA\", \"1\") == \"1\"\n"
            "    use_cuda = use_cuda and torch.cuda.is_available() and CUDA_HOME is not None\n"
            "    extension = CUDAExtension if use_cuda else CppExtension\n"
        )

        patched = _build_conservative_partial_patch(finding, finding.evidence[0], source)

        self.assertIsNotNone(patched)
        patched_text, rationale = patched or ("", "")
        self.assertIn('is_rocm_pytorch = getattr(torch.version, "hip", None) is not None', patched_text)
        self.assertIn("CUDAExtension if use_cuda else CppExtension", patched_text)
        self.assertIn("relax the CUDA_HOME gate", rationale)

    def test_conservative_partial_patch_for_nvcc_probe_keeps_cudaextension(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build configuration",
            recommendation="Make setup.py ROCm-aware.",
            details="setup.py probes nvcc directly.",
            confidence="high",
            evidence=[EvidenceItem(path="csrc/fused_dense_lib/setup.py", lineStart=10, lineEnd=18, matchText="nvcc")],
        )
        source = (
            "def append_nvcc_threads(nvcc_extra_args):\n"
            "    _, bare_metal_version = get_cuda_bare_metal_version(CUDA_HOME)\n"
            "    if bare_metal_version >= Version(\"11.2\"):\n"
            "        nvcc_threads = os.getenv(\"NVCC_THREADS\") or \"4\"\n"
            "        return nvcc_extra_args + [\"--threads\", nvcc_threads]\n"
            "    return nvcc_extra_args\n"
        )

        patched = _build_conservative_partial_patch(finding, finding.evidence[0], source)

        self.assertIsNotNone(patched)
        patched_text, rationale = patched or ("", "")
        self.assertIn('getattr(torch.version, "hip", None) is not None or CUDA_HOME is None', patched_text)
        self.assertIn("subprocess.CalledProcessError", patched_text)
        self.assertIn("nvcc probe tolerant", rationale)

    def test_conservative_partial_patch_for_flash_attention_root_setup_skips_nvcc_threads_on_rocm(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build configuration",
            recommendation="Make setup.py ROCm-aware.",
            details="setup.py uses NVCC thread flags.",
            confidence="high",
            evidence=[EvidenceItem(path="setup.py", lineStart=192, lineEnd=193, matchText="NVCC_THREADS")],
        )
        source = (
            "def append_nvcc_threads(nvcc_extra_args):\n"
            "    return nvcc_extra_args + [\"--threads\", NVCC_THREADS]\n"
        )

        patched = _build_conservative_partial_patch(finding, finding.evidence[0], source)

        self.assertIsNotNone(patched)
        patched_text, rationale = patched or ("", "")
        self.assertIn("if IS_ROCM:", patched_text)
        self.assertIn("return nvcc_extra_args", patched_text)
        self.assertIn("skip NVCC-only thread flags", rationale)

    def test_conservative_partial_patch_for_root_cmakelists_adds_review_mode(self) -> None:
        finding = Finding(
            id="cuda_build_config",
            severity="high",
            title="CUDA build configuration",
            recommendation="Make CMake ROCm-aware.",
            details="Root CMakeLists.txt requires CUDA toolkit.",
            confidence="high",
            evidence=[EvidenceItem(path="CMakeLists.txt", lineStart=3, lineEnd=5, matchText="CUDAToolkit")],
        )
        source = (
            "cmake_minimum_required(VERSION 3.20)\n\n"
            "project(cuda-samples LANGUAGES C CXX CUDA)\n\n"
            "find_package(CUDAToolkit REQUIRED)\n"
            "set(CMAKE_POSITION_INDEPENDENT_CODE ON)\n"
        )

        patched = _build_conservative_partial_patch(finding, finding.evidence[0], source)

        self.assertIsNotNone(patched)
        patched_text, rationale = patched or ("", "")
        self.assertIn("option(ENABLE_ROCM_REVIEW", patched_text)
        self.assertIn("message(WARNING", patched_text)
        self.assertIn("top-level CMake entrypoint", rationale)

    def test_partial_patch_outside_evidence_window_drops_to_medium_severity(self) -> None:
        evidence = EvidenceItem(path="setup.py", lineStart=2, lineEnd=3, matchText="nvcc")
        original_text = "\n".join(f"line_{index}" for index in range(1, 31)) + "\n"
        patched_text = original_text.replace("line_25", "line_25_changed")
        validation = _validate_patched_content("value = 1\n", "setup.py")
        metrics = _measure_diff(original_text, patched_text)

        warnings = _build_patch_warnings(
            validation,
            evidence,
            metrics,
            original_text,
            patched_text,
            patch_mode="partial",
        )

        outside_focus = next((warning for warning in warnings if warning.code == "change_outside_evidence_window"), None)
        self.assertIsNotNone(outside_focus)
        self.assertEqual(outside_focus.severity, "medium")

    def test_all_checks_ok_can_allow_warning_for_export_only_validation(self) -> None:
        checks = [
            PatchVerificationCheck(code="patch_status", label="Patch Status", state="passed", message="ok"),
            PatchVerificationCheck(code="syntax_validation", label="Syntax Validation", state="warning", message="unsupported"),
        ]

        self.assertFalse(_all_checks_ok(checks, required={"patch_status", "syntax_validation"}))
        self.assertTrue(
            _all_checks_ok(
                checks,
                required={"patch_status", "syntax_validation"},
                allow_warning_codes={"syntax_validation"},
            )
        )


if __name__ == "__main__":
    unittest.main()
