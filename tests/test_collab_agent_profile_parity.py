from __future__ import annotations

import unittest
from pathlib import Path

try:
    from tests import _profile_test_support as support
except ImportError:  # Direct test-file execution keeps tests/ on sys.path.
    import _profile_test_support as support

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"

PROFILE_NAMES = (
    "collab-acceptor",
    "collab-implementer",
    "contract-reviewer",
    "repo-investigator",
    "mechanical-implementer",
)

# The two Collab roles carry runtime-specific tooling, so their three copies are not byte-identical
# and cannot be checked the way the profiles below are.
PARITY_NAMES = (
    "contract-reviewer",
    "repo-investigator",
    "mechanical-implementer",
)

# A dispatched child reads one profile: not the other runtimes' copies of it, and not the dev-flow
# references that own these rules. Each clause is therefore a deliberate per-partition copy, and a
# copy without a consistency test is how five of them silently went missing from Codex and Claude.
# A clause earns a place here by blocking, authorizing, or obliging the role — not by being shared
# wording, which stays each runtime's own business.
SHARED_CLAUSES = {
    "collab-implementer": (
        # The ticket's own `## Mechanical gates` order governs when it states one. It usually does
        # not survive publication, so the default belongs where the writer already is.
        "focused (or explicitly failing) → affected → formatter/style",
        # A mandatory `BLOCKED` keyed to that reference's publication preconditions needs its path.
        "references/ticket-seam-contract.md",
        # record-hygiene grants the writer this container and expects the role to derive it.
        "`scripts/` subtree",
        # An acceptor blocks a moved seam left undeclared; the writer is told what to declare.
        "error modes, lifecycle and ownership, required configuration",
        "class rather than only the named examples",
        "when closure requires wider scope",
        "completed the exact assigned appendix",
        "## Assigned ticket checkboxes",
    ),
    "collab-acceptor": (
        # Without this section the writer fills an appendix no reviewer knows how to judge.
        "## Acceptance appendix",
        "A directly observable claim must remain appendix-free",
        "references/ticket-seam-contract.md",
        # Dropping the qualifier turns an out-of-envelope finding back into a blocker.
        "whether inside or outside the envelope",
        "references/efficiency-feedback.md",
        "## Writer-maintained checkboxes",
    ),
}


class CollabAgentProfileParityTests(unittest.TestCase):
    def test_allowed_copies_are_identical_in_body(self) -> None:
        for name in PARITY_NAMES:
            with self.subTest(profile=name):
                profile = support.load_runtime_profile(HOME, name)
                support.assert_prompt_parity(self, profile)

    def test_shared_clauses_reach_every_runtime_copy(self) -> None:
        for name, clauses in SHARED_CLAUSES.items():
            profile = support.load_runtime_profile(HOME, name)
            for runtime, prompt in support.runtime_prompts(profile).items():
                for clause in clauses:
                    with self.subTest(profile=name, runtime=runtime, clause=clause):
                        # assertIn would print the whole profile body on failure.
                        self.assertTrue(
                            clause in prompt,
                            f"{name}/{runtime} is missing the shared clause {clause!r}",
                        )

    def test_orchestrator_readable_sections_exist_in_every_runtime_copy(self) -> None:
        # collab/SKILL.md bounds the Orchestrator's read of a receiver profile to that profile's
        # `Dispatch contract` and `Result` sections. Bodies may diverge per runtime; these two
        # sections may not go missing, or that instruction dangles under the runtime that lacks one.
        for name in ("collab-implementer", "collab-acceptor"):
            profile = support.load_runtime_profile(HOME, name)
            for runtime, prompt in support.runtime_prompts(profile).items():
                with self.subTest(profile=name, runtime=runtime):
                    headings = support.section_headings(prompt)
                    self.assertIn("## Dispatch contract", headings)
                    self.assertTrue(
                        any(heading.startswith("## Result") for heading in headings),
                        f"{name}/{runtime} carries no Result section: {headings}",
                    )


if __name__ == "__main__":
    unittest.main()
