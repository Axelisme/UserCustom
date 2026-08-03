from __future__ import annotations

import importlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from tests._orchestrate_cli_support import OrchestrateCliRepositoryTestCase, run_git


class ObservationReportingCleanupContractTests(OrchestrateCliRepositoryTestCase):
    """Contract module D through the shipped subprocess and real Git/filesystem."""

    def task_root(self, task_id: str) -> Path:
        return self.root / ".agent_state" / "worktrees" / task_id

    def integration_path(self, task_id: str) -> Path:
        return self.task_root(task_id) / "integration"

    def acceptance_path(self, task_id: str) -> Path:
        return self.task_root(task_id) / "acceptance"

    def lane_path(self, task_id: str, lane_id: str) -> Path:
        return self.task_root(task_id) / "lanes" / lane_id

    def telemetry_path(self, task_id: str) -> Path:
        return (
            self.root
            / ".agent_state"
            / "worktrees"
            / task_id
            / "telemetry.jsonl"
        )

    def integration_ref(self, task_id: str) -> str:
        return f"refs/heads/wave/{task_id}/integration"

    def accepted_ref(self, task_id: str) -> str:
        return f"refs/orchestrate/{task_id}/accepted"

    def landed_ref(self, task_id: str) -> str:
        return f"refs/orchestrate/{task_id}/landed"

    def create_task(self, task_id: str) -> Path:
        self.mutation_success(
            self.cli(self.nested, "integration", "create", "--task-id", task_id),
            "integration-create",
        )
        return self.integration_path(task_id)

    def create_lane(self, task_id: str, lane_id: str) -> Path:
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                task_id,
                "--lane-id",
                lane_id,
            ),
            "lane-create",
        )
        return self.lane_path(task_id, lane_id)

    def collect_lane(self, task_id: str, lane_id: str) -> None:
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "collect",
                "--task-id",
                task_id,
                "--lane-id",
                lane_id,
            ),
            "integration-collect",
        )

    def accept_current(self, task_id: str) -> str:
        self.mutation_success(
            self.cli(self.nested, "acceptance", "start", "--task-id", task_id),
            "acceptance-start",
        )
        subject = self.git(self.acceptance_path(task_id), "rev-parse", "HEAD")
        payload = self.success(
            self.cli(
                self.nested,
                "acceptance",
                "result",
                "--task-id",
                task_id,
                "--verifier",
                "agent",
                "--outcome",
                "pass",
            )
        )
        self.assertEqual(payload["operation"], "acceptance-result")
        return subject

    def land(self, task_id: str) -> None:
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "land",
                "--task-id",
                task_id,
                "--persist",
                "main",
            ),
            "integration-land",
        )

    def events(self, task_id: str) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in self.telemetry_path(task_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]

    def event(
        self,
        at: str,
        operation: str,
        outcome: str,
        **extra: object,
    ) -> dict[str, object]:
        return {
            "event_version": 1,
            "at": at,
            "task_id": "alpha",
            "operation": operation,
            "outcome": outcome,
            **extra,
        }

    def compute_report(
        self,
        events: list[dict[str, object]],
        now: datetime,
        *,
        integration_diff: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        module = importlib.import_module("_orchestrate.telemetry")
        candidate = getattr(module, "compute_report", None)
        self.assertTrue(
            callable(candidate),
            "Telemetry must expose the admitted pure compute_report seam",
        )
        compute = candidate
        assert isinstance(compute, Callable)
        snapshot: dict[str, object] = {
            "task_id": "alpha",
            "warnings": [],
            "invalid_telemetry_lines": 0,
            "integration_diff": dict(
                integration_diff
                or {
                    "files": 0,
                    "binary_files": 0,
                    "additions": 0,
                    "deletions": 0,
                    "churn": 0,
                }
            ),
        }
        result = compute(snapshot, events, now)
        self.assertIsInstance(result, dict)
        return result

    def report(self, task_id: str, output_dir: Path) -> dict[str, Any]:
        return self.mutation_success(
            self.cli(
                self.nested,
                "report",
                "--task-id",
                task_id,
                "--output-dir",
                str(output_dir),
            ),
            "report",
        )

    def report_json(self, output_dir: Path) -> dict[str, Any]:
        value = json.loads(
            (output_dir / "orchestrate-report.json").read_text(encoding="utf-8")
        )
        self.assertIsInstance(value, dict)
        return value

    def assert_task_git_resources_absent(self, task_id: str) -> None:
        refs = self.git(
            self.root,
            "for-each-ref",
            "--format=%(refname)",
            f"refs/orchestrate/{task_id}/",
            f"refs/heads/wave/{task_id}/",
        )
        self.assertEqual(refs, "")
        worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        self.assertNotIn(str(self.task_root(task_id)), worktrees)

    def test_01_task_start_and_duplicate_pause_resume_event_semantics(self) -> None:
        task_id = "timing-explicit"
        self.create_task(task_id)
        initial = self.events(task_id)
        self.assertEqual(len(initial), 1)
        self.assertEqual(initial[0]["operation"], "integration-create")
        self.assertEqual(initial[0]["outcome"], "success")

        self.mutation_success(
            self.cli(self.nested, "timing", "pause", "--task-id", task_id),
            "timing-pause",
        )
        paused_bytes = self.telemetry_path(task_id).read_bytes()
        paused_events = self.events(task_id)
        self.assertEqual(paused_events[-1]["operation"], "timing-pause")

        self.mutation_success(
            self.cli(self.nested, "timing", "pause", "--task-id", task_id),
            "timing-pause",
            warnings=True,
        )
        self.assertEqual(self.telemetry_path(task_id).read_bytes(), paused_bytes)

        self.mutation_success(
            self.cli(self.nested, "timing", "resume", "--task-id", task_id),
            "timing-resume",
        )
        resumed_bytes = self.telemetry_path(task_id).read_bytes()
        self.assertEqual(self.events(task_id)[-1]["operation"], "timing-resume")
        self.mutation_success(
            self.cli(self.nested, "timing", "resume", "--task-id", task_id),
            "timing-resume",
            warnings=True,
        )
        self.assertEqual(self.telemetry_path(task_id).read_bytes(), resumed_bytes)

    def test_02_closed_auto_resume_set_precedes_success_or_failure_and_queries_are_excluded(
        self,
    ) -> None:
        invocations: tuple[tuple[str, tuple[str, ...], int, str], ...] = (
            (
                "lane-create",
                ("lane", "create", "--lane-id", "writer"),
                0,
                "success",
            ),
            ("lane-check", ("lane", "check", "--lane-id", "missing"), 1, "failure"),
            ("lane-sync", ("lane", "sync", "--lane-id", "missing"), 2, "failure"),
            ("lane-drop", ("lane", "drop", "--lane-id", "missing"), 2, "failure"),
            (
                "integration-collect",
                ("integration", "collect", "--lane-id", "missing"),
                2,
                "failure",
            ),
            (
                "integration-reconcile",
                (
                    "integration",
                    "reconcile",
                    "--lane-id",
                    "repair",
                    "--persist",
                    "missing",
                ),
                2,
                "failure",
            ),
            (
                "integration-land",
                ("integration", "land", "--persist", "main"),
                2,
                "failure",
            ),
            ("integration-remove", ("integration", "remove", "--no-report"), 2, "failure"),
            ("acceptance-start", ("acceptance", "start"), 0, "success"),
            (
                "acceptance-result",
                ("acceptance", "result", "--verifier", "agent", "--outcome", "pass"),
                2,
                "failure",
            ),
        )
        for index, (operation, argv, returncode, outcome) in enumerate(invocations):
            task_id = f"auto-{index}"
            self.create_task(task_id)
            if operation == "integration-remove":
                self.create_lane(task_id, "blocker")
            self.mutation_success(
                self.cli(self.nested, "timing", "pause", "--task-id", task_id),
                "timing-pause",
            )
            result = self.cli(
                self.nested,
                *argv,
                "--task-id",
                task_id,
            )
            self.assertEqual(result.returncode, returncode, result.stderr)
            observed = self.events(task_id)
            resume_indexes = [
                position
                for position, event in enumerate(observed)
                if event["operation"] == "timing-resume" and event.get("auto") is True
            ]
            operation_indexes = [
                position
                for position, event in enumerate(observed)
                if event["operation"] == operation
            ]
            with self.subTest(operation=operation, assertion="one-auto-resume"):
                self.assertEqual(len(resume_indexes), 1)
            with self.subTest(operation=operation, assertion="before-outcome"):
                self.assertTrue(operation_indexes)
                self.assertLess(resume_indexes[0], operation_indexes[-1])
                self.assertEqual(observed[operation_indexes[-1]]["outcome"], outcome)

        task_id = "excluded-queries"
        self.create_task(task_id)
        self.mutation_success(
            self.cli(self.nested, "timing", "pause", "--task-id", task_id),
            "timing-pause",
        )
        before = self.telemetry_path(task_id).read_bytes()
        output_dir = self.root / "query-report"
        excluded = (
            ("status", "--task-id", task_id),
            ("report", "--task-id", task_id, "--output-dir", str(output_dir)),
            ("pin", "status"),
            ("doctor",),
            ("doctor", "diff", "136", "136"),
            ("release", "--version", "136"),
        )
        for argv in excluded:
            self.cli(self.nested, *argv)
            with self.subTest(argv=argv):
                self.assertEqual(self.telemetry_path(task_id).read_bytes(), before)

    def test_03_observation_append_failure_warns_but_explicit_timing_failure_is_fatal(
        self,
    ) -> None:
        task_id = "append-warning"
        self.create_task(task_id)
        telemetry = self.telemetry_path(task_id)
        telemetry.unlink()
        telemetry.mkdir()

        lane = self.cli(
            self.nested,
            "lane",
            "create",
            "--task-id",
            task_id,
            "--lane-id",
            "writer",
        )
        self.mutation_success(lane, "lane-create", warnings=True)
        self.assertTrue(self.lane_path(task_id, "writer").is_dir())

        timing = self.cli(
            self.nested,
            "timing",
            "pause",
            "--task-id",
            task_id,
        )
        self.operational_failure(timing, "timing-pause", "telemetry_write_failed")
        self.assertTrue(telemetry.is_dir())

    def test_04_literal_events_compute_exact_counts_rates_spans_and_markers(self) -> None:
        events = [
            self.event("2026-07-30T12:00:00+00:00", "integration-create", "success"),
            self.event("2026-07-30T12:02:00+00:00", "lane-create", "success", lane_id="docs"),
            self.event("2026-07-30T12:03:00+00:00", "lane-create", "success", lane_id="api"),
            self.event("2026-07-30T12:04:00+00:00", "lane-sync", "conflict", lane_id="docs"),
            self.event("2026-07-30T12:05:00+00:00", "integration-collect", "conflict", lane_id="docs"),
            self.event("2026-07-30T12:06:00+00:00", "lane-sync", "success", lane_id="docs"),
            self.event("2026-07-30T12:07:00+00:00", "integration-collect", "success", lane_id="docs"),
            self.event("2026-07-30T12:08:00+00:00", "lane-drop", "success", lane_id="api"),
            self.event("2026-07-30T12:10:00+00:00", "timing-pause", "success"),
            self.event("2026-07-30T12:15:00+00:00", "timing-resume", "success"),
            self.event("2026-07-30T12:16:00+00:00", "acceptance-start", "success", subject_sha="a" * 40),
            self.event("2026-07-30T12:17:00+00:00", "acceptance-result", "fail", subject_sha="a" * 40),
            self.event("2026-07-30T12:18:00+00:00", "acceptance-start", "success", subject_sha="b" * 40),
            self.event("2026-07-30T12:19:00+00:00", "acceptance-result", "pass", subject_sha="b" * 40),
            self.event("2026-07-30T12:20:00+00:00", "integration-reconcile", "noop", lane_id="repair", persist="dev"),
            self.event("2026-07-30T12:21:00+00:00", "integration-reconcile", "success", lane_id="repair", persist="dev"),
            self.event("2026-07-30T12:22:00+00:00", "integration-reconcile", "conflict", lane_id="repair", persist="dev"),
            self.event("2026-07-30T12:23:00+00:00", "integration-land", "stale", persist="dev"),
            self.event("2026-07-30T12:24:00+00:00", "integration-land", "nothing_to_land", persist="dev"),
            self.event("2026-07-30T12:25:00+00:00", "integration-land", "success", persist="dev"),
            self.event("2026-07-30T12:30:00+00:00", "integration-remove", "success"),
        ]
        report = self.compute_report(
            events,
            datetime(2026, 7, 30, 12, 30, tzinfo=UTC),
            integration_diff={
                "files": 2,
                "binary_files": 0,
                "additions": 12,
                "deletions": 3,
                "churn": 15,
            },
        )
        self.assertEqual(report["report_version"], 1)
        self.assertEqual(report["task_id"], "alpha")
        self.assertEqual(report["generated_at"], "2026-07-30T12:30:00+00:00")
        self.assertEqual(report["warnings"], [])
        self.assertEqual(
            report["counts"],
            {
                "lifecycle_events": 21,
                "lanes_created": 2,
                "lanes_collected": 1,
                "lanes_dropped": 1,
                "sync_attempts": 2,
                "sync_conflicts": 1,
                "collect_attempts": 2,
                "collect_conflicts": 1,
                "acceptance_passes": 1,
                "acceptance_failures": 1,
                "reconciliation_attempts": 3,
                "reconciliation_noops": 1,
                "reconciliation_clean": 1,
                "reconciliation_conflicts": 1,
                "landing_attempts": 3,
                "landing_successes": 1,
                "landing_stale": 1,
                "landing_nothing_to_land": 1,
                "invalid_telemetry_lines": 0,
            },
        )
        self.assertEqual(
            report["rates"],
            {
                "lane_collection_rate": 0.5,
                "sync_conflict_rate": 0.5,
                "collect_conflict_rate": 0.5,
                "acceptance_pass_rate": 0.5,
                "reconciliation_conflict_rate": 1 / 3,
                "landing_success_rate": 1 / 3,
                "events_per_wall_hour": 42.0,
                "events_per_recorded_hour": 50.4,
                "churn_per_wall_hour": 30.0,
                "churn_per_recorded_hour": 36.0,
            },
        )
        self.assertEqual(
            report["timing"],
            {"wall_seconds": 1800.0, "paused_seconds": 300.0, "recorded_seconds": 1500.0},
        )
        self.assertEqual(
            report["integration_diff"],
            {"files": 2, "binary_files": 0, "additions": 12, "deletions": 3, "churn": 15},
        )
        # A dropped lane's time is kept out of the collected total: the two numbers answer
        # different questions and summing them inflates "how long a lane takes".
        self.assertEqual(
            report["lane_durations"],
            {
                "collected": {"lanes": 1.0, "elapsed_seconds": 300.0, "recorded_seconds": 300.0},
                "dropped": {"lanes": 1.0, "elapsed_seconds": 300.0, "recorded_seconds": 300.0},
            },
        )
        timeline = report["timeline"]
        self.assertEqual(
            timeline,
            [
                {"type": "span", "kind": "task", "identity": "alpha", "outcome": "success", "started_at": "2026-07-30T12:00:00+00:00", "ended_at": "2026-07-30T12:30:00+00:00", "elapsed_seconds": 1800.0, "recorded_seconds": 1500.0},
                {"type": "span", "kind": "lane", "identity": "docs", "outcome": "success", "disposition": "collected", "started_at": "2026-07-30T12:02:00+00:00", "ended_at": "2026-07-30T12:07:00+00:00", "elapsed_seconds": 300.0, "recorded_seconds": 300.0},
                {"type": "span", "kind": "lane", "identity": "api", "outcome": "success", "disposition": "dropped", "started_at": "2026-07-30T12:03:00+00:00", "ended_at": "2026-07-30T12:08:00+00:00", "elapsed_seconds": 300.0, "recorded_seconds": 300.0},
                {"type": "marker", "kind": "sync", "identity": "docs", "outcome": "conflict", "at": "2026-07-30T12:04:00+00:00"},
                {"type": "marker", "kind": "collect", "identity": "docs", "outcome": "conflict", "at": "2026-07-30T12:05:00+00:00"},
                {"type": "marker", "kind": "sync", "identity": "docs", "outcome": "success", "at": "2026-07-30T12:06:00+00:00"},
                {"type": "marker", "kind": "collect", "identity": "docs", "outcome": "success", "at": "2026-07-30T12:07:00+00:00"},
                {"type": "span", "kind": "pause", "identity": "pause", "outcome": "success", "started_at": "2026-07-30T12:10:00+00:00", "ended_at": "2026-07-30T12:15:00+00:00", "elapsed_seconds": 300.0, "recorded_seconds": 0.0},
                {"type": "span", "kind": "acceptance", "identity": "a" * 40, "outcome": "fail", "started_at": "2026-07-30T12:16:00+00:00", "ended_at": "2026-07-30T12:17:00+00:00", "elapsed_seconds": 60.0, "recorded_seconds": 60.0},
                {"type": "span", "kind": "acceptance", "identity": "b" * 40, "outcome": "success", "started_at": "2026-07-30T12:18:00+00:00", "ended_at": "2026-07-30T12:19:00+00:00", "elapsed_seconds": 60.0, "recorded_seconds": 60.0},
                {"type": "marker", "kind": "reconcile", "identity": "dev", "outcome": "noop", "at": "2026-07-30T12:20:00+00:00"},
                {"type": "marker", "kind": "reconcile", "identity": "dev", "outcome": "success", "at": "2026-07-30T12:21:00+00:00"},
                {"type": "marker", "kind": "reconcile", "identity": "dev", "outcome": "conflict", "at": "2026-07-30T12:22:00+00:00"},
                {"type": "marker", "kind": "land", "identity": "dev", "outcome": "stale", "at": "2026-07-30T12:23:00+00:00"},
                {"type": "marker", "kind": "land", "identity": "dev", "outcome": "nothing_to_land", "at": "2026-07-30T12:24:00+00:00"},
                {"type": "marker", "kind": "land", "identity": "dev", "outcome": "success", "at": "2026-07-30T12:25:00+00:00"},
            ],
        )
        self.assertEqual(
            timeline,
            sorted(
                timeline,
                key=lambda entry: (
                    entry.get("at", entry.get("started_at")),
                    entry["type"],
                    entry["kind"],
                    entry["identity"],
                ),
            ),
        )

    def test_05_zero_denominators_are_omitted_independently_and_outputs_are_finite(self) -> None:
        start = self.event(
            "2026-07-30T12:00:00+00:00", "integration-create", "success"
        )
        report = self.compute_report(
            [start], datetime(2026, 7, 30, 13, 0, tzinfo=UTC)
        )
        rates = report["rates"]
        for absent in (
            "lane_collection_rate",
            "sync_conflict_rate",
            "collect_conflict_rate",
            "acceptance_pass_rate",
            "reconciliation_conflict_rate",
            "landing_success_rate",
        ):
            self.assertNotIn(absent, rates)
        self.assertEqual(rates["events_per_wall_hour"], 1.0)
        self.assertEqual(rates["events_per_recorded_hour"], 1.0)
        self.assertEqual(rates["churn_per_wall_hour"], 0.0)
        self.assertEqual(rates["churn_per_recorded_hour"], 0.0)

        domain_rates = {
            "lane_collection_rate": self.event("2026-07-30T12:30:00+00:00", "lane-create", "success", lane_id="docs"),
            "sync_conflict_rate": self.event("2026-07-30T12:30:00+00:00", "lane-sync", "success", lane_id="docs"),
            "collect_conflict_rate": self.event("2026-07-30T12:30:00+00:00", "integration-collect", "conflict", lane_id="docs"),
            "acceptance_pass_rate": self.event("2026-07-30T12:30:00+00:00", "acceptance-result", "pass", subject_sha="a" * 40),
            "reconciliation_conflict_rate": self.event("2026-07-30T12:30:00+00:00", "integration-reconcile", "conflict", lane_id="repair", persist="dev"),
            "landing_success_rate": self.event("2026-07-30T12:30:00+00:00", "integration-land", "stale", persist="dev"),
        }
        expected_values = {
            "lane_collection_rate": 0.0,
            "sync_conflict_rate": 0.0,
            "collect_conflict_rate": 1.0,
            "acceptance_pass_rate": 1.0,
            "reconciliation_conflict_rate": 1.0,
            "landing_success_rate": 0.0,
        }
        for target, denominator_event in domain_rates.items():
            observed = self.compute_report(
                [start, denominator_event],
                datetime(2026, 7, 30, 13, 0, tzinfo=UTC),
            )["rates"]
            with self.subTest(target=target):
                self.assertEqual(observed[target], expected_values[target])
                for other in domain_rates:
                    if other != target:
                        self.assertNotIn(other, observed)
                for value in observed.values():
                    self.assertTrue(math.isfinite(value))

        zero_time = self.compute_report(
            [start], datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        )
        for absent in (
            "events_per_wall_hour",
            "events_per_recorded_hour",
            "churn_per_wall_hour",
            "churn_per_recorded_hour",
        ):
            self.assertNotIn(absent, zero_time["rates"])
        encoded = json.dumps(zero_time, allow_nan=False)
        self.assertNotIn("NaN", encoded)
        self.assertNotIn("Infinity", encoded)

    def test_06_open_pause_is_virtually_closed_without_a_resume_event(self) -> None:
        events = [
            self.event("2026-07-30T12:00:00+00:00", "integration-create", "success"),
            self.event("2026-07-30T12:10:00+00:00", "timing-pause", "success"),
        ]
        report = self.compute_report(
            events, datetime(2026, 7, 30, 12, 30, tzinfo=UTC)
        )
        self.assertEqual(
            report["timing"],
            {"wall_seconds": 1800.0, "paused_seconds": 1200.0, "recorded_seconds": 600.0},
        )
        self.assertIn(
            {
                "type": "span",
                "kind": "pause",
                "identity": "pause",
                "started_at": "2026-07-30T12:10:00+00:00",
                "ended_at": "2026-07-30T12:30:00+00:00",
                "elapsed_seconds": 1200.0,
                "recorded_seconds": 0.0,
            },
            report["timeline"],
        )
        self.assertEqual([event["operation"] for event in events], ["integration-create", "timing-pause"])

    def test_07_malformed_unknown_and_truncated_events_warn_skip_and_preserve_raw_bytes(self) -> None:
        task_id = "raw-invalid"
        self.create_task(task_id)
        valid = json.dumps(
            self.event(
                "2026-07-30T12:00:00+00:00",
                "integration-create",
                "success",
            ),
            separators=(",", ":"),
        ).encode()
        raw = b"\n".join(
            (
                valid,
                b"\xffnot-utf8",
                b'{"event_version":9,"at":"2026-07-30T12:01:00+00:00","task_id":"alpha","operation":"lane-create","outcome":"success"}',
                b'{"event_version":1,"at":"2026-07-30T12:02:00+00:00"}',
                b'{"event_version":1,"at":"truncated"',
            )
        )
        self.telemetry_path(task_id).write_bytes(raw)
        output = self.root / "raw-report"
        self.report(task_id, output)
        self.assertEqual((output / "orchestrate-telemetry.jsonl").read_bytes(), raw)
        report = self.report_json(output)
        self.assertEqual(report["counts"]["invalid_telemetry_lines"], 4)
        self.assertEqual(report["counts"]["lifecycle_events"], 1)
        self.assertTrue(report["warnings"])

    def test_08_missing_telemetry_writes_zero_raw_warning_and_retains_git_fields(self) -> None:
        task_id = "missing-raw"
        self.create_task(task_id)
        self.telemetry_path(task_id).unlink()
        output = self.root / "missing-report"
        self.report(task_id, output)
        self.assertEqual((output / "orchestrate-telemetry.jsonl").read_bytes(), b"")
        report = self.report_json(output)
        self.assertEqual(report["task_id"], task_id)
        self.assertTrue(report["warnings"])
        self.assertNotIn("timing", report)
        self.assertEqual(
            report["integration_diff"],
            {"files": 0, "binary_files": 0, "additions": 0, "deletions": 0, "churn": 0},
        )
        self.assertEqual(report["counts"]["lifecycle_events"], 0)

    def test_09_integration_diff_is_exact_recorded_base_to_current_text_and_binary(self) -> None:
        task_id = "whole-diff"
        integration = self.create_task(task_id)
        (integration / "base.txt").write_text("changed\n", encoding="utf-8")
        (integration / "added.txt").write_text("one\ntwo\n", encoding="utf-8")
        (integration / "binary.bin").write_bytes(b"\x00\x01\xff")
        run_git(integration, "add", "base.txt", "added.txt", "binary.bin")
        run_git(integration, "commit", "-q", "-m", "Mixed task diff")

        output = self.root / "diff-report"
        self.report(task_id, output)
        report = self.report_json(output)
        self.assertEqual(
            report["integration_diff"],
            {"files": 3, "binary_files": 1, "additions": 3, "deletions": 1, "churn": 4},
        )

    def test_10_report_owns_two_fixed_names_and_atomically_overwrites_without_timestamps(self) -> None:
        task_id = "atomic-report"
        self.create_task(task_id)
        output = self.root / "operator" / "arbitrary" / "artifacts"
        output.mkdir(parents=True)
        sentinel = output / "operator.bin"
        sentinel.write_bytes(b"operator-owned\x00\xff")
        report_path = output / "orchestrate-report.json"
        raw_path = output / "orchestrate-telemetry.jsonl"
        report_path.write_bytes(b"old-report")
        raw_path.write_bytes(b"old-raw")
        old_inodes = (report_path.stat().st_ino, raw_path.stat().st_ino)

        self.report(task_id, output)
        self.assertEqual(
            {path.name for path in output.iterdir()},
            {"operator.bin", "orchestrate-report.json", "orchestrate-telemetry.jsonl"},
        )
        self.assertEqual(sentinel.read_bytes(), b"operator-owned\x00\xff")
        self.assertNotEqual(report_path.read_bytes(), b"old-report")
        self.assertNotEqual(raw_path.read_bytes(), b"old-raw")
        self.assertNotEqual(
            (report_path.stat().st_ino, raw_path.stat().st_ino), old_inodes
        )

        first_inodes = (report_path.stat().st_ino, raw_path.stat().st_ino)
        self.report(task_id, output)
        self.assertNotEqual(
            (report_path.stat().st_ino, raw_path.stat().st_ino), first_inodes
        )
        self.assertFalse(any("2026" in path.name for path in output.iterdir()))

    def test_11_deterministic_report_failure_preserves_artifacts_and_task_resources(self) -> None:
        task_id = "report-failure"
        self.create_task(task_id)
        output = self.root / "blocked-report"
        output.mkdir()
        report_collision = output / "orchestrate-report.json"
        report_collision.mkdir()
        (report_collision / "owned.bin").write_bytes(b"do-not-touch\x00\xff")
        raw_path = output / "orchestrate-telemetry.jsonl"
        raw_path.write_bytes(b"existing-raw\x00\xff")
        artifacts_before = {
            path.relative_to(output).as_posix(): (
                None if path.is_dir() else path.read_bytes()
            )
            for path in sorted(output.rglob("*"))
        }
        resources_before = self.managed_state_snapshot()

        result = self.cli(
            self.nested,
            "report",
            "--task-id",
            task_id,
            "--output-dir",
            str(output),
        )
        self.operational_failure(result, "report", "report_write_failed")
        self.assertEqual(self.managed_state_snapshot(), resources_before)
        self.assertEqual(
            {
                path.relative_to(output).as_posix(): (
                    None if path.is_dir() else path.read_bytes()
                )
                for path in sorted(output.rglob("*"))
            },
            artifacts_before,
        )

    def test_12_remove_requires_exactly_one_report_choice_and_checks_preconditions_first(self) -> None:
        task_id = "remove-choice"
        self.create_task(task_id)
        for choice in ((), ("--output-dir", "unused", "--no-report")):
            result = self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                *choice,
            )
            with self.subTest(choice=choice):
                self.operational_failure(result, "cli", "cli_usage")

        self.create_lane(task_id, "unfinished")
        output = self.root / "must-not-exist"
        before = self.managed_state_snapshot()
        result = self.cli(
            self.nested,
            "integration",
            "remove",
            "--task-id",
            task_id,
            "--output-dir",
            str(output),
        )
        self.operational_failure(result, "integration-remove", "task_incomplete")
        self.assertEqual(self.managed_state_snapshot(), before)
        self.assertFalse(output.exists())

    def test_13_normal_changed_remove_requires_no_lanes_and_equal_landed_accepted_integration(self) -> None:
        task_id = "normal-proof"
        lane = self.create_lane_after_task(task_id, "delivery")
        self.commit_lane(lane)
        self.collect_lane(task_id, "delivery")
        accepted = self.accept_current(task_id)
        self.land(task_id)
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), accepted)
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), accepted)
        self.assertEqual(self.ref_value(self.integration_ref(task_id)), accepted)
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--no-report",
            ),
            "integration-remove",
        )
        self.assert_task_git_resources_absent(task_id)

        revoked = "revoked-proof"
        lane = self.create_lane_after_task(revoked, "delivery")
        self.commit_lane(lane, path="revoked-delivery.txt")
        self.collect_lane(revoked, "delivery")
        self.accept_current(revoked)
        self.land(revoked)
        payload = self.success(
            self.cli(
                self.nested,
                "acceptance",
                "result",
                "--task-id",
                revoked,
                "--verifier",
                "agent",
                "--outcome",
                "fail",
            )
        )
        self.assertEqual(payload["operation"], "acceptance-result")
        self.assertEqual(self.ref_value(self.accepted_ref(revoked)), "")
        before = self.managed_state_snapshot()
        result = self.cli(
            self.nested,
            "integration",
            "remove",
            "--task-id",
            revoked,
            "--no-report",
        )
        self.operational_failure(result, "integration-remove", "task_incomplete")
        self.assertEqual(self.managed_state_snapshot(), before)

    def create_lane_after_task(self, task_id: str, lane_id: str) -> Path:
        self.create_task(task_id)
        return self.create_lane(task_id, lane_id)

    def test_14_reverted_to_base_no_change_discards_stale_authority_without_empty_land(self) -> None:
        task_id = "reverted-task"
        first = self.create_lane_after_task(task_id, "forward")
        (first / "base.txt").write_text("changed\n", encoding="utf-8")
        run_git(first, "add", "base.txt")
        run_git(first, "commit", "-q", "-m", "Change base")
        self.collect_lane(task_id, "forward")
        stale = self.accept_current(task_id)
        self.land(task_id)
        main_before = self.git(self.root, "rev-parse", "main")
        count_before = self.git(self.root, "rev-list", "--count", "main")

        revert = self.create_lane(task_id, "revert")
        (revert / "base.txt").write_text("base\n", encoding="utf-8")
        run_git(revert, "add", "base.txt")
        run_git(revert, "commit", "-q", "-m", "Revert task tree")
        self.collect_lane(task_id, "revert")
        current = self.ref_value(self.integration_ref(task_id))
        self.assertNotEqual(current, stale)
        self.assertEqual(
            self.git(self.root, "rev-parse", f"{current}^{{tree}}"),
            self.git(self.root, "rev-parse", f"{self.base}^{{tree}}"),
        )
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--no-report",
            ),
            "integration-remove",
            warnings=True,
        )
        self.assert_task_git_resources_absent(task_id)
        self.assertEqual(self.git(self.root, "rev-parse", "main"), main_before)
        self.assertEqual(self.git(self.root, "rev-list", "--count", "main"), count_before)

    def test_15_dirty_acceptance_is_force_removed_but_dirty_or_wrong_integration_refuses(self) -> None:
        accepted_dirty = "dirty-acceptance"
        self.create_task(accepted_dirty)
        self.mutation_success(
            self.cli(
                self.nested,
                "acceptance",
                "start",
                "--task-id",
                accepted_dirty,
            ),
            "acceptance-start",
        )
        (self.acceptance_path(accepted_dirty) / "diagnostic.bin").write_bytes(
            b"discard after proof\x00\xff"
        )
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                accepted_dirty,
                "--no-report",
            ),
            "integration-remove",
            warnings=True,
        )
        self.assert_task_git_resources_absent(accepted_dirty)

        dirty = "dirty-integration"
        integration = self.create_task(dirty)
        sentinel = integration / "writer.bin"
        sentinel.write_bytes(b"preserve dirty integration\x00\xff")
        before = self.managed_state_snapshot()
        result = self.cli(
            self.nested,
            "integration",
            "remove",
            "--task-id",
            dirty,
            "--no-report",
        )
        self.operational_failure(result, "integration-remove", "dirty_worktree")
        self.assertEqual(self.managed_state_snapshot(), before)
        self.assertEqual(sentinel.read_bytes(), b"preserve dirty integration\x00\xff")

        wrong = "wrong-integration"
        integration = self.create_task(wrong)
        run_git(integration, "switch", "-c", "operator-preserve")
        before = self.managed_state_snapshot()
        result = self.cli(
            self.nested,
            "integration",
            "remove",
            "--task-id",
            wrong,
            "--no-report",
        )
        self.operational_failure(
            result, "integration-remove", "worktree_identity_mismatch"
        )
        self.assertEqual(self.managed_state_snapshot(), before)
        self.assertTrue(self.ref_value("refs/heads/operator-preserve"))

    def test_16_abandon_removes_only_closed_known_inventory_and_active_telemetry(self) -> None:
        task_id = "bounded-abandon"
        self.create_task(task_id)
        lane = self.create_lane(task_id, "writer")
        (lane / "writer.bin").write_bytes(b"managed dirt")
        run_git(lane, "switch", "-c", "operator-unrelated")
        unrelated_tip = self.ref_value("refs/heads/operator-unrelated")
        unknown = self.task_root(task_id) / "operator" / "evidence.bin"
        unknown.parent.mkdir(parents=True)
        unknown.write_bytes(b"unknown directory bytes\x00\xff")
        telemetry = self.telemetry_path(task_id)
        self.assertTrue(telemetry.exists())

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--no-report",
                "--abandon",
            ),
            "integration-remove",
        )
        self.assert_task_git_resources_absent(task_id)
        self.assertFalse(telemetry.exists())
        self.assertEqual(unknown.read_bytes(), b"unknown directory bytes\x00\xff")
        self.assertEqual(
            self.ref_value("refs/heads/operator-unrelated"), unrelated_tip
        )

    def test_17_report_completes_before_cleanup_and_dev_flow_evidence_is_never_removed(self) -> None:
        task_id = "report-before-remove"
        lane = self.create_lane_after_task(task_id, "delivery")
        self.commit_lane(lane, path="delivered.txt")
        self.collect_lane(task_id, "delivery")
        accepted = self.accept_current(task_id)
        self.land(task_id)
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), accepted)

        record = self.root / ".agent_state" / "plans" / task_id / "ticket.md"
        evidence = self.root / ".agent_state" / "evidence" / task_id / "proof.bin"
        record.parent.mkdir(parents=True)
        evidence.parent.mkdir(parents=True)
        record.write_text("durable task record\n", encoding="utf-8")
        evidence.write_bytes(b"dev-flow evidence\x00\xff")
        output = self.root / ".agent_state" / "plans" / task_id / "artifacts"

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--output-dir",
                str(output),
            ),
            "integration-remove",
        )
        self.assertEqual(
            {path.name for path in output.iterdir()},
            {"orchestrate-report.json", "orchestrate-telemetry.jsonl"},
        )
        report = self.report_json(output)
        self.assertEqual(report["task_id"], task_id)
        self.assertGreater(report["counts"]["lifecycle_events"], 0)
        self.assertTrue((output / "orchestrate-telemetry.jsonl").read_bytes())
        self.assert_task_git_resources_absent(task_id)
        self.assertFalse(self.telemetry_path(task_id).exists())
        self.assertEqual(record.read_text(encoding="utf-8"), "durable task record\n")
        self.assertEqual(evidence.read_bytes(), b"dev-flow evidence\x00\xff")

    def test_18_remove_refuses_report_output_overlapping_exact_cleanup_inventory(self) -> None:
        failure_codes: list[str] = []
        for location in ("integration", "acceptance", "telemetry"):
            task_id = f"overlap-{location}"
            self.create_task(task_id)
            if location == "acceptance":
                self.mutation_success(
                    self.cli(
                        self.nested,
                        "acceptance",
                        "start",
                        "--task-id",
                        task_id,
                    ),
                    "acceptance-start",
                )
            output = {
                "integration": self.integration_path(task_id),
                "acceptance": self.acceptance_path(task_id),
                "telemetry": self.telemetry_path(task_id),
            }[location]
            telemetry_before = self.telemetry_path(task_id).read_bytes()
            resources_before = self.managed_state_snapshot()

            result = self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--output-dir",
                str(output),
            )

            with self.subTest(location=location):
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                payload = json.loads(result.stderr)
                self.assertEqual(payload["operation"], "integration-remove")
                failure_codes.append(payload["error"]["code"])
                self.assertIn(
                    payload["error"]["code"],
                    {"report_write_failed", "task_state_invalid"},
                )
                self.assertEqual(self.managed_state_snapshot(), resources_before)
                self.assertEqual(
                    self.telemetry_path(task_id).read_bytes(), telemetry_before
                )
                if output.is_dir():
                    self.assertFalse((output / "orchestrate-report.json").exists())
                    self.assertFalse(
                        (output / "orchestrate-telemetry.jsonl").exists()
                    )
        self.assertEqual(len(set(failure_codes)), 1)

    def test_19_abandon_unlinks_unregistered_lane_symlink_only_after_cleanup_preflight(self) -> None:
        task_id = "symlink-lane-abandon"
        self.create_task(task_id)
        lane = self.create_lane(task_id, "detached")
        self.mutation_success(
            self.cli(
                self.nested,
                "acceptance",
                "start",
                "--task-id",
                task_id,
            ),
            "acceptance-start",
        )
        run_git(self.root, "worktree", "remove", "--force", str(lane))
        self.assertFalse(lane.exists())

        external = self.root / "operator-external-lane-target"
        external.mkdir()
        sentinel = external / "evidence.bin"
        sentinel.write_bytes(b"external operator bytes\x00\xff")
        lane.symlink_to(external, target_is_directory=True)
        self.assertTrue(lane.is_symlink())
        self.assertTrue(self.integration_path(task_id).is_dir())
        self.assertTrue(self.acceptance_path(task_id).is_dir())

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--no-report",
                "--abandon",
            ),
            "integration-remove",
        )

        self.assertFalse(lane.is_symlink())
        self.assertFalse(lane.exists())
        self.assertEqual(sentinel.read_bytes(), b"external operator bytes\x00\xff")
        self.assert_task_git_resources_absent(task_id)
        self.assertFalse(self.integration_path(task_id).exists())
        self.assertFalse(self.acceptance_path(task_id).exists())
        self.assertFalse(self.telemetry_path(task_id).exists())

    def test_20_remove_report_projects_terminal_span_without_durable_success_event(self) -> None:
        task_id = "projected-terminal-report"
        self.create_task(task_id)
        telemetry_before = self.telemetry_path(task_id).read_bytes()
        events_before = [
            json.loads(line) for line in telemetry_before.decode("utf-8").splitlines()
        ]
        self.assertFalse(
            any(event["operation"] == "integration-remove" for event in events_before)
        )
        output = self.root / "terminal-report"

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--output-dir",
                str(output),
            ),
            "integration-remove",
            warnings=True,
        )

        raw = (output / "orchestrate-telemetry.jsonl").read_bytes()
        self.assertEqual(raw, telemetry_before)
        durable_events = [
            json.loads(line) for line in raw.decode("utf-8").splitlines()
        ]
        self.assertFalse(
            any(
                event["operation"] == "integration-remove"
                and event["outcome"] == "success"
                for event in durable_events
            )
        )
        report = self.report_json(output)
        self.assertEqual(
            report["counts"]["lifecycle_events"], len(durable_events) + 1
        )
        task_spans = [
            entry
            for entry in report["timeline"]
            if entry["type"] == "span"
            and entry["kind"] == "task"
            and entry["identity"] == task_id
        ]
        self.assertEqual(len(task_spans), 1)
        self.assertEqual(task_spans[0]["outcome"], "success")
        self.assertEqual(task_spans[0]["ended_at"], report["generated_at"])
        self.assert_task_git_resources_absent(task_id)
        self.assertFalse(self.telemetry_path(task_id).exists())

    def test_21_remove_refuses_external_symlink_output_resolving_inside_cleanup_worktree(
        self,
    ) -> None:
        for relation in ("equal", "descendant"):
            task_id = f"resolved-output-{relation}"
            self.create_task(task_id)
            self.mutation_success(
                self.cli(
                    self.nested,
                    "acceptance",
                    "start",
                    "--task-id",
                    task_id,
                ),
                "acceptance-start",
            )
            acceptance = self.acceptance_path(task_id)
            target_output = (
                acceptance
                if relation == "equal"
                else acceptance / "operator-report-artifacts"
            )
            target_output.mkdir(exist_ok=True)
            artifacts = {
                target_output / "orchestrate-report.json": b"existing-report\x00\xff",
                target_output / "orchestrate-telemetry.jsonl": b"existing-raw\x00\xff",
            }
            for path, content in artifacts.items():
                path.write_bytes(content)

            output = self.root / f"external-report-link-{relation}"
            output.symlink_to(target_output, target_is_directory=True)
            symlink_target = output.readlink()
            resources_before = self.managed_state_snapshot()

            result = self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--output-dir",
                str(output),
            )

            with self.subTest(relation=relation):
                self.operational_failure(
                    result,
                    "integration-remove",
                    "report_write_failed",
                )
                self.assertEqual(self.managed_state_snapshot(), resources_before)
                self.assertTrue(acceptance.is_dir())
                self.assertTrue(output.is_symlink())
                self.assertEqual(output.readlink(), symlink_target)
                self.assertTrue(output.is_dir(), "refusal must not leave a dangling link")
                for path, content in artifacts.items():
                    self.assertEqual(path.read_bytes(), content)


if __name__ == "__main__":
    raise SystemExit("Run with: python3 -m unittest tests.test_orchestrate_lifecycle")
