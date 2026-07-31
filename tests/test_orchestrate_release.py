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

    @staticmethod
    def run_cli(
        *args: str, skill_dir: Path = CODEX_SKILL
    ) -> subprocess.CompletedProcess[str]:
        script = skill_dir / "scripts/orchestrate.py"
        return subprocess.run(
            [sys.executable, str(script), "--skill-dir", str(skill_dir), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_every_runtime_builds_the_same_manifest(self) -> None:
        release = load_release_module()
        self.assertEqual(
            release.build_manifest(CODEX_SKILL, SHIPPED_VERSION),
            release.build_manifest(PI_SKILL, SHIPPED_VERSION),
        )


class RuntimeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.release = load_release_module()

    def test_source_home_resolves_all_runtime_layouts(self) -> None:
        self.assertEqual(self.release.source_home(CODEX_SKILL), HOME.resolve())
        self.assertEqual(self.release.source_home(PI_SKILL), HOME.resolve())
        with self.assertRaisesRegex(Exception, "cannot locate home root"):
            self.release.source_home(Path("/tmp/unsupported/skills/orchestrate"))

    def test_manifest_inventory_covers_every_runtime_profile_without_runtime_assets(self) -> None:
        for skill in (CODEX_SKILL, PI_SKILL):
            manifest = self.release.build_manifest(skill, SHIPPED_VERSION)
            self.assertTrue(
                {"runtime-codex.md", "runtime-claude.md", "runtime-pi.md"}
                <= set(manifest["documents"])
            )
            self.assertNotIn("runtime_assets", manifest)
            expected = {
                path.relative_to(HOME).as_posix()
                for path in self.release.profile_paths(HOME)
                if path.is_file()
            }
            self.assertEqual(set(manifest["profiles"]), expected)
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

    def test_release_cli_success_reports_newly_installed_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            shutil.copytree(HOME, home)
            skill = home / ".codex/skills/orchestrate"
            version = self.release.skill_version(skill)
            guide = skill / f"migrations/{version + 1}.md"
            guide.parent.mkdir(parents=True, exist_ok=True)
            guide.write_text("# test guide\n", encoding="utf-8")
            (skill / f"manifests/{version}.json").write_text(
                json.dumps(self.release.build_manifest(skill, version)), encoding="utf-8"
            )
            script = skill / "scripts/orchestrate.py"

            result = subprocess.run(
                [sys.executable, str(script), "--skill-dir", str(skill),
                 "release", "--version", str(version + 1)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["orchestrate_version"], version + 1)

    def test_v138_manifest_rejects_runtime_assets(self) -> None:
        payload = {
            "schema_version": 1,
            "skill_version": 138,
            "orchestrate_compat": 138,
            "documents": {},
            "profiles": {},
            "runtime_assets": {},
        }
        with self.assertRaisesRegex(
            self.release.OrchestrateError,
            r"runtime_assets is not allowed for v138 and later",
        ):
            self.release.validate_manifest_structure(
                payload, Path("/tmp/v138-invalid-manifest.json"), 138
            )

    def test_v137_manifest_requires_runtime_assets(self) -> None:
        payload = {
            "schema_version": 1,
            "skill_version": 137,
            "orchestrate_compat": 137,
            "documents": {},
            "profiles": {},
        }
        with self.assertRaisesRegex(
            self.release.OrchestrateError,
            r"runtime_assets must be an object for v137 and earlier",
        ):
            self.release.validate_manifest_structure(
                payload, Path("/tmp/v137-invalid-manifest.json"), 137
            )

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
