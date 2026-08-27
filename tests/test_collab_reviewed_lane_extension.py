from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any

from tests.test_collab_op_extension import (
    git,
    invoke as invoke_extension,
    seed_managed_task,
    seed_repository,
    seed_task_container,
)

ROOT = Path(__file__).resolve().parents[1]
RPC_MOCK = ROOT / "tests/collab_rpc_mock_extension.ts"
SCRIPT_HARNESS = ROOT / "tests/collab_workflow_script_harness.mjs"
ROLE_CONTEXT_HARNESS = ROOT / "tests/collab_role_context_harness.mjs"
EXTENSION_HARNESS = ROOT / "tests/collab_op_extension_harness.mjs"
PI_PACKAGE = Path("/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js")
AGENT_PACKAGE = Path.home() / ".pi/agent/npm/package.json"
COMPANION = ROOT / "home/.pi/agent/extensions/collab-reviewed-lane.ts"
COLLAB_EXTENSION = ROOT / "home/.pi/agent/extensions/collab-op.ts"
TOOL = "collab_run_reviewed_lane"


def completed_step(result: dict[str, Any], run_id: str | None = None) -> dict[str, Any]:
    step = {"structuredOutput": result}
    if run_id is not None:
        step["runId"] = run_id
    return step


def invoke(repository: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Reuse the shared extension harness with the reviewed-lane RPC support extension."""
    return invoke_extension(repository, request, support_extension=RPC_MOCK)


def seed_profiles(repository: Path) -> None:
    profiles = repository / ".pi/agents"
    profiles.mkdir(parents=True)
    (profiles / "collab-implementer.md").write_text(
        "---\nname: collab-implementer\ndescription: Disposable bounded implementer.\n"
        "tools: read, write, edit, bash\ndefaultContext: fresh\n"
        "inheritProjectContext: true\ncompletionGuard: true\n"
        "---\nImplement the bounded brief.\n",
        encoding="utf-8",
    )
    (profiles / "collab-acceptor.md").write_text(
        "---\nname: collab-acceptor\ndescription: Disposable bounded acceptor.\n"
        "tools: read, bash\ndefaultContext: fresh\n"
        "inheritProjectContext: true\n---\nReview the bounded brief.\n",
        encoding="utf-8",
    )
    git(repository, "add", ".pi/agents")
    git(repository, "commit", "-m", "test profiles")


def seed_disposable_agent_home(
    base: Path,
    inheritance: dict[str, bool | str | None] | None = None,
) -> tuple[Path, Path]:
    inheritance = inheritance or {}
    home = base / "disposable-home"
    agent_dir = home / ".pi/agent"
    profiles = agent_dir / "agents"
    profiles.mkdir(parents=True)
    (agent_dir / "npm").symlink_to(AGENT_PACKAGE.parent, target_is_directory=True)

    def inheritance_line(role: str) -> str:
        value = inheritance.get(role, True)
        if value is None:
            return ""
        if isinstance(value, bool):
            return f"inheritProjectContext: {str(value).lower()}\n"
        return f"inheritProjectContext: {value}\n"

    (profiles / "collab-implementer.md").write_text(
        "---\nname: collab-implementer\ndescription: Disposable bounded implementer.\n"
        "tools: read, write, edit, bash\ndefaultContext: fresh\n"
        + inheritance_line("collab-implementer")
        + "completionGuard: true\n---\nImplement the bounded brief.\n",
        encoding="utf-8",
    )
    (profiles / "collab-acceptor.md").write_text(
        "---\nname: collab-acceptor\ndescription: Disposable bounded acceptor.\n"
        "tools: read, bash\ndefaultContext: fresh\n"
        + inheritance_line("collab-acceptor")
        + "---\nReview the bounded brief.\n",
        encoding="utf-8",
    )
    return home, agent_dir


def invoke_with_disposable_home(
    repository: Path,
    request: dict[str, Any],
    home: Path,
) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["HOME"] = str(home)
    run = subprocess.run(
        [
            "node",
            str(EXTENSION_HARNESS),
            str(PI_PACKAGE),
            str(COLLAB_EXTENSION),
            str(repository),
            str(RPC_MOCK),
        ],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if run.returncode != 0:
        raise AssertionError(f"isolated extension harness failed: {run.stderr}")
    return json.loads(run.stdout)


def seed_role_context_fixture(repository: Path, marker: str) -> None:
    (repository / "AGENTS.md").write_text(
        f"# Disposable lane instructions\n\nEffective project marker: {marker}\n",
        encoding="utf-8",
    )
    runtime = repository / ".runtime"
    runtime.mkdir()
    (runtime / "observe.py").write_text(
        "import json, os\n"
        "print(json.dumps({'cwd': os.getcwd(), 'role_token': os.environ['ROLE_TOKEN']}))\n",
        encoding="utf-8",
    )
    bin_dir = runtime / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)
    git(repository, "add", "AGENTS.md", ".runtime")
    git(repository, "commit", "-m", "test lane context and runtime")


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
    def assert_fresh_reviewer_options(
        self, options: dict[str, Any], expected_lane: str
    ) -> None:
        self.assertEqual(options["agent"], "collab-acceptor")
        self.assertEqual(options["cwd"], expected_lane)
        self.assertIs(options["worktree"], False)
        self.assertEqual(options["context"], "fresh")
        self.assertNotIn("resume", options)

    def test_companion_is_loadable_as_top_level_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = subprocess.run(
                [
                    "node",
                    str(EXTENSION_HARNESS),
                    str(PI_PACKAGE),
                    str(COMPANION),
                    temporary,
                ],
                input='{"tool":"missing"}\n',
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(run.returncode, 0, run.stderr)
        observed = json.loads(run.stdout)
        self.assertEqual(observed["tools"], [])
        self.assertTrue(observed["is_error"])
        self.assertEqual(observed["error"]["error"]["code"], "unknown_tool")

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

    def test_profile_inheritance_failures_never_request_rpc_spawn(self) -> None:
        cases: tuple[tuple[str, bool | str | None], ...] = (
            ("collab-implementer", None),
            ("collab-implementer", False),
            ("collab-implementer", "not-a-boolean"),
            ("collab-acceptor", None),
            ("collab-acceptor", False),
            ("collab-acceptor", "not-a-boolean"),
        )
        for role, declaration in cases:
            with (
                self.subTest(role=role, declaration=declaration),
                tempfile.TemporaryDirectory() as temporary,
            ):
                base = Path(temporary)
                repository, _ = seed_repository(base)
                seed_managed_task(repository)
                home, _ = seed_disposable_agent_home(base, {role: declaration})
                capture = base / "rpc.jsonl"
                observed = invoke_with_disposable_home(
                    repository,
                    valid_request(capture),
                    home,
                )

                self.assertTrue(observed["is_error"], observed)
                self.assertIn(
                    observed["error"]["error"]["code"],
                    {"profile_unavailable", "project_context_unavailable"},
                )
                self.assertIn(role, observed["error"]["error"]["message"])
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse(
                    capture.exists(), "profile rejection must happen before RPC spawn"
                )

    def test_fresh_roles_observe_lane_context_and_consume_exact_execution_parameters(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            marker = f"lane-root-{uuid.uuid4().hex}"
            repository, _ = seed_repository(base)
            seed_role_context_fixture(repository, marker)
            expected = seed_managed_task(repository)
            home, disposable_agent_dir = seed_disposable_agent_home(base)
            lane = Path(expected["lane"])
            runtime = lane / ".runtime/bin/python3"
            observer = lane / ".runtime/observe.py"

            def execution(role: str) -> dict[str, Any]:
                return {
                    "runtime": str(runtime),
                    "args": [str(observer)],
                    "environment": {"ROLE_TOKEN": role},
                }

            worker_execution = execution("collab-implementer")
            reviewer_execution = execution("collab-acceptor")
            capture = base / "rpc.jsonl"
            observed = invoke_with_disposable_home(
                repository,
                valid_request(
                    capture,
                    worker_brief=(
                        "Implement the bounded fixture.\n"
                        f"Execution parameters JSON: {json.dumps(worker_execution, separators=(',', ':'))}"
                    ),
                    review_brief=(
                        "Review the bounded fixture read-only.\n"
                        f"Execution parameters JSON: {json.dumps(reviewer_execution, separators=(',', ':'))}"
                    ),
                ),
                home,
            )
            self.assertFalse(observed["is_error"], observed)

            isolated_agent_dir = base / "isolated-agent"
            isolated_agent_dir.mkdir()
            role_environment = dict(os.environ)
            role_environment["HOME"] = str(home)
            role_run = subprocess.run(
                [
                    "node",
                    str(ROLE_CONTEXT_HARNESS),
                    str(capture),
                    str(PI_PACKAGE),
                    str(disposable_agent_dir / "npm/package.json"),
                    str(isolated_agent_dir),
                    marker,
                ],
                capture_output=True,
                text=True,
                check=False,
                env=role_environment,
            )
            self.assertEqual(role_run.returncode, 0, role_run.stderr)
            result = json.loads(role_run.stdout)

        self.assertEqual(result["result"]["outcome"], "REVIEWED")
        self.assertEqual(
            [item["agent"] for item in result["observations"]],
            ["collab-implementer", "collab-acceptor"],
        )
        for item in result["observations"]:
            self.assertEqual(item["context"], "fresh")
            self.assertEqual(item["cwd"], expected["lane"])
            self.assertIs(item["markerObserved"], True)
            self.assertEqual(item["execution"]["runtime"], str(runtime))
            self.assertEqual(
                item["execution"]["environment"], {"ROLE_TOKEN": item["agent"]}
            )
            self.assertEqual(item["commandObservation"]["cwd"], expected["lane"])
            self.assertEqual(item["commandObservation"]["role_token"], item["agent"])

    def test_shipped_registration_exposes_narrow_public_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, _, observed = self.launch_case(base)

        self.assertIn(TOOL, observed["tools"])
        schema = observed["schemas"][TOOL]["parameters"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {
                "task_id",
                "ticket_id",
                "lane_id",
                "worker_brief",
                "review_brief",
                "correction_budget",
            },
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
        self.assertEqual(
            set(observed["result"]), {"workflow_id", "async_id", "async_dir"}
        )
        self.assertEqual(observed["result"]["async_id"], "async-test-id")
        self.assertEqual(
            observed["result"]["async_dir"], "/tmp/pi-subagents/async-test-id"
        )
        self.assertEqual(rpc["version"], 1)
        self.assertEqual(rpc["method"], "spawn")
        self.assertEqual(set(rpc["params"]), {"cwd", "workflowScript", "async"})
        self.assertEqual(rpc["params"]["cwd"], expected["lane"])
        self.assertIs(rpc["params"]["async"], True)
        self.assertIn(expected["lane"], rpc["params"]["workflowScript"])

    def test_receipt_projects_pi_subagents_run_id_when_distinct_from_async_id(
        self,
    ) -> None:
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

    def test_spawned_workflow_uses_fresh_exact_lane_typed_children_and_structured_control(
        self,
    ) -> None:
        worker = {"outcome": "COMPLETED", "residualRisks": ["bounded risk"]}
        reviewer = {"verdict": "PASS", "residualRisks": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base)
            self.assertFalse(observed["is_error"], observed)
            run = subprocess.run(
                [
                    "node",
                    str(SCRIPT_HARNESS),
                    str(capture),
                    json.dumps([completed_step(worker), reviewer]),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            execution = json.loads(run.stdout)

        self.assertEqual(execution["result"]["outcome"], "REVIEWED")
        self.assertEqual(
            [call["key"] for call in execution["calls"]], ["impl-0", "review-0"]
        )
        self.assertEqual(
            [call["options"]["agent"] for call in execution["calls"]],
            ["collab-implementer", "collab-acceptor"],
        )
        for call in execution["calls"]:
            options = call["options"]
            expected_keys = {
                "agent",
                "cwd",
                "worktree",
                "context",
                "task",
                "outputSchema",
            }
            if options["agent"] == "collab-implementer":
                expected_keys.add("agentContract")
                self.assertEqual(options["agentContract"], {"version": 1})
            self.assertEqual(set(options), expected_keys)
            self.assertEqual(options["cwd"], expected["lane"])
            self.assertIs(options["worktree"], False)
            self.assertEqual(options["context"], "fresh")
            self.assertIsInstance(options["outputSchema"], dict)
            self.assertNotIn("model", options)
            self.assertNotIn("thinking", options)
            self.assertNotIn("runId", options)

    def test_initial_reviewer_dispatch_receives_runtime_integration_baseline(
        self,
    ) -> None:
        worker = {"outcome": "COMPLETED", "residualRisks": []}
        reviewer = {"verdict": "PASS", "residualRisks": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base)
            self.assertFalse(observed["is_error"], observed)
            rpc = json.loads(capture.read_text(encoding="utf-8").strip())
            workflow_script = rpc["params"]["workflowScript"]
            self.assertIn(expected["integration_head"], workflow_script)
            self.assertIn("git diff --find-renames ", workflow_script)
            execution = json.loads(
                subprocess.run(
                    [
                        "node",
                        str(SCRIPT_HARNESS),
                        str(capture),
                        json.dumps([completed_step(worker), reviewer]),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )

        review_task = execution["calls"][1]["options"]["task"]
        self.assertIn(expected["integration_head"], review_task)
        self.assertIn(
            f"git diff --find-renames {expected['integration_head']}...HEAD --",
            review_task,
        )
        self.assertIn("complete candidate lane diff", review_task)
        # The baseline is reviewer dispatch context; the worker brief carries none.
        self.assertNotIn(
            expected["integration_head"], execution["calls"][0]["options"]["task"]
        )

    def test_every_rereview_keeps_the_same_immutable_baseline(self) -> None:
        worker = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [{"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}],
            "residualRisks": [],
        }
        passed = {"verdict": "PASS", "residualRisks": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base, correction_budget=2)
            self.assertFalse(observed["is_error"], observed)
            execution = json.loads(
                subprocess.run(
                    [
                        "node",
                        str(SCRIPT_HARNESS),
                        str(capture),
                        json.dumps(
                            [
                                completed_step(worker),
                                blocked,
                                completed_step(worker),
                                blocked,
                                completed_step(worker),
                                passed,
                            ]
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )

        sha = expected["integration_head"]
        canonical_initial = f"git diff --find-renames {sha}...HEAD --"
        # Use the correctionBase from the blocked fixture
        correction_base = (
            blocked["correctionBase"]
            if "blocked" in locals()
            else "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        )
        canonical_rereview = f"git diff --find-renames {correction_base}...HEAD --"
        review_tasks = {
            call["key"]: call["options"]["task"]
            for call in execution["calls"]
            if call["key"].startswith("review-")
        }
        self.assertEqual(set(review_tasks), {"review-0", "review-1", "review-2"})
        for key, task in review_tasks.items():
            if key == "review-0":
                self.assertIn(sha, task, key)
                self.assertIn(canonical_initial, task, key)
                self.assertIn("complete candidate lane diff", task, key)
            else:
                self.assertIn(correction_base, task, key)
                self.assertIn(canonical_rereview, task, key)
                self.assertIn("complete current lane diff", task, key)
        # Rereviews inspect the complete current lane diff after correction,
        # not only the latest change.
        for key in ("review-1", "review-2"):
            self.assertIn("complete current lane diff", review_tasks[key], key)
        # The rereviews share the same correctionBase, not integration tip
        self.assertEqual(len(execution["calls"]), 6)

    def test_public_input_admits_no_caller_baseline_and_typed_results_carry_none(
        self,
    ) -> None:
        worker = {"outcome": "COMPLETED", "residualRisks": []}
        reviewer = {"verdict": "PASS", "residualRisks": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base)
            self.assertFalse(observed["is_error"], observed)
            schema = observed["schemas"][TOOL]["parameters"]
            self.assertFalse(schema["additionalProperties"])
            for forbidden in (
                "baseline",
                "integration_tip",
                "integration_sha",
                "base_sha",
                "starting_head",
                "diff_command",
            ):
                self.assertNotIn(forbidden, schema["properties"])
            execution = json.loads(
                subprocess.run(
                    [
                        "node",
                        str(SCRIPT_HARNESS),
                        str(capture),
                        json.dumps([completed_step(worker), reviewer]),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )

        # Baseline identity stays in dispatch context; it never enters the typed
        # terminal semantic result.
        self.assertNotIn(expected["integration_head"], json.dumps(execution["result"]))

    def test_schema_valid_writer_stop_survives_the_runtime_no_edit_guard(self) -> None:
        blocked = {"outcome": "BLOCKED", "blocker": "required input is missing"}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base)
            self.assertFalse(observed["is_error"], observed)
            run = subprocess.run(
                [
                    "node",
                    str(SCRIPT_HARNESS),
                    str(capture),
                    json.dumps(
                        [
                            {
                                "structuredOutput": blocked,
                                "noMutationStop": True,
                                "mutationStatus": "missing",
                            }
                        ]
                    ),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            execution = json.loads(run.stdout)

        self.assertEqual(execution["result"], blocked)
        self.assertEqual(len(execution["calls"]), 1)
        self.assertEqual(
            execution["calls"][0]["options"]["agentContract"], {"version": 1}
        )

    def test_initial_no_effect_completion_always_launches_a_fresh_reviewer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base)
            self.assertFalse(observed["is_error"], observed)
            request = json.loads(capture.read_text(encoding="utf-8").strip())
            workflow_script = request["params"]["workflowScript"]
            runner = r"""
const workflowScript = JSON.parse(process.argv[1]);
const writerEnvelope = JSON.parse(process.argv[2]);
const calls = [];
const runs = {
  async run(key, options) {
    calls.push({key, options});
    if (calls.length === 1) return {
      structuredOutput: {outcome:"COMPLETED", residualRisks:[]},
      ...writerEnvelope
    };
    return {structuredOutput:{verdict:"PASS", residualRisks:[]}, results:[]};
  },
  async all(items) {
    const results = [];
    for (const item of items) {
      const {key, ...options} = item;
      const res = await this.run(key, options);
      results.push({key, ok: true, structuredOutput: res.structuredOutput, runId: res.runId, output: res.output || "output", artifactPaths: [], results: res.results || []});
    }
    return results;
  }
};
const execute = Function("runs", `return (async () => {\n${workflowScript}\n})()`);
const result = await execute(runs);
process.stdout.write(JSON.stringify({result, calls}));
"""
            effect_shapes = {
                "absent": {},
                "empty": {"results": []},
                "missing": {"results": [{}]},
                "empty-effects": {"results": [{"effects": {}}]},
                "not-applicable": {
                    "results": [
                        {"effects": {"fileMutation": {"status": "not-applicable"}}}
                    ]
                },
                "observed-diagnostic": {
                    "results": [{"effects": {"fileMutation": {"status": "observed"}}}]
                },
            }
            for shape, writer_envelope in effect_shapes.items():
                with self.subTest(shape=shape):
                    execution = json.loads(
                        subprocess.run(
                            [
                                "node",
                                "-e",
                                runner,
                                json.dumps(workflow_script),
                                json.dumps(writer_envelope),
                            ],
                            capture_output=True,
                            text=True,
                            check=True,
                        ).stdout
                    )
                    self.assertEqual(execution["result"]["outcome"], "REVIEWED")
                    self.assertEqual(
                        [call["key"] for call in execution["calls"]],
                        ["impl-0", "review-0"],
                    )
                    self.assertEqual(
                        execution["calls"][0]["options"]["agentContract"],
                        {"version": 1},
                    )
                    reviewer = execution["calls"][1]["options"]
                    self.assert_fresh_reviewer_options(reviewer, expected["lane"])

    def test_terminal_branches_are_typed_and_zero_budget_is_terminal(self) -> None:
        completed = {"outcome": "COMPLETED", "residualRisks": []}
        cases = [
            (
                [{"outcome": "BLOCKED", "blocker": "blocked"}],
                {"outcome": "BLOCKED", "blocker": "blocked"},
                1,
            ),
            (
                [
                    {
                        "outcome": "NEEDS_DECISION",
                        "decision": {"why": "why", "question": "question"},
                    }
                ],
                {"outcome": "NEEDS_DECISION", "why": "why", "question": "question"},
                1,
            ),
            (
                [
                    completed_step(completed),
                    {
                        "verdict": "NEEDS_DECISION",
                        "decision": {
                            "why": "review why",
                            "question": "review question",
                        },
                    },
                ],
                {
                    "outcome": "NEEDS_DECISION",
                    "why": "review why",
                    "question": "review question",
                },
                2,
            ),
            (
                [
                    completed_step(completed),
                    {
                        "verdict": "BLOCKED",
                        "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                        "blockers": [
                            {"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}
                        ],
                    },
                ],
                {
                    "outcome": "CORRECTION_BUDGET_EXHAUSTED",
                    "blockers": [
                        {"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}
                    ],
                    "residualRisks": [],
                },
                2,
            ),
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

    def test_budget_one_runs_one_correction_and_rereview_with_current_blockers(
        self,
    ) -> None:
        worker = {"outcome": "COMPLETED", "residualRisks": ["latest risk"]}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [
                {
                    "where": "current.ts",
                    "why": "missing behavior",
                    "howToFix": "add behavior",
                    "trigger": "t",
                }
            ],
            "residualRisks": [],
        }
        passed = {"verdict": "PASS", "residualRisks": ["scope: finding"]}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            execution = json.loads(
                subprocess.run(
                    [
                        "node",
                        str(SCRIPT_HARNESS),
                        str(capture),
                        json.dumps(
                            [
                                completed_step(worker),
                                blocked,
                                completed_step(worker),
                                passed,
                            ]
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )

        self.assertEqual(
            execution["result"],
            {
                "outcome": "REVIEWED",
                "residualRisks": worker["residualRisks"] + passed["residualRisks"],
            },
        )
        self.assertEqual(
            [call["key"] for call in execution["calls"]],
            ["impl-0", "review-0", "impl-1", "review-1"],
        )
        self.assertEqual(
            [call["options"]["cwd"] for call in execution["calls"]],
            [expected["lane"]] * 4,
        )
        self.assertIn('"where":"current.ts"', execution["calls"][2]["options"]["task"])
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

    def test_no_effect_retained_corrections_replace_latest_writer_and_keep_every_review_fresh(
        self,
    ) -> None:
        completed = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [
                {
                    "where": "lane.ts",
                    "why": "first blocker",
                    "howToFix": "correct it",
                    "trigger": "review one",
                }
            ],
        }
        blocked_again = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [
                {
                    "where": "lane.ts",
                    "why": "second blocker",
                    "howToFix": "correct it again",
                    "trigger": "rereview one",
                }
            ],
        }
        passed = {"verdict": "PASS", "residualRisks": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            capture = base / "supported-rpc.jsonl"
            _, expected, _, observed = self.launch_case(
                base,
                capture_name=capture.name,
                correction_budget=2,
                __rpc={
                    "mode": "available",
                    "capture": str(capture),
                    "foregroundStructuredResume": {
                        "version": 1,
                        "recoveryDescriptorVersion": 1,
                    },
                },
            )
            self.assertFalse(observed["is_error"], observed)
            run = subprocess.run(
                [
                    "node",
                    str(SCRIPT_HARNESS),
                    str(capture),
                    json.dumps(
                        [
                            completed_step(completed, "writer-initial"),
                            blocked,
                            completed_step(completed, "writer-correction-1"),
                            blocked_again,
                            completed_step(completed, "writer-correction-2"),
                            passed,
                        ]
                    ),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            execution = json.loads(run.stdout)

        self.assertEqual(execution["result"]["outcome"], "REVIEWED")
        self.assertEqual(
            [call["key"] for call in execution["calls"]],
            ["impl-0", "review-0", "impl-1", "review-1", "impl-2", "review-2"],
        )
        self.assertEqual(execution["calls"][2]["options"]["resume"], "writer-initial")
        self.assertEqual(
            execution["calls"][4]["options"]["resume"], "writer-correction-1"
        )
        for index in (2, 4):
            self.assertEqual(
                set(execution["calls"][index]["options"]), {"resume", "task"}
            )
            self.assertIn(
                "latest typed blockers", execution["calls"][index]["options"]["task"]
            )
            self.assertIn(
                "efficiencyFeedback", execution["calls"][index]["options"]["task"]
            )
        for index in (0, 1, 3, 5):
            options = execution["calls"][index]["options"]
            self.assertEqual(options["cwd"], expected["lane"])
            self.assertIs(options["worktree"], False)
            self.assertEqual(options["context"], "fresh")
        self.assertEqual(
            [execution["calls"][index]["options"]["agent"] for index in (1, 3, 5)],
            ["collab-acceptor"] * 3,
        )

    def test_every_nonexact_capability_preselects_one_no_effect_bounded_fresh_fallback(
        self,
    ) -> None:
        missing = object()
        signals: list[object] = [
            missing,
            False,
            True,
            None,
            "version-one",
            [],
            {},
            {"version": 1},
            {"version": 1, "recoveryDescriptorVersion": False},
            {"version": 2, "recoveryDescriptorVersion": 1},
            {"version": 1, "recoveryDescriptorVersion": 2},
        ]
        completed = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [
                {
                    "where": "current.ts",
                    "why": "typed blocker marker",
                    "howToFix": "apply the bounded correction",
                    "trigger": "fresh fallback probe",
                }
            ],
        }
        passed = {"verdict": "PASS", "residualRisks": []}
        original_contract = (
            "Original ticket contract marker.\n\n"
            "Exact execution parameters: installed node; environment variables none; "
            "five-minute timeout.\n\n"
            "Return optional native efficiencyFeedback for observed correction friction."
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, signal in enumerate(signals):
                with self.subTest(signal=signal):
                    base = root / str(index)
                    base.mkdir()
                    capture = base / "fallback-rpc.jsonl"
                    rpc: dict[str, object] = {
                        "mode": "available",
                        "capture": str(capture),
                    }
                    if signal is not missing:
                        rpc["foregroundStructuredResume"] = signal
                    _, expected, _, observed = self.launch_case(
                        base,
                        capture_name=capture.name,
                        worker_brief=original_contract,
                        review_brief="Fresh review marker; forbidden from writer fallback payload.",
                        correction_budget=1,
                        __rpc=rpc,
                    )
                    self.assertFalse(observed["is_error"], observed)
                    execution = json.loads(
                        subprocess.run(
                            [
                                "node",
                                str(SCRIPT_HARNESS),
                                str(capture),
                                json.dumps(
                                    [
                                        completed_step(completed, "writer-initial"),
                                        blocked,
                                        completed_step(completed, "writer-fallback"),
                                        passed,
                                    ]
                                ),
                            ],
                            capture_output=True,
                            text=True,
                            check=True,
                        ).stdout
                    )
                    self.assertEqual(
                        [call["key"] for call in execution["calls"]],
                        ["impl-0", "review-0", "impl-1", "review-1"],
                    )
                    fallback = execution["calls"][2]["options"]
                    self.assertEqual(
                        set(fallback),
                        {
                            "agent",
                            "cwd",
                            "worktree",
                            "context",
                            "task",
                            "outputSchema",
                            "agentContract",
                        },
                    )
                    self.assertEqual(fallback["agent"], "collab-implementer")
                    self.assertEqual(fallback["cwd"], expected["lane"])
                    self.assertIs(fallback["worktree"], False)
                    self.assertEqual(fallback["context"], "fresh")
                    self.assertNotIn("resume", fallback)
                    initial_worker_contract = execution["calls"][0]["options"]["task"]
                    self.assertIn(original_contract, initial_worker_contract)
                    self.assertEqual(
                        fallback["task"],
                        "\n\n".join(
                            [
                                "Fresh compatible correction writer selected before launch.",
                                "Original ticket contract and exact execution parameters:",
                                initial_worker_contract,
                                "Latest typed blockers:",
                                json.dumps(blocked["blockers"], separators=(",", ":")),
                                "Current lane placement:",
                                expected["lane"],
                            ]
                        ),
                    )
                    self.assertEqual(fallback["task"].count("efficiencyFeedback"), 1)
                    self.assertNotIn("Fresh review marker", fallback["task"])
                    self.assertNotIn("INDEX", fallback["task"])
                    self.assertNotIn("sibling", fallback["task"])
                    self.assertNotIn("task history", fallback["task"])
                    rereviewer = execution["calls"][3]["options"]
                    self.assert_fresh_reviewer_options(rereviewer, expected["lane"])

    def test_harness_rejects_fresh_reviewer_run_as_writer_resume_target(self) -> None:
        completed = {"outcome": "COMPLETED", "residualRisks": []}
        passed = {"verdict": "PASS", "residualRisks": []}
        workflow_script = """
const writer = await runs.run("impl-0", { agent: "collab-implementer" });
const reviewer = await runs.run("review-0", { agent: "collab-acceptor" });
await runs.run("impl-1", { resume: reviewer.runId, task: "must reject reviewer target" });
return { writerRunId: writer.runId };
"""
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "reviewer-resume-target.jsonl"
            capture.write_text(
                json.dumps({"params": {"workflowScript": workflow_script}}) + "\n",
                encoding="utf-8",
            )
            run = subprocess.run(
                [
                    "node",
                    str(SCRIPT_HARNESS),
                    str(capture),
                    json.dumps(
                        [
                            completed_step(completed, "writer-run"),
                            completed_step(passed, "reviewer-run"),
                            completed_step(completed, "must-not-resume"),
                        ]
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            execution = json.loads(run.stdout)

        self.assertNotEqual(run.returncode, 0)
        self.assertIn(
            "resume target was not a successful earlier writer: reviewer-run",
            run.stderr,
        )
        self.assertEqual(
            [call["key"] for call in execution["calls"]],
            ["impl-0", "review-0", "impl-1"],
        )

    def test_resume_rejection_never_reacts_by_launching_a_fresh_writer(self) -> None:
        completed = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [
                {"where": "x", "why": "y", "howToFix": "z", "trigger": "review"}
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            capture = base / "resume-rejection-rpc.jsonl"
            _, _, _, observed = self.launch_case(
                base,
                capture_name=capture.name,
                correction_budget=1,
                __rpc={
                    "mode": "available",
                    "capture": str(capture),
                    "foregroundStructuredResume": {
                        "version": 1,
                        "recoveryDescriptorVersion": 1,
                    },
                },
            )
            self.assertFalse(observed["is_error"], observed)
            run = subprocess.run(
                [
                    "node",
                    str(SCRIPT_HARNESS),
                    str(capture),
                    json.dumps(
                        [
                            completed_step(completed, "writer-initial"),
                            blocked,
                            {
                                "structuredOutput": completed,
                                "mutationStatus": "observed",
                                "throwMessage": "resume rejected before child launch",
                            },
                            completed_step(completed, "must-not-launch"),
                        ]
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            execution = json.loads(run.stdout)

        self.assertNotEqual(run.returncode, 0)
        self.assertIn("resume rejected before child launch", run.stderr)
        self.assertEqual(
            [call["key"] for call in execution["calls"]],
            ["impl-0", "review-0", "impl-1"],
        )
        self.assertEqual(execution["calls"][2]["options"]["resume"], "writer-initial")
        self.assertEqual(set(execution["calls"][2]["options"]), {"resume", "task"})

    def test_unchanged_candidate_consumes_exact_budget_without_an_extra_writer(
        self,
    ) -> None:
        completed = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [
                {
                    "where": "x",
                    "why": "the unchanged candidate remains unacceptable",
                    "howToFix": "make the required correction",
                    "trigger": "review the unchanged candidate",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base, correction_budget=2)
            self.assertFalse(observed["is_error"], observed)
            steps = [
                completed_step(completed),
                blocked,
                completed_step(completed),
                blocked,
                completed_step(completed),
                blocked,
            ]
            execution = json.loads(
                subprocess.run(
                    ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )

        self.assertEqual(
            execution["result"],
            {
                "outcome": "CORRECTION_BUDGET_EXHAUSTED",
                "blockers": blocked["blockers"],
                "residualRisks": [],
            },
        )
        self.assertEqual(
            [call["key"] for call in execution["calls"]],
            ["impl-0", "review-0", "impl-1", "review-1", "impl-2", "review-2"],
        )
        self.assertEqual(
            [
                call["key"]
                for call in execution["calls"]
                if call["key"].startswith("impl-")
            ],
            ["impl-0", "impl-1", "impl-2"],
        )

    def test_every_correction_terminal_branch_stops_at_the_current_round(self) -> None:
        completed = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [
                {
                    "where": "lane.ts",
                    "why": "expectation",
                    "howToFix": "correct it",
                    "trigger": "t",
                }
            ],
            "residualRisks": [],
        }
        cases = [
            (
                1,
                [
                    completed_step(completed),
                    blocked,
                    {"outcome": "BLOCKED", "blocker": "correction blocked"},
                ],
                {"outcome": "BLOCKED", "blocker": "correction blocked"},
                ["impl-0", "review-0", "impl-1"],
            ),
            (
                1,
                [
                    completed_step(completed),
                    blocked,
                    {
                        "outcome": "NEEDS_DECISION",
                        "decision": {
                            "why": "correction why",
                            "question": "correction question",
                        },
                    },
                ],
                {
                    "outcome": "NEEDS_DECISION",
                    "why": "correction why",
                    "question": "correction question",
                },
                ["impl-0", "review-0", "impl-1"],
            ),
            (
                1,
                [
                    completed_step(completed),
                    blocked,
                    completed_step(completed),
                    {
                        "verdict": "NEEDS_DECISION",
                        "decision": {
                            "why": "rereview why",
                            "question": "rereview question",
                        },
                    },
                ],
                {
                    "outcome": "NEEDS_DECISION",
                    "why": "rereview why",
                    "question": "rereview question",
                },
                ["impl-0", "review-0", "impl-1", "review-1"],
            ),
            (
                1,
                [
                    completed_step(completed),
                    blocked,
                    completed_step(completed),
                    blocked,
                ],
                {
                    "outcome": "CORRECTION_BUDGET_EXHAUSTED",
                    "blockers": blocked["blockers"],
                    "residualRisks": [],
                },
                ["impl-0", "review-0", "impl-1", "review-1"],
            ),
        ]
        for budget, steps, expected_result, expected_keys in cases:
            with (
                self.subTest(expected=expected_result["outcome"]),
                tempfile.TemporaryDirectory() as temporary,
            ):
                base = Path(temporary)
                _, _, capture, observed = self.launch_case(
                    base, correction_budget=budget
                )
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
                self.assertEqual(
                    [call["key"] for call in execution["calls"]], expected_keys
                )
                for call in execution["calls"]:
                    expected_options = {
                        "agent",
                        "cwd",
                        "worktree",
                        "context",
                        "task",
                        "outputSchema",
                    }
                    if call["options"]["agent"] == "collab-implementer":
                        expected_options.add("agentContract")
                        self.assertEqual(
                            call["options"]["agentContract"], {"version": 1}
                        )
                    self.assertEqual(set(call["options"]), expected_options)
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
            with (
                self.subTest(override=override),
                tempfile.TemporaryDirectory() as temporary,
            ):
                base = Path(temporary)
                _, _, capture, observed = self.launch_case(
                    base,
                    capture_name=f"rpc-{index}.jsonl",
                    **override,
                )
                self.assertTrue(observed["is_error"], observed)
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse(capture.exists())


def make_status(
    workflow_id: str,
    lane_path: str,
    workflow_key: str,
    child_run_id: str,
    turn_count: int,
    session_file: str,
    duration_ms: int = 12345,
    state: str = "complete",
) -> dict[str, object]:
    return {
        "runId": workflow_id,
        "cwd": lane_path,
        "state": state,
        "workflow": {
            "trace": [
                {
                    "key": workflow_key,
                    "runId": child_run_id,
                    "durationMs": duration_ms,
                    "state": "completed",
                }
            ],
            "emits": [],
            "console": [],
        },
        "steps": [
            {
                "agent": "collab-implementer"
                if workflow_key.startswith("impl")
                else "collab-acceptor",
                "workflowKey": workflow_key,
                "parentWorkflowRunId": workflow_id,
                "status": "completed",
                "turnCount": turn_count,
                "sessionFile": session_file,
            }
        ],
    }


def make_session(
    calls: list[tuple[str, str, int, int | None, bool]],
    tokens: list[int],
) -> str:
    lines: list[str] = []
    token_idx = 0
    for idx, (call_id, name, start, end, is_error) in enumerate(calls):
        total = tokens[token_idx] if token_idx < len(tokens) else 1000
        token_idx += 1
        assistant = {
            "type": "message",
            "id": f"assist-{idx}",
            "timestamp": "2026-08-21T12:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "toolCall", "id": call_id, "name": name, "arguments": {}}
                ],
                "usage": {"totalTokens": total},
                "timestamp": start,
            },
        }
        lines.append(json.dumps(assistant))
        if end is not None:
            result = {
                "type": "message",
                "id": f"result-{idx}",
                "timestamp": "2026-08-21T12:00:01.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": call_id,
                    "toolName": name,
                    "isError": is_error,
                    "timestamp": end,
                    "content": [{"type": "text", "text": "ok"}],
                },
            }
            lines.append(json.dumps(result))
    while token_idx < len(tokens):
        total = tokens[token_idx]
        token_idx += 1
        assistant = {
            "type": "message",
            "id": f"assist-extra-{token_idx}",
            "timestamp": "2026-08-21T12:00:02.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "extra"}],
                "usage": {"totalTokens": total},
                "timestamp": 1787314140000 + token_idx,
            },
        }
        lines.append(json.dumps(assistant))
    return "\n".join(lines)


import textwrap

COLLREPORT = ROOT / "home/.pi/agent/extensions/collab-shared/report.ts"


def run_report_node(request: dict) -> dict:
    inner = json.dumps(request)
    script = textwrap.dedent(f"""
        import {{ pathToFileURL }} from "node:url";
        import path from "node:path";
        const extUrl = pathToFileURL("{COLLREPORT}");
        const mod = await import(extUrl.href);
        const req = {inner};
        let result;
        try {{
            if (req.action === "derive") {{
                const report = mod.deriveReportFromArtifacts({{
                    taskId: req.taskId,
                    ticketId: req.ticketId,
                    laneId: req.laneId,
                    workflowId: req.workflowId,
                    workflowKey: req.workflowKey,
                    childRunId: req.childRunId,
                    lanePath: req.lanePath,
                    statusObj: req.statusObj,
                    sessionText: req.sessionText}});
                result = {{ok: true, report}};
            }} else if (req.action === "publish") {{
                const res = await mod.publishReport({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    ticketId: req.ticketId,
                    laneId: req.laneId,
                    workflowId: req.workflowId,
                    workflowKey: req.workflowKey,
                    childRunId: req.childRunId,
                    lanePath: req.lanePath,
                    report: req.report}});
                result = {{ok: true, result: res}};
            }} else if (req.action === "handleCompletion") {{
                const res = await mod.handleReviewedLaneCompletion({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    ticketId: req.ticketId,
                    laneId: req.laneId,
                    lanePath: req.lanePath,
                    workflowId: req.workflowId,
                    asyncDir: req.asyncDir,
                    eventWorkflowId: req.eventWorkflowId,
                    eventAsyncDir: req.eventAsyncDir}});
                result = {{ok: true, result: res}};
            }} else if (req.action === "snapshot") {{
                await mod.snapshotLaneLoopReport({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    outputDir: req.outputDir}});
                result = {{ok: true}};
            }} else if (req.action === "role") {{
                result = {{ok: true, role: mod.roleForWorkflowKey(req.workflowKey)}};
            }} else {{
                result = {{ok: false, error: "unknown action"}};
            }}
        }} catch (e) {{
            result = {{ok: false, error: e instanceof Error ? e.message : String(e)}};
        }}
        process.stdout.write(JSON.stringify(result));
    """)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        run = subprocess.run(
            ["/usr/bin/node", "--experimental-strip-types", fname],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            raise AssertionError(
                f"node failed: {run.stderr}\n{run.stdout}\nscript:{script}"
            )
        lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
        return json.loads(lines[-1])
    finally:
        Path(fname).unlink(missing_ok=True)


class CollabReviewedLaneT06ReportTests(CollabReviewedLaneExtensionTests):
    def seed_repo_with_lane(self, base: Path) -> tuple[Path, dict[str, str], str, str]:
        repository, expected = self.managed_repository(base)
        lane_path = expected["lane"]
        control_root = str(repository.resolve())
        return repository, expected, lane_path, control_root

    def test_derive_exact_metrics_with_overlapping_intervals_and_null_durations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            workflow_key = "impl-0"
            task_id = "demo"
            ticket_id = "T001"
            lane_id = "writer-1"
            session_file = f"/tmp/{child_run_id}/session.jsonl"
            session = make_session(
                [
                    ("call1", "read", 1000, 1500, False),
                    ("call2", "bash", 1200, 1700, False),
                    ("call3", "read", 2000, None, False),
                ],
                [100, 200, 50],
            )
            status = make_status(
                workflow_id,
                lane_path,
                workflow_key,
                child_run_id,
                5,
                session_file,
                duration_ms=9999,
            )
            result = run_report_node(
                {
                    "action": "derive",
                    "taskId": task_id,
                    "ticketId": ticket_id,
                    "laneId": lane_id,
                    "workflowId": workflow_id,
                    "workflowKey": workflow_key,
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status,
                    "sessionText": session,
                }
            )
            self.assertTrue(result["ok"], result)
            report = result["report"]
            self.assertEqual(report["reportVersion"], 2)
            self.assertEqual(report["taskId"], task_id)
            self.assertEqual(report["ticketId"], ticket_id)
            self.assertEqual(report["laneId"], lane_id)
            self.assertEqual(report["workflowId"], workflow_id)
            self.assertEqual(report["workflowKey"], workflow_key)
            self.assertEqual(report["childRunId"], child_run_id)
            self.assertEqual(report["role"], "implementer")
            self.assertEqual(report["terminalState"], "completed")
            self.assertEqual(report["agentDurationMs"], 9999)
            self.assertEqual(report["turns"], 5)
            self.assertEqual(report["tokens"], 350)
            self.assertEqual(report["toolObservedDurationMs"], 1000)
            tools = report["tools"]
            self.assertEqual(tools["read"]["calls"], 2)
            self.assertEqual(tools["read"]["succeeded"], 1)
            self.assertEqual(tools["read"]["failed"], 0)
            self.assertEqual(tools["read"]["unresolved"], 1)
            self.assertEqual(tools["read"]["observedDurationsMs"], [500, None])
            self.assertEqual(tools["bash"]["calls"], 1)
            self.assertEqual(tools["bash"]["succeeded"], 1)
            self.assertEqual(tools["bash"]["failed"], 0)
            self.assertEqual(tools["bash"]["unresolved"], 0)
            self.assertEqual(tools["bash"]["observedDurationsMs"], [500])
            self.assertEqual(
                set(report.keys()),
                {
                    "reportVersion",
                    "taskId",
                    "ticketId",
                    "laneId",
                    "workflowId",
                    "workflowKey",
                    "childRunId",
                    "role",
                    "terminalState",
                    "agentDurationMs",
                    "toolObservedDurationMs",
                    "turns",
                    "tokens",
                    "tools",
                },
            )

    def test_role_identities_for_all_four_keys(self) -> None:
        for key, expected_role in [
            ("impl-0", "implementer"),
            ("impl-1", "correction"),
            ("review-0", "acceptor"),
            ("review-1", "rereview"),
        ]:
            with self.subTest(key=key):
                result = run_report_node({"action": "role", "workflowKey": key})
                self.assertTrue(result["ok"])
                self.assertEqual(result["role"], expected_role)

    def test_publish_complete_file_and_exclusive_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            workflow_key = "impl-0"
            session_file = f"/tmp/{child_run_id}/session.jsonl"
            status = make_status(
                workflow_id, lane_path, workflow_key, child_run_id, 1, session_file
            )
            session = make_session([("c1", "read", 1000, 1100, False)], [10])
            derive = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": workflow_key,
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status,
                    "sessionText": session,
                }
            )
            self.assertTrue(derive["ok"])
            report = derive["report"]
            pub1 = run_report_node(
                {
                    "action": "publish",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": workflow_key,
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "report": report,
                }
            )
            self.assertTrue(pub1["ok"])
            self.assertTrue(pub1["result"]["published"])
            container = (
                repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1"
            )
            report_file = container / f"{child_run_id}.json"
            self.assertTrue(report_file.is_file())
            content = report_file.read_text(encoding="utf-8")
            self.assertEqual(json.loads(content), report)
            self.assertEqual(oct(report_file.stat().st_mode)[-3:], "600")
            pub2 = run_report_node(
                {
                    "action": "publish",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": workflow_key,
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "report": report,
                }
            )
            self.assertTrue(pub2["ok"])
            self.assertTrue(pub2["result"].get("isDuplicate"))
            self.assertFalse(pub2["result"]["published"])
            report2 = dict(report)
            report2["tokens"] = 99999
            pub3 = run_report_node(
                {
                    "action": "publish",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": workflow_key,
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "report": report2,
                }
            )
            self.assertTrue(pub3["ok"])
            self.assertFalse(pub3["result"]["published"])
            self.assertIn("warning", pub3["result"])
            self.assertEqual(
                json.loads(report_file.read_text(encoding="utf-8")), report
            )
            warnings_file = (
                repo
                / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            )
            self.assertTrue(warnings_file.is_file())
            warnings = warnings_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(warnings), 1)
            last = json.loads(warnings[-1])
            self.assertEqual(last["taskId"], "demo")
            self.assertEqual(last["laneId"], "writer-1")

    def test_missing_and_mismatched_session_produce_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            workflow_key = "impl-0"
            async_dir = base / "async-missing"
            async_dir.mkdir()
            missing_session = str(async_dir / child_run_id / "missing.jsonl")
            status = make_status(
                workflow_id, lane_path, workflow_key, child_run_id, 1, missing_session
            )
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            seed_task_container(repo)
            result = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["result"]["handled"])
            self.assertEqual(len(result["result"]["published"]), 0)
            self.assertGreaterEqual(len(result["result"]["warnings"]), 1)
            async_dir2 = base / "async-mismatch"
            async_dir2.mkdir()
            mismatched_session = str(async_dir2 / "wrong" / "session.jsonl")
            Path(mismatched_session).parent.mkdir(parents=True, exist_ok=True)
            Path(mismatched_session).write_text(
                make_session([("c1", "read", 1000, 1100, False)], [10]),
                encoding="utf-8",
            )
            status_mismatch = make_status(
                workflow_id,
                lane_path,
                workflow_key,
                child_run_id,
                1,
                mismatched_session,
            )
            (async_dir2 / "status.json").write_text(
                json.dumps(status_mismatch), encoding="utf-8"
            )
            result2 = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir2),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir2),
                }
            )
            self.assertTrue(result2["ok"])
            self.assertGreaterEqual(len(result2["result"]["warnings"]), 1)
            warnings_file = (
                repo
                / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            )
            self.assertTrue(warnings_file.is_file())
            self.assertFalse(
                (
                    Path(control_root)
                    / ".agent_state/.collab_op_operation_warnings.jsonl"
                ).exists()
            )

    def test_unsafe_warning_fallback_for_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            unsafe_lane = "../evil"
            report = {
                "reportVersion": 1,
                "taskId": "demo",
                "ticketId": "T001",
                "laneId": unsafe_lane,
                "workflowId": workflow_id,
                "workflowKey": "impl-0",
                "childRunId": child_run_id,
                "role": "implementer",
                "agentDurationMs": 1,
                "toolObservedDurationMs": 0,
                "turns": 1,
                "tokens": 10,
                "tools": {},
            }
            pub = run_report_node(
                {
                    "action": "publish",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": unsafe_lane,
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "report": report,
                }
            )
            self.assertTrue(pub["ok"])
            self.assertFalse(pub["result"]["published"])
            self.assertIn("warning", pub["result"])
            self.assertFalse((Path(control_root) / "evil").exists())
            self.assertFalse(
                (
                    Path(control_root)
                    / ".agent_state/.collab_op_operation_warnings.jsonl"
                ).exists()
            )
            self.assertIn("unsafe", pub["result"]["warning"].lower())

    def test_warning_fifo_falls_back_without_opening_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            warnings_file = (
                repo
                / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            )
            warnings_file.parent.mkdir(parents=True)
            os.mkfifo(warnings_file)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            report_file = warnings_file.parent / "writer-1" / f"{child_run_id}.json"
            report_file.parent.mkdir()
            report_file.write_text("different\n", encoding="utf-8")
            report = {
                "reportVersion": 1,
                "taskId": "demo",
                "ticketId": "T001",
                "laneId": "writer-1",
                "workflowId": workflow_id,
                "workflowKey": "impl-0",
                "childRunId": child_run_id,
                "role": "implementer",
                "agentDurationMs": 1,
                "toolObservedDurationMs": 0,
                "turns": 1,
                "tokens": 10,
                "tools": {},
            }
            pub = run_report_node(
                {
                    "action": "publish",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "report": report,
                }
            )
            self.assertTrue(pub["ok"], pub)
            self.assertFalse(pub["result"]["published"])
            self.assertIn("not a regular file", pub["result"]["warning"])
            self.assertTrue(warnings_file.is_fifo())

    def test_existing_report_fifo_warns_without_reading_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            report_file = (
                repo
                / f".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1/{child_run_id}.json"
            )
            report_file.parent.mkdir(parents=True)
            os.mkfifo(report_file)
            report = {
                "reportVersion": 1,
                "taskId": "demo",
                "ticketId": "T001",
                "laneId": "writer-1",
                "workflowId": workflow_id,
                "workflowKey": "impl-0",
                "childRunId": child_run_id,
                "role": "implementer",
                "agentDurationMs": 1,
                "toolObservedDurationMs": 0,
                "turns": 1,
                "tokens": 10,
                "tools": {},
            }
            pub = run_report_node(
                {
                    "action": "publish",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "report": report,
                }
            )
            self.assertTrue(pub["ok"], pub)
            self.assertFalse(pub["result"]["published"])
            self.assertIn("not a regular file", pub["result"]["warning"])
            self.assertTrue(report_file.is_fifo())
            warnings_file = report_file.parents[1] / "warnings.jsonl"
            self.assertEqual(
                len(warnings_file.read_text(encoding="utf-8").splitlines()), 1
            )

    def test_snapshot_rejects_symlinked_destination_ancestor_before_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _expected, _lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            foreign = base / "foreign"
            foreign_report = foreign / "lane_loop_report"
            foreign_report.mkdir(parents=True)
            sentinel = foreign_report / "sentinel"
            sentinel.write_text("foreign\n", encoding="utf-8")
            (repo / "reports-link").symlink_to(foreign, target_is_directory=True)
            snap = run_report_node(
                {
                    "action": "snapshot",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "outputDir": "reports-link",
                }
            )
            self.assertFalse(snap["ok"], snap)
            self.assertIn("ancestry is unsafe", snap["error"])
            self.assertNotIn("already exists", snap["error"])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "foreign\n")

    def test_exact_completion_with_nonterminal_status_warns_and_handles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            async_dir = base / "async-nonterminal"
            async_dir.mkdir()
            status = make_status(
                workflow_id,
                lane_path,
                "impl-0",
                child_run_id,
                1,
                str(async_dir / child_run_id / "session.jsonl"),
            )
            status["state"] = "running"
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["result"]["handled"])
            self.assertEqual(
                result["result"]["ignoredReason"], "nonterminal status artifact"
            )
            self.assertEqual(len(result["result"]["warnings"]), 1)
            warnings_file = (
                repo
                / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            )
            self.assertEqual(
                len(warnings_file.read_text(encoding="utf-8").splitlines()), 1
            )

    def test_partial_then_exact_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            async_dir = base / "async-partial"
            async_dir.mkdir()
            child_session_dir = async_dir / child_run_id
            child_session_dir.mkdir(parents=True)
            session_path = child_session_dir / "session.jsonl"
            session_path.write_text(
                make_session([("c1", "read", 1000, 1100, False)], [10]),
                encoding="utf-8",
            )
            status = make_status(
                workflow_id, lane_path, "impl-0", child_run_id, 1, str(session_path)
            )
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result_partial = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result_partial["ok"])
            self.assertFalse(result_partial["result"]["handled"])
            self.assertEqual(len(result_partial["result"]["published"]), 0)
            result_partial2 = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": "/tmp/wrong/async",
                }
            )
            self.assertTrue(result_partial2["ok"])
            self.assertFalse(result_partial2["result"]["handled"])
            result_exact = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result_exact["ok"])
            self.assertTrue(result_exact["result"]["handled"])
            self.assertEqual(len(result_exact["result"]["published"]), 1)
            report_file = (
                repo
                / f".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1/{child_run_id}.json"
            )
            self.assertTrue(report_file.is_file())

    def test_wrapper_counts_once_and_structured_output_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _repo, expected, lane_path, _control = self.seed_repo_with_lane(base)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            session_file = f"/tmp/{child_run_id}/session.jsonl"
            session = make_session(
                [
                    ("wrapper1", "mcpScript", 1000, 1500, False),
                    ("struct1", "structured_output", 2000, 2100, False),
                    ("read1", "read", 3000, 3100, False),
                ],
                [100, 100, 100],
            )
            status = make_status(
                workflow_id, lane_path, "impl-0", child_run_id, 2, session_file
            )
            result = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status,
                    "sessionText": session,
                }
            )
            self.assertTrue(result["ok"])
            tools = result["report"]["tools"]
            self.assertEqual(tools["mcpScript"]["calls"], 1)
            self.assertEqual(tools["structured_output"]["calls"], 1)
            self.assertEqual(tools["read"]["calls"], 1)
            self.assertEqual(len(tools), 3)

    def test_duplicate_trace_and_step_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            session_file = f"/tmp/{child_run_id}/session.jsonl"
            session = make_session([("c1", "read", 1000, 1100, False)], [10])
            status_dup_trace = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {
                    "trace": [
                        {
                            "key": "impl-0",
                            "runId": child_run_id,
                            "durationMs": 100,
                            "state": "completed",
                        },
                        {
                            "key": "impl-0",
                            "runId": child_run_id,
                            "durationMs": 200,
                            "state": "completed",
                        },
                    ],
                    "emits": [],
                    "console": [],
                },
                "steps": [
                    {
                        "workflowKey": "impl-0",
                        "parentWorkflowRunId": workflow_id,
                        "status": "completed",
                        "turnCount": 1,
                        "sessionFile": session_file,
                    }
                ],
            }
            result = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status_dup_trace,
                    "sessionText": session,
                }
            )
            self.assertFalse(result["ok"])
            self.assertIn("duplicate", result["error"].lower())
            status_dup_step = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {
                    "trace": [
                        {
                            "key": "impl-0",
                            "runId": child_run_id,
                            "durationMs": 100,
                            "state": "completed",
                        }
                    ],
                    "emits": [],
                    "console": [],
                },
                "steps": [
                    {
                        "workflowKey": "impl-0",
                        "parentWorkflowRunId": workflow_id,
                        "status": "completed",
                        "turnCount": 1,
                        "sessionFile": session_file,
                    },
                    {
                        "workflowKey": "impl-0",
                        "parentWorkflowRunId": workflow_id,
                        "status": "completed",
                        "turnCount": 2,
                        "sessionFile": session_file,
                    },
                ],
            }
            result2 = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status_dup_step,
                    "sessionText": session,
                }
            )
            self.assertFalse(result2["ok"])
            self.assertIn("duplicate", result2["error"].lower())

    def test_correlation_requires_absolute_session_path_with_child_segment(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            session = make_session([("c1", "read", 1000, 1100, False)], [10])
            status_rel = make_status(
                workflow_id,
                lane_path,
                "impl-0",
                child_run_id,
                1,
                "relative/session.jsonl",
            )
            result = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status_rel,
                    "sessionText": session,
                }
            )
            self.assertFalse(result["ok"])
            self.assertIn("absolute", result["error"].lower())
            status_mismatch = make_status(
                workflow_id,
                lane_path,
                "impl-0",
                child_run_id,
                1,
                "/tmp/wrong/session.jsonl",
            )
            result2 = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status_mismatch,
                    "sessionText": session,
                }
            )
            self.assertFalse(result2["ok"])
            self.assertIn("childrunid", result2["error"].lower())

    def test_wrong_lane_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _repo, expected, lane_path, _control = self.seed_repo_with_lane(base)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            session_file = f"/tmp/{child_run_id}/session.jsonl"
            session = make_session([("c1", "read", 1000, 1100, False)], [10])
            # correct lane should succeed
            status_ok = make_status(
                workflow_id, lane_path, "impl-0", child_run_id, 1, session_file
            )
            ok = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status_ok,
                    "sessionText": session,
                }
            )
            self.assertTrue(ok["ok"], ok)
            # wrong lane must be rejected via normalized cwd mismatch
            wrong_lane = (
                lane_path + "-other"
                if not lane_path.endswith("/")
                else lane_path + "other"
            )
            # also test with trailing slash normalization
            status_wrong = make_status(
                workflow_id, lane_path, "impl-0", child_run_id, 1, session_file
            )
            wrong = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": wrong_lane,
                    "statusObj": status_wrong,
                    "sessionText": session,
                }
            )
            self.assertFalse(wrong["ok"])
            self.assertIn("lane", wrong["error"].lower())
            # also via handleCompletion path
            with tempfile.TemporaryDirectory() as tmp2:
                base2 = Path(tmp2)
                repo2, expected2, lane_path2, control_root2 = self.seed_repo_with_lane(
                    base2
                )
                seed_task_container(repo2)
                async_dir = base2 / "async-wrong-lane"
                async_dir.mkdir()
                child_run_id2 = "33333333-3333-3333-3333-333333333333"
                workflow_id2 = "44444444-4444-4444-4444-444444444444"
                sess_dir = async_dir / child_run_id2
                sess_dir.mkdir(parents=True)
                sess_path = sess_dir / "session.jsonl"
                sess_path.write_text(
                    make_session([("c1", "read", 1000, 1100, False)], [10]),
                    encoding="utf-8",
                )
                status2 = make_status(
                    workflow_id2, lane_path2, "impl-0", child_run_id2, 1, str(sess_path)
                )
                (async_dir / "status.json").write_text(
                    json.dumps(status2), encoding="utf-8"
                )
                wrong_lane2 = str(Path(lane_path2).parent / "other-lane")
                res = run_report_node(
                    {
                        "action": "handleCompletion",
                        "repoControlRoot": control_root2,
                        "taskId": "demo",
                        "ticketId": "T001",
                        "laneId": "writer-1",
                        "lanePath": wrong_lane2,
                        "workflowId": workflow_id2,
                        "asyncDir": str(async_dir),
                        "eventWorkflowId": workflow_id2,
                        "eventAsyncDir": str(async_dir),
                    }
                )
                self.assertTrue(res["ok"])
                self.assertTrue(res["result"]["handled"])
                self.assertEqual(len(res["result"]["published"]), 0)
                self.assertGreaterEqual(len(res["result"]["warnings"]), 1)
                warnings_file = (
                    repo2
                    / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
                )
                self.assertTrue(warnings_file.is_file())
                self.assertFalse(
                    (
                        Path(control_root2)
                        / ".agent_state/.collab_op_operation_warnings.jsonl"
                    ).exists()
                )

    def test_same_name_calls_first_missing_second_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _repo, expected, lane_path, _control = self.seed_repo_with_lane(base)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            session_file = f"/tmp/{child_run_id}/session.jsonl"
            # Two same-name tool calls: first missing result, second completes with 100ms duration
            session = make_session(
                [
                    ("call1", "read", 1000, None, False),
                    ("call2", "read", 2000, 2100, False),
                ],
                [10, 10],
            )
            status = make_status(
                workflow_id, lane_path, "impl-0", child_run_id, 1, session_file
            )
            result = run_report_node(
                {
                    "action": "derive",
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "statusObj": status,
                    "sessionText": session,
                }
            )
            self.assertTrue(result["ok"], result)
            tools = result["report"]["tools"]
            self.assertIn("read", tools)
            self.assertEqual(tools["read"]["calls"], 2)
            self.assertEqual(tools["read"]["succeeded"], 1)
            self.assertEqual(tools["read"]["failed"], 0)
            self.assertEqual(tools["read"]["unresolved"], 1)
            self.assertEqual(tools["read"]["observedDurationsMs"], [None, 100])
            self.assertEqual(result["report"]["toolObservedDurationMs"], 100)

    def test_listener_exception_retires_pending_and_partial_remains(self) -> None:
        script = textwrap.dedent(f'''
            import {{ createRequire }} from "node:module";
            const require = createRequire('/home/axel/.pi/agent/npm/package.json');
            const createJiti = require('jiti');
            const jiti = createJiti('/home/axel/.pi/agent/npm/package.json', {{ alias: {{ "@earendil-works/pi-coding-agent": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js" }}, fsCache:false, moduleCache:false }});
            const laneMod = jiti("{ROOT / "home/.pi/agent/extensions/collab-reviewed-lane.ts"}");
            const harness = laneMod.createIsolatedReviewedLaneHarness();
            let warned = null;
            const origWarn = console.warn;
            console.warn = (msg) => {{ warned = String(msg); try {{ origWarn(String(msg)); }} catch {{}} }};
            function createFakePi() {{
              const handlers = new Map();
              return {{
                events: {{
                  on: (event, handler) => {{
                    if (!handlers.has(event)) handlers.set(event, []);
                    handlers.get(event).push(handler);
                    return () => {{
                      const arr = handlers.get(event) || [];
                      const idx = arr.indexOf(handler);
                      if (idx !== -1) arr.splice(idx, 1);
                    }};
                  }},
                  emit: (event, data) => {{
                    const arr = handlers.get(event) || [];
                    for (const h of [...arr]) h(data);
                  }}
                }},
                _handlers: handlers
              }};
            }}
            const fakePi = createFakePi();
            const failingDeps = {{
              withTaskLock: async () => {{ throw new Error("injected lock failure for test"); }},
              error: (code, msg) => new Error(msg)}};
            harness.registerPending({{
              pi: fakePi,
              repo: {{ controlRoot: "/tmp/repo", gitDir: "/tmp/repo/.git", worktreeRoot: "/tmp/repo", git: async () => ({{}}) }},
              taskId: "demo",
              ticketId: "T001",
              laneId: "writer-1",
              lanePath: "/tmp/lane",
              workflowId: "11111111-1111-1111-1111-111111111111",
              asyncDir: "/tmp/async",
              deps: failingDeps
            }});
            if (harness.getPendingCount() !== 1) throw new Error("setup failed");
            fakePi.events.emit("subagent:async-complete", {{ runId: "11111111-1111-1111-1111-111111111111", asyncDir: "/tmp/async" }});
            await new Promise(r => setTimeout(r, 1300));
            if (harness.getPendingCount() !== 0) throw new Error("pending not retired on exact tuple exception");
            if (!warned || !warned.toLowerCase().includes("injected")) throw new Error("warning not emitted on lock exception: " + String(warned));
            if (warned && warned.includes(".collab_op_operation_warnings")) throw new Error("should not create operation warnings file");
            warned = null;
            const fakePi2 = createFakePi();
            const harness2 = laneMod.createIsolatedReviewedLaneHarness();
            const okDeps = {{
              withTaskLock: async () => {{ throw new Error("should not be called for partial"); }},
              error: (code, msg) => new Error(msg)}};
            harness2.registerPending({{
              pi: fakePi2,
              repo: {{ controlRoot: "/tmp/repo", gitDir: "/tmp/repo/.git", worktreeRoot: "/tmp/repo", git: async () => ({{}}) }},
              taskId: "demo",
              ticketId: "T001",
              laneId: "writer-1",
              lanePath: "/tmp/lane",
              workflowId: "22222222-2222-2222-2222-222222222222",
              asyncDir: "/tmp/async-exact",
              deps: okDeps
            }});
            fakePi2.events.emit("subagent:async-complete", {{ runId: "22222222-2222-2222-2222-222222222222", asyncDir: "/tmp/wrong" }});
            await new Promise(r => setTimeout(r, 30));
            if (harness2.getPendingCount() !== 1) throw new Error("partial event should not retire pending");
            if (warned) throw new Error("partial should not warn");
            fakePi2.events.emit("subagent:async-complete", {{ runId: "wrong-id", asyncDir: "/tmp/async-exact" }});
            await new Promise(r => setTimeout(r, 30));
            if (harness2.getPendingCount() !== 1) throw new Error("unrelated event should not retire");
            console.warn = origWarn;
            process.stdout.write(JSON.stringify({{ok:true}}));
        ''')
        import subprocess, textwrap as _tw, json as _json, tempfile as _tf
        from pathlib import Path as _P

        with _tf.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as f:
            f.write(script)
            fname = f.name
        try:
            run = subprocess.run(
                ["/usr/bin/node", fname], capture_output=True, text=True
            )
            self.assertEqual(
                run.returncode, 0, f"node failed: {run.stderr}\\n{run.stdout}"
            )
            out = _json.loads(run.stdout.strip().splitlines()[-1])
            self.assertTrue(out.get("ok"))
            # ensure no global operation warnings file was created at repo control root (our dummy /tmp/repo should not have file)
            self.assertFalse(
                (
                    _P("/tmp/repo") / ".agent_state/.collab_op_operation_warnings.jsonl"
                ).exists()
            )
        finally:
            _P(fname).unlink(missing_ok=True)


def run_feedback_node(request: dict) -> dict:
    inner = json.dumps(request)
    script = textwrap.dedent(f"""
        import {{ pathToFileURL }} from "node:url";
        const extUrl = pathToFileURL("{COLLREPORT}");
        const mod = await import(extUrl.href);
        const req = {inner};
        let result;
        try {{
            if (req.action === "publishFeedback") {{
                const res = await mod.publishFeedback({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    ticketId: req.ticketId,
                    laneId: req.laneId,
                    workflowId: req.workflowId,
                    workflowKey: req.workflowKey,
                    childRunId: req.childRunId,
                    lanePath: req.lanePath,
                    efficiencyFeedback: req.efficiencyFeedback}});
                result = {{ok: true, result: res}};
            }} else if (req.action === "snapshotFeedback") {{
                await mod.snapshotLaneLoopFeedback({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    outputDir: req.outputDir}});
                result = {{ok: true}};
            }} else if (req.action === "snapshotReport") {{
                await mod.snapshotLaneLoopReport({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    outputDir: req.outputDir}});
                result = {{ok: true}};
            }} else if (req.action === "preflight") {{
                await mod.preflightSnapshot({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    outputDir: req.outputDir,
                    subtree: req.subtree}});
                result = {{ok: true}};
            }} else {{
                result = {{ok: false, error: "unknown action"}};
            }}
        }} catch (e) {{
            result = {{ok: false, error: e instanceof Error ? e.message : String(e)}};
        }}
        process.stdout.write(JSON.stringify(result));
    """)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        run = subprocess.run(
            ["/usr/bin/node", "--experimental-strip-types", fname],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            raise AssertionError(
                f"node failed: {run.stderr}\n{run.stdout}\nscript:{script}"
            )
        lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
        return json.loads(lines[-1])
    finally:
        Path(fname).unlink(missing_ok=True)


COLL_RESULT_SCHEMA = ROOT / "home/.pi/agent/extensions/collab-shared/result-schema.ts"


def run_schema_validation(request: dict) -> dict:
    inner = json.dumps(request)
    script = textwrap.dedent(f"""
        import {{ pathToFileURL }} from "node:url";
        const extUrl = pathToFileURL("{COLL_RESULT_SCHEMA}");
        const mod = await import(extUrl.href);
        const req = {inner};
        let result;
        try {{
            if (req.kind === "worker") {{
                result = {{ok: true, valid: mod.isValidWorkerOutput(req.value)}};
            }} else if (req.kind === "reviewer") {{
                result = {{ok: true, valid: mod.isValidReviewerOutput(req.value)}};
            }} else if (req.kind === "structured") {{
                result = {{ok: true, valid: mod.isValidStructuredOutput(req.workflowKey, req.value)}};
            }} else {{
                result = {{ok: false, error: "unknown kind"}};
            }}
        }} catch (e) {{
            result = {{ok: false, error: e instanceof Error ? e.message : String(e)}};
        }}
        process.stdout.write(JSON.stringify(result));
    """)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        run = subprocess.run(
            ["/usr/bin/node", "--experimental-strip-types", fname],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            raise AssertionError(
                f"node schema validation failed: {run.stderr}\n{run.stdout}"
            )
        lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
        return json.loads(lines[-1])
    finally:
        Path(fname).unlink(missing_ok=True)


def run_blocker_schema_agreement(cases: list[dict]) -> dict:
    """For each candidate blocker object, independently evaluate it against the
    declared JSON Schema shape (a generic, from-scratch reader of `required` /
    `properties` / `additionalProperties`, not a copy of the hand-written
    validator's field list) and against `isValidReviewerOutput`, wrapped in a
    minimal well-formed BLOCKED reviewer envelope. Returns both verdicts per
    case so a Python assertion can compare them instead of the claim resting
    on reading both by eye."""
    inner = json.dumps(cases)
    script = textwrap.dedent(f"""
        import {{ pathToFileURL }} from "node:url";
        const mod = await import(pathToFileURL("{COLL_RESULT_SCHEMA}").href);
        const cases = {inner};

        const blockedBranch = mod.reviewedLaneReviewerSchema.oneOf.find(
          (branch) => branch.properties && branch.properties.verdict && branch.properties.verdict.const === "BLOCKED"
        );
        const blockerItemSchema = blockedBranch.properties.blockers.items;

        function schemaSaysValid(schema, value) {{
          if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
          const keys = Object.keys(value);
          if (schema.additionalProperties === false) {{
            for (const k of keys) {{
              if (!(k in schema.properties)) return false;
            }}
          }}
          for (const req of schema.required || []) {{
            if (!(req in value)) return false;
          }}
          for (const [k, v] of Object.entries(value)) {{
            const propSchema = schema.properties[k];
            if (!propSchema) continue;
            if (propSchema.type === "string" && typeof v !== "string") return false;
          }}
          return true;
        }}

        const results = cases.map((blocker) => {{
          const schemaVerdict = schemaSaysValid(blockerItemSchema, blocker);
          const wrapped = {{ verdict: "BLOCKED", correctionBase: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2", blockers: [blocker] }};
          const validatorVerdict = mod.isValidReviewerOutput(wrapped);
          return {{ blocker, schemaVerdict, validatorVerdict }};
        }});
        process.stdout.write(JSON.stringify({{ok: true, results}}));
    """)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        run = subprocess.run(
            ["/usr/bin/node", "--experimental-strip-types", fname],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            raise AssertionError(
                f"node blocker schema agreement check failed: {run.stderr}\n{run.stdout}"
            )
        lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
        return json.loads(lines[-1])
    finally:
        Path(fname).unlink(missing_ok=True)


def valid_worker_completed(feedback: str | None) -> dict:
    base: dict = {"outcome": "COMPLETED"}
    if feedback is not None:
        base["efficiencyFeedback"] = feedback
    return base


def valid_worker_blocked(feedback: str | None) -> dict:
    base: dict = {"outcome": "BLOCKED", "blocker": "blocked"}
    if feedback is not None:
        base["efficiencyFeedback"] = feedback
    return base


def valid_worker_needs(feedback: str | None) -> dict:
    base: dict = {
        "outcome": "NEEDS_DECISION",
        "decision": {"why": "why", "question": "q"},
    }
    if feedback is not None:
        base["efficiencyFeedback"] = feedback
    return base


def valid_reviewer_pass(feedback: str | None) -> dict:
    base: dict = {"verdict": "PASS"}
    if feedback is not None:
        base["efficiencyFeedback"] = feedback
    return base


def valid_reviewer_blocked(feedback: str | None) -> dict:
    base: dict = {
        "verdict": "BLOCKED",
        "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        "blockers": [{"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}],
    }
    if feedback is not None:
        base["efficiencyFeedback"] = feedback
    return base


def valid_reviewer_needs(feedback: str | None) -> dict:
    base: dict = {
        "verdict": "NEEDS_DECISION",
        "decision": {"why": "why", "question": "q"},
    }
    if feedback is not None:
        base["efficiencyFeedback"] = feedback
    return base


def make_status_with_feedback(
    workflow_id: str,
    lane_path: str,
    workflow_key: str,
    child_run_id: str,
    turn_count: int,
    session_file: str,
    feedback: object,
    duration_ms: int = 12345,
    state: str = "complete",
) -> dict[str, object]:
    base = make_status(
        workflow_id,
        lane_path,
        workflow_key,
        child_run_id,
        turn_count,
        session_file,
        duration_ms,
        state,
    )
    steps = base["steps"]  # type: ignore
    is_worker = workflow_key.startswith("impl-")
    if isinstance(feedback, str) and feedback == "__OMIT__":
        # valid structure without efficiencyFeedback
        if is_worker:
            steps[0]["structuredOutput"] = valid_worker_completed(None)  # type: ignore
        else:
            steps[0]["structuredOutput"] = valid_reviewer_pass(None)  # type: ignore
    elif feedback is None:
        if is_worker:
            steps[0]["structuredOutput"] = valid_worker_completed(None)  # type: ignore
        else:
            steps[0]["structuredOutput"] = valid_reviewer_pass(None)  # type: ignore
    else:
        # feedback is string (including "" and 10000/10001) or other type for negative tests
        if is_worker:
            # choose COMPLETED as default for worker feedback tests
            if isinstance(feedback, str):
                steps[0]["structuredOutput"] = valid_worker_completed(feedback)  # type: ignore
            else:
                # for invalid type test, still produce valid structure but with invalid feedback type
                steps[0]["structuredOutput"] = {
                    "outcome": "COMPLETED",
                    "efficiencyFeedback": feedback,
                }  # type: ignore
        else:
            if isinstance(feedback, str):
                steps[0]["structuredOutput"] = valid_reviewer_pass(feedback)  # type: ignore
            else:
                steps[0]["structuredOutput"] = {
                    "verdict": "PASS",
                    "efficiencyFeedback": feedback,
                }  # type: ignore
    return base


class CollabReviewedLaneT07FeedbackTests(CollabReviewedLaneT06ReportTests):
    def test_omission_creates_no_artifact_plans_and_archives(self) -> None:
        for kind, structured in (
            ("worker", valid_worker_completed(None)),
            ("reviewer", valid_reviewer_pass(None)),
        ):
            with self.subTest(kind=kind):
                valid = run_schema_validation({"kind": kind, "value": structured})
                self.assertTrue(valid["ok"], valid)
                self.assertTrue(
                    valid["valid"], f"omitted feedback must remain valid for {kind}"
                )

        for archived in (False, True):
            with self.subTest(archived=archived), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
                seed_task_container(repo, archived=archived)
                workflow_id = "11111111-1111-1111-1111-111111111111"
                child_run_id = "22222222-2222-2222-2222-222222222222"
                async_dir = base / "async-omission"
                async_dir.mkdir()
                sess_dir = async_dir / child_run_id
                sess_dir.mkdir(parents=True)
                sess_path = sess_dir / "session.jsonl"
                sess_path.write_text(
                    make_session([("c1", "read", 1000, 1100, False)], [10]),
                    encoding="utf-8",
                )
                status = make_status_with_feedback(
                    workflow_id,
                    lane_path,
                    "impl-0",
                    child_run_id,
                    1,
                    str(sess_path),
                    "__OMIT__",
                )
                (async_dir / "status.json").write_text(
                    json.dumps(status), encoding="utf-8"
                )
                result = run_report_node(
                    {
                        "action": "handleCompletion",
                        "repoControlRoot": control_root,
                        "taskId": "demo",
                        "ticketId": "T001",
                        "laneId": "writer-1",
                        "lanePath": lane_path,
                        "workflowId": workflow_id,
                        "asyncDir": str(async_dir),
                        "eventWorkflowId": workflow_id,
                        "eventAsyncDir": str(async_dir),
                    }
                )
                self.assertTrue(result["ok"], result)
                self.assertTrue(result["result"]["handled"])
                self.assertEqual(len(result["result"]["published"]), 1)
                container = repo / (
                    ".agent_state/archives/demo"
                    if archived
                    else ".agent_state/plans/demo"
                )
                feedback_file = (
                    container
                    / ".collab_op/lane_loop_feedback/writer-1"
                    / f"{child_run_id}.json"
                )
                self.assertFalse(feedback_file.exists())
                warnings_file = (
                    container / ".collab_op/lane_loop_feedback/warnings.jsonl"
                )
                if warnings_file.exists():
                    self.assertNotIn(
                        "efficiencyFeedback", warnings_file.read_text(encoding="utf-8")
                    )

    def test_empty_and_10000_bmp_nonbmp_via_registered_schema(self) -> None:
        cases = [
            ("", "empty"),
            ("a" * 10000, "bmp-10000"),
            ("😀" * 10000, "nonbmp-10000"),
        ]
        for feedback, label in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
                seed_task_container(repo)
                workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
                # validate via registered adapter schema first
                valid = run_schema_validation(
                    {"kind": "worker", "value": valid_worker_completed(feedback)}
                )
                self.assertTrue(valid["ok"], valid)
                self.assertTrue(
                    valid["valid"], f"{label} should pass registered schema"
                )
                async_dir = base / f"async-{label}"
                async_dir.mkdir()
                sess_dir = async_dir / child_run_id
                sess_dir.mkdir(parents=True)
                sess_path = sess_dir / "session.jsonl"
                sess_path.write_text(
                    make_session([("c1", "read", 1000, 1100, False)], [10]),
                    encoding="utf-8",
                )
                status = make_status_with_feedback(
                    workflow_id,
                    lane_path,
                    "impl-0",
                    child_run_id,
                    1,
                    str(sess_path),
                    feedback,
                )
                (async_dir / "status.json").write_text(
                    json.dumps(status), encoding="utf-8"
                )
                result = run_report_node(
                    {
                        "action": "handleCompletion",
                        "repoControlRoot": control_root,
                        "taskId": "demo",
                        "ticketId": "T001",
                        "laneId": "writer-1",
                        "lanePath": lane_path,
                        "workflowId": workflow_id,
                        "asyncDir": str(async_dir),
                        "eventWorkflowId": workflow_id,
                        "eventAsyncDir": str(async_dir),
                    }
                )
                self.assertTrue(result["ok"], result)
                feedback_file = (
                    repo
                    / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1"
                    / f"{child_run_id}.json"
                )
                self.assertTrue(feedback_file.is_file(), f"{label} should be accepted")
                payload = json.loads(feedback_file.read_text(encoding="utf-8"))
                self.assertEqual(payload["efficiencyFeedback"], feedback)
                content = feedback_file.read_text(encoding="utf-8")
                self.assertEqual(
                    content,
                    json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
                    + "\n",
                )

    def test_10001_bmp_nonbmp_rejected_via_registered_schema(self) -> None:
        for char, label in [("a", "bmp"), ("😀", "nonbmp")]:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
                seed_task_container(repo)
                workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
                feedback = char * 10001
                self.assertEqual(len([*feedback]), 10001)
                invalid = run_schema_validation(
                    {"kind": "worker", "value": valid_worker_completed(feedback)}
                )
                self.assertTrue(invalid["ok"], invalid)
                self.assertFalse(
                    invalid["valid"], f"{label} 10001 should fail registered schema"
                )
                pub = run_feedback_node(
                    {
                        "action": "publishFeedback",
                        "repoControlRoot": control_root,
                        "taskId": "demo",
                        "ticketId": "T001",
                        "laneId": "writer-1",
                        "workflowId": workflow_id,
                        "workflowKey": "impl-0",
                        "childRunId": child_run_id,
                        "lanePath": lane_path,
                        "efficiencyFeedback": feedback,
                    }
                )
                self.assertTrue(pub["ok"], pub)
                self.assertFalse(pub["result"]["published"])
                self.assertIn("warning", pub["result"])
                feedback_file = (
                    repo
                    / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1"
                    / f"{child_run_id}.json"
                )
                self.assertFalse(feedback_file.exists())
                async_dir = base / f"async-10001-{label}"
                async_dir.mkdir()
                sess_dir = async_dir / child_run_id
                sess_dir.mkdir(parents=True)
                sess_path = sess_dir / "session.jsonl"
                sess_path.write_text(
                    make_session([("c1", "read", 1000, 1100, False)], [10]),
                    encoding="utf-8",
                )
                status = make_status_with_feedback(
                    workflow_id,
                    lane_path,
                    "impl-0",
                    child_run_id,
                    1,
                    str(sess_path),
                    feedback,
                )
                (async_dir / "status.json").write_text(
                    json.dumps(status), encoding="utf-8"
                )
                result = run_report_node(
                    {
                        "action": "handleCompletion",
                        "repoControlRoot": control_root,
                        "taskId": "demo",
                        "ticketId": "T001",
                        "laneId": "writer-1",
                        "lanePath": lane_path,
                        "workflowId": workflow_id,
                        "asyncDir": str(async_dir),
                        "eventWorkflowId": workflow_id,
                        "eventAsyncDir": str(async_dir),
                    }
                )
                self.assertTrue(result["ok"], result)
                self.assertFalse(
                    (
                        repo
                        / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1"
                        / f"{child_run_id}.json"
                    ).exists()
                )
                self.assertGreaterEqual(len(result["result"]["warnings"]), 1)

    def test_blocker_schema_and_validator_agree_on_every_case(self) -> None:
        well_formed = {"where": "w", "why": "y", "howToFix": "h", "trigger": "t"}
        cases = [
            well_formed,
            {k: v for k, v in well_formed.items() if k != "where"},
            {k: v for k, v in well_formed.items() if k != "why"},
            {k: v for k, v in well_formed.items() if k != "howToFix"},
            {k: v for k, v in well_formed.items() if k != "trigger"},
            {**well_formed, "extra": "not allowed"},
            {**well_formed, "trigger": 5},
            {"location": "x", "reason": "y", "fix": "z"},
        ]
        outcome = run_blocker_schema_agreement(cases)
        self.assertTrue(outcome["ok"], outcome)
        for result in outcome["results"]:
            self.assertEqual(
                result["schemaVerdict"],
                result["validatorVerdict"],
                f"schema and isValidReviewerOutput disagree on {result['blocker']}",
            )
        # Sanity: the well-formed case is accepted by both, and the
        # missing-trigger case is rejected by both, so this is not a vacuous pass.
        self.assertTrue(outcome["results"][0]["schemaVerdict"])
        self.assertTrue(outcome["results"][0]["validatorVerdict"])
        self.assertFalse(outcome["results"][4]["schemaVerdict"])
        self.assertFalse(outcome["results"][4]["validatorVerdict"])

    def test_all_six_branches_via_registered_adapter(self) -> None:
        branches = [
            ("impl-0", valid_worker_completed("impl completed"), "worker COMPLETED"),
            ("impl-0", valid_worker_blocked("impl blocked"), "worker BLOCKED"),
            ("impl-0", valid_worker_needs("impl needs"), "worker NEEDS_DECISION"),
            ("review-0", valid_reviewer_pass("review pass"), "reviewer PASS"),
            ("review-0", valid_reviewer_blocked("review blocked"), "reviewer BLOCKED"),
            (
                "review-0",
                valid_reviewer_needs("review needs"),
                "reviewer NEEDS_DECISION",
            ),
        ]
        for workflow_key, structured, label in branches:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
                seed_task_container(repo)
                workflow_id = "11111111-1111-1111-1111-111111111111"
                child_run_id = "22222222-2222-2222-2222-222222222222"
                kind = "worker" if workflow_key.startswith("impl") else "reviewer"
                valid = run_schema_validation({"kind": kind, "value": structured})
                self.assertTrue(valid["ok"], valid)
                self.assertTrue(
                    valid["valid"], f"{label} should pass registered schema"
                )
                async_dir = base / "async-branch"
                async_dir.mkdir()
                sess_dir = async_dir / child_run_id
                sess_dir.mkdir(parents=True)
                sess_path = sess_dir / "session.jsonl"
                sess_path.write_text(
                    make_session([("c1", "read", 1000, 1100, False)], [10]),
                    encoding="utf-8",
                )
                status = make_status(
                    workflow_id,
                    lane_path,
                    workflow_key,
                    child_run_id,
                    1,
                    str(sess_path),
                )
                status["steps"][0]["structuredOutput"] = structured  # type: ignore
                (async_dir / "status.json").write_text(
                    json.dumps(status), encoding="utf-8"
                )
                result = run_report_node(
                    {
                        "action": "handleCompletion",
                        "repoControlRoot": control_root,
                        "taskId": "demo",
                        "ticketId": "T001",
                        "laneId": "writer-1",
                        "lanePath": lane_path,
                        "workflowId": workflow_id,
                        "asyncDir": str(async_dir),
                        "eventWorkflowId": workflow_id,
                        "eventAsyncDir": str(async_dir),
                    }
                )
                self.assertTrue(result["ok"], f"{label} {result}")
                feedback_file = (
                    repo
                    / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1"
                    / f"{child_run_id}.json"
                )
                self.assertTrue(
                    feedback_file.is_file(), f"{label} should create feedback"
                )
                payload = json.loads(feedback_file.read_text(encoding="utf-8"))
                self.assertIn("efficiencyFeedback", payload)
                self.assertEqual(
                    payload["role"],
                    "implementer" if workflow_key.startswith("impl") else "acceptor",
                )

    def test_malformed_output_no_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            async_dir = base / "async-malformed"
            async_dir.mkdir()
            sess_dir = async_dir / child_run_id
            sess_dir.mkdir(parents=True)
            sess_path = sess_dir / "session.jsonl"
            sess_path.write_text(
                make_session([("c1", "read", 1000, 1100, False)], [10]),
                encoding="utf-8",
            )
            # Invalid COMPLETED missing required outcome but with efficiencyFeedback
            malformed = {"efficiencyFeedback": "should not be accepted"}
            invalid = run_schema_validation({"kind": "worker", "value": malformed})
            self.assertTrue(invalid["ok"])
            self.assertFalse(
                invalid["valid"], "malformed missing outcome should fail schema"
            )
            status = make_status(
                workflow_id, lane_path, "impl-0", child_run_id, 1, str(sess_path)
            )
            status["steps"][0]["structuredOutput"] = malformed  # type: ignore
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result["ok"], result)
            self.assertFalse(
                (
                    repo
                    / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1"
                    / f"{child_run_id}.json"
                ).exists(),
                "malformed output must not create artifact",
            )
            # also test BLOCKED missing blocker
            malformed2 = {"outcome": "BLOCKED", "efficiencyFeedback": "also malformed"}
            invalid2 = run_schema_validation({"kind": "worker", "value": malformed2})
            self.assertFalse(invalid2["valid"])
            status2 = make_status(
                workflow_id, lane_path, "impl-0", child_run_id, 1, str(sess_path)
            )
            status2["steps"][0]["structuredOutput"] = malformed2  # type: ignore
            (base / "async-malformed2").mkdir()
            async_dir2 = base / "async-malformed2"
            sess_dir2 = async_dir2 / child_run_id
            sess_dir2.mkdir(parents=True)
            (sess_dir2 / "session.jsonl").write_text(
                make_session([("c1", "read", 1000, 1100, False)], [10]),
                encoding="utf-8",
            )
            status2["steps"][0]["sessionFile"] = str(sess_dir2 / "session.jsonl")
            status2["workflow"]["trace"][0]["runId"] = child_run_id  # type: ignore
            # Need to reconstruct status correctly: use make_status for same ids but inject malformed2
            status2b = make_status(
                workflow_id,
                lane_path,
                "impl-0",
                child_run_id,
                1,
                str(sess_dir2 / "session.jsonl"),
            )
            status2b["steps"][0]["structuredOutput"] = malformed2  # type: ignore
            (async_dir2 / "status.json").write_text(
                json.dumps(status2b), encoding="utf-8"
            )
            result2 = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir2),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir2),
                }
            )
            self.assertTrue(result2["ok"])
            self.assertFalse(
                (
                    repo
                    / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1"
                    / f"{child_run_id}.json"
                ).exists()
            )

    def test_exact_child_mismatch_no_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            correct_child = "22222222-2222-2222-2222-222222222222"
            wrong_child = "33333333-3333-3333-3333-333333333333"
            async_dir = base / "async-mismatch"
            async_dir.mkdir()
            sess_dir = async_dir / correct_child
            sess_dir.mkdir(parents=True)
            sess_path = sess_dir / "session.jsonl"
            sess_path.write_text(
                make_session([("c1", "read", 1000, 1100, False)], [10]),
                encoding="utf-8",
            )
            status = make_status(
                workflow_id, lane_path, "impl-0", wrong_child, 1, str(sess_path)
            )
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result["ok"], result)
            self.assertFalse(
                (
                    repo
                    / f".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1/{wrong_child}.json"
                ).exists()
            )
            self.assertFalse(
                (
                    repo
                    / f".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1/{correct_child}.json"
                ).exists()
            )

    def test_correction_rereview_separation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child1 = "11111111-1111-1111-1111-111111111111"
            child2 = "22222222-2222-2222-2222-222222222222"
            async_dir = base / "async-correction"
            async_dir.mkdir()
            for child in [child1, child2]:
                d = async_dir / child
                d.mkdir(parents=True)
                (d / "session.jsonl").write_text(
                    make_session([("c1", "read", 1000, 1100, False)], [10]),
                    encoding="utf-8",
                )
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {
                    "trace": [
                        {
                            "key": "impl-0",
                            "runId": child1,
                            "durationMs": 100,
                            "state": "completed",
                        },
                        {
                            "key": "impl-1",
                            "runId": child2,
                            "durationMs": 200,
                            "state": "completed",
                        },
                    ],
                    "emits": [],
                    "console": [],
                },
                "steps": [
                    {
                        "workflowKey": "impl-0",
                        "parentWorkflowRunId": workflow_id,
                        "status": "completed",
                        "turnCount": 1,
                        "sessionFile": str(async_dir / child1 / "session.jsonl"),
                        "structuredOutput": {
                            "outcome": "COMPLETED",
                            "efficiencyFeedback": "feedback impl-0",
                        },
                    },
                    {
                        "workflowKey": "impl-1",
                        "parentWorkflowRunId": workflow_id,
                        "status": "completed",
                        "turnCount": 1,
                        "sessionFile": str(async_dir / child2 / "session.jsonl"),
                        "structuredOutput": {
                            "outcome": "COMPLETED",
                            "efficiencyFeedback": "feedback impl-1",
                        },
                    },
                ],
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result["ok"], result)
            f1 = (
                repo
                / f".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1/{child1}.json"
            )
            f2 = (
                repo
                / f".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1/{child2}.json"
            )
            self.assertTrue(f1.is_file())
            self.assertTrue(f2.is_file())
            self.assertEqual(
                json.loads(f1.read_text(encoding="utf-8"))["efficiencyFeedback"],
                "feedback impl-0",
            )
            self.assertEqual(
                json.loads(f2.read_text(encoding="utf-8"))["efficiencyFeedback"],
                "feedback impl-1",
            )
            self.assertNotEqual(
                f1.read_text(encoding="utf-8"), f2.read_text(encoding="utf-8")
            )

    def test_exact_duplicate_and_different_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            fb = "same feedback"
            pub1 = run_feedback_node(
                {
                    "action": "publishFeedback",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "efficiencyFeedback": fb,
                }
            )
            self.assertTrue(pub1["ok"])
            self.assertTrue(pub1["result"]["published"])
            feedback_file = (
                repo
                / f".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1/{child_run_id}.json"
            )
            content1 = feedback_file.read_text(encoding="utf-8")
            pub2 = run_feedback_node(
                {
                    "action": "publishFeedback",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "efficiencyFeedback": fb,
                }
            )
            self.assertTrue(pub2["ok"])
            self.assertTrue(pub2["result"].get("isDuplicate"))
            self.assertFalse(pub2["result"]["published"])
            self.assertEqual(feedback_file.read_text(encoding="utf-8"), content1)
            pub3 = run_feedback_node(
                {
                    "action": "publishFeedback",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "efficiencyFeedback": "different",
                }
            )
            self.assertTrue(pub3["ok"])
            self.assertFalse(pub3["result"]["published"])
            self.assertIn("warning", pub3["result"])
            self.assertEqual(feedback_file.read_text(encoding="utf-8"), content1)
            warnings = (
                repo
                / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/warnings.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn("collision", warnings)

    def test_warning_dedup_and_unsafe_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            async_dir = base / "async-warn"
            async_dir.mkdir()
            sess_dir = async_dir / child_run_id
            sess_dir.mkdir(parents=True)
            (sess_dir / "session.jsonl").write_text(
                make_session([("c1", "read", 1000, 1100, False)], [10]),
                encoding="utf-8",
            )
            status = make_status(
                workflow_id,
                lane_path,
                "impl-0",
                child_run_id,
                1,
                str(sess_dir / "session.jsonl"),
            )
            status["steps"][0]["structuredOutput"] = {
                "outcome": "COMPLETED",
                "efficiencyFeedback": 12345,
            }  # type: ignore
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result1 = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result1["ok"])
            warnings_file = (
                repo
                / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/warnings.jsonl"
            )
            self.assertTrue(warnings_file.is_file())
            lines1 = warnings_file.read_text(encoding="utf-8").strip().splitlines()
            result2 = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result2["ok"])
            lines2 = warnings_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(
                len(lines1), len(lines2), "duplicate warning should be suppressed"
            )
            status2 = make_status(
                workflow_id,
                lane_path,
                "impl-0",
                child_run_id,
                1,
                str(sess_dir / "session.jsonl"),
            )
            status2["steps"][0]["structuredOutput"] = {
                "outcome": "COMPLETED",
                "efficiencyFeedback": "a" * 10001,
            }  # type: ignore
            (async_dir / "status.json").write_text(
                json.dumps(status2), encoding="utf-8"
            )
            result3 = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result3["ok"])
            lines3 = warnings_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(
                len(lines3), len(lines2) + 1, "different warning should not be deduped"
            )
            unsafe = run_feedback_node(
                {
                    "action": "publishFeedback",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "../evil",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "efficiencyFeedback": "test",
                }
            )
            self.assertTrue(unsafe["ok"])
            self.assertFalse(unsafe["result"]["published"])
            self.assertIn("unsafe", unsafe["result"]["warning"].lower())
            self.assertFalse((Path(control_root) / "evil").exists())

    def test_feedback_not_copied_into_report_or_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            fb = "qualitative feedback"
            pub = run_feedback_node(
                {
                    "action": "publishFeedback",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "workflowId": workflow_id,
                    "workflowKey": "impl-0",
                    "childRunId": child_run_id,
                    "lanePath": lane_path,
                    "efficiencyFeedback": fb,
                }
            )
            self.assertTrue(pub["ok"])
            report_file = (
                repo
                / f".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1/{child_run_id}.json"
            )
            self.assertFalse(report_file.exists())
            telemetry = repo / ".agent_state/plans/demo/.collab_op/telemetry.jsonl"
            if telemetry.exists():
                self.assertNotIn(fb, telemetry.read_text(encoding="utf-8"))
                self.assertNotIn(
                    "efficiencyFeedback", telemetry.read_text(encoding="utf-8")
                )

    def test_report_and_feedback_independent_after_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, expected, lane_path, control_root = self.seed_repo_with_lane(base)
            seed_task_container(repo)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            async_dir = base / "async-independent"
            async_dir.mkdir()
            missing_session = str(async_dir / child_run_id / "missing.jsonl")
            status = make_status_with_feedback(
                workflow_id,
                lane_path,
                "impl-0",
                child_run_id,
                1,
                missing_session,
                "feedback even though session missing",
            )
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node(
                {
                    "action": "handleCompletion",
                    "repoControlRoot": control_root,
                    "taskId": "demo",
                    "ticketId": "T001",
                    "laneId": "writer-1",
                    "lanePath": lane_path,
                    "workflowId": workflow_id,
                    "asyncDir": str(async_dir),
                    "eventWorkflowId": workflow_id,
                    "eventAsyncDir": str(async_dir),
                }
            )
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["result"]["handled"])
            self.assertEqual(len(result["result"]["published"]), 0)
            feedback_file = (
                repo
                / f".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1/{child_run_id}.json"
            )
            self.assertTrue(
                feedback_file.is_file(),
                "feedback should survive report session failure after exact correlation",
            )
            self.assertEqual(
                json.loads(feedback_file.read_text(encoding="utf-8"))[
                    "efficiencyFeedback"
                ],
                "feedback even though session missing",
            )
            self.assertGreaterEqual(len(result["result"]["warnings"]), 1)

    def test_workflow_with_feedback_preserves_call_sequence_branching_and_projection(
        self,
    ) -> None:
        worker_completed = {
            "outcome": "COMPLETED",
            "residualRisks": [],
            "efficiencyFeedback": "qualitative worker feedback",
        }
        reviewer_pass = {
            "verdict": "PASS",
            "residualRisks": [],
            "efficiencyFeedback": "review feedback",
        }
        worker_blocked = {
            "outcome": "BLOCKED",
            "blocker": "blocked reason",
            "efficiencyFeedback": "blocked feedback",
        }
        worker_needs = {
            "outcome": "NEEDS_DECISION",
            "decision": {"why": "why", "question": "q"},
            "efficiencyFeedback": "needs feedback",
        }
        reviewer_blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [{"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}],
            "efficiencyFeedback": "review blocked fb",
        }
        reviewer_needs = {
            "verdict": "NEEDS_DECISION",
            "decision": {"why": "why", "question": "q"},
            "efficiencyFeedback": "review needs fb",
        }
        cases = [
            (
                [completed_step(worker_completed), reviewer_pass],
                {
                    "outcome": "REVIEWED",
                    "residualRisks": worker_completed["residualRisks"]
                    + reviewer_pass["residualRisks"],
                },
                ["impl-0", "review-0"],
            ),
            (
                [worker_blocked],
                {"outcome": "BLOCKED", "blocker": "blocked reason"},
                ["impl-0"],
            ),
            (
                [worker_needs],
                {"outcome": "NEEDS_DECISION", "why": "why", "question": "q"},
                ["impl-0"],
            ),
            (
                [completed_step(worker_completed), reviewer_needs],
                {"outcome": "NEEDS_DECISION", "why": "why", "question": "q"},
                ["impl-0", "review-0"],
            ),
            (
                [completed_step(worker_completed), reviewer_blocked],
                {
                    "outcome": "CORRECTION_BUDGET_EXHAUSTED",
                    "blockers": reviewer_blocked["blockers"],
                    "residualRisks": [],
                },
                ["impl-0", "review-0"],
            ),
        ]
        for steps, expected_terminal, expected_keys in cases:
            with (
                self.subTest(expected=expected_terminal["outcome"]),
                tempfile.TemporaryDirectory() as temporary,
            ):
                base = Path(temporary)
                _, expected, capture, observed = self.launch_case(base)
                self.assertFalse(observed["is_error"], observed)
                # Validate each structured output via registered schema before exercising workflow
                for step in steps:
                    out = (
                        step["structuredOutput"]
                        if isinstance(step, dict) and "structuredOutput" in step
                        else step
                    )
                    kind = "worker" if out.get("outcome") else "reviewer"
                    valid = run_schema_validation({"kind": kind, "value": out})
                    self.assertTrue(
                        valid["ok"] and valid["valid"],
                        f"structured output should pass registered schema: {out}",
                    )
                run = subprocess.run(
                    ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                execution = json.loads(run.stdout)
                self.assertEqual(execution["result"], expected_terminal)
                self.assertNotIn("efficiencyFeedback", execution["result"])
                self.assertEqual(
                    [call["key"] for call in execution["calls"]], expected_keys
                )
                for call in execution["calls"]:
                    self.assertIsInstance(call["options"]["outputSchema"], dict)
                    # The async workflow runtime keeps native supervisor coordination
                    # attached; Collab must not override the configured bridge.
                    self.assertNotIn("intercomBridge", call["options"])
                    self.assertEqual(call["options"]["context"], "fresh")
                    self.assertIs(call["options"]["worktree"], False)

        # also verify that feedback presence does not change correction branching
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, _, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            blocked_review = {
                "verdict": "BLOCKED",
                "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                "blockers": [
                    {"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}
                ],
                "efficiencyFeedback": "fb",
            }
            completed_with_fb = {
                "outcome": "COMPLETED",
                "residualRisks": ["bounded risk"],
                "efficiencyFeedback": "fb2",
            }
            passed_with_fb = {
                "verdict": "PASS",
                "residualRisks": ["scope: finding"],
                "efficiencyFeedback": "fb3",
            }
            run = subprocess.run(
                [
                    "node",
                    str(SCRIPT_HARNESS),
                    str(capture),
                    json.dumps(
                        [
                            completed_step(completed_with_fb),
                            blocked_review,
                            completed_step(completed_with_fb),
                            passed_with_fb,
                        ]
                    ),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            execution = json.loads(run.stdout)
            self.assertEqual(
                execution["result"],
                {
                    "outcome": "REVIEWED",
                    "residualRisks": completed_with_fb["residualRisks"]
                    + passed_with_fb["residualRisks"],
                },
            )
            self.assertNotIn("efficiencyFeedback", execution["result"])
            self.assertEqual(
                [c["key"] for c in execution["calls"]],
                ["impl-0", "review-0", "impl-1", "review-1"],
            )

    def test_initial_reviewer_transport_failure_recovers_with_fresh_retry_and_preserves_subject(
        self,
    ) -> None:
        # Portable harness test: initial review transport failure is recovered via one
        # fresh replacement; every attempt uses fresh context, same lane/brief/baseline.
        worker = {"outcome": "COMPLETED", "residualRisks": []}
        passed = {"verdict": "PASS", "residualRisks": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            steps = [
                completed_step(worker),
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "WebSocket provider_transport_failure",
                },
                passed,
            ]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            execution = json.loads(run.stdout)
            self.assertEqual(execution["result"]["outcome"], "REVIEWED")
            self.assertEqual(
                [c["key"] for c in execution["calls"]],
                ["impl-0", "review-0", "review-0-retry-1"],
            )
            # every reviewer attempt is fresh, same lane, same integration baseline and brief
            for key in ("review-0", "review-0-retry-1"):
                opts = next(c["options"] for c in execution["calls"] if c["key"] == key)
                self.assertEqual(opts["cwd"], expected["lane"])
                self.assertEqual(opts["context"], "fresh")
                self.assertIs(opts["worktree"], False)
                self.assertEqual(opts["agent"], "collab-acceptor")
            tasks = [
                next(c["options"]["task"] for c in execution["calls"] if c["key"] == k)
                for k in ("review-0", "review-0-retry-1")
            ]
            self.assertEqual(tasks[0], tasks[1])
            self.assertIn(expected["integration_head"], tasks[0])
            self.assertIn(
                f"git diff --find-renames {expected['integration_head']}...HEAD --",
                tasks[0],
            )
            # correction budget is not consumed by reviewer retry - no extra writer launched
            self.assertEqual(
                [c["key"] for c in execution["calls"] if c["key"].startswith("impl-")],
                ["impl-0"],
            )

    def test_rereview_transport_failure_recovers_with_fresh_retry_and_preserves_subject(
        self,
    ) -> None:
        # Portable harness test: rereview transport failure after a correction is recovered;
        # subject (lane/brief/baseline) unchanged and correction accounting preserved.
        worker = {"outcome": "COMPLETED", "residualRisks": ["bounded"]}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [{"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}],
            "residualRisks": [],
        }
        passed = {"verdict": "PASS", "residualRisks": []}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            steps = [
                completed_step(worker),
                blocked,
                completed_step(worker),
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "provider_transport_failure",
                },
                passed,
            ]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            execution = json.loads(run.stdout)
            self.assertEqual(execution["result"]["outcome"], "REVIEWED")
            self.assertEqual(
                [c["key"] for c in execution["calls"]],
                ["impl-0", "review-0", "impl-1", "review-1", "review-1-retry-1"],
            )
            # fresh context for every reviewer attempt, same lane/brief/baseline across retries
            for key in ("review-1", "review-1-retry-1"):
                opts = next(c["options"] for c in execution["calls"] if c["key"] == key)
                self.assertEqual(opts["cwd"], expected["lane"])
                self.assertEqual(opts["context"], "fresh")
                self.assertIs(opts["worktree"], False)
            tasks = [
                next(c["options"]["task"] for c in execution["calls"] if c["key"] == k)
                for k in ("review-1", "review-1-retry-1")
            ]
            self.assertEqual(tasks[0], tasks[1])
            self.assertIn(blocked["correctionBase"], tasks[0])
            self.assertIn(
                f"git diff --find-renames {blocked['correctionBase']}...HEAD --",
                tasks[0],
            )
            self.assertIn("complete current lane diff", tasks[0])
            # correction accounting: only one BLOCKED->writer transition consumed budget; retry did not add a writer
            self.assertEqual(
                [c["key"] for c in execution["calls"] if c["key"].startswith("impl-")],
                ["impl-0", "impl-1"],
            )
            # initial review task uses integration tip, rereview uses correctionBase
            initial_task = next(
                c["options"]["task"]
                for c in execution["calls"]
                if c["key"] == "review-0"
            )
            self.assertIn(expected["integration_head"], initial_task)
            self.assertNotIn(blocked["correctionBase"], initial_task)

    def test_reviewer_recovery_exhausts_after_exactly_two_replacements_with_typed_outcome(
        self,
    ) -> None:
        # Portable harness test: after exactly two failed replacements (three attempts) the
        # workflow returns REVIEWER_RUNTIME_RECOVERY_EXHAUSTED with bounded phase/diagnostics,
        # not an unclassified exception. Cover both REVIEW and REREVIEW phases.
        worker = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [{"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}],
            "residualRisks": [],
        }
        # REVIEW exhaustion
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            steps = [
                completed_step(worker),
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "transport fail 1",
                },
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "transport fail 2",
                },
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "transport fail 3",
                },
            ]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            execution = json.loads(run.stdout)
            self.assertEqual(
                execution["result"]["outcome"], "REVIEWER_RUNTIME_RECOVERY_EXHAUSTED"
            )
            self.assertEqual(execution["result"]["phase"], "REVIEW")
            self.assertIsInstance(execution["result"]["error"], str)
            self.assertGreater(len(execution["result"]["error"]), 0)
            self.assertLessEqual(len(execution["result"]["error"]), 300)
            self.assertNotIn("\n", execution["result"]["error"])
            self.assertNotIn("\r", execution["result"]["error"])
            self.assertEqual(
                [c["key"] for c in execution["calls"]],
                ["impl-0", "review-0", "review-0-retry-1", "review-0-retry-2"],
            )
        # REREVIEW exhaustion
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, expected2, capture2, observed2 = self.launch_case(
                base, correction_budget=2
            )
            self.assertFalse(observed2["is_error"], observed2)
            steps2 = [
                completed_step(worker),
                blocked,
                completed_step(worker),
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "transport fail 1",
                },
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "transport fail 2",
                },
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "transport fail 3",
                },
            ]
            run2 = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture2), json.dumps(steps2)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run2.returncode, 0, run2.stderr)
            execution2 = json.loads(run2.stdout)
            self.assertEqual(
                execution2["result"]["outcome"], "REVIEWER_RUNTIME_RECOVERY_EXHAUSTED"
            )
            self.assertEqual(execution2["result"]["phase"], "REREVIEW")
            self.assertIsInstance(execution2["result"]["error"], str)
            self.assertLessEqual(len(execution2["result"]["error"]), 300)
            self.assertEqual(
                [c["key"] for c in execution2["calls"]],
                [
                    "impl-0",
                    "review-0",
                    "impl-1",
                    "review-1",
                    "review-1-retry-1",
                    "review-1-retry-2",
                ],
            )
            # correction accounting preserved across exhaustion: only one writer correction before REREVIEW exhaustion
            self.assertEqual(
                [c["key"] for c in execution2["calls"] if c["key"].startswith("impl-")],
                ["impl-0", "impl-1"],
            )

    def test_reviewer_recovery_preserves_correction_budget_and_semantic_verdict_does_not_retry(
        self,
    ) -> None:
        # Portable harness test: semantic BLOCKED/PASS/NEEDS_DECISION do not trigger retry;
        # recovery does not consume or reset correction budget.
        worker = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [{"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}],
            "residualRisks": [],
        }
        passed = {"verdict": "PASS", "residualRisks": []}
        needs = {
            "verdict": "NEEDS_DECISION",
            "decision": {"why": "why", "question": "q"},
        }
        # semantic BLOCKED drives correction, not retry
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            steps = [completed_step(worker), blocked, completed_step(worker), passed]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            execution = json.loads(run.stdout)
            self.assertEqual(execution["result"]["outcome"], "REVIEWED")
            self.assertEqual(
                [c["key"] for c in execution["calls"]],
                ["impl-0", "review-0", "impl-1", "review-1"],
            )
            self.assertNotIn("review-0-retry-1", [c["key"] for c in execution["calls"]])
        # NEEDS_DECISION also does not trigger retry
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            steps = [completed_step(worker), needs]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            execution = json.loads(run.stdout)
            self.assertEqual(execution["result"]["outcome"], "NEEDS_DECISION")
            self.assertEqual(len(execution["calls"]), 2)
            self.assertNotIn("review-0-retry-1", [c["key"] for c in execution["calls"]])
        # recovery does not consume budget: one BLOCKED + rereview retry still within budget 1
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            steps = [
                completed_step(worker),
                blocked,
                completed_step(worker),
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "transport",
                },
                passed,
            ]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            execution = json.loads(run.stdout)
            self.assertEqual(execution["result"]["outcome"], "REVIEWED")
            self.assertEqual(
                [c["key"] for c in execution["calls"] if c["key"].startswith("impl-")],
                ["impl-0", "impl-1"],
            )
        # recovery does not reset budget: two BLOCKEDs with retry in between still exhausts with budget 1
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            retry_blocked = blocked  # second BLOCKED after retry
            steps = [
                completed_step(worker),
                blocked,
                completed_step(worker),
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "transport",
                },
                retry_blocked,
            ]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            execution = json.loads(run.stdout)
            self.assertEqual(
                execution["result"]["outcome"], "CORRECTION_BUDGET_EXHAUSTED"
            )
            self.assertEqual(
                [c["key"] for c in execution["calls"]],
                ["impl-0", "review-0", "impl-1", "review-1", "review-1-retry-1"],
            )
            self.assertNotIn("impl-2", [c["key"] for c in execution["calls"]])

    def test_writer_runtime_failure_does_not_retry(self) -> None:
        worker_pass = {"outcome": "COMPLETED", "residualRisks": []}
        blocked = {
            "verdict": "BLOCKED",
            "correctionBase": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "blockers": [{"where": "x", "why": "y", "howToFix": "z", "trigger": "t"}],
            "residualRisks": [],
        }
        # initial writer throw - no replacement
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            steps = [
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "lane partially mutated transport failure",
                }
            ]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(run.returncode, 0)
            execution = json.loads(run.stdout)
            self.assertEqual([c["key"] for c in execution["calls"]], ["impl-0"])
            self.assertNotIn("impl-0-retry-1", [c["key"] for c in execution["calls"]])
            self.assertIn(
                "lane partially mutated", run.stderr + execution.get("error", "")
            )
        # correction writer throw - no replacement or resume
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            _, _, capture, observed = self.launch_case(base, correction_budget=1)
            self.assertFalse(observed["is_error"], observed)
            steps = [
                completed_step(worker_pass),
                blocked,
                {
                    "structuredOutput": {"verdict": "PASS", "residualRisks": []},
                    "throwMessage": "correction transport failure",
                },
            ]
            run = subprocess.run(
                ["node", str(SCRIPT_HARNESS), str(capture), json.dumps(steps)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(run.returncode, 0)
            execution = json.loads(run.stdout)
            self.assertEqual(
                [c["key"] for c in execution["calls"]], ["impl-0", "review-0", "impl-1"]
            )
            self.assertNotIn("impl-1-retry-1", [c["key"] for c in execution["calls"]])
            self.assertNotIn("review-1", [c["key"] for c in execution["calls"]])


if __name__ == "__main__":
    unittest.main()
