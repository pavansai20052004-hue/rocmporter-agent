// Original CUDA source — the "before" of a ROCmPorter migration.
// The migrated HIP version (vector_add.hip) is produced from THIS file by
// ROCmPorter's deterministic hipify engine and is compile-checked in CI.
#include <cuda_runtime.h>
#include <cstdio>

__global__ void vec_add(const float* a, const float* b, float* c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + b[i];
}

int main() {
    const int n = 256;
    const size_t bytes = n * sizeof(float);
    float *da, *db, *dc;
    cudaMalloc(&da, bytes);
    cudaMalloc(&db, bytes);
    cudaMalloc(&dc, bytes);

    cudaStream_t stream;
    cudaStreamCreate(&stream);
    vec_add<<<(n + 63) / 64, 64, 0, stream>>>(da, db, dc, n);
    cudaStreamSynchronize(stream);

    cudaError_t err = cudaGetLastError();
    if (err != cudaSuccess) {
        printf("error: %s\n", cudaGetErrorString(err));
    }

    cudaStreamDestroy(stream);
    cudaFree(da);
    cudaFree(db);
    cudaFree(dc);
    return err == cudaSuccess ? 0 : 1;
}
