# Local-First Runbook

ROCmPorter Agent can be developed and demoed without paid AMD Developer Cloud resources. The local path uses deterministic scanning, local Ollama patch generation, local syntax validation, offline export bundles, and optional GitHub Actions artifacts.

## Why local-first

- No paid cloud dependency for daily development.
- Ollama keeps patch generation private and reproducible on the laptop.
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

This checks tool availability, Ollama model availability, backend compilation, frontend linting, and browser smoke tests.

## Start the product

From the repository root:

```powershell
.\scripts\local\start-local-dev.ps1
```

Open:

```text
http://127.0.0.1:5173
```

The backend runs on `http://127.0.0.1:8000`, and the frontend proxies API calls during development.

## CLI demo path

From `backend/`:

```powershell
.\.venv\Scripts\python rocmporter.py models
.\.venv\Scripts\python rocmporter.py run https://github.com/pytorch/extension-cpp --finding-id cuda_build_config --evidence-path extension_cpp/setup.py --model qwen2.5-coder:latest --export json,md,diff,html,zip,github
```

The output bundle is written under `backend\work\cli_exports\` unless `--out` is provided.

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
