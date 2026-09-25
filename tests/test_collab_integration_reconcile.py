"""collab_integration reconcile contract."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
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


class CollabOpExtensionIntegrationReconcileContractRegressionTests(unittest.TestCase):
    def test_reconcile_requires_tracked_cleanliness_and_matching_identity(self) -> None:
        for case in ("tracked", "identity"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                integration = Path(expected["integration"])
                if case == "tracked":
                    (integration / "tracked.txt").write_text("preserve tracked change\n", encoding="utf-8")
                else:
                    git(integration, "checkout", "--detach")

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_lane",
                        "action": "reconcile_persistence",
                        "task_id": "demo",
                        "lane_id": "repair"},
                )

                self.assertTrue(observed["is_error"])
                expected_code = "dirty_worktree" if case == "tracked" else "worktree_identity_mismatch"
                self.assertEqual(observed["error"]["error"]["code"], expected_code)
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_integration_reconcile_accepts_untracked_and_ignored_paths(self) -> None:
        for state in ("untracked", "ignored"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime state")
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                integration = Path(expected["integration"])
                candidate = integration / ("ordinary.tmp" if state == "untracked" else "ignored.tmp")
                candidate.write_text(f"{state} runtime\n", encoding="utf-8")

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_lane",
                        "action": "reconcile_persistence",
                        "task_id": "demo",
                        "lane_id": "repair"},
                )

                self.assertFalse(observed["is_error"])
                self.assertEqual(observed["result"]["state"], "noop")
                self.assertTrue(candidate.is_file())
                self.assertFalse(
                    any("dirty" in warning or "preserv" in warning for warning in observed["result"]["warnings"])
                )

    def test_reconcile_compensation_uses_native_non_force_worktree_removal(self) -> None:
        for state in ("untracked", "ignored"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                (repository / ".gitignore").write_text(".cache/\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime cache")
                seed_managed_task(repository)
                (repository / "persistence.txt").write_text("persistence advance\n", encoding="utf-8")
                git(repository, "add", "persistence.txt")
                git(repository, "commit", "-m", "advance persistence")
                lane = repository / ".agent_state/worktrees/demo/lanes/repair"
                candidate = lane / ("ordinary.tmp" if state == "untracked" else ".cache/runtime.tmp")
                wrapper_script = """#!/bin/sh
real_git="__REAL_GIT__"
if [ "$1" = "merge" ]; then
  mkdir -p "__PARENT__"
  printf 'runtime\\n' > "__CANDIDATE__"
  exit 73
