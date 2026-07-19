from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from importlib import import_module
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

cli = import_module("_orchestrate.cli")
git_ops = import_module("_orchestrate.git_ops")
landing = import_module("_orchestrate.landing")
lanes = import_module("_orchestrate.lanes")
review = import_module("_orchestrate.review")
OrchestrateError = import_module("_orchestrate.primitives").OrchestrateError


def git(root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=False, text=True, capture_output=True
    )
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def init_repo(root: Path, *, object_format: str | None = None) -> str:
    command = ["init", "-b", "main"]
    if object_format is not None:
        command.append(f"--object-format={object_format}")
    git(root, *command)
    git(root, "config", "user.name", "Review Regression")
    git(root, "config", "user.email", "review@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    return git(root, "rev-parse", "HEAD")


class ReviewRegressionTests(unittest.TestCase):
    def test_land_finish_rechecks_task_ref_under_lock_and_merges_exact_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            git(root, "branch", "task/demo", base)
            task = root / ".agent_state" / "worktrees" / "task-demo"
            task.parent.mkdir(parents=True)
            git(root, "worktree", "add", str(task), "task/demo")
            (task / "approved.txt").write_text("approved\n", encoding="utf-8")
            git(task, "add", "approved.txt")
            git(task, "commit", "-m", "approved")
            expected = git(root, "rev-parse", "task/demo")
            (task / "late.txt").write_text("late\n", encoding="utf-8")
            git(task, "add", "late.txt")
            git(task, "commit", "-m", "late")
            late = git(root, "rev-parse", "task/demo")
            git(root, "update-ref", "refs/heads/task/demo", expected)
            declaration = root / ".agent_state" / "landing.json"
            declaration.write_text(
                json.dumps(
                    {
                        "landing_version": 1,
                        "task_id": "demo",
                        "policy": "commit-authorized",
                        "target_ref": "main",
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                root=str(root),
                declaration=str(declaration),
                task_ref="task/demo",
                task_sha=expected,
                confirmed=False,
                message=None,
            )
            before = git(root, "rev-parse", "main")

            def advance_task(lock_root: Path) -> None:
                self.assertEqual(lock_root, root)
                git(root, "update-ref", "refs/heads/task/demo", late)

            with patch.object(landing, "acquire_landing_lock", advance_task):
                with self.assertRaisesRegex(OrchestrateError, "drifted while acquiring"):
                    landing.command_land_finish(args)
            self.assertEqual(git(root, "rev-parse", "main"), before)
            self.assertFalse((root / "late.txt").exists())

    def test_land_finish_verifies_candidate_before_atomic_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            git(root, "branch", "task/demo", base)
            task = root / ".agent_state" / "worktrees" / "task-demo"
            task.parent.mkdir(parents=True)
            git(root, "worktree", "add", str(task), "task/demo")
            (task / "approved.txt").write_text("approved\n", encoding="utf-8")
            git(task, "add", "approved.txt")
            git(task, "commit", "-m", "approved")
            expected = git(root, "rev-parse", "task/demo")
            declaration = root / ".agent_state" / "landing.json"
            declaration.write_text(
                json.dumps(
                    {
                        "landing_version": 1,
                        "task_id": "demo",
                        "policy": "commit-authorized",
                        "target_ref": "main",
                    }
                ),
                encoding="utf-8",
            )
            hook = root / ".git" / "hooks" / "pre-commit"
            hook.write_text(
                "#!/bin/sh\nprintf injected > injected.txt\ngit add injected.txt\n",
                encoding="utf-8",
            )
            hook.chmod(0o755)
            payload = landing.command_land_finish(
                argparse.Namespace(
                    root=str(root),
                    declaration=str(declaration),
                    task_ref="task/demo",
                    task_sha=expected,
                    confirmed=False,
                    message=None,
                )
            )
            self.assertTrue(payload["tree_identity"])
            self.assertEqual(
                git(root, "rev-parse", "main^{tree}"),
                git(root, "rev-parse", f"{expected}^{{tree}}"),
            )
            self.assertFalse((root / "injected.txt").exists())
            self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_cleanup_mutation_gets_release_preflight_but_dry_run_does_not(self) -> None:
        mutation = [
            "--skill-dir",
            str(SKILL),
            "cleanup",
            "--root",
            "/repo",
            "--worktree",
            "/repo/.agent_state/worktrees/demo-a",
        ]
        dry_run = [
            "--skill-dir",
            str(SKILL),
            "cleanup",
            "--root",
            "/repo",
            "--absorbed",
            "--dry-run",
        ]
        payload = {"ok": True}
        with patch.object(cli, "require_release_preflight", return_value={"checked": True}) as preflight:
            with patch.object(cli, "command_cleanup", return_value=payload):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(mutation), 0)
            preflight.assert_called_once()
        with patch.object(cli, "require_release_preflight") as preflight:
            with patch.object(cli, "command_cleanup", return_value=payload):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(dry_run), 0)
            preflight.assert_not_called()

    def test_recovered_review_checkout_rejects_dirt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            args = argparse.Namespace(root=str(root), sha=base, label="base", worktree=None)
            created = review.command_review_checkout(args)
            path = Path(created["path"])
            (path / "untracked.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(OrchestrateError, "dirty"):
                review.command_review_checkout(args)

    def test_lane_create_recovery_rejects_a_different_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = init_repo(root)
            git(root, "checkout", "-b", "other", first)
            (root / "other.txt").write_text("other\n", encoding="utf-8")
            git(root, "add", "other.txt")
            git(root, "commit", "-m", "other")
            second = git(root, "rev-parse", "HEAD")
            git(root, "checkout", "main")
            args = argparse.Namespace(
                root=str(root), task_id="demo", lane="a", base=first, worktree=None
            )
            lanes.command_lane_create(args)
            args.base = second
            with self.assertRaisesRegex(OrchestrateError, "not a recovery"):
                lanes.command_lane_create(args)

    def test_review_audit_tracks_renamed_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            tests = root / "tests"
            tests.mkdir()
            old = tests / "test_old.py"
            old.write_text(
                "def test_keep():\n    assert True\n\ndef test_removed():\n    assert True\n",
                encoding="utf-8",
            )
            git(root, "add", ".")
            git(root, "commit", "-m", "tests")
            base = git(root, "rev-parse", "HEAD")
            new = tests / "test_new.py"
            old.rename(new)
            new.write_text("def test_keep():\n    assert True\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-m", "rename and weaken")
            subject = git(root, "rev-parse", "HEAD")
            payload = review.command_review_audit(
                argparse.Namespace(root=str(root), base=base, subject=subject)
            )
            kinds = {signal["kind"] for signal in payload["signals"]}
            self.assertIn("deleted-test", kinds)
            self.assertIn("assertion-count-decrease", kinds)
            self.assertTrue(payload["manual_review_required"])

    def test_exact_commit_uses_repository_object_format(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe = subprocess.run(
                ["git", "init", "-b", "main", "--object-format=sha256", str(root)],
                check=False,
                text=True,
                capture_output=True,
            )
            if probe.returncode != 0:
                self.skipTest("git sha256 repositories unavailable")
            git(root, "config", "user.name", "SHA256")
            git(root, "config", "user.email", "sha256@example.invalid")
            (root / "a.txt").write_text("a\n", encoding="utf-8")
            git(root, "add", "a.txt")
            git(root, "commit", "-m", "a")
            full = git(root, "rev-parse", "HEAD")
            self.assertEqual(len(full), 64)
            self.assertEqual(git_ops.exact_commit(root, full, label="sha"), full)
            with self.assertRaisesRegex(OrchestrateError, "full 64-character"):
                git_ops.exact_commit(root, full[:40], label="sha")
            git(root, "checkout", "-b", "other")
            (root / "b.txt").write_text("b\n", encoding="utf-8")
            git(root, "add", "b.txt")
            git(root, "commit", "-m", "b")
            other = git(root, "rev-parse", "HEAD")
            self.assertTrue(git_ops.merge_tree_probe(root, full, other)["clean"])

    def test_compose_recovery_requires_the_same_dependency_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            lane_shas = []
            for name in ("a", "b"):
                git(root, "checkout", "-b", name, base)
                (root / f"{name}.txt").write_text(f"{name}\n", encoding="utf-8")
                git(root, "add", f"{name}.txt")
                git(root, "commit", "-m", name)
                lane_shas.append(git(root, "rev-parse", "HEAD"))
            git(root, "checkout", "main")
            args = argparse.Namespace(
                root=str(root), task_id="demo", name="both", base=base, lane=lane_shas
            )
            lanes.command_compose_base(args)
            args.lane = [lane_shas[0]]
            with self.assertRaisesRegex(OrchestrateError, "different lane inputs"):
                lanes.command_compose_base(args)

    def test_compose_recovery_ignores_nested_input_compose_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            lane_shas = []
            for name in ("a", "b", "c"):
                git(root, "checkout", "-b", name, base)
                (root / f"{name}.txt").write_text(f"{name}\n", encoding="utf-8")
                git(root, "add", f"{name}.txt")
                git(root, "commit", "-m", name)
                lane_shas.append(git(root, "rev-parse", "HEAD"))
            git(root, "checkout", "main")
            inner = lanes.command_compose_base(
                argparse.Namespace(
                    root=str(root),
                    task_id="demo",
                    name="inner",
                    base=base,
                    lane=lane_shas[:2],
                )
            )["composite_sha"]
            args = argparse.Namespace(
                root=str(root),
                task_id="demo",
                name="outer",
                base=base,
                lane=[inner, lane_shas[2]],
            )
            first = lanes.command_compose_base(args)
            recovered = lanes.command_compose_base(args)
            self.assertEqual(recovered["recovered"], "already-composed")
            self.assertEqual(recovered["composite_sha"], first["composite_sha"])

    def test_review_advance_rejects_unrelated_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = init_repo(root)
            created = review.command_review_checkout(
                argparse.Namespace(root=str(root), sha=first, label="chain", worktree=None)
            )
            git(root, "checkout", "--orphan", "unrelated")
            git(root, "rm", "-rf", ".")
            (root / "other.txt").write_text("other\n", encoding="utf-8")
            git(root, "add", "other.txt")
            git(root, "commit", "-m", "unrelated")
            unrelated = git(root, "rev-parse", "HEAD")
            args = argparse.Namespace(
                root=str(root),
                worktree=created["path"],
                from_sha=first,
                to_sha=unrelated,
            )
            with self.assertRaisesRegex(OrchestrateError, "must descend"):
                review.command_review_advance(args)

    def test_landing_guidance_uses_exact_target_cleanup(self) -> None:
        source = (SCRIPTS / "_orchestrate" / "landing.py").read_text(encoding="utf-8")
        self.assertNotIn("cleanup --absorbed", source)
        self.assertIn("safe-to-remove exact --worktree", source)


if __name__ == "__main__":
    unittest.main()
