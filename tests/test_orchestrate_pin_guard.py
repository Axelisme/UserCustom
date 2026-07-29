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


def load_release_module():
    sys.path.insert(0, str(CODEX_SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


class VerifiedReleaseTaskMutationGuardTests(unittest.TestCase):
    """One CLI preflight seam covers every task-mutating command."""

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def make_case(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, Path, str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "config", "user.name", "Guard Test")
        self.git(root, "config", "user.email", "guard@example.test")
        (root / "README").write_text("base\n", encoding="utf-8")
        self.git(root, "add", "README")
        self.git(root, "commit", "-qm", "base")
        base = self.git(root, "rev-parse", "HEAD")
        home = root / "home"
        shutil.copytree(ROOT / "home", home)
        skill = home / ".codex/skills/orchestrate"
        script = skill / "scripts/orchestrate.py"
        release = load_release_module()
        version = release.skill_version(skill)
        (skill / f"manifests/{version}.json").write_text(
            json.dumps(release.build_manifest(skill, version)), encoding="utf-8"
        )
        return temporary, root, home, script, base

    @staticmethod
    def cli(
        root: Path, skill: Path, script: Path, *args: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), "--skill-dir", str(skill), *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def state(self, root: Path) -> tuple[str, str, str, list[str]]:
        refs = subprocess.run(
            ["git", "show-ref"], cwd=root, text=True, capture_output=True, check=False
        ).stdout
        worktrees = self.git(root, "worktree", "list", "--porcelain")
        status = self.git(root, "status", "--porcelain")
        agent_state = sorted(
            path.relative_to(root).as_posix()
            for path in (root / ".agent_state").rglob("*")
        ) if (root / ".agent_state").exists() else []
        return refs, worktrees, status, agent_state

    @staticmethod
    def task_bytes(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and path.relative_to(root).parts[0] != "home"
        }

    def test_corrupt_mandatory_asset_refuses_every_task_mutation_before_change(self) -> None:
        cases = {
            "lane-create": lambda root, base: (
                "lane", "create", "--root", str(root), "--task-id", "task",
                "--lane-id", "lane", "--base", base,
            ),
            "lane-drop": lambda root, base: (
                "lane", "drop", "--root", str(root), "--task-id", "task",
                "--lane-id", "lane",
            ),
            "integration-create": lambda root, base: (
                "integration", "create", "--root", str(root), "--task-id", "task",
                "--base", base,
            ),
            "integration-collect": lambda root, base: (
                "integration", "collect", "--root", str(root), "--task-id", "task",
                "--lane-id", "lane", "--sha", base,
            ),
            "integration-candidate": lambda root, base: (
                "integration", "candidate", "--root", str(root), "--task-id", "task",
                "--sha", base,
            ),
            "integration-remove": lambda root, base: (
                "integration", "remove", "--root", str(root), "--task-id", "task",
            ),
            "integration-land": lambda root, base: (
                "integration", "land", "--root", str(root), "--task-id", "task",
                "--persist", "main",
            ),
            "pin-set": lambda root, base: (
                "pin", "set", "--root", str(root),
            ),
        }
        for name, arguments in cases.items():
            with self.subTest(command=name):
                temporary, root, home, script, base = self.make_case()
                try:
                    skill = home / ".codex/skills/orchestrate"
                    adapter = home / ".pi/agent/extensions/orchestrate-pi.ts"
                    adapter.write_bytes(adapter.read_bytes() + b"\ncorrupt\n")
                    before = self.state(root)

                    result = self.cli(root, skill, script, *arguments(root, base))

                    self.assertEqual(result.returncode, 2, result.stdout)
                    payload = json.loads(result.stderr)
                    self.assertEqual(payload["orchestrate_version"], 134)
                    self.assertIn("release preflight failed", payload["error"]["message"])
                    self.assertEqual(self.state(root), before)
                finally:
                    temporary.cleanup()

    def test_malformed_manifest_refuses_task_mutation_without_traceback_or_state(self) -> None:
        temporary, root, home, script, base = self.make_case()
        try:
            skill = home / ".codex/skills/orchestrate"
            release = load_release_module()
            version = release.skill_version(skill)
            manifest_path = skill / f"manifests/{version}.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            document_name = next(iter(manifest["documents"]))
            manifest["documents"] = {document_name: []}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            before = (self.state(root), self.task_bytes(root))

            result = self.cli(
                root,
                skill,
                script,
                "lane",
                "create",
                "--root",
                str(root),
                "--task-id",
                "malformed-manifest",
                "--lane-id",
                "lane",
                "--base",
                base,
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)
            payload = json.loads(result.stderr)
            self.assertEqual(payload["orchestrate_version"], version)
            self.assertIsInstance(payload["orchestrate_version"], int)
            self.assertEqual(payload["error"]["type"], "orchestrate")
            self.assertIn(
                "invalid release manifest structure",
                payload["error"]["message"],
            )
            self.assertEqual((self.state(root), self.task_bytes(root)), before)
        finally:
            temporary.cleanup()

    def test_alternate_skill_dir_cannot_supply_task_mutation_provenance(self) -> None:
        temporary, root, home, script, base = self.make_case()
        try:
            executing_adapter = home / ".pi/agent/extensions/orchestrate-pi.ts"
            executing_adapter.write_bytes(executing_adapter.read_bytes() + b"\ncorrupt\n")

            alternate_home = root / "alternate-home"
            shutil.copytree(ROOT / "home", alternate_home)
            alternate_skill = alternate_home / ".codex/skills/orchestrate"
            alternate_skill_md = alternate_skill / "SKILL.md"
            alternate_skill_md.write_text(
                alternate_skill_md.read_text(encoding="utf-8").replace(
                    "skill_version: 134", "skill_version: 133"
                ),
                encoding="utf-8",
            )
            release = load_release_module()
            (alternate_skill / "manifests/133.json").write_text(
                json.dumps(release.build_manifest(alternate_skill, 133)),
                encoding="utf-8",
            )
            before = self.state(root)

            result = self.cli(
                root,
                alternate_skill,
                script,
                "lane",
                "create",
                "--root",
                str(root),
                "--task-id",
                "wrong-package",
                "--lane-id",
                "lane",
                "--base",
                base,
            )

            self.assertEqual(result.returncode, 2, result.stdout)
            payload = json.loads(result.stderr)
            self.assertEqual(payload["orchestrate_version"], 134)
            self.assertIn("--skill-dir", payload["error"]["message"])
            self.assertEqual(self.state(root), before)
        finally:
            temporary.cleanup()

    def test_missing_and_mismatched_pin_do_not_block_task_mutation(self) -> None:
        temporary, root, home, script, base = self.make_case()
        try:
            skill = home / ".codex/skills/orchestrate"
            missing = self.cli(
                root, skill, script, "lane", "create", "--root", str(root),
                "--task-id", "missing-pin", "--lane-id", "lane", "--base", base,
            )
            self.assertEqual(missing.returncode, 0, missing.stderr)

            pin = root / ".agent_state/orchestrate/version-pin.json"
            pin.parent.mkdir(parents=True, exist_ok=True)
            pin.write_text(
                json.dumps({"pin_version": 1, "skill_version": 130,
                            "orchestrate_compat": 130}),
                encoding="utf-8",
            )
            drift = self.cli(
                root, skill, script, "integration", "create", "--root", str(root),
                "--task-id", "drift", "--base", base,
            )
            self.assertEqual(drift.returncode, 0, drift.stderr)
            self.assertEqual(json.loads(drift.stdout)["orchestrate_version"], 134)
        finally:
            temporary.cleanup()


class CurrentManifestParityTests(unittest.TestCase):
    def test_v134_manifest_is_byte_identical_across_codex_and_pi(self) -> None:
        release = load_release_module()
        self.assertEqual(release.skill_version(CODEX_SKILL), 134)
        codex_manifest = CODEX_SKILL / "manifests/134.json"
        pi_manifest = PI_SKILL / "manifests/134.json"
        self.assertTrue(codex_manifest.is_file())
        self.assertTrue(pi_manifest.is_file())
        self.assertEqual(codex_manifest.read_bytes(), pi_manifest.read_bytes())


if __name__ == "__main__":
    unittest.main()
