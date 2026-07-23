from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
PI_SKILL = HOME / ".pi" / "agent" / "skills" / "orchestrate"
CODEX_SKILL = HOME / ".codex" / "skills" / "orchestrate"


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    end = text.index("\n---", 4)
    return text[:end]


class Pwr08WavePolicyTests(unittest.TestCase):
    def test_pi_wave_profiles_machine_opt_in_and_integration_stays_one_shot(self) -> None:
        for role in ("wave-implementer", "wave-reviewer"):
            path = HOME / ".pi" / "agent" / "agents" / f"{role}.md"
            with self.subTest(path=path):
                self.assertIn("pipeline: true", frontmatter(path))

        integration = HOME / ".pi" / "agent" / "agents" / "integration-reviewer.md"
        self.assertNotIn("pipeline: true", frontmatter(integration))
        self.assertIn("pipeline_capable = false", integration.read_text(encoding="utf-8"))
        self.assertIn("fresh one-shot", integration.read_text(encoding="utf-8"))

    def test_non_pi_mirrors_do_not_claim_runtime_pipeline_capability(self) -> None:
        for role in ("wave-implementer", "wave-reviewer"):
            for path in (
                HOME / ".codex" / "agents" / f"{role}.toml",
                HOME / ".claude" / "agents" / f"{role}.md",
            ):
                with self.subTest(path=path):
                    text = path.read_text(encoding="utf-8")
                    self.assertNotIn("pipeline: true", text)
                    self.assertIn("eligibility, not runtime capability", text)
                    self.assertIn("ordinary fallback", text)

    def test_all_reviewer_mirrors_use_root_owned_immutable_review_jobs(self) -> None:
        paths = (
            HOME / ".pi" / "agent" / "agents" / "wave-reviewer.md",
            HOME / ".codex" / "agents" / "wave-reviewer.toml",
            HOME / ".claude" / "agents" / "wave-reviewer.md",
        )
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn(
                    "Root creates and proves each immutable exact-SHA review job/worktree before dispatch",
                    text,
                )
                self.assertIn("supplies its job cwd in the dispatch", text)
                self.assertIn("Never create, advance, retarget, or clean", text)
                self.assertIn("Reviewed source is read-only", text)
                self.assertIn("exact dispatch-provided receipt path", text)
                self.assertNotIn("Open your own detached checkout", text)
                self.assertNotIn("review checkout <sha>", text)

    def test_all_planner_mirrors_keep_arbitrary_ready_depth_and_root_queue_authority(self) -> None:
        paths = (
            HOME / ".pi" / "agent" / "agents" / "contract-planner.md",
            HOME / ".codex" / "agents" / "contract-planner.toml",
            HOME / ".claude" / "agents" / "contract-planner.md",
        )
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("eligible ready set stocked", text)
                self.assertIn("every dependency- and authority-valid ready slice", text)
                self.assertIn("arbitrary ready depth", text)
                self.assertIn("critical-path ordering", text)
                self.assertIn("decisions before fanout", text)
                self.assertIn("root owns runtime queue placement", text)
                self.assertIn("priority, and timing", text)
                self.assertIn("may release any dependency- and authority-valid ready depth", text)
                self.assertIn("there is no global one-deep queue", text)
                self.assertIn("proposes stock only", text)
                self.assertIn("never mutates runtime queue", text)
                for stale in (
                    "next ready slice",
                    "never deeper",
                    "stock goes stale",
                    "Do not pad speculative",
                    "releases waves one at a time",
                ):
                    self.assertNotIn(stale, text)

    def test_pi_binding_is_concise_and_preserves_runtime_neutral_authority(self) -> None:
        text = " ".join((PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        for phrase in (
            "Pi recommends pipeline attachment for wave roles",
            "root ordinary-launches then attaches",
            "even for one",
            "verify the loaded runtime advertises `pipeline`",
            "name any fallback",
            "policy authority",
        ):
            self.assertIn(phrase, text)

    def test_codex_is_explicit_named_ordinary_fallback(self) -> None:
        text = " ".join((CODEX_SKILL / "runtime-codex.md").read_text(encoding="utf-8").split())
        for phrase in (
            "does not implement or emulate a durable `pipeline` queue",
            "explicit pipeline-capable profile contract",
            "concrete non-attach reason",
            "pipeline capability unavailable in Codex runtime",
            "named ordinary one-deep fallback",
            "only one-deep policy",
            "explicit no-durable-runtime fallback",
            "not a global review-lag cap",
            "integration-reviewer` remains a fresh one-shot role",
            "must not claim pipeline persistence",
        ):
            self.assertIn(phrase, text)

    def test_common_policy_removes_global_depth_cap(self) -> None:
        for skill in (PI_SKILL, CODEX_SKILL):
            with self.subTest(skill=skill):
                skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
                coordination = (skill / "references" / "coordination.md").read_text(encoding="utf-8")
                self.assertNotIn("Depth one only", skill_text)
                self.assertNotIn("depth one only", skill_text)
                self.assertIn("arbitrary ready depth", skill_text)
                self.assertNotIn("Depth one only", coordination)
                self.assertNotIn("depth one only", coordination)
                policy = " ".join(coordination.split())
                for phrase in (
                    "Pi wave roles default to attach",
                    "one item still attaches",
                    "non-attach names a reason",
                    "Root owns ready queues",
                    "cross-lane blocking",
                    "cost-growing holds",
                    "Reviewers keep one latest frontier",
                    "integration review stays one-shot",
                ):
                    self.assertIn(phrase, policy)

    def test_pi_runtime_binding_is_mirrored(self) -> None:
        self.assertEqual(
            (PI_SKILL / "runtime-pi.md").read_bytes(),
            (CODEX_SKILL / "runtime-pi.md").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
