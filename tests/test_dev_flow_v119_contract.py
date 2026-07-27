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
    """Contract for the v128 admission authority and complete S1-S7 behavior."""

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

    def assert_terms(self, section: str, *terms: str) -> None:
        normalized = section.casefold()
        for term in terms:
            with self.subTest(term=term):
                self.assertIn(term.casefold(), normalized)

    def assert_any_term(self, section: str, *terms: str) -> None:
        normalized = section.casefold()
        self.assertTrue(any(term.casefold() in normalized for term in terms), terms)

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

    def test_admission_s1_preserves_observable_deletion_size_and_landability_clauses(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s1 = self.section(standard, "## S1 ", "## S2 ")
        self.assert_terms(
            s1,
            "S1.1 Observable sentence",
            "the user does",
            "<production entrypoint>",
            "refuse the Slice",
            "S1.2 Named deletion",
            "file:symbol",
            "deletes: none",
            "once per task",
            "predecessor",
            "deleting Slice",
            "S1.3 Size",
            "non-test production diff",
            "≤ 1500",
            "S1.4 Independently landable",
            "later Slice",
            "days",
            "weeks",
        )

    def test_admission_s2_preserves_observability_red_evidence_envelope_and_hardening_boundary(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s2 = self.section(standard, "## S2 ", "## S3 ")
        self.assert_terms(
            s2,
            "S2.1 Observability",
            "user",
            "client outside this module",
            "internal objects",
            "hardening",
            "candidate-backlog",
            "S2.2 Red evidence",
            "red without the device",
            "specific",
            "red",
            "evidence",
            "S2.3 Envelope",
            "frozen spec",
            "recorded usage envelope",
        )

    def test_admission_s3_names_all_decidable_checks_and_two_consecutive_stall(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s3 = self.section(standard, "## S3 ", "## S4 ")
        self.assert_terms(
            s3,
            "Reachability",
            "Deletion",
            "Loop",
            "Mass",
            "Focus",
            "Burn-down",
            "Downgrade",
            "S3.8 Stall",
            "two consecutive",
        )

    def test_admission_s4_preserves_cycle_scope_event_spec_width_and_cost_alarm(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s4 = self.section(standard, "## S4 ", "## S5 ")
        self.assert_terms(
            s4,
            "S4.1",
            "machine_rework_cycles",
            "≤ 2",
            "S4.2",
            "third",
            "scope event",
            "exactly three",
            "actions are legal",
            "shrink the Slice",
            "return to S1",
            "downgrade",
            "backlog",
            "report to the user",
            "S4.3",
            "spec-too-wide",
            "100% blocking",
            "S4.4",
            "cost-alarm",
            "S4.5 Provenance",
            "user_acceptance",
            "simplify",
            "standards_review",
            "spec_review",
            "initial simplify",
            "user acceptance",
            "blocked_on_decision",
            "do not increment",
        )

    def test_admission_s4_preserves_closed_blocker_enum_and_decision_routing(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s4 = self.section(standard, "## S4 ", "## S5 ")
        self.assert_terms(
            s4,
            "closed enum",
            "spec_violation",
            "data_loss",
            "security",
            "reproducible_behavior_failure",
            "frozen envelope",
            "contract_basis",
            "backlog",
            "blocked_on_decision",
        )

    def test_admission_s5_preserves_machine_order_integration_bracket_and_exact_sha(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s5 = self.section(standard, "## S5 ", "## S6 ")
        normalized = " ".join(s5.casefold().split())
        for term in ("simplify", "canonical tests", "reviewgate"):
            self.assertIn(term, normalized)
        positions = [normalized.index(term) for term in ("simplify", "canonical tests", "reviewgate")]
        self.assertEqual(positions, sorted(positions), normalized)
        self.assert_terms(
            s5,
            "S5.1 Gated checkpoint",
            "integration-first",
            "review bracket",
            "pre and post",
            "same path",
            "branch",
            "HEAD",
            "clean tree",
            "no collect",
            "no mutate",
            "mismatch invalidates evidence",
            "exact reviewed SHA",
            "same exact SHA",
            "same source",
            "two fresh axes",
            "one reviewer on the originating axis",
        )

    def test_admission_s5_preserves_per_slice_exercise_rejection_reopen_and_staleness(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s5 = self.section(standard, "## S5 ", "## S6 ")
        self.assert_terms(
            s5,
            "S5.2",
            "per Slice",
            "real entrypoint",
            "acceptance does not mutate persistence",
            "not persistence-landed",
            "S5.3",
            "rejection returns the Slice to S1",
            "do not increment",
            "machine_rework_cycles",
            "new exact SHA",
            "reopens",
            "gates",
            "S5.4",
            "outside the frozen usage envelope",
            "spec amendment",
            "new Slice",
            "historical exact-SHA evidence",
            "unless marked stale",
            "dependent provisional checkpoints",
        )

    def test_admission_s6_preserves_mode_inference_queue_depth_and_deferred_state(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s6 = self.section(standard, "## S6 ", "## S7 ")
        self.assert_any_term(s6, "day | night | auto", "day/night/auto")
        self.assert_terms(
            s6,
            "S6.1 Mode",
            "mode_override",
            "user-authored task turn",
            "autonomous continuation",
            "active goal",
            "no live user turn",
            "recomputed",
            "not durable state",
            "S6.2 Queue",
            "phase",
            "phase template",
            "queue",
            "reviewed_awaiting_user",
            "provisional",
            "never means accepted or landed",
            "latest accepted checkpoint",
            "ordered",
            "do not add chain depth",
            "S6.3 Depth",
            "max speculative dependency depth",
            "10",
            "independent pending Slices",
        )

    def test_admission_s6_preserves_oldest_drain_night_no_landing_and_forward_repair(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s6 = self.section(standard, "## S6 ", "## S7 ")
        self.assert_terms(
            s6,
            "S6.4 Drain",
            "oldest-first",
            "dependency order",
            "same-SHA acceptance",
            "machine evidence",
            "without persistence mutation",
            "rejection",
            "descendants stale",
            "S6.5 Landing",
            "Night Mode",
            "never lands",
            "live explicit user request",
            "S6.6 Append-only integration",
            "append-only",
            "never reset",
            "rebase",
            "force-update",
            "forward commits",
            "repaired",
        )

    def test_admission_s7_preserves_authority_target_topology_and_ff_only_prohibitions(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s7 = self.section(standard, "## S7 ")
        self.assert_terms(
            s7,
            "S7.1 Authority",
            "current user authority",
            "S7.2 Exact target",
            "exact SHA recorded as accepted",
            "S7.3 Topology",
            "target is an ancestor of the integration tip",
            "persistence tip is an ancestor of the target",
            "S7.4 Method",
            "fast-forward-only",
            "no squash",
            "cherry-pick",
            "rebase",
            "merge commit",
            "no reset",
            "no push",
        )

    def test_admission_s7_preserves_partial_final_eligibility_cleanup_and_dirt_protection(self) -> None:
        standard = self.read(ADMISSION_PATHS[0])
        s7 = self.section(standard, "## S7 ")
        self.assert_terms(
            s7,
            "S7.5 Partial landing",
            "never performs task cleanup",
            "task integration worktree",
            "refs",
            "phase records",
            "open",
            "S7.6 Final landing",
            "every item accepted",
            "no stale",
            "unresolved",
            "target equal to the current clean integration tip",
            "task integration worktree",
            "role worktrees",
            "integration branches",
            "refs/orchestrate/<task-id>",
            "task phase records",
            "pre-existing",
            "user dirt",
            "non-task evidence",
            "unchanged",
            "before and after cleanup",
            "never delete",
            "stash",
            "reset",
            "overwrite",
            "include them",
        )


if __name__ == "__main__":
    unittest.main()
