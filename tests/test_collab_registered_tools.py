"""Registered collab tools: schemas, envelopes, and cross-tool behavior."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    FAIL_WORKTREE_REMOVE,
    REPORT_SNAPSHOT_BLOCK_WRAPPER,
    close_harness,
    close_harness_for,
    commit_agent_state_ignore,
    git,
    git_on_path,
    invoke,
    last_telemetry_event,
    seed_donor,
    seed_managed_task,
    seed_repository,
    seed_task_container,
    send_request,
    spawn_raw_harness,
    telemetry_events,
    wait_until,
    write_git_wrapper,
)

setUpModule = _support.require_pi


class CollabOpExtensionRegisteredToolTests(unittest.TestCase):
    def test_final_inventory_exposes_only_independent_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

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
            self.assertEqual(set(observed["schemas"]), set(observed["tools"]))
            self.assertFalse(observed["is_error"])
            for name in observed["tools"]:
                schema = observed["schemas"][name]["parameters"]
                self.assertEqual(schema["type"], "object")
                self.assertFalse(schema["additionalProperties"])
                self.assertIn("repo", schema["properties"])
                self.assertNotIn("repo", schema.get("required", []))
            integration_schema = observed["schemas"]["collab_integration"]["parameters"]
            self.assertEqual(
                set(integration_schema["properties"]),
                {"action", "task_id", "message", "repo"},
            )
            self.assertEqual(integration_schema["required"], ["action", "task_id"])
            self.assertEqual(integration_schema["properties"]["action"]["enum"], ["create", "land", "remove"])
            lane_schema = observed["schemas"]["collab_lane"]["parameters"]
            self.assertEqual(
                lane_schema["properties"]["action"]["enum"],
                ["create", "reconcile", "reconcile_persistence", "collect", "drop"],
            )
            for name in observed["tools"]:
                self.assertNotIn("method", observed["schemas"][name]["parameters"]["properties"])

            for legacy_name in (
                "collab_op",
                "collab_integration_create",
                "collab_integration_land",
                "collab_integration_reconcile",
                "collab_integration_remove",
            ):
                legacy = invoke(repository, {"tool": legacy_name, "method": "status"})
                self.assertTrue(legacy["is_error"])
                self.assertEqual(legacy["error"]["error"]["code"], "unknown_tool")

    def test_action_specific_integration_parameters_are_rejected_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)

            for action in ("create", "remove"):
                observed = invoke(
                    repository,
                    {
                        "tool": "collab_integration",
                        "action": action,
                        "task_id": "demo",
                        "message": "not valid here",
                    },
                )
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertFalse((repository / ".agent_state/worktrees/demo/integration").exists())

    def test_repo_selects_create_target_from_outside_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            seed_task_container(target)

            observed = invoke(
                outside,
                {
                    "tool": "collab_integration",
                    "action": "create",
                    "task_id": "demo",
                    "repo": str(target),
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue((target / ".agent_state/worktrees/demo/integration").is_dir())
            self.assertEqual(git(target, "status", "--porcelain"), "")

    def test_repo_drives_complete_lifecycle_from_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            commit_agent_state_ignore(target)
            seed_task_container(target)
            selected_repo = str(target)

            created = invoke(
                outside,
                {
                    "tool": "collab_integration",
                    "action": "create",
                    "task_id": "demo",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(created["is_error"])

            lane_created = invoke(
                outside,
                {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": "writer",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(lane_created["is_error"])
            lane = Path(lane_created["result"]["lane_path"])
            self.assertEqual(lane, target / ".agent_state/worktrees/demo/lanes/writer")
            self.assertEqual(git(lane, "rev-parse", "HEAD"), lane_created["result"]["lane_sha"])
            (lane / "work.txt").write_text("lane work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")

            collected = invoke(
                outside,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")

            landed = invoke(
                outside,
                {
                    "tool": "collab_integration",
                    "action": "land",
                    "task_id": "demo",
                    "message": "Land selected repository work",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(landed["is_error"])
            self.assertEqual(git(target, "show", "HEAD:work.txt"), "lane work")
            self.assertFalse((outside / ".agent_state").exists())

            removed = invoke(
                outside,
                {
                    "tool": "collab_integration",
                    "action": "remove",
                    "task_id": "demo",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(removed["is_error"])
            self.assertFalse((target / ".agent_state/worktrees/demo").exists())

    def test_repo_rejects_invalid_shapes_before_git_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            file_path = base / "not-a-directory"
            file_path.write_text("file\n", encoding="utf-8")
            invalid_values: tuple[tuple[str, object], ...] = (
                ("non-string", 7),
                ("empty", ""),
                ("relative", "repository"),
                ("missing", str(base / "missing")),
                ("file", str(file_path)),
            )

            for case, value in invalid_values:
                with self.subTest(case=case):
                    observed = invoke(
                        outside,
                        {"tool": "collab_status", "repo": value},
                    )
                    self.assertTrue(observed["is_error"])
                    self.assertEqual(observed["error"]["error"]["code"], "invalid_repo")
                    self.assertTrue(observed["error"]["error"]["repair"])

    def test_repo_rejects_subdirectory_with_worktree_root_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            subdirectory = target / "nested"
            subdirectory.mkdir()

            observed = invoke(
                outside,
                {"tool": "collab_status", "repo": str(subdirectory)},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "repo_not_worktree_root")
            self.assertEqual(error["details"]["worktree_root"], str(target.resolve()))

    def test_repo_rejects_directory_outside_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            selected = base / "not-a-repository"
            selected.mkdir()

            observed = invoke(
                outside,
                {"tool": "collab_status", "repo": str(selected)},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "not_git_repository")
            self.assertTrue(error["repair"])

    def test_repo_accepts_symlink_to_worktree_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            selected = base / "selected-repository"
            selected.symlink_to(target, target_is_directory=True)

            observed = invoke(
                outside,
                {"tool": "collab_status", "repo": str(selected)},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["tasks"], [])

    def test_repo_accepts_linked_worktree_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            linked_worktree = base / "linked-worktree"
            git(target, "worktree", "add", "-b", "linked", str(linked_worktree), "HEAD")

            observed = invoke(
                outside,
                {"tool": "collab_status", "repo": str(linked_worktree)},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["tasks"], [])

    def test_repo_selects_named_worktree_attached_branch_for_create(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            session_base = base / "session"
            session_base.mkdir()
            session_repository, _ = seed_repository(session_base)
            git(session_repository, "checkout", "-b", "session-persist")
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            git(target, "checkout", "-b", "target-persist")
            seed_task_container(target)

            observed = invoke(
                session_repository,
                {
                    "tool": "collab_integration",
                    "action": "create",
                    "task_id": "demo",
                    "repo": str(target),
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                git(target, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                "refs/heads/target-persist",
            )
            self.assertEqual(
                git(session_repository, "symbolic-ref", "--short", "HEAD"),
                "session-persist",
            )

    def test_repo_controls_relative_report_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            seed_task_container(target)
            selected_repo = str(target)
            created = invoke(
                outside,
                {
                    "tool": "collab_integration",
                    "action": "create",
                    "task_id": "demo",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(created["is_error"])

            observed = invoke(
                outside,
                {
                    "tool": "collab_report",
                    "task_id": "demo",
                    "output_dir": "reports/selected",
                    "repo": selected_repo,
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue((target / "reports/selected/collab-report.json").is_file())
            self.assertTrue((target / "reports/selected/collab-telemetry.jsonl").is_file())
            self.assertFalse((outside / "reports").exists())

    def test_reconcile_persistence_derives_branch_and_projects_lane_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            (repository / "persistence.txt").write_text("persisted\n", encoding="utf-8")
            git(repository, "add", "persistence.txt")
            git(repository, "commit", "-m", "persistence work")
            persistence_sha = git(repository, "rev-parse", "HEAD")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane",
                    "action": "reconcile_persistence",
                    "task_id": "demo",
                    "lane_id": "persistence"},
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "merged")
            self.assertEqual(result["lane_id"], "persistence")
            self.assertEqual(result["integration_sha"], expected["integration_head"])
            self.assertEqual(result["persistence_sha"], persistence_sha)
            self.assertEqual(result["lane_sha"], git(repository, "rev-parse", "wave/demo/persistence"))
            self.assertEqual(result["lane_branch"], "wave/demo/persistence")
            self.assertEqual(result["lane_path"], str(repository / ".agent_state/worktrees/demo/lanes/persistence"))
            self.assertNotIn("persist", result)
            self.assertNotIn("conflict_paths", result)

    def test_integration_land_derives_persistence_and_projects_common_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            seed_task_container(repository)
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "land", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["ok"], True)
            self.assertEqual(observed["result"]["tool_version"], 1)
            self.assertNotIn("integration_sha", observed["result"])
            self.assertNotIn("persistence_sha", observed["result"])
            self.assertNotIn("landed_sha", observed["result"])

    def test_integration_remove_best_effort_cleans_dirty_uncollected_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "lane-work.txt").write_text("uncollected\n", encoding="utf-8")
            git(lane, "add", "lane-work.txt")
            git(lane, "commit", "-m", "lane work")
            (Path(expected["integration"]) / "dirty.txt").write_text("dirty\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                {key for key in observed["result"] if key != "warnings"},
                {"ok", "tool_version"},
            )
            self.assertTrue(observed["result"].get("warnings"))
            self.assertFalse(Path(expected["integration"]).exists())
            self.assertFalse(Path(expected["lane"]).exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repository), "show-ref", "--verify", "--quiet", "refs/orchestrate/demo/integration/base"],
                    capture_output=True,
                ).returncode,
                0,
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repository), "symbolic-ref", "--quiet", "refs/orchestrate/demo/persistence"],
                    capture_output=True,
                ).returncode,
                0,
            )

    def test_integration_remove_force_retires_untracked_and_ignored_paths_without_warning(self) -> None:
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

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertNotIn("warnings", observed["result"])
            self.assertFalse(Path(expected["integration"]).exists())
            self.assertFalse(Path(expected["lane"]).exists())

    def test_integration_remove_reports_residuals_and_continues_after_git_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            wrapper = write_git_wrapper(base, FAIL_WORKTREE_REMOVE)
            close_harness_for(repository)
            try:
                with git_on_path(wrapper.parent):
                    observed = invoke(
                        repository,
                        {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
                    )
            finally:
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(Path(expected["integration"]).exists())
            self.assertTrue(Path(expected["lane"]).exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "+ wave/demo/integration")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "+ wave/demo/writer-1")

    def test_migration_namespace_does_not_gate_current_tools_or_get_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, base_sha = seed_repository(Path(temporary))
            seed_task_container(repository)
            seed_managed_task(repository)
            git(repository, "update-ref", "refs/orchestrate/demo/migration", base_sha)

            observed = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "new-lane"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/migration"),
                base_sha,
            )
            status = invoke(repository, {"tool": "collab_status", "task_id": "demo"})
            self.assertFalse(status["is_error"])
            self.assertNotIn("recovery_required", status["result"])

    def test_legacy_layout_returns_ordinary_error_without_deleting_unknown_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, base_sha = seed_repository(Path(temporary))
            git(repository, "update-ref", "refs/orchestrate/demo/accepted", base_sha)

            observed = invoke(
                repository,
                {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_not_found")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/accepted"),
                base_sha,
            )

    def test_all_final_tools_return_actionable_structured_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            requests = (
                ("collab_integration", {"action": "create"}),
                ("collab_integration_adopt", {"task_id": "demo"}),
                ("collab_lane", {"action": "reconcile_persistence", "task_id": "demo"}),
                ("collab_integration", {"action": "land"}),
                ("collab_integration", {"action": "remove"}),
                ("collab_lane_create", {"task_id": "demo"}),
                ("collab_lane_reconcile", {"task_id": "demo"}),
                ("collab_lane_collect", {"task_id": "demo"}),
                ("collab_lane_drop", {"task_id": "demo"}),
                ("collab_report", {"task_id": "demo"}),
                ("collab_status", {"task_id": "Not-Safe"}),
            )

            for tool, request in requests:
                with self.subTest(tool=tool):
                    observed = invoke(repository, {"tool": tool, **request})
                    self.assertTrue(observed["is_error"])
                    error = observed["error"]
                    self.assertEqual(error["ok"], False)
                    self.assertEqual(error["tool_version"], 1)
                    self.assertNotIn("operation", error)
                    self.assertIsInstance(error["error"]["code"], str)
                    self.assertTrue(error["error"]["message"])
                    self.assertTrue(error["error"]["repair"])

    def test_complete_lifecycle_uses_only_final_registered_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
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
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")

            reported = invoke(
                repository,
                {"tool": "collab_report", "task_id": "demo", "output_dir": "reports"},
            )
            self.assertFalse(reported["is_error"])
            self.assertTrue((repository / "reports/collab-report.json").is_file())
            # Reports are ordinary untracked; clean before native landing (S4 requires no ordinary untracked)
            import shutil
            shutil.rmtree(repository / "reports")

            landed = invoke(
                repository,
                {"tool": "collab_integration", "action": "land", "task_id": "demo", "message": "Ship lane work"},
            )
            self.assertFalse(landed["is_error"])
            self.assertEqual(landed["result"]["ok"], True)
            self.assertEqual(landed["result"]["tool_version"], 1)
            self.assertNotIn("warnings", landed["result"])

            removed = invoke(
                repository,
                {"tool": "collab_integration", "action": "remove", "task_id": "demo"},
            )
            self.assertFalse(removed["is_error"])
            self.assertEqual(set(removed["result"]), {"ok", "tool_version"})

    def test_report_snapshots_fixed_artifacts_at_relative_destination_without_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            created = invoke(repository, {"tool": "collab_integration", "action": "create", "task_id": "demo"})
            self.assertFalse(created["is_error"])
            lane_created = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
            )
            self.assertFalse(lane_created["is_error"])
            telemetry_before = (
                repository / ".agent_state/plans/demo/.collab_op/telemetry.jsonl"
            ).read_text(encoding="utf-8")
            expected_events = telemetry_events(repository)

            observed = invoke(
                repository,
                {"tool": "collab_report", "task_id": "demo", "output_dir": "reports"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            report_dir = repository / "reports"
            self.assertTrue((report_dir / "collab-report.json").is_file())
            self.assertTrue((report_dir / "collab-telemetry.jsonl").is_file())
            self.assertEqual(
                (report_dir / "collab-telemetry.jsonl").read_text(encoding="utf-8"),
                telemetry_before,
            )
            report = json.loads((report_dir / "collab-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["task_id"], "demo")
            self.assertEqual(report["timeline"], expected_events)
            self.assertEqual(
                [event["operation"] for event in report["timeline"]],
                ["integration-create", "lane-create"],
            )
            self.assertEqual(
                report["counts"]["operations"],
                {"integration-create": 1, "lane-create": 1},
            )
            self.assertTrue((repository / ".agent_state/worktrees/demo/integration").is_dir())

    def test_report_holds_task_lock_while_capturing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            created = invoke(repository, {"tool": "collab_integration", "action": "create", "task_id": "demo"})
            self.assertFalse(created["is_error"])
            block = base / "release-report"
            blocked = base / "report-blocked"
            wrapper = write_git_wrapper(
                base,
                REPORT_SNAPSHOT_BLOCK_WRAPPER.replace("__BLOCK__", str(block)).replace(
                    "__BLOCKED__", str(blocked)
                ),
            )
            first: subprocess.Popen[str] | None = None
            second: subprocess.Popen[str] | None = None
            try:
                with git_on_path(wrapper.parent):
                    first = spawn_raw_harness(repository)
                    second = spawn_raw_harness(repository)
                    first_stdin = first.stdin
                    first_stdout = first.stdout
                    assert first_stdin is not None and first_stdout is not None
                    first_stdin.write(
                        f"{json.dumps({'tool': 'collab_report', 'task_id': 'demo', 'output_dir': 'reports'})}\n"
                    )
                    first_stdin.flush()
                    self.assertTrue(
                        wait_until(lambda: blocked.exists()),
                        "report never reached its ref snapshot",
                    )

                    refused = send_request(
                        second,
                        {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "concurrent"},
                    )

                    self.assertTrue(refused["is_error"])
                    self.assertEqual(refused["error"]["error"]["code"], "task_busy")
                    self.assertEqual(git(repository, "branch", "--list", "wave/demo/concurrent"), "")
                    block.write_text("go\\n", encoding="utf-8")
                    observed = json.loads(first_stdout.readline())
                    self.assertFalse(observed["is_error"])
                    self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            finally:
                for process in (first, second):
                    if process is not None:
                        close_harness(process)

    def test_report_rejects_legacy_method_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(
                repository,
                {
                    "tool": "collab_report",
                    "task_id": "demo",
                    "output_dir": "reports",
                    "method": "report"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertTrue(observed["error"]["error"]["repair"])

    def test_status_lists_tasks_without_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            for task_id in ("zeta", "alpha"):
                git(repository, "update-ref", f"refs/orchestrate/{task_id}/integration/base", head)

            observed = invoke(repository, {"tool": "collab_status"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"tool_version": 1, "tasks": ["alpha", "zeta"], "warnings": []},
            )

    def test_status_projects_exact_managed_task_result_without_recovery_state(self) -> None:
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
            self.assertNotIn("recovery_required", observed["result"])

    def test_status_rejects_legacy_method_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(repository, {"tool": "collab_status", "method": "status"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertTrue(observed["error"]["error"]["repair"])

    def test_adopt_success_exposes_only_agreed_result_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            base_sha = commit_agent_state_ignore(repository)
            seed_donor(repository, base, base_sha)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                set(observed["result"]),
                {"ok", "tool_version", "source_branch", "integration_branch"},
            )
            self.assertEqual(observed["result"]["source_branch"], "donor")
            self.assertEqual(observed["result"]["integration_branch"], "wave/demo/integration")
            self.assertEqual(
                git(repository, "rev-parse", "wave/demo/integration"),
                git(repository, "rev-parse", "donor"),
            )

    def test_adopt_rejects_legacy_dry_run_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            seed_donor(repository, base, base_sha)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": git(repository, "rev-parse", "HEAD"),
                    "dry_run": True},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertTrue(observed["error"]["error"]["repair"])

    def test_create_performs_git_setup_and_returns_only_common_success_fields(self) -> None:
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

    def test_create_rejects_legacy_method_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration",
                    "action": "create",
                    "task_id": "demo",
                    "method": "integration_create"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertTrue(observed["error"]["error"]["repair"])

    def test_production_loader_registers_discoverable_operation_tools(self) -> None:
        self.test_final_inventory_exposes_only_independent_tools()

    def test_lane_collect_rejects_dirty_lane_with_actionable_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            (Path(expected["lane"]) / "tracked.txt").write_text("dirty\n", encoding="utf-8")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "dirty_worktree")
            self.assertTrue(error["repair"])
            self.assertEqual(
                (Path(expected["lane"]) / "tracked.txt").read_text(encoding="utf-8"),
                "dirty\n",
            )

    def test_lane_collect_reports_conflict_with_conflict_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "tracked.txt").write_text("integration change\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration change")
            (lane / "tracked.txt").write_text("lane change\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane change")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "conflicted")
            self.assertEqual(observed["result"]["conflict_paths"], ["tracked.txt"])
            self.assertEqual(observed["result"]["lane_sha"], git(repository, "rev-parse", "wave/demo/writer-1"))
            self.assertEqual(observed["result"]["integration_sha"], git(repository, "rev-parse", "wave/demo/integration"))
            self.assertTrue(observed["result"]["warnings"])

    def test_lane_collect_reconciles_stale_lane_without_reviewed_sha_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "integration.txt").write_text("advanced\n", encoding="utf-8")
            git(integration, "add", "integration.txt")
            git(integration, "commit", "-m", "integration advances")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                {key for key in observed["result"] if key in ("ok", "tool_version", "state")},
                {"ok", "tool_version", "state"},
            )
            self.assertEqual(observed["result"]["state"], "reconciled")
            self.assertTrue(observed["result"]["warnings"])
            self.assertEqual(
                git(repository, "branch", "--list", "--format=%(refname:short)", "wave/demo/writer-1"),
                "wave/demo/writer-1",
            )
            self.assertTrue(Path(expected["lane"]).exists())
            self.assertNotIn("comparison_moved", observed["result"])
            self.assertFalse(observed["result"]["collected"])

    def test_lane_tools_reject_reviewed_sha_and_abandon_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            requests = (
                ("collab_lane_create", {"task_id": "demo", "lane_id": "writer-1", "sha": "x"}),
                ("collab_lane_reconcile", {"task_id": "demo", "lane_id": "writer-1", "integration_sha": "x"}),
                ("collab_lane_collect", {"task_id": "demo", "lane_id": "writer-1", "sha": "x"}),
                ("collab_lane_drop", {"task_id": "demo", "lane_id": "writer-1", "abandon": True}),
            )

            for tool, request in requests:
                with self.subTest(tool=tool):
                    request["tool"] = tool
                    observed = invoke(repository, request)
                    self.assertTrue(observed["is_error"])
                    self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
                    self.assertTrue(observed["error"]["error"]["repair"])

    def test_lane_drop_reports_partial_cleanup_without_failing_the_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            wrapper = write_git_wrapper(base, FAIL_WORKTREE_REMOVE)
            close_harness_for(repository)
            try:
                with git_on_path(wrapper.parent):
                    observed = invoke(
                        repository,
                        {
                            "tool": "collab_lane_drop",
                            "task_id": "demo",
                            "lane_id": "writer-1"},
                    )
            finally:
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(Path(expected["lane"]).exists())
            self.assertEqual(
                git(repository, "branch", "--list", "wave/demo/writer-1"),
                "+ wave/demo/writer-1",
            )
            self.assertEqual(observed["result"]["disposition"], "abandoned")

    def test_lane_drop_removes_dirty_uncollected_lane_without_abandon_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "tracked.txt").write_text("dirty lane\n", encoding="utf-8")
            (lane / "lane.txt").write_text("uncollected\n", encoding="utf-8")
            git(lane, "add", "lane.txt")
            git(lane, "commit", "-m", "uncollected lane")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_drop",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertFalse(Path(expected["lane"]).exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
            self.assertEqual(observed["result"]["disposition"], "abandoned")

    def test_lane_collect_collects_uncollected_lane_from_current_tips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "lane.txt").write_text("lane work\n", encoding="utf-8")
            git(lane, "add", "lane.txt")
            git(lane, "commit", "-m", "lane work")
            lane_tip = git(lane, "rev-parse", "HEAD")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_tip)
            self.assertEqual(git(repository, "rev-parse", "main"), expected["base"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")

    def test_lane_collect_uses_current_tips_and_removes_collected_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"]["state"],
                "collected",
            )
            self.assertEqual(last_telemetry_event(repository)["state"], "collected")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
            self.assertFalse(Path(expected["lane"]).exists())

    def test_lane_reconcile_projects_noop_state_with_identity_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_reconcile",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "noop")
            self.assertTrue(observed["result"]["warnings"])
            self.assertEqual(observed["result"]["lane_sha"], git(repository, "rev-parse", "wave/demo/writer-1"))
            self.assertEqual(observed["result"]["integration_sha"], git(repository, "rev-parse", "wave/demo/integration"))
            self.assertNotIn("conflict_paths", observed["result"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])

    def test_lane_reconcile_projects_conflicted_state_with_identity_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "tracked.txt").write_text("integration change\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration change")
            (lane / "tracked.txt").write_text("lane change\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane change")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_reconcile",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "conflicted")
            self.assertTrue(observed["result"]["warnings"])
            self.assertEqual(observed["result"]["lane_sha"], git(repository, "rev-parse", "wave/demo/writer-1"))
            self.assertEqual(observed["result"]["integration_sha"], git(repository, "rev-parse", "wave/demo/integration"))
            self.assertEqual(observed["result"]["conflict_paths"], ["tracked.txt"])

    def test_lane_reconcile_projects_state_with_identity_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "integration.txt").write_text("advanced\n", encoding="utf-8")
            git(integration, "add", "integration.txt")
            git(integration, "commit", "-m", "integration advances")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_reconcile",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"]["state"],
                "merged",
            )
            self.assertEqual(observed["result"]["lane_sha"], git(repository, "rev-parse", "wave/demo/writer-1"))
            self.assertEqual(observed["result"]["integration_sha"], git(repository, "rev-parse", "wave/demo/integration"))
            self.assertNotIn("conflict_paths", observed["result"])

    def test_lane_create_preserves_comment_and_projects_common_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": "new-lane",
                    "comment": "  preserve this comment  "},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["ok"])
            self.assertEqual(observed["result"]["tool_version"], 1)
            self.assertEqual(
                git(repository, "rev-parse", "wave/demo/new-lane"),
                expected["integration_head"],
            )
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-create")
            self.assertEqual(event["comment"], "preserve this comment")


if __name__ == "__main__":
    unittest.main()
