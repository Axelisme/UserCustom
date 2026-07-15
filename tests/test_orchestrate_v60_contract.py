from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"


class OrchestrateV60ContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_release_and_compat_are_60(self) -> None:
        self.assertIn(
            "skill_version: 60",
            self.read("home/.codex/skills/orchestrate/SKILL.md"),
        )
        for relative in (
            "home/.codex/skills/orchestrate/runtime-codex.md",
            "home/.codex/skills/orchestrate/runtime-claude.md",
            "home/.codex/skills/orchestrate/references/delegation-and-review.md",
            "home/.codex/skills/orchestrate/references/evidence-and-handoff.md",
            "home/.codex/skills/orchestrate/references/git-coordination.md",
            "home/.codex/skills/orchestrate/references/slice-queues.md",
            "home/.codex/skills/orchestrate/references/durable-delivery-spool.md",
        ):
            self.assertIn("orchestrate_compat: 60", self.read(relative), relative)

        for relative in (
            "home/.codex/agents/contract-planner.toml",
            "home/.codex/agents/implementer.toml",
            "home/.codex/agents/reviewer.toml",
            "home/.claude/agents/contract-planner.md",
            "home/.claude/agents/implementer.md",
            "home/.claude/agents/reviewer.md",
        ):
            self.assertIn("orchestrate_compat: 60", self.read(relative), relative)

        manifest = json.loads(
            (SKILL / "manifests" / "60.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["skill_version"], 60)
        self.assertEqual(manifest["release_delta"]["from_version"], 59)

    def test_entrypoint_names_bounded_delivery_spool_exception(self) -> None:
        text = " ".join(self.read("home/.codex/skills/orchestrate/SKILL.md").split())
        self.assertIn("three authoritative carriers", text)
        self.assertIn("durable delivery spool", text)
        self.assertIn("at-least-once", text)
        self.assertIn("Queue absence is not completion evidence", text)
        self.assertIn("queue publish", text)
        self.assertIn("queue inspect", text)
        self.assertIn("queue remove", text)

    def test_delivery_spool_contract_is_closed_and_recoverable(self) -> None:
        text = " ".join(
            self.read(
                "home/.codex/skills/orchestrate/references/durable-delivery-spool.md"
            ).split()
        )
        for phrase in (
            "Root is the only producer",
            "single consumer",
            "at-least-once",
            "terminal milestone",
            "lease_generation",
            "generation",
            "completion-side",
            "lost wakeup",
            "No `active/`",
            "No `done/`",
            "never infer readiness",
            "normal writer/reviewer",
            "Planner",
            "hard-critical",
        ):
            self.assertIn(phrase, text)
        self.assertIn("not an exactly-once protocol", text)

    def test_slice_queue_and_evidence_boundaries_match_spool(self) -> None:
        queues = self.read("home/.codex/skills/orchestrate/references/slice-queues.md")
        evidence = self.read(
            "home/.codex/skills/orchestrate/references/evidence-and-handoff.md"
        )
        self.assertIn("durable delivery spool", queues)
        self.assertIn("already-ready", queues)
        self.assertIn("bounded wave", queues)
        self.assertIn("does not create review debt", queues)
        self.assertIn("reconcile", evidence)
        self.assertIn("does not auto-resume", evidence)

    def test_runtime_defines_symmetric_event_driven_wakeup(self) -> None:
        for runtime in ("runtime-codex.md", "runtime-claude.md"):
            text = self.read(f"home/.codex/skills/orchestrate/{runtime}")
            for phrase in (
                "absolute queue path",
                "publish",
                "idle",
                "completion event",
                "item boundary",
                "not polling",
                "urgent",
            ):
                self.assertIn(phrase, text, runtime)

    def test_role_profiles_carry_consumer_rules_but_planner_is_excluded(self) -> None:
        for relative in (
            "home/.codex/agents/implementer.toml",
            "home/.codex/agents/reviewer.toml",
            "home/.claude/agents/implementer.md",
            "home/.claude/agents/reviewer.md",
        ):
            text = self.read(relative)
            for phrase in (
                "absolute queue path",
                "lease_generation",
                "item boundary",
                "terminal milestone",
                "at-least-once",
            ):
                self.assertIn(phrase, text, relative)

        for relative in (
            "home/.codex/agents/contract-planner.toml",
            "home/.claude/agents/contract-planner.md",
        ):
            text = self.read(relative)
            self.assertIn("v60", text, relative)
            self.assertIn("does not use the durable delivery spool", text, relative)


if __name__ == "__main__":
    unittest.main()
