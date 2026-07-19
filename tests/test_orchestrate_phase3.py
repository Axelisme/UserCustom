from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


def run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--root", str(root)],
        check=False,
        text=True,
        capture_output=True,
    )


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=False, text=True, capture_output=True
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def init_repo(root: Path) -> str:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Phase 3")
    git(root, "config", "user.email", "phase3@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")
    return git(root, "rev-parse", "HEAD")


def commit_tree(root: Path, tree: str, *parents: str, message: str) -> str:
    command = ["git", "commit-tree", tree]
    for parent in parents:
        command.extend(["-p", parent])
    result = subprocess.run(
        command,
        cwd=root,
        input=message + "\n",
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class Phase3OrchestrateTests(unittest.TestCase):
    def test_revalidate_is_read_only_and_reports_merge_tree_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            git(root, "branch", "agent/demo/a", base)
            lane = root / "lane"
            git(root, "worktree", "add", str(lane), "agent/demo/a")
            (lane / "a.txt").write_text("a\n", encoding="utf-8")
            git(lane, "add", "a.txt")
            git(lane, "commit", "-m", "lane")
            recorded = git(root, "rev-parse", "agent/demo/a")
            (lane / "a.txt").write_text("a follow-up\n", encoding="utf-8")
            git(lane, "add", "a.txt")
            git(lane, "commit", "-m", "follow-up")
            final = git(root, "rev-parse", "agent/demo/a")

            merge_tree = git(root, "merge-tree", "--write-tree", base, recorded)
            composite = commit_tree(
                root,
                merge_tree.splitlines()[0],
                base,
                recorded,
                message="spec\n\nSpeculative-Base: true\nDepends-Lane: " + recorded,
            )
            successor_tree = git(root, "write-tree")
            successor = commit_tree(
                root,
                successor_tree,
                composite,
                message="successor",
            )
            before = git(root, "show-ref")
            result = run_cli(
                root,
                "revalidate",
                "--task-ref",
                "task/demo",
                "--composite",
                composite,
                "--successor",
                successor,
                "--lane",
                final,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["read_only"])
            self.assertEqual(payload["deps"][0]["recorded"], recorded)
            self.assertEqual(payload["deps"][0]["final"], final)
            self.assertTrue(payload["deps"][0]["follow_up_present"])
            self.assertIn("a.txt", payload["deps"][0]["follow_up_paths"])
            self.assertFalse(payload["deps"][0]["final_on_task"])
            self.assertTrue(payload["recompose_needed"])
            self.assertEqual(git(root, "show-ref"), before)

    def test_revalidate_rejects_missing_unused_and_non_descending_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            git(root, "branch", "agent/demo/a", base)
            lane = root / "lane"
            git(root, "worktree", "add", str(lane), "agent/demo/a")
            (lane / "a.txt").write_text("a\n", encoding="utf-8")
            git(lane, "add", "a.txt")
            git(lane, "commit", "-m", "lane")
            recorded = git(root, "rev-parse", "agent/demo/a")
            tree = git(root, "merge-tree", "--write-tree", base, recorded).splitlines()[0]
            composite = commit_tree(
                root,
                tree,
                base,
                recorded,
                message="spec\n\nSpeculative-Base: true\nDepends-Lane: " + recorded,
            )
            successor = commit_tree(root, git(root, "rev-parse", f"{composite}^{{tree}}"), composite, message="successor")
            before = git(root, "show-ref")
            missing = run_cli(
                root,
                "revalidate",
                "--task-ref",
                "task/demo",
                "--composite",
                composite,
                "--successor",
                successor,
                "--lane",
                base,
            )
            self.assertEqual(missing.returncode, 2)
            self.assertIn("missing final predecessor", missing.stderr)
            non_descending = run_cli(
                root,
                "revalidate",
                "--task-ref",
                "task/demo",
                "--composite",
                composite,
                "--successor",
                base,
                "--lane",
                recorded,
            )
            self.assertEqual(non_descending.returncode, 2)
            self.assertIn("successor must descend", non_descending.stderr)
            self.assertEqual(git(root, "show-ref"), before)

    def test_review_audit_reports_mechanical_test_integrity_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            path = root / "tests" / "test_sample.py"
            path.parent.mkdir()
            path.write_text(
                "def test_kept():\n    assert 1 == 1\n\ndef test_deleted():\n    assert 2 == 2\n",
                encoding="utf-8",
            )
            git(root, "add", "tests/test_sample.py")
            git(root, "commit", "-m", "tests")
            subject_base = git(root, "rev-parse", "HEAD")
            path.write_text(
                "import pytest\n\ndef test_kept():\n    pytest.skip('temporary')\n    return\n",
                encoding="utf-8",
            )
            git(root, "add", "tests/test_sample.py")
            git(root, "commit", "-m", "weaken tests")
            subject = git(root, "rev-parse", "HEAD")
            result = run_cli(
                root,
                "review",
                "audit",
                "--base",
                subject_base,
                "--subject",
                subject,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            kinds = {signal["kind"] for signal in payload["signals"]}
            self.assertTrue({"deleted-test", "added-skip", "added-early-return"} <= kinds)
            self.assertTrue(payload["manual_review_required"])
            self.assertEqual(payload["base_sha"], subject_base)
            self.assertEqual(payload["subject_sha"], subject)

    def test_reconcile_uses_structured_classifier_and_dirty_is_not_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            git(root, "branch", "agent/demo/a", base)
            lane = root / ".agent_state" / "worktrees" / "demo-a"
            lane.parent.mkdir(parents=True)
            git(root, "worktree", "add", str(lane), "agent/demo/a")
            (lane / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            result = run_cli(root, "reconcile")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            entry = next(item for item in payload["worktrees"] if item["branch"] == "agent/demo/a")
            self.assertEqual(entry["class"], "active")
            self.assertFalse(entry["cleanup_eligible"])
            self.assertTrue(entry["dirty"])

    def test_reconcile_distinguishes_prerequisite_debt_from_run_ahead(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            managed = root / ".agent_state" / "worktrees"
            managed.mkdir(parents=True)
            git(root, "branch", "agent/demo/a", base)
            lane_a = managed / "demo-a"
            git(root, "worktree", "add", str(lane_a), "agent/demo/a")
            (lane_a / "a.txt").write_text("a\n", encoding="utf-8")
            git(lane_a, "add", "a.txt")
            git(lane_a, "commit", "-m", "a")
            recorded = git(root, "rev-parse", "agent/demo/a")
            composite_tree = git(
                root, "merge-tree", "--write-tree", base, recorded
            ).splitlines()[0]
            composite = commit_tree(
                root,
                composite_tree,
                base,
                recorded,
                message=(
                    "spec\n\nSpeculative-Base: true\nDepends-Lane: " + recorded
                ),
            )
            git(root, "branch", "agent/demo/c", composite)
            lane_c = managed / "demo-c"
            git(root, "worktree", "add", str(lane_c), "agent/demo/c")
            ledger = root / ".agent_state" / "orchestrate" / "findings" / "demo.jsonl"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(
                json.dumps(
                    {
                        "id": "OPEN-1",
                        "severity": "blocker",
                        "propagation": "gates-the-slice",
                        "owner": "original-writer",
                        "subject_sha": recorded,
                        "verdict": "needs_fix",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_cli(root, "reconcile")
            self.assertEqual(result.returncode, 0, result.stderr)
            entries = {
                item["branch"]: item for item in json.loads(result.stdout)["worktrees"]
            }
            self.assertEqual(entries["agent/demo/a"]["class"], "held-by-review-debt")
            self.assertEqual(
                entries["agent/demo/c"]["class"], "active-run-ahead-base"
            )
            self.assertEqual(
                entries["agent/demo/c"]["speculative_prerequisite_findings"],
                ["OPEN-1"],
            )

    def test_cleanup_is_targeted_and_dry_run_uses_reconcile_classifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = init_repo(root)
            managed = root / ".agent_state" / "worktrees"
            managed.mkdir(parents=True)
            review = managed / "review-base"
            git(root, "worktree", "add", "--detach", str(review), base)
            git(root, "branch", "agent/demo/a", base)
            lane = managed / "demo-a"
            git(root, "worktree", "add", str(lane), "agent/demo/a")
            (lane / "a.txt").write_text("a\n", encoding="utf-8")
            git(lane, "add", "a.txt")
            git(lane, "commit", "-m", "a")
            lane_head = git(root, "rev-parse", "agent/demo/a")
            git(root, "update-ref", "refs/heads/task/demo", lane_head)

            sweep = run_cli(root, "cleanup", "--absorbed", "--dry-run")
            self.assertEqual(sweep.returncode, 0, sweep.stderr)
            payload = json.loads(sweep.stdout)
            self.assertTrue(payload["bulk_cleanup_disabled"])
            self.assertIn(str(lane.resolve()), payload["safe_to_remove"])
            review_entry = next(
                item for item in payload["worktrees"] if item["path"] == str(review)
            )
            self.assertEqual(review_entry["class"], "unknown")
            self.assertFalse(review_entry["cleanup_eligible"])

            target = run_cli(
                root, "cleanup", "--worktree", str(lane), "--dry-run"
            )
            self.assertEqual(target.returncode, 0, target.stderr)
            self.assertTrue(
                json.loads(target.stdout)["worktree"]["cleanup_eligible"]
            )
            blocked_bulk = run_cli(root, "cleanup", "--absorbed")
            self.assertEqual(blocked_bulk.returncode, 2)
            self.assertIn("bulk cleanup is disabled", blocked_bulk.stderr)
            review_without_sha = run_cli(
                root, "cleanup", "--worktree", str(review)
            )
            self.assertEqual(review_without_sha.returncode, 2)
            self.assertIn("requires --subject-sha", review_without_sha.stderr)
            self.assertTrue(review.exists())
            self.assertTrue(lane.exists())
            self.assertEqual(git(root, "rev-parse", "agent/demo/a"), lane_head)


if __name__ == "__main__":
    unittest.main()
