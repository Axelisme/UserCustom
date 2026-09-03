from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path
from typing import Any

from tests import _profile_test_support as support

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
PI_SCHEMA = HOME / ".pi/agent/extensions/collab-shared/result-schema.ts"
CLAUDE_WORKFLOW = HOME / ".claude/workflows/collab-reviewed-lane.js"
CLAUDE_HARNESS = ROOT / "tests/collab_reviewed_lane_workflow_harness.mjs"
ROLE_SCHEMA_NAMES = {
    "collab-implementer": "worker",
    "collab-acceptor": "reviewer",
}
FIELD_TOKEN = re.compile(r"`([^`]+)`")
BRANCH = re.compile(
    r"- `([A-Z_]+)`: required (.*?); optional (.*?)(?=\. - `[A-Z_]+`|\.$)"
)
ALIASES = {
    "`Outcome`",
    "`Residual risks`",
    "`Efficiency feedback`",
    "`Blocker`",
    "`Decision needed`",
    "`Verdict`",
    "`Where`",
    "`Why`",
    "`How to fix`",
    "`Trigger`",
    "`Question`",
    "`Suggestion`",
    "`suggestion`",
    "`none`",
}


def raw_section(document: str, heading: str) -> str:
    lines = document.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == heading]
    if len(starts) != 1:
        raise AssertionError(f"expected one {heading!r}, found {len(starts)}")
    start = starts[0] + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


def declared_contract(section: str) -> dict[str, dict[str, set[str]]]:
    marker = re.search(
        r"(?:The exact branch contract is|uses one exact branch contract):\s*\n",
        section,
    )
    if marker is None:
        raise AssertionError("exact branch contract marker is missing")
    block = section[marker.end() :].split("\n\n", 1)[0]
    normalized = re.sub(r"\s+", " ", block).strip()
    parsed: dict[str, dict[str, set[str]]] = {}
    for branch, required, optional in BRANCH.findall(normalized):
        parsed[branch] = {
            "required": set(FIELD_TOKEN.findall(required)),
            "optional": set(FIELD_TOKEN.findall(optional)),
        }
    if not parsed:
        raise AssertionError("no branch declarations were parsed")
    return parsed


def object_paths(
    schema: dict[str, Any],
    *,
    prefix: str = "",
) -> tuple[set[str], set[str]]:
    allowed: set[str] = set()
    required: set[str] = set()
    required_names = set(schema.get("required", []))
    for name, child in schema.get("properties", {}).items():
        path = f"{prefix}.{name}" if prefix else name
        allowed.add(path)
        is_required = name in required_names
        if is_required:
            required.add(path)

        child_allowed: set[str] = set()
        child_required: set[str] = set()
        if child.get("type") == "object":
            child_allowed, child_required = object_paths(child, prefix=path)
        elif child.get("type") == "array" and child.get("items", {}).get("type") == "object":
            child_allowed, child_required = object_paths(
                child["items"],
                prefix=f"{path}[]",
            )
        allowed.update(child_allowed)
        if is_required:
            required.update(child_required)
    return allowed, required


def schema_contract(
    schema: dict[str, Any],
    discriminator: str,
) -> dict[str, dict[str, set[str]]]:
    parsed: dict[str, dict[str, set[str]]] = {}
    for branch in schema["oneOf"]:
        branch_name = branch["properties"][discriminator]["const"]
        allowed, required = object_paths(branch)
        parsed[branch_name] = {
            "required": required,
            "optional": allowed - required,
        }
    return parsed


def load_pi_contracts() -> dict[str, dict[str, dict[str, set[str]]]]:
    script = (
        f'import * as mod from {json.dumps(PI_SCHEMA.as_uri())};'
        'process.stdout.write(JSON.stringify({'
        'worker: mod.reviewedLaneWorkerSchema, reviewer: mod.reviewedLaneReviewerSchema}));'
    )
    run = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "--eval",
            script,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        raise AssertionError(f"Pi schema load failed:\n{run.stderr}\n{run.stdout}")
    schemas = json.loads(run.stdout)
    return {
        "worker": schema_contract(schemas["worker"], "outcome"),
        "reviewer": schema_contract(schemas["reviewer"], "verdict"),
    }


