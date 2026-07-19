import unittest

from app.hipify_service import build_hybrid_note, hipify_text, is_hipifiable_path


CUDA_SNIPPET = """
#include <cuda.h>
#include <cuda_runtime.h>
#include <cublas_v2.h>

__global__ void add(float* a) { a[0] += 1.0f; }

int main() {
    float* d;
    cudaError_t err = cudaMalloc(&d, 4);
    cudaMemcpy(d, d, 4, cudaMemcpyHostToDevice);
    cudaStream_t s;
    cudaStreamCreate(&s);
    cublasHandle_t h;
    cublasCreate(&h);
    cudaDeviceSynchronize();
    cudaFree(d);
    return err == cudaSuccess ? 0 : 1;
}
"""


class HipifyServiceTests(unittest.TestCase):
    def test_converts_core_runtime_calls(self):
        result = hipify_text(CUDA_SNIPPET, "kernel.cu")
        self.assertIn("hipMalloc", result.converted)
        self.assertIn("hipMemcpy", result.converted)
        self.assertIn("hipMemcpyHostToDevice", result.converted)
        self.assertIn("hipStream_t", result.converted)
        self.assertIn("hipStreamCreate", result.converted)
        self.assertIn("hipDeviceSynchronize", result.converted)
        self.assertIn("hipFree", result.converted)
        self.assertIn("hipError_t", result.converted)
        self.assertIn("hipSuccess", result.converted)

    def test_converts_headers_and_libraries(self):
        result = hipify_text(CUDA_SNIPPET, "kernel.cu")
        self.assertIn("<hip/hip_runtime.h>", result.converted)
        self.assertIn("<hipblas/hipblas.h>", result.converted)
        self.assertIn("hipblasCreate", result.converted)
        self.assertIn("hipblasHandle_t", result.converted)
        self.assertNotIn("<cuda.h>", result.converted)
        self.assertNotIn("cublasCreate(", result.converted.replace("hipblasCreate(", ""))

    def test_counts_and_reports_changes(self):
        result = hipify_text(CUDA_SNIPPET, "kernel.cu")
        self.assertGreater(result.total_replacements, 8)
        names = {c["from"] for c in result.changes}
        self.assertIn("cudaMalloc", names)
        self.assertTrue(result.fully_converted, f"residual: {result.residual_tokens}")

    def test_residual_tokens_flagged(self):
        src = "cudaMalloc(&p, 4); cudaGraphLaunch(g, s); nvcc_flag();"
        result = hipify_text(src)
        self.assertIn("hipMalloc", result.converted)
        self.assertIn("cudaGraphLaunch", result.residual_tokens)
        self.assertFalse(result.fully_converted)

    def test_word_boundaries_do_not_mangle(self):
        src = "int mycudaMallocCount = 0; // cudaMalloc"
        result = hipify_text(src)
        self.assertIn("mycudaMallocCount", result.converted)
        self.assertIn("// hipMalloc", result.converted)

    def test_noop_on_non_cuda_source(self):
        result = hipify_text("print('hello world')\n", "setup.py")
        self.assertEqual(result.total_replacements, 0)
        self.assertEqual(result.converted, "print('hello world')\n")

    def test_hipifiable_paths(self):
        self.assertTrue(is_hipifiable_path("src/kernels/muladd.cu"))
        self.assertTrue(is_hipifiable_path("include/ops.cuh"))
        self.assertTrue(is_hipifiable_path("lib/math.cpp"))
        self.assertFalse(is_hipifiable_path("setup.py"))
        self.assertFalse(is_hipifiable_path("Dockerfile"))

    def test_hybrid_note_mentions_conversions(self):
        result = hipify_text(CUDA_SNIPPET, "kernel.cu")
        note = build_hybrid_note(result)
        self.assertIn("cudaMalloc -> hipMalloc", note)


if __name__ == "__main__":
    unittest.main()
