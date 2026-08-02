from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tests._orchestrate_cli_support import OrchestrateCliRepositoryTestCase, json_object


class LaneSafetyAndTopologyContractTests(OrchestrateCliRepositoryTestCase):
    """Contract module B through the shipped subprocess and real local Git."""

    task_id = "lane-safety"
    lane_id = "writer"

    def integration_path_for(self, task_id: str | None = None) -> Path:
        return (
            self.root
            / ".agent_state"
            / "worktrees"
            / (task_id or self.task_id)
            / "integration"
        )

    def lane_path_for(
        self, task_id: str | None = None, lane_id: str | None = None
    ) -> Path:
        return (
            self.root
            / ".agent_state"
            / "worktrees"
            / (task_id or self.task_id)
            / "lanes"
            / (lane_id or self.lane_id)
        )

    def telemetry_path_for(self, task_id: str | None = None) -> Path:
        return (
            self.root
            / ".agent_state"
            / "worktrees"
            / (task_id or self.task_id)
            / "telemetry.jsonl"
        )

    def integration_branch(self, task_id: str | None = None) -> str:
        return f"wave/{task_id or self.task_id}/integration"

    def lane_branch(
        self, task_id: str | None = None, lane_id: str | None = None
    ) -> str:
        return f"wave/{task_id or self.task_id}/{lane_id or self.lane_id}"

    def lane_base_ref(
        self, task_id: str | None = None, lane_id: str | None = None
    ) -> str:
        return (
            f"refs/orchestrate/{task_id or self.task_id}/"
            f"{lane_id or self.lane_id}/base"
        )

    def create_task(self, task_id: str | None = None) -> None:
        task = task_id or self.task_id
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "create",
                "--task-id",
                task,
            ),
            "integration-create",
        )

    def create_lane(
        self,
        task_id: str | None = None,
        lane_id: str | None = None,
    ) -> Path:
        task = task_id or self.task_id
        lane = lane_id or self.lane_id
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                task,
                "--lane-id",
                lane,
            ),
            "lane-create",
        )
        return self.lane_path_for(task, lane)

    def lane_command(
        self,
        command: str,
        task_id: str | None = None,
        lane_id: str | None = None,
    ):
        lane = lane_id or self.lane_id
        return self.cli(
            self.nested,
            "lane",
            command,
            "--task-id",
            task_id or self.task_id,
            "--lane-id",
            lane,
        )

    def collect(
        self, task_id: str | None = None, lane_id: str | None = None
    ):
        return self.cli(
            self.nested,
            "integration",
            "collect",
            "--task-id",
            task_id or self.task_id,
            "--lane-id",
            lane_id or self.lane_id,
        )

    def commit_file(
        self,
        cwd: Path,
        path: str,
        content: str | bytes,
        subject: str,
        trailers: tuple[str, ...] = (),
    ) -> str:
        target = cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        self.git(cwd, "add", path)
        message = subject
        if trailers:
            message += "\n\n" + "\n".join(trailers)
        self.git(cwd, "commit", "-q", "-m", message)
        return self.git(cwd, "rev-parse", "HEAD")

    def predicate_failure(
        self,
        result,
        expected_diagnostic_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json_object(result.stdout)
        self.assertEqual(
            set(payload),
            {"ok", "operation", "orchestrate_version", "error", "diagnostics"},
        )
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["operation"], "lane-check")
        self.assertEqual(payload["orchestrate_version"], self.orchestrate_version)
        self.assertEqual(set(payload["error"]), {"code", "message"})
        self.assertEqual(payload["error"]["code"], "lane_not_ready")
        self.assertIsInstance(payload["error"]["message"], str)
        self.assertTrue(payload["error"]["message"])
        diagnostics = payload["diagnostics"]
        self.assertIsInstance(diagnostics, list)
        self.assertGreater(len(diagnostics), 0)
        self.assertLessEqual(len(diagnostics), 20)
        self.assertEqual(
            len(diagnostics),
            len({(item["code"], item["message"]) for item in diagnostics}),
        )
        for diagnostic in diagnostics:
            self.assertEqual(set(diagnostic), {"code", "message"})
            self.assertIsInstance(diagnostic["code"], str)
            self.assertTrue(diagnostic["code"])
            self.assertIsInstance(diagnostic["message"], str)
            self.assertTrue(diagnostic["message"])
            self.assertNotIn(str(self.root), diagnostic["message"])
        if expected_diagnostic_codes is not None:
            self.assertEqual(
                [item["code"] for item in diagnostics], expected_diagnostic_codes
            )
        return payload

    def ref_value(self, ref: str) -> str:
        return self.git(
            self.root, "show-ref", "--hash", ref, check=False
        )

    def merge_head(self, cwd: Path) -> str:
        return self.git(cwd, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)

    def managed_resource_snapshot(self) -> dict[str, object]:
        """Capture authoritative lane resources while allowing observational events."""
        snapshot = self.managed_state_snapshot()
        filesystem = snapshot["filesystem"]
        assert isinstance(filesystem, list)
        snapshot["filesystem"] = [
            item
            for item in filesystem
            if not item[0].endswith("/telemetry.jsonl")
        ]
        return snapshot

    def immutable_trailers(self, cwd: Path, sha: str = "HEAD") -> list[str]:
        raw = self.git(
            cwd,
            "show",
            "-s",
            "--format=%(trailers:key=Immutable,valueonly,unfold)",
            sha,
        )
        return raw.splitlines() if raw else []

    def test_lane_create_requires_task_and_uses_current_integration_tip(self) -> None:
        before = self.managed_state_snapshot()
        self.operational_failure(
            self.lane_command("create"),
            "lane-create",
            "task_not_found",
        )
        self.assertEqual(self.managed_state_snapshot(), before)

        self.create_task()
        integration = self.integration_path_for()
        integration_tip = self.commit_file(
            integration,
            "integration-current.txt",
            "current integration\n",
            "Advance integration before lane creation",
        )
        lane = self.create_lane()

        self.assertEqual(lane, self.lane_path_for())
        self.assertTrue(lane.is_dir())
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), integration_tip)
        self.assertEqual(
            self.git(lane, "symbolic-ref", "--short", "HEAD"),
            self.lane_branch(),
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", self.lane_branch()), integration_tip
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", self.lane_base_ref()), integration_tip
        )

    def test_lane_create_requires_active_valid_integration_not_lookalikes(self) -> None:
        branch_only = "branch-only-task"
        self.git(
            self.root,
            "branch",
            self.integration_branch(branch_only),
            self.base,
        )
        before_branch_only = self.managed_resource_snapshot()
        self.operational_failure(
            self.lane_command("create", branch_only, "writer"),
            "lane-create",
            "task_not_found",
        )
        self.assertEqual(self.managed_resource_snapshot(), before_branch_only)

        base_only = "base-only-task"
        self.git(
            self.root,
            "update-ref",
            f"refs/orchestrate/{base_only}/integration/base",
            self.base,
        )
        before_base_only = self.managed_resource_snapshot()
        self.operational_failure(
            self.lane_command("create", base_only, "writer"),
            "lane-create",
            "task_state_invalid",
        )
        self.assertEqual(self.managed_resource_snapshot(), before_base_only)

    def test_lane_create_refuses_every_exact_and_parent_df_collision_atomically(
        self,
    ) -> None:
        cases = (
            "branch",
            "base-ref",
            "path",
            "branch-df-child",
            "base-ref-df-child",
            "path-parent-file",
        )
        for collision in cases:
            with self.subTest(collision=collision):
                task = f"collision-{collision}"
                lane = "writer"
                self.create_task(task)
                path = self.lane_path_for(task, lane)
                branch = self.lane_branch(task, lane)
                base_ref = self.lane_base_ref(task, lane)
                if collision == "branch":
                    self.git(self.root, "branch", branch, self.base)
                elif collision == "base-ref":
                    self.git(self.root, "update-ref", base_ref, self.base)
                elif collision == "path":
                    path.mkdir(parents=True)
                    (path / "sentinel.bin").write_bytes(b"exact path collision\x00\xff")
                elif collision == "branch-df-child":
                    self.git(self.root, "branch", f"{branch}/child", self.base)
                elif collision == "base-ref-df-child":
                    self.git(self.root, "update-ref", f"{base_ref}/child", self.base)
                else:
                    path.parent.parent.mkdir(parents=True, exist_ok=True)
                    path.parent.write_bytes(b"parent D/F collision\x00\xff")
                before = self.managed_resource_snapshot()

                result = self.lane_command("create", task, lane)

                self.operational_failure(
                    result, "lane-create", "lane_resource_collision"
                )
                self.assertEqual(self.managed_resource_snapshot(), before)

    def test_zero_immutable_declarations_are_ready_and_collectable(self) -> None:
        self.create_task()
        lane = self.create_lane()
        lane_tip = self.commit_file(
            lane,
            "feature.txt",
            "feature\n",
            "Implement without an Immutable declaration",
        )

        self.mutation_success(self.lane_command("check"), "lane-check")
        integration_before = self.git(
            self.root, "rev-parse", self.integration_branch()
        )
        self.mutation_success(self.collect(), "integration-collect")
        collected = self.git(self.root, "rev-parse", self.integration_branch())

        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%P", collected),
            f"{integration_before} {lane_tip}",
        )

    def test_repeatable_normalized_declarations_and_later_redeclaration_are_ready(
        self,
    ) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(
            lane,
            "tests/contract.py",
            "ROUND = 1\n",
            "Declare two protected paths",
            (
                "Immutable: tests/contract.py",
                "Immutable: docs/contract.md",
                "Immutable: tests/contract.py",
            ),
        )
        self.commit_file(
            lane,
            "docs/contract.md",
            "contract\n",
            "Materialize and redeclare second protected path",
            ("Immutable: docs/contract.md",),
        )
        lane_tip = self.commit_file(
            lane,
            "tests/contract.py",
            "ROUND = 2\n",
            "Redeclare a later Contract round",
            ("Immutable: tests/contract.py", "Immutable: docs/contract.md"),
        )

        self.mutation_success(self.lane_command("check"), "lane-check")
        self.mutation_success(self.collect(), "integration-collect")
        collected = self.git(self.root, "rev-parse", self.integration_branch())
        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%P", collected).split()[1],
            lane_tip,
        )

    def test_malformed_declaration_makes_check_and_collect_share_not_ready(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(
            lane,
            "feature.txt",
            "feature\n",
            "Malformed protection",
            ("Immutable: ./feature.txt", "Immutable: ../outside.txt"),
        )
        before_check = self.managed_state_snapshot()

        self.predicate_failure(self.lane_command("check"), ["lane_not_ready"])
        self.assertEqual(self.managed_state_snapshot(), before_check)
        before_collect = self.managed_resource_snapshot()
        self.operational_failure(self.collect(), "integration-collect", "lane_not_ready")
        self.assertEqual(self.managed_resource_snapshot(), before_collect)

    def test_later_undeclared_protected_change_fails_both_shared_validators(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(
            lane,
            "tests/contract.py",
            "FROZEN = True\n",
            "Freeze Contract",
            ("Immutable: tests/contract.py",),
        )
        self.commit_file(
            lane,
            "tests/contract.py",
            "FROZEN = False\n",
            "Change protected path without redeclaring",
        )
        before = self.managed_state_snapshot()

        self.predicate_failure(self.lane_command("check"), ["lane_not_ready"])
        self.assertEqual(self.managed_state_snapshot(), before)
        resources_before_collect = self.managed_resource_snapshot()
        self.operational_failure(self.collect(), "integration-collect", "lane_not_ready")
        self.assertEqual(self.managed_resource_snapshot(), resources_before_collect)

    def test_unicode_protected_change_requires_later_redeclaration(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(
            lane,
            "café.txt",
            "frozen\n",
            "Freeze Unicode Contract path",
            ("Immutable: café.txt",),
        )
        self.commit_file(
            lane,
            "café.txt",
            "changed without redeclaration\n",
            "Change Unicode Contract path",
        )
        before_check = self.managed_state_snapshot()

        self.predicate_failure(self.lane_command("check"), ["lane_not_ready"])
        self.assertEqual(self.managed_state_snapshot(), before_check)
        before_collect = self.managed_resource_snapshot()
        self.operational_failure(self.collect(), "integration-collect", "lane_not_ready")
        self.assertEqual(self.managed_resource_snapshot(), before_collect)

    def test_invalid_first_parent_range_fails_check_and_collect_without_mutation(
        self,
    ) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(lane, "feature.txt", "feature\n", "Lane work")
        unrelated = self.git(
            self.root,
            "commit-tree",
            self.git(self.root, "rev-parse", f"{self.base}^{{tree}}"),
            "-m",
            "unrelated root",
        )
        self.git(self.root, "update-ref", self.lane_base_ref(), unrelated)
        before = self.managed_state_snapshot()

        self.predicate_failure(self.lane_command("check"), ["lane_not_ready"])
        self.assertEqual(self.managed_state_snapshot(), before)
        resources_before_collect = self.managed_resource_snapshot()
        self.operational_failure(self.collect(), "integration-collect", "lane_not_ready")
        self.assertEqual(self.managed_resource_snapshot(), resources_before_collect)

    def test_check_wrong_attachment_is_predicate_false_with_ordered_bounded_diagnostics(
        self,
    ) -> None:
        self.create_task()
        lane = self.create_lane()
        self.git(lane, "switch", "-q", "-c", "operator-branch")
        (lane / "staged.txt").write_text("staged\n", encoding="utf-8")
        self.git(lane, "add", "staged.txt")
        (lane / "untracked.txt").write_bytes(b"untracked\x00\xff")
        self.git(self.root, "update-ref", "-d", self.lane_base_ref())
        before = self.managed_state_snapshot()

        payload = self.predicate_failure(
            self.lane_command("check"),
            ["worktree_identity_mismatch", "dirty_worktree", "lane_not_ready"],
        )

        self.assertEqual(self.managed_state_snapshot(), before)
        self.assertNotIn("paths", payload)
        self.assertNotIn("sha", payload)
        resources_before_collect = self.managed_resource_snapshot()
        self.operational_failure(
            self.collect(),
            "integration-collect",
            "worktree_identity_mismatch",
        )
        self.assertEqual(self.managed_resource_snapshot(), resources_before_collect)

    def test_check_and_collect_share_each_cleanliness_refusal(self) -> None:
        for dirt in ("staged", "unstaged", "untracked", "merge-state"):
            with self.subTest(dirt=dirt):
                task = f"readiness-dirt-{dirt}"
                self.create_task(task)
                lane = self.create_lane(task, "writer")
                if dirt == "staged":
                    (lane / "staged.txt").write_text("staged\n", encoding="utf-8")
                    self.git(lane, "add", "staged.txt")
                elif dirt == "unstaged":
                    (lane / "base.txt").write_text("unstaged\n", encoding="utf-8")
                elif dirt == "untracked":
                    (lane / "untracked.bin").write_bytes(b"untracked\x00\xff")
                else:
                    source_branch = f"readiness-source-{task}"
                    self.git(self.root, "branch", source_branch, self.base)
                    source = self.root / f"readiness-source-{task}"
                    self.git(
                        self.root,
                        "worktree",
                        "add",
                        "-q",
                        str(source),
                        source_branch,
                    )
                    self.commit_file(
                        source, "base.txt", "source\n", "Conflicting source"
                    )
                    self.commit_file(
                        lane, "base.txt", "lane\n", "Conflicting lane"
                    )
                    self.git(
                        lane,
                        "merge",
                        "--no-ff",
                        "--no-commit",
                        source_branch,
                        check=False,
                    )
                    self.assertTrue(self.merge_head(lane))
                before = self.managed_state_snapshot()

                self.predicate_failure(
                    self.lane_command("check", task, "writer"),
                    ["dirty_worktree"],
                )
                self.assertEqual(self.managed_state_snapshot(), before)
                resources_before_collect = self.managed_resource_snapshot()
                self.operational_failure(
                    self.collect(task, "writer"),
                    "integration-collect",
                    "dirty_worktree",
                )
                self.assertEqual(
                    self.managed_resource_snapshot(), resources_before_collect
                )

    def test_sync_current_is_exact_warning_noop_with_one_event_and_no_commit(self) -> None:
        self.create_task()
        lane = self.create_lane()
        head_before = self.git(lane, "rev-parse", "HEAD")
        event_path = self.telemetry_path_for()
        events_before = event_path.read_text(encoding="utf-8").splitlines()

        payload = self.mutation_success(
            self.lane_command("sync"), "lane-sync", warnings=True
        )

        self.assertEqual(payload["warnings"], ["lane already includes latest integration"])
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), head_before)
        self.assertEqual(self.git(lane, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual(self.git(lane, "status", "--porcelain"), "")
        events_after = event_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(events_after), len(events_before) + 1)
        event = json.loads(events_after[-1])
        self.assertEqual(event["operation"], "lane-sync")
        self.assertEqual(event["outcome"], "noop")
        self.assertEqual(event["lane_id"], self.lane_id)

    def test_clean_sync_has_fixed_parents_and_only_redeclares_protected_changes(
        self,
    ) -> None:
        self.create_task()
        lane = self.create_lane()
        lane_tip = self.commit_file(
            lane,
            "lane.txt",
            "lane\n",
            "Protect an existing path",
            ("Immutable: base.txt",),
        )
        integration = self.integration_path_for()
        self.commit_file(
            integration,
            "base.txt",
            "integration changed protected path\n",
            "Change protected path in integration",
        )
        integration_tip = self.commit_file(
            integration,
            "integration.txt",
            "integration-only\n",
            "Change an unprotected path in integration",
        )

        self.mutation_success(self.lane_command("sync"), "lane-sync")
        sync_tip = self.git(lane, "rev-parse", "HEAD")

        self.assertEqual(
            self.git(lane, "show", "-s", "--format=%P", sync_tip),
            f"{lane_tip} {integration_tip}",
        )
        self.assertEqual(
            self.git(lane, "show", "-s", "--format=%s", sync_tip),
            f"Sync integration into lane {self.lane_id}",
        )
        self.assertEqual(self.immutable_trailers(lane, sync_tip), ["base.txt"])
        self.assertEqual(
            self.git(
                lane,
                "show",
                "-s",
                "--format=%(trailers:key=Task,valueonly)",
                sync_tip,
            ),
            self.task_id,
        )
        self.assertEqual(
            self.git(
                lane,
                "show",
                "-s",
                "--format=%(trailers:key=Lane,valueonly)",
                sync_tip,
            ),
            self.lane_id,
        )
        self.assertEqual(self.git(lane, "status", "--porcelain"), "")
        self.assertEqual(
            self.git(
                lane,
                "rev-list",
                "--first-parent",
                "--count",
                f"{lane_tip}..HEAD",
            ),
            "1",
        )

    def test_sync_refuses_each_dirt_class_and_existing_merge_before_mutation(self) -> None:
        for dirt in ("staged", "unstaged", "untracked", "merge-state"):
            with self.subTest(dirt=dirt):
                task = f"sync-dirt-{dirt}"
                self.create_task(task)
                lane = self.create_lane(task, "writer")
                if dirt == "staged":
                    (lane / "staged.txt").write_text("staged\n", encoding="utf-8")
                    self.git(lane, "add", "staged.txt")
                elif dirt == "unstaged":
                    (lane / "base.txt").write_text("unstaged\n", encoding="utf-8")
                elif dirt == "untracked":
                    (lane / "untracked.bin").write_bytes(b"untracked\x00\xff")
                else:
                    other = f"merge-source-{task}"
                    self.git(self.root, "branch", other, self.base)
                    source = self.root / f"source-{task}"
                    self.git(
                        self.root,
                        "worktree",
                        "add",
                        "-q",
                        str(source),
                        other,
                    )
                    self.commit_file(
                        source, "base.txt", "source\n", "Conflicting source"
                    )
                    self.commit_file(lane, "base.txt", "lane\n", "Conflicting lane")
                    self.git(
                        lane,
                        "merge",
                        "--no-ff",
                        "--no-commit",
                        other,
                        check=False,
                    )
                    self.assertTrue(self.merge_head(lane))
                before = self.managed_resource_snapshot()

                self.operational_failure(
                    self.lane_command("sync", task, "writer"),
                    "lane-sync",
                    "dirty_worktree",
                )
                self.assertEqual(self.managed_resource_snapshot(), before)

    def test_sync_conflict_leaves_exact_writer_owned_lane_state(self) -> None:
        self.create_task()
        lane = self.create_lane()
        lane_tip = self.commit_file(
            lane, "base.txt", "lane\n", "Lane side of conflict"
        )
        integration = self.integration_path_for()
        integration_tip = self.commit_file(
            integration,
            "base.txt",
            "integration\n",
            "Integration side of conflict",
        )
        base_blob = self.git(self.root, "rev-parse", f"{self.base}:base.txt")
        lane_blob = self.git(self.root, "rev-parse", f"{lane_tip}:base.txt")
        integration_blob = self.git(
            self.root, "rev-parse", f"{integration_tip}:base.txt"
        )

        self.operational_failure(
            self.lane_command("sync"), "lane-sync", "merge_conflict"
        )

        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), lane_tip)
        self.assertEqual(self.git(self.root, "rev-parse", self.lane_branch()), lane_tip)
        self.assertEqual(self.merge_head(lane), integration_tip)
        self.assertEqual(self.git(lane, "status", "--porcelain"), "UU base.txt")
        entries = self.git(lane, "ls-files", "-s", "base.txt").splitlines()
        self.assertEqual(
            [(entry.split()[1], entry.split()[2]) for entry in entries],
            [(base_blob, "1"), (lane_blob, "2"), (integration_blob, "3")],
        )
        expected = (
            f"<<<<<<< HEAD\nlane\n=======\nintegration\n>>>>>>> {integration_tip}\n"
        ).encode()
        self.assertEqual((lane / "base.txt").read_bytes(), expected)

    def assert_collect_topology(self, *, stale: bool) -> None:
        self.create_task()
        lane = self.create_lane()
        lane_tip = self.commit_file(
            lane, "lane.txt", "lane\n", "Lane-owned change"
        )
        integration_before = self.git(
            self.root, "rev-parse", self.integration_branch()
        )
        if stale:
            integration_before = self.commit_file(
                self.integration_path_for(),
                "integration.txt",
                "integration\n",
                "Concurrent non-conflicting integration change",
            )
        integration_count = int(
            self.git(
                self.root,
                "rev-list",
                "--first-parent",
                "--count",
                self.integration_branch(),
            )
        )
        lane_tree = self.git(self.root, "rev-parse", f"{lane_tip}^{{tree}}")

        self.mutation_success(self.collect(), "integration-collect")
        collected = self.git(self.root, "rev-parse", self.integration_branch())

        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%P", collected),
            f"{integration_before} {lane_tip}",
        )
        self.assertEqual(
            int(
                self.git(
                    self.root,
                    "rev-list",
                    "--first-parent",
                    "--count",
                    self.integration_branch(),
                )
            ),
            integration_count + 1,
        )
        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%s", collected),
            f"Collect lane {self.lane_id}",
        )
        self.assertEqual(
            self.git(
                self.root,
                "show",
                "-s",
                "--format=%(trailers:key=Task,valueonly)",
                collected,
            ),
            self.task_id,
        )
        self.assertEqual(
            self.git(
                self.root,
                "show",
                "-s",
                "--format=%(trailers:key=Lane,valueonly)",
                collected,
            ),
            self.lane_id,
        )
        if not stale:
            self.assertEqual(
                self.git(self.root, "rev-parse", f"{collected}^{{tree}}"), lane_tree
            )
        else:
            self.assertEqual(
                (self.integration_path_for() / "lane.txt").read_bytes(), b"lane\n"
            )
            self.assertEqual(
                (self.integration_path_for() / "integration.txt").read_bytes(),
                b"integration\n",
            )
        self.assertFalse(self.lane_path_for().exists())
        self.assertEqual(
            self.ref_value(f"refs/heads/{self.lane_branch()}"), ""
        )
        self.assertEqual(self.ref_value(self.lane_base_ref()), "")
        worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        self.assertNotIn(str(self.lane_path_for()), worktrees)

    def test_current_collect_is_one_fixed_parent_no_ff_commit_and_cleans_lane(self) -> None:
        self.assert_collect_topology(stale=False)

    def test_stale_clean_collect_merges_directly_without_rewriting_lane(self) -> None:
        self.assert_collect_topology(stale=True)

    def test_collect_conflict_aborts_shared_integration_exactly(self) -> None:
        self.create_task()
        lane = self.create_lane()
        lane_tip = self.commit_file(
            lane, "base.txt", "lane\n", "Lane side of collect conflict"
        )
        integration = self.integration_path_for()
        integration_tip = self.commit_file(
            integration,
            "base.txt",
            "integration\n",
            "Integration side of collect conflict",
        )
        before = {
            "head": self.git(integration, "rev-parse", "HEAD"),
            "tree": self.git(integration, "rev-parse", "HEAD^{tree}"),
            "index": self.git(integration, "ls-files", "-s"),
            "status": self.git(integration, "status", "--porcelain=v1"),
            "base-bytes": (integration / "base.txt").read_bytes(),
            "merge-head": self.merge_head(integration),
        }

        self.operational_failure(
            self.collect(), "integration-collect", "merge_conflict"
        )

        after = {
            "head": self.git(integration, "rev-parse", "HEAD"),
            "tree": self.git(integration, "rev-parse", "HEAD^{tree}"),
            "index": self.git(integration, "ls-files", "-s"),
            "status": self.git(integration, "status", "--porcelain=v1"),
            "base-bytes": (integration / "base.txt").read_bytes(),
            "merge-head": self.merge_head(integration),
        }
        self.assertEqual(after, before)
        self.assertEqual(before["head"], integration_tip)
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), lane_tip)
        self.assertTrue(lane.is_dir())
        self.assertEqual(self.ref_value(self.lane_base_ref()), self.base)

    def test_drop_force_removes_dirty_exact_inventory(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(lane, "lane.txt", "committed\n", "Lane commit")
        (lane / "base.txt").write_text("unstaged dirt\n", encoding="utf-8")
        sentinel = lane / "untracked.bin"
        sentinel.write_bytes(b"discard authority\x00\xff")
        unrelated = self.git(self.root, "rev-parse", "main")

        self.mutation_success(self.lane_command("drop"), "lane-drop")

        self.assertFalse(lane.exists())
        self.assertEqual(self.ref_value(f"refs/heads/{self.lane_branch()}"), "")
        self.assertEqual(self.ref_value(self.lane_base_ref()), "")
        self.assertEqual(self.git(self.root, "rev-parse", "main"), unrelated)

    def test_drop_repairs_each_partial_inventory_and_refuses_all_absent(self) -> None:
        for member in ("path", "branch", "base-ref"):
            with self.subTest(member=member):
                task = f"partial-{member}"
                lane_id = "writer"
                self.create_task(task)
                path = self.lane_path_for(task, lane_id)
                branch = self.lane_branch(task, lane_id)
                base_ref = self.lane_base_ref(task, lane_id)
                if member == "path":
                    path.mkdir(parents=True)
                    (path / "dirty.bin").write_bytes(b"partial path\x00\xff")
                elif member == "branch":
                    self.git(self.root, "branch", branch, self.base)
                else:
                    self.git(self.root, "update-ref", base_ref, self.base)

                self.mutation_success(
                    self.lane_command("drop", task, lane_id),
                    "lane-drop",
                    warnings=True,
                )
                self.assertFalse(path.exists())
                self.assertEqual(self.ref_value(f"refs/heads/{branch}"), "")
                self.assertEqual(self.ref_value(base_ref), "")

        before = self.managed_resource_snapshot()
        self.operational_failure(
            self.lane_command("drop", "partial-path", "absent"),
            "lane-drop",
            "lane_not_found",
        )
        self.assertEqual(self.managed_resource_snapshot(), before)

    def test_drop_unlinks_symlink_without_removing_aliased_worktree(self) -> None:
        self.create_task()
        lane = self.create_lane()
        unrelated_branch = "operator-preserve-symlink"
        unrelated = self.root / "operator-worktree"
        self.git(self.root, "branch", unrelated_branch, self.base)
        self.git(
            self.root,
            "worktree",
            "add",
            "-q",
            str(unrelated),
            unrelated_branch,
        )
        unrelated_tip = self.git(unrelated, "rev-parse", "HEAD")
        sentinel = unrelated / "operator-untracked.bin"
        sentinel_bytes = b"operator-owned dirt\x00\xff"
        sentinel.write_bytes(sentinel_bytes)

        self.git(self.root, "worktree", "remove", "--force", str(lane))
        lane.symlink_to(unrelated, target_is_directory=True)
        registrations_before = self.git(
            self.root, "worktree", "list", "--porcelain"
        )

        result = self.lane_command("drop")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json_object(result.stdout)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["operation"], "lane-drop")
        self.assertEqual(payload["orchestrate_version"], self.orchestrate_version)

        self.assertTrue(unrelated.is_dir())
        self.assertEqual(
            self.git(self.root, "worktree", "list", "--porcelain"),
            registrations_before,
        )
        self.assertEqual(
            self.ref_value(f"refs/heads/{unrelated_branch}"), unrelated_tip
        )
        self.assertEqual(sentinel.read_bytes(), sentinel_bytes)
        self.assertFalse(os.path.lexists(lane))
        self.assertEqual(self.ref_value(f"refs/heads/{self.lane_branch()}"), "")
        self.assertEqual(self.ref_value(self.lane_base_ref()), "")

    def test_drop_removes_managed_path_but_never_deletes_different_branch(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(lane, "lane.txt", "derived\n", "Derived branch commit")
        other_branch = "operator-preserve"
        self.git(lane, "switch", "-q", "-c", other_branch)
        other_tip = self.commit_file(
            lane,
            "operator.bin",
            b"operator branch bytes\n",
            "Operator-owned commit",
        )
        operator_blob = self.git(
            self.root, "rev-parse", f"{other_tip}:operator.bin"
        )

        self.mutation_success(self.lane_command("drop"), "lane-drop")

        self.assertFalse(lane.exists())
        self.assertEqual(self.ref_value(f"refs/heads/{self.lane_branch()}"), "")
        self.assertEqual(self.ref_value(self.lane_base_ref()), "")
        self.assertEqual(
            self.ref_value(f"refs/heads/{other_branch}"), other_tip
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", f"{other_branch}:operator.bin"),
            operator_blob,
        )

    def prepare_external_history(self, *, effective_change: bool) -> Path:
        self.create_task()
        lane = self.create_lane()
        declared = self.commit_file(
            lane,
            "declaration.txt",
            "declared\n",
            "Protect base path",
            ("Immutable: base.txt",),
        )
        external_branch = "external-history"
        self.git(self.root, "branch", external_branch, declared)
        external = self.root / "external-worktree"
        self.git(
            self.root,
            "worktree",
            "add",
            "-q",
            str(external),
            external_branch,
        )
        self.commit_file(
            external,
            "base.txt",
            "external history\n",
            "External second-parent change",
        )
        self.commit_file(lane, "lane.txt", "lane\n", "Advance lane first parent")
        self.git(
            lane,
            "merge",
            "--no-ff",
            "--no-commit",
            external_branch,
        )
        if not effective_change:
            self.git(lane, "checkout", "HEAD", "--", "base.txt")
            self.git(lane, "add", "base.txt")
        self.git(lane, "commit", "-q", "-m", "Merge external history")
        return lane

    def test_first_parent_validation_ignores_second_parent_only_protected_change(
        self,
    ) -> None:
        lane = self.prepare_external_history(effective_change=False)
        merge_tip = self.git(lane, "rev-parse", "HEAD")
        parents = self.git(lane, "show", "-s", "--format=%P", merge_tip).split()
        self.assertEqual(len(parents), 2)
        self.assertNotEqual(
            self.git(self.root, "rev-parse", f"{parents[1]}:base.txt"),
            self.git(self.root, "rev-parse", f"{parents[0]}:base.txt"),
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", f"{merge_tip}:base.txt"),
            self.git(self.root, "rev-parse", f"{parents[0]}:base.txt"),
        )
        self.assertEqual(self.immutable_trailers(lane, merge_tip), [])

        self.mutation_success(self.lane_command("check"), "lane-check")
        self.mutation_success(self.collect(), "integration-collect")

    def test_first_parent_validation_checks_effective_merge_commit_change(self) -> None:
        lane = self.prepare_external_history(effective_change=True)
        merge_tip = self.git(lane, "rev-parse", "HEAD")
        first_parent = self.git(
            lane, "show", "-s", "--format=%P", merge_tip
        ).split()[0]
        self.assertNotEqual(
            self.git(self.root, "rev-parse", f"{merge_tip}:base.txt"),
            self.git(self.root, "rev-parse", f"{first_parent}:base.txt"),
        )
        self.assertEqual(self.immutable_trailers(lane, merge_tip), [])
        before = self.managed_state_snapshot()

        self.predicate_failure(self.lane_command("check"), ["lane_not_ready"])
        self.assertEqual(self.managed_state_snapshot(), before)
        resources_before_collect = self.managed_resource_snapshot()
        self.operational_failure(self.collect(), "integration-collect", "lane_not_ready")
        self.assertEqual(self.managed_resource_snapshot(), resources_before_collect)


if __name__ == "__main__":
    import unittest

    unittest.main()
