from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
ADMISSION_PATHS = (
    HOME / ".codex" / "skills" / "dev-flow" / "references" / "admission-standard.md",
    HOME / ".pi" / "agent" / "skills" / "dev-flow" / "references" / "admission-standard.md",
    HOME / ".claude" / "skills" / "dev-flow" / "references" / "admission-standard.md",
)
ROUTING_DOCUMENTS = (
    HOME / ".codex" / "skills" / "dev-flow" / "SKILL.md",
    HOME / ".codex" / "skills" / "orchestrate" / "SKILL.md",
    HOME / ".codex" / "AGENTS.md",
    HOME / ".pi" / "agent" / "APPEND_SYSTEM.md",
)


class DevFlowV128ContractTests(unittest.TestCase):
    """Contract for the v128 admission authority and routing seam."""

    @staticmethod
    def read(path: Path) -> str:
        if not path.is_file():
            raise AssertionError(f"missing shipped document: {path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def headings(text: str) -> list[str]:
        return [line.lstrip("#").strip() for line in text.splitlines() if line.startswith("#")]

    @classmethod
    def section(cls, text: str, prefix: str, next_prefix: str | None = None) -> str:
        lines = text.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith(prefix))
        end = next(
            (
                i
                for i in range(start + 1, len(lines))
                if next_prefix and lines[i].startswith(next_prefix)
            ),
            len(lines),
        )
        return "\n".join(lines[start:end])

    def test_admission_standard_is_one_mirrored_s1_to_s7_authority(self) -> None:
        documents = [self.read(path) for path in ADMISSION_PATHS]
        self.assertEqual(len({document.encode() for document in documents}), 1)
        headings = self.headings(documents[0])
        for number in range(1, 8):
            with self.subTest(section=f"S{number}"):
                self.assertTrue(any(heading.startswith(f"S{number} ") for heading in headings))

        for path in ROUTING_DOCUMENTS:
            text = self.read(path)
            with self.subTest(path=path):
                self.assertNotRegex(text, r"(?m)^#{1,6} S[1-7]\b")
                self.assertIn("admission standard", text.lower())
                self.assertTrue("S1–S7" in text or "S1-S7" in text)

    def test_admission_s1_requires_first_checkpoint_days_not_weeks(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s1 = self.section(standard, "## S1 ", "## S2 ")
        normalized = " ".join(s1.lower().split())
        self.assertTrue("days, not weeks" in normalized or "days-not-weeks" in normalized)

    def test_admission_s4_defines_blocking_as_a_closed_enum(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s4 = self.section(standard, "## S4 ", "## S5 ").lower()
        self.assertIn("closed enum", s4)

    def test_admission_s4_requires_contract_basis_for_blockers(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s4 = self.section(standard, "## S4 ", "## S5 ").lower()
        self.assertIn("contract_basis", s4)

    def test_admission_s4_routes_missing_decisions_to_blocked_on_decision(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s4 = self.section(standard, "## S4 ", "## S5 ").lower()
        self.assertIn("blocked_on_decision", s4)

    def test_admission_s5_and_s6_share_reviewgate_machine_order(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s5 = self.section(standard, "## S5 ", "## S6 ")
        s6 = self.section(standard, "## S6 ", "## S7 ")
        for name, section in (("S5", s5), ("S6", s6)):
            with self.subTest(section=name):
                normalized = " ".join(section.split())
                for term in ("simplify", "canonical tests", "ReviewGate"):
                    self.assertIn(term, normalized)
                positions = [
                    normalized.index(term)
                    for term in ("simplify", "canonical tests", "ReviewGate")
                ]
                self.assertEqual(positions, sorted(positions), normalized)

    def test_admission_s7_names_the_task_integration_worktree_cleanup(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s7 = self.section(standard, "## S7 ").lower()
        self.assertIn("task integration worktree", s7)

    def test_admission_s7_names_role_and_integration_branch_cleanup(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s7 = self.section(standard, "## S7 ").lower()
        self.assertIn("role", s7)
        self.assertIn("integration branches", s7)

    def test_admission_s7_names_task_ref_and_phase_cleanup(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s7 = self.section(standard, "## S7 ").lower()
        self.assertIn("refs/orchestrate", s7)
        self.assertIn("phase", s7)


if __name__ == "__main__":
    unittest.main()
