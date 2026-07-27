from __future__ import annotations

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


class CrossSkillV128ContractTests(unittest.TestCase):
    """Contract for v128 ownership and the formal ReviewGate interface."""

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

    def test_reviewgate_requires_two_fresh_axes_on_one_exact_source(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "code-review/SKILL.md"))
        lowered = text.lower()
        self.assertIn("post-simplify", lowered)
        self.assertIn("two fresh", lowered)
        self.assertIn("Axis: standards", text)
        self.assertIn("Axis: spec", text)
        self.assertIn("same exact SHA", text)
        self.assertIn("same source", lowered)

    def test_reviewgate_defaults_to_a_clean_integration_source(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "code-review/SKILL.md"))
        lowered = text.lower()
        self.assertIn("integration-first", lowered)
        for term in ("same path", "same branch", "same head", "clean"):
            with self.subTest(term=term):
                self.assertIn(term, lowered)

    def test_reviewgate_bracket_forbids_collection_and_mutation(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "code-review/SKILL.md"))
        lowered = text.lower()
        self.assertIn("review bracket", lowered)
        self.assertIn("pre", lowered)
        self.assertIn("post", lowered)
        self.assertLess(lowered.index("pre"), lowered.index("post"))
        self.assertIn("collect", lowered)
        self.assertIn("mutate", lowered)

    def test_reviewgate_uses_capability_based_shared_detached_fallback(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "code-review/SKILL.md"))
        lowered = text.lower()
        self.assertIn("capability-based", lowered)
        self.assertIn("shared detached fallback", lowered)
        self.assertIn("read-only", lowered)
        self.assertIn("integration", lowered)

    def test_bounded_delta_uses_one_reviewer_on_the_originating_axis(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "code-review/SKILL.md"))
        lowered = text.lower()
        self.assertIn("bounded delta", lowered)
        self.assertIn("one reviewer", lowered)
        self.assertIn("originating axis", lowered)

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
