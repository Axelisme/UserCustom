"""collab_integration retarget."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    commit_agent_state_ignore,
    git,
    invoke,
    last_telemetry_event,
    seed_repository,
    seed_task_container,
)

setUpModule = _support.require_pi


def seed_stacked_tasks(repository: Path) -> Path:
    """Create task `base` on main and task `stacked` on base's integration; return base's worktree."""
    commit_agent_state_ignore(repository)
    seed_task_container(repository, "base")
    seed_task_container(repository, "stacked")
    created = invoke(
        repository, {"tool": "collab_integration", "action": "create", "task_id": "base"}
    )
    assert not created["is_error"], created
    base_integration = repository / ".agent_state/worktrees/base/integration"
    (base_integration / "base.txt").write_text("base work\n", encoding="utf-8")
    git(base_integration, "add", "base.txt")
    git(base_integration, "commit", "-m", "base work")
    stacked = invoke(
        base_integration, {"tool": "collab_integration", "action": "create", "task_id": "stacked"}
    )
    assert not stacked["is_error"], stacked
    return base_integration


class CollabOpExtensionIntegrationRetargetTests(unittest.TestCase):
    def test_retarget_moves_persistence_once_the_base_task_has_landed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_stacked_tasks(repository)
            self.assertEqual(
                git(repository, "symbolic-ref", "refs/orchestrate/stacked/persistence"),
                "refs/heads/wave/base/integration",
            )
            git(repository, "merge", "--no-ff", "-m", "land base", "wave/base/integration")

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration",
                    "action": "retarget",
                    "task_id": "stacked",
                    "persist": "main",
                },
            )

            self.assertFalse(observed["is_error"], observed)
            self.assertEqual(
                git(repository, "symbolic-ref", "refs/orchestrate/stacked/persistence"),
                "refs/heads/main",
            )
            event = last_telemetry_event(repository, "stacked")
            self.assertEqual(event["operation"], "integration-retarget")
            self.assertEqual(event["previous_persist"], "wave/base/integration")
            self.assertEqual(event["persist"], "main")
            reconciled = invoke(
                repository,
                {
                    "tool": "collab_lane",
                    "action": "reconcile_persistence",
                    "task_id": "stacked",
                    "lane_id": "sync",
                },
            )
            self.assertFalse(reconciled["is_error"], reconciled)
            self.assertEqual(
                reconciled["result"]["persistence_sha"], git(repository, "rev-parse", "main")
            )

    def test_retarget_refuses_a_branch_missing_the_current_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_stacked_tasks(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration",
                    "action": "retarget",
                    "task_id": "stacked",
                    "persist": "main",
                },
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "persistence_not_contained")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(
                git(repository, "symbolic-ref", "refs/orchestrate/stacked/persistence"),
                "refs/heads/wave/base/integration",
            )

    def test_retarget_refuses_unusable_persistence_branches(self) -> None:
        cases = {
            "missing": ("no-such-branch", "branch_unavailable"),
            "own integration": ("wave/stacked/integration", "invalid_branch"),
        }
        for case, (branch, code) in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                seed_stacked_tasks(repository)

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_integration",
                        "action": "retarget",
                        "task_id": "stacked",
                        "persist": branch,
                    },
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], code)
                self.assertEqual(
                    git(repository, "symbolic-ref", "refs/orchestrate/stacked/persistence"),
                    "refs/heads/wave/base/integration",
                )

    def test_remove_keeps_an_integration_that_another_task_stacks_on(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            base_integration = seed_stacked_tasks(repository)
            git(repository, "merge", "--no-ff", "-m", "land base", "wave/base/integration")

            refused = invoke(
                repository, {"tool": "collab_integration", "action": "remove", "task_id": "base"}
            )

            self.assertTrue(refused["is_error"])
            self.assertEqual(refused["error"]["error"]["code"], "integration_in_use")
            self.assertTrue(refused["error"]["error"]["repair"])
            self.assertTrue(base_integration.is_dir())
            self.assertNotEqual(git(repository, "branch", "--list", "wave/base/integration"), "")

            retargeted = invoke(
                repository,
                {
                    "tool": "collab_integration",
                    "action": "retarget",
                    "task_id": "stacked",
                    "persist": "main",
                },
            )
            self.assertFalse(retargeted["is_error"], retargeted)
            removed = invoke(
                repository, {"tool": "collab_integration", "action": "remove", "task_id": "base"}
            )
            self.assertFalse(removed["is_error"], removed)
            self.assertEqual(git(repository, "branch", "--list", "wave/base/integration"), "")

    def test_persist_is_required_for_retarget_and_rejected_elsewhere(self) -> None:
        requests = (
            {"action": "retarget", "task_id": "demo"},
            {"action": "create", "task_id": "demo", "persist": "main"},
        )
        for request in requests:
            with self.subTest(action=request["action"]), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))

                observed = invoke(repository, {"tool": "collab_integration", **request})

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")


if __name__ == "__main__":
    unittest.main()
