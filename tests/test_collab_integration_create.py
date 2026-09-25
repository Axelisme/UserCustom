"""collab_integration create."""

from __future__ import annotations

from pathlib import Path
import stat
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


class CollabOpExtensionIntegrationCreateRegressionTests(unittest.TestCase):
    def test_create_builds_managed_resources_and_records_active_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            head = commit_agent_state_ignore(repository)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), head)
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"),
                head,
            )
            self.assertEqual(
                git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                "refs/heads/main",
            )
            status_result = invoke(
                repository,
                {"tool": "collab_status", "task_id": "demo"},
            )["result"]
            self.assertEqual(status_result["integration"]["HEAD"], head)
            self.assertFalse(status_result["integration"]["stale"])
            telemetry = repository / ".agent_state/plans/demo/.collab_op/telemetry.jsonl"
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-create")
            self.assertEqual(event["subject_sha"], head)
            self.assertEqual(event["persist"], "main")
            self.assertEqual(stat.S_IMODE(telemetry.stat().st_mode), 0o600)

    def test_create_without_task_container_warns_but_does_not_create_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in item for item in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())
            self.assertEqual(
                git(repository, "rev-parse", "wave/demo/integration"),
                git(repository, "rev-parse", "main"),
            )

    def test_create_records_telemetry_in_an_archived_container(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            commit_agent_state_ignore(repository)
            archive = seed_task_container(repository, archived=True)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertNotIn("warnings", observed["result"])
            self.assertTrue((archive / ".collab_op/telemetry.jsonl").is_file())

    def test_create_collision_refuses_without_changing_existing_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            root = repository / ".agent_state/worktrees/demo"
            root.mkdir(parents=True)
            sentinel = root / "user.txt"
            sentinel.write_text("preserve\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")

    def test_create_detached_head_refuses_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            git(repository, "checkout", "--detach", head)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "detached_head")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")

    def test_create_symlinked_managed_parent_refuses_without_writing_through_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            outside = base / "outside"
            outside.mkdir()
            (repository / ".agent_state").symlink_to(outside, target_is_directory=True)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(list(outside.iterdir()), [])

    def test_create_later_ref_failure_rolls_back_worktree_and_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            lock = repository / ".git/refs/orchestrate/demo/integration/base.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo"),
                "",
            )
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())
            self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock\n")

    def test_create_adjacent_task_namespace_does_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            git(repository, "update-ref", "refs/orchestrate/demo-extra/integration/base", head)
            git(repository, "branch", "wave/demo-extra/integration", head)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), head)


if __name__ == "__main__":
    unittest.main()
