from __future__ import annotations

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
HOME = ROOT / "home"
CODEX_SKILL = HOME / ".codex" / "skills" / "orchestrate"
PI_SKILL = HOME / ".pi" / "agent" / "skills" / "orchestrate"
CODEX_SCRIPT = CODEX_SKILL / "scripts" / "orchestrate.py"
VERSION_MATCH = re.search(
    r"(?m)^skill_version: (\d+)$",
    (CODEX_SKILL / "SKILL.md").read_text(encoding="utf-8"),
)
if VERSION_MATCH is None:
    raise RuntimeError("orchestrate SKILL.md has no skill_version")
SHIPPED_VERSION = int(VERSION_MATCH.group(1))


def load_release_module():
    sys.path.insert(0, str(CODEX_SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


class ReleasedPackageTests(unittest.TestCase):
    """Black-box contract for the shipped package and its root CLI.

    The shipped version is read from SKILL.md, so a release does not require
    editing this file.
    """

    retained_commands = {
        "admission",
        "lane",
        "integration",
        "profile",
        "doctor",
        "diff",
        "pin",
        "release",
    }
    removed_commands = {
        "worktree",
        "contract",
        "compose-base",
        "review",
        "land",
        "collect",
        "cleanup",
        "slice",
        "findings",
        "feedback",
        "revalidate",
        "reconcile",
        "wave",
    }

    @staticmethod
    def run_cli(*args: str, skill_dir: Path = CODEX_SKILL) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CODEX_SCRIPT), "--skill-dir", str(skill_dir), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def help_commands(text: str) -> set[str]:
        match = re.search(r"\{([^{}]+)\}", text)
        if match is None:
            raise AssertionError(f"root help has no command set:\n{text}")
        return set(match.group(1).split(","))

    def test_root_help_is_only_the_workflow_and_retained_administration(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.help_commands(result.stdout), self.retained_commands)
        for command in self.removed_commands | {"review", "lock", "ledger"}:
            self.assertNotIn(command, result.stdout)

    def test_historical_manifests_and_pin_migration_remain_available(self) -> None:
        for skill in (CODEX_SKILL, PI_SKILL):
            with self.subTest(skill=skill):
                historical = sorted(
                    path for path in (skill / "manifests").glob("*.json")
                    if path.stem.isdigit() and int(path.stem) < SHIPPED_VERSION
                )
                self.assertTrue(historical, skill)
                for path in historical:
                    version = int(path.stem)
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(manifest["skill_version"], version)
                    self.assertEqual(manifest["orchestrate_compat"], version)
        result = self.run_cli("pin", "migrate", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("lock", result.stdout.lower())
        self.assertNotIn("ledger", result.stdout.lower())

    def test_every_runtime_ships_a_manifest_for_its_declared_version(self) -> None:
        # Metadata only.  Whether the shipped bytes still match the manifest
        # checksums is the doctor's question, not a test's: asserting it here
        # would turn every edit to a shipped document into a test failure.
        for skill in (CODEX_SKILL, PI_SKILL):
            with self.subTest(skill=skill):
                skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertRegex(skill_text, rf"(?m)^skill_version: {SHIPPED_VERSION}$")
                manifest_path = skill / "manifests" / f"{SHIPPED_VERSION}.json"
                self.assertTrue(manifest_path.is_file(), f"missing manifest: {manifest_path}")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["skill_version"], SHIPPED_VERSION)
                self.assertEqual(manifest["orchestrate_compat"], SHIPPED_VERSION)

    def test_pin_migrate_remains_a_retained_administration_command(self) -> None:
        result = self.run_cli("pin", "migrate", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--root", result.stdout)


class RuntimeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.release = load_release_module()

    def test_source_home_resolves_all_runtime_layouts(self) -> None:
        self.assertEqual(self.release.source_home(CODEX_SKILL), HOME.resolve())
        self.assertEqual(self.release.source_home(PI_SKILL), HOME.resolve())
        with self.assertRaisesRegex(Exception, "cannot locate home root"):
            self.release.source_home(Path("/tmp/unsupported/skills/orchestrate"))

    def test_manifest_inventory_covers_every_runtime_and_profile(self) -> None:
        for skill in (CODEX_SKILL, PI_SKILL):
            manifest = self.release.build_manifest(skill, SHIPPED_VERSION)
            self.assertTrue(
                {"runtime-codex.md", "runtime-claude.md", "runtime-pi.md"}
                <= set(manifest["documents"])
            )
            expected = {
                path.relative_to(HOME).as_posix()
                for path in self.release.profile_paths(HOME)
                if path.is_file()
            }
            self.assertEqual(set(manifest["profiles"]), expected)
            self.assertIn(".codex/agents/wave-oracle.toml", manifest["profiles"])
            self.assertNotIn(".codex/agents/wave-reviewer.toml", manifest["profiles"])

    def test_profile_contracts_match_across_runtimes(self) -> None:
        for name in (
            "acceptance-reviewer",
            "contract-planner",
            "wave-oracle",
            "wave-implementer",
        ):
            files = (
                (HOME / ".codex" / "agents" / f"{name}.toml", ".toml"),
                (HOME / ".claude" / "agents" / f"{name}.md", ".md"),
                (HOME / ".pi" / "agent" / "agents" / f"{name}.md", ".md"),
            )
            bodies = {
                self.release.normalized_sha256(
                    self.release.profile_standing_orders(path.read_text(encoding="utf-8"), suffix)
                )
                for path, suffix in files
            }
            self.assertEqual(len(bodies), 1, name)

    def test_codex_and_claude_profiles_do_not_advertise_pipeline_capability(self) -> None:
        for runtime, root, suffix in (
            ("codex", HOME / ".codex" / "agents", ".toml"),
            ("claude", HOME / ".claude" / "agents", ".md"),
        ):
            for role in ("wave-oracle", "wave-implementer"):
                with self.subTest(runtime=runtime, role=role):
                    text = (root / f"{role}{suffix}").read_text(encoding="utf-8")
                    self.assertNotRegex(text, r"(?m)^pipeline:\s*true\s*$")
        for role in ("wave-oracle", "wave-implementer"):
            pi = (HOME / ".pi" / "agent" / "agents" / f"{role}.md").read_text(
                encoding="utf-8"
            )
            self.assertRegex(pi, r"(?m)^pipeline:\s*true\s*$")

    def test_pi_profiles_keep_runtime_frontmatter_contract(self) -> None:
        for name in ("wave-oracle", "wave-implementer"):
            text = (HOME / ".pi" / "agent" / "agents" / f"{name}.md").read_text(
                encoding="utf-8"
            )
            for key in (
                "model:",
                "thinking:",
                "tools:",
                "systemPromptMode:",
                "inheritProjectContext:",
                "inheritSkills:",
                "pipeline:",
            ):
                self.assertIn(key, text)

    def test_doctor_detects_shipped_profile_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "home" / ".codex" / "skills" / "orchestrate"
            skill.parent.mkdir(parents=True)
            shutil.copytree(CODEX_SKILL, skill)
            profile = root / "home" / ".codex" / "agents" / "wave-oracle.toml"
            profile.parent.mkdir(parents=True)
            shutil.copy2(HOME / ".codex" / "agents" / "wave-oracle.toml", profile)
            profile.write_text(profile.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
            result = self.release.verify_release(skill)
            self.assertFalse(result["ok"])
            self.assertTrue(any("wave-oracle" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