def load_claude_allowed_paths() -> dict[str, set[str]]:
    workflow_input = {
        "lane": "/tmp/collab-lane",
        "startingHead": "0123456789abcdef",
        "ticket": "/tmp/ticket.md",
        "envelope": None,
        "correctionBudget": 0,
        "operatorNotes": None,
    }
    run = subprocess.run(
        [
            "node",
            str(CLAUDE_HARNESS),
            str(CLAUDE_WORKFLOW),
            json.dumps(workflow_input),
            "happy",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        raise AssertionError(f"Claude schema load failed:\n{run.stderr}\n{run.stdout}")
    output = json.loads(run.stdout)
    invocations = output["invocations"]
    worker_allowed, _ = object_paths(invocations[0][1]["schema"])
    reviewer_allowed, _ = object_paths(invocations[1][1]["schema"])
    return {"worker": worker_allowed, "reviewer": reviewer_allowed}


class CollabResultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pi_contracts = load_pi_contracts()
        cls.claude_allowed = load_claude_allowed_paths()

    def result_sections(self, profile_name: str) -> dict[str, str]:
        profile = support.load_runtime_profile(HOME, profile_name)
        return {
            runtime: raw_section(prompt, "## Result")
            for runtime, prompt in support.runtime_prompts(profile).items()
        }

    def assert_uses_exact_keys(self, label: str, section: str) -> None:
        present = sorted(alias for alias in ALIASES if alias in section)
        self.assertEqual([], present, f"{label} carries result aliases or sentinels: {present}")

    def test_every_profile_declares_the_strict_common_contract(self) -> None:
        for profile_name, schema_name in ROLE_SCHEMA_NAMES.items():
            expected = self.pi_contracts[schema_name]
            for runtime, section in self.result_sections(profile_name).items():
                with self.subTest(profile=profile_name, runtime=runtime):
                    self.assertEqual(expected, declared_contract(section))
                    self.assert_uses_exact_keys(f"{profile_name}/{runtime}", section)

    def test_guard_rejects_each_regression_class(self) -> None:
        worker = self.result_sections("collab-implementer")["claude"]
        reviewer = self.result_sections("collab-acceptor")["claude"]
        mutations = {
            "suggestion": (
                "reviewer",
                reviewer.replace(
                    "`residualRisks`, `efficiencyFeedback`.",
                    "`residualRisks`, `efficiencyFeedback`, `suggestion`.",
                    1,
                ),
            ),
            "none-sentinel": (
                "worker",
                worker.replace("Omit it when\nempty.", "Return `none` when empty.", 1),
            ),
            "field-alias": (
                "worker",
                worker.replace("required `outcome`", "required `Outcome`", 1),
            ),
            "missing-required-field": (
                "worker",
                worker.replace("required `outcome`, `blocker`", "required `outcome`", 1),
            ),
        }
        for name, (schema_name, mutated) in mutations.items():
            original = reviewer if schema_name == "reviewer" else worker
            with self.subTest(mutation=name):
                self.assertNotEqual(original, mutated, "mutation probe did not alter the section")
                contract_changed = (
                    declared_contract(mutated) != self.pi_contracts[schema_name]
                )
                carries_alias = any(alias in mutated for alias in ALIASES)
                self.assertTrue(contract_changed or carries_alias)

    def test_common_profile_contract_is_allowed_by_claude_workflow(self) -> None:
        for schema_name, contract in self.pi_contracts.items():
            allowed = self.claude_allowed[schema_name]
            for branch, fields in contract.items():
                with self.subTest(schema=schema_name, branch=branch):
                    declared = fields["required"] | fields["optional"]
                    self.assertLessEqual(declared, allowed)

    def test_collab_core_uses_the_same_exact_contracts(self) -> None:
        skill = (HOME / ".codex/skills/collab/SKILL.md").read_text(encoding="utf-8")
        sections = {
            "worker": raw_section(skill, "## Worker results are semantic"),
            "reviewer": raw_section(skill, "## Generic Acceptance"),
        }
        for schema_name, section in sections.items():
            with self.subTest(schema=schema_name):
                self.assertEqual(self.pi_contracts[schema_name], declared_contract(section))
                self.assert_uses_exact_keys(f"collab/{schema_name}", section)


if __name__ == "__main__":
    unittest.main()
