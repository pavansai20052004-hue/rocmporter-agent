from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analyzer import build_report  # noqa: E402


class AnalyzerReportTests(unittest.TestCase):
    def test_cuda_repo_signals_are_grouped_into_actionable_findings(self) -> None:
        with tempfile.TemporaryDirectory() as raw_repo_dir:
            repo_dir = Path(raw_repo_dir)
            (repo_dir / "kernels").mkdir()
            (repo_dir / "docker").mkdir()
            (repo_dir / "python").mkdir()

            (repo_dir / "kernels" / "vector_add.cu").write_text(
                '#include <cuda_runtime.h>\n'
                "__global__ void add_kernel(float *out) {}\n",
                encoding="utf-8",
            )
            (repo_dir / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.22)\n"
                "enable_language(CUDA)\n"
                "set(CMAKE_CUDA_ARCHITECTURES 75)\n",
                encoding="utf-8",
            )
            (repo_dir / "python" / "train.py").write_text(
                "import torch\n"
                "device = 'cuda' if torch.cuda.is_available() else 'cpu'\n",
                encoding="utf-8",
            )
            (repo_dir / "docker" / "Dockerfile").write_text(
                "FROM nvidia/cuda:12.4.1-devel-ubuntu22.04\n"
                "RUN nvidia-smi\n",
                encoding="utf-8",
            )
            (repo_dir / "requirements.txt").write_text(
                "torch\ncupy\n",
                encoding="utf-8",
            )

            report = build_report(
                "https://github.com/example/cuda-app",
                "cuda-app",
                "main",
                repo_dir,
            )

        finding_ids = {finding.id for finding in report.findings}
        self.assertIn("cuda_source_files", finding_ids)
        self.assertIn("cuda_runtime_headers", finding_ids)
        self.assertIn("cuda_build_config", finding_ids)
        self.assertIn("pytorch_cuda_api", finding_ids)
        self.assertIn("nvidia_container_signals", finding_ids)
        self.assertIn("python_gpu_packages", finding_ids)
        self.assertLess(report.summary.portabilityScore, 80)
        self.assertEqual(report.summary.riskLevel, "high")
        self.assertIn("CMake", report.build.buildSystems)
        self.assertIn("Docker", report.build.buildSystems)
        self.assertIn("Python Packaging", report.build.buildSystems)
        self.assertIn("CUDA C++", report.build.languages)
        self.assertGreaterEqual(report.coverage.scannedFiles, 5)
        self.assertTrue(any("HIP" in step or "ROCm" in step for step in report.nextSteps))

    def test_clean_python_repo_gets_default_rocm_validation_steps(self) -> None:
        with tempfile.TemporaryDirectory() as raw_repo_dir:
            repo_dir = Path(raw_repo_dir)
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "main.py").write_text(
                "def add(left, right):\n"
                "    return left + right\n",
                encoding="utf-8",
            )

            report = build_report(
                "https://github.com/example/python-app",
                "python-app",
                "main",
                repo_dir,
            )

        self.assertEqual(report.findings, [])
        self.assertGreaterEqual(report.summary.portabilityScore, 90)
        self.assertEqual(report.summary.riskLevel, "low")
        self.assertIn("Python", report.build.languages)
        self.assertEqual(report.build.gpuSignals, ["No CUDA-specific files were matched by the current ruleset."])
        self.assertEqual(
            report.nextSteps[0],
            "Validate the project with a ROCm-enabled PyTorch environment.",
        )


if __name__ == "__main__":
    unittest.main()
