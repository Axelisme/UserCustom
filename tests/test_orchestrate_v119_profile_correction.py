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


class ProfileReportContractHarness(unittest.TestCase):
    """Shared Git/CLI helpers for profile report Contract tests."""

    task_id = "profile-correction-task"
    wave_id = "profile-correction-wave"
    slice_id = "profile-correction-slice"

    def git(
        self, cwd: Path, *args: str, env: dict[str, str] | None = None
    ) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def cli(
        self, root: Path, *args: str, env: dict[str, str] | None = None
    ) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
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
        self,
        worktree: Path,
        relative_path: str,
        content: str,
        subject: str,
        role: str,
        date: str,
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
        self.git(
            worktree,
            "commit",
            "-q",
            "-m",
            message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return self.git(worktree, "rev-parse", "HEAD")

class ProfileCorrectionAttemptAssignmentContractTests(ProfileReportContractHarness):
    """Black-box Contract for assigning an Implementation to its Contract attempt."""

    def test_final_implementation_belongs_to_latest_preceding_contract_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.name", "Profile Contract Test")
            self.git(repo, "config", "user.email", "profile-contract@example.test")
            (repo / "README").write_text("base\n", encoding="utf-8")
            self.git(repo, "add", "README")
            self.git(
                repo,
                "commit",
                "-q",
                "-m",
                "base",
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:00:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:00:00+0000",
                },
            )
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
                "2025-01-01T00:01:00+0000",
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
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:02:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:02:00+0000",
                },
            )
            merge_1 = str(merge_1_payload["merge_sha"])

            retired_checkpoint = self.commit_file(
                implementation_worktree,
                "src/retired-checkpoint.txt",
                "not a v119 milestone\n",
                "Commit carrying the retired checkpoint role",
                "implementation-checkpoint",
                "2025-01-01T00:02:15+0000",
            )

            oracle_2 = self.commit_file(
                oracle_worktree,
                "tests/contract.txt",
                "attempt 2\n",
                "Oracle Contract correction attempt 2",
                "oracle",
                "2025-01-01T00:03:00+0000",
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
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:04:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:04:00+0000",
                },
            )
            merge_2 = str(merge_2_payload["merge_sha"])

            implementation_sha = self.commit_file(
                implementation_worktree,
                "src/implementation.txt",
                "ready after correction\n",
                "Implementation ready after Contract correction",
                "implementation",
                "2025-01-01T00:05:00+0000",
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
            slice_report = report["slices"][self.slice_id]
            rendered = json.dumps(report, sort_keys=True)
            self.assertNotIn(retired_checkpoint, rendered)
            self.assertNotIn("checkpoint", rendered)

            attempts = slice_report["attempts"]
            self.assertEqual(
                attempts,
                [
                    {
                        "attempt": 1,
                        "oracle_sha": oracle_1,
                        "contract_merge_sha": merge_1,
                        "implementation_sha": None,
                        "oracle_interval_seconds": None,
                        "handoff_interval_seconds": 60,
                        "implementation_interval_seconds": None,
                    },
                    {
                        "attempt": 2,
                        "oracle_sha": oracle_2,
                        "contract_merge_sha": merge_2,
                        "implementation_sha": implementation_sha,
                        "oracle_interval_seconds": 120,
                        "handoff_interval_seconds": 60,
                        "implementation_interval_seconds": 60,
                    },
                ],
            )
            self.assertEqual(slice_report["oracle_interval_seconds"], 120)
            self.assertEqual(slice_report["handoff_interval_seconds"], 60)
            self.assertEqual(slice_report["implementation_interval_seconds"], 60)


class ProfileInterleavedSliceContractTests(ProfileReportContractHarness):
    """Endpoints keep their Slice attempt when another Slice merges in between."""

    def commit_empty(self, worktree: Path, slice_id: str, subject: str, date: str) -> str:
        message = (
            f"{subject}\n\n"
            f"Wave: {self.wave_id}\n"
            f"Slice: {slice_id}\n"
            f"Role: implementation"
        )
        self.git(
            worktree,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return self.git(worktree, "rev-parse", "HEAD")

    def test_interleaved_slice_merges_keep_each_implementation_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.name", "Profile Contract Test")
            self.git(repo, "config", "user.email", "profile-contract@example.test")
            (repo / "README").write_text("base\n", encoding="utf-8")
            self.git(
                repo,
                "add",
                "README",
            )
            self.git(
                repo,
                "commit",
                "-q",
                "-m",
                "base",
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:00:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:00:00+0000",
                },
            )
            base = self.git(repo, "rev-parse", "HEAD")
            implementation = self.cli(
                repo, "worktree", "create", "--root", str(repo),
                "--task-id", self.task_id, "--wave-id", self.wave_id,
                "--role", "implementation", "--base", base,
            )
            oracle = self.cli(
                repo, "worktree", "create", "--root", str(repo),
                "--task-id", self.task_id, "--wave-id", self.wave_id,
                "--role", "oracle", "--base", base,
            )
            implementation_worktree = Path(str(implementation["worktree"]))
            oracle_worktree = Path(str(oracle["worktree"]))

            # Slice A and Slice B each merge a Contract before either
            # Implementation lands, so Slice A's endpoint sits inside Slice
            # B's global merge window.
            self.slice_id = "slice-a"
            oracle_a = self.commit_file(
                oracle_worktree, "tests/a.txt", "contract a\n",
                "Oracle A", "oracle", "2025-01-01T00:01:00+0000",
            )
            merge_a = str(self.cli(
                repo, "contract", "merge", "--root", str(repo),
                "--task-id", self.task_id, "--wave-id", self.wave_id,
                "--contract-sha", oracle_a,
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:02:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:02:00+0000",
                },
            )["merge_sha"])
            self.slice_id = "slice-b"
            oracle_b = self.commit_file(
                oracle_worktree, "tests/b.txt", "contract b\n",
                "Oracle B", "oracle", "2025-01-01T00:03:00+0000",
            )
            merge_b = str(self.cli(
                repo, "contract", "merge", "--root", str(repo),
                "--task-id", self.task_id, "--wave-id", self.wave_id,
                "--contract-sha", oracle_b,
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:04:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:04:00+0000",
                },
            )["merge_sha"])

            # Slice A hands off with an --allow-empty commit: a legal exact
            # consumption marker after a non-behavioral Contract correction.
            implementation_a = self.commit_empty(
                implementation_worktree, "slice-a",
                "Empty Implementation handoff A", "2025-01-01T00:05:00+0000",
            )
            self.slice_id = "slice-b"
            implementation_b = self.commit_file(
                implementation_worktree, "src/b.txt", "ready b\n",
                "Implementation B", "implementation", "2025-01-01T00:06:00+0000",
            )

            report = self.cli(
                repo, "profile", "report", "--root", str(repo),
                "--task-id", self.task_id, "--wave-id", self.wave_id,
                "--base", base,
            )
            slice_a = report["slices"]["slice-a"]["attempts"]
            slice_b = report["slices"]["slice-b"]["attempts"]
            self.assertEqual(slice_a[-1]["contract_merge_sha"], merge_a)
            self.assertEqual(slice_a[-1]["implementation_sha"], implementation_a)
            self.assertEqual(slice_b[-1]["contract_merge_sha"], merge_b)
            self.assertEqual(slice_b[-1]["implementation_sha"], implementation_b)


