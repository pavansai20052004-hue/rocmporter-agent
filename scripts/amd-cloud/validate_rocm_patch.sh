#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/pytorch/extension-cpp"
REPO_DIR=""
PATCH_FILE=""
BUNDLE_DIR=""
OUTPUT_DIR="amd-cloud-validation-output"
PROJECT_SUBDIR="extension_cpp"
BUILD_COMMAND='USE_ROCM=1 USE_CUDA=0 python -m pip install --no-build-isolation -e .'
TEST_COMMAND='python test/test_extension.py'
SKIP_BUILD=0
SKIP_TEST=0
PYTHON_BIN="${PYTHON_BIN:-}"
SETUP_PYTHON_ENV=0
REQUIRE_ROCM=0
TORCH_SPEC="torch"
PYTORCH_INDEX_URL="https://download.pytorch.org/whl/rocm7.2"
PYTHON_DEPS="setuptools wheel ninja pytest pytest-mock pytest-cov expecttest numpy"
PYTHON_ENV_PREFIX=""

usage() {
  cat <<'USAGE'
Validate a ROCmPorter patch on an AMD Developer Cloud ROCm machine.

Required input:
  --patch-file PATH       Unified diff to validate
  --bundle-dir PATH       Export bundle containing patch-result.json and patch diff

Common options:
  --repo-url URL          Target repository URL
  --repo-dir PATH         Existing target repository checkout to reuse
  --output-dir PATH       Evidence output directory
  --project-subdir PATH   Directory containing setup.py inside target repo
  --build-command CMD     Build command run inside project subdir
  --test-command CMD      Test command run inside repo root
  --skip-build            Skip build command
  --skip-test             Skip test command
  --setup-python-env      Create a local venv and install Python build/test dependencies
  --require-rocm          Fail validation when ROCm/PyTorch GPU probes fail
  --torch-spec SPEC       Torch package spec for --setup-python-env
  --pytorch-index-url URL PyTorch package index URL for --setup-python-env

Example:
  ./scripts/amd-cloud/validate_rocm_patch.sh \
    --repo-url https://github.com/pytorch/extension-cpp \
    --patch-file examples/amd-cloud/extension_cpp_setup_rocm_candidate.diff
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --repo-dir) REPO_DIR="$2"; shift 2 ;;
    --patch-file) PATCH_FILE="$2"; shift 2 ;;
    --bundle-dir) BUNDLE_DIR="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --project-subdir) PROJECT_SUBDIR="$2"; shift 2 ;;
    --build-command) BUILD_COMMAND="$2"; shift 2 ;;
    --test-command) TEST_COMMAND="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --skip-test) SKIP_TEST=1; shift ;;
    --setup-python-env) SETUP_PYTHON_ENV=1; shift ;;
    --require-rocm) REQUIRE_ROCM=1; shift ;;
    --torch-spec) TORCH_SPEC="$2"; shift 2 ;;
    --pytorch-index-url) PYTORCH_INDEX_URL="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Python is required but neither python3 nor python was found." >&2
    exit 2
  fi
fi

OUTPUT_DIR="$("$PYTHON_BIN" - "$OUTPUT_DIR" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"

mkdir -p "$OUTPUT_DIR/logs"
RESULTS_TSV="$OUTPUT_DIR/results.tsv"
: > "$RESULTS_TSV"
REQUIRED_FAILED=0

if [[ -n "$BUNDLE_DIR" && -z "$PATCH_FILE" ]]; then
  if [[ ! -f "$BUNDLE_DIR/patch-result.json" ]]; then
    echo "Bundle is missing patch-result.json: $BUNDLE_DIR" >&2
    exit 2
  fi
  PATCH_FILE="$("$PYTHON_BIN" - "$BUNDLE_DIR" <<'PY'
import json
import sys
from pathlib import Path

bundle = Path(sys.argv[1])
patch = json.loads((bundle / "patch-result.json").read_text(encoding="utf-8"))
relative = patch.get("savedPatchPath")
if not relative:
    raise SystemExit("patch-result.json does not contain savedPatchPath")
print(bundle / relative)
PY
)"
fi

if [[ -z "$PATCH_FILE" ]]; then
  echo "Provide --patch-file or --bundle-dir." >&2
  usage >&2
  exit 2
fi

PATCH_FILE="$("$PYTHON_BIN" - "$PATCH_FILE" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"

if [[ ! -f "$PATCH_FILE" ]]; then
  echo "Patch file not found: $PATCH_FILE" >&2
  exit 2
fi

log_path() {
  local name="$1"
  echo "$OUTPUT_DIR/logs/${name}.log"
}

