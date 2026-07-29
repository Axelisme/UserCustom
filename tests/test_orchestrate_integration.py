from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

from tests._orchestrate_cli_support import SCRIPT, VERIFIED_SKILL


class IntegrationWorktreeContractTests(unittest.TestCase):
    """Black-box Contract for the integration branch's lane-collect lifecycle."""

    task_id = "integration-task"

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
        self,
        root: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--skill-dir", str(VERIFIED_SKILL), *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        value = json.loads(result.stdout)
        self.assertIsInstance(value, dict)
        self.assertTrue(value.get("ok"), value)
        return value

    def error_payload(
        self, result: subprocess.CompletedProcess[str]
    ) -> dict[str, object]:
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "", result.stdout)
        value = json.loads(result.stderr)
        self.assertIsInstance(value, dict)
        self.assertFalse(value.get("ok"), value)
        self.assertIsInstance(value.get("error"), dict)
        return value

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git(self.root, "init", "-q", "-b", "main")
        self.git(self.root, "config", "user.name", "Integration Test")
        self.git(self.root, "config", "user.email", "integration@example.test")
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
        self.base_ref = f"refs/orchestrate/{self.task_id}/integration/base"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def integration_create(
        self, task_id: str | None = None, base: str | None = None
    ) -> dict[str, object]:
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
        declare_immutable: bool = True,
    ) -> str:
        (worktree / path).write_text(content, encoding="utf-8")
        self.git(worktree, "add", path)
        if declare_immutable and "Immutable:" not in message:
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

    def collect(self, lane_id: str, sha: str) -> dict[str, object]:
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
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:10:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:10:00+0000",
                },
            )
        )

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

    def status(self) -> dict[str, object]:
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

    def test_create_collect_status_tracks_two_lanes_in_git_order(self) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))
        self.assertEqual(created["operation"], "integration-create")
        self.assertEqual(created["branch"], f"wave/{self.task_id}/integration")
        self.assertEqual(
            created["worktree"],
            str(
                self.root / ".agent_state" / "worktrees" / f"{self.task_id}-integration"
            ),
        )
        self.assertEqual(created["base"], self.base)
        self.assertTrue(created["clean"])

        lane_a = self.lane_create("lane-a", self.base)
        sha_a = self.commit_lane(lane_a, "lane a\n")
        collect_a = self.collect("lane-a", sha_a)
        self.assertEqual(collect_a["operation"], "integration-collect")
        self.assertEqual(collect_a["lane_id"], "lane-a")

        integration_tip = self.git(integration_path, "rev-parse", "HEAD")
        lane_b = self.lane_create("lane-b", integration_tip)
        sha_b = self.commit_lane(
            lane_b, "lane a\nlane b\n", date="2025-01-01T00:02:00+0000"
        )
        collect_b = self.collect("lane-b", sha_b)

        status = self.status()
        self.assertEqual(status["operation"], "integration-status")
        self.assertTrue(status["exists"])
        self.assertEqual(status["head"], collect_b["collect_sha"])
        self.assertEqual(
            status["collected"],
            [
                {
                    "lane": "lane-a",
                    "collect_sha": collect_a["collect_sha"],
                    "sha": sha_a,
                },
                {
                    "lane": "lane-b",
                    "collect_sha": collect_b["collect_sha"],
                    "sha": sha_b,
                },
            ],
        )

    def test_collect_rejects_a_dirty_integration_worktree_and_a_re_collected_lane(
        self,
    ) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))

        lane = self.lane_create("lane-a", self.base)
        sha = self.commit_lane(lane, "lane a\n")
        (integration_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-a",
                "--sha",
                sha,
            )
        )
        self.assertIn("integration worktree must be clean", str(error["error"]))
        (integration_path / "dirty.txt").unlink()
        self.collect("lane-a", sha)

        # The lane worktree is gone after the first collect, so a repeated
        # collect of the same lane id has nothing left to verify against.
        error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-a",
                "--sha",
                sha,
            )
        )
        self.assertIn("does not exist", str(error["error"]))

    def test_conflict_is_resolved_in_the_lane_worktree_not_the_integration_worktree(
        self,
    ) -> None:
        """Deliverable 5: conflict resolution follows Git's own pull-then-push
        model.  Two lanes edit the same line; the second lane is behind the
        integration tip by the time it collects, so `collect` first merges
        the integration tip into the *lane* worktree (never the integration
        worktree, which must stay pristine).  That merge conflicts here, so
        the refusal leaves the conflict exactly where Git put it -- in the
        lane -- and the integration worktree is untouched.  Resolving the
        conflict in the lane, committing it there, and re-running collect
        with the lane's new tip then succeeds.
        """
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))

        lane_a = self.lane_create("lane-a", self.base)
        sha_a = self.commit_lane(lane_a, "lane a\n")
        collect_a = self.collect("lane-a", sha_a)
        integration_tip_after_a = collect_a["collect_sha"]

        # lane-b is created from the original base, not the post-collect
        # integration tip -- it is behind, exactly the staleness case.
        lane_b = self.lane_create("lane-b", self.base)
        sha_b = self.commit_lane(lane_b, "lane b\n")
        error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-b",
                "--sha",
                sha_b,
            )
        )
        self.assertIn("collect refused", str(error["error"]))
        self.assertIn("app.txt", str(error["error"]))
        self.assertIn(str(lane_b), str(error["error"]))

        # the lane worktree holds the conflict...
        self.assertIn("UU app.txt", self.git(lane_b, "status", "--porcelain"))
        self.assertEqual(
            self.git(lane_b, "rev-parse", "--verify", "MERGE_HEAD"),
            integration_tip_after_a,
        )
        # ...and it is not removed on a failed collect.
        self.assertTrue(lane_b.exists())

        # ...while the integration worktree stays exactly where it was:
        # clean, unmoved, and with no merge in progress.
        self.assertEqual(self.git(integration_path, "status", "--porcelain"), "")
        self.assertEqual(
            self.git(integration_path, "rev-parse", "HEAD"), integration_tip_after_a
        )
        merge_head_probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "MERGE_HEAD"],
            cwd=integration_path,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(merge_head_probe.returncode, 0)

        # resolve in the lane worktree, commit it there, and re-run collect
        # with the lane's new tip.
        (lane_b / "app.txt").write_text("lane a\nlane b\n", encoding="utf-8")
        self.git(lane_b, "add", "app.txt")
        self.git(
            lane_b,
            "commit",
            "-q",
            "-m",
            "resolve conflict",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:05:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:05:00+0000",
            },
        )
        resolved_tip = self.git(lane_b, "rev-parse", "HEAD")

        collect_b = self.collect("lane-b", resolved_tip)
        self.assertEqual(collect_b["merged_sha"], resolved_tip)
        self.assertFalse(lane_b.exists())

    def test_a_stale_lane_touching_a_different_file_merges_automatically_in_one_call(
        self,
    ) -> None:
        """Two lanes editing different files: the staleness merge is clean,
        so collect succeeds in a single call and reports a `merged_sha`
        distinct from the asserted `--sha` -- the caller can see the lane's
        tip advanced underneath it.
        """
        self.integration_create()

        lane_a = self.lane_create("lane-a", self.base)
        sha_a = self.commit_lane(lane_a, "lane a\n")
        self.collect("lane-a", sha_a)

        lane_b = self.lane_create("lane-b", self.base)
        sha_b = self.commit_lane(lane_b, "lane b\n", path="other.txt")

        collected = self.collect("lane-b", sha_b)

        self.assertEqual(collected["sha"], sha_b)
        self.assertNotEqual(collected["merged_sha"], sha_b)
        self.assertEqual(
            self.git(
                self.root, "log", "-1", "--format=%s", str(collected["merged_sha"])
            ),
            "Merge integration into lane lane-b",
        )
        self.assertFalse(lane_b.exists())

    def test_first_parent_immutable_walk_ignores_net_zero_history_from_another_lane(
        self,
    ) -> None:
        """Ticket deliverable 5's literal Tests-section case: a lane declares
        an Immutable path and never touches it again; another lane's own
        history touches -- and then reverts -- that same path before
        collecting, so integration's content for it never actually changes.
        The staleness merge is therefore TREESAME to this lane's own first
        parent for that path, so ``--first-parent`` never even walks into it,
        and collect succeeds.
        """
        self.integration_create()
        lane_a, _declaring_sha = self.prepare_declared_lane("lane-a")
        declared_content = (
            "assert app == 1\n"  # must match prepare_declared_lane's own content
        )

        # lane-b touches contract_test.py twice, ending up back at exactly
        # the content lane-a declared frozen -- net zero for that path.
        # lane-b starts from self.base (contract_test.py does not exist
        # there yet -- it is lane-a's own, undeclared-to-lane-b file), so
        # lane-b's first touch also creates it.
        lane_b = self.lane_create("lane-b", self.base)
        self.commit_lane(
            lane_b,
            "temporarily different\n",
            "touch contract_test.py",
            date="2025-01-01T00:02:00+0000",
            path="contract_test.py",
        )
        self.commit_lane(
            lane_b,
            declared_content,
            "revert contract_test.py",
            date="2025-01-01T00:02:30+0000",
            path="contract_test.py",
        )
        sha_b = self.commit_lane(
            lane_b, "lane b\n", date="2025-01-01T00:03:00+0000", path="other.txt"
        )
        self.collect("lane-b", sha_b)

        # lane-a fills in production behavior, leaving its declared surface
        # byte-identical, then collects -- its staleness merge pulls in
        # lane-b's history (which touched contract_test.py) without net
        # effect on it.
        sha_a = self.commit_lane(
            lane_a,
            "lane a\n",
            date="2025-01-01T00:04:00+0000",
            declare_immutable=False,
        )
        collected = self.collect("lane-a", sha_a)
        self.assertEqual(collected["immutable_paths_verified"], ["contract_test.py"])

    def test_lane_still_rejected_for_changing_its_own_declared_path_after_a_staleness_merge(
        self,
    ) -> None:
        """The existing rule is not weakened by the staleness merge: a lane
        that changes its own declared Immutable: path without redeclaring is
        still rejected, even once its own history includes a merge commit.
        """
        self.integration_create()
        other_lane = self.lane_create("lane-b", self.base)
        sha_other = self.commit_lane(
            other_lane, "unrelated\n", date="2025-01-01T00:01:00+0000", path="other.txt"
        )
        self.collect("lane-b", sha_other)

        lane_a, _declaring_sha = self.prepare_declared_lane("lane-a")
        # lane-a is behind (created from self.base, and lane-b already
        # collected), so this collect must first do the staleness merge.
        weakened = self.commit_lane(
            lane_a,
            "assert True\n",
            "weaken",
            date="2025-01-01T00:03:00+0000",
            path="contract_test.py",
        )
        error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-a",
                "--sha",
                weakened,
            )
        )
        self.assertIn("without redeclaring", str(error["error"]))
        self.assertIn("contract_test.py", str(error["error"]))

    def test_candidate_refuses_collect_shaped_merge_with_a_forged_tree_atomically(
        self,
    ) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))
        acceptance_path = (
            self.root
            / ".agent_state"
            / "worktrees"
            / f"{self.task_id}-acceptance"
        )
        lane = self.lane_create("lane-a", self.base)
        lane_sha = self.commit_lane(
            lane,
            "lane tree\n",
            "contract\n\nImmutable: app.txt",
        )
        base_tree = self.git(self.root, "rev-parse", f"{self.base}^{{tree}}")
        forged = self.git(
            self.root,
            "commit-tree",
            base_tree,
            "-p",
            self.base,
            "-p",
            lane_sha,
            "-m",
            f"Collect lane lane-a\n\nTask: {self.task_id}\nLane: lane-a",
        )
        self.git(integration_path, "reset", "--hard", forged)
        old_acceptance_head = self.git(acceptance_path, "rev-parse", "HEAD")
        candidate_ref = f"refs/orchestrate/{self.task_id}/candidate"

        error = self.error_payload(self.candidate(forged))

        self.assertIn("tree", str(error["error"]).lower())
        self.assertEqual(
            self.git(acceptance_path, "rev-parse", "HEAD"), old_acceptance_head
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", "--verify", "--quiet", candidate_ref, check=False),
            "",
        )

    def test_create_refuses_existing_path_or_branch_and_remove_refuses_dirty(
        self,
    ) -> None:
        self.integration_create()
        duplicate_branch = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--base",
                self.base,
            )
        )
        self.assertIn("already exists", str(duplicate_branch["error"]))

        path_task = "path-task"
        path = self.root / ".agent_state" / "worktrees" / f"{path_task}-integration"
        path.mkdir(parents=True)
        duplicate_path = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                path_task,
                "--base",
                self.base,
            )
        )
        self.assertIn("already exists", str(duplicate_path["error"]))

        integration_path = (
            self.root / ".agent_state" / "worktrees" / f"{self.task_id}-integration"
        )
        (integration_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        dirty_remove = self.error_payload(
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
        self.assertIn("not clean", str(dirty_remove["error"]))
        # nothing was deleted: not the worktree, not the base ref, not the branch.
        self.assertTrue(integration_path.is_dir())
        self.assertEqual(
            self.git(self.root, "rev-parse", "--verify", self.base_ref), self.base
        )
        self.assertEqual(
            self.git(
                self.root, "rev-parse", "--verify", f"wave/{self.task_id}/integration"
            ),
            self.base,
        )

    def test_collected_projection_is_bounded_by_the_recorded_base_ref(self) -> None:
        # A landed task leaves its own collect commits in the persistence branch history.
        (self.root / "landed.txt").write_text("landed\n", encoding="utf-8")
        self.git(self.root, "add", "landed.txt")
        self.git(
            self.root,
            "commit",
            "-q",
            "-m",
            "Collect lane lane-a\n\nTask: previous-task\nLane: lane-a",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:00:30+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:00:30+0000",
            },
        )
        landed_base = self.git(self.root, "rev-parse", "HEAD")

        created = self.integration_create(base=landed_base)
        self.assertEqual(self.status()["collected"], [])
        self.assertEqual(created["base_ref"], self.base_ref)
        self.assertEqual(
            self.git(self.root, "rev-parse", "--verify", self.base_ref), landed_base
        )

        # The reused lane id belonged to a different task, so it must not be rejected here.
        lane = self.lane_create("lane-a", landed_base)
        sha = self.commit_lane(lane, "lane a\n")
        collected = self.collect("lane-a", sha)
        self.assertEqual(
            self.status()["collected"],
            [{"lane": "lane-a", "collect_sha": collected["collect_sha"], "sha": sha}],
        )

    def prepare_declared_lane(self, lane_id: str) -> tuple[Path, str]:
        """Create a lane that declares one immutable path in its first commit."""
        lane = self.lane_create(lane_id, self.base)
        (lane / "contract_test.py").write_text("assert app == 1\n", encoding="utf-8")
        self.git(lane, "add", "contract_test.py")
        self.git(
            lane,
            "commit",
            "-q",
            "-m",
            "declare contract\n\nImmutable: contract_test.py",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:01:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:01:00+0000",
            },
        )
        declaring_sha = self.git(lane, "rev-parse", "HEAD")
        return lane, declaring_sha

    def test_collect_verifies_the_declared_immutable_surface(self) -> None:
        self.integration_create()
        lane, _declaring_sha = self.prepare_declared_lane("lane-a")

        # Filling production behavior leaves the declared surface byte-identical.
        sha = self.commit_lane(
            lane,
            "lane a\n",
            date="2025-01-01T00:03:00+0000",
            declare_immutable=False,
        )
        collected = self.collect("lane-a", sha)
        self.assertEqual(collected["immutable_paths_verified"], ["contract_test.py"])

    def test_collect_refuses_a_weakened_or_relocated_acceptance_surface_without_redeclaration(
        self,
    ) -> None:
        self.integration_create()
        lane, _declaring_sha = self.prepare_declared_lane("lane-a")

        (lane / "contract_test.py").write_text("assert True\n", encoding="utf-8")
        self.git(lane, "add", "contract_test.py")
        weakened = self.commit_lane(
            lane, "lane a\n", "weaken", date="2025-01-01T00:03:00+0000"
        )
        weakened_error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-a",
                "--sha",
                weakened,
            )
        )
        self.assertIn("without redeclaring", str(weakened_error["error"]))
        self.assertIn("contract_test.py", str(weakened_error["error"]))
        self.assertIn(weakened, str(weakened_error["error"]))

        self.git(lane, "mv", "contract_test.py", "moved_contract_test.py")
        relocated = self.commit_lane(
            lane, "lane a moved\n", "relocate", date="2025-01-01T00:04:00+0000"
        )
        relocated_error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-a",
                "--sha",
                relocated,
            )
        )
        self.assertIn("without redeclaring", str(relocated_error["error"]))
        self.assertIn("contract_test.py", str(relocated_error["error"]))
        self.assertIn(relocated, str(relocated_error["error"]))

    def test_status_fails_closed_without_the_base_ref(self) -> None:
        self.integration_create()
        self.git(self.root, "update-ref", "-d", self.base_ref)

        error = self.error_payload(
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
        self.assertIn("integration base ref is missing", str(error["error"]))

    def list_tasks(self) -> dict[str, object]:
        return self.payload(
            self.cli(self.root, "integration", "list", "--root", str(self.root))
        )

    # `integration list`: read-only, never refuses, no --task-id, sorted by
    # task id -- the shallow view of every task in one repository.
    def test_list_on_an_empty_repo_returns_an_empty_list(self) -> None:
        result = self.list_tasks()
        self.assertEqual(result["operation"], "integration-list")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["tasks"], [])

    def lane_create_for(self, task_id: str, lane_id: str, base: str) -> Path:
        payload = self.payload(
            self.cli(
                self.root,
                "lane",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                task_id,
                "--lane-id",
                lane_id,
                "--base",
                base,
            )
        )
        return Path(str(payload["worktree"]))

    def test_list_reports_both_tasks_sorted_with_lane_ids_and_candidate_state(
        self,
    ) -> None:
        # task "b" created first, task "a" second -- list must still sort by
        # task id, not creation order.
        self.integration_create(task_id="task-b")
        lane_b = self.lane_create_for("task-b", "lane-b1", self.base)

        created_a = self.integration_create(task_id="task-a")
        lane_a = self.lane_create_for("task-a", "lane-a1", self.base)

        sha_a = self.commit_lane(lane_a, "lane a\n")
        self.payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                "task-a",
                "--lane-id",
                "lane-a1",
                "--sha",
                sha_a,
            )
        )
        integration_a_tip = self.git(self.root, "rev-parse", "wave/task-a/integration")
        self.payload(
            self.cli(
                self.root,
                "integration",
                "candidate",
                "--root",
                str(self.root),
                "--task-id",
                "task-a",
                "--sha",
                integration_a_tip,
            )
        )

        sha_b = self.commit_lane(lane_b, "lane b\n")
        self.payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                "task-b",
                "--lane-id",
                "lane-b1",
                "--sha",
                sha_b,
            )
        )

        result = self.list_tasks()
        tasks = cast("list[dict[str, object]]", result["tasks"])
        self.assertEqual([task["task_id"] for task in tasks], ["task-a", "task-b"])

        task_a = tasks[0]
        self.assertEqual(task_a["branch"], "wave/task-a/integration")
        self.assertTrue(task_a["branch_exists"])
        self.assertEqual(task_a["base"], created_a["base"])
        # collect keeps the lane branch even after removing its worktree
        # (see test_orchestrate_lane.py), so the branch is still listed here.
        self.assertEqual(task_a["lanes"], ["lane-a1"])
        self.assertIsNotNone(task_a["candidate"])
        candidate_a = cast("dict[str, object]", task_a["candidate"])
        self.assertEqual(candidate_a["sha"], integration_a_tip)
        self.assertTrue(task_a["integration_worktree_present"])
        self.assertTrue(task_a["acceptance_worktree_present"])

        task_b = tasks[1]
        self.assertEqual(task_b["branch"], "wave/task-b/integration")
        self.assertTrue(task_b["branch_exists"])
        self.assertEqual(task_b["lanes"], ["lane-b1"])
        self.assertIsNone(task_b["candidate"])

    def remove(self, *, abandon: bool = False) -> subprocess.CompletedProcess[str]:
        args = [
            "integration",
            "remove",
            "--root",
            str(self.root),
            "--task-id",
            self.task_id,
        ]
        if abandon:
            args.append("--abandon")
        return self.cli(self.root, *args)

    # `integration remove` (S5.7 close-out): never destroys work that has no
    # other home.  A collected-but-never-landed integration branch refuses,
    # and names the branch.
    def test_remove_refuses_an_unlanded_integration_branch_and_names_it(self) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))
        lane = self.lane_create("lane-a", self.base)
        sha = self.commit_lane(lane, "lane a\n")
        self.collect("lane-a", sha)

        error = self.error_payload(self.remove())
        self.assertIn("unlanded", str(error["error"]))
        self.assertIn(f"wave/{self.task_id}/integration", str(error["error"]))
        # nothing deleted
        self.assertTrue(integration_path.is_dir())
        self.assertEqual(
            self.git(self.root, "rev-parse", "--verify", f"wave/{self.task_id}/lane-a"),
            sha,
        )

    # An uncollected lane branch (its worktree dropped, never merged into
    # integration) refuses removal too, and names the lane branch.
    def test_remove_refuses_an_uncollected_lane_branch_and_names_it(self) -> None:
        self.integration_create()
        lane_path = self.lane_create("lane-a", self.base)
        self.commit_lane(lane_path, "lane a\n")
        self.payload(
            self.cli(
                self.root,
                "lane",
                "drop",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-a",
            )
        )

        error = self.error_payload(self.remove())
        self.assertIn("uncollected", str(error["error"]))
        self.assertIn(f"wave/{self.task_id}/lane-a", str(error["error"]))

    # --abandon proceeds over both categories at once and reports it; the
    # refusal it bypasses names both, and after abandoning, every ref and
    # branch of the task is gone.
    def test_abandon_proceeds_over_both_unlanded_and_uncollected_and_reports_it(
        self,
    ) -> None:
        self.integration_create()
        collected_lane = self.lane_create("lane-a", self.base)
        sha = self.commit_lane(collected_lane, "lane a\n")
        self.collect("lane-a", sha)

        dropped_lane = self.lane_create("lane-b", self.base)
        self.commit_lane(dropped_lane, "lane b\n")
        self.payload(
            self.cli(
                self.root,
                "lane",
                "drop",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--lane-id",
                "lane-b",
            )
        )

        refused = self.error_payload(self.remove())
        self.assertIn("unlanded", str(refused["error"]))
        self.assertIn("uncollected", str(refused["error"]))
        self.assertIn(f"wave/{self.task_id}/lane-b", str(refused["error"]))

        removed = self.payload(self.remove(abandon=True))
        self.assertTrue(removed["abandoned"])
        removed_branches = cast("list[str]", removed["removed_branches"])
        self.assertIn(f"wave/{self.task_id}/integration", removed_branches)
        self.assertIn(f"wave/{self.task_id}/lane-a", removed_branches)
        self.assertIn(f"wave/{self.task_id}/lane-b", removed_branches)
        self.assertEqual(
            self.git(self.root, "for-each-ref", f"refs/orchestrate/{self.task_id}/"), ""
        )
        self.assertEqual(
            self.git(self.root, "branch", "--list", f"wave/{self.task_id}/*"), ""
        )

    def test_abandon_recovers_a_conflicted_integration_merge_before_removal(self) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))

        (integration_path / "app.txt").write_text("integration\n", encoding="utf-8")
        self.git(integration_path, "add", "app.txt")
        self.git(integration_path, "commit", "-q", "-m", "integration work")

        (self.root / "app.txt").write_text("persist\n", encoding="utf-8")
        self.git(self.root, "add", "app.txt")
        self.git(self.root, "commit", "-q", "-m", "persist work")

        self.git(integration_path, "merge", "main", check=False)
        self.assertTrue((integration_path / ".git").is_file())
        self.assertNotEqual(
            self.git(integration_path, "rev-parse", "-q", "--verify", "MERGE_HEAD"),
            "",
        )

        removed = self.payload(self.remove(abandon=True))

        self.assertTrue(removed["abandoned"])
        self.assertFalse(integration_path.exists())
        self.assertEqual(
            self.git(self.root, "for-each-ref", f"refs/orchestrate/{self.task_id}/"), ""
        )
        self.assertEqual(
            self.git(self.root, "branch", "--list", f"wave/{self.task_id}/*"), ""
        )


if __name__ == "__main__":
    unittest.main()