class ProfileUnattributedEndpointContractTests(ProfileReportContractHarness):
    """A handoff recorded before any Contract merge must not vanish silently."""

    def test_endpoint_before_every_contract_merge_is_reported_as_unattributed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.name", "Profile Contract Test")
            self.git(repo, "config", "user.email", "profile-contract@example.test")
            (repo / "README").write_text("base\n", encoding="utf-8")
            self.git(repo, "add", "README")
            self.git(
                repo,
                "commit",
                "-q",
                "-m",
                "base",
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:00:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:00:00+0000",
                },
            )
            base = self.git(repo, "rev-parse", "HEAD")
            worktrees = {
                role: Path(
                    str(
                        self.cli(
                            repo, "worktree", "create", "--root", str(repo),
                            "--task-id", self.task_id, "--wave-id", self.wave_id,
                            "--role", role, "--base", base,
                        )["worktree"]
                    )
                )
                for role in ("oracle", "implementation")
            }

            misplaced = self.commit_file(
                worktrees["implementation"],
                "src/early.txt",
                "handoff before any Contract merge\n",
                "Implementation handoff recorded too early",
                "implementation",
                "2025-01-01T00:01:00+0000",
            )
            oracle_sha = self.commit_file(
                worktrees["oracle"],
                "tests/contract.txt",
                "attempt 1\n",
                "Oracle Contract attempt 1",
                "oracle",
                "2025-01-01T00:02:00+0000",
            )
            self.cli(
                repo, "contract", "merge", "--root", str(repo),
                "--task-id", self.task_id, "--wave-id", self.wave_id,
                "--contract-sha", oracle_sha,
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:03:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:03:00+0000",
                },
            )

            report = self.cli(
                repo, "profile", "report", "--root", str(repo),
                "--task-id", self.task_id, "--wave-id", self.wave_id,
                "--base", base,
            )
            attempts = report["slices"][self.slice_id]["attempts"]
            self.assertEqual(attempts[-1]["implementation_sha"], None)
            self.assertTrue(
                any(
                    misplaced in warning and "unattributed" in warning
                    for warning in report["warnings"]
                ),
                report["warnings"],
            )


if __name__ == "__main__":
    unittest.main()
