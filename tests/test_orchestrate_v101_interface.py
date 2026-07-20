from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


def cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
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


def init_repo(root: Path) -> str:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "V101")
    git(root, "config", "user.email", "v101@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")
    return git(root, "rev-parse", "HEAD")


class SpellingUnificationTests(unittest.TestCase):
    """v101: one concept, one spelling — with the old spelling still accepted so a
    task in flight is never broken by the rename."""

    def test_collect_keeps_integration_worktree_and_never_gains_root(self) -> None:
        # Not a synonym to unify: collect derives task identity from *this* checkout's
        # branch, so the flag must name which checkout it is. A generic --root would
        # invite passing any repo root, so the distinction is load-bearing.
        result = cli("collect", "--help")
        self.assertIn("--integration-worktree", result.stdout)
        self.assertNotIn("--root", result.stdout)

    def test_subject_sha_and_subject_are_the_same_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            for flag in ("--subject", "--subject-sha"):
                result = cli(
                    "review", "audit", "--root", str(root), "--base", base, flag, base
                )
                combined = result.stderr + result.stdout
                self.assertNotIn("unrecognized arguments", combined, flag)

    def test_task_id_accepts_both_bare_id_and_task_ref_form(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            receipt = root / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "subject_sha": git(root, "rev-parse", "HEAD"),
                        "verdict": "pass",
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            recorded = cli(
                "findings",
                "record",
                "--root",
                str(root),
                "--task-id",
                "task/demo",
                "--receipt",
                str(receipt),
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            self.assertEqual(json.loads(recorded.stdout)["task_id"], "demo")
            # The bare id reads the very same ledger.
            status = cli("findings", "status", "--root", str(root), "--task-id", "demo")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertTrue(json.loads(status.stdout)["reviewed_clean"])


if __name__ == "__main__":
    unittest.main()
