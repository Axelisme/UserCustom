from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MDSEC = ROOT / "home/.local/bin/mdsec"
SKILL = "# Flow\n\n## Resume\n\nresume body\n\n## Gates\n\ngates body\n\n## Land\n\nland body\n\n## Close\n\nclose body\n"


class SkillPointerTest(unittest.TestCase):
    def setUp(self) -> None:
        # mdsec resolves bare pointers under ~/, so each test gets a home with its own skill tree:
        # one skill of its own and one bridged in through a symlink, as upstream skills are.
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        skills = self.home / ".codex/skills"
        (skills / "flow").mkdir(parents=True)
        self.skill = skills / "flow/SKILL.md"
        self.skill.write_text(SKILL)
        bridged = self.home / "vendor/bridged"
        bridged.mkdir(parents=True)
        (bridged / "SKILL.md").write_text("# Bridged\n\n## Use\n")
        (skills / "bridged").symlink_to(bridged, target_is_directory=True)

    def run_mdsec(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(MDSEC), *args],
            capture_output=True,
            text=True,
            cwd=self.home,
            env={**os.environ, "HOME": str(self.home)},
        )

    def test_a_stale_anchor_fails_loudly_with_the_closest_and_real_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp, "doc.md")
            doc.write_text("# Doc\n\n## Evidence file\n\nbody\n\n## Other rule\n")
            result = self.run_mdsec(f"{doc}#evidence-fil")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Did you mean '#evidence-file'?", result.stderr)
        self.assertIn("#other-rule", result.stderr)

    def test_check_catches_a_broken_pointer_of_every_kind_it_claims(self) -> None:
        # The corpus being green proves nothing about detection, so plant one break of each kind.
        pointers = {
            "link": "[x](missing-doc.md)",
            "link anchor": "[x](real.md#no-such-heading)",
            "bare rooted": "`~/.codex/skills/flow/no-such-doc.md`",
            "bare anchor": "`real.md#no-such-heading`",
        }
        for kind, pointer in pointers.items():
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "real.md").write_text("# Real\n")
                (root / "doc.md").write_text(f"See {pointer} for details.\n")
                result = self.run_mdsec("--check", str(root))
                self.assertEqual(result.returncode, 1, f"{kind} went undetected: {result.stdout}")

    def test_check_leaves_runtime_artifact_prose_alone(self) -> None:
        # `INDEX.md` and friends name a file a ticket creates, not a document to open.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc.md").write_text(
                "Repair `INDEX.md`, then write `research/skill-feedback.md`.\n"
            )
            result = self.run_mdsec("--check", str(root))
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_pointer_into_a_bridged_skill_resolves(self) -> None:
        # Upstream skills are symlinks into vendor/; a walk that skips them misses most of the fleet.
        result = self.run_mdsec("../bridged/SKILL.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("#", result.stdout)

    def test_check_reports_the_symlinked_directories_it_skips(self) -> None:
        # Vendored skills are symlinks whose pointers belong upstream; skipping them must be visible.
        with tempfile.TemporaryDirectory() as tmp:
            vendor = Path(tmp, "vendor", "skill")
            vendor.mkdir(parents=True)
            (vendor / "doc.md").write_text("See [x](missing-doc.md) for details.\n")
            root = Path(tmp, "skills")
            root.mkdir()
            (root / "bridged").symlink_to(vendor, target_is_directory=True)
            (root / "own.md").write_text("Nothing to resolve.\n")
            result = self.run_mdsec("--check", str(root))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("checked 1 files", result.stdout)
            self.assertIn("skipped 1 symlinked directory", result.stdout)

    def test_a_pointer_is_read_at_its_section(self) -> None:
        result = self.run_mdsec("../flow/SKILL.md#land")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Land", result.stdout)
        self.assertNotIn("## Close", result.stdout)

    def test_several_pointers_are_read_in_order(self) -> None:
        skill = self.skill
        result = self.run_mdsec(f"{skill}#resume", f"{skill}#close")
        self.assertEqual(result.returncode, 0, result.stderr)
        first = result.stdout.index("#resume")
        second = result.stdout.index("#close")
        self.assertLess(first, second)
        self.assertIn("## Resume", result.stdout)
        self.assertIn("## Close", result.stdout)

    def test_a_broken_pointer_is_skipped_and_the_rest_still_read(self) -> None:
        skill = self.skill
        result = self.run_mdsec(
            f"{skill}#no-such-heading",
            "../flow/no-such-doc.md#anything",
            f"{skill}#gates",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("#no-such-heading", result.stderr)
        self.assertIn("no-such-doc.md", result.stderr)
        self.assertIn("## Gates", result.stdout)


if __name__ == "__main__":
    unittest.main()
