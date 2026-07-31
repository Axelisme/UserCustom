from __future__ import annotations

import hashlib
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
SCRIPT = CODEX_SKILL / "scripts/orchestrate.py"
GUIDE_VERSIONS = (131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142)
RETAINED_GUIDE_SHA256 = {
    131: "3ac711b53f0410640179261ee45288ce0b6a7d1e470c85df0623d2f2da5266ad",
    132: "02b355608886e893ad9fa17c5d797e3822fd980f9a8d2072232ec6c199a57cb3",
    133: "529d3702851b721580544743ab5f6539ee47e6e404c67c744368d4191632dde4",
    134: "8a3a425463086faf852ea4639389dc3f16dfe20579d2006ebe49c2ec4d6d915b",
    135: "610fe2f54db967f287002ead5dcd7717b9c6ae91f085399ca6b86853fb7d686b",
    136: "35bf94bea868b3ed90a2de541df0009fac20b51293f922dadfdd3cd92af7e8e1",
    137: "f084bcc68d976fa5129ef8b28dcb7610acacbb2249555cf8ec03e27b7052ddb2",
    138: "65eac25828efb888c81664d4200c0af5522a5a4062ed56135e190721c2679017",
    139: "ced3c3c9bd8549835fe92ce75e254cb4cbd27645bad0067b8c9fd5274979ad47",
    140: "042bd28d751bd177fb5037d2d290e13966cbc0b01a155e51fc987d03630f2a92",
    141: "d1a73855e69b45f721949815cd5155ef2c9ae4bab7588f2cd964516fd1526988",
}
GUIDE_SECTIONS = (
    "From",
    "Observable changes",
    "Active-task impact",
    "Manual steps",
    "Verification",
    "Rollback",
)


def load_release_module():
    sys.path.insert(0, str(CODEX_SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


class PinAndMigrationGuideContractTests(unittest.TestCase):
    """The pin has one writer; immutable guides replace active-state migration."""

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
        self.git(self.root, "config", "user.name", "Migration Test")
        self.git(self.root, "config", "user.email", "migration@example.test")
        self.git(self.root, "commit", "--allow-empty", "-qm", "base")
        self.home = self.root / "home"
        shutil.copytree(ROOT / "home", self.home)
        self.skill = self.home / ".codex/skills/orchestrate"
        self.script = self.skill / "scripts/orchestrate.py"
        self.version = self.release.skill_version(self.skill)
        (self.skill / f"manifests/{self.version}.json").write_text(
            json.dumps(self.release.build_manifest(self.skill, self.version)),
            encoding="utf-8",
        )
        self.pin = self.root / ".agent_state/orchestrate/version-pin.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.script), "--skill-dir", str(self.skill), *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_pin(self, version: int) -> bytes:
        self.pin.parent.mkdir(parents=True, exist_ok=True)
        self.pin.write_text(
            json.dumps(
                {"pin_version": 1, "skill_version": version,
                 "orchestrate_compat": version, "pinned_at": "retained"},
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return self.pin.read_bytes()

    def test_pin_migrate_is_absent_and_pin_set_is_the_only_pin_writer(self) -> None:
        help_result = self.cli("pin", "--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertNotIn("migrate", help_result.stdout)
        source = (self.skill / "scripts/_orchestrate/release.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("MIGRATION_BOUNDARIES", source)
        self.assertNotIn("command_pin_migrate", source)
        self.assertNotIn("active_task_state", source)
        self.assertEqual(source.count("write_version_pin("), 2)  # definition + pin set

    def test_guides_are_complete_and_hashed_as_release_documents(self) -> None:
        guide_137 = CODEX_SKILL / "migrations/137.md"
        self.assertTrue(guide_137.is_file(), "missing v137 migration guide")
        manifest = self.release.build_manifest(
            CODEX_SKILL, self.release.skill_version(CODEX_SKILL)
        )
        guides = CODEX_SKILL / "migrations"
        self.assertEqual(
            {int(path.stem) for path in guides.glob("*.md")}, set(GUIDE_VERSIONS)
        )
        for version in GUIDE_VERSIONS:
            with self.subTest(version=version):
                path = guides / f"{version}.md"
                text = path.read_text(encoding="utf-8")
                self.assertIn(f"# Migrate to Orchestrate v{version}", text)
                self.assertIn(f"## From\n\nv{version - 1}", text)
                for section in GUIDE_SECTIONS:
                    self.assertIn(f"## {section}", text)
                entry = manifest["documents"][f"migrations/{version}.md"]
                self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_retained_guides_remain_byte_immutable(self) -> None:
        for version, digest in RETAINED_GUIDE_SHA256.items():
            with self.subTest(version=version):
                observed = hashlib.sha256(
                    (CODEX_SKILL / f"migrations/{version}.md").read_bytes()
                ).hexdigest()
                self.assertEqual(observed, digest)

    def test_v135_is_docs_only_and_defers_the_planning_cutover(self) -> None:
        text = (CODEX_SKILL / "migrations/135.md").read_text(encoding="utf-8")
        required = (
            "docs-only release",
            "planning-with-files to dev-flow cutover is not implemented in v135",
            "future atomic Wave B cutover",
            "manual legacy migration",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_v136_records_atomic_cutover_and_truthful_no_migration(self) -> None:
        text = (CODEX_SKILL / "migrations/136.md").read_text(encoding="utf-8")
        required = (
            "dev-flow is the sole active durable-task authority",
            "replacement verification succeeds before managed planning links are removed",
            "v136 migrates no legacy records",
            "normal setup rerun is the only removal recovery",
            "v135 pin remains unchanged",
            "repair forward",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn("convert legacy", text.casefold())
        self.assertNotIn("restore planning", text.casefold())

    def test_retrospective_guides_preserve_every_removed_boundary(self) -> None:
        required_phrases = {
            131: (
                "landing is a squash commit",
                "Landed:",
                "task refs and branches",
                "integration candidate",
            ),
            132: (
                "one worker per lane",
                "redispatch",
                "pre-collect test review",
                "cwd attestation",
            ),
            133: (
                "Pi Adapter is mandatory",
                "exact run/process terminal evidence",
                "Root authority is unchanged",
            ),
        }
        for version, phrases in required_phrases.items():
            text = (CODEX_SKILL / f"migrations/{version}.md").read_text(
                encoding="utf-8"
            )
            with self.subTest(version=version):
                self.assertIn("No automatic conversion", text)
                for phrase in phrases:
                    self.assertIn(phrase, text)

    def test_v134_guide_records_best_effort_tested_pi_subagents_version(self) -> None:
        text = (CODEX_SKILL / "migrations/134.md").read_text(encoding="utf-8")
        self.assertIn("pi-subagents 0.37.2", text)
        self.assertIn("best-effort", text)
        self.assertIn("does not block", text)


if __name__ == "__main__":
    unittest.main()
