# ROCmPorter Submission Proof v2

Generated: `2026-07-03T04:39:47Z`

Case file: `benchmarks/submission-proof-cases.json`

Model: `qwen2.5-coder:latest`

This tracked summary mirrors the local benchmark output from `work/benchmark-runs/submission-proof-v2/summary.json`. The raw `work/` folder is intentionally ignored, so this file is the portable proof record for judges and reviewers.

## Result

| Metric | Value |
| --- | ---: |
| Run status | completed |
| Cases completed | 3 / 3 |
| Remaining cases | 0 |
| Completed exports | 3 |
| Export-ready review artifacts | 3 |
| Export blocked | 0 |
| Apply ready | 0 |
| Infrastructure failures | 0 |
| Generation failures | 0 |
| Scanner gaps | 0 |
| High-risk patches | 0 |
| Medium-risk patches | 1 |
| Low-risk patches | 2 |

## Cases

| Case | Repository | Evidence file | Quality lane | Risk | Apply ready | Export ready | Judge signal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `extension-cpp-build` | `pytorch/extension-cpp` | `extension_cpp/setup.py` | review-ready | low | no | yes | Export-ready review artifact; workspace apply remains gated for ROCm validation. |
| `extension-cpp-stable-abi` | `pytorch/extension-cpp` | `extension_cpp_stable/setup.py` | review-ready | low | no | yes | Export-ready review artifact; workspace apply remains gated for ROCm validation. |
| `cuda-samples-cmake` | `NVIDIA/cuda-samples` | `CMakeLists.txt` | review-ready | medium | no | yes | Export-ready review artifact; workspace apply remains gated for ROCm validation. |

## Interpretation

ROCmPorter is intentionally conservative. The local LLM creates single-file review artifacts and export bundles, but workspace apply remains blocked until verification returns `applyReady=true` and ROCm validation is available.

For final demos, cite this proof before running any longer or experimental benchmark suite.
