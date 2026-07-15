from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"
)


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


def initialize_repo(root: Path, *, ignore_agent_state: bool = True) -> str:
    git(root, "init", "-b", "task/demo")
    git(root, "config", "user.name", "Orchestrate Test")
    git(root, "config", "user.email", "orchestrate@example.invalid")
    if ignore_agent_state:
        (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    paths = ["README.md"]
    if ignore_agent_state:
        paths.append(".gitignore")
    git(root, "add", *paths)
    git(root, "commit", "-m", "base")
    return git(root, "rev-parse", "HEAD")


def queue_item(
    *,
    item_id: str,
    order: int,
    role: str,
    lease_id: str,
    generation: int,
    basis_sha: str,
    hard_critical_axes: str = "none",
) -> str:
    return f"""---
queue_version: 1
item_id: {item_id}
order: {order}
role: {role}
lease_id: {lease_id}
lease_generation: {generation}
basis_sha: {basis_sha}
hard_critical_axes: {hard_critical_axes}
---

# {item_id}

objective: deliver the frozen behavior
dependencies: already satisfied
scope: assigned path only
acceptance: targeted test plus independent oracle
named_review_risks: none
stop_conditions: stale basis or scope collision
"""


def write_item(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


class OrchestrateQueueTests(unittest.TestCase):
    def queue_args(
        self,
        root: Path,
        *,
        role: str = "writer",
        generation: int = 2,
    ) -> tuple[str, ...]:
        return (
            "--root",
            str(root),
            "--task-id",
            "demo",
            "--role",
            role,
            "--lease-id",
            "writer1" if role == "writer" else "reviewer1",
            "--generation",
            str(generation),
        )

    def test_inspect_missing_queue_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_repo(root)

            result = run_cli("queue", "inspect", *self.queue_args(root))

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["items"], [])
            self.assertEqual(payload["pending_artifacts"], [])
            self.assertFalse(payload["completion_inferred"])
            self.assertFalse((root / ".agent_state").exists())

    def test_publish_batch_and_inspect_ordered_items(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            later = write_item(
                root,
                "later.md",
                queue_item(
                    item_id="slice-b",
                    order=20,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )
            earlier = write_item(
                root,
                "earlier.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )

            published = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(later),
                "--input",
                str(earlier),
            )

            self.assertEqual(published.returncode, 0, published.stderr)
            publish_payload = json.loads(published.stdout)
            self.assertFalse(publish_payload["readiness_inferred"])
            self.assertEqual(
                [item["item_id"] for item in publish_payload["items"]],
                ["slice-a", "slice-b"],
            )
            queue_path = (
                root
                / ".agent_state"
                / "orchestrate"
                / "demo"
                / "queues"
                / "writer1"
                / "g0002"
            )
            self.assertEqual(
                sorted(path.name for path in queue_path.glob("*.md")),
                ["000010-slice-a.md", "000020-slice-b.md"],
            )
            self.assertEqual(list(queue_path.glob("*.pending-*")), [])

            inspected = run_cli("queue", "inspect", *self.queue_args(root))
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            inspect_payload = json.loads(inspected.stdout)
            self.assertEqual(
                [item["item_id"] for item in inspect_payload["items"]],
                ["slice-a", "slice-b"],
            )
            self.assertTrue(
                all(len(item["sha256"]) == 64 for item in inspect_payload["items"])
            )

    def test_publish_validates_entire_batch_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            valid = write_item(
                root,
                "valid.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )
            invalid = write_item(root, "invalid.md", "not front matter\n")

            result = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(valid),
                "--input",
                str(invalid),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("front matter", result.stderr)
            self.assertFalse((root / ".agent_state").exists())

    def test_publish_rejects_unignored_or_hard_critical_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root, ignore_agent_state=False)
            item = write_item(
                root,
                "item.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )
            result = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(item),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("gitignored", result.stderr)
            self.assertFalse((root / ".agent_state").exists())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            item = write_item(
                root,
                "item.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                    hard_critical_axes="security",
                ),
            )
            result = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(item),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("normal writer/reviewer", result.stderr)
            self.assertFalse((root / ".agent_state").exists())

    def test_publish_rejects_duplicate_item_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            item = write_item(
                root,
                "item.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )
            first = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(item),
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            path = Path(json.loads(first.stdout)["items"][0]["path"])
            original = path.read_bytes()

            duplicate = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(item),
            )

            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("already exists", duplicate.stderr)
            self.assertEqual(path.read_bytes(), original)

    def test_concurrent_publishers_cannot_overwrite_the_same_item(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            item = write_item(
                root,
                "item.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )
            command = [
                sys.executable,
                str(SCRIPT),
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(item),
            ]
            processes = [
                subprocess.Popen(
                    command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                for _ in range(2)
            ]
            results = [process.communicate() for process in processes]

            self.assertEqual(
                sorted(process.returncode for process in processes), [0, 2]
            )
            self.assertTrue(
                any("already exists" in stderr for _, stderr in results), results
            )
            queue_path = (
                root
                / ".agent_state"
                / "orchestrate"
                / "demo"
                / "queues"
                / "writer1"
                / "g0002"
            )
            self.assertEqual(
                [path.name for path in queue_path.glob("*.md")],
                ["000010-slice-a.md"],
            )

    def test_publish_rejects_a_mismatched_lease_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            item = write_item(
                root,
                "item.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=1,
                    basis_sha=basis,
                ),
            )

            result = run_cli(
                "queue",
                "publish",
                *self.queue_args(root, generation=2),
                "--input",
                str(item),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("lease_generation", result.stderr)
            self.assertFalse((root / ".agent_state").exists())

    def test_remove_requires_exact_hash_and_terminal_delivery_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            item = write_item(
                root,
                "item.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )
            published = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(item),
            )
            self.assertEqual(published.returncode, 0, published.stderr)
            published_item = json.loads(published.stdout)["items"][0]
            path = Path(published_item["path"])

            no_authorization = run_cli(
                "queue",
                "remove",
                *self.queue_args(root),
                "--item-id",
                "slice-a",
                "--order",
                "10",
                "--expected-sha256",
                published_item["sha256"],
            )
            self.assertEqual(no_authorization.returncode, 2)
            self.assertTrue(path.exists())

            wrong_hash = run_cli(
                "queue",
                "remove",
                *self.queue_args(root),
                "--item-id",
                "slice-a",
                "--order",
                "10",
                "--expected-sha256",
                "0" * 64,
                "--terminal-delivery-confirmed",
            )
            self.assertEqual(wrong_hash.returncode, 2)
            self.assertIn("hash", wrong_hash.stderr)
            self.assertTrue(path.exists())

            removed = run_cli(
                "queue",
                "remove",
                *self.queue_args(root),
                "--item-id",
                "slice-a",
                "--order",
                "10",
                "--expected-sha256",
                published_item["sha256"],
                "--terminal-delivery-confirmed",
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)
            payload = json.loads(removed.stdout)
            self.assertTrue(payload["terminal_delivery_declared"])
            self.assertFalse(payload["terminal_delivery_inferred"])
            self.assertFalse(payload["completion_inferred"])
            self.assertFalse(path.exists())

    def test_root_stale_reconciliation_requires_ended_consumer_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            item = write_item(
                root,
                "item.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )
            published = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(item),
            )
            self.assertEqual(published.returncode, 0, published.stderr)
            published_item = json.loads(published.stdout)["items"][0]
            path = Path(published_item["path"])
            base_remove = (
                "queue",
                "remove",
                *self.queue_args(root),
                "--item-id",
                "slice-a",
                "--order",
                "10",
                "--expected-sha256",
                published_item["sha256"],
                "--stale-reconciliation-confirmed",
            )

            unsafe = run_cli(*base_remove, "--reason", "stale basis")
            self.assertEqual(unsafe.returncode, 2)
            self.assertIn("consumer-ended", unsafe.stderr)
            self.assertTrue(path.exists())

            removed = run_cli(
                *base_remove,
                "--consumer-ended-confirmed",
                "--reason",
                "stale basis after session recovery",
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)
            payload = json.loads(removed.stdout)
            self.assertEqual(payload["removal_authorization"], "stale-reconciliation")
            self.assertTrue(payload["consumer_ended_declared"])
            self.assertFalse(payload["terminal_delivery_declared"])
            self.assertFalse(payload["completion_inferred"])
            self.assertFalse(path.exists())

    def test_inspect_reports_stale_pending_artifact_without_removing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            queue_path = (
                root
                / ".agent_state"
                / "orchestrate"
                / "demo"
                / "queues"
                / "writer1"
                / "g0002"
            )
            queue_path.mkdir(parents=True)
            pending = queue_path / ".000010-slice-a.md.pending-crash"
            pending.write_text("partial", encoding="utf-8")

            inspected = run_cli("queue", "inspect", *self.queue_args(root))

            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            payload = json.loads(inspected.stdout)
            self.assertEqual(payload["pending_artifacts"], [pending.name])
            self.assertTrue(pending.exists())

            item = write_item(
                root,
                "item.md",
                queue_item(
                    item_id="slice-a",
                    order=10,
                    role="writer",
                    lease_id="writer1",
                    generation=2,
                    basis_sha=basis,
                ),
            )
            publish = run_cli(
                "queue",
                "publish",
                *self.queue_args(root),
                "--input",
                str(item),
            )
            self.assertEqual(publish.returncode, 2)
            self.assertIn("unreconciled artifacts", publish.stderr)
            self.assertTrue(pending.exists())


if __name__ == "__main__":
    unittest.main()
