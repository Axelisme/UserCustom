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
    git(root, "config", "user.name", "V96")
    git(root, "config", "user.email", "v96@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")
    return git(root, "rev-parse", "HEAD")


class SweepFindingTests(unittest.TestCase):
    """M1 root-cause sweep: a sweep_required finding must be a hard gate."""

    def _record(
        self, root: Path, findings: list[dict], verdict: str = "needs_fix"
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
                }
            ),
            encoding="utf-8",
        )
        return run_cli(
            root, "findings", "record", "--task-id", "demo", "--receipt", str(receipt)
        )

    def test_sweep_required_forces_gating_propagation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            result = self._record(
                root,
                [
                    {
                        "id": "SWEEP-1",
                        "severity": "major",
                        "propagation": "follow-up-to-writer",
                        "sweep_required": True,
                    }
                ],
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sweep_required", result.stderr + result.stdout)
            # Nothing must be written when validation rejects the batch.
            ledger = (
                root / ".agent_state" / "orchestrate" / "findings" / "demo.jsonl"
            )
            self.assertFalse(ledger.exists())

    def test_sweep_required_records_and_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            record = self._record(
                root,
                [
                    {
                        "id": "SWEEP-1",
                        "severity": "major",
                        "propagation": "gates-the-slice",
                        "sweep_required": True,
                        "root_cause": "reset --hard moves a ref",
                    }
                ],
            )
            self.assertEqual(record.returncode, 0, record.stderr)
            status = run_cli(root, "findings", "status", "--task-id", "demo")
            self.assertEqual(status.returncode, 0, status.stderr)
            payload = json.loads(status.stdout)
            self.assertEqual(
                [r["id"] for r in payload["open"] if r.get("sweep_required")],
                ["SWEEP-1"],
            )
            self.assertIn("SWEEP-1", payload["gating_open"])
            self.assertTrue(payload["collect_blocked"])
            opened = payload["open"][0]
            self.assertTrue(opened["sweep_required"])
            self.assertEqual(opened["root_cause"], "reset --hard moves a ref")

    def test_ordinary_finding_leaves_sweep_bucket_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            record = self._record(
                root,
                [
                    {
                        "id": "PLAIN-1",
                        "severity": "major",
                        "propagation": "gates-the-slice",
                    }
                ],
            )
            self.assertEqual(record.returncode, 0, record.stderr)
            status = run_cli(root, "findings", "status", "--task-id", "demo")
            payload = json.loads(status.stdout)
            self.assertEqual(
                [r["id"] for r in payload["open"] if r.get("sweep_required")], []
            )
            self.assertEqual(payload["gating_open"], ["PLAIN-1"])
            self.assertFalse(payload["open"][0]["sweep_required"])
            self.assertIsNone(payload["open"][0]["root_cause"])


if __name__ == "__main__":
    unittest.main()
