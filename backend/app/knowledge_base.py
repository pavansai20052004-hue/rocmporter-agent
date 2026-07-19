"""Curated CUDA -> ROCm/HIP migration knowledge base (RAG-lite).

Instead of relying on the model's general training, each patch/migration
prompt is grounded with short, curated notes about the API families actually
present in the file being migrated. Retrieval is deterministic: a note is
included only when one of its detection patterns matches the source.

Notes are intentionally terse (the model needs facts, not essays) and
hand-written from ROCm porting guides, HIP documentation, and real-world
porting experience. Keep each note under ~450 characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Note:
    id: str
    patterns: tuple[str, ...]
    text: str


_NOTES: tuple[Note, ...] = (
    Note(
        "warp-size",
        (r"__shfl", r"__ballot", r"__any\b", r"__all\b", r"warpSize", r"\b32\b.*warp|warp.*\b32\b"),
        "AMD CDNA GPUs have warpSize 64 (not 32). Never hardcode 32 for warp width — "
        "use warpSize or HIP's warpSize constant. __shfl*/__ballot exist in HIP but masks are "
        "64-bit; __activemask() is unsupported — restructure to avoid it.",
    ),
    Note(
        "cudnn-miopen",
        (r"cudnn", r"cuDNN"),
        "cuDNN has no 1:1 HIP mapping — the ROCm equivalent is MIOpen (<miopen/miopen.h>), "
        "with a similar-but-different API: descriptors exist but algorithm selection uses "
        "miopenFindConvolutionForwardAlgorithm (benchmarking, not heuristics). Flag any "
        "non-trivial cuDNN usage for manual review rather than guessing.",
    ),
    Note(
        "thrust-rocthrust",
        (r"#include\s*<thrust/", r"\bthrust::"),
        "Thrust code is source-compatible with ROCm via rocThrust: keep #include <thrust/...> "
        "and thrust:: namespaces unchanged; link rocThrust instead of Thrust/CUB. Do not "
        "rewrite thrust:: calls.",
    ),
    Note(
        "cub-hipcub",
        (r"#include\s*<cub/", r"\bcub::"),
        "CUB maps to hipCUB: #include <cub/cub.cuh> -> <hipcub/hipcub.hpp> and the cub:: "
        "namespace becomes hipcub::. APIs (DeviceReduce, BlockScan, etc.) are otherwise 1:1.",
    ),
    Note(
        "nccl-rccl",
        (r"\bnccl", r"NCCL"),
        "NCCL maps to RCCL nearly 1:1: <nccl.h> -> <rccl/rccl.h>, link rccl. The ncclComm_t/"
        "ncclAllReduce-style symbols keep their nccl* names in RCCL, so header+link changes are "
        "usually enough — do not blindly rename nccl* calls.",
    ),
    Note(
        "tensor-cores",
        (r"wmma", r"mma\.sync", r"tensor\s*core", r"__hmma", r"cudaTensorCore"),
        "nvcuda::wmma tensor-core code has no direct HIP equivalent — ROCm uses rocWMMA "
        "(rocwmma::) with a similar fragment API but different tile shapes on CDNA matrix "
        "cores. This is a semantic port, not a rename; mark it for manual review with a "
        "rocWMMA pointer if non-trivial.",
    ),
    Note(
        "torch-python",
        (r"torch\.cuda", r"\.to\(['\"]cuda", r"device=['\"]cuda"),
        "PyTorch ROCm builds keep the 'cuda' device string: torch.cuda.is_available() and "
        ".to('cuda') work unchanged on AMD GPUs. Do NOT rename 'cuda' device strings to 'hip'. "
        "Detect ROCm at runtime with torch.version.hip. Only nvidia-specific bits (apex, "
        "nvidia-smi calls, CUDA_HOME assumptions) need changes.",
    ),
    Note(
        "torch-cpp-extension",
        (r"CUDAExtension", r"torch\.utils\.cpp_extension", r"BuildExtension"),
        "torch.utils.cpp_extension.CUDAExtension builds correctly on ROCm — PyTorch auto-"
        "hipifies sources at build time. Keep CUDAExtension (there is no HIPExtension); at "
        "most guard nvcc-specific extra_compile_args with torch.version.hip checks.",
    ),
    Note(
        "cmake-hip",
        (r"find_package\(CUDA", r"enable_language\(CUDA", r"CMAKE_CUDA", r"cuda_add_"),
        "CMake: replace enable_language(CUDA) with enable_language(HIP) (CMake >= 3.21), "
        "CMAKE_CUDA_ARCHITECTURES -> CMAKE_HIP_ARCHITECTURES (e.g. gfx90a;gfx942), "
        "find_package(CUDAToolkit) -> find_package(hip). Legacy cuda_add_library -> plain "
        "add_library with LANGUAGE HIP source properties.",
    ),
    Note(
        "docker",
        (r"nvidia/cuda", r"nvidia-docker", r"--gpus", r"nvidia-container"),
        "Docker: base images nvidia/cuda:* -> rocm/dev-ubuntu-22.04 (or rocm/pytorch for DL). "
        "Runtime flags: '--gpus all' -> '--device=/dev/kfd --device=/dev/dri "
        "--security-opt seccomp=unconfined --group-add video'. nvidia-smi -> rocm-smi.",
    ),
    Note(
        "driver-api",
        (r"\bcuInit\b", r"\bcuDevice", r"\bcuModule", r"\bcuLaunchKernel", r"\bCUcontext", r"\bCUdevice"),
        "CUDA Driver API (cu* / CUcontext) maps to the same hip* runtime API namespace: "
        "cuInit->hipInit, cuModuleLoad->hipModuleLoad, cuLaunchKernel->hipModuleLaunchKernel, "
        "CUcontext->hipCtx_t (deprecated; often removable since HIP contexts are implicit).",
    ),
    Note(
        "nvrtc",
        (r"nvrtc", r"NVRTC"),
        "NVRTC maps to hipRTC: <nvrtc.h> -> <hiprtc.h>, nvrtcCompileProgram -> "
        "hiprtcCompileProgram, nvrtcGetPTX -> hiprtcGetCode (returns GCN ISA/code object, "
        "not PTX — downstream cuModuleLoadData becomes hipModuleLoadData on that code).",
    ),
    Note(
        "kernel-launch",
        (r"<<<", r"hipLaunchKernelGGL"),
        "The <<<grid, block, shmem, stream>>> launch syntax is fully supported by hipcc — "
        "keep it unchanged. Only convert to hipLaunchKernelGGL if the build must also pass "
        "through a plain C++ compiler.",
    ),
    Note(
        "build-nvcc",
        (r"\bnvcc\b", r"-gencode", r"-arch=sm_", r"compute_\d\d"),
        "Build: nvcc -> hipcc. Remove -gencode/-arch=sm_* flags; ROCm targets are set with "
        "--offload-arch=gfx90a (MI200) / gfx942 (MI300) etc. -Xcompiler passthrough works "
        "the same. CUDA_HOME-style env checks become ROCM_PATH (default /opt/rocm).",
    ),
    Note(
        "streams-graphs",
        (r"cudaGraph", r"cudaStreamCapture", r"cudaStreamBeginCapture"),
        "CUDA Graphs map 1:1 to HIP Graphs: cudaGraph_t->hipGraph_t, cudaStreamBeginCapture->"
        "hipStreamBeginCapture, cudaGraphInstantiate->hipGraphInstantiate. Supported from "
        "ROCm 5.3+; keep the same capture/instantiate/launch structure.",
    ),
    Note(
        "cusparse-cusolver",
        (r"cusparse", r"cusolver", r"cuSPARSE", r"cuSOLVER"),
        "cuSPARSE -> hipSPARSE (<hipsparse/hipsparse.h>, cusparseX -> hipsparseX) and "
        "cuSOLVER -> hipSOLVER (<hipsolver/hipsolver.h>). Enum prefixes change too: "
        "CUSPARSE_* -> HIPSPARSE_*. Generic 1:1 renames are safe for the common dense/CSR paths.",
    ),
    Note(
        "unified-memory",
        (r"cudaMallocManaged", r"cudaMemPrefetchAsync", r"cudaMemAdvise"),
        "Unified/managed memory works on ROCm: hipMallocManaged, hipMemPrefetchAsync, "
        "hipMemAdvise are 1:1. Note performance semantics differ (XNACK must be enabled on "
        "some GPUs); do not restructure the code, just map the calls.",
    ),
    Note(
        "half-precision",
        (r"__half", r"cuda_fp16", r"__float2half", r"__hmul", r"__hadd"),
        "FP16: <cuda_fp16.h> -> <hip/hip_fp16.h>; __half, __half2, __float2half and the "
        "__h* intrinsics are 1:1 in HIP. bfloat16: <cuda_bf16.h> -> <hip/hip_bf16.h> with "
        "__hip_bfloat16 replacing __nv_bfloat16.",
    ),
)


def relevant_notes(source: str, limit: int = 6) -> list[Note]:
    """Deterministically retrieve the notes whose patterns match the source."""
    matched: list[Note] = []
    for note in _NOTES:
        for pattern in note.patterns:
            if re.search(pattern, source):
                matched.append(note)
                break
        if len(matched) >= limit:
            break
    return matched


def build_knowledge_block(source: str, limit: int = 6, max_chars: int = 2800) -> str:
    """A prompt block grounding the model in curated migration facts.

    Empty string when nothing matches, so callers can concatenate blindly.
    """
    notes = relevant_notes(source, limit=limit)
    if not notes:
        return ""
    lines = ["Grounding notes from the ROCm migration knowledge base (follow these over general knowledge):"]
    total = len(lines[0])
    for note in notes:
        entry = f"- [{note.id}] {note.text}"
        if total + len(entry) > max_chars:
            break
        lines.append(entry)
        total += len(entry)
    return "\n".join(lines)
