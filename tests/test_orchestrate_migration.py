from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = SKILL / "scripts" / "orchestrate.py"
BOUNDARY_REASON = re.compile(r"^v(\d+)-to-v(\d+)-[a-z0-9-]+$")


def load_release_module():
    """Import the shipped release module the way the installed CLI does."""
    sys.path.insert(0, str(SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


class PinMigrationContractTests(unittest.TestCase):
    """Contract for pin migration across every shipped version boundary.

    The boundaries themselves are read out of the shipped release module, so a new
    release adds a boundary without editing this file.  What is asserted is the
    shape every boundary must keep, not the wording of any one of them.
    """

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def init_repo(self, root: Path) -> None:
        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "config", "user.name", "Oracle Test")
        self.git(root, "config", "user.email", "oracle@example.test")
        self.git(root, "commit", "--allow-empty", "-qm", "base")

    def write_pin(self, root: Path, version: int) -> Path:
        pin = root / ".agent_state" / "orchestrate" / "version-pin.json"
        pin.parent.mkdir(parents=True, exist_ok=True)
        pin.write_text(
            json.dumps(
                {
                    "pin_version": 1,
                    "skill_version": version,
                    "orchestrate_compat": version,
                }
            ),
            encoding="utf-8",
        )
        return pin

    def shipped_skill_fixture(self, root: Path, release, drop_manifest: int) -> tuple[Path, int]:
        # Copy the shipped package as an installed-package-shaped fixture.  Dropping
        # the pinned version's manifest exercises the documented manual migration
        # path rather than a synthetic private helper.
        home = root / "home"
        shutil.copytree(ROOT / "home", home)
        skill = home / ".codex" / "skills" / "orchestrate"
        version = release.skill_version(skill)
        (skill / "manifests" / f"{drop_manifest}.json").unlink()
        manifest = release.build_manifest(skill, version)
        (skill / "manifests" / f"{version}.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return skill, version

    def oldest_shipped_version(self) -> int:
        versions = [
            int(path.stem)
            for path in (SKILL / "manifests").glob("*.json")
            if path.stem.isdigit()
        ]
        self.assertTrue(versions)
        return min(versions)

    def boundary_targets(self, requirements: list[dict[str, object]]) -> list[int]:
        """Assert the shape every version boundary must keep, and return its targets.

        A manifest-unavailable block is a reread instruction, not a version
        boundary, so it is reported separately and skipped here.
        """
        targets: list[int] = []
        for block in requirements:
            reason = str(block["reason"])
            if reason == "source-manifest-unavailable":
                continue
            match = BOUNDARY_REASON.match(reason)
            self.assertIsNotNone(match, f"malformed migration reason: {reason}")
            assert match is not None
            source, target = int(match.group(1)), int(match.group(2))
            self.assertLess(source, target, reason)
            self.assertIs(
                block["automatic_conversion"],
                False,
                f"{reason} must never claim automatic conversion",
            )
            for key, value in block.items():
                if key in {"reason", "automatic_conversion"}:
                    continue
                self.assertIs(value, True, f"{reason}: {key} must be a stated requirement")
            targets.append(target)
        return targets

    def test_pin_migrate_emits_every_crossed_boundary_and_preserves_legacy_state(self) -> None:
        release = load_release_module()
        oldest = self.oldest_shipped_version()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.init_repo(root)
            skill, version = self.shipped_skill_fixture(root, release, drop_manifest=oldest)

            # Legacy evidence and state are read-only migration input.  The
            # migration must not attempt to convert or delete either asset.
            evidence = root / ".agent_state" / "legacy" / "findings.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text('{"legacy": true}\n', encoding="utf-8")
            legacy_state = root / ".agent_state" / "legacy-lanes.json"
            legacy_state.write_text('{"lane": "old"}\n', encoding="utf-8")
            pin = self.write_pin(root, oldest)

            result = release.command_pin_migrate(
                argparse.Namespace(root=str(root), skill_dir=str(skill))
            )

            self.assertEqual(
                set(result),
                {
                    "ok",
                    "operation",
                    "from_version",
                    "to_version",
                    "delta",
                    "migration_requirements",
                    "delta_note",
                },
            )
            self.assertEqual(result["operation"], "pin-migrate")
            self.assertEqual(result["from_version"], oldest)
            self.assertEqual(result["to_version"], version)
            self.assertIsNone(result["delta"])

            targets = self.boundary_targets(result["migration_requirements"])
            self.assertTrue(targets, "migrating from the oldest pin must cross a boundary")
            self.assertEqual(targets, sorted(targets), "boundaries must be emitted in order")
            self.assertEqual(len(targets), len(set(targets)), "duplicate boundary target")
            self.assertGreater(min(targets), oldest)
            self.assertLessEqual(max(targets), version)

            self.assertEqual(
                json.loads(pin.read_text(encoding="utf-8"))["skill_version"], version
            )
            self.assertEqual(evidence.read_text(encoding="utf-8"), '{"legacy": true}\n')
            self.assertEqual(legacy_state.read_text(encoding="utf-8"), '{"lane": "old"}\n')

    def test_a_pin_just_below_the_newest_boundary_receives_only_that_boundary(self) -> None:
        release = load_release_module()
        oldest = self.oldest_shipped_version()
        with tempfile.TemporaryDirectory() as package, tempfile.TemporaryDirectory() as second:
            root = Path(package)
            self.init_repo(root)
            skill, _ = self.shipped_skill_fixture(root, release, drop_manifest=oldest)
            self.write_pin(root, oldest)
            everything = release.command_pin_migrate(
                argparse.Namespace(root=str(root), skill_dir=str(skill))
            )["migration_requirements"]
            newest = max(self.boundary_targets(everything))

            later = Path(second)
            self.init_repo(later)
            self.write_pin(later, newest - 1)

            result = release.command_pin_migrate(
                argparse.Namespace(root=str(later), skill_dir=str(skill))
            )

            self.assertEqual(self.boundary_targets(result["migration_requirements"]), [newest])

    def test_retained_administration_stays_on_the_root_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("release", "manifest", "doctor", "pin"):
            self.assertIn(command, result.stdout)
        pin_help = subprocess.run(
            [sys.executable, str(SCRIPT), "pin", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(pin_help.returncode, 0, pin_help.stderr)
        self.assertIn("migrate", pin_help.stdout)

    def test_pin_migrate_same_version_keeps_existing_compatibility_response(self) -> None:
        release = load_release_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.init_repo(root)
            skill, version = self.shipped_skill_fixture(
                root, release, drop_manifest=self.oldest_shipped_version()
            )
            self.write_pin(root, version)

            result = release.command_pin_migrate(
                argparse.Namespace(root=str(root), skill_dir=str(skill))
            )
            self.assertEqual(
                result,
                {
                    "ok": True,
                    "operation": "pin-migrate",
                    "recovered": "already-current",
                    "pinned_version": version,
                },
            )


if __name__ == "__main__":
    unittest.main()
