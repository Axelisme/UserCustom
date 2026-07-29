from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CODEX_SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = CODEX_SKILL / "scripts/orchestrate.py"
GUIDE_VERSIONS = (131, 132, 133, 134, 135)
RETAINED_GUIDE_SHA256 = {
    131: "3ac711b53f0410640179261ee45288ce0b6a7d1e470c85df0623d2f2da5266ad",
    132: "02b355608886e893ad9fa17c5d797e3822fd980f9a8d2072232ec6c199a57cb3",
    133: "529d3702851b721580544743ab5f6539ee47e6e404c67c744368d4191632dde4",
    134: "8a3a425463086faf852ea4639389dc3f16dfe20579d2006ebe49c2ec4d6d915b",
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

    def test_pin_set_overwrites_drift_despite_active_task_state(self) -> None:
        self.write_pin(130)
        base = self.git(self.root, "rev-parse", "HEAD")
        self.git(self.root, "branch", "wave/active/lane", base)
        self.git(self.root, "update-ref", "refs/orchestrate/active/candidate", base)
        refs_before = self.git(self.root, "show-ref")

        result = self.cli("pin", "set", "--root", str(self.root))

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["operation"], "pin-set")
        self.assertEqual(payload["previous_version"], 130)
        self.assertEqual(payload["pinned_version"], self.version)
        self.assertEqual(json.loads(self.pin.read_text())["skill_version"], self.version)
        self.assertEqual(self.git(self.root, "show-ref"), refs_before)

    def test_pin_set_same_version_is_idempotent_without_rewrite(self) -> None:
        before = self.write_pin(self.version)

        result = self.cli("pin", "set", "--root", str(self.root))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.pin.read_bytes(), before)
        self.assertEqual(json.loads(result.stdout)["recovered"], "already-pinned")

    def test_failed_release_verification_preserves_previous_pin(self) -> None:
        before = self.write_pin(130)
        adapter = self.home / ".pi/agent/extensions/orchestrate-pi.ts"
        adapter.write_bytes(adapter.read_bytes() + b"\ncorrupt\n")

        result = self.cli("pin", "set", "--root", str(self.root))

        self.assertEqual(result.returncode, 2)
        self.assertIn("release preflight failed", result.stderr)
        self.assertEqual(self.pin.read_bytes(), before)

    def test_atomic_replace_failure_preserves_pin_and_removes_temporary_file(self) -> None:
        before = self.write_pin(130)
        entries_before = sorted(self.pin.parent.iterdir())
        cli = importlib.import_module("_orchestrate.cli")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with mock.patch.object(
            cli,
            "require_verified_release",
            return_value={
                "skill_version": self.version,
                "orchestrate_compat": self.version,
            },
        ), mock.patch.object(
            self.release.os, "replace", side_effect=OSError("replace failed")
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = cli.main(["pin", "set", "--root", str(self.root)])

        self.assertEqual(result, 2, stdout.getvalue())
        self.assertIn("replace failed", stderr.getvalue())
        self.assertEqual(self.pin.read_bytes(), before)
        self.assertEqual(sorted(self.pin.parent.iterdir()), entries_before)

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
        manifest = self.release.build_manifest(CODEX_SKILL, 135)
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
