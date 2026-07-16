from __future__ import annotations

import json
import shutil
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
ROOT = Path(__file__).resolve().parents[1]


def copy_release_home(root: Path) -> Path:
    home = root / "home"
    skill = home / ".codex" / "skills" / "orchestrate"
    shutil.copytree(ROOT / "home" / ".codex" / "skills" / "orchestrate", skill)
    for runtime, suffix in ((".codex", ".toml"), (".claude", ".md")):
        agents = home / runtime / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        source = ROOT / "home" / runtime / "agents"
        for role in ("contract-planner", "implementer", "reviewer"):
            shutil.copy2(source / f"{role}{suffix}", agents / f"{role}{suffix}")
    return skill


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

    def test_claim_fails_release_preflight_before_creating_slot_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            skill = copy_release_home(temporary / "release")
            runtime = skill / "runtime-codex.md"
            runtime.write_text(
                runtime.read_text(encoding="utf-8") + "\ntampered\n",
                encoding="utf-8",
            )
            root = temporary / "repo"
            root.mkdir()

            claim = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--skill-dir",
                    str(skill),
                    "--root",
                    str(root),
                    "claim",
                    "task-a",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(claim.returncode, 2)
            self.assertIn("release preflight failed", claim.stderr)
            self.assertFalse((root / ".agent_state").exists())

    def test_expired_holder_cannot_renew(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            claim = self.run_slot(root, "claim", "task-a", "--lease", "0")
            self.assertEqual(claim.returncode, 0, claim.stderr)
            claim_payload = json.loads(claim.stdout)
            self.assertEqual(claim_payload["status"], "acquired")
            self.assertTrue(claim_payload["owner_token"].startswith("owner_"))

            renew = self.run_slot(
                root,
                "renew",
                "task-a",
                "--owner-token",
                claim_payload["owner_token"],
            )
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
            owner_token = json.loads(claim.stdout)["owner_token"]

            yielded = self.run_slot(
                root,
                "yield",
                "task-a",
                "--owner-token",
                owner_token,
            )
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
            first_payload = json.loads(first.stdout)
            second_payload = json.loads(second.stdout)
            self.assertEqual(first_payload["status"], "acquired")
            self.assertEqual(second_payload["status"], "queued")
            self.assertEqual(second_payload["holder"], "task-a")
            self.assertEqual(second_payload["position"], 2)
            self.assertEqual(second_payload["queue"], ["task-a", "task-b"])

            released = self.run_slot(
                root,
                "release",
                "task-a",
                "--owner-token",
                first_payload["owner_token"],
            )
            self.assertEqual(json.loads(released.stdout)["queue"], ["task-b"])

            next_claim = self.run_slot(
                root,
                "claim",
                "task-b",
                "--owner-token",
                second_payload["owner_token"],
            )
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

    def test_concurrent_same_task_claims_have_one_holder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processes = [
                subprocess.Popen(
                    self.slot_command(root, "claim", "task-a"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(2)
            ]

            results = [process.communicate() for process in processes]
            self.assertTrue(
                all(process.returncode == 0 for process in processes), results
            )
            payloads = [json.loads(stdout) for stdout, _ in results]
            self.assertEqual(
                sorted(payload["status"] for payload in payloads),
                ["acquired", "queued"],
            )
            self.assertEqual(len({payload["owner_token"] for payload in payloads}), 2)
            self.assertEqual(
                next(
                    payload["position"]
                    for payload in payloads
                    if payload["status"] == "queued"
                ),
                2,
            )

    def test_same_task_claimants_have_distinct_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            first = self.run_slot(root, "claim", "task-a")
            second = self.run_slot(root, "claim", "task-a")

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_payload = json.loads(first.stdout)
            second_payload = json.loads(second.stdout)
            self.assertEqual(first_payload["status"], "acquired")
            self.assertEqual(second_payload["status"], "queued")
            self.assertNotEqual(
                first_payload["owner_token"], second_payload["owner_token"]
            )
            self.assertEqual(second_payload["position"], 2)
            self.assertEqual(second_payload["queue"], ["task-a", "task-a"])

            released = self.run_slot(
                root,
                "release",
                "task-a",
                "--owner-token",
                first_payload["owner_token"],
            )
            self.assertEqual(released.returncode, 0, released.stderr)
            acquired = self.run_slot(
                root,
                "claim",
                "task-a",
                "--owner-token",
                second_payload["owner_token"],
            )
            self.assertEqual(json.loads(acquired.stdout)["status"], "acquired")

    def test_wrong_owner_token_cannot_release_holder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claim = self.run_slot(root, "claim", "task-a")
            owner_token = json.loads(claim.stdout)["owner_token"]

            wrong_token = "x" * len(owner_token)
            for command in ("verify", "renew", "yield", "release"):
                with self.subTest(command=command):
                    rejected = self.run_slot(
                        root,
                        command,
                        "task-a",
                        "--owner-token",
                        wrong_token,
                    )
                    self.assertEqual(rejected.returncode, 2)
                    status = self.run_slot(root, "status")
                    payload = json.loads(status.stdout)
                    self.assertEqual(payload["holder"]["task"], "task-a")
            released = self.run_slot(
                root,
                "release",
                "task-a",
                "--owner-token",
                owner_token,
            )
            self.assertEqual(released.returncode, 0, released.stderr)

    def test_status_on_fresh_repo_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            status = self.run_slot(root, "status")

            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(
                json.loads(status.stdout),
                {"holder": None, "holder_expired": False, "queue": []},
            )
            self.assertFalse((root / ".agent_state").exists())

    def test_repeat_claim_never_reauthorizes_critical_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = json.loads(self.run_slot(root, "claim", "task-a").stdout)

            repeated = self.run_slot(
                root,
                "claim",
                "task-a",
                "--owner-token",
                first["owner_token"],
            )

            payload = json.loads(repeated.stdout)
            self.assertEqual(payload["status"], "already_acquired")
            self.assertFalse(payload["enter_critical_section"])
            verified = self.run_slot(
                root,
                "verify",
                "task-a",
                "--owner-token",
                first["owner_token"],
            )
            self.assertEqual(json.loads(verified.stdout)["status"], "verified")

    def test_status_does_not_rewrite_existing_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claim = json.loads(self.run_slot(root, "claim", "task-a").stdout)
            directory = root / ".agent_state" / "merge-slot"
            before = {
                path.relative_to(directory): path.read_bytes()
                for path in directory.rglob("*")
                if path.is_file()
            }

            status = self.run_slot(root, "status")

            self.assertEqual(status.returncode, 0, status.stderr)
            payload = json.loads(status.stdout)
            self.assertNotIn(claim["owner_token"], status.stdout)
            self.assertEqual(payload["holder"]["task"], "task-a")
            after = {
                path.relative_to(directory): path.read_bytes()
                for path in directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
