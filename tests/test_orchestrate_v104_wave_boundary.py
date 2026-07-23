from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"
from tests._orchestrate_test_support import cli_command


def run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cli_command(SCRIPT, [*arguments, "--root", str(root)]),
        check=False,
        text=True,
        capture_output=True,
    )


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=False, text=True, capture_output=True
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def init_repo(root: Path) -> Path:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "V104")
    git(root, "config", "user.email", "v104@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")
    managed = root / ".agent_state" / "worktrees"
    managed.mkdir(parents=True)
    for lane in ("a", "b"):
        git(root, "branch", f"agent/demo/{lane}")
        git(root, "worktree", "add", str(managed / f"demo-{lane}"), f"agent/demo/{lane}")
    # A different task's lane must be out of scope.
    git(root, "branch", "agent/other/z")
    git(root, "worktree", "add", str(managed / "other-z"), "agent/other/z")
    # A detached review worktree carries no task identity.
    git(root, "worktree", "add", "--detach", str(managed / "review-xyz"), "HEAD")
    # Half-abandoned dirt in one demo lane — the sweep must clear it anyway.
    (managed / "demo-b" / "scratch.txt").write_text("wip\n", encoding="utf-8")
    integration = root / ".agent_state" / "intg"
    git(root, "worktree", "add", str(integration), "task/demo")
    return integration


class WaveBoundarySweepTests(unittest.TestCase):
    """v104: a task-scoped bulk sweep that clears this task's leftover lane worktrees at
    a boundary root has judged safe — abandoned/dirty included — while never touching
    another task's lanes, the detached review worktrees it cannot attribute, or the
    integration checkout itself."""

    def test_dry_run_previews_only_this_tasks_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integration = init_repo(root)
            result = run_cli(integration, "cleanup", "--wave-boundary", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["operation"], "cleanup-wave-boundary")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["eligible"], 2)
            by_name = {Path(e["path"]).name: e for e in payload["entries"]}
            self.assertEqual(by_name["demo-a"]["action"], "eligible")
            self.assertEqual(by_name["demo-b"]["action"], "eligible")
            self.assertTrue(by_name["demo-b"]["dirty"])
            self.assertEqual(by_name["other-z"]["action"], "skipped")
            self.assertEqual(by_name["review-xyz"]["kind"], "review")
            self.assertEqual(by_name["review-xyz"]["action"], "skipped")
            # A dry run mutates nothing.
            self.assertTrue((root / ".agent_state" / "worktrees" / "demo-a").exists())
            branches = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/agent/")
            self.assertIn("agent/demo/a", branches.split("\n"))

    def test_real_sweep_scoped_to_task_removes_lanes_and_branches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integration = init_repo(root)
            managed = root / ".agent_state" / "worktrees"
            result = run_cli(integration, "cleanup", "--wave-boundary")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["removed"], 2)
            # This task's lanes and their branches are gone.
            self.assertFalse((managed / "demo-a").exists())
            self.assertFalse((managed / "demo-b").exists())
            branches = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/agent/")
            self.assertEqual(branches, "agent/other/z")
            # The other task's lane, the review worktree, and integration are untouched.
            self.assertTrue((managed / "other-z").exists())
            self.assertTrue((managed / "review-xyz").exists())
            self.assertTrue(integration.exists())
            self.assertEqual(git(integration, "rev-parse", "--abbrev-ref", "HEAD"), "task/demo")

    def test_requires_a_task_branch_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            # `root` itself is on main, not task/<task>.
            result = run_cli(root, "cleanup", "--wave-boundary", "--dry-run")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("task/<task>", result.stderr + result.stdout)

    def test_wave_boundary_rejects_a_named_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integration = init_repo(root)
            some = str((root / ".agent_state" / "worktrees" / "demo-a"))
            result = run_cli(
                integration, "cleanup", "--wave-boundary", "--worktree", some
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("takes no --worktree", result.stderr + result.stdout)


class WaveStatusRemovableTests(unittest.TestCase):
    def test_summary_reports_wave_boundary_removable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            result = run_cli(root, "wave", "status", "--summary", "--task-ref", "task/demo")
            self.assertEqual(result.returncode, 0, result.stderr)
            removable = json.loads(result.stdout)["handoff"]["wave_boundary_removable"]
            names = sorted(Path(p).name for p in removable)
            self.assertEqual(names, ["demo-a", "demo-b"])


class FeedbackRecordTests(unittest.TestCase):
    """v104: an append-only subagent feedback channel — free text, no machine dedup,
    gating nothing, not folded into wave status."""

    def _ledger(self, root: Path) -> Path:
        return root / ".agent_state" / "orchestrate" / "feedback" / "demo.jsonl"

    def test_records_free_text_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            first = run_cli(
                root, "feedback", "record", "--task-id", "demo",
                "--note", "  the --authorized-sha   error was unclear ",
                "--source", "agent/demo/a",
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(
                json.loads(first.stdout)["recorded"],
                "the --authorized-sha error was unclear",
            )
            run_cli(
                root, "feedback", "record", "--task-id", "demo",
                "--note", "collect help confusing", "--source", "agent/demo/b",
            )
            rows = [
                json.loads(line)
                for line in self._ledger(root).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source"], "agent/demo/a")
            self.assertEqual(rows[1]["note"], "collect help confusing")

    def test_empty_note_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            result = run_cli(
                root, "feedback", "record", "--task-id", "demo", "--note", "   "
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-empty", result.stderr + result.stdout)
            self.assertFalse(self._ledger(root).exists())


if __name__ == "__main__":
    unittest.main()
