from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATE = ROOT / "home" / ".codex" / "skills" / "orchestrate"


def section_bytes(text: str, heading: str, next_heading: str) -> bytes:
    start = text.index(heading)
    end = text.index(next_heading, start)
    return text[start:end].encode("utf-8")


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class OrchestrateContractTests(unittest.TestCase):
    def test_release_101_keeps_iron_rules_and_pipeline_byte_exact(self) -> None:
        text = (ORCHESTRATE / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("skill_version: 101", text)
        iron = section_bytes(text, "## Iron rules", "## Pipeline model")
        pipeline = section_bytes(text, "## Pipeline model", "## Control loop")
        # v100 touches collect/findings/worktrees behavior and prose, but the iron
        # and pipeline sections stay byte-exact from v98.
        self.assertEqual(
            hashlib.sha256(iron).hexdigest(),
            "42c8f0c80e10d3f9b7b5f559714870ad064497a8b4bf581d8d243ff1136872be",
        )
        self.assertEqual(
            hashlib.sha256(pipeline).hexdigest(),
            "900fdd967b042ebbaf3e50b1a068d4e1720a8630d4e985bf8e7d7ba024686bd3",
        )

    def test_skill_is_mental_model_plus_tools_not_argument_manual(self) -> None:
        text = normalized(ORCHESTRATE / "SKILL.md")
        for phrase in (
            "own the control flow",
            "Git is the durable log",
            "critical-path lead time",
            "Structural",
            "Data",
            "Control",
            "Run-ahead is the default",
            "consult per-command `--help`",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("--expected-lane-sha", text)
        self.assertNotIn("--task-ref task/", text)

    def test_maintainer_readme_is_a_design_constitution(self) -> None:
        text = normalized(ORCHESTRATE / "README.md")
        for phrase in (
            "mental model + tools",
            "Litmus test",
            "Narrow waist",
            "state test",
            "git is the durable log",
            "must not change",
        ):
            self.assertIn(phrase, text)

    def test_progressive_documents_remain_single_read(self) -> None:
        documents = [
            ORCHESTRATE / "SKILL.md",
            ORCHESTRATE / "runtime-codex.md",
            ORCHESTRATE / "runtime-claude.md",
            *sorted((ORCHESTRATE / "references").glob("*.md")),
        ]
        for path in documents:
            with self.subTest(path=path.name):
                self.assertLessEqual(len(path.read_bytes()), 16_384)
        self.assertEqual(
            {path.name for path in (ORCHESTRATE / "references").glob("*.md")},
            {"coordination.md", "publication-review.md"},
        )

    def test_package_has_one_way_domain_boundaries(self) -> None:
        package = ORCHESTRATE / "scripts" / "_orchestrate"
        expected = {
            "__init__.py",
            "cli.py",
            "findings.py",
            "git_ops.py",
            "landing.py",
            "lanes.py",
            "primitives.py",
            "release.py",
            "review.py",
            "worktrees.py",
        }
        self.assertEqual({path.name for path in package.glob("*.py")}, expected)
        entrypoint = (ORCHESTRATE / "scripts" / "orchestrate.py").read_text(
            encoding="utf-8"
        )
        self.assertLess(len(entrypoint.encode("utf-8")), 512)
        self.assertIn("_orchestrate.cli", entrypoint)

    def test_narrow_waist_did_not_add_forbidden_core_protocol(self) -> None:
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ORCHESTRATE / "SKILL.md",
                ORCHESTRATE / "references" / "coordination.md",
                ORCHESTRATE / "references" / "publication-review.md",
            )
        )
        for forbidden in (
            "Seam-Risk:",
            "Denied-SHA:",
            "Compensation:",
            "slice recut",
            "heartbeat command",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
