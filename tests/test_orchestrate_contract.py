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

    def test_core_defines_checkpoint_taxonomy_and_run_ahead(self) -> None:
        text = normalized_text(ORCHESTRATE / "SKILL.md")
        self.assertIn("skill_version: 54", text)
        self.assertIn("## Routing fast paths", text)
        self.assertIn("checkpoint_kind", text)
        self.assertIn("progress", text)
        self.assertIn("validated", text)
        self.assertIn("review", text)
        self.assertIn("TDD cycle", text)
        self.assertIn("green checkpoint", text)
        self.assertIn("TDD subtype", text)
        self.assertIn("targeted-acceptance", text)
        self.assertIn("behavior-dependent", text)
        self.assertIn("structure-dependent", text)
        self.assertIn("run-ahead evidence, never review sign-off", text)
        self.assertIn("hard-critical slices keep", text)
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
        self.assertIn("hard_critical_axes", text)
        self.assertIn("named_review_risks", text)
        self.assertIn(
            "hardware operation, persistence/migration, public wire schema, security",
            text,
        )
        self.assertIn("broadest gate required by the repo and risk", text)
        self.assertIn("If that is not the full suite", text)
        self.assertNotIn("The full suite runs **once**", text)
        self.assertIn("landing on them requires the user's explicit authority", text)

    def test_runtime_bindings_carry_checkpoint_specific_payloads(self) -> None:
        for name in ("runtime-codex.md", "runtime-claude.md"):
            with self.subTest(runtime=name):
                text = (ORCHESTRATE / name).read_text(encoding="utf-8")
                self.assertIn("checkpoint_kind", text)
                self.assertIn("progress", text)
                self.assertIn("validated", text)
                self.assertIn("review", text)
                self.assertIn("completion", text)
                self.assertIn("stop_reason", text)
                self.assertIn("tdd-green", text)
                self.assertIn("targeted-acceptance", text)
                self.assertIn("remaining_uncertainty", text)
                self.assertIn("behavior-only", text)
                self.assertIn("structural", text)
                self.assertIn("hard-critical", text)
                self.assertIn("anomaly", text)
                self.assertIn("diagnostics", text)
                self.assertIn("non-gating", text)
                self.assertIn("non-review evidence", text)
                self.assertNotIn("review_target", text)

    def test_disclosed_files_match_entrypoint_compatibility(self) -> None:
        paths = [
            *(ORCHESTRATE / "references").glob("*.md"),
            ORCHESTRATE / "runtime-codex.md",
            ORCHESTRATE / "runtime-claude.md",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertIn(
                    "orchestrate_compat: 54", path.read_text(encoding="utf-8")
                )

    def test_codex_wait_is_event_driven_not_single_shot(self) -> None:
        text = normalized_text(ORCHESTRATE / "runtime-codex.md")
        self.assertIn("Repeated event-driven `wait_agent`", text)
        self.assertIn("timeout", text)
        self.assertIn("user update", text)
        self.assertIn("Do not infer an agent's phase from `running`", text)
        self.assertNotIn("a single `wait_agent` result", text)

    def test_telemetry_accepts_unknown_without_guessing(self) -> None:
        text = normalized_text(ORCHESTRATE / "references" / "slice-queues.md")
        self.assertIn("wall=~18m", text)
        self.assertIn("wait=unknown", text)
        self.assertIn("Never reconstruct or guess timing", text)
        self.assertIn("review=<initial reviews/time>", text)
        self.assertIn("re-review=<closure or refreshed-SHA reviews/time>", text)
        self.assertIn("re-verify=<writer/root fix checks/time>", text)
        self.assertIn("Never infer re-review from rounds", text)

    def test_wave_close_maintains_durable_narrative(self) -> None:
        text = normalized_text(ORCHESTRATE / "references" / "slice-queues.md")
        self.assertIn("## Wave-boundary narrative maintenance", text)
        self.assertIn("reconcile Current State against Git", text)
        self.assertIn("only open/deferred review findings", text)
        self.assertIn("counts plus evidence pointers", text)
        self.assertIn("compact <task-id>", text)
        self.assertIn("no unresolved finding", text)

    def test_durable_decisions_separate_effect_from_recording(self) -> None:
        text = normalized_text(ORCHESTRATE / "references" / "evidence-and-handoff.md")
        self.assertIn("Decisions take effect in the in-band control plane", text)
        self.assertIn("conclusion or ADR pointer", text)
        self.assertIn("never dispatches work or triggers a state transition", text)
        self.assertIn("compact <task-id>", text)
        self.assertIn("status remains read-only", text)

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
                self.assertIn("checkpoint_kind=progress|validated|review", implementer)
                self.assertIn("finding_class", implementer)
                self.assertIn("diagnostics", implementer)
                self.assertIn("non-gating, non-review evidence", implementer)
                self.assertNotIn("review_target", implementer)
                self.assertIn("permanent regression test", reviewer)
                self.assertIn("checkpoint_kind=review", reviewer)
                self.assertIn("Test seams and oracles", planner)

    def test_tdd_allows_local_cleanup_after_green(self) -> None:
        text = TDD_SKILL.read_text(encoding="utf-8")
        self.assertIn("One cycle at a time", text)
        self.assertIn("Local cleanup after green", text)
        self.assertNotIn("Refactoring is not part of the loop", text)


if __name__ == "__main__":
    unittest.main()
