# Validating ROCmPorter migrations on the real ROCm toolchain

ROCmPorter's hybrid engine (deterministic hipify + AI remainder) produces the
patches. This guide is how you **prove** them:

## Level 1 — Compile validation (no GPU needed) ✅ available now

Copy [`.github/workflows/rocm-compile-validate.yml`](../.github/workflows/rocm-compile-validate.yml)
into your repository. On every pull request — including ROCmPorter migration
PRs — it:

1. Spins up AMD's official `rocm/dev-ubuntu-22.04` container on a normal
   GitHub-hosted runner (compilation needs no GPU).
2. Runs `hipcc -fsyntax-only` on every `.hip` / `.cu` translation unit.
3. Fails the check with per-file errors if anything doesn't compile.

A green check means the migrated code is **accepted by the real ROCm
compiler** — not just "looks right."

## Level 2 — Execution validation (needs an AMD GPU)

To actually *run* tests on ROCm hardware you need a runner with an AMD GPU:

1. Get access to an AMD GPU machine (e.g. **AMD Developer Cloud**, or any
   MI/Radeon box with ROCm installed).
2. Register it as a **self-hosted GitHub runner** with labels
   `self-hosted, rocm, gpu`.
3. Use the workflow at
   [`.github/workflows/amd-devcloud-rocm-validation.yml`](../.github/workflows/amd-devcloud-rocm-validation.yml)
   as the template — it builds and runs the project's test suite on the GPU and
   uploads the receipt as an artifact.

## How this fits ROCmPorter's trust ladder

| Level | Claim | Proof |
|---|---|---|
| Scan | "This is where your CUDA is" | Static analysis, file+line evidence |
| Patch | "Here's the migration" | Deterministic hipify % + AI remainder, diff replay |
| **Compile** | "The ROCm compiler accepts it" | `hipcc` in the official ROCm container (CI) |
| **Execute** | "It runs on AMD hardware" | Self-hosted AMD GPU runner receipt |
