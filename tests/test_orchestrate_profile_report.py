from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


class ProfileReportContractHarness(unittest.TestCase):
    """Shared Git/CLI helpers for profile report Contract tests.

    ``profile report`` is unaffected by the lane model (it is retired in a
    later Slice, not this one) and still walks the Oracle/Implementation role
    branches and Contract-merge commits it always has.  The lane model no
    longer ships a CLI command that creates a role worktree or merges a
    Contract, so these fixtures build the identical commit graph with raw Git
    plumbing instead of the retired ``worktree create --role`` / ``contract
    merge`` commands.
    """

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
    ) -> dict[str, Any]:
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

    def create_role_worktree(
        self, repo: Path, base: str, task_id: str, wave_id: str, role: str
    ) -> Path:
        """Stand in for the retired ``worktree create --role`` command.

        Real ``git worktree add`` gives profile report an identical
        ``wave/<task>/<wave>/<role>`` branch to walk, just without going
        through the lane-model CLI that no longer creates role worktrees.
        """
        branch = f"wave/{task_id}/{wave_id}/{role}"
        path = repo / ".agent_state" / "worktrees" / f"{task_id}-{wave_id}-{role}"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.git(repo, "worktree", "add", "-b", branch, str(path), base)
        return path

    def merge_contract_raw(
        self,
        implementation_worktree: Path,
        wave_id: str,
        slice_id: str,
        contract_sha: str,
        date: str,
    ) -> str:
        """Stand in for the retired ``contract merge`` command."""
        self.git(implementation_worktree, "merge", "--no-ff", "--no-commit", contract_sha)
        message = f"Merge Contract {contract_sha}\n\nWave: {wave_id}\nSlice: {slice_id}\nRole: merge"
        self.git(
            implementation_worktree,
            "commit",
            "-q",
            "-m",
            message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return self.git(implementation_worktree, "rev-parse", "HEAD")

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

            implementation_worktree = self.create_role_worktree(
                repo, base, self.task_id, self.wave_id, "implementation"
            )
            oracle_worktree = self.create_role_worktree(
                repo, base, self.task_id, self.wave_id, "oracle"
            )

            oracle_1 = self.commit_file(
                oracle_worktree,
                "tests/contract.txt",
                "attempt 1\n",
                "Oracle Contract attempt 1",
                "oracle",
                "2025-01-01T00:01:00+0000",
            )
            merge_1 = self.merge_contract_raw(
                implementation_worktree,
                self.wave_id,
                self.slice_id,
                oracle_1,
                "2025-01-01T00:02:00+0000",
            )

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
            merge_2 = self.merge_contract_raw(
                implementation_worktree,
                self.wave_id,
                self.slice_id,
                oracle_2,
                "2025-01-01T00:04:00+0000",
            )

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
            implementation_worktree = self.create_role_worktree(
                repo, base, self.task_id, self.wave_id, "implementation"
            )
            oracle_worktree = self.create_role_worktree(
                repo, base, self.task_id, self.wave_id, "oracle"
            )

            # Slice A and Slice B each merge a Contract before either
            # Implementation lands, so Slice A's endpoint sits inside Slice
            # B's global merge window.
            self.slice_id = "slice-a"
            oracle_a = self.commit_file(
                oracle_worktree, "tests/a.txt", "contract a\n",
                "Oracle A", "oracle", "2025-01-01T00:01:00+0000",
            )
            merge_a = self.merge_contract_raw(
                implementation_worktree, self.wave_id, "slice-a", oracle_a,
                "2025-01-01T00:02:00+0000",
            )
            self.slice_id = "slice-b"
            oracle_b = self.commit_file(
                oracle_worktree, "tests/b.txt", "contract b\n",
                "Oracle B", "oracle", "2025-01-01T00:03:00+0000",
            )
            merge_b = self.merge_contract_raw(
                implementation_worktree, self.wave_id, "slice-b", oracle_b,
                "2025-01-01T00:04:00+0000",
            )

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
                role: self.create_role_worktree(repo, base, self.task_id, self.wave_id, role)
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
            self.merge_contract_raw(
                worktrees["implementation"], self.wave_id, self.slice_id, oracle_sha,
                "2025-01-01T00:03:00+0000",
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


class ProfileRangeNumstatContractTests(unittest.TestCase):
    """Black-box Contract for topology-assigned Git range accounting."""

    task_id = "final-review-profile"
    wave_id = "owp04"
    slice_id = "range-accounting"

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
    ) -> dict[str, Any]:
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
            self.fail(f"CLI did not return one JSON object: {result.stdout!r}: {exc}")
        self.assertTrue(payload.get("ok"), payload)
        return payload

    def create_role_worktree(self, repo: Path, base: str, role: str) -> Path:
        branch = f"wave/{self.task_id}/{self.wave_id}/{role}"
        path = repo / ".agent_state" / "worktrees" / f"{self.task_id}-{self.wave_id}-{role}"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.git(repo, "worktree", "add", "-b", branch, str(path), base)
        return path

    def commit(
        self,
        worktree: Path,
        relative: str,
        content: str,
        subject: str,
        date: str,
        role: str | None = None,
        slice_id: str | None = None,
    ) -> str:
        target = worktree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(worktree, "add", relative)
        message = subject
        if role is not None:
            message += (
                f"\n\nWave: {self.wave_id}\n"
                f"Slice: {slice_id or self.slice_id}\n"
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

    def merge_contract(
        self, implementation_worktree: Path, slice_id: str, oracle_sha: str, date: str
    ) -> str:
        self.git(implementation_worktree, "merge", "--no-ff", "--no-commit", oracle_sha)
        message = f"Merge Contract {oracle_sha}\n\nWave: {self.wave_id}\nSlice: {slice_id}\nRole: merge"
        self.git(
            implementation_worktree,
            "commit",
            "-q",
            "-m",
            message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return self.git(implementation_worktree, "rev-parse", "HEAD")

    def test_report_counts_each_complete_attempt_range_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.name", "Range Contract Test")
            self.git(repo, "config", "user.email", "range-contract@example.test")
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

            implementation = self.create_role_worktree(repo, base, "implementation")
            oracle = self.create_role_worktree(repo, base, "oracle")

            # Attempt 1: both ready commits have untrailed work immediately before them.
            self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\n",
                "untrailed Contract draft 1",
                "2025-01-01T00:01:00+0000",
            )
            oracle_1 = self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\n",
                "Contract ready 1",
                "2025-01-01T00:02:00+0000",
                "oracle",
            )
            merge_1 = self.merge_contract(implementation, self.slice_id, oracle_1, "2025-01-01T00:03:00+0000")
            self.commit(
                implementation,
                "src/attempt_1.txt",
                "draft\n",
                "untrailed Implementation draft 1",
                "2025-01-01T00:04:00+0000",
            )
            implementation_1 = self.commit(
                implementation,
                "src/attempt_1.txt",
                "draft\nready\n",
                "Implementation ready 1",
                "2025-01-01T00:05:00+0000",
                "implementation",
            )

            # Attempt 2 has no ready Implementation, so it contributes no endpoint
            # and no Implementation numstat at all.
            self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\nattempt 2 draft\n",
                "untrailed Contract draft 2",
                "2025-01-01T00:06:00+0000",
            )
            oracle_2 = self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\nattempt 2 draft\nattempt 2 ready\n",
                "Contract ready 2",
                "2025-01-01T00:07:00+0000",
                "oracle",
            )
            merge_2 = self.merge_contract(implementation, self.slice_id, oracle_2, "2025-01-01T00:08:00+0000")
            self.commit(
                implementation,
                "src/attempt_2.txt",
                "draft\n",
                "untrailed blocked Implementation work",
                "2025-01-01T00:09:00+0000",
            )

            # Attempt 3 has untrailed work followed by a ready commit. The complete
            # merge-to-ready net range is counted exactly once, not per commit.
            self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\nattempt 2 draft\nattempt 2 ready\nattempt 3 draft\n",
                "untrailed Contract draft 3",
                "2025-01-01T00:11:00+0000",
            )
            oracle_3 = self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\nattempt 2 draft\nattempt 2 ready\nattempt 3 draft\nattempt 3 ready\n",
                "Contract ready 3",
                "2025-01-01T00:12:00+0000",
                "oracle",
            )
            merge_3 = self.merge_contract(implementation, self.slice_id, oracle_3, "2025-01-01T00:13:00+0000")
            self.commit(
                implementation,
                "src/attempt_3.txt",
                "draft\n",
                "untrailed Implementation draft 3",
                "2025-01-01T00:15:00+0000",
            )
            implementation_3 = self.commit(
                implementation,
                "src/attempt_3.txt",
                "draft\nready\n",
                "Implementation ready 3",
                "2025-01-01T00:16:00+0000",
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
            self.assertEqual(report["warnings"], [])
            slice_report = report["slices"][self.slice_id]
            self.assertEqual(
                [
                    (
                        attempt["oracle_sha"],
                        attempt["contract_merge_sha"],
                        attempt["implementation_sha"],
                    )
                    for attempt in slice_report["attempts"]
                ],
                [
                    (oracle_1, merge_1, implementation_1),
                    (oracle_2, merge_2, None),
                    (oracle_3, merge_3, implementation_3),
                ],
            )
            for attempt in slice_report["attempts"]:
                self.assertTrue(
                    {
                        "attempt",
                        "oracle_interval_seconds",
                        "handoff_interval_seconds",
                        "implementation_interval_seconds",
                    }
                    <= set(attempt),
                    attempt,
                )
            self.assertEqual(
                slice_report["contract_numstat"],
                {"files": 3, "insertions": 6, "deletions": 0},
            )
            self.assertEqual(
                slice_report["implementation_numstat"],
                {"files": 2, "insertions": 4, "deletions": 0},
                "the endpointless attempt 2 must contribute nothing",
            )
            self.assertEqual(
                report["wave"]["contract_numstat"],
                slice_report["contract_numstat"],
            )
            self.assertEqual(
                report["wave"]["implementation_numstat"],
                slice_report["implementation_numstat"],
            )

    def test_report_isolates_ranges_across_slices_in_one_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.name", "Multi-Slice Contract Test")
            self.git(repo, "config", "user.email", "multi-slice@example.test")
            (repo / "README").write_text("base\n", encoding="utf-8")
            self.git(repo, "add", "README")
            self.git(
                repo,
                "commit",
                "-q",
                "-m",
                "base",
                env={
                    "GIT_AUTHOR_DATE": "2025-02-01T00:00:00+0000",
                    "GIT_COMMITTER_DATE": "2025-02-01T00:00:00+0000",
                },
            )
            base = self.git(repo, "rev-parse", "HEAD")

            implementation = self.create_role_worktree(repo, base, "implementation")
            oracle = self.create_role_worktree(repo, base, "oracle")

            # Slice A publishes a two-commit Contract range and is merged first.
            self.commit(
                oracle,
                "tests/slice_a_contract.txt",
                "A draft\n",
                "untrailed Slice A Contract work",
                "2025-02-01T00:01:00+0000",
            )
            oracle_a = self.commit(
                oracle,
                "tests/slice_a_contract.txt",
                "A ready one\nA ready two\n",
                "Slice A Contract ready",
                "2025-02-01T00:02:00+0000",
                "oracle",
                slice_id="slice-a",
            )
            merge_a = self.merge_contract(implementation, "slice-a", oracle_a, "2025-02-01T00:03:00+0000")

            # Slice B continues the Oracle topology. Its Contract range starts at
            # Oracle A, never at the report base, and is merged after A.
            self.commit(
                oracle,
                "tests/slice_b_contract.txt",
                "B draft\n",
                "untrailed Slice B Contract work",
                "2025-02-01T00:04:00+0000",
            )
            oracle_b = self.commit(
                oracle,
                "tests/slice_b_contract.txt",
                "B ready one\nB ready two\n",
                "Slice B Contract ready",
                "2025-02-01T00:05:00+0000",
                "oracle",
                slice_id="slice-b",
            )
            merge_b = self.merge_contract(implementation, "slice-b", oracle_b, "2025-02-01T00:06:00+0000")

            # A deliberately has no endpoint before merge B. Only B owns the
            # complete merge-B-to-ready range, including its untrailed work.
            self.commit(
                implementation,
                "src/slice_b.py",
                "draft = True\n",
                "untrailed Slice B Implementation work",
                "2025-02-01T00:07:00+0000",
            )
            implementation_b_sha = self.commit(
                implementation,
                "src/slice_b.py",
                "draft = True\nready = True\n",
                "Slice B Implementation ready",
                "2025-02-01T00:08:00+0000",
                "implementation",
                slice_id="slice-b",
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
            self.assertEqual(report["warnings"], [])
            slice_a = report["slices"]["slice-a"]
            slice_b = report["slices"]["slice-b"]

            self.assertEqual(
                [
                    (
                        attempt["oracle_sha"],
                        attempt["contract_merge_sha"],
                        attempt["implementation_sha"],
                    )
                    for attempt in slice_a["attempts"]
                ],
                [(oracle_a, merge_a, None)],
            )
            self.assertEqual(
                [
                    (
                        attempt["oracle_sha"],
                        attempt["contract_merge_sha"],
                        attempt["implementation_sha"],
                    )
                    for attempt in slice_b["attempts"]
                ],
                [(oracle_b, merge_b, implementation_b_sha)],
            )
            contract_a = {"files": 1, "insertions": 2, "deletions": 0}
            contract_b = {"files": 1, "insertions": 2, "deletions": 0}
            implementation_a = {"files": 0, "insertions": 0, "deletions": 0}
            implementation_b = {"files": 1, "insertions": 2, "deletions": 0}
            self.assertEqual(
                slice_b["contract_numstat"],
                contract_b,
                "Slice B must exclude Slice A's base-to-Oracle Contract range",
            )
            self.assertEqual(slice_a["contract_numstat"], contract_a)
            self.assertEqual(
                slice_a["implementation_numstat"],
                implementation_a,
                "Slice A must stop at merge B rather than claim B's range",
            )
            self.assertEqual(
                slice_b["implementation_numstat"],
                implementation_b,
                "Slice B must own its complete merge-to-ready range",
            )

            for metric in ("contract_numstat", "implementation_numstat"):
                isolated_total = {
                    key: slice_a[metric][key] + slice_b[metric][key]
                    for key in ("files", "insertions", "deletions")
                }
                self.assertEqual(
                    report["wave"][metric],
                    isolated_total,
                    f"Wave {metric} must sum isolated Slice ranges exactly once",
                )


if __name__ == "__main__":
    unittest.main()
