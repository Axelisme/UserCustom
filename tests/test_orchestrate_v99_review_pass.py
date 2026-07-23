from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"
from tests._orchestrate_test_support import cli_command


def run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cli_command(SCRIPT, [*arguments, "--root", str(root)]),
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
    git(root, "config", "user.name", "V99")
    git(root, "config", "user.email", "v99@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")
    return git(root, "rev-parse", "HEAD")


def record(
    root: Path, findings: list[dict], verdict: str, **extra: object
) -> subprocess.CompletedProcess[str]:
    subject = git(root, "rev-parse", "HEAD")
    canonical_findings = [
        {
            "path": "test.py",
            "behavior": "test finding",
            "evidence": ["test evidence"],
            **finding,
        }
        for finding in findings
    ]
    receipt = root / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "subject_sha": subject,
                "verdict": verdict,
                "evidence": ["test receipt"],
                "findings": canonical_findings,
                **extra,
            }
        ),
        encoding="utf-8",
    )
    return run_cli(
        root, "findings", "record", "--task-id", "demo", "--receipt", str(receipt)
    )


class ReviewPassReceiptTests(unittest.TestCase):
    """v99 #1: a clean review (verdict=pass, findings=[]) records a durable,
    Git-derivable marker instead of forcing a fake finding or a prose-only receipt."""

    def test_pass_clean_records_a_review_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            subject = git(root, "rev-parse", "HEAD")
            result = record(root, [], "pass", evidence=["suite: 55 passed"])
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(len(payload["appended"]), 1)
            self.assertTrue(payload["appended"][0].startswith(f"review-pass:{subject}:"))

            status = run_cli(root, "findings", "status", "--task-id", "demo")
            self.assertEqual(status.returncode, 0, status.stderr)
            st = json.loads(status.stdout)
            self.assertEqual(
                [m["subject_sha"] for m in st["review_outcomes"]], [subject]
            )
            self.assertEqual(st["open"], [])
            self.assertEqual(st["closed"], [])
            self.assertFalse(st["collect_blocked"])
            marker = st["review_outcomes"][0]
            self.assertEqual(marker["kind"], "review-pass")
            self.assertEqual(marker["evidence"], ["suite: 55 passed"])

    def test_pass_clean_is_idempotent_on_same_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            subject = git(root, "rev-parse", "HEAD")
            first = record(root, [], "pass")
            second = record(root, [], "pass")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            marker_id = json.loads(first.stdout)["appended"][0]
            self.assertTrue(marker_id.startswith(f"review-pass:{subject}:"))
            self.assertEqual(
                json.loads(second.stdout)["skipped_existing"],
                [marker_id],
            )
            status = json.loads(
                run_cli(root, "findings", "status", "--task-id", "demo").stdout
            )
            self.assertEqual(len(status["review_outcomes"]), 1)

    def test_needs_fix_with_no_findings_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            result = record(root, [], "needs_fix")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-empty", result.stderr + result.stdout)
            ledger = root / ".agent_state" / "orchestrate" / "findings" / "demo.jsonl"
            self.assertFalse(ledger.exists())

    def test_marker_does_not_gate_collect_or_pollute_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            record(root, [], "pass")
            gated = record(
                root,
                [{"id": "F1", "severity": "major", "propagation": "gates-the-slice"}],
                "needs_fix",
            )
            self.assertEqual(gated.returncode, 0, gated.stderr)
            status = json.loads(
                run_cli(root, "findings", "status", "--task-id", "demo").stdout
            )
            # The marker is not a finding: only F1 gates, and reviewed_clean stands.
            self.assertEqual(status["gating_open"], ["F1"])
            self.assertEqual([r["id"] for r in status["open"]], ["F1"])
            self.assertTrue(status["review_outcomes"])


class WaveStatusTests(unittest.TestCase):
    """v99 #4+6: a read-only wave rollup that composes the derived reads a wave
    boundary already needs, plus a restart handoff — never mutating anything."""

    def test_wave_status_aggregates_read_only_with_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            record(root, [], "pass", evidence=["gate green"])
            gated = record(
                root,
                [{"id": "F1", "severity": "major", "propagation": "gates-the-slice"}],
                "needs_fix",
            )
            self.assertEqual(gated.returncode, 0, gated.stderr)

            before = git(root, "rev-parse", "task/demo")
            result = run_cli(root, "wave", "status", "--task-ref", "task/demo")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["read_only"])
            self.assertEqual(payload["operation"], "wave-status")
            # Composes all three derived reads.
            for key in ("slice", "findings", "reconcile", "handoff"):
                self.assertIn(key, payload)
            handoff = payload["handoff"]
            self.assertEqual(handoff["gating_open"], ["F1"])
            self.assertEqual(handoff["open_findings"], ["F1"])
            self.assertTrue(handoff["collect_blocked"])
            self.assertFalse(handoff["reviewed_clean"])
            self.assertIsNotNone(handoff["review_cursor"])
            # Purely read-only: the task tip did not move.
            self.assertEqual(git(root, "rev-parse", "task/demo"), before)

    def test_wave_status_rejects_non_task_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            result = run_cli(root, "wave", "status", "--task-ref", "main")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("task/<task>", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
