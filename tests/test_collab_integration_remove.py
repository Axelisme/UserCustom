"""collab_integration remove contract."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    FAIL_LANE_BRANCH_REMOVE,
    close_harness_for,
    git,
    invoke,
    seed_managed_task,
    seed_repository,
    write_git_wrapper,
)

setUpModule = _support.require_pi


class CollabOpExtensionIntegrationRemoveContractRegressionTests(unittest.TestCase):
    def test_remove_preserves_foreign_integration_symlink_custody(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            git(repository, "worktree", "remove", "--force", str(integration))
            foreign = base / "foreign-integration"
            git(repository, "branch", "foreign-integration", "main")
            git(repository, "worktree", "add", str(foreign), "foreign-integration")
            (foreign / "operator.txt").write_text("preserve\n", encoding="utf-8")
            integration.symlink_to(foreign, target_is_directory=True)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(integration.is_symlink())
            self.assertTrue(foreign.is_dir())
            self.assertEqual((foreign / "operator.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(git(repository, "branch", "--list", "foreign-integration"), "+ foreign-integration")
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repository), "show-ref", "--verify", "--quiet", "refs/orchestrate/demo/integration/base"],
                    capture_output=True,
                ).returncode,
                0,
            )

    def test_remove_continues_after_lane_branch_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            wrapper = write_git_wrapper(base, FAIL_LANE_BRANCH_REMOVE)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertFalse(Path(repository / ".agent_state/worktrees/demo/lanes/writer-1").exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "  wave/demo/writer-1")
            self.assertFalse(Path(repository / ".agent_state/worktrees/demo/integration").exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")

    def test_remove_retains_unrecognized_refs_while_cleaning_known_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            git(repository, "update-ref", "refs/orchestrate/demo/accepted", expected["integration_head"])

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("unrecognized task refs retained" in warning for warning in observed["result"]["warnings"]))
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/accepted"), expected["integration_head"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repository), "show-ref", "--verify", "--quiet", "refs/orchestrate/demo/integration/base"],
                    capture_output=True,
                ).returncode,
                0,
            )

    def test_remove_without_task_container_reports_telemetry_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


if __name__ == "__main__":
    unittest.main()
