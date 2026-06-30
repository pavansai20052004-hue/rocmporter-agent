from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .models import BuildProfile, CoverageSummary, Finding, ReportSummary, RepositoryInfo, ScanReport


SKIP_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
}

TEXT_FILE_SUFFIXES = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
    ".cu",
    ".cuh",
    ".cmake",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".sh",
}

LANGUAGE_MAP = {
    ".py": "Python",
    ".cu": "CUDA C++",
    ".cuh": "CUDA C++",
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".h": "C/C++ Headers",
    ".hpp": "C/C++ Headers",
    ".js": "JavaScript",
    ".jsx": "React",
    ".ts": "TypeScript",
    ".tsx": "React",
    ".rs": "Rust",
    ".go": "Go",
}

SNIPPET_RADIUS = 2
RULESET_VERSION = "2026.06.29"

PATTERN_RULES = [
    {
        "id": "cuda_source_files",
        "pattern": re.compile(r"\.(cu|cuh)$", re.IGNORECASE),
        "severity": "high",
        "title": "CUDA translation units detected",
        "details": "The repository includes CUDA-specific source files that will need hipify or manual porting.",
        "recommendation": "Audit .cu/.cuh files and plan a HIP translation path before runtime validation.",
        "kind": "path",
        "confidence": "high",
    },
    {
        "id": "cuda_runtime_headers",
        "pattern": re.compile(r"(cuda_runtime\.h|cuda\.h|cublas|cudnn|curand|cusparse)", re.IGNORECASE),
        "severity": "high",
        "title": "CUDA-only headers or libraries referenced",
        "details": "Direct CUDA library usage usually needs ROCm-specific replacements or compatibility work.",
        "recommendation": "Map CUDA libraries to ROCm or HIP alternatives and verify equivalent package availability.",
        "kind": "content",
        "confidence": "high",
    },
    {
        "id": "pytorch_cuda_api",
        "pattern": re.compile(r"(torch\.cuda|cuda\.is_available|set_device\(|device\s*=\s*['\"]cuda)", re.IGNORECASE),
        "severity": "medium",
        "title": "PyTorch CUDA-specific code paths found",
        "details": "The code appears to assume CUDA device strings or CUDA-only runtime checks.",
        "recommendation": "Refactor device selection to support ROCm-compatible PyTorch builds and generic accelerator detection.",
        "kind": "content",
        "confidence": "medium",
    },
    {
        "id": "cuda_build_config",
        "pattern": re.compile(r"(find_package\(CUDA|enable_language\(CUDA|CMAKE_CUDA|nvcc|--gencode)", re.IGNORECASE),
        "severity": "high",
        "title": "Build configuration is tied to CUDA or NVCC",
        "details": "Build scripts reference NVIDIA-specific toolchains or compile flags.",
        "recommendation": "Replace CUDA-specific CMake and compiler assumptions with HIP/ROCm-aware build logic.",
        "kind": "content",
        "confidence": "high",
    },
    {
        "id": "nvidia_container_signals",
        "pattern": re.compile(r"(nvidia/cuda|nvidia-smi|CUDA_VISIBLE_DEVICES)", re.IGNORECASE),
        "severity": "medium",
        "title": "Container or runtime scripts assume NVIDIA GPUs",
        "details": "Deployment or CI assets are coupled to NVIDIA container images or runtime commands.",
        "recommendation": "Switch images and runtime checks to AMD-compatible container and monitoring workflows.",
        "kind": "content",
        "confidence": "medium",
    },
    {
        "id": "python_gpu_packages",
        "pattern": re.compile(r"(cupy|jax\[cuda\]|tensorflow-gpu|flash-attn|triton)", re.IGNORECASE),
        "severity": "medium",
        "title": "GPU package choices may require ROCm validation",
        "details": "One or more dependencies have CUDA-first installation or compatibility expectations.",
        "recommendation": "Verify ROCm package support and pin known-good versions before migration testing.",
        "kind": "content",
        "confidence": "medium",
    },
]


