#!/usr/bin/env bash
set -Eeuo pipefail

if [[ -z "${GITHUB_REPO:-}" || -z "${RUNNER_TOKEN:-}" ]]; then
  cat >&2 <<'USAGE'
Set these environment variables first:

  export GITHUB_REPO="https://github.com/<owner>/<repo>"
  export RUNNER_TOKEN="<registration-token-from-github-runner-settings>"

Then run:

  bash scripts/amd-cloud/bootstrap_github_runner.sh
USAGE
  exit 2
fi

RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
RUNNER_VERSION="${RUNNER_VERSION:-2.326.0}"
RUNNER_LABELS="${RUNNER_LABELS:-amd,rocm,devcloud,self-hosted}"
RUNNER_NAME="${RUNNER_NAME:-amd-devcloud-$(hostname)}"

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

if [[ ! -f ./config.sh ]]; then
  archive="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
  curl -L -o "$archive" "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${archive}"
  tar xzf "$archive"
fi

./config.sh \
  --url "$GITHUB_REPO" \
  --token "$RUNNER_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --unattended \
  --replace

cat <<'NEXT'
Runner configured. To start it interactively:

  ./run.sh

For a persistent service on a supported Linux image:

  sudo ./svc.sh install
  sudo ./svc.sh start
NEXT
