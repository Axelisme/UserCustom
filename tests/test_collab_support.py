"""Regression tests for the shared collab test helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    git,
    seed_repository,
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


if __name__ == "__main__":
    unittest.main()
