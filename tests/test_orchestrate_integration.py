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
            [sys.executable, str(SCRIPT), *args],
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

    def error_payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
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

    def integration_create(self, task_id: str | None = None, base: str | None = None) -> dict[str, object]:
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
        self.assertEqual(created["worktree"], str(self.root / ".agent_state" / "worktrees" / f"{self.task_id}-integration"))
        self.assertEqual(created["base"], self.base)
        self.assertTrue(created["clean"])

        lane_a = self.lane_create("lane-a", self.base)
        sha_a = self.commit_lane(lane_a, "lane a\n")
        collect_a = self.collect("lane-a", sha_a)
        self.assertEqual(collect_a["operation"], "integration-collect")
        self.assertEqual(collect_a["lane_id"], "lane-a")

        integration_tip = self.git(integration_path, "rev-parse", "HEAD")
        lane_b = self.lane_create("lane-b", integration_tip)
        sha_b = self.commit_lane(lane_b, "lane a\nlane b\n", date="2025-01-01T00:02:00+0000")
        collect_b = self.collect("lane-b", sha_b)

        status = self.status()
        self.assertEqual(status["operation"], "integration-status")
        self.assertTrue(status["exists"])
        self.assertEqual(status["head"], collect_b["collect_sha"])
        self.assertEqual(
            status["collected"],
            [
                {"lane": "lane-a", "collect_sha": collect_a["collect_sha"], "sha": sha_a},
                {"lane": "lane-b", "collect_sha": collect_b["collect_sha"], "sha": sha_b},
            ],
        )

    def test_collect_rejects_a_dirty_integration_worktree_and_a_re_collected_lane(self) -> None:
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

    def test_conflict_stays_visible_in_integration_worktree(self) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))

        lane_a = self.lane_create("lane-a", self.base)
        sha_a = self.commit_lane(lane_a, "lane a\n")
        self.collect("lane-a", sha_a)

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
        self.assertIn("git integration collect failed", str(error["error"]))
        self.assertIn("UU app.txt", self.git(integration_path, "status", "--porcelain"))
        self.assertTrue((integration_path / ".git").is_file())
        self.assertEqual(self.git(integration_path, "rev-parse", "--verify", "MERGE_HEAD"), sha_b)
        # A real 3-way conflict carries the shared ancestor at stage 1, unlike
        # a synthetic add/add conflict which has no common ancestor at all.
        self.assertEqual(self.git(integration_path, "show", ":1:app.txt"), "base")
        # Non-destructive: the lane worktree is not removed on a failed collect.
        self.assertTrue(lane_b.exists())

    def test_create_refuses_existing_path_or_branch_and_remove_refuses_dirty(self) -> None:
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

        integration_path = self.root / ".agent_state" / "worktrees" / f"{self.task_id}-integration"
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
        self.assertEqual(self.git(self.root, "rev-parse", "--verify", self.base_ref), landed_base)

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
        sha = self.commit_lane(lane, "lane a\n", date="2025-01-01T00:03:00+0000")
        collected = self.collect("lane-a", sha)
        self.assertEqual(collected["immutable_paths_verified"], ["contract_test.py"])

    def test_collect_refuses_a_weakened_or_relocated_acceptance_surface_without_redeclaration(
        self,
    ) -> None:
        self.integration_create()
        lane, _declaring_sha = self.prepare_declared_lane("lane-a")

        (lane / "contract_test.py").write_text("assert True\n", encoding="utf-8")
        self.git(lane, "add", "contract_test.py")
        weakened = self.commit_lane(lane, "lane a\n", "weaken", date="2025-01-01T00:03:00+0000")
        weakened_error = self.error_payload(
            self.cli(
                self.root, "integration", "collect", "--root", str(self.root),
                "--task-id", self.task_id, "--lane-id", "lane-a", "--sha", weakened,
            )
        )
        self.assertIn("without redeclaring", str(weakened_error["error"]))
        self.assertIn("contract_test.py", str(weakened_error["error"]))
        self.assertIn(weakened, str(weakened_error["error"]))

        self.git(lane, "mv", "contract_test.py", "moved_contract_test.py")
        relocated = self.commit_lane(lane, "lane a moved\n", "relocate", date="2025-01-01T00:04:00+0000")
        relocated_error = self.error_payload(
            self.cli(
                self.root, "integration", "collect", "--root", str(self.root),
                "--task-id", self.task_id, "--lane-id", "lane-a", "--sha", relocated,
            )
        )
        self.assertIn("without redeclaring", str(relocated_error["error"]))
        self.assertIn("contract_test.py", str(relocated_error["error"]))
        self.assertIn(relocated, str(relocated_error["error"]))

    def test_status_fails_closed_without_the_base_ref(self) -> None:
        self.integration_create()
        self.git(self.root, "update-ref", "-d", self.base_ref)

        error = self.error_payload(
            self.cli(self.root, "integration", "status", "--root", str(self.root), "--task-id", self.task_id)
        )
        self.assertIn("integration base ref is missing", str(error["error"]))


if __name__ == "__main__":
    unittest.main()
