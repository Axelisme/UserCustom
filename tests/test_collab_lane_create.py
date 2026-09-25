"""collab_lane create."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    git,
    invoke,
    last_telemetry_event,
    seed_managed_task,
    seed_repository,
    seed_task_container,
)

setUpModule = _support.require_pi


class CollabOpExtensionLaneCreateRegressionTests(unittest.TestCase):
    def test_lane_create_uses_committed_integration_tip_and_records_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            committed_tip = expected["integration_head"]
            (integration / "tracked.txt").write_text("dirty integration\n", encoding="utf-8")
            (integration / "untracked.txt").write_text("exclude me\n", encoding="utf-8")
            (repository / ".git/info/exclude").write_text("ignored.txt\n", encoding="utf-8")
            (integration / "ignored.txt").write_text("exclude ignored\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": "writer",
                    "comment": "  review 🧭  "},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["ok"])
            self.assertEqual(observed["result"]["tool_version"], 1)
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            self.assertEqual(git(lane, "rev-parse", "HEAD"), committed_tip)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual((integration / "tracked.txt").read_text(encoding="utf-8"), "dirty integration\n")
            self.assertEqual((integration / "untracked.txt").read_text(encoding="utf-8"), "exclude me\n")
            self.assertEqual((integration / "ignored.txt").read_text(encoding="utf-8"), "exclude ignored\n")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-create")
            self.assertEqual(event["lane_id"], "writer")
            self.assertEqual(event["comment"], "review 🧭")
            self.assertEqual(event["lane_sha"], committed_tip)
            self.assertEqual(event["integration_sha"], committed_tip)

    def test_lane_create_rejects_reserved_lane_and_invalid_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)

            for lane_id, comment, expected_code in (
                ("integration", None, "reserved_lane"),
                ("writer", "🧭" * 501, "invalid_comment"),
                ("writer", "control\x01byte", "invalid_comment"),
            ):
                request: dict[str, object] = {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": lane_id}
                if comment is not None:
                    request["comment"] = comment
                observed = invoke(repository, request)
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], expected_code)
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer").exists())

            valid = invoke(
                repository,
                {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": "unicode",
                    "comment": "🧭" * 500},
            )
            self.assertFalse(valid["is_error"])

    def test_lane_create_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())

    def test_lane_create_collision_refuses_before_mutation(self) -> None:
        for collision in ("branch", "path"):
            with self.subTest(collision=collision), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                expected = seed_managed_task(repository)
                lane = repository / ".agent_state/worktrees/demo/lanes/writer"
                if collision == "branch":
                    git(repository, "branch", "wave/demo/writer", expected["base"])
                else:
                    lane.mkdir(parents=True)
                    (lane / "sentinel.bin").write_bytes(b"preserve\x00\xff")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "lane_resource_collision")
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertEqual(
                    git(repository, "rev-parse", "wave/demo/integration"),
                    expected["integration_head"],
                )
                if collision == "path":
                    self.assertEqual((lane / "sentinel.bin").read_bytes(), b"preserve\x00\xff")

    def test_lane_create_failure_leaves_no_partial_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            lock = repository / ".git/refs/heads/wave/demo/writer.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertTrue(observed["is_error"])
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer").exists())
            self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock\n")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])

    def test_lane_create_warns_when_nine_existing_lanes_have_uncollected_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            for index in range(9):
                lane_id = f"writer-{index:02d}"
                created = invoke(
                    repository,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": lane_id},
                )
                self.assertFalse(created["is_error"])
                lane = repository / ".agent_state/worktrees/demo/lanes" / lane_id
                (lane / f"{lane_id}.txt").write_text("work\n", encoding="utf-8")
                git(lane, "add", f"{lane_id}.txt")
                git(lane, "commit", "-m", f"work {lane_id}")

            observed = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer-final"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("9 or more" in warning for warning in observed["result"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
