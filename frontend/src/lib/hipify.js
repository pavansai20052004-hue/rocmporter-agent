/**
 * Client-side mirror of the backend's deterministic CUDA -> HIP mapping
 * (backend/app/hipify_service.py).
 *
 * This exists so evidence snippets can show the mechanical translation the
 * moment a scan lands — no round-trip, no model, no waiting. It is deliberately
 * a preview: the backend remains the source of truth for anything that gets
 * written into a patch or a pull request.
 */

const MAP = [
  // memory
  ['cudaMallocManaged', 'hipMallocManaged'],
  ['cudaMallocHost', 'hipHostMalloc'],
  ['cudaMallocPitch', 'hipMallocPitch'],
  ['cudaMallocArray', 'hipMallocArray'],
  ['cudaMallocAsync', 'hipMallocAsync'],
  ['cudaMalloc', 'hipMalloc'],
  ['cudaFreeHost', 'hipHostFree'],
  ['cudaFreeArray', 'hipFreeArray'],
  ['cudaFreeAsync', 'hipFreeAsync'],
  ['cudaFree', 'hipFree'],
  ['cudaMemcpyAsync', 'hipMemcpyAsync'],
  ['cudaMemcpyToSymbol', 'hipMemcpyToSymbol'],
  ['cudaMemcpyFromSymbol', 'hipMemcpyFromSymbol'],
  ['cudaMemcpy2D', 'hipMemcpy2D'],
  ['cudaMemcpy', 'hipMemcpy'],
  ['cudaMemsetAsync', 'hipMemsetAsync'],
  ['cudaMemset', 'hipMemset'],
  ['cudaMemGetInfo', 'hipMemGetInfo'],
  ['cudaHostAlloc', 'hipHostMalloc'],
  ['cudaHostRegister', 'hipHostRegister'],
  ['cudaMemcpyHostToDevice', 'hipMemcpyHostToDevice'],
  ['cudaMemcpyDeviceToHost', 'hipMemcpyDeviceToHost'],
  ['cudaMemcpyDeviceToDevice', 'hipMemcpyDeviceToDevice'],
  ['cudaMemcpyDefault', 'hipMemcpyDefault'],
  // device / stream / event
  ['cudaGetDeviceProperties', 'hipGetDeviceProperties'],
  ['cudaGetDeviceCount', 'hipGetDeviceCount'],
  ['cudaGetDevice', 'hipGetDevice'],
  ['cudaSetDevice', 'hipSetDevice'],
  ['cudaDeviceSynchronize', 'hipDeviceSynchronize'],
  ['cudaDeviceReset', 'hipDeviceReset'],
  ['cudaDeviceProp', 'hipDeviceProp_t'],
  ['cudaStreamCreateWithFlags', 'hipStreamCreateWithFlags'],
  ['cudaStreamCreate', 'hipStreamCreate'],
  ['cudaStreamDestroy', 'hipStreamDestroy'],
  ['cudaStreamSynchronize', 'hipStreamSynchronize'],
  ['cudaStreamWaitEvent', 'hipStreamWaitEvent'],
  ['cudaStream_t', 'hipStream_t'],
  ['cudaEventCreateWithFlags', 'hipEventCreateWithFlags'],
  ['cudaEventCreate', 'hipEventCreate'],
  ['cudaEventDestroy', 'hipEventDestroy'],
  ['cudaEventRecord', 'hipEventRecord'],
  ['cudaEventSynchronize', 'hipEventSynchronize'],
  ['cudaEventElapsedTime', 'hipEventElapsedTime'],
  ['cudaEvent_t', 'hipEvent_t'],
  // errors
  ['cudaGetErrorString', 'hipGetErrorString'],
  ['cudaGetLastError', 'hipGetLastError'],
  ['cudaPeekAtLastError', 'hipPeekAtLastError'],
  ['cudaSuccess', 'hipSuccess'],
  ['cudaError_t', 'hipError_t'],
  ['cudaLaunchKernel', 'hipLaunchKernel'],
  // libraries
  ['cublasCreate', 'hipblasCreate'],
  ['cublasDestroy', 'hipblasDestroy'],
  ['cublasSetStream', 'hipblasSetStream'],
  ['cublasSgemm', 'hipblasSgemm'],
  ['cublasDgemm', 'hipblasDgemm'],
  ['cublasHandle_t', 'hipblasHandle_t'],
  ['cublasStatus_t', 'hipblasStatus_t'],
  ['curandCreateGenerator', 'hiprandCreateGenerator'],
  ['curandGenerateUniform', 'hiprandGenerateUniform'],
  ['curandState', 'hiprandState'],
  ['curand_init', 'hiprand_init'],
  ['curand_uniform', 'hiprand_uniform'],
  ['cufftPlan1d', 'hipfftPlan1d'],
  ['cufftPlan2d', 'hipfftPlan2d'],
  ['cufftExecC2C', 'hipfftExecC2C'],
  ['cufftHandle', 'hipfftHandle'],
  ['ncclAllReduce', 'rcclAllReduce'],
  ['ncclComm_t', 'rcclComm_t'],
  ['__half2float', '__half2float'],
]

