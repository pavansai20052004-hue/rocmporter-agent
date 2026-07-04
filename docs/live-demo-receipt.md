# Live Demo Receipt

Date: 2026-07-01

Repository tested:

```text
https://github.com/pytorch/extension-cpp
```

Command:

```powershell
cd backend
.\.venv\Scripts\python rocmporter.py run https://github.com/pytorch/extension-cpp --finding-id cuda_build_config --evidence-path extension_cpp/setup.py --model qwen2.5-coder:latest --export json,md,diff,html,zip,github --out ..\work\live-demo-extension-cpp
```

Result:

- Scan completed with `scan_f68d284b27`
- Local Ollama model `qwen2.5-coder:latest` generated patch `patch_3c5aed80e6`
- Patch diff, patched file snapshot, verification receipt, HTML report, GitHub review artifacts, checksums, and zip bundle were exported
- Python syntax validation and diff replay passed
- ROCm semantic sanity failed because the model invented PyTorch extension APIs and changed compile argument keys in a risky way

Decision:

ROCmPorter correctly keeps this artifact as review evidence, but it marks it not apply-ready. This is the desired product behavior: local AI can draft migration patches, while the tool blocks unsafe application until semantic review or ROCm hardware validation passes.

Follow-up benchmark:

Run the same flow against the demo bench list in `docs/demo-script.md`, then record whether each generated patch is low, medium, or high review risk.

Benchmark smoke run:

- Command path: `.\scripts\local\run-benchmarks.ps1`
- Case file: `benchmarks/demo-cases.json`
- Verified smoke output: `work\benchmark-smoke-run\summary.json`
- `extension-cpp` blocked export because the generated patch leaked `needsMoreContext`
- `cuda-samples` blocked export because the generated diff was corrupt during replay

This is good benchmark evidence for the current phase: the scanner, verifier, and export gate are catching weak model output before it can be treated as a shippable migration artifact.

Update on 2026-07-02:

- Focused benchmark case file: `benchmarks\quality-check-cases.json`
- Verified output: `work\benchmark-runs\quality-check-partial-mode-v3\summary.json`
- `extension-cpp` now exports a conservative partial patch artifact with `exportReady=true` and `applyReady=false`
- `flash-attention` now exports a conservative partial patch artifact with `exportReady=true` and `applyReady=false`

This is a stronger demo story for judges: ROCmPorter no longer hallucinates a full one-file ROCm migration for these build-config cases. It produces reviewable evidence and diff bundles, then keeps live apply blocked until the migration is genuinely ready.

Auto-selection update on 2026-07-02:

- Case file: `benchmarks\selection-check-cases.json`
- Verified output: `work\benchmark-runs\selection-check-v3\summary.json`
- `flash-attention-auto` selected the repo root `setup.py` and exported a conservative partial artifact
- `cuda-samples-auto` selected the repo root `CMakeLists.txt` and exported a conservative partial artifact

That makes the product story stronger in front of judges: even when the user does not manually choose the exact evidence file, ROCmPorter can now steer toward better patch targets on larger repos.

Regression expansion update on 2026-07-02:

- Case file: `benchmarks\regression-expansion-cases.json`
- Verified output: `work\benchmark-runs\regression-expansion-v1\summary.json`
- `extension-cpp-stable` exported a conservative partial artifact for `extension_cpp_stable/setup.py`
- `flash-attention-layer-norm` exported a conservative partial artifact for `csrc/layer_norm/setup.py`

The main focused benchmark file now includes these two cases too, so the standard quality check covers four concrete CUDA build-system migration surfaces.

Expanded quality benchmark update on 2026-07-02:

- Case file: `benchmarks\quality-check-cases.json`
- Verified output: `work\benchmark-runs\quality-check-expanded-v1\summary.json`
- 4 of 4 cases completed export bundles
- 4 of 4 cases were export-ready review artifacts
- 0 of 4 cases were apply-ready, which is intentional for conservative partial migration artifacts
- 0 high-risk patches remained in the focused quality run

Submission proof update on 2026-07-03:

- Case file: `benchmarks\submission-proof-cases.json`
- Tracked summary: `docs\benchmark-proof\submission-proof-v2-summary.md`
- Raw local output: `work\benchmark-runs\submission-proof-v2\summary.json`
- 3 of 3 cases completed export bundles
- 3 of 3 cases were export-ready review artifacts
- 0 cases were export blocked
- 0 infrastructure failures occurred
- 0 high-risk patches remained in the proof run
- 0 cases were apply-ready, intentionally, because workspace apply remains gated until ROCm validation is available

This is the preferred final proof run for the live demo because it is fast, repeatable, and covers PyTorch extension setup, stable ABI setup, and CUDA samples CMake review artifacts.

Next benchmark target:

- Case file: `benchmarks\judge-quality-cases.json`
- Scope: 6 pinned CUDA/NVIDIA build surfaces mapped to current deterministic patch paths
- Purpose: capture defensible patch-quality evidence and classify each case with `qualityLane` plus `judgeSignal`
- Status: candidate run target until a completed `summary.json` is captured
