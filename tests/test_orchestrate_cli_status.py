from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from tests._orchestrate_cli_support import OrchestrateCliRepositoryTestCase


class CliStatusContractTests(OrchestrateCliRepositoryTestCase):
    """v146 status/comment behavior through the production subprocess seam."""

    task_id = "cli-status"
    lane_id = "writer"

    def task_root(self, task_id: str | None = None) -> Path:
        return self.root / ".agent_state" / "worktrees" / (task_id or self.task_id)

    def integration_path(self, task_id: str | None = None) -> Path:
        return self.task_root(task_id) / "integration"

    def lane_path(self, task_id: str | None = None, lane_id: str | None = None) -> Path:
        return self.task_root(task_id) / "lanes" / (lane_id or self.lane_id)

    def telemetry_path(self, task_id: str | None = None) -> Path:
        return self.task_root(task_id) / "telemetry.jsonl"

    def lane_ref(self, task_id: str | None = None, lane_id: str | None = None) -> str:
        return f"refs/heads/wave/{task_id or self.task_id}/{lane_id or self.lane_id}"

    def lane_base_ref(self, task_id: str | None = None, lane_id: str | None = None) -> str:
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
        comment: str | None = None,
    ) -> Path:
        task = task_id or self.task_id
        lane = lane_id or self.lane_id
        argv = [
            "lane",
            "create",
            "--task-id",
            task,
            "--lane-id",
            lane,
        ]
        if comment is not None:
            argv.extend(("--comment", comment))
        self.mutation_success(self.cli(self.nested, *argv), "lane-create")
        return self.lane_path(task, lane)

    def comment_command(
        self,
        task_id: str | None = None,
        lane_id: str | None = None,
        *options: str,
    ):
        return self.cli(
            self.nested,
            "lane",
            "comment",
            "--task-id",
            task_id or self.task_id,
            "--lane-id",
            lane_id or self.lane_id,
            *options,
        )

    def status(self, task_id: str | None = None) -> dict[str, Any]:
        return self.success(
            self.cli(
                self.nested,
                "status",
                "--task-id",
                task_id or self.task_id,
            )
        )

    def events(self, task_id: str | None = None) -> list[dict[str, Any]]:
        path = self.telemetry_path(task_id)
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_top_level_version_is_one_json_envelope_without_repository(self) -> None:
        with tempfile.TemporaryDirectory(prefix="orchestrate-version- outside-") as outside:
            result = self.cli(Path(outside), "--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.count("\n"), 1)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "ok": True,
                "operation": "version",
                "orchestrate_version": self.orchestrate_version,
            },
        )
        self.operational_failure(
            self.cli(self.nested, "version"),
            "cli",
            "cli_usage",
        )

    def test_lane_help_and_group_are_removed_but_comment_grammar_is_public(self) -> None:
        lane_help = self.assert_help_surface(
            ("lane",), commands=("create", "check", "sync", "drop", "comment")
        )
        self.assertNotIn("--group", lane_help)
        self.assert_help_surface(
            ("lane", "create"),
            long_options=("--task-id", "--lane-id", "--comment"),
        )
        comment_help = self.assert_help_surface(
            ("lane", "comment"),
            long_options=("--task-id", "--lane-id", "--text", "--clear"),
        )
        self.assertIn("--text", comment_help)
        self.assertIn("--clear", comment_help)

        self.create_task()
        before = self.managed_state_snapshot()
        self.operational_failure(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                self.task_id,
                "--lane-id",
                self.lane_id,
                "--group",
                "legacy-group",
            ),
            "cli",
            "cli_usage",
        )
        self.assertEqual(self.managed_state_snapshot(), before)

    def test_create_overwrite_and_clear_comments_are_trimmed_sparse_and_audited(self) -> None:
        self.create_task()
        lane = self.create_lane(comment="  initial 🧭  ")
        created = self.status()
        self.assertEqual(
            created["lanes"],
            {self.lane_id: {"sha": self.base, "comment": "initial 🧭"}},
        )
        self.assertNotIn("acceptance", created)
        self.assertNotIn("lane_consumption", created)

        before_resources = self.managed_state_snapshot()
        overwritten = self.mutation_success(
            self.comment_command("", "", "--text", "  blocked: waiting  "),
            "lane-comment",
        )
        self.assertEqual(overwritten, {
            "ok": True,
            "operation": "lane-comment",
            "orchestrate_version": self.orchestrate_version,
        })
        after_resources = self.managed_state_snapshot()
        for key in ("refs", "worktrees"):
            self.assertEqual(after_resources[key], before_resources[key])
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), self.base)
        self.assertEqual(
            self.status()["lanes"],
            {self.lane_id: {"sha": self.base, "comment": "blocked: waiting"}},
        )

        self.mutation_success(
            self.comment_command("", "", "--clear"),
            "lane-comment",
        )
        cleared = self.status()
        self.assertEqual(cleared["lanes"], {self.lane_id: {"sha": self.base}})
        self.assertNotIn("lane_comments", cleared)
        self.assertEqual(self.git(lane, "status", "--porcelain"), "")

        comment_events = [
            event for event in self.events() if event["operation"] == "lane-comment"
        ]
        self.assertEqual(len(comment_events), 2)
        self.assertEqual(comment_events[0]["comment"], "blocked: waiting")
        self.assertIsNone(comment_events[1]["comment"])

    def test_comment_requires_one_choice_and_rejects_invalid_text_without_mutation(self) -> None:
        self.create_task()
        self.create_lane()
        cases = (
            (),
            ("--text", "one", "--clear"),
            ("--text", ""),
            ("--text", "   \t"),
            ("--text", "line\nfeed"),
            ("--text", "control\x01byte"),
            ("--text", "x" * 501),
        )
        before = self.managed_state_snapshot()
        for options in cases:
            with self.subTest(options=options):
                # Keep the public argv explicit: malformed choices are parser or
                # usage failures and must not become an implicit clear.
                result = self.cli(
                    self.nested,
                    "lane",
                    "comment",
                    "--task-id",
                    self.task_id,
                    "--lane-id",
                    self.lane_id,
                    *options,
                )
                self.operational_failure(result, "lane-comment" if options and options[0] == "--text" and len(options) == 2 else "cli", "cli_usage")
                self.assertEqual(self.managed_state_snapshot(), before)

        self.mutation_success(
            self.comment_command("", "", "--text", "  " + "x" * 500 + "  "),
            "lane-comment",
        )
        self.assertEqual(self.status()["lanes"][self.lane_id]["comment"], "x" * 500)

    def test_comment_mutation_requires_a_currently_projected_active_lane(self) -> None:
        self.create_task()
        self.create_lane(comment="terminal candidate")
        self.git(self.root, "worktree", "remove", "--force", str(self.lane_path()))
        self.git(self.root, "branch", "-D", f"wave/{self.task_id}/{self.lane_id}")
        self.git(self.root, "update-ref", "-d", self.lane_base_ref())
        before = self.managed_state_snapshot()
        self.operational_failure(
            self.comment_command("", "", "--text", "must fail"),
            "lane-comment",
            "lane_not_found",
        )
        self.assertEqual(self.managed_state_snapshot(), before)

    def test_terminal_comment_history_is_reported_but_not_current_status(self) -> None:
        self.create_task()
        self.create_lane(comment="keep audit context")
        self.mutation_success(
            self.comment_command("", "", "--text", "updated audit context"),
            "lane-comment",
        )
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "drop",
                "--task-id",
                self.task_id,
                "--lane-id",
                self.lane_id,
            ),
            "lane-drop",
        )
        current = self.status()
        self.assertEqual(current["lanes"], {})
        self.assertNotIn("lane_comments", current)
        self.operational_failure(
            self.comment_command("", "", "--clear"),
            "lane-comment",
            "lane_not_found",
        )

        output = self.root / "comment-report"
        self.mutation_success(
            self.cli(
                self.nested,
                "report",
                "--task-id",
                self.task_id,
                "--output-dir",
                str(output),
            ),
            "report",
        )
        raw = (output / "orchestrate-telemetry.jsonl").read_text(encoding="utf-8")
        self.assertIn("keep audit context", raw)
        self.assertIn("updated audit context", raw)
        report = json.loads((output / "orchestrate-report.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(report["counts"]["lifecycle_events"], 4)

    def test_status_uses_nested_lane_objects_and_preserves_real_evidence_slots(self) -> None:
        self.create_task()
        lane = self.create_lane()
        accepted = self.base
        for name in ("accepted", "user-accepted", "landed"):
            self.git(self.root, "update-ref", f"refs/orchestrate/{self.task_id}/{name}", accepted)
        acceptance = self.task_root() / "acceptance"
        self.git(self.root, "worktree", "add", "-q", "--detach", str(acceptance), accepted)

        payload = self.status()
        self.assertEqual(payload["lanes"], {self.lane_id: {"sha": accepted}})
        self.assertNotIn("acceptance", payload)
        self.assertEqual(payload["accepted"], accepted)
        self.assertEqual(payload["user_accepted"], accepted)
        self.assertEqual(payload["landed"], accepted)
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), accepted)

    def test_ninth_active_lane_warns_and_history_does_not_count(self) -> None:
        self.create_task()
        for index in range(1, 9):
            result = self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                self.task_id,
                "--lane-id",
                f"lane-{index:02d}",
            )
            self.mutation_success(result, "lane-create")

        ninth = self.cli(
            self.nested,
            "lane",
            "create",
            "--task-id",
            self.task_id,
            "--lane-id",
            "lane-09",
        )
        payload = self.mutation_success(ninth, "lane-create", warnings=True)
        self.assertEqual(len(payload["warnings"]), 1)
        self.assertIn("9", payload["warnings"][0])
        self.assertIn("collect/drop", payload["warnings"][0].lower())

        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "drop",
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-09",
            ),
            "lane-drop",
        )
        eighth_active = self.status()
        self.assertEqual(len(eighth_active["lanes"]), 8)

        # A historical create and drop do not count. This create is active #9
        # only because eight other managed lane inventories remain.
        no_warning = self.cli(
            self.nested,
            "lane",
            "create",
            "--task-id",
            self.task_id,
            "--lane-id",
            "lane-10",
        )
        warning_payload = self.mutation_success(no_warning, "lane-create", warnings=True)
        self.assertIn("9", warning_payload["warnings"][0])
        self.assertEqual(len(self.status()["lanes"]), 9)
        self.assertNotIn("lane_consumption", self.status())


if __name__ == "__main__":
    import unittest

    unittest.main()
