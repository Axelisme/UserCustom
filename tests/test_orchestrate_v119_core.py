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


class V119CoreContractTests(unittest.TestCase):
    """Black-box Root contract for the v119 Git-only core tracer.

    These tests deliberately invoke the shipped entrypoint rather than importing
    implementation helpers.  The implementation may change every production path;
    this file, and any fixture/adapters it gains, are Oracle-owned acceptance.
    """

    task_id = "demo-task"
    wave_id = "wave-a"

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
        command = [
            sys.executable,
            str(SCRIPT),
            *args,
        ]
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            command, cwd=root, text=True, capture_output=True, check=False,
            env=merged_env,
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"success was not one JSON object: {result.stdout!r}: {exc}")
        self.assertIsInstance(value, dict)
        self.assertTrue(value.get("ok"), value)
        return value

    def error_payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
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

    def init_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "config", "user.name", "Oracle Test")
        self.git(root, "config", "user.email", "oracle@example.test")
        (root / "README").write_text("base\n", encoding="utf-8")
        self.git(root, "add", "README")
        self.git(
            root,
            "commit",
            "-q",
            "-m",
            "base",
            env=None,
        )
        return temporary, root, self.git(root, "rev-parse", "HEAD")

    def commit_file(
        self, cwd: Path, path: str, content: str, message: str, date: str | None = None
    ) -> str:
        target = cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(cwd, "add", path)
        env = None
        if date:
            env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        result = subprocess.run(
            ["git", "commit", "-q", "-m", message],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.git(cwd, "rev-parse", "HEAD")

    def create_worktree(self, root: Path, role: str) -> dict[str, object]:
        result = self.cli(
            root,
            "worktree", "create", "--root", str(root), "--task-id", self.task_id,
            "--wave-id", self.wave_id, "--role", role, "--base", self.base,
        )
        return self.payload(result)

    def setUp(self) -> None:
        self.temporary, self.root, self.base = self.init_repo()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_help_exposes_only_v119_workflow_and_administration(self) -> None:
        result = self.cli(self.root, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("worktree", "contract", "profile", "release", "doctor", "diff", "pin"):
            self.assertIn(command, result.stdout)
        for command in ("lane", "compose-base", "collect", "findings", "land", "review"):
            self.assertNotIn(command, result.stdout)

    def test_create_status_remove_each_role_is_live_and_deterministic(self) -> None:
        oracle = self.create_worktree(self.root, "oracle")
        implementation = self.create_worktree(self.root, "implementation")
        expected_root = self.root / ".agent_state" / "worktrees"
        for role, payload in (("oracle", oracle), ("implementation", implementation)):
            expected_branch = f"wave/{self.task_id}/{self.wave_id}/{role}"
            expected_path = expected_root / f"{self.task_id}-{self.wave_id}-{role}"
            self.assertEqual(payload["operation"], "worktree-create")
            self.assertEqual(payload["branch"], expected_branch)
            self.assertEqual(payload["worktree"], str(expected_path))
            self.assertEqual(payload["base"], self.base)
            self.assertEqual(payload["head"], self.base)
            self.assertTrue(payload["clean"])
            self.assertTrue(expected_path.is_dir())
            self.assertEqual(self.git(self.root, "rev-parse", expected_branch), self.base)

            status = self.payload(self.cli(
                self.root, "worktree", "status", "--root", str(self.root),
                "--task-id", self.task_id, "--wave-id", self.wave_id, "--role", role,
            ))
            self.assertEqual(status["operation"], "worktree-status")
            self.assertTrue(status["exists"])
            self.assertEqual(status["path"], str(expected_path))
            self.assertEqual(status["branch"], expected_branch)
            self.assertEqual(status["head"], self.base)
            self.assertEqual(status["tree"], "clean")
            self.assertTrue(status["clean"])

        # Removal is per role and deliberately leaves its branch behind.
        removed = self.payload(self.cli(
            self.root, "worktree", "remove", "--root", str(self.root),
            "--task-id", self.task_id, "--wave-id", self.wave_id, "--role", "oracle",
        ))
        self.assertEqual(removed["operation"], "worktree-remove")
        self.assertFalse((expected_root / f"{self.task_id}-{self.wave_id}-oracle").exists())
        self.assertEqual(
            self.git(self.root, "rev-parse", f"wave/{self.task_id}/{self.wave_id}/oracle"),
            self.base,
        )

    def test_create_refuses_existing_derived_branch_or_path(self) -> None:
        first = self.create_worktree(self.root, "oracle")
        duplicate = self.error_payload(self.cli(
            self.root, "worktree", "create", "--root", str(self.root), "--task-id",
            self.task_id, "--wave-id", self.wave_id, "--role", "oracle", "--base", self.base,
        ))
        self.assertIn("already exists", str(duplicate["error"]))
        self.assertEqual(first["head"], self.base)
        self.assertEqual(self.git(self.root, "worktree", "list", "--porcelain").count("wave/demo-task/wave-a/oracle"), 1)

        # A pre-existing path is rejected even when its branch is otherwise free.
        path = self.root / ".agent_state" / "worktrees" / "demo-task-wave-a-implementation"
        path.mkdir(parents=True)
        duplicate_path = self.error_payload(self.cli(
            self.root, "worktree", "create", "--root", str(self.root), "--task-id",
            self.task_id, "--wave-id", self.wave_id, "--role", "implementation", "--base", self.base,
        ))
        self.assertIn("already exists", str(duplicate_path["error"]))

    def test_dirty_removal_and_dirty_contract_merge_are_non_destructive(self) -> None:
        oracle = self.create_worktree(self.root, "oracle")
        implementation = self.create_worktree(self.root, "implementation")
        oracle_path = Path(str(oracle["worktree"]))
        implementation_path = Path(str(implementation["worktree"]))
        (implementation_path / "uncommitted").write_text("keep me\n", encoding="utf-8")
        error = self.error_payload(self.cli(
            self.root, "worktree", "remove", "--root", str(self.root), "--task-id",
            self.task_id, "--wave-id", self.wave_id, "--role", "implementation",
        ))
        self.assertIn("clean", str(error["error"]))
        self.assertTrue(implementation_path.exists())
        self.assertEqual(self.git(implementation_path, "status", "--porcelain"), "?? uncommitted")

        contract = self.commit_file(
            oracle_path, "public/interface.py", "CONTRACT = True\n", "contract\nWave: wave-a\nSlice: core-git-tracer\nRole: oracle\n"
        )
        merge_error = self.error_payload(self.cli(
            self.root, "contract", "merge", "--root", str(self.root), "--task-id",
            self.task_id, "--wave-id", self.wave_id, "--contract-sha", contract,
        ))
        self.assertIn("clean", str(merge_error["error"]))
        self.assertEqual(self.git(implementation_path, "rev-parse", "HEAD"), self.base)
        self.assertFalse((implementation_path / "public/interface.py").exists())
        merge_head = Path(self.git(implementation_path, "rev-parse", "--git-path", "MERGE_HEAD"))
        self.assertFalse(merge_head.exists())

    def test_exact_no_ff_contract_merge_preserves_ancestry_and_merge_trailers(self) -> None:
        self.create_worktree(self.root, "implementation")
        oracle_path = Path(str(self.create_worktree(self.root, "oracle")["worktree"]))
        contract = self.commit_file(
            oracle_path, "shared/public_api.py", "VALUE = 1\n", "publish contract\nWave: wave-a\nSlice: core-git-tracer\nRole: oracle\n", "2025-01-01T00:01:00+0000"
        )
        merged = self.payload(self.cli(
            self.root, "contract", "merge", "--root", str(self.root), "--task-id",
            self.task_id, "--wave-id", self.wave_id, "--contract-sha", contract,
            env={"GIT_AUTHOR_DATE": "2025-01-01T00:02:00+0000", "GIT_COMMITTER_DATE": "2025-01-01T00:02:00+0000"},
        ))
        implementation_path = self.root / ".agent_state" / "worktrees" / "demo-task-wave-a-implementation"
        head = self.git(implementation_path, "rev-parse", "HEAD")
        parents = self.git(implementation_path, "rev-list", "--parents", "-n", "1", head).split()
        self.assertEqual(merged["operation"], "contract-merge")
        self.assertEqual(merged["contract_sha"], contract)
        self.assertEqual(merged["merge_sha"], head)
        self.assertEqual(len(parents), 3)
        self.assertEqual(parents[1], self.base)
        self.assertEqual(parents[2], contract)
        self.assertEqual(self.git(implementation_path, "show", "-s", "--format=%(trailers:key=Wave,valueonly)", head), "wave-a")
        self.assertEqual(self.git(implementation_path, "show", "-s", "--format=%(trailers:key=Slice,valueonly)", head), "core-git-tracer")
        self.assertEqual(self.git(implementation_path, "show", "-s", "--format=%(trailers:key=Role,valueonly)", head), "merge")

    def test_merge_conflict_remains_in_ordinary_git_conflict_state(self) -> None:
        implementation = self.create_worktree(self.root, "implementation")
        oracle = self.create_worktree(self.root, "oracle")
        implementation_path = Path(str(implementation["worktree"]))
        oracle_path = Path(str(oracle["worktree"]))
        self.commit_file(implementation_path, "shared/conflict.txt", "implementation\n", "implementation base")
        contract = self.commit_file(
            oracle_path, "shared/conflict.txt", "oracle\n", "conflicting contract\nWave: wave-a\nSlice: core-git-tracer\nRole: oracle\n"
        )
        result = self.cli(
            self.root, "contract", "merge", "--root", str(self.root), "--task-id",
            self.task_id, "--wave-id", self.wave_id, "--contract-sha", contract,
        )
        self.error_payload(result)
        merge_head = Path(self.git(implementation_path, "rev-parse", "--git-path", "MERGE_HEAD"))
        self.assertTrue(merge_head.exists())
        self.assertIn("UU shared/conflict.txt", self.git(implementation_path, "status", "--porcelain"))

    def test_profile_report_classifies_repeated_attempts_intervals_numstat_and_warnings(self) -> None:
        implementation = self.create_worktree(self.root, "implementation")
        oracle = self.create_worktree(self.root, "oracle")
        oracle_path = Path(str(oracle["worktree"]))
        implementation_path = Path(str(implementation["worktree"]))
        first = self.commit_file(
            oracle_path, "shared/api.py", "VERSION = 1\n", "first contract\nWave: wave-a\nSlice: core-git-tracer\nRole: oracle\n", "2025-01-01T00:01:00+0000"
        )
        self.payload(self.cli(
            self.root, "contract", "merge", "--root", str(self.root), "--task-id", self.task_id,
            "--wave-id", self.wave_id, "--contract-sha", first,
            env={"GIT_AUTHOR_DATE": "2025-01-01T00:02:00+0000", "GIT_COMMITTER_DATE": "2025-01-01T00:02:00+0000"},
        ))
        self.commit_file(
            implementation_path, "shared/impl.py", "IMPLEMENTED = 1\n", "implementation\nWave: wave-a\nSlice: core-git-tracer\nRole: implementation\n", "2025-01-01T00:03:00+0000"
        )
        second = self.commit_file(
            oracle_path, "shared/api.py", "VERSION = 2\n", "corrected contract\nWave: wave-a\nSlice: core-git-tracer\nRole: oracle\n", "2025-01-01T00:02:30+0000"
        )
        self.payload(self.cli(
            self.root, "contract", "merge", "--root", str(self.root), "--task-id", self.task_id,
            "--wave-id", self.wave_id, "--contract-sha", second,
            env={"GIT_AUTHOR_DATE": "2025-01-01T00:04:00+0000", "GIT_COMMITTER_DATE": "2025-01-01T00:04:00+0000"},
        ))
        self.commit_file(
            implementation_path, "shared/impl.py", "IMPLEMENTED = 2\n", "implementation correction\nWave: wave-a\nSlice: core-git-tracer\nRole: implementation\n", "2025-01-01T00:05:00+0000"
        )
        report = self.payload(self.cli(
            self.root, "profile", "report", "--root", str(self.root), "--task-id", self.task_id,
            "--wave-id", self.wave_id, "--base", self.base,
        ))
        self.assertEqual(report["operation"], "profile-report")
        self.assertEqual(report["base"], self.base)
        self.assertIn("warnings", report)
        self.assertTrue(any("non-monotonic" in warning for warning in report["warnings"]))
        slice_report = report["slices"]["core-git-tracer"]
        self.assertEqual(len(slice_report["attempts"]), 2)
        self.assertIsNone(slice_report["oracle_interval_seconds"])
        self.assertGreaterEqual(slice_report["handoff_interval_seconds"], 0)
        self.assertGreaterEqual(slice_report["implementation_interval_seconds"], 0)
        self.assertEqual(slice_report["contract_numstat"], {"files": 2, "insertions": 2, "deletions": 0})
        self.assertEqual(slice_report["implementation_numstat"], {"files": 1, "insertions": 2, "deletions": 1})
        self.assertEqual(report["wave"]["contract_numstat"], slice_report["contract_numstat"])
        self.assertEqual(report["wave"]["implementation_numstat"], slice_report["implementation_numstat"])
        self.assertNotIn("active_time", json.dumps(report))
        self.assertNotIn("queue_time", json.dumps(report))

    def test_profile_accepts_shared_production_paths_and_status_projects_dirty_tree(self) -> None:
        oracle = self.create_worktree(self.root, "oracle")
        implementation = self.create_worktree(self.root, "implementation")
        oracle_path = Path(str(oracle["worktree"]))
        implementation_path = Path(str(implementation["worktree"]))
        contract = self.commit_file(
            oracle_path, "src/shared.py", "PUBLIC = 1\n", "contract\nWave: wave-a\nSlice: core-git-tracer\nRole: oracle\n"
        )
        self.payload(self.cli(
            self.root, "contract", "merge", "--root", str(self.root), "--task-id", self.task_id,
            "--wave-id", self.wave_id, "--contract-sha", contract,
        ))
        self.commit_file(implementation_path, "src/shared.py", "PUBLIC = 2\nPRIVATE = 3\n", "implementation\nWave: wave-a\nSlice: core-git-tracer\nRole: implementation\n")
        (implementation_path / "dirty.txt").write_text("not committed\n", encoding="utf-8")
        status = self.payload(self.cli(
            self.root, "worktree", "status", "--root", str(self.root), "--task-id", self.task_id,
            "--wave-id", self.wave_id, "--role", "implementation",
        ))
        self.assertEqual(status["tree"], "dirty")
        self.assertFalse(status["clean"])
        self.assertEqual(status["changed_paths"], ["dirty.txt"])

    def test_missing_status_and_invalid_base_are_json_errors_without_writes(self) -> None:
        status = self.payload(self.cli(
            self.root, "worktree", "status", "--root", str(self.root), "--task-id", self.task_id,
            "--wave-id", self.wave_id, "--role", "oracle",
        ))
        self.assertEqual(status["operation"], "worktree-status")
        self.assertFalse(status["exists"])
        self.assertFalse((self.root / ".agent_state").exists())
        error = self.error_payload(self.cli(
            self.root, "worktree", "create", "--root", str(self.root), "--task-id", self.task_id,
            "--wave-id", self.wave_id, "--role", "oracle", "--base", "0" * 40,
        ))
        self.assertIn("base", str(error["error"]).lower())
        self.assertFalse((self.root / ".agent_state").exists())


if __name__ == "__main__":
    unittest.main()
