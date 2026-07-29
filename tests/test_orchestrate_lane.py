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


class LaneLifecycleContractTests(unittest.TestCase):
    """Black-box Contract for the lane worktree lifecycle and integration collect.

    lane replaces the Oracle/Implementation Wave model: one lane is one Git
    worktree, one branch, one subagent call.  ``integration collect`` verifies
    three Git-only facts (lane tree clean, exact SHA is the lane branch tip,
    every commit that changes a once-declared ``Immutable:`` path redeclares
    it on itself) and, only if all three pass, merges into the integration
    branch and unconditionally removes the lane worktree.  Contract paths may
    evolve across multiple oracle rounds inside one lane -- what is forbidden
    is an implementer widening a declared path *quietly*, not the path ever
    changing again.
    """

    task_id = "lane-task"

    def git(
        self, cwd: Path, *args: str, check: bool = True,
        env: dict[str, str] | None = None,
    ) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, text=True, capture_output=True, check=False,
            env={**os.environ, **(env or {})},
        )
        if check and result.returncode:
            self.fail(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def cli(
        self, root: Path, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--skill-dir", str(VERIFIED_SKILL), *args], cwd=root, text=True,
            capture_output=True, check=False, env={**os.environ, **(env or {})},
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
            self.fail(f"failure was not one JSON error object: {result.stderr!r}: {exc}")
        self.assertIsInstance(value, dict)
        self.assertFalse(value.get("ok"), value)
        self.assertIsInstance(value.get("error"), dict)
        return value

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git(self.root, "init", "-q", "-b", "main")
        self.git(self.root, "config", "user.name", "Lane Test")
        self.git(self.root, "config", "user.email", "lane@example.test")
        (self.root / "README").write_text("base\n", encoding="utf-8")
        self.git(self.root, "add", "README")
        self.git(
            self.root, "commit", "-q", "-m", "base",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:00:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:00:00+0000",
            },
        )
        self.base = self.git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def lane_create(self, lane_id: str, base: str | None = None) -> dict[str, Any]:
        return self.payload(self.cli(
            self.root, "lane", "create", "--root", str(self.root),
            "--task-id", self.task_id, "--lane-id", lane_id,
            "--base", base or self.base,
        ))

    def integration_create(self, base: str | None = None) -> dict[str, Any]:
        return self.payload(self.cli(
            self.root, "integration", "create", "--root", str(self.root),
            "--task-id", self.task_id, "--base", base or self.base,
        ))

    def commit(
        self, cwd: Path, path: str, content: str, message: str,
        date: str | None = None, *, declare_immutable: bool = True,
    ) -> str:
        target = cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(cwd, "add", path)
        if declare_immutable and "Immutable:" not in message:
            message = f"{message}\n\nImmutable: {path}"
        env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else None
        result = subprocess.run(
            ["git", "commit", "-q", "-m", message], cwd=cwd, text=True,
            capture_output=True, check=False, env={**os.environ, **(env or {})},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.git(cwd, "rev-parse", "HEAD")

    def collect(self, lane_id: str, sha: str) -> subprocess.CompletedProcess[str]:
        return self.cli(
            self.root, "integration", "collect", "--root", str(self.root),
            "--task-id", self.task_id, "--lane-id", lane_id, "--sha", sha,
        )

    # 1. lane create leaves a worktree and branch that both sit at --base.
    def test_lane_create_worktree_and_branch_exist_at_base(self) -> None:
        created = self.lane_create("lane-a")
        expected_branch = f"wave/{self.task_id}/lane-a"
        expected_path = self.root / ".agent_state" / "worktrees" / f"{self.task_id}-lane-a"
        self.assertEqual(created["operation"], "lane-create")
        self.assertEqual(created["branch"], expected_branch)
        self.assertEqual(created["worktree"], str(expected_path))
        self.assertEqual(created["base"], self.base)
        self.assertTrue(created["clean"])
        self.assertTrue(expected_path.is_dir())
        self.assertEqual(self.git(self.root, "rev-parse", expected_branch), self.base)
        self.assertEqual(self.git(expected_path, "rev-parse", "HEAD"), self.base)

    # 2. an existing path or branch refuses create.
    def test_lane_create_refuses_existing_path_or_branch(self) -> None:
        self.lane_create("lane-a")
        duplicate_branch = self.error_payload(self.cli(
            self.root, "lane", "create", "--root", str(self.root),
            "--task-id", self.task_id, "--lane-id", "lane-a", "--base", self.base,
        ))
        self.assertIn("already exists", str(duplicate_branch["error"]))

        path = self.root / ".agent_state" / "worktrees" / f"{self.task_id}-lane-b"
        path.mkdir(parents=True)
        duplicate_path = self.error_payload(self.cli(
            self.root, "lane", "create", "--root", str(self.root),
            "--task-id", self.task_id, "--lane-id", "lane-b", "--base", self.base,
        ))
        self.assertIn("already exists", str(duplicate_path["error"]))

    # 3. lane status without --lane-id lists every lane of the task.
    def test_lane_status_without_lane_id_lists_all_lanes(self) -> None:
        self.lane_create("lane-a")
        self.lane_create("lane-b")
        status = self.payload(self.cli(
            self.root, "lane", "status", "--root", str(self.root),
            "--task-id", self.task_id,
        ))
        self.assertEqual(status["operation"], "lane-status")
        lane_ids = {lane["lane_id"] for lane in status["lanes"]}
        self.assertEqual(lane_ids, {"lane-a", "lane-b"})
        for lane in status["lanes"]:
            self.assertTrue(lane["exists"])
            self.assertTrue(lane["clean"])

    # 4. a successful collect removes the lane worktree, keeps its branch,
    #    and advances the integration branch tip.
    def test_collect_removes_worktree_keeps_branch_and_advances_integration(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        sha = self.commit(lane_path, "feature.txt", "value\n", "implement feature")

        collected = self.payload(self.collect("lane-a", sha))

        self.assertEqual(collected["operation"], "integration-collect")
        self.assertEqual(collected["sha"], sha)
        self.assertFalse(lane_path.exists())
        self.assertEqual(
            self.git(self.root, "rev-parse", f"wave/{self.task_id}/lane-a"), sha
        )
        integration_path = self.root / ".agent_state" / "worktrees" / f"{self.task_id}-integration"
        integration_tip = self.git(integration_path, "rev-parse", "HEAD")
        self.assertEqual(integration_tip, collected["collect_sha"])
        self.assertNotEqual(integration_tip, self.base)

    # 5. a lane that changed a declared Immutable path cannot collect, and
    #    the rejection names the violated path and the offending commit.
    #    Contract paths may evolve across oracle rework rounds -- what is
    #    forbidden is an implementer changing a declared path *without*
    #    redeclaring it on the same commit, not the path ever changing again.
    def test_collect_rejects_an_undeclared_change_to_a_declared_immutable_path(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        self.commit(
            lane_path, "contract_test.py", "assert True\n",
            "declare contract\n\nImmutable: contract_test.py",
        )
        changed = self.commit(
            lane_path, "contract_test.py", "assert False\n", "weaken contract",
            declare_immutable=False,
        )

        error = self.error_payload(self.collect("lane-a", changed))
        self.assertIn("contract_test.py", str(error["error"]))
        self.assertIn(changed, str(error["error"]))
        # Non-destructive: nothing merged, nothing removed.
        self.assertTrue(lane_path.exists())

    # 6a. oracle commit A declares x; implementer commit B changes x without
    #     redeclaring it -- rejected, and the message names commit B and x.
    def test_collect_rejects_an_implementer_commit_that_changes_x_without_redeclaring(
        self,
    ) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        self.commit(
            lane_path, "x.py", "ORIGINAL = True\n",
            "declare x\n\nImmutable: x.py",
        )
        undeclared = self.commit(
            lane_path, "x.py", "ORIGINAL = False\n",
            "implement (changes x without redeclaring it)",
            declare_immutable=False,
        )

        error = self.error_payload(self.collect("lane-a", undeclared))
        self.assertIn("x.py", str(error["error"]))
        self.assertIn(undeclared, str(error["error"]))

    # 6b. oracle declares x; implementer changes something else; a second
    #     oracle round changes x again *and* redeclares it -- multiple oracle
    #     rounds inside one lane are normal, so this must collect cleanly.
    def test_collect_succeeds_when_a_second_oracle_round_redeclares_x(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        self.commit(lane_path, "x.py", "ORIGINAL = True\n", "declare x\n\nImmutable: x.py")
        self.commit(
            lane_path, "other.py", "OTHER = 1\n", "implement something else",
            declare_immutable=False,
        )
        tip = self.commit(
            lane_path, "x.py", "ORIGINAL = False\n",
            "second oracle round\n\nImmutable: x.py",
        )

        collected = self.payload(self.collect("lane-a", tip))
        self.assertEqual(collected["immutable_paths_verified"], ["x.py"])

    # 6c. multi-path interleaving: commit A declares x, commit C declares y;
    #     a later commit changes y without redeclaring it.  The rejection
    #     must point at y, not at x (which was never touched again).
    def test_collect_rejects_undeclared_change_to_y_and_does_not_blame_x(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        self.commit(lane_path, "x.py", "X = 1\n", "declare x\n\nImmutable: x.py")
        self.commit(lane_path, "y.py", "Y = 1\n", "declare y\n\nImmutable: y.py")
        undeclared = self.commit(
            lane_path, "y.py", "Y = 2\n", "change y without redeclaring",
            declare_immutable=False,
        )

        error = self.error_payload(self.collect("lane-a", undeclared))
        self.assertIn("y.py", str(error["error"]))
        self.assertIn(undeclared, str(error["error"]))
        self.assertNotIn("x.py", str(error["error"]))

    # bonus: paths declared and genuinely left untouched still collect
    # cleanly, proving the walk does not over-trigger.
    def test_collect_succeeds_when_every_declared_path_is_left_untouched(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        self.commit(lane_path, "x.py", "X = 1\n", "declare x\n\nImmutable: x.py")
        self.commit(
            lane_path, "impl.py", "IMPL = 1\n", "implement",
            declare_immutable=False,
        )
        tip = self.commit(lane_path, "y.py", "Y = 1\n", "declare y\n\nImmutable: y.py")

        collected = self.payload(self.collect("lane-a", tip))
        self.assertEqual(set(collected["immutable_paths_verified"]), {"x.py", "y.py"})

    # regression: a path is only protected starting at the commit that first
    # declares it.  Ordinary creation before that declaration -- and the
    # declaring commit itself, which may legitimately also edit the content
    # it is freezing -- must never count as an undeclared change.
    def test_collect_succeeds_when_the_path_predates_its_own_declaration(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        self.commit(
            lane_path, "tests/c.py", "DRAFT = True\n", "create contract draft",
            declare_immutable=False,
        )
        self.commit(
            lane_path, "tests/c.py", "FROZEN = True\n",
            "declare contract\n\nImmutable: tests/c.py",
        )
        tip = self.commit(
            lane_path, "impl.py", "IMPL = 1\n", "implement, never touching tests/c.py",
            declare_immutable=False,
        )

        collected = self.payload(self.collect("lane-a", tip))
        self.assertEqual(collected["immutable_paths_verified"], ["tests/c.py"])

    def test_collect_refuses_a_whole_lane_range_without_any_immutable_declaration(
        self,
    ) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        tip = self.commit(
            lane_path, "feature.txt", "value\n", "implement only",
            declare_immutable=False,
        )

        error = self.error_payload(self.collect("lane-a", tip))

        self.assertIn("no parsed Immutable declaration", str(error["error"]))
        self.assertTrue(lane_path.exists())

    # 7. a dirty lane tree refuses collect.
    def test_collect_rejects_dirty_lane_tree(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        sha = self.commit(lane_path, "feature.txt", "value\n", "implement")
        (lane_path / "scratch.txt").write_text("dirty\n", encoding="utf-8")

        error = self.error_payload(self.collect("lane-a", sha))
        self.assertIn("clean", str(error["error"]))
        self.assertTrue(lane_path.exists())
        self.assertEqual(self.git(lane_path, "status", "--porcelain"), "?? scratch.txt")

    # 8. a --sha that is not the lane branch tip refuses collect.
    def test_collect_rejects_sha_that_is_not_lane_tip(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))
        self.commit(lane_path, "feature.txt", "first\n", "first")
        self.commit(lane_path, "feature.txt", "second\n", "second")

        error = self.error_payload(self.collect("lane-a", self.base))
        self.assertRegex(str(error["error"]).lower(), r"tip")
        self.assertTrue(lane_path.exists())
        self.assertEqual(
            self.git(self.root, "rev-parse", f"wave/{self.task_id}/lane-a"),
            self.git(lane_path, "rev-parse", "HEAD"),
        )

    # 9. lane drop removes the worktree but keeps the branch.
    def test_lane_drop_removes_worktree_but_keeps_branch(self) -> None:
        lane = self.lane_create("lane-a")
        lane_path = Path(str(lane["worktree"]))

        dropped = self.payload(self.cli(
            self.root, "lane", "drop", "--root", str(self.root),
            "--task-id", self.task_id, "--lane-id", "lane-a",
        ))

        self.assertEqual(dropped["operation"], "lane-drop")
        self.assertFalse(lane_path.exists())
        self.assertEqual(
            self.git(self.root, "rev-parse", f"wave/{self.task_id}/lane-a"), self.base
        )


if __name__ == "__main__":
    unittest.main()
