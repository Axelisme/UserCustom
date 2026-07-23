from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


class ProfileCorrectionAttemptAssignmentContractTests(unittest.TestCase):
    """Black-box Contract for assigning an Implementation to its Contract attempt."""

    task_id = "profile-correction-task"
    wave_id = "profile-correction-wave"
    slice_id = "profile-correction-slice"

    def git(self, cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def cli(self, root: Path, *args: str) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"CLI success was not one JSON object: {result.stdout!r}: {exc}")
        self.assertIsInstance(payload, dict)
        self.assertTrue(payload.get("ok"), payload)
        return payload

    def commit_file(
        self, worktree: Path, relative_path: str, content: str, subject: str, role: str
    ) -> str:
        target = worktree / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(worktree, "add", relative_path)
        message = (
            f"{subject}\n\n"
            f"Wave: {self.wave_id}\n"
            f"Slice: {self.slice_id}\n"
            f"Role: {role}"
        )
        self.git(worktree, "commit", "-q", "-m", message)
        return self.git(worktree, "rev-parse", "HEAD")

    def test_final_implementation_belongs_to_latest_preceding_contract_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.name", "Profile Contract Test")
            self.git(repo, "config", "user.email", "profile-contract@example.test")
            (repo / "README").write_text("base\n", encoding="utf-8")
            self.git(repo, "add", "README")
            self.git(repo, "commit", "-q", "-m", "base")
            base = self.git(repo, "rev-parse", "HEAD")

            implementation = self.cli(
                repo,
                "worktree",
                "create",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--role",
                "implementation",
                "--base",
                base,
            )
            oracle = self.cli(
                repo,
                "worktree",
                "create",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--role",
                "oracle",
                "--base",
                base,
            )
            implementation_worktree = Path(str(implementation["worktree"]))
            oracle_worktree = Path(str(oracle["worktree"]))

            oracle_1 = self.commit_file(
                oracle_worktree,
                "tests/contract.txt",
                "attempt 1\n",
                "Oracle Contract attempt 1",
                "oracle",
            )
            merge_1_payload = self.cli(
                repo,
                "contract",
                "merge",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--contract-sha",
                oracle_1,
            )
            merge_1 = str(merge_1_payload["merge_sha"])

            oracle_2 = self.commit_file(
                oracle_worktree,
                "tests/contract.txt",
                "attempt 2\n",
                "Oracle Contract correction attempt 2",
                "oracle",
            )
            merge_2_payload = self.cli(
                repo,
                "contract",
                "merge",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--contract-sha",
                oracle_2,
            )
            merge_2 = str(merge_2_payload["merge_sha"])

            implementation_sha = self.commit_file(
                implementation_worktree,
                "src/implementation.txt",
                "ready after correction\n",
                "Implementation ready after Contract correction",
                "implementation",
            )

            report = self.cli(
                repo,
                "profile",
                "report",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--base",
                base,
            )

            self.assertEqual(report["operation"], "profile-report")
            self.assertEqual(report["task_id"], self.task_id)
            self.assertEqual(report["wave_id"], self.wave_id)
            self.assertEqual(report["base"], base)
            attempts = report["slices"][self.slice_id]["attempts"]
            self.assertEqual(
                attempts,
                [
                    {
                        "attempt": 1,
                        "oracle_sha": oracle_1,
                        "contract_merge_sha": merge_1,
                        "implementation_sha": None,
                    },
                    {
                        "attempt": 2,
                        "oracle_sha": oracle_2,
                        "contract_merge_sha": merge_2,
                        "implementation_sha": implementation_sha,
                    },
                ],
            )


if __name__ == "__main__":
    unittest.main()
