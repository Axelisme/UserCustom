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

# After SL04, Pi collab-implementer/acceptor carry the workflow-scoped Acceptance appendix contract
# while Claude remains unchanged per A7 (no general ledger, no runtime param, no Claude change).
# Parity is therefore expected only for the profiles not owning that contract.
PARITY_NAMES = (
    "contract-reviewer",
    "repo-investigator",
    "mechanical-implementer",
)


class CollabAgentProfileParityTests(unittest.TestCase):
    def test_allowed_copies_are_identical_in_body(self) -> None:
        for name in PARITY_NAMES:
            with self.subTest(profile=name):
                profile = support.load_runtime_profile(HOME, name)
                support.assert_prompt_parity(self, profile)

    def test_sl04_appendix_ownership_diverges_pi_from_claude(self) -> None:
        # SL04 intentionally diverges Pi appendix guidance from Claude per A7; parity is not expected.
        for name in ("collab-implementer", "collab-acceptor"):
            with self.subTest(profile=name):
                profile = support.load_runtime_profile(HOME, name)
                pi_prompt = profile.prompt
                claude_prompt = support.markdown_prompt(profile.claude_path)
                self.assertNotEqual(pi_prompt, claude_prompt)


if __name__ == "__main__":
    unittest.main()
