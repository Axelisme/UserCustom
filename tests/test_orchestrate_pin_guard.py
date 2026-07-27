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


ROOT = Path(__file__).resolve().parents[1]
CODEX_SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
PI_SKILL = ROOT / "home" / ".pi" / "agent" / "skills" / "orchestrate"
SCRIPT = CODEX_SKILL / "scripts" / "orchestrate.py"
BOUNDARY_REASON = re.compile(r"^v(\d+)-to-v(\d+)-[a-z0-9-]+$")
VERSION_LEAK = re.compile(r"\bv1[0-9]{2}\b")


def load_release_module():
    """Import the shipped release module the way the installed CLI does."""
    sys.path.insert(0, str(CODEX_SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


def load_cli_module():
    """Import the shipped CLI module the way the installed entrypoint does."""
    sys.path.insert(0, str(CODEX_SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.cli")
    finally:
        sys.path.pop(0)


def all_command_paths(parser: argparse.ArgumentParser) -> list[list[str]]:
    """Every concrete command path this parser accepts, including the empty (top-level) one.

    Walks real ``argparse._SubParsersAction`` structure rather than scraping
    rendered ``--help`` text, so an unrelated ``{codex,claude,pi}`` choice list
    on an ordinary flag (``diff --runtime``) can never be mistaken for a
    subcommand set.
    """
    paths: list[list[str]] = [[]]
    for action in parser._actions:  # noqa: SLF001 - introspecting our own shipped parser
        if isinstance(action, argparse._SubParsersAction):
            for name, subparser in action.choices.items():
                for tail in all_command_paths(subparser):
                    paths.append([name, *tail])
    return paths


class PinMigrateResidueGuardTests(unittest.TestCase):
    """``pin migrate`` must refuse to advance a task repo that still carries
    pre-lane-model residue: a ``wave/`` branch, a ``refs/orchestrate/*`` ref, or a
    leftover managed worktree directory under ``.agent_state/worktrees``.

    Advancing the pin past any of these silently would leave the new model
    reading Git state a retired workflow wrote, and reading it wrong: the guard
    must fail closed, name exactly what is left, and never move the pin.
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
        self.git(root, "config", "user.name", "Guard Test")
        self.git(root, "config", "user.email", "guard@example.test")
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

    def shipped_skill_fixture(self, root: Path, release) -> tuple[Path, int]:
        # A copied, installed-package-shaped fixture: real migrations run
        # against a shipped copy, never the live checkout.
        home = root / "home"
        shutil.copytree(ROOT / "home", home)
        skill = home / ".codex" / "skills" / "orchestrate"
        return skill, release.skill_version(skill)

    def migrate(self, root: Path, skill: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--skill-dir", str(skill), "pin", "migrate", "--root", str(root)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def setUp(self) -> None:
        self.release = load_release_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.init_repo(self.root)
        self.skill, self.version = self.shipped_skill_fixture(self.root, self.release)
        # Pinned one version behind shipped, so migrate has a boundary to cross
        # and the residue guard actually has something to gate.
        self.write_pin(self.root, self.version - 1)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_wave_branch_blocks_migration_and_is_named_in_the_error(self) -> None:
        self.git(self.root, "branch", "wave/some-task/lane-a")

        result = self.migrate(self.root, self.skill)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("wave/some-task/lane-a", result.stderr)
        pin = json.loads(
            (self.root / ".agent_state" / "orchestrate" / "version-pin.json").read_text()
        )
        self.assertEqual(pin["skill_version"], self.version - 1)

    def test_an_orchestrate_ref_blocks_migration_and_is_named_in_the_error(self) -> None:
        self.git(self.root, "update-ref", "refs/orchestrate/some-task/candidate", "HEAD")

        result = self.migrate(self.root, self.skill)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refs/orchestrate/some-task/candidate", result.stderr)

    def test_a_leftover_managed_worktree_directory_blocks_migration(self) -> None:
        leftover = self.root / ".agent_state" / "worktrees" / "some-task-lane-a"
        leftover.mkdir(parents=True)

        result = self.migrate(self.root, self.skill)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(leftover), result.stderr)

    def test_multiple_residue_categories_are_all_named_at_once(self) -> None:
        self.git(self.root, "branch", "wave/some-task/lane-a")
        self.git(self.root, "update-ref", "refs/orchestrate/some-task/integration/base", "HEAD")
        leftover = self.root / ".agent_state" / "worktrees" / "some-task-lane-a"
        leftover.mkdir(parents=True)

        result = self.migrate(self.root, self.skill)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wave/some-task/lane-a", result.stderr)
        self.assertIn("refs/orchestrate/some-task/integration/base", result.stderr)
        self.assertIn(str(leftover), result.stderr)

    def test_a_clean_repo_migrates_and_receives_exactly_the_final_boundary(self) -> None:
        result = self.migrate(self.root, self.skill)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["to_version"], self.version)
        pin = json.loads(
            (self.root / ".agent_state" / "orchestrate" / "version-pin.json").read_text()
        )
        self.assertEqual(pin["skill_version"], self.version)

        requirements = payload["migration_requirements"]
        self.assertEqual(len(requirements), 1, requirements)
        reason = requirements[0]["reason"]
        match = BOUNDARY_REASON.match(reason)
        self.assertIsNotNone(match, reason)
        assert match is not None
        self.assertEqual(int(match.group(1)), self.version - 1)
        self.assertEqual(int(match.group(2)), self.version)
        self.assertIs(requirements[0]["automatic_conversion"], False)


class ManifestParityAndHistoryTests(unittest.TestCase):
    """The shipped manifest must match byte-for-byte across the Codex and Pi
    runtimes, and a release must never rewrite a manifest it did not just cut.
    """

    def setUp(self) -> None:
        self.release = load_release_module()

    def test_shipped_manifest_is_byte_identical_across_codex_and_pi(self) -> None:
        version = self.release.skill_version(CODEX_SKILL)
        codex_manifest = CODEX_SKILL / "manifests" / f"{version}.json"
        pi_manifest = PI_SKILL / "manifests" / f"{version}.json"
        self.assertTrue(codex_manifest.is_file(), codex_manifest)
        self.assertTrue(pi_manifest.is_file(), pi_manifest)
        self.assertEqual(codex_manifest.read_bytes(), pi_manifest.read_bytes())

    def test_release_never_rewrites_an_earlier_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "home" / ".codex" / "skills" / "orchestrate"
            skill.parent.mkdir(parents=True)
            shutil.copytree(CODEX_SKILL, skill)
            historical = {
                path.name: path.read_bytes()
                for path in (skill / "manifests").glob("*.json")
                if path.stem.isdigit()
            }
            self.assertTrue(historical)

            result = self.release.command_release(
                argparse.Namespace(skill_dir=str(skill), version=None)
            )
            self.assertTrue(result["ok"], result)

            for name, before in historical.items():
                after = (skill / "manifests" / name).read_bytes()
                self.assertEqual(before, after, f"release modified historical manifest {name}")


class CliHelpHasNoVersionResidueTests(unittest.TestCase):
    """CLI help text must never leak a specific skill-release version number,
    at the top level or in any subcommand or sub-subcommand.
    """

    def run_help(self, *args: str) -> str:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--help"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_top_level_and_every_subcommand_help_is_free_of_version_residue(self) -> None:
        cli = load_cli_module()
        for path in all_command_paths(cli.build_parser()):
            with self.subTest(command=path or ["--help"]):
                text = self.run_help(*path)
                self.assertNotRegex(text, VERSION_LEAK)


if __name__ == "__main__":
    unittest.main()
