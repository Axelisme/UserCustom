"""collab_lane reconcile."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    git,
    invoke,
    last_telemetry_event,
    seed_managed_task,
    seed_repository,
    seed_task_container,
)

setUpModule = _support.require_pi


class CollabOpExtensionLaneReconcileRegressionTests(unittest.TestCase):
    def test_lane_reconcile_noop_preserves_integration_dirt_and_records_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                {key: observed["result"][key] for key in ("ok", "tool_version", "state", "warnings")},
                {
                    "ok": True,
                    "tool_version": 1,
                    "state": "noop",
                    "warnings": ["lane already includes latest integration"]},
            )
            self.assertEqual((integration / "operator-dirt.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-reconcile")
            self.assertEqual(event["outcome"], "noop")
            self.assertEqual(event["state"], "noop")

    def test_lane_reconcile_clean_merge_commits_one_exact_subject_and_leaves_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            lane_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            (integration / "committed.txt").write_text("committed\n", encoding="utf-8")
            git(integration, "add", "committed.txt")
            git(integration, "commit", "-m", "integration advance")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            (integration / "tracked.txt").write_text("dirty integration content\n", encoding="utf-8")
            (integration / "untracked.txt").write_text("dirty integration file\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "merged")
            merged_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            self.assertNotEqual(merged_sha, lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertEqual(
                git(repository, "rev-list", "--parents", "-n", "1", merged_sha).split(),
                [merged_sha, lane_sha, integration_sha],
            )
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual((integration / "tracked.txt").read_text(encoding="utf-8"), "dirty integration content\n")
            self.assertEqual((integration / "untracked.txt").read_text(encoding="utf-8"), "dirty integration file\n")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-reconcile")
            self.assertEqual(event["outcome"], "success")
            self.assertEqual(event["state"], "merged")
            self.assertEqual(event["lane_sha"], merged_sha)
            self.assertEqual(event["integration_sha"], integration_sha)

    def test_lane_reconcile_conflict_is_successful_bounded_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (lane / "tracked.txt").write_text("lane\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane conflict")
            lane_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            (integration / "tracked.txt").write_text("integration\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                {key: observed["result"][key] for key in ("ok", "tool_version", "state")},
                {"ok": True, "tool_version": 1, "state": "conflicted"},
            )
            self.assertTrue(observed["result"]["warnings"])
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertTrue(last_telemetry_event(repository)["conflict_path_count"] == 1)

    def test_lane_reconcile_unexpected_merge_failure_restores_exact_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "advance.txt").write_text("advance\n", encoding="utf-8")
            git(integration, "add", "advance.txt")
            git(integration, "commit", "-m", "integration advance")
            lane_sha = git(lane, "rev-parse", "HEAD")
            lock = git(lane, "rev-parse", "--git-path", "index.lock")
            lock_path = Path(lock) if Path(lock).is_absolute() else (lane / lock)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "git_error")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertTrue(observed["error"]["error"]["details"]["rollback"]["restored"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual(lock_path.read_text(encoding="utf-8"), "foreign lock\n")

    def test_lane_reconcile_refuses_tracked_dirt_and_identity_mismatches(self) -> None:
        for case in ("tracked", "identity"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                lane = Path(expected["lane"])
                if case == "tracked":
                    (lane / "tracked.txt").write_text("tracked change\n", encoding="utf-8")
                else:
                    git(lane, "checkout", "--detach")
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
                )
                self.assertTrue(observed["is_error"])
                self.assertEqual(
                    observed["error"]["error"]["code"],
                    "dirty_worktree" if case == "tracked" else "worktree_identity_mismatch",
                )
                self.assertTrue(observed["error"]["error"]["repair"])

    def test_lane_reconcile_accepts_untracked_and_ignored_paths(self) -> None:
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
                    {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertFalse(observed["is_error"])
                self.assertEqual(observed["result"]["state"], "noop")
                self.assertTrue(candidate.is_file())
                self.assertFalse(
                    any("dirty" in warning or "preserv" in warning for warning in observed["result"]["warnings"])
                )

    def test_lane_reconcile_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "advance.txt").write_text("advance\n", encoding="utf-8")
            git(integration, "add", "advance.txt")
            git(integration, "commit", "-m", "integration advance")

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


if __name__ == "__main__":
    unittest.main()
