"""Lane results carry the facts callers need for next actions."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    FAIL_LANE_BRANCH_REMOVE,
    FAIL_WORKTREE_REMOVE,
    close_harness_for,
    git,
    invoke,
    seed_managed_task,
    seed_repository,
    seed_task_container,
    write_git_wrapper,
)

setUpModule = _support.require_pi


class CollabOpLaneResultFactsTests(unittest.TestCase):
    def assert_identity(self, result: dict, repository: Path, lane_id: str) -> None:
        self.assertEqual(result["task_id"], "demo")
        self.assertEqual(result["lane_id"], lane_id)
        self.assertEqual(result["lane_branch"], f"wave/demo/{lane_id}")
        self.assertEqual(result["lane_path"], str(repository / f".agent_state/worktrees/demo/lanes/{lane_id}"))
        self.assertEqual(result["integration_branch"], "wave/demo/integration")
        self.assertEqual(result["integration_path"], str(repository / ".agent_state/worktrees/demo/integration"))

    def test_results_support_next_actions_without_status(self) -> None:
        for object_format in ("sha1", "sha256"):
            with self.subTest(object_format=object_format), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary), object_format)
                seed_task_container(repository)
                expected = seed_managed_task(repository)
                created = invoke(repository, {"tool": "collab_lane", "action": "create", "task_id": "demo", "lane_id": "writer"})["result"]
                self.assert_identity(created, repository, "writer")
                lane = Path(created["lane_path"])
                self.assertEqual(git(lane, "branch", "--show-current"), created["lane_branch"])
                self.assertEqual(git(lane, "rev-parse", "HEAD"), created["lane_sha"])
                self.assertEqual(created["lane_sha"], created["integration_sha"])
                self.assertEqual(created["integration_sha"], expected["integration_head"])
                reconciled = invoke(repository, {"tool": "collab_lane", "action": "reconcile", "task_id": "demo", "lane_id": "writer"})["result"]
                self.assert_identity(reconciled, repository, "writer")
                self.assertEqual(reconciled["state"], "noop")
                self.assertEqual(reconciled["lane_sha"], created["lane_sha"])
                (lane / "work.txt").write_text("work\n")
                git(lane, "add", "work.txt")
                git(lane, "commit", "-m", "work")
                sha = git(lane, "rev-parse", "HEAD")
                tree = git(lane, "rev-parse", "HEAD^{tree}")
                collected = invoke(repository, {"tool": "collab_lane", "action": "collect", "task_id": "demo", "lane_id": "writer"})["result"]
                self.assert_identity(collected, repository, "writer")
                self.assertEqual(collected["state"], "collected")
                self.assertEqual(collected["integration_sha"], sha)
                self.assertEqual(collected["integration_tree"], tree)
                self.assertEqual(git(Path(collected["integration_path"]), "rev-parse", "HEAD"), sha)
                self.assertEqual(collected["cleanup"], {"cleaned": True, "branch_exists": False, "worktree_registered": False, "path_exists": False})
                self.assertFalse(lane.exists())
                dropped = invoke(repository, {"tool": "collab_lane", "action": "drop", "task_id": "demo", "lane_id": "writer-1"})["result"]
                self.assert_identity(dropped, repository, "writer-1")
                self.assertEqual(dropped["cleanup"], {"cleaned": True, "branch_exists": False, "worktree_registered": False, "path_exists": False})
                self.assertEqual(dropped["disposition"], "abandoned")

    def test_failed_post_collection_observations_preserve_completed_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            marker = base / "observing"
            wrapper = write_git_wrapper(base, """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  case "$arg" in
    *'^{tree}') touch "__MARKER__"; echo 'tree observation unavailable' >&2; exit 1 ;;
  esac
done
if [ -f "__MARKER__" ]; then
  if [ "$1" = "symbolic-ref" ] || { [ "$1" = "worktree" ] && [ "$2" = "list" ]; }; then
    echo 'resource observation unavailable' >&2
    exit 128
  fi
fi
exec "$real_git" "$@"
""".replace("__MARKER__", str(marker)))
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            try:
                observed = invoke(repository, {"tool": "collab_lane", "action": "collect", "task_id": "demo", "lane_id": "writer-1"})
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)
            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "collected")
            self.assertEqual(result["integration_sha"], expected["integration_head"])
            self.assertIsNone(result["integration_tree"])
            self.assertEqual(result["cleanup"], {"cleaned": False, "branch_exists": None, "worktree_registered": None, "path_exists": False})
            for label in ("integration tree", "lane branch", "lane worktree registration"):
                self.assertTrue(any(label in warning for warning in result["warnings"]))
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), result["integration_sha"])
            self.assertFalse(Path(result["lane_path"]).exists())
            self.assertEqual(git(repository, "branch", "--list", result["lane_branch"]), "")

    def test_partial_cleanup_reports_actual_remaining_resources(self) -> None:
        for action, failure, present in (("collect", FAIL_WORKTREE_REMOVE, (True, True, True)), ("drop", FAIL_WORKTREE_REMOVE, (True, True, True)), ("drop", FAIL_LANE_BRANCH_REMOVE, (True, False, False))):
            with self.subTest(action=action, present=present), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                seed_task_container(repository)
                expected = seed_managed_task(repository)
                wrapper = write_git_wrapper(base, failure)
                original_path = os.environ["PATH"]
                os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
                try:
                    observed = invoke(repository, {"tool": "collab_lane", "action": action, "task_id": "demo", "lane_id": "writer-1"})
                finally:
                    os.environ["PATH"] = original_path
                    close_harness_for(repository)
                self.assertFalse(observed["is_error"])
                result = observed["result"]
                self.assert_identity(result, repository, "writer-1")
                self.assertEqual(result["cleanup"], dict(zip(("cleaned", "branch_exists", "worktree_registered", "path_exists"), (False, *present))))
                self.assertTrue(result["warnings"])
                if action == "collect":
                    self.assertEqual(result["state"], "collected")
                    self.assertEqual(result["integration_sha"], expected["integration_head"])
                    self.assertEqual(result["integration_tree"], git(repository, "rev-parse", "wave/demo/integration^{tree}"))


if __name__ == "__main__":
    unittest.main()
