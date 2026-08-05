from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from tests._orchestrate_cli_support import OrchestrateCliRepositoryTestCase, json_object


class LaneSafetyAndTopologyContractTests(OrchestrateCliRepositoryTestCase):
    """Contract module B through the shipped subprocess and real local Git."""

    task_id = "lane-safety"
    lane_id = "writer"

    def setUp(self) -> None:
        super().setUp()
        # Commit messages live outside every managed worktree, so authoring one
        # never shows up as the dirt a cleanliness assertion is measuring.
        messages = tempfile.TemporaryDirectory(prefix="orchestrate-messages-")
        self.addCleanup(messages.cleanup)
        self.messages = Path(messages.name)

    def message_file(self, text: str) -> str:
        path = self.messages / f"message-{len(os.listdir(self.messages))}.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

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
        *extra: str,
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
            *extra,
        )

    def lane_commit(
        self,
        message: str,
        *flags: str,
        task_id: str | None = None,
        lane_id: str | None = None,
    ):
        return self.lane_command(
            "commit",
            task_id,
            lane_id,
            "--message-file",
            self.message_file(message),
            *flags,
        )

    def mode_mismatch(self, result) -> dict[str, Any]:
        """A declared mode the lane's Git shape contradicts is a negative predicate."""
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json_object(result.stdout)
        self.assertEqual(
            set(payload), {"ok", "operation", "orchestrate_version", "error"}
        )
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["operation"], "lane-check")
        self.assertEqual(payload["error"]["code"], "validation_mode_mismatch")
        self.assertTrue(payload["error"]["message"])
        return payload

    def collect(
        self,
        task_id: str | None = None,
        lane_id: str | None = None,
        ticket: str | None = "contract-ticket",
    ):
        argv = [
            "integration",
            "collect",
            "--task-id",
            task_id or self.task_id,
            "--lane-id",
            lane_id or self.lane_id,
        ]
        if ticket is not None:
            argv.extend(("--ticket", ticket))
        return self.cli(self.nested, *argv)

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
        """Read Immutable declarations with v150's per-paragraph unfolding."""
        raw = self.git(cwd, "show", "-s", "--format=%B", sha)
        values: list[str] = []
        for paragraph in re.split(r"\n(?:[ \t]*\n)+", raw):
            pending: str | None = None
            for line in paragraph.splitlines():
                if pending is not None and line[:1].isspace():
                    pending = f"{pending} {line.strip()}".strip()
                    continue
                if pending is not None:
                    values.append(pending)
                pending = None
                if line[:1].isspace():
                    continue
                key, separator, value = line.partition(":")
                if separator and key.strip().casefold() == "immutable":
                    pending = value.strip()
            if pending is not None:
                values.append(pending)
        return values

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

        self.lane_check_success(self.lane_command("check"))
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

        self.lane_check_success(self.lane_command("check"))
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

    def test_immutable_declarations_preserve_paragraph_tolerance_and_unfolding(
        self,
    ) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(
            lane, "tests/contract.py", "ROUND = 0\n", "Freeze Contract",
            ("Immutable: tests/contract.py",),
        )
        (lane / "tests" / "contract.py").write_text("ROUND = 1\n", encoding="utf-8")
        (lane / "docs").mkdir()
        (lane / "docs" / "contract.md").write_text("contract\n", encoding="utf-8")
        self.git(lane, "add", "tests/contract.py", "docs/contract.md")
        self.git(
            lane, "commit", "-q", "-m", "Redeclare from an earlier paragraph",
            "-m", "Immutable: tests/contract.py", "-m", "Narrative paragraph",
            "-m", "Immutable: docs/contract.md",
        )

        for round_, declaration in enumerate(
            ("immutable: tests/contract.py", "IMMUTABLE: tests/contract.py", "Immutable:tests/contract.py"),
            start=2,
        ):
            self.commit_file(
                lane, "tests/contract.py", f"ROUND = {round_}\n",
                "Redeclare with v150 key tolerance", (declaration,),
            )

        self.commit_file(
            lane, "src/a continuation", "ROUND = 0\n", "Freeze unfolded path",
            ("Immutable: src/a continuation",),
        )
        (lane / "src" / "a continuation").write_text("ROUND = 1\n", encoding="utf-8")
        (lane / "docs" / "unfolded.md").write_text("unfolded\n", encoding="utf-8")
        self.git(lane, "add", "src/a continuation", "docs/unfolded.md")
        self.git(
            lane, "commit", "-q", "-m", "Redeclare with Git continuation unfolding",
            "-m", "Immutable: src/a\n continuation", "-m", "Narrative paragraph",
            "-m", "Immutable: docs/unfolded.md",
        )
        lane_tip = self.git(lane, "rev-parse", "HEAD")
        self.assertEqual(self.immutable_trailers(lane, lane_tip), [
            "src/a continuation", "docs/unfolded.md",
        ])
        self.lane_check_success(self.lane_command("check"))
        self.mutation_success(self.collect(), "integration-collect")
        collected = self.git(self.root, "rev-parse", self.integration_branch())
        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%P", collected).split()[1],
            lane_tip,
        )

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

    def test_clean_sync_stages_the_merge_and_leaves_the_tip_to_the_writer(
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

        self.mutation_success(self.lane_command("sync"), "lane-sync", warnings=True)

        # Git resolved the merge, so it is staged and MERGE_HEAD is pending; the
        # lane tip stays where the writer left it until the writer signs.
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), lane_tip)
        self.assertEqual(self.merge_head(lane), integration_tip)
        self.assertNotEqual(self.git(lane, "status", "--porcelain"), "")
        # A staged merge is dirt, so the lane cannot pass check until it lands.
        self.predicate_failure(self.lane_command("check"), ["dirty_worktree"])

        payload = self.success(
            self.lane_commit(
                f"Sync integration into lane {self.lane_id}\n", "--amend-frozen"
            )
        )
        sync_tip = self.git(lane, "rev-parse", "HEAD")

        self.assertEqual(payload["sha"], sync_tip)
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
        self.lane_check_success(self.lane_command("check"))

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

        # A conflict is the handoff working, not the command failing: the merge
        # ran as asked, so the envelope is ok and the warning names the paths.
        payload = self.mutation_success(
            self.lane_command("sync"), "lane-sync", warnings=True
        )
        self.assertEqual(
            payload["warnings"],
            ["integration sync left conflicts to resolve before committing: base.txt"],
        )
        event = json.loads(
            self.telemetry_path_for().read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertEqual(event["operation"], "lane-sync")
        self.assertEqual(event["outcome"], "conflict")

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

    def freeze_oracle(self, lane: Path, path: str = "tests/contract.py") -> str:
        """Freeze one oracle path the way the instrument now does it."""
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("oracle\n", encoding="utf-8")
        self.git(lane, "add", path)
        self.success(self.lane_commit("Freeze the Contract\n", "--contract"))
        return self.git(lane, "rev-parse", "HEAD")

    def test_contract_declares_every_staged_path_and_marks_its_origin(self) -> None:
        self.create_task()
        lane = self.create_lane()
        oracle = "tests/test_c40_plot_publication_authority.py"
        (lane / "tests").mkdir()
        (lane / oracle).write_text("oracle\n", encoding="utf-8")
        (lane / "docs.md").write_text("doc\n", encoding="utf-8")
        self.git(lane, "add", oracle, "docs.md")

        payload = self.success(self.lane_commit("Freeze the Contract\n", "--contract"))

        self.assertEqual(payload["immutable"], ["docs.md", oracle])
        self.assertEqual(payload["sha"], self.git(lane, "rev-parse", "HEAD"))
        self.assertEqual(self.immutable_trailers(lane), ["docs.md", oracle])
        self.assertEqual(
            self.git(lane, "show", "-s", "--format=%(trailers:key=Origin,valueonly)"),
            "contract",
        )
        self.assertEqual(
            self.git(lane, "show", "-s", "--format=%s"), "Freeze the Contract"
        )
        self.assertEqual(self.git(lane, "status", "--porcelain"), "")

    def test_amend_frozen_declares_the_intersection_and_no_contract_origin(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.freeze_oracle(lane)
        (lane / "tests/contract.py").write_text("corrected oracle\n", encoding="utf-8")
        (lane / "src.py").write_text("implementation\n", encoding="utf-8")
        self.git(lane, "add", "tests/contract.py", "src.py")

        payload = self.success(
            self.lane_commit("Correct the oracle\n", "--amend-frozen")
        )

        # Declaring only the intersection keeps src.py free: a path declared once
        # owes a redeclaration every later time it is touched.
        self.assertEqual(payload["immutable"], ["tests/contract.py"])
        self.assertEqual(self.immutable_trailers(lane), ["tests/contract.py"])
        self.assertEqual(
            self.git(lane, "show", "-s", "--format=%(trailers:key=Origin,valueonly)"),
            "",
        )
        self.lane_check_success(self.lane_command("check"))

    def test_unflagged_commit_declares_nothing_when_no_frozen_path_is_staged(
        self,
    ) -> None:
        self.create_task()
        lane = self.create_lane()
        self.freeze_oracle(lane)
        (lane / "src.py").write_text("implementation\n", encoding="utf-8")
        self.git(lane, "add", "src.py")

        payload = self.success(self.lane_commit("Implement the slice\n"))

        self.assertEqual(payload["immutable"], [])
        self.assertEqual(self.immutable_trailers(lane), [])
        self.assertEqual(
            self.git(lane, "show", "-s", "--format=%(trailers:key=Origin,valueonly)"),
            "",
        )
        self.lane_check_success(self.lane_command("check"))

    def test_unflagged_commit_names_the_frozen_paths_and_changes_nothing(self) -> None:
        self.create_task()
        lane = self.create_lane()
        frozen_tip = self.freeze_oracle(lane)
        (lane / "tests/contract.py").write_text("quietly changed\n", encoding="utf-8")
        (lane / "src.py").write_text("implementation\n", encoding="utf-8")
        self.git(lane, "add", "tests/contract.py", "src.py")
        before = self.managed_resource_snapshot()

        payload = self.operational_failure(
            self.lane_commit("Implement the slice\n"),
            "lane-commit",
            "frozen_path_undeclared",
        )

        # The refusal is what keeps Immutable: meaningful: an intent this
        # explicit is never supplied on the author's behalf.
        self.assertIn("tests/contract.py", payload["error"]["message"])
        self.assertIn("--amend-frozen", payload["error"]["message"])
        self.assertNotIn("src.py", payload["error"]["message"])
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), frozen_tip)
        self.assertEqual(self.managed_resource_snapshot(), before)

    def test_the_two_declaration_modes_are_mutually_exclusive(self) -> None:
        self.create_task()
        lane = self.create_lane()
        (lane / "src.py").write_text("implementation\n", encoding="utf-8")
        self.git(lane, "add", "src.py")

        self.operational_failure(
            self.lane_commit("Both modes\n", "--contract", "--amend-frozen"),
            "cli",
            "cli_usage",
        )
        self.assertEqual(self.git(lane, "rev-list", "--count", "HEAD"), "1")

    def test_commit_refuses_an_unusable_message_wrong_identity_and_empty_index(
        self,
    ) -> None:
        self.create_task()
        lane = self.create_lane()
        head = self.git(lane, "rev-parse", "HEAD")

        self.operational_failure(
            self.lane_commit("Nothing staged\n"), "lane-commit", "nothing_staged"
        )
        (lane / "src.py").write_text("implementation\n", encoding="utf-8")
        self.git(lane, "add", "src.py")
        self.operational_failure(
            self.lane_commit("   \n\n"), "lane-commit", "message_file_invalid"
        )
        self.operational_failure(
            self.lane_command(
                "commit",
                None,
                None,
                "--message-file",
                str(self.messages / "absent.txt"),
            ),
            "lane-commit",
            "message_file_invalid",
        )
        self.git(lane, "switch", "-q", "-c", "operator-branch")
        self.operational_failure(
            self.lane_commit("Wrong identity\n"),
            "lane-commit",
            "worktree_identity_mismatch",
        )
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), head)

    def test_a_declared_path_carrying_whitespace_survives_the_round_trip(self) -> None:
        self.create_task()
        lane = self.create_lane()
        spaced = "tests/contract cases.py"
        (lane / "tests").mkdir()
        (lane / spaced).write_text("oracle\n", encoding="utf-8")
        self.git(lane, "add", spaced)
        self.success(self.lane_commit("Freeze a spaced path\n", "--contract"))

        (lane / spaced).write_text("corrected oracle\n", encoding="utf-8")
        self.git(lane, "add", spaced)
        payload = self.success(
            self.lane_commit("Correct the spaced path\n", "--amend-frozen")
        )

        self.assertEqual(payload["immutable"], [spaced])
        self.assertEqual(self.immutable_trailers(lane), [spaced])
        self.assertEqual(
            self.lane_check_success(self.lane_command("check"))["protected_paths"],
            [spaced],
        )

    def test_a_computed_amendment_stays_collectable_where_a_typed_one_died(
        self,
    ) -> None:
        # The regression this instrument exists for: the amendment's declaration
        # is the same string Git reports changed, so the collect predicate can
        # never see an undeclared protected path.
        self.create_task()
        lane = self.create_lane()
        oracle = "tests/test_c40_plot_publication_authority.py"
        self.freeze_oracle(lane, oracle)
        (lane / oracle).write_text("corrected oracle\n", encoding="utf-8")
        self.git(lane, "add", oracle)
        self.success(self.lane_commit("Correct the oracle\n", "--amend-frozen"))
        (lane / "src.py").write_text("implementation\n", encoding="utf-8")
        self.git(lane, "add", "src.py")
        self.success(self.lane_commit("Implement against the oracle\n"))

        payload = self.lane_check_success(self.lane_command("check"))

        self.assertEqual(payload["protected_paths"], [oracle])
        self.assertEqual(len(payload["ticket_contract_commits"]), 1)
        self.mutation_success(self.collect(), "integration-collect")

    def test_every_lane_commit_is_a_readable_ledger_entry(self) -> None:
        # The instrument v163 made mandatory writes one event per commit, so a
        # ledger that cannot read them turns adoption into report noise.
        self.create_task()
        lane = self.create_lane()
        self.freeze_oracle(lane)
        (lane / "src.py").write_text("implementation\n", encoding="utf-8")
        self.git(lane, "add", "src.py")
        self.success(self.lane_commit("Implement the slice\n"))
        output = self.root / "ledger-report"
        output.mkdir()

        self.success(
            self.cli(
                self.nested,
                "report",
                "--task-id",
                self.task_id,
                "--output-dir",
                str(output),
            )
        )

        report = json.loads(
            (output / "orchestrate-report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["counts"]["invalid_telemetry_lines"], 0)
        for warning in report["warnings"]:
            self.assertNotIn("invalid telemetry", warning)
        raw = (output / "orchestrate-telemetry.jsonl").read_text(encoding="utf-8")
        operations = [json.loads(line)["operation"] for line in raw.splitlines()]
        self.assertEqual(operations.count("lane-commit"), 2)

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

        ticket = "topology-ticket"
        self.mutation_success(
            self.collect(ticket=ticket), "integration-collect"
        )
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
        self.assertEqual(
            self.git(
                self.root,
                "show",
                "-s",
                "--format=%(trailers:key=Ticket,valueonly)",
                collected,
            ),
            ticket,
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
        self.assertTrue(self.lane_path_for().is_dir())
        self.assertEqual(
            self.ref_value(f"refs/heads/{self.lane_branch()}"), lane_tip
        )
        self.assertEqual(self.ref_value(self.lane_base_ref()), self.base)
        worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        self.assertIn(str(self.lane_path_for()), worktrees)
        self.assertIn(
            f"branch refs/heads/{self.lane_branch()}",
            worktrees,
        )

    def test_collect_requires_ticket_before_mutating_lane_resources(self) -> None:
        self.create_task()
        lane = self.create_lane()
        lane_tip = self.commit_file(
            lane, "lane.txt", "lane\n", "Lane-owned change"
        )
        before = self.managed_resource_snapshot()

        self.operational_failure(self.collect(ticket=None), "cli", "cli_usage")

        self.assertEqual(self.managed_resource_snapshot(), before)
        self.assertEqual(self.ref_value(self.lane_base_ref()), self.base)
        self.assertEqual(
            self.ref_value(f"refs/heads/{self.lane_branch()}"), lane_tip
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", self.integration_branch()), self.base
        )

    def test_collect_rejects_an_unbounded_ticket_without_mutation(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(lane, "lane.txt", "lane\n", "Lane-owned change")
        before = self.managed_resource_snapshot()

        self.operational_failure(
            self.collect(ticket="Ticket/with/slash"),
            "integration-collect",
            "invalid_identifier",
        )

        self.assertEqual(self.managed_resource_snapshot(), before)

    def test_collect_is_non_destructive_and_keeps_trailers(self) -> None:
        self.assert_collect_topology(stale=False)

    def test_stale_clean_collect_keeps_lane_and_merges_without_rewriting_lane(self) -> None:
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

    def test_dropped_lane_span_is_reported_apart_from_collected_time(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(lane, "lane.txt", "committed\n", "Lane commit")

        self.mutation_success(self.lane_command("drop"), "lane-drop")

        output_dir = self.root / "drop-report"
        self.success(
            self.cli(
                self.root, "report", "--task-id", self.task_id, "--output-dir", str(output_dir)
            )
        )
        report = json_object(
            (output_dir / "orchestrate-report.json").read_text(encoding="utf-8")
        )
        spans = [
            entry
            for entry in report["timeline"]
            if entry.get("kind") == "lane" and entry.get("identity") == self.lane_id
        ]
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["disposition"], "dropped")
        durations = report["lane_durations"]
        self.assertEqual(durations["dropped"]["lanes"], 1.0)
        # The drop must not land in the collected bucket, which is the number a reader takes for
        # how long real lane work costs.
        self.assertEqual(durations["collected"]["lanes"], 0.0)
        self.assertEqual(durations["collected"]["elapsed_seconds"], 0.0)

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

    def test_lane_check_reminds_about_a_present_gate_script_without_refusing(
        self,
    ) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(lane, "feature.txt", "feature\n", "Implement the feature")

        quiet = self.lane_check_success(self.lane_command("check"))
        self.assertNotIn("warnings", quiet)

        gate = (
            self.root / ".agent_state" / "orchestrate" / self.task_id / "gate.sh"
        )
        gate.parent.mkdir(parents=True, exist_ok=True)
        gate.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        reminded = self.lane_check_success(self.lane_command("check"))
        self.assertEqual(len(reminded["warnings"]), 1)
        self.assertIn("gate.sh", reminded["warnings"][0])
        self.assertIn("S2.5", reminded["warnings"][0])

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

        self.lane_check_success(self.lane_command("check"))
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


    def freeze_contract(self, lane: Path, path: str, content: str) -> str:
        return self.commit_file(
            lane,
            path,
            content,
            "Freeze the Contract",
            ("Origin: contract", f"Immutable: {path}"),
        )

    def test_declared_tdd_refuses_a_lane_that_froze_no_contract(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.commit_file(lane, "feature.txt", "feature\n", "Implement directly")

        # The lane is collectable; only the declared mode contradicts it.
        self.lane_check_success(self.lane_command("check"))
        self.mode_mismatch(
            self.lane_command("check", None, None, "--expect-mode", "tdd")
        )

    def test_declared_tdd_accepts_a_frozen_contract_and_direct_refuses_it(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.freeze_contract(lane, "tests/contract.py", "ROUND = 1\n")

        payload = self.lane_check_success(
            self.lane_command("check", None, None, "--expect-mode", "tdd")
        )
        self.assertEqual(len(payload["ticket_contract_commits"]), 1)
        self.mode_mismatch(
            self.lane_command("check", None, None, "--expect-mode", "direct")
        )

    def test_declared_direct_ignores_a_predecessor_ticket_already_collected(
        self,
    ) -> None:
        """A persistent lane keeps its base, so its range outlives one ticket."""
        self.create_task()
        lane = self.create_lane()
        self.freeze_contract(lane, "tests/contract.py", "ROUND = 1\n")
        self.commit_file(lane, "feature.txt", "feature\n", "Implement the Contract")
        self.mutation_success(self.collect(), "integration-collect")

        self.commit_file(lane, "second.txt", "second\n", "Serve the next ticket")

        payload = self.lane_check_success(
            self.lane_command("check", None, None, "--expect-mode", "direct")
        )
        # The predecessor's Contract stays in the lane's range and leaves the
        # ticket's window, which is the whole reason the two keys differ.
        self.assertEqual(len(payload["contract_commits"]), 1)
        self.assertEqual(payload["ticket_contract_commits"], [])
        self.assertEqual(payload["ticket_contract_added_lines"], 0)
        self.mode_mismatch(
            self.lane_command("check", None, None, "--expect-mode", "tdd")
        )

    def test_ticket_contract_depth_counts_added_lines_of_its_own_commits(self) -> None:
        self.create_task()
        lane = self.create_lane()
        self.freeze_contract(lane, "tests/contract.py", "a\nb\nc\nd\ne\n")
        self.commit_file(lane, "feature.txt", "one\ntwo\n", "Implement the Contract")

        payload = self.lane_check_success(self.lane_command("check"))

        # Five Contract lines; the two implementation lines are not depth.
        self.assertEqual(payload["ticket_contract_added_lines"], 5)


if __name__ == "__main__":
    import unittest

    unittest.main()
