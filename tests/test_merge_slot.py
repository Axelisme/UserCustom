from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "home"
    / ".codex"
    / "skills"
    / "orchestrate"
    / "scripts"
    / "merge_slot.py"
)


class MergeSlotCliTests(unittest.TestCase):
    def slot_command(self, root: Path, *args: str) -> list[str]:
        return [sys.executable, str(SCRIPT), "--root", str(root), *args]

    def run_slot(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.slot_command(root, *args),
            check=False,
            capture_output=True,
            text=True,
        )

    def test_expired_holder_cannot_renew(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            claim = self.run_slot(root, "claim", "task-a", "--lease", "0")
            self.assertEqual(claim.returncode, 0, claim.stderr)
            self.assertEqual(json.loads(claim.stdout)["status"], "acquired")

            renew = self.run_slot(root, "renew", "task-a")
            self.assertEqual(renew.returncode, 2, renew.stdout)
            self.assertIn("does not hold the merge slot", renew.stderr)

            status = self.run_slot(root, "status")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(
                json.loads(status.stdout),
                {"holder": None, "holder_expired": False, "queue": []},
            )

    def test_expired_holder_cannot_yield(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            claim = self.run_slot(root, "claim", "task-a", "--lease", "0")
            self.assertEqual(claim.returncode, 0, claim.stderr)

            yielded = self.run_slot(root, "yield", "task-a")
            self.assertEqual(yielded.returncode, 2, yielded.stdout)
            self.assertIn("does not hold the merge slot", yielded.stderr)

            status = self.run_slot(root, "status")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(
                json.loads(status.stdout),
                {"holder": None, "holder_expired": False, "queue": []},
            )

    def test_waiters_acquire_in_fifo_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            first = self.run_slot(root, "claim", "task-a")
            second = self.run_slot(root, "claim", "task-b")
            self.assertEqual(json.loads(first.stdout)["status"], "acquired")
            self.assertEqual(
                json.loads(second.stdout),
                {
                    "status": "queued",
                    "holder": "task-a",
                    "position": 2,
                    "queue": ["task-a", "task-b"],
                },
            )

            released = self.run_slot(root, "release", "task-a")
            self.assertEqual(json.loads(released.stdout)["queue"], ["task-b"])

            next_claim = self.run_slot(root, "claim", "task-b")
            self.assertEqual(json.loads(next_claim.stdout)["status"], "acquired")

    def test_concurrent_claims_have_one_holder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processes = [
                subprocess.Popen(
                    self.slot_command(root, "claim", task),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for task in ("task-a", "task-b")
            ]

            results = [process.communicate() for process in processes]
            self.assertTrue(
                all(process.returncode == 0 for process in processes), results
            )
            statuses = sorted(json.loads(stdout)["status"] for stdout, _ in results)
            self.assertEqual(statuses, ["acquired", "queued"])

            status = self.run_slot(root, "status")
            payload = json.loads(status.stdout)
            self.assertIsNotNone(payload["holder"])
            self.assertEqual(set(payload["queue"]), {"task-a", "task-b"})


if __name__ == "__main__":
    unittest.main()