fi
exec "$real_git" "$@"
""".replace("__PARENT__", str(candidate.parent)).replace("__CANDIDATE__", str(candidate))
                wrapper = write_git_wrapper(base, wrapper_script)
                original_path = os.environ["PATH"]
                os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
                close_harness_for(repository)
                try:
                    observed = invoke(
                        repository,
                        {
                            "tool": "collab_lane",
                            "action": "reconcile_persistence",
                            "task_id": "demo",
                            "lane_id": "repair"},
                    )
                finally:
                    os.environ["PATH"] = original_path
                    close_harness_for(repository)

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "git_error")
                compensation = observed["error"]["error"]["details"]["compensation"]
                if state == "untracked":
                    self.assertTrue(candidate.is_file())
                    self.assertTrue(lane.is_dir())
                    self.assertNotEqual(git(repository, "branch", "--list", "wave/demo/repair"), "")
                    self.assertFalse(compensation["restored"])
                else:
                    self.assertFalse(lane.exists())
                    self.assertEqual(git(repository, "branch", "--list", "wave/demo/repair"), "")
                    self.assertTrue(compensation["restored"])

    def test_reconcile_requires_one_persistence_checkout_at_direct_branch_tip(self) -> None:
        for case in ("head", "count"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                expected = seed_managed_task(repository)
                if case == "head":
                    side = base / "advance"
                    git(repository, "worktree", "add", "-b", "advance", str(side), "main")
                    (side / "advance.txt").write_text("advance\n", encoding="utf-8")
                    git(side, "add", "advance.txt")
                    git(side, "commit", "-m", "advance")
                    new_tip = git(side, "rev-parse", "HEAD")
                    git(repository, "update-ref", "refs/heads/main", new_tip)
                    git(repository, "checkout", "--detach", expected["base"])
                    git(repository, "worktree", "remove", "--force", str(side))
                else:
                    duplicate = base / "duplicate"
                    git(repository, "worktree", "add", "--force", str(duplicate), "main")

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_lane",
                        "action": "reconcile_persistence",
                        "task_id": "demo",
                        "lane_id": "repair"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "persistence_identity_mismatch")
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_reconcile_noop_warns_and_records_telemetry_without_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane",
                    "action": "reconcile_persistence",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["ok"], True)
            self.assertEqual(result["tool_version"], 1)
            self.assertEqual(result["state"], "noop")
            self.assertEqual(result["warnings"], ["persistence is already included in integration"])
            self.assertEqual(result["task_id"], "demo")
            self.assertEqual(result["lane_id"], "repair")
            self.assertEqual(result["lane_branch"], "wave/demo/repair")
            self.assertEqual(result["lane_path"], str(repository / ".agent_state/worktrees/demo/lanes/repair"))
            self.assertEqual(result["integration_sha"], expected["integration_head"])
            self.assertEqual(result["persistence_sha"], git(repository, "rev-parse", "main"))
            self.assertEqual(
                git(repository, "rev-parse", "wave/demo/integration"),
                expected["integration_head"],
            )
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/repair"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-reconcile")
            self.assertEqual(event["outcome"], "noop")
            self.assertEqual(event["state"], "noop")
            self.assertEqual(event["persist"], "main")

    def test_reconcile_clean_merge_creates_lane_and_leaves_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            persistence = repository
            (persistence / "persistence.txt").write_text("persistence\n", encoding="utf-8")
            git(persistence, "add", "persistence.txt")
            git(persistence, "commit", "-m", "persistence advance")
            persistence_sha = git(repository, "rev-parse", "main")
            (persistence / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane",
                    "action": "reconcile_persistence",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "merged")
            self.assertEqual(result["lane_id"], "repair")
            lane_sha = result["lane_sha"]
            self.assertNotEqual(lane_sha, expected["integration_head"])
            lane = repository / ".agent_state/worktrees/demo/lanes/repair"
            self.assertTrue(lane.exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/repair"), lane_sha)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo/repair"),
                "",
            )
            self.assertEqual(git(repository, "merge-base", "--is-ancestor", persistence_sha, lane_sha), "")
            self.assertEqual(git(repository, "merge-base", "--is-ancestor", expected["integration_head"], lane_sha), "")
            self.assertEqual((persistence / "operator-dirt.txt").read_text(encoding="utf-8"), "preserve\n")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-reconcile")
            self.assertEqual(event["outcome"], "success")
            self.assertEqual(event["state"], "merged")
            self.assertEqual(event["persistence_sha"], persistence_sha)

            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "repair"},
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertFalse(
                invoke(repository, {"tool": "collab_status", "task_id": "demo"})["result"]["integration"]["stale"]
            )

    def test_reconcile_conflict_preserves_lane_handoff_and_leaves_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "tracked.txt").write_text("integration conflict\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            (repository / "tracked.txt").write_text("persistence conflict\n", encoding="utf-8")
            git(repository, "add", "tracked.txt")
            git(repository, "commit", "-m", "persistence conflict")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            persistence_sha = git(repository, "rev-parse", "main")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane",
                    "action": "reconcile_persistence",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "conflicted")
            self.assertEqual(result["lane_id"], "repair")
            self.assertEqual(result["lane_sha"], integration_sha)
            self.assertEqual(result["integration_sha"], integration_sha)
            self.assertEqual(result["persistence_sha"], persistence_sha)
            self.assertEqual(result["conflict_paths"], ["tracked.txt"])
            lane = repository / ".agent_state/worktrees/demo/lanes/repair"
            self.assertTrue(lane.exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/repair"), integration_sha)
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-reconcile")
            self.assertEqual(event["outcome"], "success")
            self.assertEqual(event["state"], "conflicted")
            self.assertEqual(event["conflict_path_count"], 1)
            self.assertEqual(event["persistence_sha"], persistence_sha)

    def test_reconcile_collision_refuses_before_creating_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            (repository / "persistence.txt").write_text("persistence\n", encoding="utf-8")
            git(repository, "add", "persistence.txt")
            git(repository, "commit", "-m", "persistence advance")
            git(repository, "branch", "wave/demo/repair", expected["base"])

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane",
                    "action": "reconcile_persistence",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "lane_resource_collision")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_reconcile_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            (repository / "persistence.txt").write_text("persistence\n", encoding="utf-8")
            git(repository, "add", "persistence.txt")
            git(repository, "commit", "-m", "persistence advance")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane",
                    "action": "reconcile_persistence",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


if __name__ == "__main__":
    unittest.main()