record_result() {
  local name="$1"
  local status="$2"
  local seconds="$3"
  local log="$4"
  printf '%s\t%s\t%s\t%s\n' "$name" "$status" "$seconds" "$log" >> "$RESULTS_TSV"
}

run_step() {
  local name="$1"
  shift
  local log
  log="$(log_path "$name")"
  local start
  start="$(date +%s)"
  set +e
  {
    echo "## $name"
    echo "## started_at=$(date -Is)"
    echo "## command=$*"
    "$@"
  } >"$log" 2>&1
  local status=$?
  set -e
  local end
  end="$(date +%s)"
  record_result "$name" "$status" "$((end - start))" "$log"
  return "$status"
}

run_shell_step() {
  local name="$1"
  local command="$2"
  run_step "$name" bash -lc "$command"
}

run_required_step() {
  local name="$1"
  shift
  run_step "$name" "$@" || REQUIRED_FAILED=1
}

run_required_shell_step() {
  local name="$1"
  local command="$2"
  run_shell_step "$name" "$command" || REQUIRED_FAILED=1
}

run_optional_step() {
  local name="$1"
  shift
  run_step "$name" "$@" || true
}

run_optional_shell_step() {
  local name="$1"
  local command="$2"
  run_shell_step "$name" "$command" || true
}

WORK_DIR="$OUTPUT_DIR/work"
mkdir -p "$WORK_DIR"

if [[ -n "$REPO_DIR" ]]; then
  TARGET_REPO="$("$PYTHON_BIN" - "$REPO_DIR" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
else
  TARGET_REPO="$WORK_DIR/target-repo"
fi

cat > "$OUTPUT_DIR/validation-context.json" <<JSON
{
  "repoUrl": "$REPO_URL",
  "repoDir": "$TARGET_REPO",
  "patchFile": "$PATCH_FILE",
  "projectSubdir": "$PROJECT_SUBDIR",
  "buildCommand": "$BUILD_COMMAND",
  "testCommand": "$TEST_COMMAND",
  "setupPythonEnv": $([[ "$SETUP_PYTHON_ENV" == "1" ]] && echo true || echo false),
  "requireRocm": $([[ "$REQUIRE_ROCM" == "1" ]] && echo true || echo false),
  "torchSpec": "$TORCH_SPEC",
  "pytorchIndexUrl": "$PYTORCH_INDEX_URL",
  "startedAt": "$(date -Is)"
}
JSON

run_optional_step "system_uname" uname -a
run_optional_shell_step "os_release" 'cat /etc/os-release'
run_optional_shell_step "rocm_paths" 'ls -la /opt/rocm || true; find /opt/rocm -maxdepth 2 -type f \( -name hipcc -o -name rocminfo \) 2>/dev/null | sort || true'
run_optional_shell_step "gpu_inventory" 'command -v amd-smi >/dev/null && amd-smi || true; command -v rocm-smi >/dev/null && rocm-smi || true'
if [[ "$REQUIRE_ROCM" == "1" ]]; then
  run_required_shell_step "rocminfo" 'command -v rocminfo >/dev/null && rocminfo | head -240'
  run_required_shell_step "hipcc_version" 'command -v hipcc >/dev/null && hipcc --version'
else
  run_optional_shell_step "rocminfo" 'command -v rocminfo >/dev/null && rocminfo | head -240 || true'
  run_optional_shell_step "hipcc_version" 'command -v hipcc >/dev/null && hipcc --version || true'
fi
run_optional_shell_step "python_version" "\"$PYTHON_BIN\" --version; \"$PYTHON_BIN\" -m pip --version"

if [[ "$SETUP_PYTHON_ENV" == "1" ]]; then
  VENV_DIR="$OUTPUT_DIR/venv"
  TORCH_INSTALL_ARGS="'$TORCH_SPEC'"
  if [[ -n "$PYTORCH_INDEX_URL" ]]; then
    TORCH_INSTALL_ARGS="$TORCH_INSTALL_ARGS --index-url '$PYTORCH_INDEX_URL'"
  fi
  run_required_shell_step "python_env_setup" "\"$PYTHON_BIN\" -m venv '$VENV_DIR' && source '$VENV_DIR/bin/activate' && python -m pip install --upgrade pip setuptools wheel && python -m pip install $PYTHON_DEPS && python -m pip install $TORCH_INSTALL_ARGS"
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    PYTHON_BIN="$VENV_DIR/bin/python"
    PYTHON_ENV_PREFIX="source '$VENV_DIR/bin/activate' &&"
    run_optional_shell_step "python_version_active_env" "\"$PYTHON_BIN\" --version; \"$PYTHON_BIN\" -m pip --version"
  fi
fi

