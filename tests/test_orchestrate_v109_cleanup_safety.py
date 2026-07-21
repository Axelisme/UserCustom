from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"
PI_RUNTIME = ROOT / "home" / ".pi" / "agent" / "skills" / "orchestrate" / "runtime-pi.md"


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def run_cli(root: Path, *arguments: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--root", str(root)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def run_cli_failure(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--root", str(root)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        raise AssertionError(result.stdout)
    return result.stderr or result.stdout


def init_repo(root: Path) -> Path:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "V109")
    git(root, "config", "user.email", "v109@example.invalid")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")
    managed = root / ".agent_state" / "worktrees"
    managed.mkdir(parents=True)
    git(root, "branch", "agent/demo/clean")
    lane = managed / "demo-clean"
    git(root, "worktree", "add", str(lane), "agent/demo/clean")
    integration = root / ".agent_state" / "integration"
    git(root, "worktree", "add", str(integration), "task/demo")
    return integration


class CleanupSafetyTests(unittest.TestCase):
    def test_git_projection_and_legacy_alias_are_equal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            integration = init_repo(root)
            expected = [str((root / ".agent_state" / "worktrees" / "demo-clean").resolve())]

            reconcile = run_cli(root, "reconcile")
            wave = run_cli(root, "wave", "status", "--task-ref", "task/demo")
            dry_run = run_cli(root, "cleanup", "--dry-run")

            for report in (reconcile, wave["handoff"], dry_run):
                self.assertEqual(report["git_safe_to_remove"], expected)
                self.assertEqual(report["safe_to_remove"], report["git_safe_to_remove"])
                self.assertEqual(report["runtime_lease_safety"], "unchecked")
            self.assertEqual(wave["reconcile"]["git_safe_to_remove"], expected)
            self.assertEqual(wave["reconcile"]["runtime_lease_safety"], "unchecked")
            self.assertTrue(integration.exists())

    def test_cleanup_guidance_labels_git_safety_and_requires_lease_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            message = run_cli_failure(root, "cleanup")

            self.assertIn("Git-safe-to-remove targets:", message)
            self.assertIn("runtime lease safety is unchecked", message)
            self.assertIn("requires runtime binding lease preflight", message)
            self.assertNotIn("(safe:", message)

        landing = (SCRIPT.parent / "_orchestrate" / "landing.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(landing.count("Git-safe-to-remove exact"), 2)
        self.assertEqual(landing.count("runtime lease"), 2)
        self.assertEqual(landing.count("safety is unchecked"), 2)
        self.assertEqual(landing.count("runtime binding lease preflight"), 2)

    def test_pi_binding_requires_fleet_lease_exclusion_and_interrupt_cancellation(self) -> None:
        runtime = PI_RUNTIME.read_text(encoding="utf-8")
        self.assertIn("active/paused", runtime)
        self.assertIn("cwd lease", runtime)
        self.assertIn("runtime lease safety is unchecked", runtime.lower())
        self.assertIn("`steer` delivers guidance; it does not preempt active tools", runtime)
        self.assertIn("use `interrupt`", runtime)
        self.assertIn("Do not `resume` that child", runtime)


if __name__ == "__main__":
    unittest.main()
