"""Task and repository locks around collab mutations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

from tests import _support
from tests._collab_support import (
    BLOCK_WRAPPER,
    REPOSITORY_LOCK_BLOCK_WRAPPER,
    SHORT_LANE_CREATE_WAIT_MS,
    close_harness,
    git,
    git_on_path,
    invoke,
    lane_create_wait_ms,
    lock_held_by,
    managed_ref_snapshot,
    seed_managed_task,
    seed_repository,
    seed_task_container,
    send_request,
    spawn_raw_harness,
    wait_until,
    write_git_wrapper,
)

setUpModule = _support.require_pi


class CollabOpExtensionTaskLockTests(unittest.TestCase):
    def test_live_task_lock_refuses_mutation_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True)
            lock = lock_dir / "demo.lock"
            lock.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "started_at": "2026-08-13T00:00:00.000Z",
                        "task_id": "demo"}
                ),
                encoding="utf-8",
            )
            refs_before = managed_ref_snapshot(repository)

            with lane_create_wait_ms():
                observed = invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_busy")
            details = observed["error"]["error"]["details"]
            self.assertEqual(details.get("task_id"), "demo")
            # SL02: lane_create uses a bounded wait rather than immediate fail-fast. The 10 s production
            # default is covered by test_A4_live_external_lock_timeout_returns_task_busy_with_wait_facts.
            self.assertIn("waited_ms", details)
            self.assertEqual(details.get("timeout_ms"), SHORT_LANE_CREATE_WAIT_MS)
            self.assertGreaterEqual(details.get("waited_ms", 0), SHORT_LANE_CREATE_WAIT_MS - 50)
            self.assertEqual(managed_ref_snapshot(repository), refs_before)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer").exists())
            # status is read-only and is not serialized through the task lock.
            status_result = invoke(repository, {"tool": "collab_status", "task_id": "demo"})["result"]
            self.assertEqual(status_result["integration"]["HEAD"], expected["integration_head"])

    def test_stale_task_lock_is_broken_and_lock_is_released_in_finally(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True)
            dead = subprocess.Popen(["true"])
            dead.wait()
            lock = lock_dir / "demo.lock"
            lock.write_text(
                json.dumps(
                    {
                        "pid": dead.pid,
                        "started_at": "2026-08-13T00:00:00.000Z",
                        "task_id": "demo"}
                ),
                encoding="utf-8",
            )

            created = invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"})

            self.assertFalse(created["is_error"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer"), expected["integration_head"])
            self.assertFalse(lock.exists(), "lock was not released in finally")

            # A failing request also releases the lock in finally.
            git(repository, "update-ref", "refs/heads/wave/demo/other", expected["integration_head"])
            refused = invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "other"})
            self.assertTrue(refused["is_error"])
            self.assertEqual(refused["error"]["error"]["code"], "lane_resource_collision")
            self.assertFalse((lock_dir / "demo.lock").exists(), "lock leaked after a failed request")

    def test_task_lock_is_scoped_per_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            seed_managed_task(repository, "other")
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True)
            (lock_dir / "demo.lock").write_text(
                json.dumps({"pid": os.getpid(), "started_at": "2026-08-13T00:00:00.000Z", "task_id": "demo"}),
                encoding="utf-8",
            )

            observed = invoke(repository, {"tool": "collab_lane_create", "task_id": "other", "lane_id": "writer"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                git(repository, "rev-parse", "wave/other/writer"),
                git(repository, "rev-parse", "wave/other/integration"),
            )

    def test_concurrent_stale_takeover_preserves_replacement_and_verifies_release_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True)
            dead = subprocess.Popen(["true"])
            dead.wait()
            planted = lock_dir / "demo.lock"
            planted.write_text(
                json.dumps(
                    {
                        "pid": dead.pid,
                        "started_at": "2026-08-13T00:00:00.000Z",
                        "task_id": "demo",
                        "token": "stale-token"}
                ),
                encoding="utf-8",
            )
            block = base / "block"
            wrapper = write_git_wrapper(base, BLOCK_WRAPPER.replace("__BLOCK__", str(block)))
            first: subprocess.Popen[str] | None = None
            second: subprocess.Popen[str] | None = None
            try:
                with git_on_path(wrapper.parent):
                    first = spawn_raw_harness(repository)
                    second = spawn_raw_harness(repository)
                    first_stdin = first.stdin
                    first_stdout = first.stdout
                    assert first_stdin is not None and first_stdout is not None
                    first_stdin.write(
                        f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
                    )
                    first_stdin.flush()
                    # The first request takes over the stale lock, then blocks in git.
                    self.assertTrue(
                        wait_until(lambda: lock_held_by(planted, first.pid)),
                        "the stale lock was never taken over",
                    )
                    # The verified takeover leaves no quarantine residue.
                    self.assertEqual(list(lock_dir.glob("*.quarantine-*")), [])
                    # Report does not join the repository queue, so it observes the
                    # live task lock directly and fails fast.
                    refused = send_request(
                        second,
                        {"tool": "collab_report", "task_id": "demo", "output_dir": "report-refused"},
                    )
                    self.assertTrue(refused["is_error"])
                    self.assertEqual(refused["error"]["error"]["code"], "task_busy")
                    # Simulate the double-race: while the first request is in
                    # flight, its lock is replaced by a foreign live lock.
                    planted.write_text(
                        json.dumps(
                            {
                                "pid": os.getpid(),
                                "started_at": "2026-08-13T00:00:00.000Z",
                                "task_id": "demo",
                                "token": "foreign-owner-token"}
                        ),
                        encoding="utf-8",
                    )
                    # Release the first request; its release must verify ownership
                    # and must not unlink the replacement.
                    block.write_text("go\n", encoding="utf-8")
                    first_response = json.loads(first_stdout.readline())
                    self.assertFalse(first_response["is_error"])
                    self.assertTrue(planted.exists(), "release deleted a lock it did not own")
                    self.assertIn("foreign-owner-token", planted.read_text(encoding="utf-8"))
                    # The replacement still guards the task.
                    refused_again = send_request(
                        second,
                        {"tool": "collab_report", "task_id": "demo", "output_dir": "report-refused-again"},
                    )
                    self.assertTrue(refused_again["is_error"])
                    self.assertEqual(refused_again["error"]["error"]["code"], "task_busy")
                    # Once the foreign lock is removed, requests proceed normally.
                    planted.unlink()
                    ok = send_request(
                        second,
                        {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "cross"},
                    )
                    self.assertFalse(ok["is_error"])
                    self.assertEqual(
                        git(repository, "rev-parse", "wave/demo/cross"),
                        expected["integration_head"],
                    )
            finally:
                for process in (first, second):
                    if process is not None:
                        close_harness(process)

    def test_release_never_deletes_foreign_replacement_and_restores_byte_for_byte(self) -> None:
        # The replacement is present when release runs; the rename-first
        # release must quarantine it, verify it is foreign, and restore it to
        # the canonical path byte-for-byte instead of deleting it.
        for case in ("inode_replaced", "content_replaced"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lock_dir = repository / ".git/collab-op-locks"
                lock_dir.mkdir(parents=True)
                lock = lock_dir / "demo.lock"
                block = base / "block"
                wrapper = write_git_wrapper(base, BLOCK_WRAPPER.replace("__BLOCK__", str(block)))
                first: subprocess.Popen[str] | None = None
                try:
                    with git_on_path(wrapper.parent), lane_create_wait_ms():
                        first = spawn_raw_harness(repository)
                        first_stdin = first.stdin
                        first_stdout = first.stdout
                        assert first_stdin is not None and first_stdout is not None
                        first_stdin.write(
                            f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
                        )
                        first_stdin.flush()
                        self.assertTrue(
                            wait_until(lambda: lock.exists() and lock_held_by(lock, first.pid)),
                            "request never acquired the lock",
                        )
                        foreign = (
                            json.dumps(
                                {
                                    "pid": os.getpid(),
                                    "started_at": "2026-08-13T00:00:00.000Z",
                                    "task_id": "demo",
                                    "token": "foreign-owner-token"}
                            )
                            + "\n"
                        )
                        if case == "inode_replaced":
                            lock.unlink()
                        lock.write_text(foreign, encoding="utf-8")
                        # Release the request; its release must not delete the
                        # replacement.
                        block.write_text("go\n", encoding="utf-8")
                        response = json.loads(first_stdout.readline())
                        self.assertFalse(response["is_error"])
                        # The foreign replacement was restored byte-for-byte.
                        self.assertEqual(lock.read_text(encoding="utf-8"), foreign)
                        self.assertEqual(list(lock_dir.glob("*.quarantine-*")), [])
                        # The restored foreign lock still guards the task.
                        refused = send_request(
                            first,
                            {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "cross"},
                        )
                        self.assertTrue(refused["is_error"])
                        self.assertEqual(refused["error"]["error"]["code"], "task_busy")
                finally:
                    if first is not None:
                        close_harness(first)

    def test_report_cannot_cross_task_lock_held_by_public_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            block = base / "block"
            wrapper = write_git_wrapper(base, BLOCK_WRAPPER.replace("__BLOCK__", str(block)))
            first: subprocess.Popen[str] | None = None
            second: subprocess.Popen[str] | None = None
            try:
                with git_on_path(wrapper.parent):
                    first = spawn_raw_harness(repository)
                    second = spawn_raw_harness(repository)
                    # The first request blocks inside its git wrapper while it
                    # holds the task lock; its response is read after release.
                    first_stdin = first.stdin
                    first_stdout = first.stdout
                    assert first_stdin is not None and first_stdout is not None
                    first_stdin.write(
                        f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
                    )
                    first_stdin.flush()
                    lock = repository / ".git/collab-op-locks/demo.lock"
                    self.assertTrue(
                        wait_until(lambda: lock.exists()),
                        "first request never acquired the task lock",
                    )
                    # Report stays outside the repository write queue, but its
                    # task snapshot cannot cross the live task lock.
                    refused = send_request(
                        second,
                        {"tool": "collab_report", "task_id": "demo", "output_dir": "report-refused"},
                    )
                    self.assertTrue(refused["is_error"])
                    self.assertEqual(refused["error"]["error"]["code"], "task_busy")
                    self.assertFalse((repository / "report-refused").exists())
                    # Release the first request; it completes and releases the lock.
                    block.write_text("go\n", encoding="utf-8")
                    first_response = json.loads(first_stdout.readline())
                    self.assertFalse(first_response["is_error"])
                    self.assertEqual(git(repository, "rev-parse", "wave/demo/slow"), expected["integration_head"])
                    self.assertFalse(lock.exists(), "lock was not released in finally")
                    # The same report can capture a snapshot after release.
                    retried = send_request(
                        second,
                        {"tool": "collab_report", "task_id": "demo", "output_dir": "report-after"},
                    )
                    self.assertFalse(retried["is_error"])
                    self.assertTrue((repository / "report-after/collab-report.json").is_file())
            finally:
                for process in (first, second):
                    if process is not None:
                        close_harness(process)

    def test_repository_lock_serializes_different_tasks_across_processes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            seed_managed_task(repository, "other")
            release = base / "release-first"
            first_entered = base / "first-entered"
            second_entered = base / "second-entered"
            wrapper = write_git_wrapper(
                base,
                REPOSITORY_LOCK_BLOCK_WRAPPER.replace("__BLOCK__", str(release))
                .replace("__FIRST_ENTERED__", str(first_entered))
                .replace("__SECOND_ENTERED__", str(second_entered)),
            )
            first: subprocess.Popen[str] | None = None
            second: subprocess.Popen[str] | None = None
            worker: threading.Thread | None = None
            second_result: dict[str, object] = {}
            second_error: list[BaseException] = []
            try:
                with git_on_path(wrapper.parent):
                    first = spawn_raw_harness(repository)
                    second = spawn_raw_harness(repository)
                    first_stdin = first.stdin
                    first_stdout = first.stdout
                    assert first_stdin is not None and first_stdout is not None
                    first_stdin.write(
                        f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
                    )
                    first_stdin.flush()
                    repository_lock = repository / ".git/collab-op-locks/.repository.lock"
                    self.assertTrue(wait_until(first_entered.exists), "first task never reached git worktree add")
                    self.assertTrue(
                        lock_held_by(repository_lock, first.pid),
                        "first task did not hold the repository lock",
                    )

                    started = threading.Event()

                    def run_second() -> None:
                        started.set()
                        try:
                            second_result["response"] = send_request(
                                second,
                                {"tool": "collab_lane_create", "task_id": "other", "lane_id": "fast"},
                            )
                        except BaseException as error:
                            second_error.append(error)

                    worker = threading.Thread(target=run_second, daemon=True)
                    worker.start()
                    self.assertTrue(started.wait(timeout=1), "second request did not start")
                    time.sleep(0.25)
                    self.assertTrue(worker.is_alive(), "second task crossed the repository lock")
                    self.assertFalse(second_entered.exists(), "second task reached mutating Git before release")
                    self.assertEqual(git(repository, "branch", "--list", "wave/other/fast"), "")

                    release.write_text("go\n", encoding="utf-8")
                    first_response = json.loads(first_stdout.readline())
                    self.assertFalse(first_response["is_error"])
                    worker.join(timeout=10)
                    self.assertFalse(worker.is_alive(), "second task did not resume after repository lock release")
                    if second_error:
                        raise second_error[0]
                    observed = second_result.get("response")
                    self.assertIsInstance(observed, dict)
                    assert isinstance(observed, dict)
                    self.assertFalse(observed["is_error"])
                    self.assertTrue(second_entered.exists())
                    self.assertEqual(
                        git(repository, "rev-parse", "wave/demo/slow"),
                        git(repository, "rev-parse", "wave/demo/integration"),
                    )
                    self.assertEqual(
                        git(repository, "rev-parse", "wave/other/fast"),
                        git(repository, "rev-parse", "wave/other/integration"),
                    )
                    self.assertFalse(repository_lock.exists(), "repository lock leaked after both requests")
            finally:
                release.write_text("go\n", encoding="utf-8")
                if worker is not None:
                    worker.join(timeout=5)
                for process in (first, second):
                    if process is not None:
                        close_harness(process)

    def test_release_failure_is_reported_and_poisoned_instead_of_hanging_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            block = base / "release-body"
            wrapper = write_git_wrapper(base, BLOCK_WRAPPER.replace("__BLOCK__", str(block)))
            process: subprocess.Popen[str] | None = None
            lock_dir = repository / ".git/collab-op-locks"
            task_lock = lock_dir / "demo.lock"
            repository_lock = lock_dir / ".repository.lock"
            try:
                with git_on_path(wrapper.parent):
                    process = spawn_raw_harness(repository)
                    stdin = process.stdin
                    stdout = process.stdout
                    assert stdin is not None and stdout is not None
                    stdin.write(
                        f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'release-failure'})}\n"
                    )
                    stdin.flush()
                    self.assertTrue(
                        wait_until(lambda: task_lock.exists() and repository_lock.exists()),
                        "request never acquired both locks",
                    )
                    lock_dir.chmod(0o500)
                    block.write_text("go\n", encoding="utf-8")
                    observed = json.loads(stdout.readline())
                    self.assertTrue(observed["is_error"])
                    self.assertEqual(observed["error"]["error"]["code"], "lock_release_failed")
                    self.assertTrue(repository_lock.exists())

                    lock_dir.chmod(0o700)
                    started = time.monotonic()
                    refused = send_request(
                        process,
                        {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "after-release-failure"},
                    )
                    self.assertLess(time.monotonic() - started, 2)
                    self.assertTrue(refused["is_error"])
                    self.assertEqual(refused["error"]["error"]["code"], "lock_release_failed")
                    self.assertEqual(git(repository, "branch", "--list", "wave/demo/after-release-failure"), "")
            finally:
                block.write_text("go\n", encoding="utf-8")
                try:
                    lock_dir.chmod(0o700)
                except FileNotFoundError:
                    pass
                if process is not None:
                    close_harness(process)
                task_lock.unlink(missing_ok=True)
                repository_lock.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
