from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATE = ROOT / "home" / ".codex" / "skills" / "orchestrate"
CODEX_AGENTS = ROOT / "home" / ".codex" / "agents"
CLAUDE_AGENTS = ROOT / "home" / ".claude" / "agents"
TDD_SKILL = ROOT / "home" / ".codex" / "skills" / "tdd" / "SKILL.md"
REFERENCE_CONTRACTS = {
    "git-coordination.md": (
        "git merge-base --is-ancestor",
        "merge slot",
    ),
    "delegation-and-review.md": (
        "review-readiness packet",
        "temporary reproducers",
    ),
    "slice-queues.md": (
        "Wave-boundary fix wave",
        "Per-wave metrics",
    ),
    "evidence-and-handoff.md": (
        "Validation anomalies",
        "Session handoff",
    ),
}


def normalized_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class OrchestrateContractTests(unittest.TestCase):
    def test_runtime_bindings_use_current_finding_taxonomy(self) -> None:
        for name in ("runtime-codex.md", "runtime-claude.md"):
            with self.subTest(runtime=name):
                text = (ORCHESTRATE / name).read_text(encoding="utf-8")
                self.assertIn("finding_class", text)
                self.assertIn("mechanically-propagatable", text)
                self.assertIn("design-invalidating", text)
                self.assertIn("dangerous-intermediate", text)
                self.assertIn("scope-collision", text)
                self.assertNotIn("blast_radius", text)
                self.assertNotIn("blast-radius", text)

    def test_codex_binding_allows_the_pre_authorized_normal_wave(self) -> None:
        text = (ORCHESTRATE / "runtime-codex.md").read_text(encoding="utf-8")
        self.assertIn("continue through the pre-authorized normal wave", text)
        self.assertNotIn("one unreviewed slice", text)

    def test_core_defines_green_checkpoint_run_ahead(self) -> None:
        text = normalized_text(ORCHESTRATE / "SKILL.md")
        self.assertIn("skill_version: 51", text)
        self.assertIn("## Routing fast paths", text)
        self.assertIn("TDD cycle", text)
        self.assertIn("green checkpoint", text)
        self.assertIn("behavior-dependent", text)
        self.assertIn("structure-dependent", text)
        self.assertIn("run-ahead evidence, never review sign-off", text)
        self.assertIn("need not create per-slice review debt", text)
        self.assertIn("all critical slices keep", text)
        self.assertIn("never an automatic per-wave gate", text)

    def test_entrypoint_is_bounded_and_routes_progressively(self) -> None:
        path = ORCHESTRATE / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        self.assertLessEqual(len(text.encode("utf-8")), 16_384)
        self.assertLessEqual(len(text.splitlines()), 220)
        for name in REFERENCE_CONTRACTS:
            with self.subTest(reference=name):
                self.assertIn(f"(references/{name})", text)
                self.assertTrue((ORCHESTRATE / "references" / name).is_file())

    def test_disclosed_references_preserve_specialized_contracts(self) -> None:
        for name, phrases in REFERENCE_CONTRACTS.items():
            with self.subTest(reference=name):
                text = normalized_text(ORCHESTRATE / "references" / name)
                for phrase in phrases:
                    self.assertIn(phrase, text)

    def test_hard_rules_remain_closed(self) -> None:
        text = normalized_text(ORCHESTRATE / "SKILL.md")
        self.assertIn("## Hard rules (this is all of them)", text)
        self.assertIn("The full suite runs **once**", text)
        self.assertIn(
            "hardware operation, persistence/migration, public wire schema, security",
            text,
        )
        self.assertIn("landing on them requires the user's explicit authority", text)

    def test_runtime_bindings_carry_green_checkpoint_evidence(self) -> None:
        for name in ("runtime-codex.md", "runtime-claude.md"):
            with self.subTest(runtime=name):
                text = (ORCHESTRATE / name).read_text(encoding="utf-8")
                self.assertIn("green_checkpoint", text)
                self.assertIn("remaining_uncertainty", text)
                self.assertIn("review_target", text)
                self.assertIn("behavior-only", text)
                self.assertIn("structural", text)
                self.assertIn("critical", text)
                self.assertIn("anomaly", text)

    def test_role_profiles_assign_permanent_tests_to_implementer(self) -> None:
        for agents, suffix in ((CODEX_AGENTS, ".toml"), (CLAUDE_AGENTS, ".md")):
            with self.subTest(agent_format=suffix):
                implementer = (agents / f"implementer{suffix}").read_text(
                    encoding="utf-8"
                )
                reviewer = (agents / f"reviewer{suffix}").read_text(encoding="utf-8")
                planner = (agents / f"contract-planner{suffix}").read_text(
                    encoding="utf-8"
                )
                self.assertIn("permanent executable tests", implementer)
                self.assertIn("explicitly designated clean SHA", implementer)
                self.assertIn("permanent regression test", reviewer)
                self.assertIn("Test seams and oracles", planner)

    def test_tdd_allows_local_cleanup_after_green(self) -> None:
        text = TDD_SKILL.read_text(encoding="utf-8")
        self.assertIn("One cycle at a time", text)
        self.assertIn("Local cleanup after green", text)
        self.assertNotIn("Refactoring is not part of the loop", text)


if __name__ == "__main__":
    unittest.main()