TORCH_ROCM_PROBE_COMMAND="$(cat <<PY
"$PYTHON_BIN" - <<'PYTHON_PROBE'
import json
import torch

payload = {
    "torchVersion": torch.__version__,
    "torchHipVersion": getattr(torch.version, "hip", None),
    "cudaIsAvailableApi": torch.cuda.is_available(),
    "deviceCount": torch.cuda.device_count(),
}
if payload["deviceCount"]:
    payload["deviceName0"] = torch.cuda.get_device_name(0)
print(json.dumps(payload, indent=2))
PYTHON_PROBE
PY
)"
if [[ "$REQUIRE_ROCM" == "1" ]]; then
  run_required_shell_step "torch_rocm_probe" "$TORCH_ROCM_PROBE_COMMAND"
else
  run_optional_shell_step "torch_rocm_probe" "$TORCH_ROCM_PROBE_COMMAND"
fi

if [[ ! -d "$TARGET_REPO/.git" ]]; then
  rm -rf "$TARGET_REPO"
  run_required_step "clone_target_repo" git clone --depth 1 "$REPO_URL" "$TARGET_REPO"
else
  run_optional_shell_step "reuse_target_repo" "cd '$TARGET_REPO' && git rev-parse HEAD && git status --short"
fi

run_required_shell_step "prepare_clean_repo" "cd '$TARGET_REPO' && git reset --hard && git clean -fdx"
cp "$PATCH_FILE" "$OUTPUT_DIR/patch-under-test.diff"
run_required_shell_step "patch_check" "cd '$TARGET_REPO' && git apply --check -p0 '$PATCH_FILE'"
run_required_shell_step "patch_apply" "cd '$TARGET_REPO' && git apply -p0 '$PATCH_FILE'"
run_required_shell_step "patch_diff_after_apply" "cd '$TARGET_REPO' && git diff --stat && git diff -- '$PROJECT_SUBDIR/setup.py' > '$OUTPUT_DIR/applied.patch'"
run_required_shell_step "python_syntax" "cd '$TARGET_REPO' && \"$PYTHON_BIN\" -m py_compile '$PROJECT_SUBDIR/setup.py'"

if [[ "$SKIP_BUILD" == "0" ]]; then
  run_required_shell_step "rocm_build" "cd '$TARGET_REPO/$PROJECT_SUBDIR' && $PYTHON_ENV_PREFIX $BUILD_COMMAND"
else
  record_result "rocm_build" "skipped" "0" ""
fi

if [[ "$SKIP_TEST" == "0" ]]; then
  run_required_shell_step "project_tests" "cd '$TARGET_REPO' && $PYTHON_ENV_PREFIX $TEST_COMMAND"
else
  record_result "project_tests" "skipped" "0" ""
fi

"$PYTHON_BIN" - "$OUTPUT_DIR" "$RESULTS_TSV" <<'PY'
import csv
import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
rows = []
for row in csv.reader(Path(sys.argv[2]).read_text(encoding="utf-8").splitlines(), delimiter="\t"):
    if not row:
        continue
    name, status, seconds, log = row
    rows.append({
        "name": name,
        "status": "skipped" if status == "skipped" else ("passed" if status == "0" else "failed"),
        "exitCode": None if status == "skipped" else int(status),
        "durationSeconds": int(seconds),
        "log": log,
    })

required = {"prepare_clean_repo", "patch_check", "patch_apply", "patch_diff_after_apply", "python_syntax", "rocm_build", "project_tests"}
if any(row["name"] == "python_env_setup" for row in rows):
    required.add("python_env_setup")
if any(row["name"] == "torch_rocm_probe" and row["status"] != "skipped" for row in rows):
    context = json.loads((output_dir / "validation-context.json").read_text(encoding="utf-8"))
    if context.get("requireRocm"):
        required.add("rocminfo")
        required.add("hipcc_version")
        required.add("torch_rocm_probe")
failed = [row for row in rows if row["name"] in required and row["status"] == "failed"]
summary = {
    "state": "failed" if failed else "passed",
    "failedRequiredSteps": [row["name"] for row in failed],
    "steps": rows,
}
(output_dir / "validation-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

markdown = ["# AMD Developer Cloud ROCm Validation", "", f"- State: **{summary['state']}**", ""]
markdown.append("| Step | Status | Exit | Log |")
markdown.append("| --- | --- | ---: | --- |")
for row in rows:
    exit_code = "" if row["exitCode"] is None else str(row["exitCode"])
    log = row["log"].replace("\\", "/")
    markdown.append(f"| {row['name']} | {row['status']} | {exit_code} | `{log}` |")
(output_dir / "validation-summary.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

print(json.dumps(summary, indent=2))
raise SystemExit(1 if failed else 0)
PY
