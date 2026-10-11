"""Every anchored pointer in the workflow documents resolves to a real section."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests import _support as support

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "home"
MDSEC = support.load_script(HOME / ".local/bin/mdsec")

# An anchored pointer addresses one section, so a heading is an address: renaming one silently
# breaks every pointer into it. These are the trees whose pointers must keep resolving.
POINTER_ROOTS = (
    HOME / ".codex/skills/task-flow",
    HOME / ".codex/skills/advisor",
    HOME / ".claude/agents",
    HOME / ".codex/agents",
    HOME / ".pi/agent/herdr-subagents/profiles",
)


class SkillPointerCheck(unittest.TestCase):
    def test_every_anchored_pointer_resolves(self) -> None:
        # Bare pointers resolve under ~/; use this checkout's home/ tree, not the installed one.
        result = support.run_main(
            MDSEC.main, ["--check", *[str(p) for p in POINTER_ROOTS]], cwd=ROOT, home=HOME
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
