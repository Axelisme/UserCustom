from __future__ import annotations

import ast
import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = SKILL / "scripts" / "orchestrate.py"


def load_release_module():
    sys.path.insert(0, str(SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


class CliExecutableProvenanceTests(unittest.TestCase):
    """Every JSON response identifies the installed executable release."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        shutil.copytree(ROOT / "home", self.home)
        self.skill = self.home / ".codex/skills/orchestrate"
        self.script = self.skill / "scripts/orchestrate.py"
        release = load_release_module()
        self.version = release.skill_version(self.skill)
        (self.skill / f"manifests/{self.version}.json").write_text(
            json.dumps(release.build_manifest(self.skill, self.version)),
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=self.root, check=True
        )

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

    def assert_version(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        stream = result.stdout if result.stdout else result.stderr
        payload = json.loads(stream)
        self.assertEqual(payload["orchestrate_version"], self.version)
        return payload

    def test_success_response_carries_installed_version(self) -> None:
        result = self.cli("pin", "status", "--root", str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.assert_version(result)["ok"])

    def test_completed_negative_response_carries_installed_version(self) -> None:
        adapter = self.home / ".pi/agent/extensions/orchestrate-pi.ts"
        adapter.write_bytes(adapter.read_bytes() + b"\ncorrupt\n")
        result = self.cli("doctor")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(self.assert_version(result)["ok"])

    def test_command_error_carries_installed_version(self) -> None:
        pin = self.root / ".agent_state/orchestrate/version-pin.json"
        pin.parent.mkdir(parents=True)
        pin.write_text("not-json", encoding="utf-8")
        result = self.cli("pin", "status", "--root", str(self.root))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.assert_version(result)["ok"])

    def test_parser_error_carries_installed_version(self) -> None:
        result = self.cli("lane", "create")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.assert_version(result)["ok"])

    def test_unreadable_installed_version_is_the_only_null_case(self) -> None:
        skill_md = self.skill / "SKILL.md"
        skill_md.write_text("---\nname: orchestrate\n---\n", encoding="utf-8")
        result = self.cli("pin", "status", "--root", str(self.root))
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stderr)
        self.assertIsNone(payload["orchestrate_version"])
        self.assertIn("skill_version", payload["error"]["message"])


class CoreRuntimeIndependenceTests(unittest.TestCase):
    """The core tracer must not import or name any runtime adapter."""

    def test_core_has_no_runtime_binding_or_pipeline_authority(self) -> None:
        source = (SKILL / "scripts" / "_orchestrate" / "lane_core.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("pipeline", imported)
        self.assertNotIn("runtime", imported)
        self.assertNotRegex(source, r"(?i)pi-subagents|codex|claude|pipelinemanager")


class CoreCliRegressionTests(unittest.TestCase):
    """Regression guards for shared command primitives.

    Exact full-length object ids are required by every command that accepts a
    ``--base`` or ``--sha`` value.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = tempfile.TemporaryDirectory()
        home = Path(cls.package.name) / "home"
        shutil.copytree(ROOT / "home", home)
        cls.skill = home / ".codex/skills/orchestrate"
        cls.script = cls.skill / "scripts/orchestrate.py"
        release = load_release_module()
        version = release.skill_version(cls.skill)
        (cls.skill / f"manifests/{version}.json").write_text(
            json.dumps(release.build_manifest(cls.skill, version)), encoding="utf-8"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.package.cleanup()

    def git(self, root: Path, *args: str, check: bool = True) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
        if check and result.returncode:
            self.fail(result.stderr)
        return result.stdout.strip()

    def cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.script), "--skill-dir", str(self.skill), *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def init(self, *, sha256: bool = False) -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        init_args = ["init", "-q", "-b", "main"]
        if sha256:
            init_args[1:1] = ["--object-format=sha256"]
        self.git(root, *init_args)
        self.git(root, "config", "user.name", "Simplify Test")
        self.git(root, "config", "user.email", "simplify@example.test")
        (root / "README").write_text("base\n", encoding="utf-8")
        self.git(root, "add", "README")
        self.git(root, "commit", "-qm", "base")
        return temporary, root, self.git(root, "rev-parse", "HEAD")

    def commit(self, root: Path, path: str, content: str, message: str) -> str:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(root, "add", path)
        self.git(root, "commit", "-qm", message)
        return self.git(root, "rev-parse", "HEAD")

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_sha256_lane_and_integration_use_full_exact_sha(self) -> None:
        temporary, root, base = self.init(sha256=True)
        try:
            self.assertEqual(len(base), 64)
            lane = self.payload(self.cli(root, "lane", "create", "--root", str(root), "--task-id", "sha", "--lane-id", "lane-a", "--base", base))
            self.assertEqual(len(lane["base"]), 64)
            integration = self.payload(self.cli(root, "integration", "create", "--root", str(root), "--task-id", "sha", "--base", base))
            self.assertEqual(len(integration["base"]), 64)
            lane_path = Path(str(lane["worktree"]))
            (lane_path / "feature.txt").write_text("value\n", encoding="utf-8")
            self.git(lane_path, "add", "feature.txt")
            self.git(
                lane_path,
                "commit",
                "-qm",
                "implement\n\nImmutable: feature.txt",
            )
            sha = self.git(lane_path, "rev-parse", "HEAD")
            self.assertEqual(len(sha), 64)
            collected = self.payload(self.cli(root, "integration", "collect", "--root", str(root), "--task-id", "sha", "--lane-id", "lane-a", "--sha", sha))
            self.assertEqual(len(collected["collect_sha"]), 64)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
