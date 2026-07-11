# ROCmPorter Agent Submission Pitch

## Title

ROCmPorter Agent - Local LLM Assistant for CUDA-to-AMD ROCm Migration

## One-liner

ROCmPorter scans CUDA-heavy GitHub repositories, finds AMD ROCm migration blockers, and generates verified single-file review artifacts using a local coding model.

## Live demo

- **Zero-install hosted demo:** <https://rocmporter-agent.vercel.app> — click `Load Sample Scan` for the full report → patch → verify → export walkthrough (works fully offline in the browser).
- GitHub Pages mirror: <https://pavansai20052004-hue.github.io/rocmporter-agent/>
- To drive the hosted UI from a live local backend, use the `?api=<https-tunnel-url>` override documented in the repository README.

## Problem

Many AI and GPU projects are written around CUDA, NVCC, NVIDIA containers, and NVIDIA-specific package assumptions. Teams that want to move workloads to AMD ROCm need a practical way to find migration blockers, review code changes, and avoid blindly trusting AI-generated patches.

## Solution

ROCmPorter provides a local-first migration workflow:

1. Scan a public or private GitHub repository for CUDA/NVIDIA assumptions.
2. Show evidence files, line snippets, severity, confidence, and ROCm migration recommendations.
3. Generate a single-file ROCm review artifact with local Ollama and `qwen2.5-coder`.
4. Verify syntax where possible, replay diffs, score review risk, and block unsafe apply.
5. Export offline bundles and GitHub-ready review artifacts for team review.

## Why AMD and ROCm

The product is built for developers who want to move more GPU software toward AMD hardware. It does not merely say "replace CUDA with HIP." It creates a workflow around ROCm readiness, evidence-backed blockers, exportable review artifacts, and optional future ROCm hardware validation.

## What Judges Should Try

1. Start the local stack with `.\scripts\local\start-local-dev.ps1`.
2. Open `http://127.0.0.1:5178`.
3. Click `Load Sample Scan` for the reliable offline demo path.
4. Choose `extension_cpp/setup.py` and generate the sample patch.
5. Review the diff, verification receipt, export bundle, and GitHub review artifact.
6. Run the final proof suite:

   ```powershell
   .\scripts\local\run-benchmarks.ps1 -CaseFile benchmarks\submission-proof-cases.json -Out work\benchmark-runs\submission-proof-local
   ```

## Verified Benchmark Proof

Tracked proof summary: [benchmark-proof/submission-proof-v2-summary.md](benchmark-proof/submission-proof-v2-summary.md)

Latest verified result:

- 3 of 3 cases completed.
- 3 export-ready review artifacts.
- 0 export blocks.
- 0 infrastructure failures.
- 0 high-risk patches.
- 0 apply-ready patches by design, because apply is gated until ROCm validation.

## Differentiators

- Local-first: no paid cloud LLM API required.
- Evidence-driven scanner: findings cite concrete files and lines.
- Review-safe generation: patch artifacts can export even when workspace apply is blocked.
- Risk scoring: semantic checks catch hallucinated or risky migration claims.
- GitHub-ready outputs: review comment and inline suggestion artifacts are generated for PR workflows.
- CI story: scan-only runs on GitHub-hosted runners; patch generation can run on a self-hosted Ollama runner.

## Current Limitations

- The current proof focuses on single-file review artifacts, not full repository migrations.
- Apply is intentionally blocked until verification is strong enough.
- ROCm hardware validation is optional until AMD GPU access is available.
- Longer 6-case judge-quality benchmarks remain stretch evidence unless a clean summary is captured.

## Demo Fallback

If GitHub, internet, or Ollama is slow during judging, use `Load Sample Scan`. It shows the same product workflow with realistic evidence, patch, export, and GitHub review states without depending on external services.
