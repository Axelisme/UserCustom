from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
PI_SKILL = ROOT / "home" / ".pi" / "agent" / "skills" / "orchestrate"
SCRIPT = CODEX_SKILL / "scripts" / "orchestrate.py"


def load_release_module():
    sys.path.insert(0, str(CODEX_SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


class PinMigrateActiveTaskGuardTests(unittest.TestCase):
    """Pin migration is read-only while a current task remains active."""

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def setUp(self) -> None:
        self.release = load_release_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git(self.root, "init", "-q", "-b", "main")
        self.git(self.root, "config", "user.name", "Guard Test")
        self.git(self.root, "config", "user.email", "guard@example.test")
        self.git(self.root, "commit", "--allow-empty", "-qm", "base")
        self.home = self.root / "home"
        shutil.copytree(ROOT / "home", self.home)
        self.skill = self.home / ".codex" / "skills" / "orchestrate"
        self.version = self.release.skill_version(self.skill)
        (self.skill / "manifests" / f"{self.version}.json").write_text(
            json.dumps(self.release.build_manifest(self.skill, self.version)), encoding="utf-8"
        )
        self.pin = self.root / ".agent_state" / "orchestrate" / "version-pin.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_pin(self, version: int) -> None:
        self.pin.parent.mkdir(parents=True, exist_ok=True)
        self.pin.write_text(
            json.dumps(
                {
                    "pin_version": 1,
                    "skill_version": version,
                    "orchestrate_compat": version,
                }
            ),
            encoding="utf-8",
        )

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--skill-dir", str(self.skill), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def migrate(self) -> subprocess.CompletedProcess[str]:
        return self.cli("pin", "migrate", "--root", str(self.root))

    def test_current_task_state_blocks_migration_without_mutation(self) -> None:
        self.write_pin(self.version)
        created = self.cli(
            "integration",
            "create",
            "--root",
            str(self.root),
            "--task-id",
            "active-task",
            "--base",
            self.git(self.root, "rev-parse", "HEAD"),
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        payload = json.loads(created.stdout)
        integration_worktree = Path(payload["worktree"])
        acceptance_worktree = Path(payload["acceptance_worktree"])

        self.write_pin(self.release.MIN_MIGRATABLE_VERSION)
        pin_before = self.pin.read_bytes()
        branches_before = self.git(
            self.root,
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads/wave/",
        ).splitlines()
        refs_before = self.git(
            self.root,
            "for-each-ref",
            "--format=%(refname)",
            "refs/orchestrate/",
        ).splitlines()

        result = self.migrate()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("active orchestrate task state", result.stderr)
        for name in [*branches_before, *refs_before]:
            self.assertIn(name, result.stderr)
        self.assertIn(str(integration_worktree), result.stderr)
        self.assertIn(str(acceptance_worktree), result.stderr)
        self.assertEqual(self.pin.read_bytes(), pin_before)
        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/heads/wave/",
            ).splitlines(),
            branches_before,
        )
        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname)",
                "refs/orchestrate/",
            ).splitlines(),
            refs_before,
        )
        self.assertTrue(integration_worktree.is_dir())
        self.assertTrue(acceptance_worktree.is_dir())
        self.assertEqual(self.git(integration_worktree, "status", "--porcelain"), "")
        self.assertEqual(self.git(acceptance_worktree, "status", "--porcelain"), "")

    def test_clean_repo_migrates_without_creating_task_state(self) -> None:
        self.write_pin(self.release.MIN_MIGRATABLE_VERSION)

        result = self.migrate()

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["to_version"], self.version)
        self.assertIsNone(payload["delta_note"])
        self.assertEqual(json.loads(self.pin.read_text())["skill_version"], self.version)
        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/heads/wave/",
            ),
            "",
        )
        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname)",
                "refs/orchestrate/",
            ),
            "",
        )


class CurrentManifestParityTests(unittest.TestCase):
    def test_current_manifest_is_byte_identical_across_codex_and_pi(self) -> None:
        release = load_release_module()
        version = release.skill_version(CODEX_SKILL)
        codex_manifest = CODEX_SKILL / "manifests" / f"{version}.json"
        pi_manifest = PI_SKILL / "manifests" / f"{version}.json"
        self.assertEqual(codex_manifest.read_bytes(), pi_manifest.read_bytes())


if __name__ == "__main__":
    unittest.main()
