from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.repo_fetcher import clone_repo, is_transient_clone_failure  # noqa: E402


class RepoFetcherTests(unittest.TestCase):
    def test_transient_clone_failure_detector_matches_dns_message(self) -> None:
        self.assertTrue(is_transient_clone_failure("fatal: unable to access 'https://github.com/x/y/': Could not resolve host: github.com"))
        self.assertTrue(is_transient_clone_failure("Command '['git', 'clone']' timed out after 120 seconds"))
        self.assertFalse(is_transient_clone_failure("fatal: repository not found"))

    def test_clone_repo_retries_once_for_transient_network_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            target_dir = Path(raw_dir) / "repo"

            clone_failure = __import__("subprocess").CompletedProcess(
                args=["git", "clone"],
                returncode=128,
                stdout="",
                stderr="fatal: unable to access 'https://github.com/example/repo/': Could not resolve host: github.com",
            )
            clone_success = __import__("subprocess").CompletedProcess(
                args=["git", "clone"],
                returncode=0,
                stdout="",
                stderr="",
            )
            branch_success = __import__("subprocess").CompletedProcess(
                args=["git", "branch", "--show-current"],
                returncode=0,
                stdout="main\n",
                stderr="",
            )

            with patch("app.repo_fetcher.subprocess.run", side_effect=[clone_failure, clone_success, branch_success]) as run_mock:
                with patch("app.repo_fetcher.time.sleep") as sleep_mock:
                    branch = clone_repo("https://github.com/example/repo", target_dir)

        self.assertEqual(branch, "main")
        self.assertEqual(run_mock.call_count, 3)
        sleep_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
