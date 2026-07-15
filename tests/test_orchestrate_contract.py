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
        self.assertIn("skill_version: 58", text)
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
        self.assertIn("Role Pipeline Contract", text)
        self.assertIn("continue_without_ack", text)
        self.assertIn("Planner", text)
        self.assertIn("Reviewer", text)

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
                    "orchestrate_compat: 58", path.read_text(encoding="utf-8")
                )

    def test_role_pipeline_keeps_live_queue_in_context(self) -> None:
        core = normalized_text(ORCHESTRATE / "SKILL.md")
        queues = normalized_text(ORCHESTRATE / "references" / "slice-queues.md")
        self.assertIn("Root is the only control plane", core)
        self.assertIn("Live planner/writer/reviewer queues stay in agent context", core)
        self.assertIn("No script advances, dequeues, dispatches", core)
        self.assertIn("## Shared Role Pipeline Contract", queues)
        self.assertIn("live queue exists only in agent context", queues)
        self.assertIn("Never create a queue file, queue manager", queues)
        self.assertIn("autonomous coordination controller", queues)
        self.assertIn("must not write workflow state", queues)

    def test_planner_is_exactly_one_wave_ahead(self) -> None:
        queues = normalized_text(ORCHESTRATE / "references" / "slice-queues.md")
        self.assertIn("planning_mode=contract-resolution|wave-ahead", queues)
        self.assertIn("proposes exactly Wave N+1", queues)
        self.assertIn("never plans N+2", queues)
        for agents, suffix in ((CODEX_AGENTS, ".toml"), (CLAUDE_AGENTS, ".md")):
            planner = (agents / f"contract-planner{suffix}").read_text(encoding="utf-8")
            self.assertIn("planning_mode=contract-resolution|wave-ahead", planner)
            self.assertIn("PLAN_MILESTONE", planner)
            self.assertIn("Wave N+2", planner)
            self.assertIn("never freezes the proposal", planner)

    def test_reviewer_pipeline_continues_pass_without_ack(self) -> None:
        delegation = normalized_text(
            ORCHESTRATE / "references" / "delegation-and-review.md"
        )
        self.assertIn("## Reviewer pipeline", delegation)
        self.assertIn("`pass` plus a ready packet permits continuation", delegation)
        self.assertIn("Other outcomes stop by default", delegation)
        self.assertIn("independent-nonblocking", delegation)
        for agents, suffix in ((CODEX_AGENTS, ".toml"), (CLAUDE_AGENTS, ".md")):
            reviewer = (agents / f"reviewer{suffix}").read_text(encoding="utf-8")
            self.assertIn("Role Pipeline Contract consumer", reviewer)
            self.assertIn("PASS plus an already-ready packet", reviewer)
            self.assertIn("continues without acknowledgment", reviewer)
            self.assertIn("needs_fix", reviewer)

    def test_review_policy_is_separate_from_queue_mechanics(self) -> None:
        queues = normalized_text(ORCHESTRATE / "references" / "slice-queues.md")
        self.assertIn(
            "review_cadence: none | cumulative | selected | per-slice", queues
        )
        self.assertIn("review_waiting: async | before-dependent | before-next", queues)
        self.assertIn(
            "review_continuation: pass-only | independent-nonblocking", queues
        )
        self.assertIn("Pipeline mechanics do not imply per-slice review", queues)

    def test_runtime_bindings_cover_all_pipeline_roles(self) -> None:
        for name in ("runtime-codex.md", "runtime-claude.md"):
            with self.subTest(runtime=name):
                text = (ORCHESTRATE / name).read_text(encoding="utf-8")
                self.assertIn("PLAN_MILESTONE", text)
                self.assertIn("REVIEW_MILESTONE", text)
                self.assertIn("continue_without_ack", text)
                self.assertIn("wave-ahead", text)
                self.assertIn("pass", text.lower())

    def test_disclosed_docs_fit_single_read_budget(self) -> None:
        paths = [
            ORCHESTRATE / "SKILL.md",
            *(ORCHESTRATE / "references").glob("*.md"),
            ORCHESTRATE / "runtime-codex.md",
            ORCHESTRATE / "runtime-claude.md",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertLessEqual(len(path.read_bytes()), 16_384)

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
        self.assertIn("Omit timing fields with no observation", text)
        self.assertIn("not wave wall/wait time", text)
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
        self.assertIn("checkpoint <task-id>", text)
        self.assertIn("no unresolved finding", text)

    def test_durable_decisions_separate_effect_from_recording(self) -> None:
        text = normalized_text(ORCHESTRATE / "references" / "evidence-and-handoff.md")
        self.assertIn("Decisions take effect in the in-band control plane", text)
        self.assertIn("conclusion or ADR pointer", text)
        self.assertIn("never dispatches work or triggers a state transition", text)
        self.assertIn("checkpoint <task-id>", text)
        self.assertIn("status remains read-only", text)

    def test_v57_aliases_are_stateless_explicit_guards(self) -> None:
        core = normalized_text(ORCHESTRATE / "SKILL.md")
        git = normalized_text(ORCHESTRATE / "references" / "git-coordination.md")
        self.assertIn("## Inspection and safety aliases", core)
        for command in (
            "orchestrate doctor",
            "orchestrate identity",
            "orchestrate status",
            "orchestrate lane create",
            "orchestrate review checkout",
            "orchestrate collect",
            "orchestrate lane cleanup",
            "plan checkpoint",
        ):
            self.assertIn(command, core)
        self.assertIn("stateless guards", git)
        self.assertIn("never infer a verdict or queue state", git)

    def test_oversized_critical_slice_has_one_acceptance_domain(self) -> None:
        queues = normalized_text(ORCHESTRATE / "references" / "slice-queues.md")
        self.assertIn("at least two hard axes or three authority boundaries", queues)
        self.assertIn("exactly one acceptance domain", queues)
        self.assertIn("2–4 explicit progress checkpoints", queues)
        self.assertIn("one final review checkpoint/formal review", queues)

    def test_reviewer_parking_does_not_assume_runtime_capability(self) -> None:
        delegation = normalized_text(
            ORCHESTRATE / "references" / "delegation-and-review.md"
        )
        self.assertIn("slot-free parking", delegation)
        self.assertIn("slot-free|slot-held|unknown", delegation)
        for agents, suffix in ((CODEX_AGENTS, ".toml"), (CLAUDE_AGENTS, ".md")):
            reviewer = (agents / f"reviewer{suffix}").read_text(encoding="utf-8")
            self.assertIn("without surrendering the logical lease", reviewer)
            self.assertIn("active concurrency slot", reviewer)

    def test_turn_queue_freeze_is_recommended_not_mandatory(self) -> None:
        core = normalized_text(ORCHESTRATE / "SKILL.md")
        queues = normalized_text(ORCHESTRATE / "references" / "slice-queues.md")
        self.assertIn("recommended turn shape", core)
        self.assertIn("frozen bounded queue", core)
        self.assertIn("not a hard rule", core)
        self.assertIn("routine work is not drip-fed", queues)
        self.assertIn("major review finding", queues)
        self.assertIn("immediate notification", queues)
        self.assertIn("predeclared readiness", queues)

    def test_work_bearing_delta_uses_followup_without_status_branch(self) -> None:
        runtime = normalized_text(ORCHESTRATE / "runtime-codex.md")
        self.assertIn("work-bearing delta", runtime)
        self.assertIn("always uses `followup_task`", runtime)
        self.assertIn("running→idle race", runtime)
        self.assertIn("pure notification", runtime)
        self.assertNotIn(
            "running role receives an appended ready item by `send_message`/`followup_task`",
            runtime,
        )

    def test_tail_wave_does_not_pad_to_three_slices(self) -> None:
        core = normalized_text(ORCHESTRATE / "SKILL.md")
        queues = normalized_text(ORCHESTRATE / "references" / "slice-queues.md")
        runtime = normalized_text(ORCHESTRATE / "runtime-codex.md")
        self.assertIn("target 3–5 slices", core)
        self.assertIn("tail/final wave may contain 1–2", queues)
        self.assertIn("never pad", queues)
        self.assertIn("tail=1-2", runtime)

    def test_every_persistence_landing_is_fenced_and_tree_proved(self) -> None:
        core = normalized_text(ORCHESTRATE / "SKILL.md")
        git = normalized_text(ORCHESTRATE / "references" / "git-coordination.md")
        self.assertIn("Every persistence landing claims", git)
        self.assertIn("owner token", git)
        self.assertIn("status=acquired", git)
        self.assertIn("verify <task>", git)
        self.assertIn("git diff --quiet task/<task> <landed-commit>", git)
        self.assertIn(
            "successful evidence must bind to the final integrated tree", core
        )
        self.assertIn("Any later code change invalidates it", core)
        self.assertNotIn("broadest gate required by the repo and risk** once", core)

    def test_major_review_finding_is_reported_before_target_completion(self) -> None:
        delegation = normalized_text(
            ORCHESTRATE / "references" / "delegation-and-review.md"
        )
        self.assertIn("confirmed major review finding", delegation)
        self.assertIn("immediately", delegation)
        for agents, suffix in ((CODEX_AGENTS, ".toml"), (CLAUDE_AGENTS, ".md")):
            reviewer = normalized_text(agents / f"reviewer{suffix}")
            self.assertIn("confirmed major finding", reviewer)
            self.assertIn("immediately notify root", reviewer)

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
                for profile in (implementer, reviewer, planner):
                    self.assertIn("Role Pipeline Contract consumer", profile)
                    self.assertIn("continue_without_ack", profile)

    def test_tdd_allows_local_cleanup_after_green(self) -> None:
        text = TDD_SKILL.read_text(encoding="utf-8")
        self.assertIn("One cycle at a time", text)
        self.assertIn("Local cleanup after green", text)
        self.assertNotIn("Refactoring is not part of the loop", text)


if __name__ == "__main__":
    unittest.main()
