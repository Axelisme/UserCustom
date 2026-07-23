from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home/.codex/skills/orchestrate/scripts/orchestrate.py"


class V119SimplifyRegressionTests(unittest.TestCase):
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

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_profile_exposes_only_read_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, "init", "-q", "-b", "main")
            result = self.cli(root, "profile", "--help")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("report", result.stdout)
            self.assertNotIn("recommend", result.stdout)

    def test_profile_report_is_scoped_to_task_role_refs(self) -> None:
        temporary, root, base = self.init()
        try:
            for task, suffix in (("task-a", "a"), ("task-b", "b")):
                self.git(root, "checkout", "-qb", f"wave/{task}/wave-1/oracle", base)
                self.commit(root, f"oracle-{suffix}.txt", suffix, f"oracle {suffix}\n\nWave: wave-1\nSlice: slice-{suffix}\nRole: oracle\n")
                self.git(root, "checkout", "-qb", f"wave/{task}/wave-1/implementation", base)
                self.commit(root, f"implementation-{suffix}.txt", suffix, f"implementation {suffix}\n\nWave: wave-1\nSlice: slice-{suffix}\nRole: implementation\n")
                self.git(root, "checkout", "main")
            report = self.payload(self.cli(root, "profile", "report", "--root", str(root), "--task-id", "task-a", "--wave-id", "wave-1", "--base", base))
            self.assertEqual(set(report["slices"]), {"slice-a"})
            empty = self.payload(self.cli(root, "profile", "report", "--root", str(root), "--task-id", "missing", "--wave-id", "wave-1", "--base", base))
            self.assertEqual(empty["slices"], {})
        finally:
            temporary.cleanup()

    def test_modify_modify_conflict_preserves_real_stage_one(self) -> None:
        temporary, root, base = self.init()
        try:
            self.commit(root, "shared/conflict.txt", "base\n", "add conflict base")
            base = self.git(root, "rev-parse", "HEAD")
            for role in ("implementation", "oracle"):
                result = self.cli(root, "worktree", "create", "--root", str(root), "--task-id", "task", "--wave-id", "wave", "--role", role, "--base", base)
                self.payload(result)
            implementation = root / ".agent_state/worktrees/task-wave-implementation"
            oracle = root / ".agent_state/worktrees/task-wave-oracle"
            self.commit(implementation, "shared/conflict.txt", "implementation\n", "implementation change")
            contract = self.commit(oracle, "shared/conflict.txt", "oracle\n", "oracle contract\n\nWave: wave\nSlice: conflict\nRole: oracle\n")
            result = self.cli(root, "contract", "merge", "--root", str(root), "--task-id", "task", "--wave-id", "wave", "--contract-sha", contract)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.git(implementation, "show", ":1:shared/conflict.txt"), "base")
        finally:
            temporary.cleanup()

    def test_sha256_worktree_and_handoffs_use_full_exact_sha(self) -> None:
        temporary, root, base = self.init(sha256=True)
        try:
            self.assertEqual(len(base), 64)
            result = self.payload(self.cli(root, "worktree", "create", "--root", str(root), "--task-id", "sha", "--wave-id", "wave", "--role", "oracle", "--base", base))
            self.assertEqual(len(result["base"]), 64)
        finally:
            temporary.cleanup()
        for path in (
            ROOT / "home/.codex/skills/orchestrate/runtime-codex.md",
            ROOT / "home/.codex/agents/wave-oracle.toml",
            ROOT / "home/.claude/agents/wave-oracle.md",
            ROOT / "home/.pi/agent/agents/wave-oracle.md",
        ):
            self.assertNotIn("40-character", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
