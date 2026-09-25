"""collab_lane collect contract."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    FAIL_LANE_BRANCH_REMOVE,
    FAIL_WORKTREE_REMOVE,
    close_harness_for,
    git,
    git_on_path,
    invoke,
    last_telemetry_event,
    seed_managed_task,
    seed_repository,
    seed_task_container,
    write_git_wrapper,
)

setUpModule = _support.require_pi


class CollabOpExtensionLaneCollectContractRegressionTests(unittest.TestCase):
    def test_collect_ignores_disposable_lane_state_and_creates_no_extra_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text("ignored.tmp\nignored-dir/\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore local state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            (lane / "ignored.tmp").write_text("ignored runtime\n", encoding="utf-8")
            (lane / "ignored-dir").mkdir()
            (lane / "runtime.txt").write_text("disposable\n", encoding="utf-8")
            self.assertEqual(git(lane, "status", "--porcelain=v1", "--untracked-files=no"), "")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_sha)
            self.assertEqual(git(repository, "rev-list", "--count", f"{expected['integration_head']}..wave/demo/integration"), "1")
            self.assertFalse(lane.exists())

    def test_collect_preserves_tracked_lane_dirt(self) -> None:
        for case in ("unstaged", "staged", "staged_new"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                lane = Path(expected["lane"])
                (lane / "work.txt").write_text("work\n", encoding="utf-8")
                git(lane, "add", "work.txt")
                git(lane, "commit", "-m", "work")
                lane_sha = git(lane, "rev-parse", "HEAD")
                if case == "unstaged":
                    (lane / "tracked.txt").write_text("preserve unstaged\n", encoding="utf-8")
                elif case == "staged":
                    (lane / "tracked.txt").write_text("preserve staged\n", encoding="utf-8")
                    git(lane, "add", "tracked.txt")
                else:
                    (lane / "newly-staged.txt").write_text("preserve staged path\n", encoding="utf-8")
                    git(lane, "add", "newly-staged.txt")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
                self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
                self.assertTrue(lane.exists())

    def test_collect_allows_disposable_integration_state_and_preserves_unrelated_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text("ignored.tmp\nignored-dir/\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore integration runtime")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            (integration / "ignored.tmp").write_text("ignored runtime\n", encoding="utf-8")
            (integration / "ignored-dir").mkdir()
            (integration / "runtime.txt").write_text("untracked runtime\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertEqual(git(integration, "rev-parse", "HEAD"), lane_sha)
            self.assertEqual((integration / "ignored.tmp").read_text(encoding="utf-8"), "ignored runtime\n")
            self.assertEqual((integration / "runtime.txt").read_text(encoding="utf-8"), "untracked runtime\n")
            self.assertTrue((integration / "ignored-dir").is_dir())

    def test_collect_rejects_moved_integration_identity_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            git(integration, "checkout", "--detach")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "worktree_identity_mismatch")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertTrue(lane.exists())

    def test_ready_collect_reset_overwrites_untracked_and_ignored_obstructions(self) -> None:
        for state in ("untracked", "ignored"):
            for shape in ("exact", "directory_to_file", "file_to_directory"):
                with self.subTest(state=state, shape=shape), tempfile.TemporaryDirectory() as temporary:
                    repository, _ = seed_repository(Path(temporary))
                    if state == "ignored":
                        (repository / ".gitignore").write_text("fresh.txt\npair\nignored-unrelated.tmp\n", encoding="utf-8")
                        git(repository, "add", ".gitignore")
                        git(repository, "commit", "-m", "ignore runtime state")
                    expected = seed_managed_task(repository)
                    seed_task_container(repository)
                    lane = Path(expected["lane"])
                    integration = Path(expected["integration"])
                    if shape == "exact":
                        (lane / "fresh.txt").write_text("lane exact content\n", encoding="utf-8")
                        git(lane, "add", "-f" if state == "ignored" else "--", "fresh.txt")
                        (integration / "fresh.txt").write_text(f"{state} obstruction\n", encoding="utf-8")
                    elif shape == "directory_to_file":
                        (lane / "pair").write_text("lane file content\n", encoding="utf-8")
                        git(lane, "add", "-f" if state == "ignored" else "--", "pair")
                        (integration / "pair").mkdir()
                        (integration / "pair/runtime.tmp").write_text(f"{state} obstruction\n", encoding="utf-8")
                    else:
                        (lane / "pair").mkdir()
                        (lane / "pair/accepted.txt").write_text("lane nested content\n", encoding="utf-8")
                        git(lane, "add", "-f" if state == "ignored" else "--", "pair/accepted.txt")
                        (integration / "pair").write_text(f"{state} obstruction\n", encoding="utf-8")
                    git(lane, "commit", "-m", f"lane {shape} transition")
                    lane_sha = git(lane, "rev-parse", "HEAD")
                    unrelated = integration / (
                        "ignored-unrelated.tmp" if state == "ignored" else "ordinary-unrelated.tmp"
                    )
                    unrelated.write_text(f"{state} unrelated\n", encoding="utf-8")

                    observed = invoke(
                        repository,
                        {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                    )

                    self.assertFalse(observed["is_error"])
                    self.assertEqual(observed["result"]["state"], "collected")
                    self.assertEqual(git(integration, "rev-parse", "HEAD"), lane_sha)
                    self.assertEqual(unrelated.read_text(encoding="utf-8"), f"{state} unrelated\n")
                    if shape == "exact":
                        self.assertEqual((integration / "fresh.txt").read_text(encoding="utf-8"), "lane exact content\n")
                    elif shape == "directory_to_file":
                        self.assertEqual((integration / "pair").read_text(encoding="utf-8"), "lane file content\n")
                    else:
                        self.assertEqual(
                            (integration / "pair/accepted.txt").read_text(encoding="utf-8"),
                            "lane nested content\n",
                        )

    def test_collect_preserves_tracked_integration_dirt_and_merge_state(self) -> None:
        for case in ("tracked", "merge"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                expected = seed_managed_task(repository)
                integration = Path(expected["integration"])
                lane = Path(expected["lane"])
                if case == "tracked":
                    (integration / "tracked.txt").write_text("preserve integration dirt\n", encoding="utf-8")
                else:
                    (repository / "tracked.txt").write_text("main conflict\n", encoding="utf-8")
                    git(repository, "add", "tracked.txt")
                    git(repository, "commit", "-m", "main conflict")
                    (integration / "tracked.txt").write_text("integration conflict\n", encoding="utf-8")
                    git(integration, "add", "tracked.txt")
                    git(integration, "commit", "-m", "integration conflict")
                    integration_before = git(repository, "rev-parse", "wave/demo/integration")
                    merge = subprocess.run(
                        ["git", "-C", str(integration), "merge", "--no-commit", "main"],
                        text=True,
                        capture_output=True,
                    )
                    self.assertNotEqual(merge.returncode, 0)
                    self.assertIn("UU tracked.txt", git(integration, "status", "--porcelain=v1"))

                integration_before = git(repository, "rev-parse", "wave/demo/integration")
                lane_before = git(repository, "rev-parse", "wave/demo/writer-1")
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
                self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_before)
                self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_before)
                self.assertTrue(integration.exists())

    def test_collect_rejects_an_active_lane_merge_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "tracked.txt").write_text("integration conflict\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            (lane / "tracked.txt").write_text("lane conflict\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane conflict")
            lane_sha = git(lane, "rev-parse", "HEAD")
            merge = subprocess.run(
                ["git", "-C", str(lane), "merge", "--no-commit", "wave/demo/integration"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertTrue(lane.exists())

    def test_collect_reconciles_stale_lane_then_collects_current_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            (integration / "advance.txt").write_text("advance\n", encoding="utf-8")
            git(integration, "add", "advance.txt")
            git(integration, "commit", "-m", "integration advance")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")

            reconciled = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertFalse(reconciled["is_error"])
            self.assertEqual(reconciled["result"]["state"], "reconciled")
            synced_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            self.assertTrue(git(repository, "merge-base", "--is-ancestor", integration_sha, synced_sha) == "")
            self.assertTrue(lane.exists())

            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")

    def test_collect_uses_current_tips_after_another_lane_moves_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            self.assertFalse(
                invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer-2"})["is_error"]
            )
            other = repository / ".agent_state/worktrees/demo/lanes/writer-2"
            (other / "other.txt").write_text("other\n", encoding="utf-8")
            git(other, "add", "other.txt")
            git(other, "commit", "-m", "other lane work")
            other_sha = git(other, "rev-parse", "HEAD")
            moved = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-2"},
            )
            self.assertFalse(moved["is_error"])
            self.assertEqual(moved["result"]["state"], "collected")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), other_sha)

            reconciled = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertFalse(reconciled["is_error"])
            self.assertEqual(reconciled["result"]["state"], "merged")
            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer-1").exists())
            self.assertNotIn("comparison_moved", collected["result"])

    def test_stale_collect_surfaces_native_untracked_merge_collisions_without_deletion(self) -> None:
        for shape in ("exact", "directory_to_file", "file_to_directory"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                lane = Path(expected["lane"])
                integration = Path(expected["integration"])
                lane_sha = git(lane, "rev-parse", "HEAD")
                if shape == "exact":
                    (integration / "collide.txt").write_text("accepted exact\n", encoding="utf-8")
                    git(integration, "add", "collide.txt")
                    blocker = lane / "collide.txt"
                    blocker.write_text("ordinary blocker\n", encoding="utf-8")
                elif shape == "directory_to_file":
                    (integration / "pair").write_text("accepted file\n", encoding="utf-8")
                    git(integration, "add", "pair")
                    blocker = lane / "pair/runtime.tmp"
                    blocker.parent.mkdir()
                    blocker.write_text("ordinary blocker\n", encoding="utf-8")
                else:
                    (integration / "pair").mkdir()
                    (integration / "pair/accepted.txt").write_text("accepted nested\n", encoding="utf-8")
                    git(integration, "add", "pair/accepted.txt")
                    blocker = lane / "pair"
                    blocker.write_text("ordinary blocker\n", encoding="utf-8")
                git(integration, "commit", "-m", f"integration {shape} transition")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "git_error")
                self.assertEqual(blocker.read_text(encoding="utf-8"), "ordinary blocker\n")
                self.assertEqual(git(lane, "rev-parse", "HEAD"), lane_sha)
                self.assertEqual(git(lane, "status", "--porcelain=v1", "--untracked-files=no"), "")

    def test_stale_collect_merge_overwrites_ignored_exact_and_file_directory_collisions(self) -> None:
        for shape in ("exact", "directory_to_file", "file_to_directory"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                (repository / ".gitignore").write_text("collide.txt\npair\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime state")
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lane = Path(expected["lane"])
                integration = Path(expected["integration"])
                if shape == "exact":
                    (integration / "collide.txt").write_text("accepted exact\n", encoding="utf-8")
                    git(integration, "add", "-f", "collide.txt")
                    (lane / "collide.txt").write_text("ignored blocker\n", encoding="utf-8")
                elif shape == "directory_to_file":
                    (integration / "pair").write_text("accepted file\n", encoding="utf-8")
                    git(integration, "add", "-f", "pair")
                    (lane / "pair").mkdir()
                    (lane / "pair/runtime.tmp").write_text("ignored blocker\n", encoding="utf-8")
                else:
                    (integration / "pair").mkdir()
                    (integration / "pair/accepted.txt").write_text("accepted nested\n", encoding="utf-8")
                    git(integration, "add", "-f", "pair/accepted.txt")
                    (lane / "pair").write_text("ignored blocker\n", encoding="utf-8")
                git(integration, "commit", "-m", f"integration {shape} transition")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertFalse(observed["is_error"])
                self.assertEqual(observed["result"]["state"], "reconciled")
                self.assertFalse(
                    any("dirty" in warning or "preserv" in warning for warning in observed["result"]["warnings"])
                )
                if shape == "exact":
                    self.assertEqual((lane / "collide.txt").read_text(encoding="utf-8"), "accepted exact\n")
                elif shape == "directory_to_file":
                    self.assertEqual((lane / "pair").read_text(encoding="utf-8"), "accepted file\n")
                else:
                    self.assertEqual(
                        (lane / "pair/accepted.txt").read_text(encoding="utf-8"),
                        "accepted nested\n",
                    )

    def test_collect_disposal_stays_within_selected_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            other_expected = seed_managed_task(repository, "other")
            lane = Path(expected["lane"])
            other_lane = repository / ".agent_state/worktrees/other/lanes/writer-1"
            other_integration = repository / ".agent_state/worktrees/other/integration"
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            (lane / "disposable-lane.txt").write_text("disposable\n", encoding="utf-8")
            (repository / "caller-untracked.txt").write_text("caller preserve\n", encoding="utf-8")
            (other_lane / "other-disposable.txt").write_text("other lane preserve\n", encoding="utf-8")
            (other_integration / "other-disposable.txt").write_text("other integration preserve\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertEqual((repository / "caller-untracked.txt").read_text(encoding="utf-8"), "caller preserve\n")
            self.assertEqual((other_lane / "other-disposable.txt").read_text(encoding="utf-8"), "other lane preserve\n")
            self.assertEqual((other_integration / "other-disposable.txt").read_text(encoding="utf-8"), "other integration preserve\n")
            self.assertEqual(git(repository, "rev-parse", "wave/other/writer-1"), other_expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/other/integration"), other_expected["integration_head"])
            self.assertFalse(lane.exists())

    def test_collect_preserves_lane_after_worktree_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            wrapper = write_git_wrapper(base, FAIL_WORKTREE_REMOVE)
            close_harness_for(repository)
            try:
                with git_on_path(wrapper.parent):
                    observed = invoke(
                        repository,
                        {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                    )
            finally:
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(lane.exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_sha)
            self.assertEqual(last_telemetry_event(repository)["cleanup_cleaned"], False)

    def test_collect_preserves_lane_after_branch_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            wrapper = write_git_wrapper(base, FAIL_LANE_BRANCH_REMOVE)
            close_harness_for(repository)
            try:
                with git_on_path(wrapper.parent):
                    observed = invoke(
                        repository,
                        {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                    )
            finally:
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(lane.exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_sha)

    def test_collect_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


if __name__ == "__main__":
    unittest.main()
