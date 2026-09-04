from __future__ import annotations

import subprocess
import tempfile
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
    HOME / ".pi/agent/herdr-subagents/profiles",
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
        result = run(f"{lane_authority}#creating-an-evidence-fil")
        self.assertEqual(result.returncode, 1)
        self.assertIn("#creating-an-evidence-file", result.stderr)

    def test_check_catches_a_broken_pointer_of_every_kind_it_claims(self) -> None:
        # The corpus being green proves nothing about detection, so plant one break of each kind.
        pointers = {
            "link": "[x](missing-doc.md)",
            "link anchor": "[x](real.md#no-such-heading)",
            "bare rooted": "`~/.codex/skills/dev-flow/references/no-such-doc.md`",
            "bare anchor": "`real.md#no-such-heading`",
        }
        for kind, pointer in pointers.items():
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "real.md").write_text("# Real\n")
                (root / "doc.md").write_text(f"See {pointer} for details.\n")
                result = run("--check", str(root))
                self.assertEqual(result.returncode, 1, f"{kind} went undetected: {result.stdout}")

    def test_check_leaves_runtime_artifact_prose_alone(self) -> None:
        # `INDEX.md` and friends name a file a ticket creates, not a document to open.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc.md").write_text(
                "Repair `INDEX.md`, then write `research/skill-feedback.md`.\n"
            )
            result = run("--check", str(root))
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_pointer_is_read_at_its_section(self) -> None:
        result = run("../dev-flow/references/lane-authority.md#a-gate-you-cannot-close-honestly")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## A gate you cannot close honestly", result.stdout)
        self.assertNotIn("## Creating an evidence file", result.stdout)

    def test_both_collab_profiles_carry_the_orchestrators_two_anchors(self) -> None:
        profiles = [
            d / f"collab-{role}.md"
            for d in (HOME / ".claude/agents", HOME / ".pi/agent/herdr-subagents/profiles")
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
