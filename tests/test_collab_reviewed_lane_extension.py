from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.test_collab_op_extension import (
    git,
    invoke as invoke_extension,
    seed_managed_task,
    seed_repository,
)

ROOT = Path(__file__).resolve().parents[1]
RPC_MOCK = ROOT / "tests/collab_rpc_mock_extension.ts"
SCRIPT_HARNESS = ROOT / "tests/collab_workflow_script_harness.mjs"
TOOL = "collab_run_reviewed_lane"


def invoke(repository: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Reuse the shared extension harness with the reviewed-lane RPC support extension."""
    return invoke_extension(repository, request, support_extension=RPC_MOCK)


def seed_profiles(repository: Path) -> None:
    profiles = repository / ".pi/agents"
    profiles.mkdir(parents=True)
    (profiles / "collab-implementer.md").write_text(
        "---\nname: collab-implementer\ntools: read, write, edit, bash\n"
        "defaultContext: fresh\n---\nImplement the bounded brief.\n",
        encoding="utf-8",
    )
    (profiles / "collab-acceptor.md").write_text(
        "---\nname: collab-acceptor\ntools: read, bash\n"
        "defaultContext: fresh\n---\nReview the bounded brief.\n",
        encoding="utf-8",
    )
    git(repository, "add", ".pi/agents")
    git(repository, "commit", "-m", "test profiles")


def valid_request(capture: Path, **overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "tool": TOOL,
        "task_id": "demo",
        "ticket_id": "T001",
        "lane_id": "writer-1",
        "worker_brief": "Implement ticket T001 within the delegated authority.",
        "review_brief": "Review delegated acceptance criterion one read-only.",
        "correction_budget": 0,
        "__rpc": {"mode": "available", "capture": str(capture)},
    }
    request.update(overrides)
    return request


class CollabReviewedLaneExtensionTests(unittest.TestCase):
    def managed_repository(self, base: Path) -> tuple[Path, dict[str, str]]:
        repository, _ = seed_repository(base)
        seed_profiles(repository)
        return repository, seed_managed_task(repository)

    def launch_case(
        self,
        base: Path,
        *,
        capture_name: str = "rpc.jsonl",
        **overrides: Any,
    ) -> tuple[Path, dict[str, str], Path, dict[str, Any]]:
        repository, expected = self.managed_repository(base)
        capture = base / capture_name
        observed = invoke(repository, valid_request(capture, **overrides))
        return repository, expected, capture, observed

    def test_shipped_registration_exposes_narrow_public_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, _, observed = self.launch_case(base)

        self.assertIn(TOOL, observed["tools"])
        schema = observed["schemas"][TOOL]["parameters"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {"task_id", "ticket_id", "lane_id", "worker_brief", "review_brief", "correction_budget"},
        )
        self.assertEqual(schema["properties"]["correction_budget"]["type"], "integer")
        self.assertEqual(schema["properties"]["correction_budget"]["minimum"], 0)
        self.assertEqual(
            schema["properties"]["correction_budget"]["maximum"],
            9007199254740991,
        )
        self.assertEqual(schema["properties"]["worker_brief"]["minLength"], 1)
        self.assertEqual(schema["properties"]["review_brief"]["minLength"], 1)

    def test_valid_launch_returns_only_public_receipt_and_uses_rpc_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base)
            rpc = json.loads(capture.read_text(encoding="utf-8").strip())

        self.assertFalse(observed["is_error"], observed)
        self.assertEqual(set(observed["result"]), {"workflow_id", "async_id", "async_dir"})
        self.assertEqual(observed["result"]["async_id"], "async-test-id")
        self.assertEqual(observed["result"]["async_dir"], "/tmp/pi-subagents/async-test-id")
        self.assertEqual(rpc["version"], 1)
        self.assertEqual(rpc["method"], "spawn")
        self.assertEqual(set(rpc["params"]), {"workflowScript", "async"})
        self.assertIs(rpc["params"]["async"], True)
        self.assertIn(expected["lane"], rpc["params"]["workflowScript"])

    def test_receipt_projects_pi_subagents_run_id_when_distinct_from_async_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, _, observed = self.launch_case(
                base,
                __rpc={
                    "mode": "available",
                    "capture": str(base / "rpc.jsonl"),
                    "runId": "workflow-owned-id",
                },
            )

        self.assertFalse(observed["is_error"], observed)
        self.assertEqual(observed["result"]["workflow_id"], "workflow-owned-id")
        self.assertEqual(observed["result"]["async_id"], "async-test-id")

    def test_receipt_uses_correlated_async_id_only_when_run_id_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, _, observed = self.launch_case(
                base,
                __rpc={
                    "mode": "available",
                    "capture": str(base / "rpc.jsonl"),
                    "omitRunId": True,
                },
            )

        self.assertFalse(observed["is_error"], observed)
        self.assertEqual(observed["result"]["workflow_id"], "async-test-id")
        self.assertEqual(observed["result"]["async_id"], "async-test-id")

    def test_spawned_workflow_uses_fresh_exact_lane_typed_children_and_structured_control(self) -> None:
        worker = {
            "outcome": "COMPLETED",
            "validation": [{"check": "behavior", "result": "PASSED", "summary": "works"}],
            "residualRisks": ["bounded risk"],
        }
        reviewer = {"verdict": "PASS", "outOfEnvelopeFindings": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base)
            self.assertFalse(observed["is_error"], observed)
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps([worker, reviewer])],
                capture_output=True,
                text=True,
                check=True,
            )
            execution = json.loads(run.stdout)

        self.assertEqual(execution["result"]["outcome"], "REVIEWED")
        self.assertEqual([call["key"] for call in execution["calls"]], ["impl-0", "review-0"])
        self.assertEqual(
            [call["options"]["agent"] for call in execution["calls"]],
            ["collab-implementer", "collab-acceptor"],
        )
        for call in execution["calls"]:
            options = call["options"]
            self.assertEqual(
                set(options), {"agent", "cwd", "worktree", "context", "task", "outputSchema"}
            )
            self.assertEqual(options["cwd"], expected["lane"])
            self.assertIs(options["worktree"], False)
            self.assertEqual(options["context"], "fresh")
            self.assertIsInstance(options["outputSchema"], dict)
            self.assertNotIn("model", options)
            self.assertNotIn("thinking", options)
            self.assertNotIn("runId", options)

    def test_terminal_branches_are_typed_and_zero_budget_is_terminal(self) -> None:
        completed = {"outcome": "COMPLETED", "validation": [], "residualRisks": []}
        cases = [
            ([{"outcome": "BLOCKED", "blocker": "blocked"}], {"outcome": "BLOCKED", "blocker": "blocked"}, 1),
            ([{"outcome": "NEEDS_DECISION", "decision": {"why": "why", "question": "question"}}], {"outcome": "NEEDS_DECISION", "why": "why", "question": "question"}, 1),
            ([completed, {"verdict": "NEEDS_DECISION", "decision": {"why": "review why", "question": "review question"}}], {"outcome": "NEEDS_DECISION", "why": "review why", "question": "review question"}, 2),
            ([completed, {"verdict": "BLOCKED", "blockers": [{"location": "x", "reason": "y", "fix": "z"}]}], {"outcome": "CORRECTION_BUDGET_EXHAUSTED", "blockers": [{"location": "x", "reason": "y", "fix": "z"}]}, 2),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base)
            self.assertFalse(observed["is_error"], observed)
            for steps, expected, calls in cases:
                with self.subTest(expected=expected["outcome"]):
                    run = subprocess.run(
                        ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    execution = json.loads(run.stdout)
                    self.assertEqual(execution["result"], expected)
                    self.assertEqual(len(execution["calls"]), calls)

    def test_budget_one_runs_one_correction_and_rereview_with_current_blockers(self) -> None:
        worker = {
            "outcome": "COMPLETED",
            "validation": [{"check": "correction", "result": "PASSED", "summary": "corrected"}],
            "residualRisks": ["latest risk"],
        }
        blocked = {
            "verdict": "BLOCKED",
            "blockers": [{"location": "current.ts", "reason": "missing behavior", "fix": "add behavior"}],
            "outOfEnvelopeFindings": [],
        }
        passed = {"verdict": "PASS", "outOfEnvelopeFindings": [{"location": "scope", "evidence": "finding"}]}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            execution = json.loads(
                subprocess.run(
                    ["node", str(SCRIPT_HARNESS), str(capture), json.dumps([worker, blocked, worker, passed])],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )

        self.assertEqual(execution["result"], {
            "outcome": "REVIEWED",
            "validation": worker["validation"],
            "residualRisks": worker["residualRisks"],
            "outOfEnvelopeFindings": passed["outOfEnvelopeFindings"],
        })
        self.assertEqual([call["key"] for call in execution["calls"]], ["impl-0", "review-0", "impl-1", "review-1"])
        self.assertEqual([call["options"]["cwd"] for call in execution["calls"]], [expected["lane"]] * 4)
        self.assertIn('"location":"current.ts"', execution["calls"][2]["options"]["task"])
        self.assertIn("missing behavior", execution["calls"][2]["options"]["task"])
        self.assertNotIn("ignored free-form", execution["calls"][2]["options"]["task"])
        rereview = execution["calls"][3]
        self.assertEqual(rereview["key"], "review-1")
        self.assertEqual(rereview["options"]["agent"], "collab-acceptor")
        self.assertEqual(
            set(rereview["options"]),
            {"agent", "cwd", "worktree", "context", "task", "outputSchema"},
        )
        self.assertEqual(rereview["options"]["cwd"], expected["lane"])
        self.assertIs(rereview["options"]["worktree"], False)
        self.assertEqual(rereview["options"]["context"], "fresh")
        self.assertIsInstance(rereview["options"]["outputSchema"], dict)

    def test_multiple_budget_rounds_consume_one_slot_per_blocked_review(self) -> None:
        completed = {"outcome": "COMPLETED", "validation": [], "residualRisks": []}
        blocked = {"verdict": "BLOCKED", "blockers": [{"location": "x", "reason": "y", "fix": "z"}]}
        passed = {"verdict": "PASS", "outOfEnvelopeFindings": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base, correction_budget=2)
            self.assertFalse(observed["is_error"], observed)
            execution = json.loads(
                subprocess.run(
                    ["node", str(SCRIPT_HARNESS), str(capture), json.dumps([completed, blocked, completed, blocked, completed, passed])],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )

        self.assertEqual(execution["result"]["outcome"], "REVIEWED")
        self.assertEqual([call["key"] for call in execution["calls"]], ["impl-0", "review-0", "impl-1", "review-1", "impl-2", "review-2"])

    def test_every_correction_terminal_branch_stops_at_the_current_round(self) -> None:
        completed = {"outcome": "COMPLETED", "validation": [], "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "blockers": [{"location": "lane.ts", "reason": "expectation", "fix": "correct it"}],
            "outOfEnvelopeFindings": [],
        }
        cases = [
            (
                1,
                [completed, blocked, {"outcome": "BLOCKED", "blocker": "correction blocked"}],
                {"outcome": "BLOCKED", "blocker": "correction blocked"},
                ["impl-0", "review-0", "impl-1"],
            ),
            (
                1,
                [completed, blocked, {"outcome": "NEEDS_DECISION", "decision": {"why": "correction why", "question": "correction question"}}],
                {"outcome": "NEEDS_DECISION", "why": "correction why", "question": "correction question"},
                ["impl-0", "review-0", "impl-1"],
            ),
            (
                1,
                [completed, blocked, completed, {"verdict": "NEEDS_DECISION", "decision": {"why": "rereview why", "question": "rereview question"}}],
                {"outcome": "NEEDS_DECISION", "why": "rereview why", "question": "rereview question"},
                ["impl-0", "review-0", "impl-1", "review-1"],
            ),
            (
                1,
                [completed, blocked, completed, blocked],
                {"outcome": "CORRECTION_BUDGET_EXHAUSTED", "blockers": blocked["blockers"]},
                ["impl-0", "review-0", "impl-1", "review-1"],
            ),
        ]
        for budget, steps, expected_result, expected_keys in cases:
            with self.subTest(expected=expected_result["outcome"]), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                _, _, capture, observed = self.launch_case(base, correction_budget=budget)
                self.assertFalse(observed["is_error"], observed)
                execution = json.loads(
                    subprocess.run(
                        ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                        capture_output=True,
                        text=True,
                        check=True,
                    ).stdout
                )
                self.assertEqual(execution["result"], expected_result)
                self.assertEqual([call["key"] for call in execution["calls"]], expected_keys)
                for call in execution["calls"]:
                    self.assertEqual(
                        set(call["options"]),
                        {"agent", "cwd", "worktree", "context", "task", "outputSchema"},
                    )
                    self.assertIs(call["options"]["worktree"], False)
                    self.assertEqual(call["options"]["context"], "fresh")
                    self.assertIsInstance(call["options"]["outputSchema"], dict)

    def test_invalid_inputs_never_request_spawn(self) -> None:
        invalid = [
            {"task_id": "BAD/TASK"},
            {"ticket_id": "BAD TICKET"},
            {"ticket_id": "T" * 65},
            {"lane_id": "integration"},
            {"worker_brief": "   "},
            {"review_brief": "\n\t"},
            {"correction_budget": -1},
            {"correction_budget": 1.5},
            {"correction_budget": 9007199254740992},
            {"correction_budget": "1"},
        ]
        for index, override in enumerate(invalid):
            with self.subTest(override=override), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                _, _, capture, observed = self.launch_case(
                    base,
                    capture_name=f"rpc-{index}.jsonl",
                    **override,
                )
                self.assertTrue(observed["is_error"], observed)
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse(capture.exists())

    def test_arbitrary_lane_placement_profile_gap_and_rpc_gaps_prevent_spawn(self) -> None:
        cases = [
            "moved-lane",
            "disabled-settings",
            "missing-spawn",
            "unsupported-version",
        ]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, expected = self.managed_repository(base)
                if case == "moved-lane":
                    git(repository, "worktree", "move", expected["lane"], str(base / "arbitrary-lane"))
                if case == "disabled-settings":
                    lane_settings = Path(expected["lane"]) / ".pi/settings.json"
                    lane_settings.write_text(
                        json.dumps(
                            {
                                "subagents": {
                                    "agentOverrides": {
                                        "collab-acceptor": {"disabled": True}
                                    }
                                }
                            }
                        ),
                        encoding="utf-8",
                    )
                capture = base / "rpc.jsonl"
                mode = case if case in {"missing-spawn", "unsupported-version"} else "available"
                observed = invoke(
                    repository,
                    valid_request(capture, __rpc={"mode": mode, "capture": str(capture)}),
                )
                self.assertTrue(observed["is_error"], observed)
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse(capture.exists())


if __name__ == "__main__":
    unittest.main()
