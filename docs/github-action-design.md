# GitHub Action Design

This document captures the first shipped GitHub Action shape for ROCmPorter Agent.

## Goal

Run ROCmPorter against a repository in CI, generate a migration report bundle artifact, optionally emit patch artifacts for selected evidence files, and prepare a GitHub PR review comment artifact from the patch result.

## Shipped workflow shape

```yaml
name: ROCmPorter Agent

on:
  workflow_dispatch:
    inputs:
      repo_url:
        description: Public GitHub repository URL
        required: true
      finding_id:
        description: Optional finding id for patch generation
        required: false
      evidence_path:
        description: Optional evidence file path for patch generation
        required: false
      pr_number:
        description: Optional pull request number for GitHub review generation
        required: false
      post_github_comment:
        description: Post the generated comment when a GitHub token is configured
        required: false

jobs:
  validate_inputs:
    runs-on: ubuntu-latest
  scan_only:
    runs-on: ubuntu-latest
  scan_and_patch:
    runs-on: [self-hosted, linux, x64, ollama]
```

## Why it looks like this

- Scan is realistic on GitHub-hosted runners today.
- Patch generation is realistic only on a self-hosted runner where Ollama is already available.
- The CLI already supports non-interactive scan plus patch generation, so the workflow can stay thin.
- Export artifacts are deterministic and can be uploaded directly.

## Current behavior

1. Validate that `finding_id` and `evidence_path` are both set or both omitted.
2. Run scan-only on `ubuntu-latest` when no patch inputs are supplied.
3. Run scan plus patch on `[self-hosted, linux, x64, ollama]` when both patch inputs are supplied.
4. Upload the generated artifact bundle in both cases.
5. Add a patch summary to the workflow summary when patch generation runs.
6. Generate `github-review.md` and `github-review.json` after patch generation.
7. Generate line-aware inline review comment artifacts alongside the summary review.
8. Optionally post a PR comment when `post_github_comment=true` and a suitable token is available.

## Current limitation

Patch generation still depends on an Ollama-accessible model endpoint. That is acceptable for the first shipped workflow because the patch job is explicitly routed to a labeled self-hosted runner instead of pretending that GitHub-hosted runners can do local model inference.

Comment posting also depends on a token with permission to write to the target repository. The workflow reads that token from `GH_REVIEW_TOKEN` when it is provided, and private repository scan access depends on the same general token setup discipline.
