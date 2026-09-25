"""Regression tests for the shared collab test helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    git,
    git_on_path,
    invoke,
    seed_repository,
    write_git_wrapper,
)

setUpModule = _support.require_pi


class CollabOpExtensionGitHelperRegressionTests(unittest.TestCase):
    def test_unstaged_tracked_deletion_keeps_leading_worktree_column(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / "tracked.txt").unlink()

            self.assertEqual(
                git(repository, "status", "--porcelain=v1"),
                " D tracked.txt",
            )



class CollabHarnessSharingTests(unittest.TestCase):
    def test_shared_harness_serves_each_repository_and_follows_environment_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / "first").mkdir()
            (base / "second").mkdir()
            first, _ = seed_repository(base / "first")
            second, _ = seed_repository(base / "second")
            log = base / "git-calls.log"
            wrapper = write_git_wrapper(
                base,
                f'#!/bin/sh\npwd -P >> "{log}"\nexec __REAL_GIT__ "$@"\n',
            )

            for repository in (first, second):
                observed = invoke(repository, {"tool": "collab_status"})
                self.assertFalse(observed["is_error"], observed)
            self.assertFalse(log.exists(), "the harness saw a wrapper that was not on PATH yet")

            with git_on_path(wrapper.parent):
                observed = invoke(second, {"tool": "collab_status"})
            self.assertFalse(observed["is_error"], observed)
            self.assertTrue(log.exists(), "a harness spawned before the PATH change served the request")
            self.assertIn(str(second.resolve()), log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
