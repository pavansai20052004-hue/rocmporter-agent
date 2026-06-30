# ROCmPorter Agent

ROCmPorter Agent is a hackathon MVP that scans a GitHub repository for CUDA and NVIDIA-specific assumptions, then produces a clean AMD ROCm migration report with evidence, risk level, next steps, export bundles, review-scored patch artifacts, and GitHub PR review outputs.

## Stack

- `frontend/`: React + Vite report UI
- `backend/`: FastAPI scan API with deterministic static-analysis rules

## What the MVP does

1. Accepts a GitHub repository URL
2. Clones the repository with a shallow fetch
3. Scans for CUDA files, CUDA headers, build-system assumptions, container signals, and Python GPU package clues
4. Returns a ROCm portability score, findings, and a migration checklist
5. Generates single-file ROCm patch diffs per evidence file through local Ollama
6. Validates generated patches where local syntax tooling is available and surfaces warnings when review is still required
7. Scores patch review risk with CUDA and ROCm-aware semantic heuristics instead of trusting syntax alone
8. Generates GitHub-ready PR review comments with suggested patch text and optional comment posting
9. Supports private GitHub repository cloning through a local PAT in `backend/.env`
10. Applies generated patches only inside the scanned workspace copy with backup-and-restore rollback
11. Verifies patches with syntax checks, source drift checks, artifact hashes, and diff replay before apply/export
12. Exports offline HTML, JSON, Markdown, diff, GitHub review, verification receipt, checksum, and zip artifacts for sharing or CI

## Run locally

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Optional local secrets:

```powershell
Copy-Item .env.example .env
```

Frontend:

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

If the frontend is hosted separately from Vite dev proxy, create `frontend/.env` from `frontend/.env.example` and set:

```powershell
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Backend CORS can be widened with:

```powershell
APP_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Optional Ollama override:

```powershell
OLLAMA_HOST=http://127.0.0.1:11434
```

Private GitHub repository access:

```powershell
GITHUB_PAT=ghp_your_token_here
```

The Vite dev server proxies `/api/*` requests to the FastAPI server on port `8000`.

## Ollama setup

The local patch workflow expects Ollama running on the machine with at least one coding model installed.

Example:

```powershell
ollama list
ollama run qwen2.5-coder
```

## CLI

From `backend/`:

```powershell
.\.venv\Scripts\python rocmporter.py models
.\.venv\Scripts\python rocmporter.py scan https://github.com/pytorch/extension-cpp --export json,md,html,zip,github
.\.venv\Scripts\python rocmporter.py patch scan_id --finding-id cuda_build_config --evidence-path extension_cpp/setup.py --export json,md,diff,html,zip,github
.\.venv\Scripts\python rocmporter.py verify-patch scan_id --patch-id patch_id
.\.venv\Scripts\python rocmporter.py apply-patch scan_id --patch-id patch_id
.\.venv\Scripts\python rocmporter.py rollback-patch --apply-id apply_id
.\.venv\Scripts\python rocmporter.py run https://github.com/pytorch/extension-cpp --finding-id cuda_build_config --evidence-path extension_cpp/setup.py --export json,md,diff,html,zip,github
.\.venv\Scripts\python rocmporter.py github-review scan_id --patch-id patch_id --pr-number 42
```

CLI artifacts are written under `work/cli_exports/` by default.

Generated export bundles include:

- `report.json`
- `summary.md`
- `index.html`
- `github-review.md`
- `github-review.json`
- `github-review-inline-comments.json` or equivalent inline review artifact file
- `manifest.json`
- `SHA256SUMS.txt`
- `data/` scan, coverage, evidence, and patch metadata
- `patches/*.diff`
- `patch-verification.json`
- `verification/*-verification.json`
- `bundle.zip`

Patch exports are blocked unless the latest verification receipt is export-ready. Patch apply is blocked unless the receipt is apply-ready. Each patch stores an immutable source snapshot under `work/patches/source/<patch_id>/...` so exported source context does not drift from the diff.

## Quality checks

Frontend:

```powershell
cd frontend
npm run lint
npm run build
npm run test:e2e
```

Backend:

```powershell
python -m compileall backend\app
```

## GitHub Action

A real workflow now lives at [.github/workflows/rocmporter-agent.yml](C:/Users/pavansai/OneDrive/Desktop/AMD_HACKTHON/.github/workflows/rocmporter-agent.yml).

- Scan-only runs on `ubuntu-latest`
- Frontend quality checks run lint, build, and Playwright smoke tests
- Scan plus patch runs on a labeled self-hosted runner with Ollama
- Phase 4 can also generate GitHub review artifacts and optionally post a PR comment when a token is configured
- Phase 5 adds PAT-based private repo access and line-aware review artifacts for PR workflows
- Both upload the export bundle as a workflow artifact

## Next upgrade ideas

- Add an LLM-written executive summary on top of the deterministic findings
- Add direct web-based patch apply once the CLI rollback flow has enough mileage
- Add report export and benchmark capture on AMD Developer Cloud
