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
    task_id = "integration-task"
    base_ref = f"refs/orchestrate/{task_id}/integration/base"

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

    def implementation_create(self, wave_id: str, base: str) -> Path:
        payload = self.payload(
            self.cli(
                self.root,
                "worktree",
                "create",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--wave-id",
                wave_id,
                "--role",
                "implementation",
                "--base",
                base,
            )
        )
        return Path(str(payload["worktree"]))

    def commit_implementation(
        self,
        worktree: Path,
        wave_id: str,
        slice_id: str,
        content: str,
        *,
        role: str = "implementation",
        include_trailers: bool = True,
        date: str = "2025-01-01T00:01:00+0000",
    ) -> str:
        (worktree / "app.txt").write_text(content, encoding="utf-8")
        self.git(worktree, "add", "app.txt")
        if include_trailers:
            message = f"Implementation ready {wave_id}\n\nWave: {wave_id}\nSlice: {slice_id}\nRole: {role}"
        else:
            message = f"Implementation ready {wave_id}"
        self.git(
            worktree,
            "commit",
            "-q",
            "-m",
            message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return self.git(worktree, "rev-parse", "HEAD")

    def collect(self, wave_id: str, implementation_sha: str) -> dict[str, object]:
        return self.payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--wave-id",
                wave_id,
                "--implementation-sha",
                implementation_sha,
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

    def test_create_collect_status_tracks_two_waves_in_git_order(self) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))
        self.assertEqual(created["operation"], "integration-create")
        self.assertEqual(created["branch"], f"wave/{self.task_id}/integration")
        self.assertEqual(created["worktree"], str(self.root / ".agent_state" / "worktrees" / f"{self.task_id}-integration"))
        self.assertEqual(created["base"], self.base)
        self.assertTrue(created["clean"])

        wave_a_tree = self.implementation_create("wave-a", self.base)
        implementation_a = self.commit_implementation(wave_a_tree, "wave-a", "slice-a", "wave a\n")
        collect_a = self.collect("wave-a", implementation_a)
        self.assertEqual(collect_a["operation"], "integration-collect")
        self.assertEqual(collect_a["slice"], "slice-a")

        integration_tip = self.git(integration_path, "rev-parse", "HEAD")
        wave_b_tree = self.implementation_create("wave-b", integration_tip)
        implementation_b = self.commit_implementation(
            wave_b_tree,
            "wave-b",
            "slice-b",
            "wave b\n",
            date="2025-01-01T00:02:00+0000",
        )
        collect_b = self.collect("wave-b", implementation_b)

        status = self.status()
        self.assertEqual(status["operation"], "integration-status")
        self.assertTrue(status["exists"])
        self.assertEqual(status["head"], collect_b["collect_sha"])
        self.assertEqual(
            status["collected"],
            [
                {
                    "wave": "wave-a",
                    "slice": "slice-a",
                    "collect_sha": collect_a["collect_sha"],
                    "implementation_sha": implementation_a,
                },
                {
                    "wave": "wave-b",
                    "slice": "slice-b",
                    "collect_sha": collect_b["collect_sha"],
                    "implementation_sha": implementation_b,
                },
            ],
        )

    def test_collect_rejects_bad_trailers_dirty_worktree_and_duplicate_wave(self) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))

        missing_tree = self.implementation_create("missing", self.base)
        missing_sha = self.commit_implementation(missing_tree, "missing", "slice", "missing\n", include_trailers=False)
        error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--wave-id",
                "missing",
                "--implementation-sha",
                missing_sha,
            )
        )
        self.assertIn("Role: implementation", str(error["error"]))

        wrong_role_tree = self.implementation_create("wrong-role", self.base)
        wrong_role_sha = self.commit_implementation(
            wrong_role_tree,
            "wrong-role",
            "slice",
            "wrong role\n",
            role="oracle",
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
                "--wave-id",
                "wrong-role",
                "--implementation-sha",
                wrong_role_sha,
            )
        )
        self.assertIn("Role: implementation", str(error["error"]))

        mismatch_tree = self.implementation_create("mismatch", self.base)
        mismatch_sha = self.commit_implementation(mismatch_tree, "mismatch", "slice", "mismatch\n")
        error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--wave-id",
                "different-wave",
                "--implementation-sha",
                mismatch_sha,
            )
        )
        self.assertIn("matching Wave", str(error["error"]))

        good_tree = self.implementation_create("good", self.base)
        good_sha = self.commit_implementation(good_tree, "good", "slice", "good\n")
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
                "--wave-id",
                "good",
                "--implementation-sha",
                good_sha,
            )
        )
        self.assertIn("must be clean", str(error["error"]))
        (integration_path / "dirty.txt").unlink()
        self.collect("good", good_sha)

        error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--wave-id",
                "good",
                "--implementation-sha",
                good_sha,
            )
        )
        self.assertIn("already collected", str(error["error"]))

    def test_conflict_stays_visible_in_integration_worktree(self) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))

        wave_a_tree = self.implementation_create("wave-a", self.base)
        implementation_a = self.commit_implementation(wave_a_tree, "wave-a", "slice-a", "wave a\n")
        self.collect("wave-a", implementation_a)

        wave_b_tree = self.implementation_create("wave-b", self.base)
        implementation_b = self.commit_implementation(wave_b_tree, "wave-b", "slice-b", "wave b\n")
        error = self.error_payload(
            self.cli(
                self.root,
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--wave-id",
                "wave-b",
                "--implementation-sha",
                implementation_b,
            )
        )
        self.assertIn("git integration collect failed", str(error["error"]))
        self.assertIn("UU app.txt", self.git(integration_path, "status", "--porcelain"))
        self.assertTrue((integration_path / ".git").is_file())
        self.assertEqual(self.git(integration_path, "rev-parse", "--verify", "MERGE_HEAD"), implementation_b)

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
            "Collect Wave wave-a\n\nWave: wave-a\nSlice: slice-a\nRole: collect",
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

        # The reused wave id belongs to the previous task, so it must not be rejected here.
        wave_tree = self.implementation_create("wave-a", landed_base)
        implementation = self.commit_implementation(wave_tree, "wave-a", "slice-a", "wave a\n")
        collected = self.collect("wave-a", implementation)
        self.assertEqual(
            self.status()["collected"],
            [
                {
                    "wave": "wave-a",
                    "slice": "slice-a",
                    "collect_sha": collected["collect_sha"],
                    "implementation_sha": implementation,
                }
            ],
        )

    def prepare_declared_contract(self, wave_id: str) -> tuple[Path, str]:
        """Merge a Contract that declares one immutable acceptance-surface path."""
        oracle = Path(
            str(
                self.payload(
                    self.cli(
                        self.root, "worktree", "create", "--root", str(self.root),
                        "--task-id", self.task_id, "--wave-id", wave_id,
                        "--role", "oracle", "--base", self.base,
                    )
                )["worktree"]
            )
        )
        implementation = self.implementation_create(wave_id, self.base)
        (oracle / "contract_test.py").write_text("assert app == 1\n", encoding="utf-8")
        self.git(oracle, "add", "contract_test.py")
        self.git(
            oracle,
            "commit",
            "-q",
            "-m",
            f"Contract ready\n\nWave: {wave_id}\nSlice: slice-a\nRole: oracle\nImmutable: contract_test.py",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:01:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:01:00+0000",
            },
        )
        contract_sha = self.git(oracle, "rev-parse", "HEAD")
        self.payload(
            self.cli(
                self.root, "contract", "merge", "--root", str(self.root),
                "--task-id", self.task_id, "--wave-id", wave_id,
                "--contract-sha", contract_sha,
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:02:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:02:00+0000",
                },
            )
        )
        return implementation, contract_sha

    def test_collect_verifies_the_declared_immutable_surface(self) -> None:
        self.integration_create()
        implementation, _ = self.prepare_declared_contract("wave-a")

        # Filling production behavior leaves the declared surface byte-identical.
        implementation_sha = self.commit_implementation(
            implementation, "wave-a", "slice-a", "wave a\n", date="2025-01-01T00:03:00+0000"
        )
        collected = self.collect("wave-a", implementation_sha)
        self.assertEqual(collected["immutable_paths_verified"], ["contract_test.py"])
        self.assertEqual(
            collected["contract_merge_sha"],
            self.git(implementation, "rev-parse", "HEAD~1"),
        )

    def test_collect_refuses_a_weakened_or_relocated_acceptance_surface(self) -> None:
        self.integration_create()
        implementation, _ = self.prepare_declared_contract("wave-a")

        (implementation / "contract_test.py").write_text("assert True\n", encoding="utf-8")
        self.git(implementation, "add", "contract_test.py")
        weakened = self.commit_implementation(
            implementation, "wave-a", "slice-a", "wave a\n", date="2025-01-01T00:03:00+0000"
        )
        weakened_error = self.error_payload(
            self.cli(
                self.root, "integration", "collect", "--root", str(self.root),
                "--task-id", self.task_id, "--wave-id", "wave-a",
                "--implementation-sha", weakened,
            )
        )
        self.assertIn("Oracle-owned acceptance surface", str(weakened_error["error"]))
        self.assertIn("contract_test.py", str(weakened_error["error"]))

        self.git(implementation, "mv", "contract_test.py", "moved_contract_test.py")
        relocated = self.commit_implementation(
            implementation, "wave-a", "slice-a", "wave a moved\n", date="2025-01-01T00:04:00+0000"
        )
        relocated_error = self.error_payload(
            self.cli(
                self.root, "integration", "collect", "--root", str(self.root),
                "--task-id", self.task_id, "--wave-id", "wave-a",
                "--implementation-sha", relocated,
            )
        )
        self.assertIn("deleted or relocated", str(relocated_error["error"]))

    def test_status_and_collect_fail_closed_without_the_base_ref(self) -> None:
        self.integration_create()
        self.git(self.root, "update-ref", "-d", self.base_ref)

        wave_tree = self.implementation_create("wave-a", self.base)
        implementation = self.commit_implementation(wave_tree, "wave-a", "slice-a", "wave a\n")
        for arguments in (
            ("integration", "status", "--root", str(self.root), "--task-id", self.task_id),
            (
                "integration",
                "collect",
                "--root",
                str(self.root),
                "--task-id",
                self.task_id,
                "--wave-id",
                "wave-a",
                "--implementation-sha",
                implementation,
            ),
        ):
            error = self.error_payload(self.cli(self.root, *arguments))
            self.assertIn("integration base ref is missing", str(error["error"]))


if __name__ == "__main__":
    unittest.main()
