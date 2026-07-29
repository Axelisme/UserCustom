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

ROOT = Path(__file__).resolve().parents[1]


class IntegrationLandContractTests(unittest.TestCase):
    """Black-box Contract for ``integration land``.

    Reuses the same real-temp-repo fixture shape as
    ``test_orchestrate_candidate.py``: an integration branch, an acceptance
    worktree, and a published candidate.  On top of that this file adds a
    local persistence branch checked out in its own worktree, since landing
    only ever squashes the ready candidate onto that branch -- there is
    deliberately no ``--target``.
    """

    task_id = "land-task"

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
            [sys.executable, str(SCRIPT), "--skill-dir", str(VERIFIED_SKILL), *args],
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
        self.git(self.root, "config", "user.name", "Land Test")
        self.git(self.root, "config", "user.email", "land@example.test")
        (self.root / "app.txt").write_text("base\n", encoding="utf-8")
        # a second tracked file lanes never touch, so a persist-worktree
        # modification to it can never collide with a landed squash diff.
        (self.root / "user-tracked.txt").write_text("tracked v1\n", encoding="utf-8")
        self.git(self.root, "add", "app.txt", "user-tracked.txt")
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
        self.persist_branch = "persist/main"
        self.persist_worktrees_dir = tempfile.TemporaryDirectory()
        self.persist_path = Path(self.persist_worktrees_dir.name) / "persist-wt"

    def tearDown(self) -> None:
        self.persist_worktrees_dir.cleanup()
        self.temporary.cleanup()

    # -- fixture helpers, mirroring test_orchestrate_candidate.py -----------

    def integration_create(
        self, base: str | None = None, *, task_id: str | None = None
    ) -> dict[str, Any]:
        return self.payload(
            self.cli(
                self.root,
                "integration",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                task_id or self.task_id,
                "--base",
                base or self.base,
            )
        )

    def lane_create(
        self, lane_id: str, base: str, *, task_id: str | None = None
    ) -> Path:
        payload = self.payload(
            self.cli(
                self.root,
                "lane",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                task_id or self.task_id,
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
        if "Immutable:" not in message:
            message = f"{message}\n\nImmutable: .orchestrate-test-contract"
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
        self,
        lane_id: str,
        sha: str,
        date: str = "2025-01-01T00:10:00+0000",
        *,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        return self.payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                task_id or self.task_id,
                "--lane-id",
                lane_id,
                "--sha",
                sha,
                env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
            )
        )

    def advance_integration(
        self,
        lane_id: str,
        content: str,
        date: str,
        *,
        path: str = "app.txt",
        task_id: str | None = None,
    ) -> str:
        """Collect one lane's commit into integration and return the collect SHA."""
        integration_branch = f"wave/{task_id or self.task_id}/integration"
        base_tip = self.git(self.root, "rev-parse", integration_branch)
        lane = self.lane_create(lane_id, base_tip, task_id=task_id)
        sha = self.commit_lane(lane, content, date=date, path=path)
        return self.collect(lane_id, sha, date=date, task_id=task_id)["collect_sha"]

    def candidate(self, sha: str, *, task_id: str | None = None) -> dict[str, Any]:
        return self.payload(
            self.cli(
                self.root,
                "integration",
                "candidate",
                "--root",
                str(self.root),
                "--task-id",
                task_id or self.task_id,
                "--sha",
                sha,
            )
        )

    def checkout_persist(self, base: str | None = None) -> None:
        """Create the local persistence branch and check it out in its own worktree."""
        self.git(self.root, "branch", self.persist_branch, base or self.base)
        self.git(
            self.root, "worktree", "add", str(self.persist_path), self.persist_branch
        )

    def land(
        self,
        *,
        persist: str | None = None,
        final: bool = False,
        message: str | None = None,
        task_id: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "integration",
            "land",
            "--root",
            str(self.root),
            "--task-id",
            task_id or self.task_id,
            "--persist",
            persist or self.persist_branch,
        ]
        if final:
            args.append("--final")
        if message is not None:
            args.extend(["--message", message])
        return self.cli(self.root, *args)

    def trailers(self, cwd: Path, sha: str = "HEAD") -> dict[str, str]:
        raw = self.git(cwd, "show", "-s", "--format=%(trailers:only,unfold)", sha)
        values: dict[str, str] = {}
        for line in raw.splitlines():
            key, _, value = line.partition(":")
            if key:
                values[key.strip()] = value.strip()
        return values

    # -- behaviours -----------------------------------------------------

    def test_happy_path_lands_one_squash_commit_with_task_and_landed_trailers(
        self,
    ) -> None:
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(target)
        self.checkout_persist()
        before_persist_tip = self.git(self.persist_path, "rev-parse", "HEAD")

        landed = self.payload(self.land())

        self.assertEqual(landed["operation"], "integration-land")
        self.assertEqual(landed["candidate"], target)
        self.assertEqual(landed["previous_persist_tip"], before_persist_tip)
        self.assertEqual(
            self.git(self.persist_path, "rev-parse", "HEAD^{tree}"),
            self.git(self.root, "rev-parse", f"{target}^{{tree}}"),
        )
        # exactly one new commit landed on persist
        self.assertEqual(
            int(
                self.git(
                    self.persist_path,
                    "rev-list",
                    "--count",
                    f"{before_persist_tip}..HEAD",
                )
            ),
            1,
        )
        trailers = self.trailers(self.persist_path)
        self.assertEqual(trailers.get("Task"), self.task_id)
        self.assertEqual(trailers.get("Landed"), target)

    def test_partial_then_final_land_two_candidates(self) -> None:
        self.integration_create()
        first = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(first)
        self.checkout_persist()
        origin_tip = self.git(self.persist_path, "rev-parse", "HEAD")

        self.payload(self.land())

        # lane-b edits the very same line of app.txt lane-a already touched.
        # This is the realistic case, not an edge case: a repair lane almost
        # always lands back on code an earlier lane just changed. Landing
        # uses a direct two-tree application (`read-tree -m <old> <new>`),
        # not a history-based three-way merge, so there is no merge-base to
        # spuriously collapse to the pre-partial-landing fork point and no
        # overlapping hunk to conflict on -- precondition 5's anchor rule
        # already proved nothing has actually diverged.
        second = self.advance_integration(
            "lane-b", "lane a and b\n", "2025-01-01T00:02:00+0000"
        )
        self.candidate(second)
        tip = self.git(self.root, "rev-parse", self.integration_branch)
        self.assertEqual(second, tip)

        landed = self.payload(self.land(final=True))

        self.assertTrue(landed["final"])
        self.assertEqual(
            self.git(self.persist_path, "rev-parse", "HEAD^{tree}"),
            self.git(self.root, "rev-parse", f"{second}^{{tree}}"),
        )
        self.assertEqual(
            int(
                self.git(
                    self.persist_path, "rev-list", "--count", f"{origin_tip}..HEAD"
                )
            ),
            2,
        )

    def test_divergence_refused_after_direct_commit_on_persist(self) -> None:
        self.integration_create()
        first = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(first)
        self.checkout_persist()
        self.payload(self.land())
        persist_tip_after_first_land = self.git(self.persist_path, "rev-parse", "HEAD")

        # someone commits directly on the persist branch
        (self.persist_path / "direct.txt").write_text(
            "direct commit\n", encoding="utf-8"
        )
        self.git(self.persist_path, "add", "direct.txt")
        self.git(
            self.persist_path,
            "commit",
            "-q",
            "-m",
            "direct edit",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:05:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:05:00+0000",
            },
        )
        diverged_tip = self.git(self.persist_path, "rev-parse", "HEAD")
        self.assertNotEqual(diverged_tip, persist_tip_after_first_land)

        second = self.advance_integration(
            "lane-b", "lane a\nlane b\n", "2025-01-01T00:02:00+0000"
        )
        self.candidate(second)

        error = self.error_payload(self.land())
        self.assertIn("diverged", str(error["error"]).lower())
        self.assertEqual(self.git(self.persist_path, "rev-parse", "HEAD"), diverged_tip)

    def test_no_candidate_ref_refuses(self) -> None:
        self.integration_create()
        self.checkout_persist()
        error = self.error_payload(self.land())
        self.assertIn("candidate", str(error["error"]).lower())

    def test_candidate_not_ancestor_of_integration_tip_refuses(self) -> None:
        # publish a candidate, then rebuild the integration branch onto a
        # different history so the published candidate falls off the tip.
        self.integration_create()
        first = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(first)
        self.checkout_persist()

        # forcibly move the candidate ref to an unrelated commit not on the
        # integration branch at all.
        (self.root / "stray.txt").write_text("stray\n", encoding="utf-8")
        self.git(self.root, "add", "stray.txt")
        self.git(
            self.root,
            "commit",
            "-q",
            "-m",
            "stray",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:03:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:03:00+0000",
            },
        )
        stray = self.git(self.root, "rev-parse", "HEAD")
        self.git(self.root, "update-ref", self.candidate_ref, stray)

        error = self.error_payload(self.land())
        self.assertIn("ancestor", str(error["error"]).lower())

    def test_final_requires_candidate_equal_tip_else_refuses_and_succeeds_without_final(
        self,
    ) -> None:
        self.integration_create()
        first = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(first)
        self.checkout_persist()
        before = self.git(self.persist_path, "rev-parse", "HEAD")
        # advance integration past the published candidate without republishing
        self.advance_integration(
            "lane-b", "lane a\nlane b\n", "2025-01-01T00:02:00+0000"
        )

        error = self.error_payload(self.land(final=True))
        self.assertIn("final", str(error["error"]).lower())
        self.assertEqual(self.git(self.persist_path, "rev-parse", "HEAD"), before)

        landed = self.payload(self.land(final=False))
        self.assertFalse(landed["final"])

    def test_persist_branch_not_checked_out_refuses(self) -> None:
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(target)
        # never checked out into any worktree
        self.git(self.root, "branch", self.persist_branch, self.base)

        error = self.error_payload(self.land())
        self.assertIn("worktree", str(error["error"]).lower())

    def test_staged_changes_refuse_and_nothing_is_committed(self) -> None:
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(target)
        self.checkout_persist()
        before = self.git(self.persist_path, "rev-parse", "HEAD")

        (self.persist_path / "staged.txt").write_text("staged\n", encoding="utf-8")
        self.git(self.persist_path, "add", "staged.txt")

        error = self.error_payload(self.land())
        self.assertIn("staged", str(error["error"]).lower())
        self.assertEqual(self.git(self.persist_path, "rev-parse", "HEAD"), before)
        self.assertIn(
            "A  staged.txt", self.git(self.persist_path, "status", "--porcelain")
        )

    def test_unstaged_and_untracked_survive_byte_for_byte(self) -> None:
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(target)
        self.checkout_persist()

        # unstaged modification to a tracked file the candidate does not
        # touch (it was already tracked at self.base, see setUp) -- this is
        # exactly the "first landing" anchor shape, so it must not trip the
        # divergence guard.
        (self.persist_path / "user-tracked.txt").write_text(
            "tracked v2 dirty\n", encoding="utf-8"
        )
        (self.persist_path / "user-untracked.txt").write_text(
            "untracked dirt\n", encoding="utf-8"
        )

        landed = self.payload(self.land())

        self.assertIn("user-tracked.txt", landed["preserved_dirty_paths"])
        self.assertIn("user-untracked.txt", landed["preserved_dirty_paths"])
        self.assertEqual(
            (self.persist_path / "user-tracked.txt").read_text(encoding="utf-8"),
            "tracked v2 dirty\n",
        )
        self.assertEqual(
            (self.persist_path / "user-untracked.txt").read_text(encoding="utf-8"),
            "untracked dirt\n",
        )
        landed_paths = self.git(
            self.persist_path, "show", "--stat", "--format=", "HEAD"
        )
        self.assertNotIn("user-tracked.txt", landed_paths)
        self.assertNotIn("user-untracked.txt", landed_paths)
        self.assertIn(
            "?? user-untracked.txt",
            self.git(self.persist_path, "status", "--porcelain"),
        )

    def test_untracked_directory_and_non_ascii_paths_survive_byte_for_byte(
        self,
    ) -> None:
        """Regression: git collapses a wholly-untracked directory to one ``?? dir/``
        porcelain line by default, and quotes/octal-escapes any non-ASCII path.
        A naive reader of plain ``git status --porcelain`` either tries to
        ``read_bytes()`` the directory itself (a crash, not a refusal) or
        silently drops protection for files inside it and for
        non-ASCII-named files -- exactly the paths this repo's own users have.
        """
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(target)
        self.checkout_persist()

        # unstaged modification to a tracked file the candidate does not touch
        (self.persist_path / "user-tracked.txt").write_text(
            "tracked v2 dirty\n", encoding="utf-8"
        )
        # untracked file directly in the worktree
        (self.persist_path / "user-untracked.txt").write_text(
            "untracked dirt\n", encoding="utf-8"
        )
        # untracked directory holding a file -- git folds this to `?? scratch/`
        # unless the reader asks it to expand
        (self.persist_path / "scratch").mkdir()
        (self.persist_path / "scratch" / "notes.txt").write_text(
            "scratch notes\n", encoding="utf-8"
        )
        # untracked file with a non-ASCII name -- quoted/escaped by default
        # porcelain output unless the reader asks for unquoted -z output
        non_ascii_name = "使用者筆記.txt"
        (self.persist_path / non_ascii_name).write_text(
            "non-ascii dirt\n", encoding="utf-8"
        )

        landed = self.payload(self.land())

        dirty_paths = set(landed["preserved_dirty_paths"])
        self.assertIn("user-tracked.txt", dirty_paths)
        self.assertIn("user-untracked.txt", dirty_paths)
        self.assertIn("scratch/notes.txt", dirty_paths)
        self.assertIn(non_ascii_name, dirty_paths)

        self.assertEqual(
            (self.persist_path / "user-tracked.txt").read_text(encoding="utf-8"),
            "tracked v2 dirty\n",
        )
        self.assertEqual(
            (self.persist_path / "user-untracked.txt").read_text(encoding="utf-8"),
            "untracked dirt\n",
        )
        self.assertEqual(
            (self.persist_path / "scratch" / "notes.txt").read_text(encoding="utf-8"),
            "scratch notes\n",
        )
        self.assertEqual(
            (self.persist_path / non_ascii_name).read_text(encoding="utf-8"),
            "non-ascii dirt\n",
        )

        landed_paths = self.git(
            self.persist_path, "show", "--stat", "--format=", "HEAD"
        )
        for path in (
            "user-tracked.txt",
            "user-untracked.txt",
            "scratch/notes.txt",
            non_ascii_name,
        ):
            self.assertNotIn(path, landed_paths)

    def test_second_task_landing_after_a_different_task_names_the_blocking_task(
        self,
    ) -> None:
        """Regression: two tasks landing to the same persist branch in sequence.

        Once alpha has landed, its squash commit is neither an ancestor of
        beta's candidate (unrelated history) nor beta's own Landed: anchor
        (it carries a different Task: trailer) -- this must be refused, and
        the refusal must name which task got there first, since that is the
        only actionable information for a caller running several tasks in
        parallel against one persistence branch.
        """
        beta = "land-task-beta"
        self.integration_create()
        alpha_target = self.advance_integration(
            "lane-a", "alpha content\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(alpha_target)
        self.checkout_persist()
        self.payload(self.land(final=True))

        self.integration_create(task_id=beta)
        beta_target = self.advance_integration(
            "lane-b",
            "beta content\n",
            "2025-01-01T00:02:00+0000",
            path="beta.txt",
            task_id=beta,
        )
        self.candidate(beta_target, task_id=beta)

        error = self.error_payload(self.land(final=True, task_id=beta))
        self.assertIn(self.task_id, str(error["error"]))
        self.assertIn("open a lane", str(error["error"]).lower())
        self.assertIn("collect", str(error["error"]).lower())
        self.assertNotIn("merge main into this task's integration", str(error["error"]).lower())
        # nothing moved: alpha's landing is still the persist tip
        self.assertEqual(
            self.git(self.persist_path, "rev-parse", "HEAD"),
            self.git(self.persist_path, "rev-parse", self.persist_branch),
        )

    def test_second_task_lands_after_merging_persist_into_its_own_integration(
        self,
    ) -> None:
        """The forward path out of the previous test: beta merges the persist
        branch (append-only, S5.5) into its own integration branch, collects a
        lane from that merged base, and then landing succeeds -- because the
        persist tip is an ancestor and the candidate is still a proven collect.
        """
        beta = "land-task-beta"
        self.integration_create()
        alpha_target = self.advance_integration(
            "lane-a", "alpha content\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(alpha_target)
        self.checkout_persist()
        self.payload(self.land(final=True))

        self.integration_create(task_id=beta)
        self.advance_integration(
            "lane-b",
            "beta content\n",
            "2025-01-01T00:02:00+0000",
            path="beta.txt",
            task_id=beta,
        )
        beta_integration_branch = f"wave/{beta}/integration"
        beta_integration_path = (
            self.root / ".agent_state" / "worktrees" / f"{beta}-integration"
        )

        # Forward-merge the persist branch into beta's integration branch,
        # then collect one lane from that merged base so candidate provenance
        # remains an actual Orchestrate collect rather than the direct merge.
        self.git(
            beta_integration_path,
            "merge",
            "--no-ff",
            "-m",
            "merge persist into beta integration",
            self.persist_branch,
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:03:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:03:00+0000",
            },
        )
        merged_tip = self.git(self.root, "rev-parse", beta_integration_branch)
        proven_tip = self.advance_integration(
            "lane-c",
            "ready\n",
            "2025-01-01T00:04:00+0000",
            path="beta-ready.txt",
            task_id=beta,
        )
        self.assertEqual(
            self.git(self.root, "merge-base", "--is-ancestor", merged_tip, proven_tip),
            "",
        )
        self.candidate(proven_tip, task_id=beta)

        landed = self.payload(self.land(final=True, task_id=beta))

        self.assertEqual(
            self.git(self.persist_path, "rev-parse", "HEAD^{tree}"),
            self.git(self.root, "rev-parse", f"{proven_tip}^{{tree}}"),
        )
        # both tasks' files are present: beta's landing did not lose alpha's.
        self.assertEqual(
            (self.persist_path / "app.txt").read_text(encoding="utf-8"),
            "alpha content\n",
        )
        self.assertEqual(
            (self.persist_path / "beta.txt").read_text(encoding="utf-8"),
            "beta content\n",
        )
        self.assertEqual(landed["candidate"], proven_tip)

    def test_local_modification_colliding_with_the_candidates_own_change_refuses(
        self,
    ) -> None:
        """The class of collision `read-tree -m` refuses on its own: a local,
        unstaged edit to a tracked path the candidate itself also changes.
        Unlike the untouched-dirt cases above, this one must be refused --
        landing has no way to know which of the two edits should win -- and
        the local edit must survive exactly as the user left it.
        """
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(target)
        self.checkout_persist()

        # the candidate changes app.txt; dirty app.txt itself, unstaged, in
        # the persist worktree before attempting to land it.
        (self.persist_path / "app.txt").write_text(
            "locally dirty, not yet committed\n", encoding="utf-8"
        )

        error = self.error_payload(self.land())
        self.assertIn("app.txt", str(error["error"]))
        self.assertEqual(
            (self.persist_path / "app.txt").read_text(encoding="utf-8"),
            "locally dirty, not yet committed\n",
        )
        # persist tip never advanced; nothing was committed
        self.assertEqual(self.git(self.persist_path, "rev-parse", "HEAD"), self.base)

    def test_duplicate_landed_trailer_reported_as_ambiguous(self) -> None:
        self.integration_create()
        first = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(first)
        self.checkout_persist()

        # craft a persist tip that carries two Landed: trailers directly,
        # bypassing `land` -- this is the state a corrupted or hand-edited
        # commit would leave behind.
        (self.persist_path / "manual.txt").write_text("manual\n", encoding="utf-8")
        self.git(self.persist_path, "add", "manual.txt")
        message = (
            f"Manual land\n\nTask: {self.task_id}\nLanded: {first}\nLanded: {first}"
        )
        self.git(
            self.persist_path,
            "commit",
            "-q",
            "-m",
            message,
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:04:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:04:00+0000",
            },
        )

        second = self.advance_integration(
            "lane-b", "lane a\nlane b\n", "2025-01-01T00:02:00+0000"
        )
        self.candidate(second)

        error = self.error_payload(self.land())
        self.assertIn("ambiguous", str(error["error"]).lower())

    def test_full_lifecycle_leaves_zero_refs_and_zero_branches(self) -> None:
        """Regression test for the measured leak (ticket background): create,
        lane, collect, candidate, land, remove -- run through nothing but the
        documented, successful commands -- must leave the repository exactly
        as it was before the task started: no branches, no refs, nothing for
        a later `pin migrate` to trip over (S5.7).
        """
        self.integration_create()
        target = self.advance_integration(
            "lane-a", "lane a\n", "2025-01-01T00:01:00+0000"
        )
        self.candidate(target)
        self.checkout_persist()
        self.payload(self.land(final=True))

        removed = self.payload(
            self.cli(
                self.root,
                "integration",
                "remove",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
            )
        )
        self.assertFalse(removed["abandoned"])

        self.assertEqual(
            self.git(self.root, "for-each-ref", f"refs/orchestrate/{self.task_id}/"), ""
        )
        self.assertEqual(
            self.git(self.root, "branch", "--list", f"wave/{self.task_id}/*"), ""
        )


if __name__ == "__main__":
    unittest.main()
