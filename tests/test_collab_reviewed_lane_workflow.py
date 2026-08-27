from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests/collab_reviewed_lane_workflow_harness.mjs"
WORKFLOW = ROOT / "home/.claude/workflows/collab-reviewed-lane.js"
VALID_INPUT = {
    "lane": "/tmp/collab-lane",
    "startingHead": "0123456789abcdef",
    "ticket": "/tmp/ticket.md",
    "envelope": None,
    "correctionBudget": 0,
    "operatorNotes": None,
}


class CollabReviewedLaneWorkflowTests(unittest.TestCase):
    def run_workflow(
        self,
        workflow: Path,
        args: object,
        *,
        scenario: str = "happy",
    ) -> dict[str, Any]:
        result = subprocess.run(
            [
                "node",
                str(HARNESS),
                str(workflow),
                json.dumps(args),
                scenario,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def run_installed(
        self,
        args: object = VALID_INPUT,
        *,
        scenario: str = "happy",
    ) -> dict[str, Any]:
        return self.run_workflow(WORKFLOW, args, scenario=scenario)

    def assert_dispatch_shape(
        self,
        output: dict[str, Any],
        expected_roles: list[str],
    ) -> None:
        invocations = output["invocations"]
        self.assertEqual(output["calls"], len(expected_roles))
        self.assertEqual(len(invocations), len(expected_roles))
        for invocation, expected_role in zip(invocations, expected_roles):
            self.assertIsInstance(invocation, list)
            self.assertEqual(len(invocation), 2)
            prompt, options = invocation
            self.assertIsInstance(prompt, str)
            self.assertTrue(prompt.strip())
            self.assertIsInstance(options, dict)
            self.assertEqual(set(options), {"agentType", "schema"})
            self.assertEqual(options["agentType"], expected_role)
            self.assertIsInstance(options["schema"], dict)

    def assert_terminal(
        self,
        output: dict[str, Any],
        *,
        execution: str,
        outcome: str | None,
        stopped_at: str,
        stop_reason: str,
        calls: int,
        corrections_used: int = 0,
        expected_roles: list[str] | None = None,
    ) -> dict[str, Any]:
        result = output["result"]
        self.assertEqual(result["type"], "collab-reviewed-lane-result")
        self.assertEqual(result["execution"], execution)
        self.assertEqual(result["outcome"], outcome)
        self.assertEqual(result["stoppedAt"], stopped_at)
        self.assertEqual(result["stopReason"], stop_reason)
        self.assertEqual(result["correctionsUsed"], corrections_used)
        if expected_roles is None:
            expected_roles = ["collab-implementer"] if calls else []
            expected_roles.extend(["collab-acceptor"] * max(calls - 1, 0))
        self.assert_dispatch_shape(output, expected_roles)
        return result

    def test_valid_input_dispatches_worker_then_fresh_reviewer(self) -> None:
        output = self.run_installed()

        result = self.assert_terminal(
            output,
            execution="COMPLETED",
            outcome="REVIEWED",
            stopped_at="REVIEW",
            stop_reason="REVIEW_PASS",
            calls=2,
        )
        self.assertEqual(
            [invocation[1]["agentType"] for invocation in output["invocations"]],
            ["collab-implementer", "collab-acceptor"],
        )
        self.assertEqual(result["workerResult"]["outcome"], "COMPLETED")
        self.assertEqual(result["reviewResult"]["verdict"], "PASS")
        for prompt, options in output["invocations"]:
            self.assertIn(VALID_INPUT["lane"], prompt)
            self.assertIn(VALID_INPUT["ticket"], prompt)
            self.assertIsInstance(options["schema"], dict)

    def test_budget_one_dispatches_one_correction_and_fresh_rereview(self) -> None:
        args = {**VALID_INPUT, "correctionBudget": 1}

        output = self.run_installed(args, scenario="correction-rereview-pass")

        result = self.assert_terminal(
            output,
            execution="COMPLETED",
            outcome="REVIEWED",
            stopped_at="REREVIEW",
            stop_reason="REVIEW_PASS",
            calls=4,
            corrections_used=1,
            expected_roles=[
                "collab-implementer",
                "collab-acceptor",
                "collab-implementer",
                "collab-acceptor",
            ],
        )
        self.assertEqual(
            output["phases"],
            ["Validate", "Implement", "Review", "Correct", "Rereview"],
        )
        self.assertNotIn("validation", result["workerResult"])
        self.assertIn("residualRisks", result["workerResult"])
        self.assertEqual(result["reviewResult"]["verdict"], "PASS")
        self.assertNotEqual(
            output["invocations"][1][0], output["invocations"][3][0]
        )

        for prompt, _options in output["invocations"]:
            self.assertIn(VALID_INPUT["lane"], prompt)
            self.assertIn(VALID_INPUT["startingHead"], prompt)
            self.assertIn(VALID_INPUT["ticket"], prompt)
            self.assertIn('"envelope":null', prompt)
            self.assertIn('"correctionBudget":1', prompt)

        correction_prompt = output["invocations"][2][0]
        for blocker_text in (
            "reviewed behavior",
            "The protected lane does not satisfy one supplied expectation.",
            "Correct the bounded behavior before another review.",
        ):
            self.assertIn(blocker_text, correction_prompt)

    def test_correction_blocked_or_decision_stops_before_rereview(self) -> None:
        args = {**VALID_INPUT, "correctionBudget": 1}
        for scenario, outcome, stop_reason in (
            ("correction-worker-blocked", "BLOCKED", "WORKER_BLOCKED"),
            ("correction-worker-needs-decision", "NEEDS_DECISION", "DECISION_REQUIRED"),
        ):
            with self.subTest(scenario=scenario):
                output = self.run_installed(args, scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="COMPLETED",
                    outcome=outcome,
                    stopped_at="CORRECT",
                    stop_reason=stop_reason,
                    calls=3,
                    corrections_used=1,
                    expected_roles=[
                        "collab-implementer",
                        "collab-acceptor",
                        "collab-implementer",
                    ],
                )
                self.assertEqual(result["workerResult"]["outcome"], outcome)
                self.assertEqual(result["reviewResult"]["verdict"], "BLOCKED")
                self.assertEqual(
                    output["phases"], ["Validate", "Implement", "Review", "Correct"]
                )

    def test_correction_failures_preserve_initial_canonical_results(self) -> None:
        args = {**VALID_INPUT, "correctionBudget": 1}
        for scenario, code in (
            ("correction-null", "NULL_CHILD_RESULT"),
            ("correction-runtime-error", "CHILD_RUNTIME_FAILURE"),
            ("correction-capability-failure", "CHILD_RUNTIME_FAILURE"),
            ("correction-invalid", "INVALID_CHILD_RESULT"),
        ):
            with self.subTest(scenario=scenario):
                output = self.run_installed(args, scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="RUNTIME_GAP",
                    outcome=None,
                    stopped_at="CORRECT",
                    stop_reason="CAPABILITY_UNAVAILABLE",
                    calls=3,
                    corrections_used=1,
                    expected_roles=[
                        "collab-implementer",
                        "collab-acceptor",
                        "collab-implementer",
                    ],
                )
                self.assertEqual(result["error"], {"code": code})
                self.assertEqual(result["workerResult"]["outcome"], "COMPLETED")
                self.assertEqual(result["reviewResult"]["verdict"], "BLOCKED")
                self.assertEqual(
                    result["reviewResult"]["blockers"][0]["where"],
                    "reviewed behavior",
                )
                self.assertEqual(
                    output["phases"], ["Validate", "Implement", "Review", "Correct"]
                )

        output = self.run_installed(args, scenario="correction-interrupt")
        result = self.assert_terminal(
            output,
            execution="INTERRUPTED",
            outcome=None,
            stopped_at="CORRECT",
            stop_reason="CHILD_INTERRUPTED",
            calls=3,
            corrections_used=1,
            expected_roles=[
                "collab-implementer",
                "collab-acceptor",
                "collab-implementer",
            ],
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["workerResult"]["outcome"], "COMPLETED")
        self.assertEqual(result["reviewResult"]["verdict"], "BLOCKED")

    def test_rereview_terminals_are_finite_and_keep_latest_canonical_results(self) -> None:
        args = {**VALID_INPUT, "correctionBudget": 1}
        for scenario, outcome, stop_reason, verdict in (
            ("correction-rereview-pass", "REVIEWED", "REVIEW_PASS", "PASS"),
            (
                "correction-rereview-needs-decision",
                "NEEDS_DECISION",
                "DECISION_REQUIRED",
                "NEEDS_DECISION",
            ),
            (
                "correction-rereview-blocked",
                "BLOCKED",
                "CORRECTION_BUDGET_EXHAUSTED",
                "BLOCKED",
            ),
        ):
            with self.subTest(scenario=scenario):
                output = self.run_installed(args, scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="COMPLETED",
                    outcome=outcome,
                    stopped_at="REREVIEW",
                    stop_reason=stop_reason,
                    calls=4,
                    corrections_used=1,
                    expected_roles=[
                        "collab-implementer",
                        "collab-acceptor",
                        "collab-implementer",
                        "collab-acceptor",
                    ],
                )
                self.assertNotIn("validation", result["workerResult"])
                self.assertEqual(result["reviewResult"]["verdict"], verdict)
                if verdict == "BLOCKED":
                    self.assertEqual(
                        result["reviewResult"]["blockers"][0]["where"],
                        "rereviewed behavior",
                    )
                self.assertEqual(output["calls"], 4)

    def test_rereview_failures_preserve_corrected_worker_and_initial_review(self) -> None:
        args = {**VALID_INPUT, "correctionBudget": 1}
        for scenario, code in (
            ("rereview-null", "NULL_CHILD_RESULT"),
            ("rereview-runtime-error", "CHILD_RUNTIME_FAILURE"),
            ("rereview-capability-failure", "CHILD_RUNTIME_FAILURE"),
            ("rereview-invalid", "INVALID_CHILD_RESULT"),
        ):
            with self.subTest(scenario=scenario):
                output = self.run_installed(args, scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="RUNTIME_GAP",
                    outcome=None,
                    stopped_at="REREVIEW",
                    stop_reason="CAPABILITY_UNAVAILABLE",
                    calls=4,
                    corrections_used=1,
                    expected_roles=[
                        "collab-implementer",
                        "collab-acceptor",
                        "collab-implementer",
                        "collab-acceptor",
                    ],
                )
                self.assertEqual(result["error"], {"code": code})
                self.assertNotIn("validation", result["workerResult"])
                self.assertEqual(result["reviewResult"]["verdict"], "BLOCKED")
                self.assertEqual(
                    result["reviewResult"]["blockers"][0]["where"],
                    "reviewed behavior",
                )
                self.assertEqual(output["calls"], 4)

        output = self.run_installed(args, scenario="rereview-interrupt")
        result = self.assert_terminal(
            output,
            execution="INTERRUPTED",
            outcome=None,
            stopped_at="REREVIEW",
            stop_reason="CHILD_INTERRUPTED",
            calls=4,
            corrections_used=1,
            expected_roles=[
                "collab-implementer",
                "collab-acceptor",
                "collab-implementer",
                "collab-acceptor",
            ],
        )
        self.assertNotIn("error", result)
        self.assertNotIn("validation", result["workerResult"])
        self.assertIn("residualRisks", result["workerResult"])
        self.assertEqual(result["reviewResult"]["verdict"], "BLOCKED")

    def test_worker_blocked_stops_before_review(self) -> None:
        output = self.run_installed(scenario="worker-blocked")

        result = self.assert_terminal(
            output,
            execution="COMPLETED",
            outcome="BLOCKED",
            stopped_at="IMPLEMENT",
            stop_reason="WORKER_BLOCKED",
            calls=1,
        )
        self.assertEqual(output["invocations"][0][1]["agentType"], "collab-implementer")
        self.assertEqual(result["workerResult"]["outcome"], "BLOCKED")
        self.assertIsNone(result["reviewResult"])

    def test_worker_needs_decision_stops_before_review(self) -> None:
        output = self.run_installed(scenario="worker-needs-decision")

        result = self.assert_terminal(
            output,
            execution="COMPLETED",
            outcome="NEEDS_DECISION",
            stopped_at="IMPLEMENT",
            stop_reason="DECISION_REQUIRED",
            calls=1,
        )
        self.assertEqual(result["workerResult"]["outcome"], "NEEDS_DECISION")
        self.assertIsNone(result["reviewResult"])

    def test_reviewer_pass_projects_reviewed_only_after_worker_completion(self) -> None:
        output = self.run_installed(scenario="reviewer-pass")

        result = self.assert_terminal(
            output,
            execution="COMPLETED",
            outcome="REVIEWED",
            stopped_at="REVIEW",
            stop_reason="REVIEW_PASS",
            calls=2,
        )
        self.assertEqual(result["reviewResult"]["verdict"], "PASS")

    def test_reviewer_decision_suggestion_is_optional_and_allowed_when_present(self) -> None:
        for scenario, decision_keys in (
            ("reviewer-needs-decision", {"why", "question", "suggestion"}),
            ("reviewer-needs-decision-no-suggestion", {"why", "question"}),
        ):
            with self.subTest(scenario=scenario):
                output = self.run_installed(
                    {**VALID_INPUT, "correctionBudget": 1}, scenario=scenario
                )

                result = self.assert_terminal(
                    output,
                    execution="COMPLETED",
                    outcome="NEEDS_DECISION",
                    stopped_at="REVIEW",
                    stop_reason="DECISION_REQUIRED",
                    calls=2,
                )
                self.assertEqual(result["reviewResult"]["verdict"], "NEEDS_DECISION")
                self.assertEqual(
                    set(result["reviewResult"]["decision"]), decision_keys
                )

    def test_reviewer_blocked_is_blocked_and_never_falls_back(self) -> None:
        output = self.run_installed(scenario="reviewer-blocked")

        result = self.assert_terminal(
            output,
            execution="COMPLETED",
            outcome="BLOCKED",
            stopped_at="REVIEW",
            stop_reason="REVIEW_BLOCKED",
            calls=2,
        )
        self.assertEqual(result["reviewResult"]["verdict"], "BLOCKED")

    def test_reviewer_blocker_missing_trigger_is_rejected(self) -> None:
        output = self.run_installed(scenario="reviewer-blocked-missing-trigger")

        result = self.assert_terminal(
            output,
            execution="RUNTIME_GAP",
            outcome=None,
            stopped_at="REVIEW",
            stop_reason="CAPABILITY_UNAVAILABLE",
            calls=2,
        )
        self.assertEqual(result["error"], {"code": "INVALID_CHILD_RESULT"})

    def test_null_worker_result_is_runtime_gap_without_reviewer(self) -> None:
        output = self.run_installed(scenario="null-worker")

        result = self.assert_terminal(
            output,
            execution="RUNTIME_GAP",
            outcome=None,
            stopped_at="IMPLEMENT",
            stop_reason="CAPABILITY_UNAVAILABLE",
            calls=1,
        )
        self.assertEqual(result["error"], {"code": "NULL_CHILD_RESULT"})
        self.assertIsNone(result["workerResult"])
        self.assertIsNone(result["reviewResult"])

    def test_null_reviewer_result_preserves_completed_worker_without_semantic_outcome(self) -> None:
        output = self.run_installed(scenario="null-reviewer")

        result = self.assert_terminal(
            output,
            execution="RUNTIME_GAP",
            outcome=None,
            stopped_at="REVIEW",
            stop_reason="CAPABILITY_UNAVAILABLE",
            calls=2,
        )
        self.assertEqual(result["error"], {"code": "NULL_CHILD_RESULT"})
        self.assertEqual(result["workerResult"]["outcome"], "COMPLETED")
        self.assertIsNone(result["reviewResult"])

    def test_interruption_stops_at_the_child_without_fallback(self) -> None:
        for scenario, stopped_at, calls in (
            ("interrupt-worker", "IMPLEMENT", 1),
            ("interrupt-reviewer", "REVIEW", 2),
        ):
            with self.subTest(scenario=scenario):
                output = self.run_installed(scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="INTERRUPTED",
                    outcome=None,
                    stopped_at=stopped_at,
                    stop_reason="CHILD_INTERRUPTED",
                    calls=calls,
                )
                if stopped_at == "IMPLEMENT":
                    self.assertIsNone(result["workerResult"])
                else:
                    self.assertEqual(result["workerResult"]["outcome"], "COMPLETED")
                self.assertIsNone(result["reviewResult"])

    def test_runtime_and_capability_failures_do_not_select_a_generic_role(self) -> None:
        for scenario in ("runtime-error", "capability-failure"):
            with self.subTest(scenario=scenario):
                output = self.run_installed(scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="RUNTIME_GAP",
                    outcome=None,
                    stopped_at="IMPLEMENT",
                    stop_reason="CAPABILITY_UNAVAILABLE",
                    calls=1,
                )
                self.assertEqual(
                    result["capability"]["roles"],
                    ["collab-implementer", "collab-acceptor"],
                )
                self.assertEqual(result["capability"]["dispatch"], "native-child-agent")

    def test_reviewer_runtime_and_capability_failures_preserve_worker_without_extra_dispatch(self) -> None:
        expected_worker = {
            "outcome": "COMPLETED",
            "residualRisks": [],
        }
        for scenario in ("runtime-error-reviewer", "capability-failure-reviewer"):
            with self.subTest(scenario=scenario):
                output = self.run_installed(scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="RUNTIME_GAP",
                    outcome=None,
                    stopped_at="REVIEW",
                    stop_reason="CAPABILITY_UNAVAILABLE",
                    calls=2,
                )
                self.assertEqual(result["error"], {"code": "CHILD_RUNTIME_FAILURE"})
                self.assertEqual(result["workerResult"], expected_worker)
                self.assertIsNone(result["reviewResult"])
                self.assertEqual(
                    [invocation[1]["agentType"] for invocation in output["invocations"]],
                    ["collab-implementer", "collab-acceptor"],
                )

    def test_missing_native_dispatch_returns_capability_gap_before_child_dispatch(self) -> None:
        output = self.run_installed(scenario="missing")

        result = self.assert_terminal(
            output,
            execution="RUNTIME_GAP",
            outcome=None,
            stopped_at="VALIDATE",
            stop_reason="CAPABILITY_UNAVAILABLE",
            calls=0,
        )
        self.assertEqual(result["error"], {"code": "NATIVE_DISPATCH_UNAVAILABLE"})
        self.assertEqual(result["capability"]["status"], "RUNTIME_GAP")
        self.assertEqual(
            result["capability"]["roles"],
            ["collab-implementer", "collab-acceptor"],
        )

    def test_invalid_child_results_are_not_used_for_routing(self) -> None:
        for scenario, stopped_at, calls in (
            ("invalid-worker", "IMPLEMENT", 1),
            ("invalid-reviewer", "REVIEW", 2),
        ):
            with self.subTest(scenario=scenario):
                output = self.run_installed(scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="RUNTIME_GAP",
                    outcome=None,
                    stopped_at=stopped_at,
                    stop_reason="CAPABILITY_UNAVAILABLE",
                    calls=calls,
                )
                self.assertEqual(result["error"], {"code": "INVALID_CHILD_RESULT"})

    def test_runtime_validators_still_reject_malformed_branch_combinations(
        self,
    ) -> None:
        # The flattened dispatched schema alone would now accept a
        # branch-foreign key (e.g. `blocker` on a COMPLETED result) or a
        # missing branch-specific key (e.g. `blocker` absent on BLOCKED),
        # since those fields are declared optional at the schema's top
        # level. The closed-branch guarantee must still come from
        # validWorkerResult / validReviewerResult's hasExactKeys checks.
        worker_cases = (
            "invalid-worker-completed-with-blocker",
            "invalid-worker-blocked-missing-blocker",
            "invalid-worker-needs-decision-with-blocker",
        )
        for scenario in worker_cases:
            with self.subTest(scenario=scenario):
                output = self.run_installed(scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="RUNTIME_GAP",
                    outcome=None,
                    stopped_at="IMPLEMENT",
                    stop_reason="CAPABILITY_UNAVAILABLE",
                    calls=1,
                )
                self.assertEqual(result["error"], {"code": "INVALID_CHILD_RESULT"})

        reviewer_cases = (
            "invalid-reviewer-pass-with-blockers",
            "invalid-reviewer-blocked-missing-blockers",
            "invalid-reviewer-needs-decision-with-blockers",
        )
        for scenario in reviewer_cases:
            with self.subTest(scenario=scenario):
                output = self.run_installed(scenario=scenario)
                result = self.assert_terminal(
                    output,
                    execution="RUNTIME_GAP",
                    outcome=None,
                    stopped_at="REVIEW",
                    stop_reason="CAPABILITY_UNAVAILABLE",
                    calls=2,
                )
                self.assertEqual(result["error"], {"code": "INVALID_CHILD_RESULT"})
                self.assertEqual(result["workerResult"]["outcome"], "COMPLETED")
                self.assertIsNone(result["reviewResult"])

    def test_reviewer_decision_rejects_unknown_fields(self) -> None:
        output = self.run_installed(scenario="invalid-reviewer-decision-extra")

        result = self.assert_terminal(
            output,
            execution="RUNTIME_GAP",
            outcome=None,
            stopped_at="REVIEW",
            stop_reason="CAPABILITY_UNAVAILABLE",
            calls=2,
        )
        self.assertEqual(result["error"], {"code": "INVALID_CHILD_RESULT"})
        self.assertEqual(result["workerResult"]["outcome"], "COMPLETED")
        self.assertIsNone(result["reviewResult"])

    def test_structured_output_is_consumed_but_free_form_output_is_not_routing_input(self) -> None:
        output = self.run_installed(scenario="structured-happy")

        result = self.assert_terminal(
            output,
            execution="COMPLETED",
            outcome="REVIEWED",
            stopped_at="REVIEW",
            stop_reason="REVIEW_PASS",
            calls=2,
        )
        self.assertEqual(result["reviewResult"]["verdict"], "PASS")

    def test_blocker_field_newline_is_still_rejected(self) -> None:
        # operatorNotes alone gained newline support; a blocker field keeps the strict
        # single-line usableText check.
        scenario = json.dumps(
            {
                "steps": [
                    {
                        "outcome": "COMPLETED",
                        "residualRisks": [],
                    },
                    {
                        "verdict": "BLOCKED",
                        "blockers": [
                            {
                                "where": "line one\nline two",
                                "why": "A newline in a blocker field is out of shape.",
                                "howToFix": "Keep the field on one line.",
                                "trigger": "A reviewer submits a multi-line where.",
                            }
                        ],
                        "residualRisks": [],
                    },
                ]
            }
        )
        output = self.run_installed(scenario=scenario)

        result = self.assert_terminal(
            output,
            execution="RUNTIME_GAP",
            outcome=None,
            stopped_at="REVIEW",
            stop_reason="CAPABILITY_UNAVAILABLE",
            calls=2,
        )
        self.assertEqual(result["error"], {"code": "INVALID_CHILD_RESULT"})
        self.assertEqual(result["workerResult"]["outcome"], "COMPLETED")
        self.assertIsNone(result["reviewResult"])

    def test_invalid_inputs_dispatch_no_child_and_preserve_six_value_interface(self) -> None:
        cases = (
            (
                {key: value for key, value in VALID_INPUT.items() if key != "envelope"},
                "MISSING_INPUT",
                {"envelope"},
            ),
            (
                {key: value for key, value in VALID_INPUT.items() if key != "operatorNotes"},
                "MISSING_INPUT",
                {"operatorNotes"},
            ),
            ({**VALID_INPUT, "extra": True}, "UNKNOWN_INPUT", {"extra"}),
            ({**VALID_INPUT, "correctionBudget": 2}, "UNUSABLE_INPUT", {"correctionBudget"}),
            ({**VALID_INPUT, "lane": "relative/lane"}, "UNUSABLE_INPUT", {"lane"}),
            ({**VALID_INPUT, "ticket": "ticket.md"}, "UNUSABLE_INPUT", {"ticket"}),
            ({**VALID_INPUT, "envelope": "envelope.md"}, "UNUSABLE_INPUT", {"envelope"}),
            ({**VALID_INPUT, "startingHead": "   "}, "UNUSABLE_INPUT", {"startingHead"}),
            (
                {**VALID_INPUT, "lane": "/tmp/collab-lane\n/extra"},
                "UNUSABLE_INPUT",
                {"lane"},
            ),
            (
                {**VALID_INPUT, "ticket": "/tmp/ticket.md\n"},
                "UNUSABLE_INPUT",
                {"ticket"},
            ),
            (
                {**VALID_INPUT, "startingHead": "0123456789abcdef\n"},
                "UNUSABLE_INPUT",
                {"startingHead"},
            ),
            ({**VALID_INPUT, "operatorNotes": ""}, "UNUSABLE_INPUT", {"operatorNotes"}),
            ({**VALID_INPUT, "operatorNotes": 42}, "UNUSABLE_INPUT", {"operatorNotes"}),
            ({**VALID_INPUT, "operatorNotes": "   \n  "}, "UNUSABLE_INPUT", {"operatorNotes"}),
            (
                # A tab is a control character other than the newline/carriage-return pair
                # operatorNotes permits, so it still fails the field.
                {**VALID_INPUT, "operatorNotes": "line one\tindented"},
                "UNUSABLE_INPUT",
                {"operatorNotes"},
            ),
            (
                {**VALID_INPUT, "operatorNotes": "x" * 4097},
                "UNUSABLE_INPUT",
                {"operatorNotes"},
            ),
            ([], "INVALID_INPUT", {"args"}),
        )
        for args, code, fields in cases:
            with self.subTest(code=code, args=args):
                output = self.run_installed(args)
                result = self.assert_terminal(
                    output,
                    execution="RUNTIME_GAP",
                    outcome=None,
                    stopped_at="VALIDATE",
                    stop_reason="INVALID_INPUT",
                    calls=0,
                )
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(set(result["error"]["fields"]), fields)
                self.assertEqual(result["capability"], {"status": "NOT_CHECKED"})

    def test_operator_notes_reach_all_four_prompts_with_authority_rule(self) -> None:
        notes = "Runtime caution: the sandbox network is offline for this run."
        args = {**VALID_INPUT, "correctionBudget": 1, "operatorNotes": notes}
        output = self.run_installed(args, scenario="correction-rereview-pass")

        self.assert_dispatch_shape(
            output,
            [
                "collab-implementer",
                "collab-acceptor",
                "collab-implementer",
                "collab-acceptor",
            ],
        )
        self.assertEqual(output["calls"], 4)
        authority_phrase = "ticket wins"
        for prompt, _options in output["invocations"]:
            self.assertIn(notes, prompt)
            self.assertIn(authority_phrase, prompt)
            self.assertIn("no scope", prompt)
            self.assertIn("NEEDS_DECISION", prompt)

    def test_operator_notes_with_newlines_reach_prompts_intact(self) -> None:
        notes = (
            "Orientation: the collab-reviewed-lane workflow's input validators.\n\n"
            "Execution parameters: node, no environment variables.\n"
            "Placement and safety notes:\r\n"
            "- do not widen scope beyond the ticket.\n"
            "- report plainly if the suite regresses."
        )
        args = {**VALID_INPUT, "correctionBudget": 0, "operatorNotes": notes}
        output = self.run_installed(args, scenario="happy")

        result = self.assert_terminal(
            output,
            execution="COMPLETED",
            outcome="REVIEWED",
            stopped_at="REVIEW",
            stop_reason="REVIEW_PASS",
            calls=2,
        )
        self.assertEqual(result["reviewResult"]["verdict"], "PASS")
        for prompt, _options in output["invocations"]:
            self.assertIn(notes, prompt)

    def test_operator_notes_absent_from_all_prompts_when_null(self) -> None:
        args = {**VALID_INPUT, "correctionBudget": 1, "operatorNotes": None}
        output = self.run_installed(args, scenario="correction-rereview-pass")

        self.assertEqual(output["calls"], 4)
        for prompt, _options in output["invocations"]:
            self.assertNotIn("Operator notes:", prompt)
            self.assertNotIn("ticket wins", prompt)

    def test_role_schemas_are_flat_tool_input_schemas_with_enum_discriminator(
        self,
    ) -> None:
        output = self.run_installed()
        worker_schema = output["invocations"][0][1]["schema"]
        reviewer_schema = output["invocations"][1][1]["schema"]

        def assert_no_combinator_at_any_depth(node: Any) -> None:
            if isinstance(node, dict):
                for combinator in ("oneOf", "allOf", "anyOf"):
                    self.assertNotIn(
                        combinator,
                        node,
                        f"{combinator} is not permitted in a dispatched schema",
                    )
                for value in node.values():
                    assert_no_combinator_at_any_depth(value)
            elif isinstance(node, list):
                for item in node:
                    assert_no_combinator_at_any_depth(item)

        for schema in (worker_schema, reviewer_schema):
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            assert_no_combinator_at_any_depth(schema)

        self.assertEqual(
            worker_schema["properties"]["outcome"]["enum"],
            ["COMPLETED", "BLOCKED", "NEEDS_DECISION"],
        )
        self.assertEqual(
            set(worker_schema["required"]),
            {"outcome"},
        )
        self.assertEqual(
            set(worker_schema["properties"]),
            {"outcome", "residualRisks", "blocker", "decision"},
        )
        self.assertNotIn("blocker", worker_schema["required"])
        self.assertNotIn("decision", worker_schema["required"])

        self.assertEqual(
            reviewer_schema["properties"]["verdict"]["enum"],
            ["PASS", "BLOCKED", "NEEDS_DECISION"],
        )
        self.assertEqual(
            set(reviewer_schema["required"]),
            {"verdict"},
        )
        self.assertEqual(
            set(reviewer_schema["properties"]),
            {"verdict", "residualRisks", "blockers", "correctionBase", "decision"},
        )
        self.assertNotIn("blockers", reviewer_schema["required"])
        self.assertNotIn("decision", reviewer_schema["required"])
        blocker_properties = reviewer_schema["properties"]["blockers"]
        self.assertEqual(
            set(blocker_properties["items"]["properties"]),
            {"where", "why", "howToFix", "trigger"},
        )

        correction_output = self.run_installed(
            {**VALID_INPUT, "correctionBudget": 1},
            scenario="correction-rereview-pass",
        )
        self.assertEqual(
            correction_output["invocations"][2][1]["schema"], worker_schema
        )
        self.assertEqual(
            correction_output["invocations"][3][1]["schema"], reviewer_schema
        )
        self.assertEqual(
            [invocation[1]["agentType"] for invocation in correction_output["invocations"]],
            [
                "collab-implementer",
                "collab-acceptor",
                "collab-implementer",
                "collab-acceptor",
            ],
        )

    def test_terminal_projection_excludes_operational_identity_and_telemetry(self) -> None:
        output = self.run_installed()
        result = output["result"]

        self.assertEqual(
            set(result),
            {
                "type",
                "execution",
                "outcome",
                "stoppedAt",
                "stopReason",
                "correctionsUsed",
                "workerResult",
                "reviewResult",
            },
        )
        for forbidden in (
            "agentId",
            "runId",
            "model",
            "commit",
            "branch",
            "worktree",
            "transcript",
            "cost",
            "telemetry",
        ):
            self.assertNotIn(forbidden, result)


if __name__ == "__main__":
    unittest.main()
