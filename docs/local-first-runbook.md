# Local-First Runbook

ROCmPorter Agent can be developed and demoed without paid AMD Developer Cloud resources. The local path uses deterministic scanning, local Ollama patch generation, local syntax validation, offline export bundles, and optional GitHub Actions artifacts.

## Why local-first

- No paid cloud dependency for daily development.
- Ollama keeps patch generation local and private; repeatability depends on the installed model version, host resources, and pinned run settings.
- Scan-only GitHub Actions still run on free GitHub-hosted runners.
- A self-hosted runner can be added later from the same laptop if CI patch generation is needed.
- AMD/ROCm hardware validation remains optional evidence for later credits, sponsorship, or a teammate machine with AMD GPU access.

## One-time setup

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Frontend:

```powershell
cd frontend
npm install
npx playwright install chromium
```

Ollama:

```powershell
ollama pull qwen2.5-coder
ollama list
```

Optional private repository access:

```powershell
cd backend
Copy-Item .env.example .env
```

Then set `GITHUB_PAT` in `backend/.env` only when private repository cloning is required.

## Daily readiness check

From the repository root:

```powershell
.\scripts\local\check-local.ps1
```

For a deeper local verification pass:

```powershell
.\scripts\local\check-local.ps1 -RunChecks
```

This checks tool availability, Ollama model availability, backend compilation, backend unit tests, frontend linting, frontend production build, and browser smoke tests.

## Start the product

From the repository root:

```powershell
.\scripts\local\start-local-dev.ps1
```

Open:

```text
http://127.0.0.1:5178
```

The backend runs on `http://127.0.0.1:8000`, and the frontend proxies API calls during development.

The launcher writes logs and process state under `work\local-dev\`. Use these commands during demos:

```powershell
.\scripts\local\status-local-dev.ps1
.\scripts\local\stop-local-dev.ps1
```

## CLI demo path

From `backend/`:

```powershell
.\.venv\Scripts\python rocmporter.py models
.\.venv\Scripts\python rocmporter.py run https://github.com/pytorch/extension-cpp --finding-id cuda_build_config --evidence-path extension_cpp/setup.py --model qwen2.5-coder:latest --export json,md,diff,html,zip,github
```

The output bundle is written under `backend\work\cli_exports\` unless `--out` is provided.

## Multi-repo benchmark path

From the repository root:

```powershell
.\scripts\local\run-benchmarks.ps1
```

This uses [benchmarks/demo-cases.json](../benchmarks/demo-cases.json) by default and writes a per-run folder with `summary.json`, `summary.md`, per-case artifacts, and verification receipts under `work\benchmark-runs\`.

For the tighter build-system quality loop, run:

```powershell
.\scripts\local\run-benchmarks.ps1 -CaseFile benchmarks\quality-check-cases.json
```

For the fastest submission proof loop, run:

```powershell
.\scripts\local\run-benchmarks.ps1 -CaseFile benchmarks\submission-proof-cases.json -Out work\benchmark-runs\submission-proof-local
```

This 3-case suite is the preferred pre-demo proof run. It keeps the runtime bounded while still covering PyTorch extension setup, stable ABI setup, and CUDA samples CMake review artifacts.

Latest verified submission proof:

- Tracked summary: `docs\benchmark-proof\submission-proof-v2-summary.md`
- Raw local output: `work\benchmark-runs\submission-proof-v2\summary.json`
- Cases: 3
- Completed exports: 3
- Export ready: 3
- Review-ready artifacts: 3
- Apply ready: 0, intentionally gated for ROCm validation
- Infrastructure failures: 0
- High risk patches: 0

Latest verified focused benchmark:

- Output: `work\benchmark-runs\quality-check-partial-mode-v3\summary.json`
- `extension-cpp`: completed, medium risk, `exportReady=true`, `applyReady=false`
- `flash-attention`: completed, medium risk, `exportReady=true`, `applyReady=false`

That is the current intended product lane for hard single-file build-config migrations: conservative review artifacts can export cleanly, while workspace apply stays blocked until broader ROCm work is finished.

Latest verified auto-selection benchmark:

- Output: `work\benchmark-runs\selection-check-v3\summary.json`
- `flash-attention-auto`: selected `setup.py`, completed, `exportReady=true`, `applyReady=false`
- `cuda-samples-auto`: selected `CMakeLists.txt`, completed, `exportReady=true`, `applyReady=false`

This checks that the broader product flow can choose stronger evidence files automatically on larger repositories instead of relying only on hand-picked demo paths.

Latest verified regression expansion benchmark:

- Output: `work\benchmark-runs\regression-expansion-v1\summary.json`
- `extension-cpp-stable`: selected `extension_cpp_stable/setup.py`, completed, `exportReady=true`, `applyReady=false`
- `flash-attention-layer-norm`: selected `csrc/layer_norm/setup.py`, completed, `exportReady=true`, `applyReady=false`

These cases are now included in `benchmarks\quality-check-cases.json` so the focused quality run covers four real build-system surfaces.

Latest verified expanded quality benchmark:

- Output: `work\benchmark-runs\quality-check-expanded-v1\summary.json`
- Cases: 4
- Completed exports: 4
- Export ready: 4
- Apply ready: 0
- High risk patches: 0

This remains useful as a product-quality regression check, while `submission-proof-cases.json` is the fastest final proof for judge demos.

Advanced judge-quality benchmark suite:

```powershell
.\scripts\local\run-benchmarks.ps1 -CaseFile benchmarks\judge-quality-cases.json -Out work\benchmark-runs\judge-quality-local
```

This candidate 6-case suite is intentionally pinned to evidence files that map to current deterministic conservative patch paths. It covers small PyTorch extensions, CUDA samples CMake, and three FlashAttention setup paths. Treat it as unverified until a completed `summary.json` is captured and linked.

Benchmark summaries include:

- `qualityLane`: `apply-ready`, `review-ready`, `blocked`, `scanner-gap`, `generation-failed`, or `infrastructure-failed`
- `judgeSignal`: a short reader-facing explanation of what each case shows
- totals for review-ready artifacts, blocked cases, scanner gaps, and generation failures

Fresh benchmark runs record `qualityLane`, `judgeSignal`, `runStatus`, planned case count, and remaining case count. Older verified summaries may predate this format, so rerun before citing those fields as captured evidence.

## GitHub Actions without cloud spend

Use `.github/workflows/rocmporter-agent.yml` in two modes:

- Scan-only: runs on `ubuntu-latest` and uploads a report bundle.
- Scan plus patch: requires a self-hosted runner labeled `ollama` on a machine where Ollama is running.

AMD Developer Cloud validation remains in `.github/workflows/amd-devcloud-rocm-validation.yml`, but it should be treated as optional until free AMD GPU access is available.

## Demo narrative

Position the product as a local enterprise readiness scanner and developer assistant:

1. Scan a CUDA/NVIDIA-heavy repository.
2. Show exact evidence files and migration risks.
3. Generate one single-file patch with local Ollama.
4. Show the diff, validation receipt, warnings, and GitHub review artifact.
5. Export the offline bundle for a reviewer or CI system.
6. Explain that ROCm hardware validation can plug in later without changing the product flow.
