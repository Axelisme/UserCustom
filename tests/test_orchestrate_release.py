from __future__ import annotations

import argparse
import hashlib
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
        "lane",
        "integration",
        "report",
        "doctor",
        "diff",
        "pin",
        "release",
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

    def test_manifest_inventory_covers_every_runtime_profile_and_raw_runtime_asset(self) -> None:
        adapter_relative = ".pi/agent/extensions/orchestrate-pi.ts"
        adapter = HOME / adapter_relative
        expected_adapter = {
            "bytes": len(adapter.read_bytes()),
            "sha256": hashlib.sha256(adapter.read_bytes()).hexdigest(),
        }
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
            self.assertEqual(
                manifest["runtime_assets"], {adapter_relative: expected_adapter}
            )
            for runtime, suffix in (
                ("codex", ".toml"),
                ("claude", ".md"),
                ("pi/agent", ".md"),
            ):
                self.assertIn(f".{runtime}/agents/lane-worker{suffix}", manifest["profiles"])

    def test_profile_contract_hash_is_compare_authority(self) -> None:
        old = {
            "skill_version": 130,
            "orchestrate_compat": 130,
            "documents": {},
            "profiles": {
                ".codex/agents/contract-planner.toml": {
                    "profile_contract_sha256": "old-contract",
                    "standing_orders_sha256": "same-standing-orders",
                }
            },
        }
        new = {
            "skill_version": 131,
            "orchestrate_compat": 131,
            "documents": {},
            "profiles": {
                ".codex/agents/contract-planner.toml": {
                    "profile_contract_sha256": "new-contract",
                    "standing_orders_sha256": "same-standing-orders",
                }
            },
        }
        comparison = self.release.compare_manifests(old, new)
        self.assertEqual(comparison["changed_profiles"], [".codex/agents/contract-planner.toml"])

    def test_lane_worker_models_and_skill_selection_are_structured(self) -> None:
        import tomllib

        codex = tomllib.loads(
            (HOME / ".codex" / "agents" / "lane-worker.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(codex["model"], "gpt-5.6-sol")
        self.assertEqual(codex["model_reasoning_effort"], "high")
        self.assertNotIn("pipeline", codex)
        self.assertNotIn("skills", codex)

        claude = (HOME / ".claude" / "agents" / "lane-worker.md").read_text(encoding="utf-8")
        self.assertRegex(claude, r"(?m)^model:\s*sonnet\s*$")
        self.assertRegex(claude, r"(?m)^skills:\s*\[tdd\]\s*$")
        self.assertNotRegex(claude, r"(?m)^pipeline:")

        pi = (HOME / ".pi" / "agent" / "agents" / "lane-worker.md").read_text(encoding="utf-8")
        self.assertRegex(pi, r"(?m)^model:\s*openai-codex/gpt-5.6-sol\s*$")
        self.assertRegex(pi, r"(?m)^thinking:\s*high\s*$")
        self.assertRegex(pi, r"(?m)^inheritSkills:\s*false\s*$")
        self.assertRegex(pi, r"(?m)^skills:\s*tdd\s*$")
        self.assertNotRegex(pi, r"(?m)^pipeline:")

    def test_old_schema_one_manifest_without_runtime_assets_compares_as_empty(self) -> None:
        old = {
            "schema_version": 1,
            "skill_version": 132,
            "orchestrate_compat": 132,
            "documents": {},
            "profiles": {},
        }
        new = {
            **old,
            "skill_version": 133,
            "orchestrate_compat": 133,
            "runtime_assets": {},
        }

        comparison = self.release.compare_manifests(old, new)

        self.assertEqual(comparison["changed_runtime_assets"], [])

    def test_runtime_filtered_diff_includes_only_matching_runtime_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "home/.codex/skills/orchestrate"
            manifests = skill / "manifests"
            manifests.mkdir(parents=True)
            old = {
                "schema_version": 1,
                "skill_version": 132,
                "orchestrate_compat": 132,
                "documents": {},
                "profiles": {},
            }
            new = {
                **old,
                "skill_version": 133,
                "orchestrate_compat": 133,
                "runtime_assets": {
                    ".pi/agent/extensions/orchestrate-pi.ts": {
                        "bytes": 7,
                        "sha256": "adapter",
                    }
                },
            }
            (manifests / "132.json").write_text(json.dumps(old), encoding="utf-8")
            (manifests / "133.json").write_text(json.dumps(new), encoding="utf-8")

            pi = self.release.command_diff(
                argparse.Namespace(
                    skill_dir=str(skill), old_version=132, new_version=133, runtime="pi"
                )
            )
            codex = self.release.command_diff(
                argparse.Namespace(
                    skill_dir=str(skill), old_version=132, new_version=133, runtime="codex"
                )
            )

            self.assertEqual(
                pi["changed_runtime_assets"],
                [".pi/agent/extensions/orchestrate-pi.ts"],
            )
            self.assertEqual(codex["changed_runtime_assets"], [])

    def test_doctor_detects_missing_and_tampered_runtime_asset_raw_bytes(self) -> None:
        for state in ("missing", "tampered"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = root / "home"
                shutil.copytree(HOME, home)
                skill = home / ".codex/skills/orchestrate"
                version = self.release.skill_version(skill)
                manifest = self.release.build_manifest(skill, version)
                (skill / "manifests" / f"{version}.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
                adapter = home / ".pi/agent/extensions/orchestrate-pi.ts"
                if state == "missing":
                    adapter.unlink()
                else:
                    adapter.write_bytes(adapter.read_bytes() + b"\r\nraw-tamper\r\n")

                result = self.release.verify_release(skill)

                self.assertFalse(result["ok"])
                self.assertTrue(
                    any("orchestrate-pi.ts" in error for error in result["errors"]),
                    result,
                )

    def test_release_publication_refuses_missing_mandatory_runtime_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            shutil.copytree(HOME, home)
            skill = home / ".codex/skills/orchestrate"
            adapter = home / ".pi/agent/extensions/orchestrate-pi.ts"
            adapter.unlink()
            output = skill / "manifests/next.json"

            with self.assertRaisesRegex(
                self.release.OrchestrateError,
                r"mandatory runtime asset.*orchestrate-pi\.ts",
            ):
                self.release.write_release_manifest(
                    skill,
                    SHIPPED_VERSION + 1,
                    None,
                    output,
                )

            self.assertFalse(output.exists())

    def test_doctor_detects_shipped_profile_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "home" / ".codex" / "skills" / "orchestrate"
            skill.parent.mkdir(parents=True)
            shutil.copytree(CODEX_SKILL, skill)
            profile = root / "home" / ".codex" / "agents" / "lane-worker.toml"
            profile.parent.mkdir(parents=True)
            shutil.copy2(HOME / ".codex" / "agents" / "lane-worker.toml", profile)
            profile.write_text(profile.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
            result = self.release.verify_release(skill)
            self.assertFalse(result["ok"])
            self.assertTrue(any("lane-worker" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
