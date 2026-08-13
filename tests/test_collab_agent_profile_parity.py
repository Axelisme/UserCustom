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
)


class CollabAgentProfileParityTests(unittest.TestCase):
    def test_three_copies_are_identical_in_body(self) -> None:
        for name in PROFILE_NAMES:
            with self.subTest(profile=name):
                profile = support.load_runtime_profile(HOME, name)
                support.assert_prompt_parity(self, profile)


if __name__ == "__main__":
    unittest.main()
