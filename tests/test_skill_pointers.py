from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
SECTION = HOME / ".codex/skills/dev-flow/scripts/section.py"

# An anchored pointer addresses one section, so a heading is an address: renaming one silently
# breaks every pointer into it. These are the trees whose pointers dev-flow principle 17 governs.
POINTER_ROOTS = (
    HOME / ".codex/skills/dev-flow",
    HOME / ".codex/skills/collab",
    HOME / ".claude/agents",
    HOME / ".codex/agents",
    HOME / ".pi/agent/agents",
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SECTION), *args], capture_output=True, text=True, cwd=ROOT
    )


class SkillPointerTest(unittest.TestCase):
    def test_every_anchored_pointer_resolves(self) -> None:
        result = run("--check", *[str(p) for p in POINTER_ROOTS])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_stale_anchor_fails_loudly_with_the_real_anchors(self) -> None:
        lane_authority = HOME / ".codex/skills/dev-flow/references/lane-authority.md"
        result = run(f"{lane_authority}#the-closing-swep")
        self.assertEqual(result.returncode, 1)
        self.assertIn("#the-closing-sweep", result.stderr)

    def test_a_pointer_is_read_at_its_section(self) -> None:
        result = run("../dev-flow/references/lane-authority.md#the-closing-sweep")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## The closing sweep", result.stdout)
        self.assertNotIn("## Creating an evidence file", result.stdout)

    def test_both_collab_profiles_carry_the_orchestrators_two_anchors(self) -> None:
        profiles = [
            d / f"collab-{role}.md"
            for d in (HOME / ".claude/agents", HOME / ".pi/agent/agents")
            for role in ("implementer", "acceptor")
        ] + [
            HOME / f".codex/agents/collab-{role}.toml"
            for role in ("implementer", "acceptor")
        ]
        for profile in profiles:
            with self.subTest(profile=profile.name):
                anchors = run("--list", str(profile)).stdout
                self.assertIn("#dispatch-contract", anchors)
                self.assertIn("#result\n", anchors)


if __name__ == "__main__":
    unittest.main()
