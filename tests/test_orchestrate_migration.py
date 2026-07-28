from __future__ import annotations

import argparse
import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CODEX_SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
PI_SKILL = ROOT / "home" / ".pi" / "agent" / "skills" / "orchestrate"
SCRIPT = CODEX_SKILL / "scripts" / "orchestrate.py"
BOUNDARY_REASON = re.compile(r"^v(\d+)-to-v(\d+)-[a-z0-9-]+$")


def load_release_module():
    sys.path.insert(0, str(CODEX_SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


class PinMigrationContractTests(unittest.TestCase):
    """Contract for the supported manifest range and pin migration Interface."""

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
        self.git(root, "config", "user.name", "Migration Test")
        self.git(root, "config", "user.email", "migration@example.test")
        self.git(root, "commit", "--allow-empty", "-qm", "base")

    def write_pin(self, root: Path, version: int) -> Path:
        pin = root / ".agent_state" / "orchestrate" / "version-pin.json"
        pin.parent.mkdir(parents=True, exist_ok=True)
        pin.write_text(
            json.dumps(
                {"pin_version": 1, "skill_version": version, "orchestrate_compat": version}
            ),
            encoding="utf-8",
        )
        return pin

    def shipped_skill_fixture(self, root: Path) -> tuple[Path, int]:
        home = root / "home"
        shutil.copytree(ROOT / "home", home)
        skill = home / ".codex" / "skills" / "orchestrate"
        version = self.release.skill_version(skill)
        (skill / "manifests" / f"{version}.json").write_text(
            json.dumps(self.release.build_manifest(skill, version)), encoding="utf-8"
        )
        return skill, version

    def setUp(self) -> None:
        self.release = load_release_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.init_repo(self.root)
        self.skill, self.version = self.shipped_skill_fixture(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def migrate(self) -> dict[str, Any]:
        return self.release.command_pin_migrate(
            argparse.Namespace(root=str(self.root), skill_dir=str(self.skill))
        )

    def migrate_cli(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--skill-dir",
                str(self.skill),
                "pin",
                "migrate",
                "--root",
                str(self.root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_manifest_inventory_is_the_contiguous_supported_range(self) -> None:
        expected = set(range(self.release.MIN_MIGRATABLE_VERSION, self.version + 1))
        for skill in (CODEX_SKILL, PI_SKILL):
            with self.subTest(skill=skill):
                observed = {
                    int(path.stem)
                    for path in (skill / "manifests").glob("*.json")
                    if path.stem.isdigit()
                }
                self.assertEqual(observed, expected)

    def test_pin_migrate_emits_each_selected_boundary_in_order(self) -> None:
        pin = self.write_pin(self.root, self.release.MIN_MIGRATABLE_VERSION)

        result = self.migrate()

        self.assertEqual(result["from_version"], self.release.MIN_MIGRATABLE_VERSION)
        self.assertEqual(result["to_version"], self.version)
        self.assertIsInstance(result["delta"], dict)
        self.assertIsNone(result["delta_note"])
        requirements = result["migration_requirements"] or []
        selected = [
            (target, requirement)
            for target, requirement in self.release.MIGRATION_BOUNDARIES
            if self.release.MIN_MIGRATABLE_VERSION < target <= self.version
        ]
        self.assertEqual(
            [item["reason"] for item in requirements],
            [item["reason"] for _, item in selected],
        )
        for (target, _), requirement in zip(selected, requirements, strict=True):
            reason = requirement["reason"]
            match = BOUNDARY_REASON.fullmatch(reason)
            self.assertIsNotNone(match, reason)
            assert match is not None
            self.assertEqual((int(match.group(1)), int(match.group(2))), (target - 1, target))
            self.assertIs(requirement["automatic_conversion"], False)
            for key, value in requirement.items():
                if key in {"reason", "automatic_conversion"}:
                    continue
                self.assertIs(value, True, f"{reason}: {key}")
        self.assertEqual(json.loads(pin.read_text())["skill_version"], self.version)

    def test_pin_just_below_current_selects_only_current_boundary(self) -> None:
        self.assertGreater(self.version, self.release.MIN_MIGRATABLE_VERSION)
        self.write_pin(self.root, self.version - 1)

        result = self.migrate()

        requirements = result["migration_requirements"] or []
        expected = [
            requirement["reason"]
            for target, requirement in self.release.MIGRATION_BOUNDARIES
            if self.version - 1 < target <= self.version
        ]
        self.assertEqual([item["reason"] for item in requirements], expected)

    def test_pin_below_floor_is_rejected_without_writing(self) -> None:
        pin = self.write_pin(self.root, self.release.MIN_MIGRATABLE_VERSION - 1)
        before = pin.read_bytes()

        result = self.migrate_cli()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        error = json.loads(result.stderr)
        self.assertEqual(error["error"]["type"], "orchestrate")
        self.assertIn(
            f"v{self.release.MIN_MIGRATABLE_VERSION} and newer",
            error["error"]["message"],
        )
        self.assertEqual(pin.read_bytes(), before)

    def test_pin_ahead_of_current_is_rejected_without_writing(self) -> None:
        pin = self.write_pin(self.root, self.version + 1)
        before = pin.read_bytes()

        with self.assertRaisesRegex(Exception, "cannot migrate down"):
            self.migrate()

        self.assertEqual(pin.read_bytes(), before)

    def test_same_version_is_a_no_op(self) -> None:
        self.write_pin(self.root, self.version)

        self.assertEqual(
            self.migrate(),
            {
                "ok": True,
                "operation": "pin-migrate",
                "recovered": "already-current",
                "pinned_version": self.version,
            },
        )

    def test_missing_retained_manifest_fails_closed(self) -> None:
        old = self.release.MIN_MIGRATABLE_VERSION
        (self.skill / "manifests" / f"{old}.json").unlink()
        pin = self.write_pin(self.root, old)
        before = pin.read_bytes()

        with self.assertRaisesRegex(Exception, "release manifest not found"):
            self.migrate()

        self.assertEqual(pin.read_bytes(), before)

    def test_missing_intermediate_manifest_fails_closed(self) -> None:
        old = self.release.MIN_MIGRATABLE_VERSION
        intermediate = old + 1
        self.assertLess(intermediate, self.version)
        (self.skill / "manifests" / f"{intermediate}.json").unlink()
        pin = self.write_pin(self.root, old)
        before = pin.read_bytes()

        with self.assertRaisesRegex(Exception, "release manifest not found"):
            self.migrate()

        self.assertEqual(pin.read_bytes(), before)

    def test_pin_set_does_not_offer_migrate_below_the_floor(self) -> None:
        self.write_pin(self.root, self.release.MIN_MIGRATABLE_VERSION - 1)

        with self.assertRaisesRegex(Exception, "below the supported migration floor"):
            self.release.command_pin_set(
                argparse.Namespace(root=str(self.root), skill_dir=str(self.skill))
            )

    def test_pin_help_retains_migrate(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "pin", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("migrate", result.stdout)


if __name__ == "__main__":
    unittest.main()
