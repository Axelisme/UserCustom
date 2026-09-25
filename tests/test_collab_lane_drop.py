"""collab_lane drop contract."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    FAIL_LANE_BRANCH_REMOVE,
    FAIL_STATUS,
    close_harness_for,
    git,
    invoke,
    last_telemetry_event,
    seed_managed_task,
    seed_repository,
    seed_task_container,
    write_git_wrapper,
)

setUpModule = _support.require_pi


class CollabOpExtensionLaneDropContractRegressionTests(unittest.TestCase):
    def test_drop_removes_clean_lane_and_records_internal_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            created = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
            )
            self.assertFalse(created["is_error"])
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            lane_sha = git(lane, "rev-parse", "HEAD")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["ok"])
            self.assertEqual(observed["result"]["tool_version"], 1)
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-drop")
            self.assertEqual(event["disposition"], "abandoned")
            self.assertEqual(event["lane_sha"], lane_sha)
            self.assertEqual(event["dirty"], False)
            self.assertEqual(event["uncollected"], False)
            self.assertEqual(expected["integration_head"], integration_sha)

    def test_drop_untracked_and_ignored_only_state_does_not_warn(self) -> None:
        for state in ("untracked", "ignored"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime state")
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lane = Path(expected["lane"])
                candidate = lane / ("ordinary.tmp" if state == "untracked" else "ignored.tmp")
                candidate.write_text(f"{state} runtime\n", encoding="utf-8")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertFalse(observed["is_error"])
                self.assertNotIn("warnings", observed["result"])
                self.assertFalse(lane.exists())
                self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
                self.assertEqual(last_telemetry_event(repository)["dirty"], False)

    def test_drop_tracked_and_staged_state_warn(self) -> None:
        for state in ("tracked", "staged"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lane = Path(expected["lane"])
                if state == "tracked":
                    (lane / "tracked.txt").write_text("modified\n", encoding="utf-8")
                else:
                    candidate = lane / "staged.txt"
                    candidate.write_text("staged\n", encoding="utf-8")
                    git(lane, "add", candidate.name)

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertFalse(observed["is_error"])
                self.assertTrue(
                    any(
                        "dirty or conflicted" in warning
                        for warning in observed["result"]["warnings"]
                    )
                )
                self.assertFalse(lane.exists())
                self.assertEqual(last_telemetry_event(repository)["dirty"], True)

    def test_drop_conflict_state_warns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "tracked.txt").write_text("lane conflict\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane conflict")
            (integration / "tracked.txt").write_text("integration conflict\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            reconciled = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertEqual(reconciled["result"]["state"], "conflicted")

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(
                any(
                    "dirty or conflicted" in warning
                    for warning in observed["result"]["warnings"]
                )
            )
            self.assertFalse(lane.exists())
            event = last_telemetry_event(repository)
            self.assertEqual(event["dirty"], True)
            self.assertEqual(event["conflicted"], True)

    def test_drop_unclassifiable_status_warns_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            wrapper = write_git_wrapper(base, FAIL_STATUS)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(
                any("incomplete" in warning for warning in observed["result"]["warnings"])
            )
            self.assertFalse(Path(expected["lane"]).exists())
            self.assertEqual(last_telemetry_event(repository)["incomplete"], True)

    def test_drop_reports_branch_cleanup_residual_after_path_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository)
            wrapper = write_git_wrapper(base, FAIL_LANE_BRANCH_REMOVE)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertFalse(Path(repository / ".agent_state/worktrees/demo/lanes/writer-1").exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "  wave/demo/writer-1")

    def test_drop_unlinks_canonical_symlink_without_touching_aliased_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            self.assertFalse(
                invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"})["is_error"]
            )
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            git(repository, "worktree", "remove", "--force", str(lane))
            unrelated = base / "unrelated-worktree"
            git(repository, "branch", "operator-preserve", git(repository, "rev-parse", "main"))
            git(repository, "worktree", "add", str(unrelated), "operator-preserve")
            (unrelated / "operator.txt").write_text("preserve\n", encoding="utf-8")
            lane.symlink_to(unrelated, target_is_directory=True)

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertFalse(lane.exists())
            self.assertTrue(unrelated.is_dir())
            self.assertEqual((unrelated / "operator.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertEqual(git(repository, "rev-parse", "operator-preserve"), git(unrelated, "rev-parse", "HEAD"))

    def test_drop_cleans_safe_resources_from_incomplete_inventory_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            lane = Path(repository / ".agent_state/worktrees/demo/lanes/writer-1")
            git(repository, "update-ref", "--no-deref", "-d", "refs/heads/wave/demo/writer-1")

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("incomplete" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")

    def test_drop_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


if __name__ == "__main__":
    unittest.main()
