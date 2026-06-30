from __future__ import annotations

import os
from pathlib import Path


_LOADED = False


def load_local_env() -> None:
    global _LOADED
    if _LOADED:
        return

    candidate_paths = [
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ]

    for path in candidate_paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)

    _LOADED = True


def get_github_token() -> str | None:
    load_local_env()
    for key in ("ROCMPORTER_GITHUB_TOKEN", "GITHUB_PAT", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.getenv(key)
        if value:
            return value.strip()
    return None
