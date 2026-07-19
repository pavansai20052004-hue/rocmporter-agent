# vector_add — a live ROCmPorter migration fixture

A minimal but real CUDA → HIP migration, kept in this repo so CI can **prove**
the hybrid engine's output compiles on the actual ROCm toolchain:

| File | What it is |
|---|---|
| [`vector_add.cu`](vector_add.cu) | Original CUDA source (the "before") |
| [`vector_add.hip`](vector_add.hip) | **Machine-generated** by `backend/app/hipify_service.py` — 16 deterministic replacements, 100% mechanical coverage, **0% AI** |

Every push runs [`rocm-compile-validate.yml`](../../.github/workflows/rocm-compile-validate.yml),
which compiles `vector_add.hip` with `hipcc` inside AMD's official
`rocm/dev-ubuntu-22.04` container. If the engine ever produces output the ROCm
compiler rejects, CI goes red.

Regenerate the fixture after changing the mapping table:

```bash
cd backend
python -c "
from app.hipify_service import hipify_text
src = open('../examples/vector_add/vector_add.cu').read()
open('../examples/vector_add/vector_add.hip', 'w').write(hipify_text(src, 'vector_add.cu').converted)
"
```
