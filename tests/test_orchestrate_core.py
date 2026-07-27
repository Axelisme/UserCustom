from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = SKILL / "scripts" / "orchestrate.py"


class CoreRuntimeIndependenceTests(unittest.TestCase):
    """The core tracer must not import or name any runtime adapter."""

    def test_core_has_no_runtime_binding_or_pipeline_authority(self) -> None:
        source = (SKILL / "scripts" / "_orchestrate" / "v119_core.py").read_text(
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
    """Regression guards for behavior orthogonal to the lane/Wave split.

    The worktree/role/Contract-merge lifecycle these tests once exercised was
    replaced by the lane model; that Contract now lives in
    ``test_orchestrate_lane.py`` and ``test_orchestrate_integration.py``. The
    Oracle/Implementation ``profile report`` these tests used to cover was
    retired along with the role vocabulary it read; its replacement,
    ``report``, has its own Contract in ``test_orchestrate_report.py``. What
    remains here is a primitive shared by every command that accepts a
    ``--base``/``--sha`` (exact full-length object ids).
    """

    def git(self, root: Path, *args: str, check: bool = True) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
        if check and result.returncode:
            self.fail(result.stderr)
        return result.stdout.strip()

    def cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, text=True, capture_output=True, check=False)

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
            self.git(lane_path, "commit", "-qm", "implement")
            sha = self.git(lane_path, "rev-parse", "HEAD")
            self.assertEqual(len(sha), 64)
            collected = self.payload(self.cli(root, "integration", "collect", "--root", str(root), "--task-id", "sha", "--lane-id", "lane-a", "--sha", sha))
            self.assertEqual(len(collected["collect_sha"]), 64)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
