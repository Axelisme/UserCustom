from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
SECTION = HOME / ".codex/skills/dev-flow/scripts/section.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    # section.py resolves bare pointers under ~/; point it at this checkout's home/ tree
    # rather than whatever the invoking user has installed.
    return subprocess.run(
        ["python3", str(SECTION), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={**os.environ, "HOME": str(HOME)},
    )


class SkillPointerTest(unittest.TestCase):
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

    def test_several_pointers_are_read_in_order(self) -> None:
        lane_authority = HOME / ".codex/skills/dev-flow/references/lane-authority.md"
        result = run(
            f"{lane_authority}#creating-an-evidence-file",
            f"{lane_authority}#a-gate-you-cannot-close-honestly",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        first = result.stdout.index("#creating-an-evidence-file")
        second = result.stdout.index("#a-gate-you-cannot-close-honestly")
        self.assertLess(first, second)
        self.assertIn("## Creating an evidence file", result.stdout)
        self.assertIn("## A gate you cannot close honestly", result.stdout)

    def test_a_broken_pointer_is_skipped_and_the_rest_still_read(self) -> None:
        lane_authority = HOME / ".codex/skills/dev-flow/references/lane-authority.md"
        result = run(
            f"{lane_authority}#no-such-heading",
            "../dev-flow/references/no-such-doc.md#anything",
            f"{lane_authority}#a-gate-you-cannot-close-honestly",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("#no-such-heading", result.stderr)
        self.assertIn("no-such-doc.md", result.stderr)
        self.assertIn("## A gate you cannot close honestly", result.stdout)


if __name__ == "__main__":
    unittest.main()
