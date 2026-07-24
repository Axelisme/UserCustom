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
    Path("to-spec/SKILL.md"),
    Path("to-tickets/SKILL.md"),
)


class CrossSkillV119ContractTests(unittest.TestCase):
    """Package Contract preventing adjacent skills from restoring v118 flow."""

    def document(self, root: Path, relative: str) -> str:
        path = root / relative
        self.assertTrue(path.is_file(), f"missing shipped document: {path}")
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

    def test_code_review_is_only_the_final_dev_flow_gate(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "code-review/SKILL.md"))
        lowered = text.lower()
        ordered_labels = (
            "post-simplify",
            "canonical tests",
            "clean-detached",
        )
        for label in ordered_labels:
            self.assertIn(label, lowered)
        positions = [lowered.index(label) for label in ordered_labels]
        self.assertEqual(positions, sorted(positions), text)
        self.assertRegex(
            lowered,
            r"(?:only|sole).{0,240}post-simplify.{0,180}canonical tests"
            r".{0,180}clean-detached.{0,120}exact[- ]sha.{0,180}dev-flow gate",
        )

        for obsolete_instruction in (
            r"slice-level reviews?",
            r"review-depth tiers?",
            r"wave[- ]end reviews?",
            r"runs? once at a wave end",
            r"orchestrat(?:e|or).{0,100}dispatch.{0,100}review",
            r"invoked by the orchestrator",
        ):
            with self.subTest(obsolete_instruction=obsolete_instruction):
                self.assertNotRegex(lowered, obsolete_instruction)

    def test_to_spec_assigns_the_frozen_spec_only_to_roles_and_final_code_review(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "to-spec/SKILL.md"))
        lowered = text.lower()
        self.assertRegex(
            lowered,
            r"frozen contract.{0,220}(?:consum|used).{0,120}oracle"
            r".{0,100}implementation",
        )
        self.assertRegex(
            lowered,
            r"(?:only|solely).{0,100}(?:final )?code-review.{0,100}spec axis"
            r"|(?:final )?code-review.{0,100}spec axis.{0,100}(?:only|solely)",
        )
        self.assertNotRegex(
            lowered,
            r"orchestrat(?:e|or|ion).{0,100}(?:reviews?|checks?)"
            r"|(?:reviews?|checks?).{0,100}orchestrat(?:e|or|ion)",
        )

    def test_planning_documents_do_not_restore_removed_findings_authority(self) -> None:
        documents = {
            relative: self.normalized(self.document(CODEX_SKILLS, relative))
            for relative in (
                "planning-with-files/SKILL.md",
                "planning-with-files/templates/INDEX.md",
            )
        }
        for relative, text in documents.items():
            lowered = text.lower()
            with self.subTest(relative=relative):
                self.assertNotIn("orchestrate findings", lowered)
                self.assertNotIn(".agent_state/orchestrate/feedback", lowered)
                self.assertNotRegex(
                    lowered,
                    r"(?:review findings|feedback).{0,120}(?:authority|truth|真相)"
                    r".{0,120}(?:orchestrate|ledger)",
                )

    def test_plan_directory_tickets_publish_dependency_addressable_role_slices(self) -> None:
        text = self.normalized(self.document(CODEX_SKILLS, "to-tickets/SKILL.md"))
        start = text.index("**Plan-directory repo**")
        end = text.index("**Tracker repo**", start)
        plan_directory = text[start:end]
        lowered = plan_directory.lower()

        self.assertRegex(
            plan_directory,
            r"(?:Each|Every).{0,120}\bSlice\b.{0,220}\bOracle\b.{0,100}"
            r"\bContract\b.{0,180}\bRoot\b.{0,100}exact.{0,80}merge"
            r".{0,180}\bImplementation\b",
        )
        self.assertRegex(
            plan_directory,
            r"\bRoot\b.{0,180}(?:chooses|decides).{0,120}\bWaves\b"
            r".{0,180}queue depth",
        )
        for obsolete_instruction in (
            r"\blanes?\b",
            r"one worktree each",
            r"one-worktree-per-ticket",
            r"dispatch an implementer",
            r"implementer per frontier ticket",
        ):
            with self.subTest(obsolete_instruction=obsolete_instruction):
                self.assertNotRegex(lowered, obsolete_instruction)


if __name__ == "__main__":
    unittest.main()
