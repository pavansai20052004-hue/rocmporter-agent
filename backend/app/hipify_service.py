"""Deterministic CUDA -> HIP conversion (the "hipify" pass).

This is the mechanical half of ROCmPorter's hybrid migration engine, modeled on
AMD's hipify tooling: a curated mapping of CUDA APIs, headers, types, and
library calls to their HIP/ROCm equivalents, applied with word-boundary regex
substitutions. Deterministic, reviewable, and fast — no model involved.

The LLM is only asked to handle what this pass cannot: build-system semantics,
torch.cuda logic, custom abstractions, and any residual CUDA tokens reported
by `hipify_text`. Patches therefore become mostly deterministic with a small,
clearly-labeled AI-assisted remainder.

If a real `hipify-perl` binary is available (env HIPIFY_PERL_PATH), it is used
instead of the built-in table; the built-in table is the portable default.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Mapping table (curated core of the CUDA->HIP API surface)
# Order matters: longer/more specific patterns first.
# --------------------------------------------------------------------------- #

_HEADER_MAP: list[tuple[str, str]] = [
    (r"<cuda_runtime_api\.h>", "<hip/hip_runtime_api.h>"),
    (r"<cuda_runtime\.h>", "<hip/hip_runtime.h>"),
    (r"<cuda_fp16\.h>", "<hip/hip_fp16.h>"),
    (r"<cuda_bf16\.h>", "<hip/hip_bf16.h>"),
    (r"<cuda\.h>", "<hip/hip_runtime.h>"),
    (r"<cublas_v2\.h>", "<hipblas/hipblas.h>"),
    (r"<cublas\.h>", "<hipblas/hipblas.h>"),
    (r"<curand_kernel\.h>", "<hiprand/hiprand_kernel.h>"),
    (r"<curand\.h>", "<hiprand/hiprand.h>"),
    (r"<cufft\.h>", "<hipfft/hipfft.h>"),
    (r"<cusparse\.h>", "<hipsparse/hipsparse.h>"),
    (r"<cusolverDn\.h>", "<hipsolver/hipsolver.h>"),
    (r"<cudnn\.h>", "<miopen/miopen.h>"),
    (r"<nccl\.h>", "<rccl/rccl.h>"),
    (r"<cub/cub\.cuh>", "<hipcub/hipcub.hpp>"),
    (r"<cooperative_groups\.h>", "<hip/hip_cooperative_groups.h>"),
    (r"<ATen/cuda/CUDAContext\.h>", "<ATen/hip/HIPContext.h>"),
    (r"<c10/cuda/CUDAGuard\.h>", "<c10/hip/HIPGuard.h>"),
    (r"<c10/cuda/CUDAStream\.h>", "<c10/hip/HIPStream.h>"),
]

# Identifier-level mappings (applied with \b word boundaries).
_IDENT_MAP: list[tuple[str, str]] = [
    # ---- runtime: memory ----
    ("cudaMallocManaged", "hipMallocManaged"),
    ("cudaMallocHost", "hipHostMalloc"),
    ("cudaMallocPitch", "hipMallocPitch"),
    ("cudaMallocArray", "hipMallocArray"),
    ("cudaMalloc3D", "hipMalloc3D"),
    ("cudaMallocAsync", "hipMallocAsync"),
    ("cudaMalloc", "hipMalloc"),
    ("cudaFreeHost", "hipHostFree"),
    ("cudaFreeArray", "hipFreeArray"),
    ("cudaFreeAsync", "hipFreeAsync"),
    ("cudaFree", "hipFree"),
    ("cudaMemcpyAsync", "hipMemcpyAsync"),
    ("cudaMemcpyPeerAsync", "hipMemcpyPeerAsync"),
    ("cudaMemcpyPeer", "hipMemcpyPeer"),
    ("cudaMemcpy2DAsync", "hipMemcpy2DAsync"),
    ("cudaMemcpy2D", "hipMemcpy2D"),
    ("cudaMemcpyToSymbolAsync", "hipMemcpyToSymbolAsync"),
    ("cudaMemcpyToSymbol", "hipMemcpyToSymbol"),
    ("cudaMemcpyFromSymbol", "hipMemcpyFromSymbol"),
    ("cudaMemcpy", "hipMemcpy"),
    ("cudaMemsetAsync", "hipMemsetAsync"),
    ("cudaMemset", "hipMemset"),
    ("cudaMemGetInfo", "hipMemGetInfo"),
    ("cudaHostAlloc", "hipHostMalloc"),
    ("cudaHostRegister", "hipHostRegister"),
    ("cudaHostUnregister", "hipHostUnregister"),
    ("cudaHostGetDevicePointer", "hipHostGetDevicePointer"),
    # memcpy kinds
    ("cudaMemcpyHostToDevice", "hipMemcpyHostToDevice"),
    ("cudaMemcpyDeviceToHost", "hipMemcpyDeviceToHost"),
    ("cudaMemcpyDeviceToDevice", "hipMemcpyDeviceToDevice"),
    ("cudaMemcpyHostToHost", "hipMemcpyHostToHost"),
    ("cudaMemcpyDefault", "hipMemcpyDefault"),
    # ---- runtime: device / stream / event ----
    ("cudaGetDeviceProperties", "hipGetDeviceProperties"),
    ("cudaGetDeviceCount", "hipGetDeviceCount"),
    ("cudaGetDevice", "hipGetDevice"),
    ("cudaSetDevice", "hipSetDevice"),
    ("cudaDeviceSynchronize", "hipDeviceSynchronize"),
    ("cudaDeviceReset", "hipDeviceReset"),
    ("cudaDeviceGetAttribute", "hipDeviceGetAttribute"),
    ("cudaDeviceProp", "hipDeviceProp_t"),
    ("cudaStreamCreateWithFlags", "hipStreamCreateWithFlags"),
    ("cudaStreamCreate", "hipStreamCreate"),
    ("cudaStreamDestroy", "hipStreamDestroy"),
    ("cudaStreamSynchronize", "hipStreamSynchronize"),
    ("cudaStreamWaitEvent", "hipStreamWaitEvent"),
    ("cudaStreamNonBlocking", "hipStreamNonBlocking"),
    ("cudaStreamDefault", "hipStreamDefault"),
    ("cudaStream_t", "hipStream_t"),
    ("cudaEventCreateWithFlags", "hipEventCreateWithFlags"),
    ("cudaEventCreate", "hipEventCreate"),
    ("cudaEventDestroy", "hipEventDestroy"),
    ("cudaEventRecord", "hipEventRecord"),
    ("cudaEventSynchronize", "hipEventSynchronize"),
    ("cudaEventElapsedTime", "hipEventElapsedTime"),
    ("cudaEventDisableTiming", "hipEventDisableTiming"),
    ("cudaEvent_t", "hipEvent_t"),
    # ---- errors ----
    ("cudaGetErrorString", "hipGetErrorString"),
    ("cudaGetLastError", "hipGetLastError"),
    ("cudaPeekAtLastError", "hipPeekAtLastError"),
    ("cudaSuccess", "hipSuccess"),
    ("cudaErrorMemoryAllocation", "hipErrorOutOfMemory"),
    ("cudaError_t", "hipError_t"),
    # ---- kernel launch helpers ----
    ("cudaLaunchKernel", "hipLaunchKernel"),
    ("cudaFuncSetCacheConfig", "hipFuncSetCacheConfig"),
    ("cudaOccupancyMaxActiveBlocksPerMultiprocessor", "hipOccupancyMaxActiveBlocksPerMultiprocessor"),
    # ---- libraries ----
    ("cublasCreate", "hipblasCreate"),
    ("cublasDestroy", "hipblasDestroy"),
    ("cublasSetStream", "hipblasSetStream"),
    ("cublasSgemm", "hipblasSgemm"),
    ("cublasDgemm", "hipblasDgemm"),
    ("cublasHandle_t", "hipblasHandle_t"),
    ("cublasStatus_t", "hipblasStatus_t"),
    ("CUBLAS_STATUS_SUCCESS", "HIPBLAS_STATUS_SUCCESS"),
    ("CUBLAS_OP_N", "HIPBLAS_OP_N"),
    ("CUBLAS_OP_T", "HIPBLAS_OP_T"),
    ("curandCreateGenerator", "hiprandCreateGenerator"),
    ("curandSetPseudoRandomGeneratorSeed", "hiprandSetPseudoRandomGeneratorSeed"),
    ("curandGenerateUniform", "hiprandGenerateUniform"),
    ("curandState", "hiprandState"),
    ("curand_init", "hiprand_init"),
    ("curand_uniform", "hiprand_uniform"),
    ("cufftPlan1d", "hipfftPlan1d"),
    ("cufftPlan2d", "hipfftPlan2d"),
    ("cufftExecC2C", "hipfftExecC2C"),
    ("cufftHandle", "hipfftHandle"),
    ("ncclAllReduce", "rcclAllReduce"),
    ("ncclComm_t", "rcclComm_t"),
    # ---- half precision ----
    ("__half2float", "__half2float"),  # same name; keep for coverage counting
    # ---- PyTorch C++ ----
    ("at::cuda::getCurrentCUDAStream", "at::hip::getCurrentHIPStream"),
    ("at::cuda::CUDAGuard", "at::hip::HIPGuard"),
    ("c10::cuda::CUDAGuard", "c10::hip::HIPGuard"),
]

_EXTENSION_HINTS = (".cu", ".cuh", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hip")

# Tokens that indicate CUDA remains after the mechanical pass.
_RESIDUAL_PATTERN = re.compile(
    r"\b(cuda[A-Z]\w*|cu(?:blas|rand|fft|sparse|solver|dnn)[A-Z_]\w*|nccl[A-Z]\w*|"
    r"CUDA_[A-Z_]+|__nv_\w+|nvcc|CUcontext|CUdevice|CUmodule|CUfunction)\b"
)


@dataclass
class HipifyResult:
    converted: str
    total_replacements: int = 0
    changes: list[dict] = field(default_factory=list)  # {from, to, count}
    residual_tokens: list[str] = field(default_factory=list)
    used_external_tool: bool = False

    @property
    def fully_converted(self) -> bool:
        return self.total_replacements > 0 and not self.residual_tokens

    def summary_line(self) -> str:
        if self.total_replacements == 0:
            return "hipify: no mechanical CUDA->HIP mappings applied"
        pct = "100%" if self.fully_converted else "partial"
        return (
            f"hipify: {self.total_replacements} deterministic replacement(s) across "
            f"{len(self.changes)} API(s) ({pct} mechanical coverage)"
        )


def is_hipifiable_path(path: str) -> bool:
    lower = path.lower()
    return lower.endswith(_EXTENSION_HINTS)


def hipify_text(source: str, path: str = "") -> HipifyResult:
    """Apply the deterministic CUDA->HIP mapping to source text."""
    external = _try_external_hipify(source)
    if external is not None:
        residual = sorted(set(_RESIDUAL_PATTERN.findall(external)))
        return HipifyResult(
            converted=external,
            total_replacements=1 if external != source else 0,
            changes=[{"from": "hipify-perl", "to": "(external tool)", "count": 1}] if external != source else [],
            residual_tokens=residual,
            used_external_tool=True,
        )

    converted = source
    changes: list[dict] = []
    total = 0

    for pattern, replacement in _HEADER_MAP:
        converted, count = re.subn(pattern, replacement, converted)
        if count:
            changes.append({"from": pattern.strip("\\"), "to": replacement, "count": count})
            total += count

    for name, replacement in _IDENT_MAP:
        if name == replacement:
            continue
        converted, count = re.subn(rf"\b{re.escape(name)}\b", replacement, converted)
        if count:
            changes.append({"from": name, "to": replacement, "count": count})
            total += count

    residual = sorted(set(_RESIDUAL_PATTERN.findall(converted)))
    return HipifyResult(converted=converted, total_replacements=total, changes=changes, residual_tokens=residual)


def _try_external_hipify(source: str) -> str | None:
    """Use a real hipify-perl if configured (HIPIFY_PERL_PATH). Best-effort."""
    tool = os.getenv("HIPIFY_PERL_PATH")
    if not tool or not os.path.exists(tool):
        return None
    try:
        completed = subprocess.run(
            ["perl", tool],
            input=source,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout:
            return completed.stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def build_hybrid_note(result: HipifyResult) -> str:
    """A short note handed to the LLM describing what the mechanical pass did."""
    if result.total_replacements == 0:
        return (
            "No mechanical CUDA->HIP mappings applied (file may be build config or Python). "
            "Perform the migration yourself, keeping changes minimal."
        )
    lines = [
        "A deterministic hipify pass ALREADY converted these CUDA APIs to HIP "
        "(do not re-translate them; treat them as correct):",
    ]
    for change in result.changes[:20]:
        lines.append(f"- {change['from']} -> {change['to']} ({change['count']}x)")
    if result.residual_tokens:
        lines.append(
            "Remaining CUDA-specific tokens that still need your judgment: "
            + ", ".join(result.residual_tokens[:15])
        )
    else:
        lines.append("No residual CUDA tokens detected; verify semantics and finish any build/glue changes.")
    return "\n".join(lines)