const HEADERS = [
  ['<cuda_runtime_api.h>', '<hip/hip_runtime_api.h>'],
  ['<cuda_runtime.h>', '<hip/hip_runtime.h>'],
  ['<cuda_fp16.h>', '<hip/hip_fp16.h>'],
  ['<cuda_bf16.h>', '<hip/hip_bf16.h>'],
  ['<cuda.h>', '<hip/hip_runtime.h>'],
  ['<cublas_v2.h>', '<hipblas/hipblas.h>'],
  ['<cublas.h>', '<hipblas/hipblas.h>'],
  ['<curand_kernel.h>', '<hiprand/hiprand_kernel.h>'],
  ['<curand.h>', '<hiprand/hiprand.h>'],
  ['<cufft.h>', '<hipfft/hipfft.h>'],
  ['<cudnn.h>', '<miopen/miopen.h>'],
  ['<nccl.h>', '<rccl/rccl.h>'],
  ['<cub/cub.cuh>', '<hipcub/hipcub.hpp>'],
]

const LOOKUP = new Map([...MAP, ...HEADERS].filter(([a, b]) => a !== b))

// Longest-first so cudaMallocManaged is matched before cudaMalloc.
const TOKEN_RE = new RegExp(
  '(' +
    [...LOOKUP.keys()]
      .sort((a, b) => b.length - a.length)
      .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
      .join('|') +
    ')',
  'g',
)

/** Identifiers we flag but deliberately do not auto-translate. */
const ADVISORY = /\b(cudnn\w*|nvcc|torch\.cuda|CUDAExtension|wmma|__activemask)\b/g

/**
 * Splits a line into parts, marking which ones have a deterministic HIP
 * equivalent. Returns [{ text, hip? , advisory? }].
 */
export function tokenizeLine(line) {
  if (!line) return [{ text: '' }]
  const parts = []
  let last = 0
  TOKEN_RE.lastIndex = 0
  let m
  while ((m = TOKEN_RE.exec(line)) !== null) {
    if (m.index > last) parts.push({ text: line.slice(last, m.index) })
    parts.push({ text: m[0], hip: LOOKUP.get(m[0]) })
    last = m.index + m[0].length
  }
  if (last < line.length) parts.push({ text: line.slice(last) })

  // Mark advisory-only tokens inside the plain runs.
  return parts.flatMap((p) => {
    if (p.hip || !p.text) return [p]
    const sub = []
    let l = 0
    let a
    ADVISORY.lastIndex = 0
    while ((a = ADVISORY.exec(p.text)) !== null) {
      if (a.index > l) sub.push({ text: p.text.slice(l, a.index) })
      sub.push({ text: a[0], advisory: true })
      l = a.index + a[0].length
    }
    if (l < p.text.length) sub.push({ text: p.text.slice(l) })
    return sub.length ? sub : [p]
  })
}

/** Deterministic replacement count + converted text for a snippet. */
export function previewMigration(snippet) {
  if (!snippet) return { converted: '', replacements: 0, advisories: 0 }
  let replacements = 0
  TOKEN_RE.lastIndex = 0
  const converted = snippet.replace(TOKEN_RE, (match) => {
    replacements += 1
    return LOOKUP.get(match) ?? match
  })
  ADVISORY.lastIndex = 0
  const advisories = (snippet.match(ADVISORY) || []).length
  return { converted, replacements, advisories }
}
