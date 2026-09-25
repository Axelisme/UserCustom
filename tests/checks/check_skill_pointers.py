"""Every anchored pointer in the workflow documents resolves to a real section."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "home"
SECTION = HOME / ".codex/skills/dev-flow/scripts/section.py"

# An anchored pointer addresses one section, so a heading is an address: renaming one silently
# breaks every pointer into it. These are the trees whose pointers dev-flow principle 17 governs.
POINTER_ROOTS = (
    HOME / ".codex/skills/dev-flow",
    HOME / ".codex/skills/collab",
    HOME / ".claude/agents",
    HOME / ".codex/agents",
    HOME / ".pi/agent/herdr-subagents/profiles",
)


class SkillPointerCheck(unittest.TestCase):
    def test_every_anchored_pointer_resolves(self) -> None:
        # Bare pointers resolve under ~/; use this checkout's home/ tree, not the installed one.
        result = subprocess.run(
            ["python3", str(SECTION), "--check", *[str(p) for p in POINTER_ROOTS]],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={**os.environ, "HOME": str(HOME)},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
