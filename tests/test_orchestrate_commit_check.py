from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests._orchestrate_cli_support import SCRIPT, VERIFIED_SKILL


class CommitCheckContractTests(unittest.TestCase):
    """Black-box Contract for the read-only whole-lane ``commit-check`` seam."""

    task_id = "check-task"
    lane_id = "lane-a"

    def git(self, cwd: Path, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
        )
        if check and result.returncode:
            self.fail(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--skill-dir", str(VERIFIED_SKILL), *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )

    def success(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload)
        return payload

    def completed_no(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"], payload)
        return payload

    def command_error(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(result.stdout, "")
        payload = json.loads(result.stderr)
        self.assertFalse(payload["ok"], payload)
        return payload

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git(self.root, "init", "-q", "-b", "main")
        self.git(self.root, "config", "user.name", "Commit Check Test")
        self.git(self.root, "config", "user.email", "check@example.test")
        (self.root / "README").write_text("base\n", encoding="utf-8")
        self.git(self.root, "add", "README")
        self.git(self.root, "commit", "-q", "-m", "base")
        self.base = self.git(self.root, "rev-parse", "HEAD")
        created = self.success(
            self.cli(
                "lane",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                self.lane_id,
                "--base",
                self.base,
            )
        )
        self.lane = Path(created["worktree"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def commit(self, path: str, content: str, message: str) -> str:
        target = self.lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(self.lane, "add", path)
        self.git(self.lane, "commit", "-q", "-m", message)
        return self.git(self.lane, "rev-parse", "HEAD")

    def check(self, sha: str) -> subprocess.CompletedProcess[str]:
        return self.cli(
            "commit-check",
            "--root",
            str(self.root),
            "--task-id",
            self.task_id,
            "--lane-id",
            self.lane_id,
            "--sha",
            sha,
        )

    def test_commit_check_projects_the_exact_first_parent_range_without_mutation(self) -> None:
        contract = self.commit(
            "tests/test_feature.py",
            "assert True\n",
            "contract\n\nImmutable: tests/test_feature.py",
        )
        tip = self.commit("src/feature.py", "VALUE = 1\n", "implement")
        before_status = self.git(self.lane, "status", "--porcelain")

        payload = self.success(self.check(tip))

        self.assertEqual(payload["operation"], "commit-check")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["task_id"], self.task_id)
        self.assertEqual(payload["lane_id"], self.lane_id)
        self.assertEqual(payload["base"], self.base)
        self.assertEqual(payload["sha"], tip)
        self.assertEqual([entry["sha"] for entry in payload["commits"]], [contract, tip])
        self.assertEqual(
            payload["commits"][0]["immutable"], ["tests/test_feature.py"]
        )
        self.assertEqual(payload["commits"][0]["changed_paths"], ["tests/test_feature.py"])
        self.assertEqual(payload["commits"][1]["changed_paths"], ["src/feature.py"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(self.git(self.lane, "rev-parse", "HEAD"), tip)
        self.assertEqual(self.git(self.lane, "status", "--porcelain"), before_status)

    def test_commit_check_refuses_a_range_without_one_valid_declaration(self) -> None:
        malformed = self.commit(
            "src/feature.py",
            "VALUE = 1\n",
            "implement\n\nImmutable:\nImmutable: ../outside.py",
        )
        before_status = self.git(self.lane, "status", "--porcelain")

        payload = self.completed_no(self.check(malformed))

        self.assertEqual(payload["operation"], "commit-check")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["sha"], malformed)
        self.assertEqual(payload["commits"][0]["immutable"], [])
        self.assertTrue(any("repo-relative" in error for error in payload["errors"]))
        self.assertTrue(
            any("no parsed Immutable declaration" in error for error in payload["errors"])
        )
        self.assertEqual(self.git(self.lane, "rev-parse", "HEAD"), malformed)
        self.assertEqual(self.git(self.lane, "status", "--porcelain"), before_status)

    def test_commit_check_refuses_a_later_undeclared_change(self) -> None:
        self.commit(
            "tests/test_feature.py",
            "assert True\n",
            "contract\n\nImmutable: tests/test_feature.py",
        )
        changed = self.commit(
            "tests/test_feature.py",
            "assert False\n",
            "weaken without redeclaring",
        )

        payload = self.completed_no(self.check(changed))

        self.assertTrue(
            any(
                changed in error and "tests/test_feature.py" in error
                for error in payload["errors"]
            )
        )
        self.assertEqual(payload["commits"][-1]["immutable"], [])
        self.assertEqual(
            payload["commits"][-1]["changed_paths"], ["tests/test_feature.py"]
        )

    def test_commit_check_rejects_a_stale_non_tip_sha_without_mutation(self) -> None:
        stale = self.commit(
            "tests/test_feature.py",
            "assert True\n",
            "contract\n\nImmutable: tests/test_feature.py",
        )
        tip = self.commit("src/feature.py", "VALUE = 1\n", "implement")
        before_status = self.git(self.lane, "status", "--porcelain")

        payload = self.command_error(self.check(stale))

        self.assertIn("tip", payload["error"]["message"])
        self.assertEqual(self.git(self.lane, "rev-parse", "HEAD"), tip)
        self.assertEqual(self.git(self.lane, "status", "--porcelain"), before_status)


if __name__ == "__main__":
    unittest.main()
