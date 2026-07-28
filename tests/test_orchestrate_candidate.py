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
SCRIPT = (
    ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"
)


class ReadyCandidateContractTests(unittest.TestCase):
    """Black-box Contract for the ready-candidate gating lifecycle.

    ``integration create`` builds both the integration worktree and a second,
    detached-HEAD acceptance worktree in one call.  ``integration candidate``
    only ever *checks out* that acceptance worktree to an exact, already
    gated SHA and then records the SHA in ``refs/orchestrate/<task>/candidate``
    -- in that order, so a dirty acceptance worktree (the user's own leftover
    test artifacts) can never be silently clobbered and a failed candidate call
    can never leave the candidate ref pointing at a SHA the worktree does not
    actually hold.  ``integration status`` projects the candidate purely from
    Git: no new persisted format is introduced.
    """

    task_id = "candidate-task"

    def git(
        self,
        cwd: Path,
        *args: str,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )
        if check and result.returncode:
            self.fail(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def cli(
        self, root: Path, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"success was not one JSON object: {result.stdout!r}: {exc}")
        self.assertIsInstance(value, dict)
        self.assertTrue(value.get("ok"), value)
        return value

    def error_payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "", result.stdout)
        try:
            value = json.loads(result.stderr)
        except json.JSONDecodeError as exc:
            self.fail(
                f"failure was not one JSON error object: {result.stderr!r}: {exc}"
            )
        self.assertIsInstance(value, dict)
        self.assertFalse(value.get("ok"), value)
        self.assertIsInstance(value.get("error"), dict)
        return value

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git(self.root, "init", "-q", "-b", "main")
        self.git(self.root, "config", "user.name", "Candidate Test")
        self.git(self.root, "config", "user.email", "candidate@example.test")
        (self.root / "app.txt").write_text("base\n", encoding="utf-8")
        self.git(self.root, "add", "app.txt")
        self.git(
            self.root,
            "commit",
            "-q",
            "-m",
            "base",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:00:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:00:00+0000",
            },
        )
        self.base = self.git(self.root, "rev-parse", "HEAD")
        self.integration_branch = f"wave/{self.task_id}/integration"
        self.candidate_ref = f"refs/orchestrate/{self.task_id}/candidate"
        self.acceptance_path = (
            self.root / ".agent_state" / "worktrees" / f"{self.task_id}-acceptance"
        )
        self.integration_path = (
            self.root / ".agent_state" / "worktrees" / f"{self.task_id}-integration"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def integration_create(self, base: str | None = None) -> dict[str, Any]:
        return self.payload(
            self.cli(
                self.root,
                "integration",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--base",
                base or self.base,
            )
        )

    def lane_create(self, lane_id: str, base: str) -> Path:
        payload = self.payload(
            self.cli(
                self.root,
                "lane",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                lane_id,
                "--base",
                base,
            )
        )
        return Path(str(payload["worktree"]))

    def commit_lane(
        self,
        worktree: Path,
        content: str,
        message: str = "implement",
        *,
        date: str = "2025-01-01T00:01:00+0000",
        path: str = "app.txt",
    ) -> str:
        (worktree / path).write_text(content, encoding="utf-8")
        self.git(worktree, "add", path)
        self.git(
            worktree,
            "commit",
            "-q",
            "-m",
            message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return self.git(worktree, "rev-parse", "HEAD")

    def collect(
        self, lane_id: str, sha: str, date: str = "2025-01-01T00:10:00+0000"
    ) -> dict[str, Any]:
        return self.payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                lane_id,
                "--sha",
                sha,
                env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
            )
        )

    def advance_integration(self, lane_id: str, content: str, date: str) -> str:
        """Collect one lane's commit into integration and return the collect SHA."""
        base_tip = self.git(self.root, "rev-parse", self.integration_branch)
        lane = self.lane_create(lane_id, base_tip)
        sha = self.commit_lane(lane, content, date=date)
        return self.collect(lane_id, sha, date=date)["collect_sha"]

    def candidate(self, sha: str) -> subprocess.CompletedProcess[str]:
        return self.cli(
            self.root,
            "integration",
            "candidate",
            "--root",
            str(self.root),
            "--task-id",
            self.task_id,
            "--sha",
            sha,
        )

    def status(self) -> dict[str, Any]:
        return self.payload(
            self.cli(
                self.root,
                "integration",
                "status",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
            )
        )

    # 1. integration create builds the acceptance worktree too, at --base.
    def test_integration_create_also_builds_the_acceptance_worktree(self) -> None:
        created = self.integration_create()
        self.assertTrue(self.acceptance_path.is_dir())
        self.assertEqual(self.git(self.acceptance_path, "rev-parse", "HEAD"), self.base)
        # It is a detached-HEAD worktree: no branch, so candidate can freely
        # checkout arbitrary gated SHAs without ever needing a fast-forward.
        symbolic = self.git(
            self.acceptance_path, "symbolic-ref", "-q", "HEAD", check=False
        )
        self.assertEqual(symbolic, "")
        self.assertEqual(created["operation"], "integration-create")

    # 2. candidate moves the ref and the acceptance worktree HEAD to --sha.
    def test_candidate_moves_ref_and_acceptance_head_to_sha(self) -> None:
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )

        gated = self.payload(self.candidate(target))

        self.assertEqual(gated["operation"], "integration-candidate")
        self.assertEqual(gated["sha"], target)
        self.assertEqual(self.git(self.root, "rev-parse", self.candidate_ref), target)
        self.assertEqual(self.git(self.acceptance_path, "rev-parse", "HEAD"), target)

        status = self.status()
        self.assertEqual(status["candidate"]["sha"], target)
        self.assertTrue(status["candidate"]["worktree_ready"])
        self.assertEqual(
            status["candidate"]["acceptance_worktree"], str(self.acceptance_path)
        )

    # 3. a dirty acceptance worktree refuses candidate: the ref keeps its old
    #    value and the worktree's own uncommitted content -- the user's own
    #    leftover test artifacts -- is left completely untouched.
    def test_candidate_refuses_a_dirty_acceptance_worktree_and_preserves_user_dirt(
        self,
    ) -> None:
        self.integration_create()
        first = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.payload(self.candidate(first))

        (self.acceptance_path / "user-notes.txt").write_text(
            "still testing\n", encoding="utf-8"
        )
        second = self.advance_integration(
            "lane-b", "lane a\nlane b\n", "2025-01-01T00:02:00+0000"
        )

        error = self.error_payload(self.candidate(second))
        self.assertIn("clean", str(error["error"]))

        # ref unchanged
        self.assertEqual(self.git(self.root, "rev-parse", self.candidate_ref), first)
        # worktree HEAD unchanged, and it was never checked out away from
        # under the user's dirt
        self.assertEqual(self.git(self.acceptance_path, "rev-parse", "HEAD"), first)
        self.assertEqual(
            (self.acceptance_path / "user-notes.txt").read_text(encoding="utf-8"),
            "still testing\n",
        )
        self.assertIn(
            "?? user-notes.txt", self.git(self.acceptance_path, "status", "--porcelain")
        )

    # 4. with no candidate gated yet, status reports candidate: null
    #    without erroring.
    def test_status_reports_null_candidate_without_error_when_none_gated(self) -> None:
        self.integration_create()
        status = self.status()
        self.assertIsNone(status["candidate"])

    # 5. behind_tip reflects how far the integration tip has moved past the
    #    gated candidate.
    def test_behind_tip_reflects_integration_tip_advancing_past_candidate(self) -> None:
        self.integration_create()
        first = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.payload(self.candidate(first))
        self.assertEqual(self.status()["candidate"]["behind_tip"], 0)

        # A --no-ff collect adds two new commits to the integration branch
        # (the lane's own commit plus the merge commit), independent of the
        # production formula: cross-check the cumulative count against the
        # sum of each collect's incremental contribution.
        after_b = self.advance_integration(
            "lane-b", "lane a\nlane b\n", "2025-01-01T00:02:00+0000"
        )
        incremental_b = int(
            self.git(self.root, "rev-list", "--count", f"{first}..{after_b}")
        )
        after_c = self.advance_integration(
            "lane-c", "lane a\nlane b\nlane c\n", "2025-01-01T00:03:00+0000"
        )
        incremental_c = int(
            self.git(self.root, "rev-list", "--count", f"{after_b}..{after_c}")
        )

        expected = incremental_b + incremental_c
        self.assertGreater(expected, 0)
        status = self.status()
        self.assertEqual(status["candidate"]["behind_tip"], expected)
        self.assertEqual(
            expected,
            int(
                self.git(
                    self.root,
                    "rev-list",
                    "--count",
                    f"{self.candidate_ref}..{self.integration_branch}",
                )
            ),
        )
        # the candidate sha itself has not moved; only the tip has, and the
        # acceptance worktree is still exactly where it was gated, so it
        # is still "ready" for that (now stale) candidate.
        self.assertEqual(status["candidate"]["sha"], first)
        self.assertTrue(status["candidate"]["worktree_ready"])

    # 6. remove tears down both worktrees and the candidate ref together.
    #    This task was never landed, so a plain remove refuses (S5.7); the
    #    deliberate throwaway case is exactly what --abandon is for.
    def test_remove_tears_down_both_worktrees_and_the_candidate_ref(self) -> None:
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.payload(self.candidate(target))

        removed = self.payload(
            self.cli(
                self.root,
                "integration",
                "remove",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--abandon",
            )
        )

        self.assertEqual(removed["operation"], "integration-remove")
        self.assertTrue(removed["abandoned"])
        self.assertIn(self.candidate_ref, removed["removed_refs"])
        self.assertFalse(self.integration_path.exists())
        self.assertFalse(self.acceptance_path.exists())
        ref_probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", self.candidate_ref],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(ref_probe.returncode, 0)


if __name__ == "__main__":
    unittest.main()
