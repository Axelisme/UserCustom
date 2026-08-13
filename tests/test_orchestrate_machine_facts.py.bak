"""Frozen machine-facts Contract tests.

These pins retire when the timing CLI and its retired report fields are removed
and ``status --task-id`` derives collect rounds from Git history rather than
requiring hand-counted task prose.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from tests._orchestrate_cli_support import (
    OrchestrateCliRepositoryTestCase,
    run_git,
)


class MachineFactsContractTests(OrchestrateCliRepositoryTestCase):
    """Exercise the admitted observables through the shipped subprocess."""

    def task_root(self, task_id: str) -> Path:
        return self.root / ".agent_state" / "worktrees" / task_id

    def lane_path(self, task_id: str, lane_id: str) -> Path:
        return self.task_root(task_id) / "lanes" / lane_id

    def create_task(self, task_id: str) -> None:
        self.mutation_success(
            self.cli(self.nested, "integration", "create", "--task-id", task_id),
            "integration-create",
        )

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

    def lane_commit(
        self,
        task_id: str,
        lane_id: str,
        path: str,
        subject: str,
        *,
        contract: bool = False,
        amend_frozen: bool = False,
    ) -> None:
        lane = self.lane_path(task_id, lane_id)
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{subject}\n", encoding="utf-8")
        run_git(lane, "add", path)
        message_file = self.root / f"{task_id}-{lane_id}-{path.replace('/', '-')}.message"
        message_file.write_text(subject, encoding="utf-8")
        argv = [
            "lane",
            "commit",
            "--task-id",
            task_id,
            "--lane-id",
            lane_id,
            "--message-file",
            str(message_file),
        ]
        if contract:
            argv.append("--contract")
        elif amend_frozen:
            argv.append("--amend-frozen")
        payload = self.success(self.cli(lane, *argv))
        self.assertEqual(payload["operation"], "lane-commit")

    def collect(self, task_id: str, lane_id: str, ticket: str) -> None:
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "collect",
                "--task-id",
                task_id,
                "--lane-id",
                lane_id,
                "--ticket",
                ticket,
            ),
            "integration-collect",
        )

    def sync_and_commit(self, task_id: str, lane_id: str) -> None:
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "sync",
                "--task-id",
                task_id,
                "--lane-id",
                lane_id,
            ),
            "lane-sync",
            warnings=True,
        )
        message_file = self.root / f"{task_id}-{lane_id}-sync.message"
        message_file.write_text(
            f"Sync integration into lane {lane_id}\n", encoding="utf-8"
        )
        payload = self.success(
            self.cli(
                self.lane_path(task_id, lane_id),
                "lane",
                "commit",
                "--task-id",
                task_id,
                "--lane-id",
                lane_id,
                "--message-file",
                str(message_file),
                "--amend-frozen",
            )
        )
        self.assertEqual(payload["operation"], "lane-commit")

    def status(self, task_id: str) -> dict[str, Any]:
        payload = self.success(
            self.cli(self.nested, "status", "--task-id", task_id)
        )
        self.assertEqual(payload["operation"], "status")
        return payload

    def report(self, task_id: str, output_dir: Path) -> dict[str, Any]:
        self.mutation_success(
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
        report = json.loads(
            (output_dir / "orchestrate-report.json").read_text(encoding="utf-8")
        )
        self.assertIsInstance(report, dict)
        return report

    @classmethod
    def objects(cls, value: object) -> Iterator[dict[str, object]]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from cls.objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls.objects(child)

    def assert_no_retired_timing_fields(self, value: object) -> None:
        for item in self.objects(value):
            self.assertNotIn("recorded_seconds", item)
            self.assertNotIn("paused_seconds", item)

    def test_timing_pause_is_rejected_as_an_unknown_command(self) -> None:
        task_id = "timing-removed"
        self.create_task(task_id)

        result = self.cli(
            self.nested,
            "timing",
            "pause",
            "--task-id",
            task_id,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("timing", result.stderr)

    def test_generated_report_keeps_wall_clock_fields_only(self) -> None:
        task_id = "wall-clock-report"
        self.create_task(task_id)
        report = self.report(task_id, self.root / "report")
        raw = [
            json.loads(line)
            for line in (self.root / "report" / "orchestrate-telemetry.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

        self.assertIn("timing", report)
        self.assertIn("wall_seconds", report["timing"])
        self.assertTrue(
            any("elapsed_seconds" in item for item in self.objects(report))
        )
        self.assert_no_retired_timing_fields(report)
        self.assert_no_retired_timing_fields(raw)

    def test_status_emits_empty_collect_round_projection_for_new_task(self) -> None:
        task_id = "collect-rounds-empty"
        self.create_task(task_id)
        self.assertEqual(self.status(task_id).get("collect_rounds"), {})

    def test_status_derives_sorted_production_collect_rounds_per_ticket(self) -> None:
        task_id = "collect-rounds"
        lane_id = "writer"
        self.create_task(task_id)
        self.create_lane(task_id, lane_id)

        self.lane_commit(task_id, lane_id, "production-one.txt", "production one")
        self.collect(task_id, lane_id, "t1")

        self.lane_commit(
            task_id,
            lane_id,
            "contract-only.txt",
            "contract only",
            contract=True,
        )
        self.collect(task_id, lane_id, "contract-only")

        self.lane_commit(task_id, lane_id, "production-two.txt", "production two")
        self.collect(task_id, lane_id, "t1")
        self.lane_commit(task_id, lane_id, "production-three.txt", "production three")
        self.collect(task_id, lane_id, "t2")

        projection = self.status(task_id).get("collect_rounds")
        self.assertIsInstance(projection, dict)
        assert isinstance(projection, dict)
        self.assertEqual(projection, {"t1": 2, "t2": 1})
        self.assertEqual(list(projection), ["t1", "t2"])
        self.assertNotIn("contract-only", projection)

    def test_contract_and_amend_frozen_contract_rounds_remain_excluded(self) -> None:
        task_id = "collect-rounds-contract-amendment"
        lane_id = "writer"
        self.create_task(task_id)
        self.create_lane(task_id, lane_id)

        self.lane_commit(task_id, lane_id, "production.txt", "production")
        self.collect(task_id, lane_id, "production")
        self.lane_commit(
            task_id,
            lane_id,
            "contract.txt",
            "contract freeze",
            contract=True,
        )
        self.collect(task_id, lane_id, "contract-only")
        self.lane_commit(
            task_id,
            lane_id,
            "contract.txt",
            "contract amendment",
            amend_frozen=True,
        )
        self.collect(task_id, lane_id, "contract-amendment")

        projection = self.status(task_id)["collect_rounds"]
        self.assertEqual(projection, {"production": 1})
        self.assertNotIn("contract-only", projection)
        self.assertNotIn("contract-amendment", projection)

    def test_sync_carriage_of_integrated_work_is_not_a_new_round(self) -> None:
        task_id = "collect-rounds-sync-carriage"
        lane_id = "writer"
        self.create_task(task_id)
        self.create_lane(task_id, lane_id)

        self.lane_commit(task_id, lane_id, "production.txt", "production")
        self.collect(task_id, lane_id, "production")
        self.sync_and_commit(task_id, lane_id)
        self.collect(task_id, lane_id, "sync-carriage")

        projection = self.status(task_id)["collect_rounds"]
        self.assertEqual(projection, {"production": 1})
        self.assertNotIn("sync-carriage", projection)

    def test_two_lane_sync_of_integrated_work_is_not_a_new_round(self) -> None:
        task_id = "collect-rounds-two-lane-sync"
        lane_a = "lane-a"
        lane_b = "lane-b"
        self.create_task(task_id)
        self.create_lane(task_id, lane_a)
        self.create_lane(task_id, lane_b)

        self.lane_commit(
            task_id,
            lane_b,
            "lane-b-contract.txt",
            "lane B contract",
            contract=True,
        )
        self.collect(task_id, lane_b, "lane-b-contract")
        self.lane_commit(task_id, lane_a, "lane-a-production.txt", "lane A production")
        self.collect(task_id, lane_a, "lane-a-production")
        self.sync_and_commit(task_id, lane_b)
        self.collect(task_id, lane_b, "lane-b-sync-carriage")

        projection = self.status(task_id)["collect_rounds"]
        self.assertEqual(projection, {"lane-a-production": 1})
        self.assertNotIn("lane-b-sync-carriage", projection)
