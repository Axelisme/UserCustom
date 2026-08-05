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

    def collect(
        self,
        task_id: str | None = None,
        lane_id: str | None = None,
        ticket: str | None = "status-ticket",
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
        self.assert_help_surface(
            ("lane",), commands=("create", "check", "sync", "drop", "comment")
        )
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
            {
                self.lane_id: {
                    "sha": self.base,
                    "comment": "initial 🧭",
                    "uncollected": 0,
                }
            },
        )
        self.assertEqual(created["pending"], 0)
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
            {
                self.lane_id: {
                    "sha": self.base,
                    "comment": "blocked: waiting",
                    "uncollected": 0,
                }
            },
        )

        self.mutation_success(
            self.comment_command("", "", "--clear"),
            "lane-comment",
        )
        cleared = self.status()
        self.assertEqual(
            cleared["lanes"],
            {self.lane_id: {"sha": self.base, "uncollected": 0}},
        )
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
        self.assertEqual(
            payload["lanes"],
            {self.lane_id: {"sha": accepted, "uncollected": 0}},
        )
        self.assertEqual(payload["pending"], 0)
        self.assertNotIn("acceptance", payload)
        self.assertEqual(payload["accepted"], accepted)
        self.assertEqual(payload["user_accepted"], accepted)
        self.assertEqual(payload["landed"], accepted)
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), accepted)

    def test_status_derives_uncollected_and_pending_from_real_collect_history(self) -> None:
        self.create_task()
        lane = self.create_lane()

        untouched = self.status()
        self.assertEqual(
            untouched["lanes"],
            {self.lane_id: {"sha": self.base, "uncollected": 0}},
        )
        self.assertEqual(untouched["pending"], 0)

        self.commit_file(
            lane, "first.txt", "first\n", "First lane commit"
        )
        second = self.commit_file(
            lane, "second.txt", "second\n", "Second lane commit"
        )
        with_commits = self.status()
        self.assertEqual(with_commits["lanes"][self.lane_id]["sha"], second)
        self.assertEqual(with_commits["lanes"][self.lane_id]["uncollected"], 2)
        self.assertEqual(with_commits["pending"], 0)

        self.mutation_success(
            self.collect(ticket="status-history-ticket"), "integration-collect"
        )
        after_collect = self.status()
        self.assertEqual(
            after_collect["lanes"][self.lane_id],
            {"sha": second, "uncollected": 0},
        )
        self.assertEqual(after_collect["pending"], 1)
        self.assertNotIn("accepted", after_collect)
        self.assertEqual(self.ref_value(self.lane_ref()), second)
        self.assertEqual(
            self.ref_value(self.lane_base_ref()), self.base
        )

        third = self.commit_file(
            lane, "third.txt", "third\n", "Third lane commit"
        )
        after_rework = self.status()
        self.assertEqual(after_rework["lanes"][self.lane_id]["sha"], third)
        self.assertEqual(after_rework["lanes"][self.lane_id]["uncollected"], 1)
        self.assertEqual(after_rework["pending"], 0)

    def test_ninth_warning_counts_only_uncollected_lanes(self) -> None:
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
        self.mutation_success(ninth, "lane-create")
        self.assertEqual(self.status()["pending"], 0)

        # One lane with new work is still below the ninth-warning threshold;
        # active lane count alone must not trigger it.
        lane = self.lane_path(self.task_id, "lane-09")
        self.commit_file(lane, "lane.txt", "lane\n", "Uncollected lane work")
        no_warning = self.cli(
            self.nested,
            "lane",
            "create",
            "--task-id",
            self.task_id,
            "--lane-id",
            "lane-10",
        )
        self.mutation_success(no_warning, "lane-create")
        self.assertEqual(self.status()["lanes"]["lane-09"]["uncollected"], 1)
        self.assertEqual(self.status()["pending"], 0)

        for index in range(1, 9):
            self.commit_file(
                self.lane_path(self.task_id, f"lane-{index:02d}"),
                f"late-{index:02d}.txt",
                f"late {index}\n",
                f"Uncollected lane-{index:02d} work",
            )
        warning = self.cli(
            self.nested,
            "lane",
            "create",
            "--task-id",
            self.task_id,
            "--lane-id",
            "lane-11",
        )
        warning_payload = self.mutation_success(warning, "lane-create", warnings=True)
        self.assertEqual(len(warning_payload["warnings"]), 1)
        self.assertIn("collect/drop", warning_payload["warnings"][0].lower())
        self.assertNotIn("lane_consumption", self.status())

    def test_pending_lanes_are_reported_separately_from_ninth_warning(self) -> None:
        self.create_task()
        lanes: list[tuple[str, Path]] = []
        for index in range(1, 10):
            lane_id = f"pending-{index:02d}"
            lane = self.create_lane(lane_id=lane_id)
            self.commit_file(
                lane,
                f"{lane_id}.txt",
                f"{lane_id}\n",
                f"Collect {lane_id}",
            )
            lanes.append((lane_id, lane))

        for index, (lane_id, _lane) in enumerate(lanes, start=1):
            self.mutation_success(
                self.collect(
                    lane_id=lane_id,
                    ticket=f"pending-ticket-{index:02d}",
                ),
                "integration-collect",
            )

        pending = self.status()
        self.assertEqual(pending["pending"], 9)
        self.assertTrue(
            all(item["uncollected"] == 0 for item in pending["lanes"].values())
        )

        no_warning = self.cli(
            self.nested,
            "lane",
            "create",
            "--task-id",
            self.task_id,
            "--lane-id",
            "lane-10",
        )
        self.mutation_success(no_warning, "lane-create")
        self.assertEqual(self.status()["pending"], 9)


if __name__ == "__main__":
    import unittest

    unittest.main()
