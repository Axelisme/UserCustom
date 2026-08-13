"""Frozen Contract tests for composed collect-round history.

This pin retires when collect-round derivation ignores Contract amendments
carried together with already-integrated production during a lane sync.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests._orchestrate_cli_support import (
    OrchestrateCliRepositoryTestCase,
    run_git,
)


class CollectRoundCompositionContractTests(OrchestrateCliRepositoryTestCase):
    """Exercise the composed two-lane history through shipped subprocesses."""

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
        message_file = self.root / (
            f"{task_id}-{lane_id}-{path.replace('/', '-')}.message"
        )
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

    def test_contract_amendment_composed_with_sync_is_not_a_new_round(self) -> None:
        task_id = "collect-rounds-contract-amendment-composition"
        lane_a = "lane-a"
        lane_b = "lane-b"
        self.create_task(task_id)
        self.create_lane(task_id, lane_a)
        self.create_lane(task_id, lane_b)

        self.lane_commit(
            task_id,
            lane_b,
            "lane-b-contract.txt",
            "lane B contract freeze",
            contract=True,
        )
        self.collect(task_id, lane_b, "lane-b-contract")
        self.lane_commit(
            task_id,
            lane_b,
            "lane-b-contract.txt",
            "lane B contract amendment",
            amend_frozen=True,
        )
        self.lane_commit(
            task_id,
            lane_a,
            "lane-a-production.txt",
            "lane A production",
        )
        self.collect(task_id, lane_a, "lane-a-production")
        self.sync_and_commit(task_id, lane_b)
        self.collect(task_id, lane_b, "lane-b-sync")

        projection = self.status(task_id)["collect_rounds"]
        self.assertEqual(projection, {"lane-a-production": 1})
        self.assertNotIn("lane-b-contract", projection)
        self.assertNotIn("lane-b-sync", projection)
