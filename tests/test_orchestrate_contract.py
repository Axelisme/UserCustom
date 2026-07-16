from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATE = ROOT / "home" / ".codex" / "skills" / "orchestrate"
CODEX_AGENTS = ROOT / "home" / ".codex" / "agents"
CLAUDE_AGENTS = ROOT / "home" / ".claude" / "agents"
TDD_SKILL = ROOT / "home" / ".codex" / "skills" / "tdd" / "SKILL.md"


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class OrchestrateContractTests(unittest.TestCase):
    def test_entrypoint_is_a_small_control_loop(self) -> None:
        path = ORCHESTRATE / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("skill_version: 61", text)
        self.assertLessEqual(len(text.encode("utf-8")), 8_192)
        self.assertLessEqual(len(text.splitlines()), 90)
        for heading in (
            "## Constitution",
            "## Root control loop",
            "## Pipeline shapes",
            "## Context pointers",
            "## Definition of done",
        ):
            self.assertIn(heading, text)
        for moved_heading in (
            "## Hard rules",
            "## Routing fast paths",
            "## Operating loop",
            "## Checkpoint taxonomy",
        ):
            self.assertNotIn(moved_heading, text)

    def test_control_loop_has_checkable_completion_criteria(self) -> None:
        text = normalized(ORCHESTRATE / "SKILL.md")
        self.assertIn("control loop", text)
        self.assertIn("completion criterion", text)
        positions = []
        for step in (
            "Observe",
            "Freeze",
            "Shape",
            "Dispatch",
            "Harvest",
            "Integrate",
            "Re-observe or close",
        ):
            position = text.find(step)
            self.assertGreaterEqual(position, 0, step)
            positions.append(position)
        self.assertEqual(positions, sorted(positions))
        for phrase in (
            "authoritative tree",
            "largest unresolved uncertainty",
            "exact base",
            "test oracle",
            "review barrier",
            "exact SHA/tree",
            "integration checkout is clean",
            "final integrated tree",
        ):
            self.assertIn(phrase, text)

    def test_pipeline_shapes_keep_the_distinguishing_mechanism_inline(self) -> None:
        text = normalized(ORCHESTRATE / "SKILL.md")
        for shape in (
            "root-only",
            "single writer",
            "normal wave",
            "critical checkpoint",
        ):
            self.assertIn(shape, text)
        for phrase in (
            "Planner N+1",
            "Writer N",
            "validated exact SHA",
            "Reviewer N",
            "serial collect",
            "final integrated gate",
            "different-identity adversarial review",
            "finding returns to the writer",
            "refreshed exact-state review",
            "release dependent work",
        ):
            self.assertIn(phrase, text)
        for phrase in (
            "critical-path lead time",
            "milestone is non-blocking",
            "checkpoint is a review barrier",
            "coherent vertical slice",
            "targeted gates",
            "broader gate",
        ):
            self.assertIn(phrase, text)

    def test_constitution_preserves_authority_and_exact_state_evidence(self) -> None:
        text = normalized(ORCHESTRATE / "SKILL.md")
        for phrase in (
            "Git",
            "active reasoning",
            "durable narrative",
            "smallest safe move",
            "actual tree",
            "user authority",
            "persistence landing",
        ):
            self.assertIn(phrase, text)

    def test_references_are_progressive_and_single_read(self) -> None:
        entrypoint = (ORCHESTRATE / "SKILL.md").read_text(encoding="utf-8")
        references = sorted((ORCHESTRATE / "references").glob("*.md"))
        self.assertGreaterEqual(len(references), 6)
        for path in references:
            with self.subTest(path=path.name):
                self.assertIn(
                    "orchestrate_compat: 61", path.read_text(encoding="utf-8")
                )
                self.assertLessEqual(len(path.read_bytes()), 16_384)
                self.assertIn(f"(references/{path.name})", entrypoint)

    def test_wave_and_critical_mechanics_are_disclosed_by_branch(self) -> None:
        references = ORCHESTRATE / "references"
        self.assertTrue((references / "wave-pipeline.md").is_file())
        self.assertTrue((references / "critical-review.md").is_file())
        self.assertFalse((references / "slice-queues.md").exists())
        wave = normalized(references / "wave-pipeline.md")
        self.assertNotIn("event=milestone", wave)
        self.assertNotIn("state=progress|terminal", wave)
        for phrase in (
            "critical-path lead time",
            "coherent vertical slice",
            "non-blocking milestone",
            "focused re-review",
            "broader gate",
        ):
            self.assertIn(phrase, wave)
        critical = normalized(references / "critical-review.md")
        for phrase in (
            "different-identity",
            "exact immutable SHA",
            "hostile reproducer",
            "original implementer",
            "refreshed full review",
        ):
            self.assertIn(phrase, critical)

    def test_dispatch_packet_is_content_not_authority(self) -> None:
        text = normalized(ORCHESTRATE / "references" / "dispatch-packets.md")
        for phrase in (
            "immutable",
            "content-addressed",
            "absolute path",
            "SHA-256",
            "does not authorize execution",
            "Authority",
            "Acceptance",
            "Non-goals",
            "Exact literals",
            "Oracles",
            "Review policy",
            "Stop conditions",
        ):
            self.assertIn(phrase, text)

    def test_one_milestone_envelope_replaces_duplicate_completion_reports(self) -> None:
        for runtime in ("runtime-codex.md", "runtime-claude.md"):
            text = normalized(ORCHESTRATE / runtime)
            for field in (
                "event=milestone",
                "item_id",
                "state=progress|terminal",
                "outcome",
                "subject_sha",
                "evidence",
                "findings",
                "next=continue|idle|stop",
            ):
                self.assertIn(field, text, runtime)
            self.assertNotIn("assigned_work_completed", text)
            self.assertNotIn("delivery_phase", text)
        for agents, suffix in ((CODEX_AGENTS, ".toml"), (CLAUDE_AGENTS, ".md")):
            for role in ("contract-planner", "implementer", "reviewer"):
                profile = normalized(agents / f"{role}{suffix}")
                self.assertIn("one milestone", profile)
                self.assertNotIn("assigned_work_completed", profile)

    def test_runtime_stall_recovery_is_budget_based_not_timer_doctrine(self) -> None:
        for runtime in ("runtime-codex.md", "runtime-claude.md"):
            text = normalized(ORCHESTRATE / runtime)
            for phrase in (
                "checkpoint budget",
                "one liveness ping",
                "interrupt",
                "same identity",
                "not proof of a stall",
            ):
                self.assertIn(phrase, text, runtime)
            self.assertNotIn("60 seconds", text)
            self.assertNotIn("120 seconds", text)

    def test_evidence_and_review_invariants_remain_precise(self) -> None:
        evidence = normalized(ORCHESTRATE / "references" / "evidence-and-handoff.md")
        delegation = normalized(ORCHESTRATE / "references" / "delegation-and-review.md")
        critical = normalized(ORCHESTRATE / "references" / "critical-review.md")
        for phrase in ("baseline-relative", "unusable", "target_sha", "target_tree"):
            self.assertIn(phrase, evidence)
        for phrase in (
            "Writer owns permanent executable tests",
            "Reviewer owns",
            "Integration owns",
        ):
            self.assertIn(phrase, delegation)
        for phrase in (
            "different-identity",
            "exact immutable SHA",
            "hostile reproducer",
        ):
            self.assertIn(phrase, critical)

    def test_spool_remains_at_least_once_transport_only(self) -> None:
        text = normalized(ORCHESTRATE / "references" / "durable-delivery-spool.md")
        for phrase in (
            "at-least-once",
            "Root is the only producer",
            "single consumer",
            "Queue absence is not completion evidence",
            "lost wakeup",
            "No `active/`",
            "No `done/`",
        ):
            self.assertIn(phrase, text)

    def test_tdd_keeps_local_cleanup_and_permanent_test_ownership(self) -> None:
        tdd = normalized(TDD_SKILL)
        delegation = normalized(ORCHESTRATE / "references" / "delegation-and-review.md")
        self.assertIn("Local cleanup after green", tdd)
        self.assertIn("Writer owns permanent executable tests", delegation)
        self.assertIn("temporary reproducers", delegation)

    def test_git_landing_remains_fenced_and_tree_proved(self) -> None:
        text = normalized(ORCHESTRATE / "references" / "git-coordination.md")
        for phrase in (
            "Every persistence landing claims the merge slot",
            "owner token",
            "status=acquired",
            "git diff --quiet task/<task> <landed-commit>",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
