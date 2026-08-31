from __future__ import annotations

import re
import unittest
from pathlib import Path

try:
    from tests import _profile_test_support as support
except ImportError:  # Direct test-file execution keeps tests/ on sys.path.
    import _profile_test_support as support

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"

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
        # A mandatory `BLOCKED` keyed to that reference's publication preconditions needs its path.
        "references/ticket-seam-contract.md",
        # record-hygiene grants the writer this container and expects the role to derive it.
        "`scripts/` subtree",
        # An acceptor blocks a moved seam left undeclared; the writer is told what to declare.
        "error modes, lifecycle and ownership, required configuration",
        "class rather than only the named examples",
        "when closure requires wider scope",
        "completed the exact assigned appendix",
        "references/efficiency-feedback.md",
        # The writer position, not the dispatch, decides which boxes are this role's to toggle.
        "## Acceptance checkboxes you own",
        "the Acceptance claims that name no observer are yours",
        "references/lane-authority.md",
        # The copy is ceremony unless the rule reaches the moment the file is filled.
        "never a whole-file write",
        # Without the sweep the terminal condition is gates alone, which is what let a checkbox
        # proved in hour one ride out to handoff unexamined.
        "closing sweep",
        "re-verified against the final tree",
        # The writer cannot legally record the sweep unless its own prose exception says so.
        "`Swept at`",
        # A gate routed around is not a gate closed; without this the writer's only visible option
        # is the workaround.
        "can only be made to pass by changing what it measures",
    ),
    "collab-acceptor": (
        # Without these the writer fills an appendix no reviewer knows how to judge.
        "## Acceptance appendix",
        "blocks Acceptance rather than being trusted on presence",
        "describes a reasonable process",
        "grants no task-record mutation",
        "remain appendix-free and is judged from the lane itself",
        "references/ticket-seam-contract.md",
        "you do not re-execute gates",
        # Dropping the qualifier turns an out-of-envelope finding back into a blocker.
        "whether inside or outside the envelope",
        "references/efficiency-feedback.md",
        "## Writer-maintained checkboxes",
        # Without these the acceptor reports a legitimate toggle, or an unproven claim, as a defect.
        "belongs to whoever held the lane's write token",
        "An unchecked claim is not by itself a defect",
        "references/lane-authority.md",
        # A hollow pass violates no claim, so a claim-scoped subject cannot reach it.
        "gate integrity",
        "the pass is hollow",
        # Reading the diff for it must not read as re-executing a gate the role may not run.
        "is not re-execution",
        # Without this the acceptor reports the writer's own sweep record as an unauthorized write.
        "`Swept at`",
        # The appendix is supporting evidence, never a substitute for reading the lane.
        "an appendix never stands in for reading the",
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

    def test_gate_repair_order_matches_the_ticket_template(self) -> None:
        # The order is copied because its two readers cannot reach each other: the Orchestrator
        # drafting a ticket reads the template, the dispatched writer reads only its own profile.
        # Reading it out of the template rather than restating it here keeps this a match check,
        # so rewording the rule in both places stays legal and rewording one of them does not.
        template = (HOME / ".codex/skills/dev-flow/templates/ticket/ticket.md").read_text("utf-8")
        match = re.search(r"Implementer runs in order: ([^\n]+)", template)
        self.assertIsNotNone(match, "the ticket template no longer states the gate repair order")
        order = match.group(1).strip()
        self.assertTrue(
            order.endswith("."),
            f"the template's repair order runs past one line, so this check would only compare "
            f"its first fragment: {order}",
        )
        profile = support.load_runtime_profile(HOME, "collab-implementer")
        for runtime, prompt in support.runtime_prompts(profile).items():
            with self.subTest(runtime=runtime):
                self.assertTrue(
                    order in prompt,
                    f"collab-implementer/{runtime} does not carry the template's repair order: {order}",
                )

    def test_skill_paths_named_for_agents_resolve(self) -> None:
        # A pointer is the whole of its reader's route to the rule: the reader cannot ask where a
        # moved file went. Renaming a reference is how one goes silently dangling, so every
        # installed-form path an agent is sent to must exist — in the profiles and in the two
        # skills' own documents alike.
        sources = {}
        for name in PARITY_NAMES + tuple(SHARED_CLAUSES):
            profile = support.load_runtime_profile(HOME, name)
            for runtime, prompt in support.runtime_prompts(profile).items():
                sources[f"{name}/{runtime}"] = prompt
        for skill in ("dev-flow", "collab"):
            for doc in sorted((HOME / ".codex/skills" / skill).rglob("*.md")):
                sources[str(doc.relative_to(HOME))] = doc.read_text("utf-8")

        checked = 0
        for source, text in sources.items():
            for path in re.findall(r"~/\.codex/skills/[\w./-]+?\.\w+", text):
                checked += 1
                with self.subTest(source=source, path=path):
                    target = HOME / ".codex" / path.split("~/.codex/", 1)[1]
                    self.assertTrue(
                        target.exists(), f"{source} points at {path}, which does not exist"
                    )
        self.assertGreater(checked, 0, "the path regex matched nothing; it has stopped checking")

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
