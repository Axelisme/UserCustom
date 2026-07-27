from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
CODEX_SKILLS = HOME / ".codex" / "skills"
PI_SKILLS = HOME / ".pi" / "agent" / "skills"
SHARED_DOCUMENTS = (
    Path("code-review/SKILL.md"),
    Path("planning-with-files/SKILL.md"),
    Path("planning-with-files/templates/INDEX.md"),
    Path("planning-with-files/templates/phase.md"),
    Path("to-spec/SKILL.md"),
    Path("to-tickets/SKILL.md"),
)


class CrossSkillV129ContractTests(unittest.TestCase):
    """Contract for v129 ownership and the formal ReviewGate interface."""

    @staticmethod
    def document(root: Path, relative: str) -> str:
        path = root / relative
        if not path.is_file():
            raise AssertionError(f"missing shipped document: {path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def normalized(text: str) -> str:
        return " ".join(text.split())

    def test_pi_and_codex_mirrors_are_exactly_equivalent(self) -> None:
        for relative in SHARED_DOCUMENTS:
            with self.subTest(relative=relative):
                self.assertEqual(
                    (CODEX_SKILLS / relative).read_bytes(),
                    (PI_SKILLS / relative).read_bytes(),
                )

    def test_reviewgate_exposes_one_small_source_and_axis_interface(self) -> None:
        text = self.document(CODEX_SKILLS, "code-review/SKILL.md")
        self.assertIn("## Source and axes", text)
        self.assertEqual(
            re.findall(r"(?m)^- `Axis: (standards|spec)`$", text),
            ["standards", "spec"],
        )
        normalized = self.normalized(text).casefold()
        for interface_token in (
            "integration-first",
            "shared detached fallback",
            "same exact sha",
            "bounded delta",
            "originating axis",
        ):
            with self.subTest(interface_token=interface_token):
                self.assertIn(interface_token, normalized)
        self.assertRegex(text, r"No `collect` or `mutate`")

    def test_orchestrate_declares_only_the_git_task_lane(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "orchestrate/SKILL.md"))
        self.assertIn("Git task lane", text)
        self.assertNotIn("PipelineManager", text)
        self.assertNotIn("ReviewGate", text)

    def test_planning_owns_storage_and_schema_only(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "planning-with-files/SKILL.md"))
        lowered = text.lower()
        self.assertIn("storage/schema", lowered)
        self.assertIn("S6/S7", text)
        self.assertNotIn("mode inference", lowered)
        self.assertNotIn("landing policy", lowered)

    def test_planning_v14_exposes_storage_schema_not_session_policy(self) -> None:
        skill = self.document(CODEX_SKILLS, "planning-with-files/SKILL.md")
        self.assertIn("skill_version: 14", skill)
        lowered = self.normalized(skill).casefold()
        for policy_term in ("day mode", "acceptance session", "coordinated repair"):
            with self.subTest(policy_term=policy_term):
                self.assertNotIn(policy_term, lowered)

    def test_spec_and_ticket_skills_own_artifacts_only(self) -> None:
        spec = self.normalized(self.document(CODEX_SKILLS, "to-spec/SKILL.md")).lower()
        tickets = self.normalized(self.document(CODEX_SKILLS, "to-tickets/SKILL.md")).lower()
        self.assertIn("artifacts only", spec)
        self.assertIn("artifacts only", tickets)
        self.assertIn("s1/s2", spec)
        self.assertNotIn("reviewgate", spec)
        self.assertNotIn("reviewgate", tickets)

    def test_code_review_owns_reviewgate_output_only(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "code-review/SKILL.md"))
        lowered = text.lower()
        self.assertIn("reviewgate output", lowered)
        self.assertIn("s4", lowered)
        self.assertNotIn("persistence landing", lowered)


if __name__ == "__main__":
    unittest.main()
