from __future__ import annotations

import base64
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from .env_config import get_github_token


GITHUB_REPO_PATTERN = re.compile(r"^/([^/]+)/([^/]+?)(?:\.git)?/?$")


def validate_repo_url(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Repository URL must start with http:// or https://")
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Only GitHub repositories are supported right now")

    match = GITHUB_REPO_PATTERN.match(parsed.path)
    if not match:
        raise ValueError("Enter a GitHub repository URL like https://github.com/org/repo")

    owner, repo = match.groups()
    return f"https://github.com/{owner}/{repo}"


def repo_name_from_url(repo_url: str) -> str:
    return repo_url.rstrip("/").split("/")[-1].removesuffix(".git")


def clone_repo(repo_url: str, target_dir: Path) -> str:
    if target_dir.exists():
        shutil.rmtree(target_dir)

    command = _clone_command(repo_url, target_dir)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Git is required for repository cloning. Install Git and make sure it is available in PATH.") from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "Unable to clone repository"
        if "Repository not found" in message or "Authentication failed" in message or "could not read Username" in message:
            message = (
                f"{message}\nIf this repository is private, add a GitHub token to backend/.env "
                "using GITHUB_PAT=your_token and retry."
            )
        raise RuntimeError(message)

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=target_dir,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    default_branch = branch.stdout.strip() or "main"
    return default_branch


def _clone_command(repo_url: str, target_dir: Path) -> list[str]:
    command = ["git", "clone", "--depth", "1"]
    token = get_github_token()
    if token:
        auth = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
        command.extend(["-c", f"http.extraheader=AUTHORIZATION: basic {auth}"])
    command.extend([repo_url, str(target_dir)])
    return command
