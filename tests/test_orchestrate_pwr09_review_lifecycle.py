from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from unittest.mock import patch
from pathlib import Path
from importlib import import_module

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
sys.path.insert(0, str(SKILL / "scripts"))
review = import_module("_orchestrate.review")
findings = import_module("_orchestrate.findings")
worktrees = import_module("_orchestrate.worktrees")
cli = import_module("_orchestrate.cli")
OrchestrateError = import_module("_orchestrate.primitives").OrchestrateError


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class PWR09ReviewLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "PWR09")
        git(self.root, "config", "user.email", "pwr09@example.invalid")
        (self.root / "file.txt").write_text("one\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_each_job_has_stable_identity_and_old_checkout_cannot_move(self) -> None:
        first = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=self.base, task_id="task", job_id="job-one",
            worktree=None,
        ))
        self.assertTrue(first["immutable"])
        self.assertEqual(first["subject_sha"], self.base)
        with self.assertRaisesRegex(OrchestrateError, "another task/job"):
            review.command_review_checkout(argparse.Namespace(
                root=str(self.root), sha=self.base, task_id="other", job_id="job-two",
                worktree=first["worktree"],
            ))
        self.assertRaises(
            OrchestrateError,
            review.command_review_checkout,
            argparse.Namespace(
                root=str(self.root), sha=self.base, task_id="task", job_id="job-one",
                worktree=str(self.root / ".agent_state/worktrees/review-task-job-one-alt"),
            ),
        )
        (self.root / "file.txt").write_text("two\n", encoding="utf-8")
        git(self.root, "add", "file.txt")
        git(self.root, "commit", "-m", "frontier")
        second_sha = git(self.root, "rev-parse", "HEAD")
        second = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=second_sha, task_id="task", job_id="job-two",
            worktree=None,
        ))
        self.assertNotEqual(first["worktree"], second["worktree"])
        self.assertEqual(git(Path(first["worktree"]), "rev-parse", "HEAD"), self.base)

    def test_creation_rolls_back_worktree_when_ledger_publication_fails(self) -> None:
        with patch.object(review, "_append_review_job", side_effect=OSError("ledger unavailable")):
            with self.assertRaises(OSError):
                review.command_review_checkout(argparse.Namespace(
                    root=str(self.root), sha=self.base, task_id="task", job_id="rollback", worktree=None,
                ))
        self.assertFalse((self.root / ".agent_state/worktrees/review-task-rollback").exists())
        self.assertEqual(git(self.root, "worktree", "list", "--porcelain").count("review-task-rollback"), 0)

    def test_double_fault_returns_reconcile_and_retry_adopts_orphan(self) -> None:
        with patch.object(review, "_append_review_job", side_effect=OSError("ledger down")), \
                patch.object(review, "_compensate_created_review_worktree", return_value={
                    "remove_ok": False, "remove_error": "remove down",
                    "prune_ok": False, "prune_error": "prune down",
                }):
            outcome = review.command_review_checkout(argparse.Namespace(
                root=str(self.root), sha=self.base, task_id="task", job_id="double", worktree=None,
            ))
        self.assertTrue(outcome["reconcile_required"])
        self.assertEqual(outcome["subject_sha"], self.base)
        retry = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=self.base, task_id="task", job_id="double", worktree=None,
        ))
        self.assertEqual(retry["recovered"], "adopted-orphan")

    def test_cleanup_requires_harvest_and_cleanup_all_respects_public_facts(self) -> None:
        created = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=self.base, task_id="task", job_id="job",
            worktree=None,
        ))
        receipt = self.root / "receipt.json"
        receipt.write_text(json.dumps({
            "subject_sha": self.base, "verdict": "pass", "evidence": ["tests"], "findings": [],
        }), encoding="utf-8")
        facts = self.root / "facts.json"
        facts.write_text(json.dumps({"schema_version": 1, "source": "pi-subagents.pipeline.status",
                                     "repo_root": str(self.root.resolve()), "owner_session": "root",
                                     "snapshot_revision": 1,
                                     "observed_at": datetime.now(UTC).isoformat(),
                                     "pipelines": [{"name": "review", "state": "active", "active": True,
                                                    "current": {"worktree": created["worktree"]}, "pending": []}],
                                     "receipts": {}}), encoding="utf-8")
        with self.assertRaisesRegex(OrchestrateError, "referenced"):
            review.command_review_cleanup(argparse.Namespace(
                root=str(self.root), task_id="task", job_id="job", receipt="",
                pipeline_facts=str(facts), owner_session="root",
            ))
        with self.assertRaisesRegex(OrchestrateError, "referenced"):
            review.command_review_cleanup_all(argparse.Namespace(
                root=str(self.root), task_id="task", pipeline_facts=str(facts), owner_session="root",
            ))
        facts.write_text(json.dumps({"schema_version": 1, "source": "pi-subagents.pipeline.status",
                                     "repo_root": str(self.root.resolve()), "owner_session": "root",
                                     "snapshot_revision": 2,
                                     "observed_at": datetime.now(UTC).isoformat(),
                                     "pipelines": [{"name": "review", "state": "idle", "active": False,
                                                    "current": None, "pending": []}],
                                     "receipts": {}}), encoding="utf-8")
        inside = Path(created["worktree"]) / "receipt.json"
        inside.write_text(receipt.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaisesRegex(OrchestrateError, "outside"):
            review.command_review_cleanup(argparse.Namespace(
                root=str(self.root), task_id="task", job_id="job", receipt=str(inside),
                pipeline_facts=str(facts), owner_session="root",
            ))
        inside.unlink()
        cleaned = review.command_review_cleanup(argparse.Namespace(
            root=str(self.root), task_id="task", job_id="job", receipt=str(receipt),
            pipeline_facts=str(facts), owner_session="root",
        ))
        self.assertTrue(cleaned["receipt_harvested"])
        self.assertFalse(Path(created["worktree"]).exists())
        with self.assertRaisesRegex(OrchestrateError, "retired"):
            review.command_review_checkout(argparse.Namespace(
                root=str(self.root), sha=self.base, task_id="task", job_id="job", worktree=None,
            ))

    def test_linked_root_uses_common_review_ledger_and_rejects_adopter(self) -> None:
        linked = self.root.parent / "linked-integration"
        git(self.root, "worktree", "add", "--detach", str(linked), self.base)
        try:
            created = review.command_review_checkout(argparse.Namespace(
                root=str(linked), sha=self.base, task_id="task", job_id="linked", worktree=None,
            ))
            ledger = self.root / ".agent_state/orchestrate/reviews/task.jsonl"
            self.assertTrue(ledger.exists())
            replay = review.command_review_checkout(argparse.Namespace(
                root=str(self.root), sha=self.base, task_id="task", job_id="linked", worktree=None,
            ))
            self.assertEqual(replay["recovered"], "already-created")
            with self.assertRaisesRegex(OrchestrateError, "another task/job"):
                review.command_review_checkout(argparse.Namespace(
                    root=str(self.root), sha=self.base, task_id="other", job_id="adopter",
                    worktree=created["worktree"],
                ))
            receipt = self.root / "linked-receipt.json"
            receipt.write_text(json.dumps({
                "subject_sha": self.base, "verdict": "pass", "evidence": ["linked"], "findings": [],
            }), encoding="utf-8")
            facts = self.root / "linked-facts.json"
            facts.write_text(json.dumps({
                "schema_version": 1, "source": "pi-subagents.pipeline.status",
                "repo_root": str(linked.resolve()), "owner_session": "linked",
                "snapshot_revision": 1, "observed_at": datetime.now(UTC).isoformat(),
                "pipelines": [{"name": "review", "state": "idle", "active": False,
                               "current": None, "pending": []}], "receipts": {},
            }), encoding="utf-8")
            cleaned = review.command_review_cleanup(argparse.Namespace(
                root=str(linked), task_id="task", job_id="linked", receipt=str(receipt),
                pipeline_facts=str(facts), owner_session="linked",
            ))
            self.assertTrue(cleaned["ok"])
            self.assertFalse(Path(created["worktree"]).exists())
        finally:
            if linked.exists():
                git(self.root, "worktree", "remove", "--force", str(linked))

    def test_legacy_cleanup_refuses_open_immutable_review_job(self) -> None:
        created = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=self.base, task_id="task", job_id="legacy", worktree=None,
        ))
        with self.assertRaisesRegex(OrchestrateError, "open immutable review job"):
            worktrees.command_cleanup(argparse.Namespace(
                root=str(self.root), worktree=created["worktree"], subject_sha=self.base,
                dry_run=False, wave_boundary=False,
            ))
        self.assertTrue(Path(created["worktree"]).exists())

    def test_drifted_open_review_refuses_targeted_cleanup_and_canonical_reports_drift(self) -> None:
        created = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=self.base, task_id="task", job_id="target-drift", worktree=None,
        ))
        target = Path(created["worktree"])
        git(self.root, "branch", "task/task")
        git(target, "checkout", "-b", "agent/task/drift-target")
        with self.assertRaisesRegex(OrchestrateError, "open immutable review job"):
            worktrees.command_cleanup(argparse.Namespace(
                root=str(self.root), worktree=str(target), subject_sha=self.base,
                dry_run=False, wave_boundary=False,
            ))
        self.assertTrue(target.exists())
        self.assertEqual(review._latest_task_job(self.root, "task", "target-drift")["state"], "open")
        receipt = self.root / "target-drift-receipt.json"
        receipt.write_text(json.dumps({
            "subject_sha": self.base, "verdict": "pass", "evidence": ["drift"], "findings": [],
        }), encoding="utf-8")
        facts = self.root / "target-drift-facts.json"
        facts.write_text(json.dumps({
            "schema_version": 1, "source": "pi-subagents.pipeline.status",
            "repo_root": str(self.root.resolve()), "owner_session": "root",
            "snapshot_revision": 1, "observed_at": datetime.now(UTC).isoformat(),
            "pipelines": [{"name": "review", "state": "idle", "active": False,
                           "current": None, "pending": []}], "receipts": {},
        }), encoding="utf-8")
        with self.assertRaisesRegex(OrchestrateError, "drifted"):
            review.command_review_cleanup(argparse.Namespace(
                root=str(self.root), task_id="task", job_id="target-drift",
                receipt=str(receipt), pipeline_facts=str(facts), owner_session="root",
            ))
        self.assertTrue(target.exists())
        self.assertEqual(review._latest_task_job(self.root, "task", "target-drift")["state"], "open")

    def test_wave_cleanup_scopes_open_owner_refusal_to_current_task_candidates(self) -> None:
        git(self.root, "branch", "task/alpha")
        git(self.root, "checkout", "task/alpha")
        alpha = self.root / ".agent_state/worktrees/alpha-lane-one"
        git(self.root, "worktree", "add", "-b", "agent/alpha/one", str(alpha), self.base)
        beta = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=self.base, task_id="beta", job_id="review", worktree=None,
        ))
        beta_path = Path(beta["worktree"])
        try:
            dry = worktrees.command_cleanup(argparse.Namespace(
                root=str(self.root), worktree=None, subject_sha=None,
                dry_run=True, wave_boundary=True,
            ))
            self.assertTrue(any(entry["path"] == str(alpha) and entry["action"] == "eligible"
                                for entry in dry["entries"]))
            self.assertTrue(any(entry["path"] == str(beta_path) and entry["action"] == "skipped"
                                for entry in dry["entries"]))
            worktrees.command_cleanup(argparse.Namespace(
                root=str(self.root), worktree=None, subject_sha=None,
                dry_run=False, wave_boundary=True,
            ))
            self.assertFalse(alpha.exists())
            self.assertTrue(beta_path.exists())
            self.assertEqual(review._latest_task_job(self.root, "beta", "review")["state"], "open")

            # A review from beta drifted onto a beta lane remains unrelated to
            # alpha's wave and must not block a fresh alpha candidate.
            git(beta_path, "checkout", "-b", "agent/beta/drift")
            alpha_two = self.root / ".agent_state/worktrees/alpha-lane-two"
            git(self.root, "worktree", "add", "-b", "agent/alpha/two", str(alpha_two), self.base)
            try:
                worktrees.command_cleanup(argparse.Namespace(
                    root=str(self.root), worktree=None, subject_sha=None,
                    dry_run=False, wave_boundary=True,
                ))
                self.assertFalse(alpha_two.exists())
                self.assertTrue(beta_path.exists())
            finally:
                if alpha_two.exists():
                    git(self.root, "worktree", "remove", "--force", str(alpha_two))
        finally:
            if alpha.exists():
                git(self.root, "worktree", "remove", "--force", str(alpha))
            if beta_path.exists():
                git(self.root, "worktree", "remove", "--force", str(beta_path))

    def test_cross_task_open_owner_drifted_onto_current_lane_refuses_wave_cleanup(self) -> None:
        git(self.root, "branch", "task/alpha")
        git(self.root, "checkout", "task/alpha")
        alpha = self.root / ".agent_state/worktrees/alpha-lane-owned"
        git(self.root, "worktree", "add", "-b", "agent/alpha/owned", str(alpha), self.base)
        beta = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=self.base, task_id="beta", job_id="cross-task", worktree=None,
        ))
        beta_path = Path(beta["worktree"])
        git(beta_path, "checkout", "-b", "agent/alpha/drifted-owner")
        try:
            with self.assertRaisesRegex(OrchestrateError, "open immutable review job"):
                worktrees.command_cleanup(argparse.Namespace(
                    root=str(self.root), worktree=None, subject_sha=None,
                    dry_run=False, wave_boundary=True,
                ))
            self.assertTrue(alpha.exists())
            self.assertTrue(beta_path.exists())
            self.assertEqual(review._latest_task_job(self.root, "beta", "cross-task")["state"], "open")
        finally:
            if alpha.exists():
                git(self.root, "worktree", "remove", "--force", str(alpha))
            if beta_path.exists():
                git(self.root, "worktree", "remove", "--force", str(beta_path))

    def test_drifted_open_review_refuses_wave_boundary_cleanup(self) -> None:
        git(self.root, "branch", "task/task")
        git(self.root, "checkout", "task/task")
        created = review.command_review_checkout(argparse.Namespace(
            root=str(self.root), sha=self.base, task_id="task", job_id="wave-drift", worktree=None,
        ))
        target = Path(created["worktree"])
        git(target, "checkout", "-b", "agent/task/drift-wave")
        with self.assertRaisesRegex(OrchestrateError, "open immutable review job"):
            worktrees.command_cleanup(argparse.Namespace(
                root=str(self.root), worktree=None, subject_sha=None,
                dry_run=False, wave_boundary=True,
            ))
        self.assertTrue(target.exists())
        self.assertEqual(review._latest_task_job(self.root, "task", "wave-drift")["state"], "open")
        receipt = self.root / "wave-drift-receipt.json"
        receipt.write_text(json.dumps({
            "subject_sha": self.base, "verdict": "pass", "evidence": ["drift"], "findings": [],
        }), encoding="utf-8")
        facts = self.root / "wave-drift-facts.json"
        facts.write_text(json.dumps({
            "schema_version": 1, "source": "pi-subagents.pipeline.status",
            "repo_root": str(self.root.resolve()), "owner_session": "root",
            "snapshot_revision": 1, "observed_at": datetime.now(UTC).isoformat(),
            "pipelines": [{"name": "review", "state": "idle", "active": False,
                           "current": None, "pending": []}], "receipts": {},
        }), encoding="utf-8")
        with self.assertRaisesRegex(OrchestrateError, "drifted"):
            review.command_review_cleanup(argparse.Namespace(
                root=str(self.root), task_id="task", job_id="wave-drift",
                receipt=str(receipt), pipeline_facts=str(facts), owner_session="root",
            ))
        self.assertTrue(target.exists())
        self.assertEqual(review._latest_task_job(self.root, "task", "wave-drift")["state"], "open")

    def test_needs_fix_cursor_is_not_reviewed_clean(self) -> None:
        git(self.root, "branch", "task/task")
        ledger = self.root / ".agent_state/orchestrate/findings/task.jsonl"
        ledger.parent.mkdir(parents=True)
        receipt = self.root / "needs-fix-wave.json"
        receipt.write_text(json.dumps({
            "subject_sha": self.base, "verdict": "needs_fix", "evidence": ["debt"],
            "findings": [{"id": "debt", "propagation": "gates-the-slice",
                          "behavior": "broken", "evidence": ["debt"], "path": "file.txt"}],
        }), encoding="utf-8")
        findings.command_findings_record(argparse.Namespace(
            root=str(self.root), task_id="task", receipt=str(receipt),
        ))
        handoff = worktrees.command_wave_status(argparse.Namespace(
            root=str(self.root), task_ref="task/task", summary=True,
        ))["handoff"]
        self.assertEqual(handoff["review_cursor"], self.base)
        self.assertEqual(handoff["reviewed_clean"], [])
        self.assertTrue(handoff["collect_blocked"])
        self.assertTrue(handoff["validated_frontier_blocked"])

    def test_sibling_valid_lanes_do_not_create_global_frontier_ambiguity(self) -> None:
        git(self.root, "branch", "task/task")
        lanes: list[Path] = []
        subjects: list[str] = []
        for name in ("a", "b"):
            lane = self.root.parent / f"lane-{name}"
            lanes.append(lane)
            git(self.root, "worktree", "add", "-b", f"agent/task/{name}", str(lane), self.base)
            (lane / f"{name}.txt").write_text(name, encoding="utf-8")
            git(lane, "add", ".")
            git(lane, "commit", "-m", name)
            subjects.append(git(lane, "rev-parse", "HEAD"))
        ledger = self.root / ".agent_state/orchestrate/findings/task.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("\n".join(json.dumps({
            "id": f"pass-{subject[:8]}", "kind": "review-pass", "subject_sha": subject,
            "verdict": "pass", "evidence": ["independent lane"],
        }) for subject in subjects) + "\n", encoding="utf-8")
        try:
            handoff = worktrees.command_wave_status(argparse.Namespace(
                root=str(self.root), task_ref="task/task", summary=True,
            ))["handoff"]
            self.assertIsNone(handoff["validated_frontier"])
            self.assertFalse(handoff["validated_frontier_ambiguous"])
            self.assertFalse(handoff["validated_frontier_blocked"])
            self.assertFalse(handoff["collect_blocked"])
            self.assertEqual(sorted(handoff["validated_unlanded"]), sorted(subjects))
        finally:
            for lane in lanes:
                if lane.exists():
                    git(self.root, "worktree", "remove", "--force", str(lane))
            for name in ("a", "b"):
                git(self.root, "branch", "-D", f"agent/task/{name}")

    def test_cursor_uses_reachable_ancestry_not_append_order(self) -> None:
        (self.root / "file.txt").write_text("two\n", encoding="utf-8")
        git(self.root, "add", "file.txt")
        git(self.root, "commit", "-m", "descendant")
        descendant = git(self.root, "rev-parse", "HEAD")
        git(self.root, "checkout", "-b", "orphan")
        (self.root / "orphan.txt").write_text("orphan\n", encoding="utf-8")
        git(self.root, "add", "orphan.txt")
        git(self.root, "commit", "-m", "orphan")
        orphan = git(self.root, "rev-parse", "HEAD")
        git(self.root, "checkout", "main")
        ledger = self.root / ".agent_state/orchestrate/findings/task.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("\n".join(json.dumps({"id": f"m-{sha[:8]}", "kind": "review-pass",
                                                      "subject_sha": sha, "verdict": "pass",
                                                      "evidence": ["review"]})
                                      for sha in (descendant, self.base, orphan)) + "\n", encoding="utf-8")
        status = findings.command_findings_status(argparse.Namespace(
            root=str(self.root), task_id="task", task_ref="HEAD", slice_sha=None,
            ids=None, open_only=False, summary=False, path=None, sweep=False,
        ))
        self.assertEqual(status["review_cursor"], descendant)
        self.assertFalse(status["review_cursor_ambiguous"])
        self.assertEqual(status["validated_frontier"], descendant)

    def test_cursor_advances_on_needs_fix_but_frontier_waits_for_closure(self) -> None:
        ledger = self.root / ".agent_state/orchestrate/findings/task.jsonl"
        ledger.parent.mkdir(parents=True)
        receipt = self.root / "needs-fix.json"
        receipt.write_text(json.dumps({
            "subject_sha": self.base, "verdict": "needs_fix", "evidence": ["test"],
            "findings": [{"id": "gate", "propagation": "gates-the-slice",
                          "behavior": "broken", "evidence": ["test"], "path": "file.txt"}],
        }), encoding="utf-8")
        findings.command_findings_record(argparse.Namespace(
            root=str(self.root), task_id="task", receipt=str(receipt),
        ))
        status = findings.command_findings_status(argparse.Namespace(
            root=str(self.root), task_id="task", task_ref="HEAD", slice_sha=None,
            ids=None, open_only=False, summary=False, path=None, sweep=False,
        ))
        self.assertEqual(status["review_cursor"], self.base)
        self.assertIsNone(status["validated_frontier"])
        self.assertTrue(status["validated_frontier_blocked"])
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["review", "advance"])


if __name__ == "__main__":
    unittest.main()
