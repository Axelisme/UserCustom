from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from tests import _profile_test_support as support
except ImportError:  # Direct test-file execution keeps tests/ on sys.path.
    import _profile_test_support as support

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"

# The two Collab roles carry runtime-specific tooling, so their three copies are not byte-identical
# and are checked below modulo COLLAB_ROLE_DELTAS instead of the byte-identity check used here.
PARITY_NAMES = (
    "contract-reviewer",
    "repo-investigator",
    "mechanical-implementer",
)

# Every explicitly allowed divergence between a Collab role's three runtime copies. A copy not
# named here must match the other two, whitespace aside; an undeclared difference fails the parity
# assertion and prints the offending diff. Each entry records profile, runtime, location and reason,
# never the diverging wording — see `DeclaredDelta`. Dead registry entries deliberately have no
# dedicated diagnostic: unknown profiles are never selected, and absent locations remove no compared
# body. Add registry coverage only after dead declarations become an observed cost.
COLLAB_ROLE_NAMES = ("collab-implementer", "collab-acceptor")
# Herdr dispatches the two Collab roles from its own registry, so their Pi copies do not sit beside
# the ordinary agent profiles the parity names above use.
COLLAB_PI_DIR = ".pi/agent/herdr-subagents/profiles"
COLLAB_ROLE_DELTAS: tuple[support.DeclaredDelta, ...] = (
    support.DeclaredDelta(
        profile="collab-implementer",
        runtime="codex",
        location="## Reorientation after compaction",
        reason=(
            "Known pre-existing defect: Codex's copy carries no Reorientation section. The task "
            "envelope explicitly forbids fixing this here; it is registered on candidate-backlog "
            "instead."
        ),
    ),
    support.DeclaredDelta(
        profile="collab-acceptor",
        runtime="codex",
        location="## Reorientation after compaction",
        reason=(
            "Known pre-existing defect: Codex's copy carries no Reorientation section. The task "
            "envelope explicitly forbids fixing this here; it is registered on candidate-backlog "
            "instead."
        ),
    ),
)


class CollabAgentProfileParityTests(unittest.TestCase):
    def test_allowed_copies_are_identical_in_body(self) -> None:
        for name in PARITY_NAMES:
            with self.subTest(profile=name):
                profile = support.load_runtime_profile(HOME, name)
                support.assert_prompt_parity(self, profile)

    def test_collab_role_copies_are_identical_modulo_declared_deltas(self) -> None:
        for name in COLLAB_ROLE_NAMES:
            profile = support.load_runtime_profile(HOME, name, pi_dir=COLLAB_PI_DIR)
            deltas = tuple(delta for delta in COLLAB_ROLE_DELTAS if delta.profile == name)
            with self.subTest(profile=name):
                support.assert_prompt_parity(
                    self,
                    profile,
                    profile_name=name,
                    deltas=deltas,
                )

    @staticmethod
    def _result_delta(runtime: str = "pi") -> support.DeclaredDelta:
        return support.DeclaredDelta(
            profile="collab-implementer",
            runtime=runtime,
            location="## Result",
            reason="synthetic runtime-specific result behavior",
        )

    def _assert_synthetic_parity_failure(
        self,
        prompts: dict[str, str],
        deltas: tuple[support.DeclaredDelta, ...],
    ) -> str:
        profile = support.RuntimeProfile(
            pi_path=Path("pi.md"),
            claude_path=Path("claude.md"),
            codex_path=Path("codex.toml"),
            prompt=prompts["pi"],
        )
        with patch.object(support, "runtime_prompts", return_value=prompts):
            with self.assertRaises(AssertionError) as raised:
                support.assert_prompt_parity(
                    self,
                    profile,
                    profile_name="collab-implementer",
                    deltas=deltas,
                )
        return str(raised.exception)

    def test_non_exempt_duplicate_section_fails_with_occurrence_diagnostic(self) -> None:
        prompts = {
            "pi": "## Result\npi-specific",
            "claude": "## Result\nshared",
            "codex": "## Result\nshared\n## Result\n",
        }
        failure = self._assert_synthetic_parity_failure(prompts, (self._result_delta(),))

        self.assertEqual(
            support.prompt_sections(prompts["codex"])["## Result"],
            ("shared", ""),
        )
        self.assertIn("occurrence", failure)
        self.assertIn("2:", failure)
        self.assertIn("## Result", failure)
        self.assertIn("differs outside its declared runtime deltas", failure)

    def test_absent_and_present_empty_sections_are_distinct(self) -> None:
        prompts = {
            "pi": "## Result\npi-specific",
            "claude": "## Result\n",
            "codex": "",
        }
        failure = self._assert_synthetic_parity_failure(prompts, (self._result_delta(),))

        self.assertIn("occurrence", failure)
        self.assertIn("''", failure)
        self.assertIn("absent", failure)
        self.assertIn("occurrences", failure)

    def test_multiple_declarations_for_one_location_fail_explicitly(self) -> None:
        prompts = {
            "pi": "## Result\nshared",
            "claude": "## Result\nshared",
            "codex": "## Result\nshared",
        }
        for runtimes in (("pi", "pi"), ("pi", "claude")):
            with self.subTest(runtimes=runtimes):
                deltas = tuple(self._result_delta(runtime) for runtime in runtimes)
                failure = self._assert_synthetic_parity_failure(prompts, deltas)
                self.assertIn("multiple declared deltas", failure)
                self.assertIn("## Result", failure)
                for runtime in runtimes:
                    self.assertIn(runtime, failure)

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
        profile = support.load_runtime_profile(HOME, "collab-implementer", pi_dir=COLLAB_PI_DIR)
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
        for name in PARITY_NAMES + COLLAB_ROLE_NAMES:
            pi_dir = COLLAB_PI_DIR if name in COLLAB_ROLE_NAMES else ".pi/agent/agents"
            profile = support.load_runtime_profile(HOME, name, pi_dir=pi_dir)
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
        for name in COLLAB_ROLE_NAMES:
            profile = support.load_runtime_profile(HOME, name, pi_dir=COLLAB_PI_DIR)
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
