from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = SKILL / "scripts" / "orchestrate.py"


def load_release_module():
    sys.path.insert(0, str(SKILL / "scripts"))
    try:
        from _orchestrate import release
    finally:
        sys.path.pop(0)
    return release


class OrchestrateV119MigrationContractTests(unittest.TestCase):
    """Oracle-owned contract for v118 pin migration into a manual v119 Wave."""

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def shipped_skill_fixture(self, root: Path, release) -> tuple[Path, int]:
        # Copy the shipped package as an installed-package-shaped fixture.  A
        # missing v118 manifest intentionally exercises the documented manual
        # migration path rather than a synthetic private helper.
        home = root / "home"
        shutil.copytree(ROOT / "home", home)
        skill = home / ".codex" / "skills" / "orchestrate"
        version = release.skill_version(skill)
        (skill / "manifests" / "118.json").unlink()
        manifest = release.build_manifest(skill, version)
        (skill / "manifests" / f"{version}.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return skill, version

    def test_pin_migrate_preserves_shape_and_emits_every_crossed_boundary(self) -> None:
        release = load_release_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, "init", "-q", "-b", "main")
            self.git(root, "config", "user.name", "Oracle Test")
            self.git(root, "config", "user.email", "oracle@example.test")
            self.git(root, "commit", "--allow-empty", "-qm", "base")
            skill, version = self.shipped_skill_fixture(root, release)

            # Legacy evidence and state are read-only migration input.  The
            # migration must not attempt to convert or delete either asset.
            evidence = root / ".agent_state" / "legacy" / "findings.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text('{"legacy": true}\n', encoding="utf-8")
            legacy_state = root / ".agent_state" / "legacy-lanes.json"
            legacy_state.write_text('{"lane": "old"}\n', encoding="utf-8")
            pin = root / ".agent_state" / "orchestrate" / "version-pin.json"
            pin.parent.mkdir(parents=True)
            pin.write_text(
                json.dumps(
                    {
                        "pin_version": 1,
                        "skill_version": 118,
                        "orchestrate_compat": 118,
                    }
                ),
                encoding="utf-8",
            )

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
            self.assertEqual(result["from_version"], 118)
            self.assertEqual(result["to_version"], version)
            self.assertIsNone(result["delta"])
            requirements = {block["reason"]: block for block in result["migration_requirements"]}
            restart = requirements["v118-to-v119-manual-restart"]
            self.assertTrue(restart["stop_legacy_dispatch"])
            self.assertTrue(restart["preserve_legacy_evidence"])
            self.assertTrue(restart["select_exact_base"])
            self.assertTrue(restart["create_new_wave"])
            self.assertTrue(restart["continue_as_v119_wave"])
            self.assertFalse(restart["automatic_conversion"])
            # Crossing v120 must also publish what the unchanged Git model does not imply.
            adoption = requirements["v119-to-v120-workflow-adoption"]
            for surface in (
                "adopt_integration_cli",
                "record_integration_base_ref",
                "machine_gates_then_collect_per_wave",
                "milestone_acceptance_replaces_per_wave_review",
                "correction_after_collect_is_a_new_wave",
                "declare_runtime_pipelines_before_enqueue",
                "empty_handoff_after_contract_merge",
                "blocked_reason_enum_replaces_checkpoint",
            ):
                self.assertTrue(adoption[surface], surface)
            self.assertFalse(adoption["automatic_conversion"])
            self.assertEqual(
                json.loads(pin.read_text(encoding="utf-8"))["skill_version"], version
            )
            self.assertEqual(evidence.read_text(encoding="utf-8"), '{"legacy": true}\n')
            self.assertEqual(legacy_state.read_text(encoding="utf-8"), '{"lane": "old"}\n')

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
            self.git(root, "init", "-q", "-b", "main")
            self.git(root, "config", "user.name", "Oracle Test")
            self.git(root, "config", "user.email", "oracle@example.test")
            self.git(root, "commit", "--allow-empty", "-qm", "base")
            skill, version = self.shipped_skill_fixture(root, release)
            pin = root / ".agent_state" / "orchestrate" / "version-pin.json"
            pin.parent.mkdir(parents=True)
            pin.write_text(
                json.dumps({"skill_version": version, "orchestrate_compat": version}),
                encoding="utf-8",
            )

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