def build_report(repo_url: str, repo_name: str, default_branch: str, repo_dir: Path) -> ScanReport:
    languages: set[str] = set()
    build_systems: set[str] = set()
    gpu_signals: list[str] = []
    findings_map: dict[str, dict] = {}
    total_files = 0
    scanned_files = 0
    skipped_large_files = 0

    for path in _iter_files(repo_dir):
        total_files += 1
        relative_path = path.relative_to(repo_dir).as_posix()
        suffix = path.suffix.lower()

        language = LANGUAGE_MAP.get(suffix)
        if language:
            languages.add(language)

        lower_name = path.name.lower()
        if lower_name == "dockerfile":
            build_systems.add("Docker")
        if path.name == "CMakeLists.txt" or suffix == ".cmake":
            build_systems.add("CMake")
        if lower_name == "requirements.txt" or lower_name == "pyproject.toml":
            build_systems.add("Python Packaging")
        if lower_name == "package.json":
            build_systems.add("Node.js")
        if lower_name.endswith(".yml") and ".github/workflows/" in relative_path:
            build_systems.add("GitHub Actions")

        for rule in PATTERN_RULES:
            if rule["kind"] == "path" and rule["pattern"].search(relative_path):
                _record_finding(findings_map, rule, _build_path_evidence(relative_path))
                if relative_path not in gpu_signals:
                    gpu_signals.append(relative_path)

        file_size = path.stat().st_size
        if not _should_read(path, file_size):
            if file_size > 1_000_000:
                skipped_large_files += 1
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned_files += 1

        for rule in PATTERN_RULES:
            if rule["kind"] != "content":
                continue

            match = rule["pattern"].search(text)
            if match is None:
                continue

            evidence = _build_content_evidence(relative_path, text, match)
            _record_finding(findings_map, rule, evidence)
            if relative_path not in gpu_signals:
                gpu_signals.append(relative_path)

    findings = list(findings_map.values())
    findings.sort(key=lambda item: _severity_weight(item["severity"]), reverse=True)

    score = _calculate_portability_score(findings)
    risk = "low" if score >= 80 else "medium" if score >= 55 else "high"
    effort = "1-2 days" if score >= 80 else "3-5 days" if score >= 55 else "1-2 weeks"

    next_steps = _build_next_steps(findings)
    if not next_steps:
        next_steps = [
            "Validate the project with a ROCm-enabled PyTorch environment.",
            "Test container and dependency installation on AMD Developer Cloud.",
            "Benchmark one representative workflow after the first successful run.",
        ]

    finding_models = [Finding(**item) for item in findings]
    gpu_signals = gpu_signals[:8]

    return ScanReport(
        repo=RepositoryInfo(url=repo_url, name=repo_name, defaultBranch=default_branch),
        summary=ReportSummary(
            portabilityScore=score,
            riskLevel=risk,
            estimatedEffort=effort,
            scanCompletedAt=datetime.now(UTC),
        ),
        findings=finding_models,
        build=BuildProfile(
            languages=sorted(languages) or ["Unknown"],
            buildSystems=sorted(build_systems) or ["Unknown"],
            gpuSignals=gpu_signals or ["No CUDA-specific files were matched by the current ruleset."],
        ),
        nextSteps=next_steps,
        coverage=CoverageSummary(
            totalFiles=total_files,
            scannedFiles=scanned_files,
            skippedLargeFiles=skipped_large_files,
            skippedDirectories=sorted(SKIP_DIRS),
            supportedTextExtensions=sorted(TEXT_FILE_SUFFIXES),
        ),
        rulesetVersion=RULESET_VERSION,
    )


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _should_read(path: Path, file_size: int | None = None) -> bool:
    size = path.stat().st_size if file_size is None else file_size
    if size > 1_000_000:
        return False
    if path.suffix.lower() in TEXT_FILE_SUFFIXES:
        return True
    return path.name in {"Dockerfile", "CMakeLists.txt", "requirements.txt", "pyproject.toml", "package.json"}


def _build_path_evidence(relative_path: str) -> dict:
    return {
        "path": relative_path,
        "lineStart": None,
        "lineEnd": None,
        "snippet": None,
        "matchText": None,
    }


def _build_content_evidence(relative_path: str, text: str, match: re.Match) -> dict:
    lines = text.splitlines()
    line_start = text.count("\n", 0, match.start()) + 1
    start_index = max(0, line_start - 1 - SNIPPET_RADIUS)
    end_index = min(len(lines), line_start + SNIPPET_RADIUS)
    snippet = "\n".join(lines[start_index:end_index]).strip()

    return {
        "path": relative_path,
        "lineStart": line_start,
        "lineEnd": end_index,
        "snippet": snippet,
        "matchText": match.group(0)[:240],
    }


def _record_finding(findings_map: dict[str, dict], rule: dict, evidence: dict) -> None:
    current = findings_map.get(rule["id"])
    if current is None:
        findings_map[rule["id"]] = {
            "id": rule["id"],
            "severity": rule["severity"],
            "title": rule["title"],
            "evidence": [evidence],
            "recommendation": rule["recommendation"],
            "details": rule["details"],
            "confidence": rule["confidence"],
        }
        return

    existing_paths = {item["path"] for item in current["evidence"]}
    if evidence["path"] not in existing_paths and len(current["evidence"]) < 8:
        current["evidence"].append(evidence)


def _severity_weight(severity: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}[severity]


def _calculate_portability_score(findings: list[dict]) -> int:
    penalties = defaultdict(int)
    for item in findings:
        penalties[item["severity"]] += 1

    score = 100
    score -= penalties["critical"] * 24
    score -= penalties["high"] * 16
    score -= penalties["medium"] * 8
    score -= penalties["low"] * 4
    return max(18, min(score, 98))


def _build_next_steps(findings: list[dict]) -> list[str]:
    next_steps: list[str] = []
    finding_ids = {item["id"] for item in findings}

    if "cuda_source_files" in finding_ids:
        next_steps.append("Run hipify planning on CUDA source files and estimate manual kernel rewrite effort.")
    if "cuda_build_config" in finding_ids:
        next_steps.append("Replace NVCC and CUDA-specific build flags with HIP or ROCm-aware equivalents.")
    if "cuda_runtime_headers" in finding_ids:
        next_steps.append("Map CUDA runtime libraries to ROCm-supported packages before attempting compilation.")
    if "pytorch_cuda_api" in finding_ids:
        next_steps.append("Generalize device-selection logic so PyTorch can target ROCm builds cleanly.")
    if "nvidia_container_signals" in finding_ids:
        next_steps.append("Update container images and scripts to remove NVIDIA runtime assumptions.")

    return next_steps[:5]
