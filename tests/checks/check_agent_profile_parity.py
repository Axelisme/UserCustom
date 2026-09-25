from __future__ import annotations

import unittest
from pathlib import Path

from tests import _profile_test_support as support

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "home"

PARITY_NAMES = (
    "contract-reviewer",
    "repo-investigator",
)


class AgentProfileParityTests(unittest.TestCase):
    def test_remaining_runtime_copies_are_identical_in_body(self) -> None:
        for name in PARITY_NAMES:
            with self.subTest(profile=name):
                profile = support.load_runtime_profile(HOME, name)
                support.assert_prompt_parity(self, profile)


if __name__ == "__main__":
    unittest.main()
