# AMD Developer Cloud ROCm Validation

These scripts are for running ROCmPorter patch proof on an AMD Developer Cloud Linux machine with ROCm and a GPU-visible PyTorch environment.

## One-time runner setup

Create a self-hosted runner token in GitHub, then run on the AMD Cloud instance:

```bash
export GITHUB_REPO="https://github.com/<owner>/<repo>"
export RUNNER_TOKEN="<registration-token>"
bash scripts/amd-cloud/bootstrap_github_runner.sh
```

Use labels: `amd,rocm,devcloud,self-hosted`.

## Manual validation

```bash
bash scripts/amd-cloud/validate_rocm_patch.sh \
  --repo-url https://github.com/pytorch/extension-cpp \
  --patch-file examples/amd-cloud/extension_cpp_setup_rocm_candidate.diff \
  --output-dir amd-cloud-validation-output
```

The validator captures ROCm/GPU environment details, applies the patch, checks Python syntax, runs a build command, runs tests, and writes:

- `validation-summary.json`
- `validation-summary.md`
- step logs under `logs/`
- `patch-under-test.diff`
- `applied.patch`
