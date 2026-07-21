from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


def run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--root", str(root)],
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


def init_repo(root: Path) -> None:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "V107")
    git(root, "config", "user.email", "v107@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")


def commit(root: Path, name: str) -> str:
    (root / name).write_text(name, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", name)
    return git(root, "rev-parse", "HEAD")


def record_pass(root: Path, subject: str) -> None:
    receipt = root / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "subject_sha": subject,
                "verdict": "pass",
                "evidence": ["test receipt"],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    result = run_cli(
        root, "findings", "record", "--task-id", "demo", "--receipt", str(receipt)
    )
    assert result.returncode == 0, result.stderr


def wave_handoff(root: Path) -> dict:
    result = run_cli(root, "wave", "status", "--task-ref", "task/demo")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["handoff"]


class ValidatedUnlandedTests(unittest.TestCase):
    """v107: `wave status` splits the reviewed-but-not-yet-landed SHAs out of
    reviewed_clean as `validated_unlanded` — the resumable set a restart or a
    tool-permission-blocked collect should pick up without a second review."""

    def test_passed_but_unlanded_subject_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            # A commit that passed review but is not on task/demo.
            c1 = commit(root, "c1.txt")
            record_pass(root, c1)
            handoff = wave_handoff(root)
            self.assertIn(c1, handoff["reviewed_clean"])
            self.assertEqual(handoff["validated_unlanded"], [c1])

    def test_landed_subject_drops_out_of_validated_unlanded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            c1 = commit(root, "c1.txt")
            record_pass(root, c1)
            # c1 lands on the task branch; a later c2 passes but stays unlanded.
            git(root, "branch", "-f", "task/demo", c1)
            c2 = commit(root, "c2.txt")
            record_pass(root, c2)
            handoff = wave_handoff(root)
            self.assertEqual(
                sorted(handoff["reviewed_clean"]), sorted([c1, c2])
            )
            # c1 is now an ancestor of task/demo; only c2 remains resumable.
            self.assertEqual(handoff["validated_unlanded"], [c2])

    def test_all_landed_leaves_validated_unlanded_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            c1 = commit(root, "c1.txt")
            record_pass(root, c1)
            git(root, "branch", "-f", "task/demo", c1)
            handoff = wave_handoff(root)
            self.assertEqual(handoff["reviewed_clean"], [c1])
            self.assertEqual(handoff["validated_unlanded"], [])


if __name__ == "__main__":
    unittest.main()
