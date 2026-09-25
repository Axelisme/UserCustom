""".agent_state exclusion across collab tools."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    commit_agent_state_ignore,
    exclude_file,
    exclusion_lines,
    exclusion_warnings,
    git,
    invoke,
    managed_ref_snapshot,
    seed_donor,
    seed_repository,
    seed_task_container,
)

setUpModule = _support.require_pi


class CollabOpExtensionAgentStateExclusionTests(unittest.TestCase):
    def test_create_in_unprepared_repository_excludes_managed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(exclusion_lines(repository), ["/.agent_state/"])
            self.assertEqual(git(repository, "status", "--porcelain"), "")
            self.assertTrue((repository / ".agent_state/worktrees/demo/integration").is_dir())

    def test_adopt_in_unprepared_repository_excludes_managed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            _, source_sha = seed_donor(repository, base, base_sha)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha,
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["integration_branch"], "wave/demo/integration")
            self.assertEqual(exclusion_lines(repository), ["/.agent_state/"])
            self.assertEqual(git(repository, "status", "--porcelain"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), source_sha)

    def test_already_ignored_repository_keeps_exclude_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            commit_agent_state_ignore(repository)
            seed_task_container(repository)
            before = exclude_file(repository).read_bytes()

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(exclude_file(repository).read_bytes(), before)
            self.assertEqual(git(repository, "status", "--porcelain"), "")

    def test_second_establishing_call_appends_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository, "demo")
            seed_task_container(repository, "second")

            first = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )
            after_first = exclude_file(repository).read_bytes()
            second = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "second"},
            )

            self.assertFalse(first["is_error"])
            self.assertFalse(second["is_error"])
            self.assertEqual(exclusion_lines(repository), ["/.agent_state/"])
            self.assertEqual(exclude_file(repository).read_bytes(), after_first)
            self.assertEqual(git(repository, "status", "--porcelain"), "")

    def test_negated_ignore_rule_refuses_before_any_managed_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            commit_agent_state_ignore(repository, "!.agent_state")
            seed_task_container(repository)
            before_refs = managed_ref_snapshot(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "agent_state_not_ignored")
            self.assertTrue(error["repair"])
            self.assertEqual(
                [entry["pattern"] for entry in error["details"]["overriding_patterns"]],
                ["!.agent_state"],
            )
            self.assertTrue(error["details"]["exclude_written"])
            self.assertIn("appended line remains", error["message"])
            self.assertIn("appended line remains", error["repair"])
            self.assertEqual(exclusion_lines(repository), ["/.agent_state/"])
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_preexisting_exclusion_failure_does_not_claim_this_call_wrote_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            commit_agent_state_ignore(repository, "!.agent_state")
            seed_task_container(repository)
            exclude_file(repository).write_text("/.agent_state/\n", encoding="utf-8")
            before = exclude_file(repository).read_bytes()

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "agent_state_not_ignored")
            self.assertFalse(error["details"]["exclude_written"])
            self.assertIn("this call did not modify", error["message"])
            self.assertNotIn("appended line remains", error["repair"])
            self.assertEqual(exclude_file(repository).read_bytes(), before)

    def test_non_regular_exclude_file_returns_coded_io_error_without_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            exclusion = exclude_file(repository)
            exclusion.unlink()
            exclusion.mkdir()
            before_refs = managed_ref_snapshot(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "agent_state_exclusion_io_error")
            self.assertTrue(error["repair"])
            self.assertEqual(
                error["details"]["operation"],
                "validate the exclusion file",
            )
            self.assertEqual(error["details"]["exclude_file"], str(exclusion))
            self.assertEqual(error["details"]["path_type"], "directory")
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_symlinked_exclude_file_is_rejected_before_it_can_discard_the_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            exclusion = exclude_file(repository)
            exclusion.unlink()
            exclusion.symlink_to("/dev/null")
            before_refs = managed_ref_snapshot(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "agent_state_exclusion_io_error")
            self.assertEqual(error["details"]["operation"], "validate the exclusion file")
            self.assertEqual(error["details"]["exclude_file"], str(exclusion))
            self.assertEqual(error["details"]["path_type"], "symbolic link")
            self.assertNotIn("exclude_written", error["details"])
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_only_a_performed_exclusion_write_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            homes = Path(temporary)
            (homes / "unprepared").mkdir()
            (homes / "prepared").mkdir()
            unprepared, _ = seed_repository(homes / "unprepared")
            seed_task_container(unprepared)
            prepared, _ = seed_repository(homes / "prepared")
            commit_agent_state_ignore(prepared)
            seed_task_container(prepared)

            wrote = invoke(
                unprepared,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )
            untouched = invoke(
                prepared,
                {"tool": "collab_integration", "action": "create", "task_id": "demo"},
            )

            self.assertFalse(wrote["is_error"])
            self.assertFalse(untouched["is_error"])
            self.assertEqual(len(exclusion_warnings(wrote["result"])), 1)
            self.assertIn("/.agent_state/", exclusion_warnings(wrote["result"])[0])
            self.assertEqual(exclusion_warnings(untouched["result"]), [])

    def test_unprepared_repository_runs_a_task_through_to_landing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)

            self.assertFalse(
                invoke(
                    repository,
                    {"tool": "collab_integration", "action": "create", "task_id": "demo"},
                )["is_error"]
            )
            self.assertFalse(
                invoke(
                    repository,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
                )["is_error"]
            )
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            (lane / "work.txt").write_text("lane work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")

            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer"},
            )
            landed = invoke(
                repository,
                {"tool": "collab_integration", "action": "land", "task_id": "demo", "message": "Ship lane work"},
            )

            self.assertEqual(collected["result"]["state"], "collected")
            self.assertFalse(landed["is_error"])
            self.assertEqual(
                (repository / "work.txt").read_text(encoding="utf-8"), "lane work\n"
            )
            self.assertEqual(git(repository, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
