from __future__ import annotations

import re
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
    """Structural contract for the v128 S1-S7 authority."""

    @staticmethod
    def read(path: Path) -> str:
        if not path.is_file():
            raise AssertionError(f"missing shipped document: {path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def section(text: str, number: int) -> str:
        match = re.search(
            rf"(?ms)^## S{number}\b.*?(?=^## S{number + 1}\b|\Z)",
            text,
        )
        if not match:
            raise AssertionError(f"missing S{number} section")
        return match.group(0)

    @staticmethod
    def clause_ids(section: str) -> set[str]:
        return set(re.findall(r"\*\*(S\d+\.\d+)\b", section))

    def test_admission_standard_is_one_mirrored_authority(self) -> None:
        documents = [self.read(path) for path in ADMISSION_PATHS]
        self.assertEqual(len({document.encode() for document in documents}), 1)
        headings = re.findall(r"(?m)^## (S[1-7])\b", documents[0])
        self.assertEqual(headings, [f"S{number}" for number in range(1, 8)])

        for path in ROUTING_DOCUMENTS:
            text = self.read(path)
            with self.subTest(path=path):
                self.assertNotRegex(text, r"(?m)^#{1,6} S[1-7]\b")
                self.assertRegex(text, r"(?i)admission standard")

    def test_numbered_clauses_are_complete(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        expected = {
            1: {f"S1.{number}" for number in range(1, 5)},
            2: {f"S2.{number}" for number in range(1, 4)},
            3: {"S3.8"},
            4: {f"S4.{number}" for number in range(1, 6)},
            5: {f"S5.{number}" for number in range(1, 5)},
            6: {f"S6.{number}" for number in range(1, 7)},
            7: {f"S7.{number}" for number in range(1, 7)},
        }
        for number, clause_ids in expected.items():
            with self.subTest(section=f"S{number}"):
                self.assertEqual(self.clause_ids(self.section(standard, number)), clause_ids)

    def test_milestone_table_keeps_all_machine_checks(self) -> None:
        rows = re.findall(
            r"(?m)^\| ([1-7]) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$",
            self.section(self.read(ADMISSION_PATHS[0]), 3),
        )
        self.assertEqual(
            [(number, name.strip()) for number, name, _, _ in rows],
            [
                ("1", "Reachability"),
                ("2", "Deletion"),
                ("3", "Loop"),
                ("4", "Mass"),
                ("5", "Focus"),
                ("6", "Burn-down"),
                ("7", "Downgrade"),
            ],
        )
        self.assertTrue(all(query.strip() and refusal.strip() for _, _, query, refusal in rows))

    def test_normative_limits_and_closed_enums_remain_decidable(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        self.assertRegex(self.section(standard, 1), r"≤\s*1500")
        self.assertRegex(self.section(standard, 4), r"machine_rework_cycles[^\n]*≤\s*2")
        self.assertRegex(self.section(standard, 6), r"max speculative dependency depth[^\n]*\*\*10\*\*")

        blockers = {
            "spec_violation",
            "data_loss",
            "security",
            "reproducible_behavior_failure",
        }
        s4 = self.section(standard, 4)
        blocker_span = re.search(r"Blocking is a \*\*closed enum\*\*: `([^`]+)`", s4)
        if blocker_span is None:
            self.fail("missing closed blocker enum")
        self.assertEqual(
            set(re.findall(r"[a-z_]+", blocker_span.group(1))),
            blockers,
        )
        self.assertIn("contract_basis", s4)
        self.assertIn("blocked_on_decision", s4)

    def test_both_modes_share_machine_order_before_night_continues(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s5 = " ".join(self.section(standard, 5).split()).casefold()
        ordered = [s5.index(term) for term in ("simplify", "canonical tests", "reviewgate")]
        self.assertEqual(ordered, sorted(ordered))
        self.assertIn("day and night", s5)

        s6 = " ".join(self.section(standard, 6).split()).casefold()
        self.assertLess(s6.index("reviewed_awaiting_user"), s6.index("dependent slice"))
        self.assertIn("never lands", s6)
        self.assertIn("append-only", s6)

    def test_review_and_landing_interfaces_keep_safety_constraints(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s5 = self.section(standard, 5).casefold()
        for token in ("same path", "branch", "head", "clean tree", "no collect", "no mutate"):
            with self.subTest(review_token=token):
                self.assertIn(token, s5)

        s7 = self.section(standard, 7).casefold()
        for operation in ("squash", "cherry-pick", "rebase", "merge commit", "reset", "push"):
            with self.subTest(forbidden_operation=operation):
                self.assertIn(operation, s7)
        self.assertIn("fast-forward-only", s7)
        self.assertIn("user dirt", s7)


if __name__ == "__main__":
    unittest.main()
