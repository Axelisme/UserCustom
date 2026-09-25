"""collab_status."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    git,
    invoke,
    seed_managed_task,
    seed_repository,
    seed_task_container,
)

setUpModule = _support.require_pi


class CollabOpExtensionStatusTests(unittest.TestCase):
    def test_production_loader_registers_one_tool_and_lists_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            for task_id in ("zeta", "alpha"):
                git(
                    repository,
                    "update-ref",
                    f"refs/orchestrate/{task_id}/integration/base",
                    head,
                )

            observed = invoke(repository, {"tool": "collab_status"})

            self.assertEqual(
                observed["tools"],
                [
                    "collab_integration",
                    "collab_integration_adopt",
                    "collab_lane",
                    "collab_report",
                    "collab_status"],
            )
            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"tool_version": 1, "tasks": ["alpha", "zeta"], "warnings": []},
            )

    def test_task_status_projects_only_integration_and_live_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "tool_version": 1,
                    "task_id": "demo",
                    "integration": {
                        "worktree": expected["integration"],
                        "HEAD": expected["integration_head"],
                        "stale": False},
                    "lanes": {
                        "writer-1": {
                            "worktree": expected["lane"],
                            "HEAD": expected["integration_head"]}
                    },
                    "warnings": []},
            )
            self.assertNotIn("acceptance", observed["result"])
            self.assertNotIn("accepted", observed["result"])
            self.assertNotIn("pending_commits", observed["result"])
            self.assertNotIn("checkpoint", observed["result"])

    def test_status_from_a_managed_worktree_uses_the_common_control_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)

            observed = invoke(
                Path(expected["integration"]),
                {"tool": "collab_status", "task_id": "demo"},
            )

            self.assertEqual(observed["result"]["integration"]["worktree"], expected["integration"])
            self.assertEqual(observed["result"]["lanes"]["writer-1"]["worktree"], expected["lane"])
            self.assertEqual(observed["result"]["integration"]["HEAD"], expected["integration_head"])

    def test_persistence_advance_makes_integration_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            (repository / "tracked.txt").write_text("base\npersistence\n", encoding="utf-8")
            git(repository, "add", "tracked.txt")
            git(repository, "commit", "-m", "persistence advances")

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertTrue(observed["result"]["integration"]["stale"])

    def test_missing_persistence_identity_is_conservatively_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            git(repository, "symbolic-ref", "--delete", "refs/orchestrate/demo/persistence")

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertTrue(observed["result"]["integration"]["stale"])
            self.assertTrue(
                any("freshness could not be proven" in warning for warning in observed["result"]["warnings"])
            )

    def test_status_warns_for_tracked_lane_dirt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "tracked.txt").write_text("tracked change\n", encoding="utf-8")

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertTrue(
                any("lane writer-1 worktree is dirty" in warning for warning in observed["result"]["warnings"])
            )

    def test_status_and_report_do_not_warn_for_untracked_or_ignored_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore runtime state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            for worktree in (Path(expected["integration"]), Path(expected["lane"])):
                (worktree / "ordinary.tmp").write_text("ordinary runtime\n", encoding="utf-8")
                (worktree / "ignored.tmp").write_text("ignored runtime\n", encoding="utf-8")

            status_observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})
            report_observed = invoke(
                repository,
                {"tool": "collab_report", "task_id": "demo", "output_dir": "presence-report"},
            )

            self.assertFalse(status_observed["is_error"])
            self.assertEqual(status_observed["result"]["warnings"], [])
            self.assertFalse(report_observed["is_error"])
            self.assertNotIn("warnings", report_observed["result"])
            report = json.loads(
                (repository / "presence-report/collab-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["warnings"], [])

            (Path(expected["lane"]) / "tracked.txt").write_text(
                "tracked change\n", encoding="utf-8"
            )
            tracked_report_observed = invoke(
                repository,
                {"tool": "collab_report", "task_id": "demo", "output_dir": "tracked-report"},
            )
            self.assertFalse(tracked_report_observed["is_error"])
            self.assertTrue(
                any(
                    "lane writer-1 worktree is dirty" in warning
                    for warning in tracked_report_observed["result"]["warnings"]
                )
            )

    def test_refusal_uses_the_structured_pi_error_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(repository, {"tool": "collab_status", "task_id": "Not-Safe"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["ok"], False)
            self.assertNotIn("operation", observed["error"])
            self.assertEqual(observed["error"]["tool_version"], 1)
            self.assertEqual(observed["error"]["error"]["code"], "invalid_identifier")


if __name__ == "__main__":
    unittest.main()
