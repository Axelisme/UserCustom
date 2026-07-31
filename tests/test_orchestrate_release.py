from __future__ import annotations

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
PUBLISHED_VERSION = 136


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

    def test_pi_layout_exposes_guides_and_builds_the_codex_v136_inventory(self) -> None:
        release = load_release_module()
        for version in range(131, PUBLISHED_VERSION + 1):
            codex_guide = CODEX_SKILL / f"migrations/{version}.md"
            pi_guide = PI_SKILL / f"migrations/{version}.md"
            self.assertTrue(pi_guide.is_file(), f"missing Pi guide: {pi_guide}")
            self.assertTrue(pi_guide.samefile(codex_guide))
        self.assertEqual(
            release.build_manifest(CODEX_SKILL, PUBLISHED_VERSION),
            release.build_manifest(PI_SKILL, PUBLISHED_VERSION),
        )

    def test_retained_manifests_remain_byte_immutable(self) -> None:
        expected = {
            130: "2821cf6ade0a2f5bf398fb3001bc104e026e7193683992d0ab74539532e7da10",
            131: "c9e9a2e36c38f31b624c947e9391124f2b397f0fb774c586f2ff2eac8e3fa22f",
            132: "49e390ecb1fe40af8d5964546e310e2dc3f6aeba22a75e30091a119dc6de7767",
            133: "15b95e3f3f55fabcb7629cd2dc9ec2eb80aabb50b825cf7a729d665493ee85c8",
            134: "744a3dbeacc31d0ce8e9dbc5806c7e9901a825c6e0369186451ba98c519d9c52",
            135: "fceecf9860fbec439af556cbf0b606e3d2ad5a4eda6fcf3ddf39f7eabdeb73f7",
        }
        for version, digest in expected.items():
            with self.subTest(version=version):
                observed = hashlib.sha256(
                    (CODEX_SKILL / f"manifests/{version}.json").read_bytes()
                ).hexdigest()
                self.assertEqual(observed, digest)


    def test_pi_guidance_yields_long_interactive_background_work(self) -> None:
        text = " ".join(
            (CODEX_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split()
        )
        required = (
            "normally return control",
            "Before ending an interactive turn or calling `yield_goal`, report concise progress",
            "only when work is blocked only on an external or background prerequisite",
            "Outside goal mode, Root ends the turn, and Pi can wake the session when background work completes",
            "Adapter process events remain wake-only attestation hints",
            "rather than defaulting to `subagent_wait`",
            "delays a compactable or yieldable boundary",
            "can increase context-exhaustion risk",
            "bounded same-turn run-to-completion exception",
            "only when the current turn must receive the result before it can finish",
            "Do not use sleep or polling loops",
            "completed evidence",
            "active run or prerequisite",
            "next action or blocker",
            "Progress prose is never terminal, readiness, or collect evidence",
            "wake-up",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


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

    def test_lane_worker_identity_and_skill_selection_are_structured(self) -> None:
        import tomllib

        codex = tomllib.loads(
            (HOME / ".codex" / "agents" / "lane-worker.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(codex["name"], "lane-worker")
        self.assertIn("description", codex)
        self.assertIn("developer_instructions", codex)
        self.assertIn("Execute one admitted lane from its frozen Contract", codex["developer_instructions"])
        self.assertNotIn("pipeline", codex)
        self.assertNotIn("skills", codex)

        claude = (HOME / ".claude" / "agents" / "lane-worker.md").read_text(encoding="utf-8")
        self.assertRegex(claude, r"(?m)^name:\s*lane-worker\s*$")
        self.assertIn("Execute one admitted lane from its frozen Contract", claude)
        self.assertRegex(claude, r"(?m)^skills:\s*\[tdd\]\s*$")
        self.assertNotRegex(claude, r"(?m)^pipeline:")

        pi = (HOME / ".pi" / "agent" / "agents" / "lane-worker.md").read_text(encoding="utf-8")
        self.assertRegex(pi, r"(?m)^name:\s*lane-worker\s*$")
        self.assertIn("Execute one admitted lane from its frozen Contract", pi)
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

    def test_release_publication_refuses_missing_mandatory_runtime_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            shutil.copytree(HOME, home)
            skill = home / ".codex/skills/orchestrate"
            target = SHIPPED_VERSION + 1
            guide = skill / f"migrations/{target}.md"
            guide.write_text("# next release fixture\n", encoding="utf-8")
            adapter = home / ".pi/agent/extensions/orchestrate-pi.ts"
            adapter.unlink()
            output = skill / "manifests/next.json"

            with self.assertRaisesRegex(
                self.release.OrchestrateError,
                r"mandatory runtime asset.*orchestrate-pi\.ts",
            ):
                self.release.write_release_manifest(
                    skill,
                    target,
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
