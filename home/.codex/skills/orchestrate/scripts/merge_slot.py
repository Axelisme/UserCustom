#!/usr/bin/env python3
"""Ephemeral merge slot: FIFO queue + lease lock for landing task branches.

Coordination primitive only — it records who is waiting and who currently holds
the slot, never any task state. Resetting ``.agent_state/merge-slot/`` while
quiescent loses only the queue and lease. Never delete it while a command is
running or a holder is inside the landing critical section: recreating the
flock file could allow two holders to land concurrently.

The tool performs no Git operations. The landing recipe (rebase off-slot, run
the repo/risk-required broader gate, claim, re-read the persistence tip,
squash-merge or yield) lives in the orchestrate skill.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_LEASE_SECONDS = 600.0
WAIT_POLL_SECONDS = 2.0
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TICKET_PATTERN = re.compile(r"^(\d{10})-(.+)$")


class SlotError(RuntimeError):
    pass


def _validate_task_id(task: str) -> None:
    if not TASK_ID_PATTERN.fullmatch(task):
        raise SlotError(f"invalid task id: {task!r}")


class Slot:
    """All mutations run inside a short flock critical section."""

    def __init__(self, root: Path) -> None:
        self.dir = root / ".agent_state" / "merge-slot"
        self.queue_dir = self.dir / "queue"
        self.lock_path = self.dir / "lock"
        self._flock_file: Any = None

    def __enter__(self) -> Slot:
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self._flock_file = open(self.dir / ".flock", "a+", encoding="utf-8")
        fcntl.flock(self._flock_file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_: object) -> None:
        fcntl.flock(self._flock_file.fileno(), fcntl.LOCK_UN)
        self._flock_file.close()
        self._flock_file = None

    def tickets(self) -> list[tuple[int, str]]:
        entries: list[tuple[int, str]] = []
        for path in self.queue_dir.iterdir():
            match = TICKET_PATTERN.fullmatch(path.name)
            if match is None:
                raise SlotError(
                    f"unrecognized queue entry {path.name!r}; "
                    "remove .agent_state/merge-slot/ to reset the slot"
                )
            entries.append((int(match.group(1)), match.group(2)))
        return sorted(entries)

    def queue(self) -> list[str]:
        return [task for _, task in self.tickets()]

    def ensure_ticket(self, task: str) -> None:
        tickets = self.tickets()
        if any(name == task for _, name in tickets):
            return
        next_seq = tickets[-1][0] + 1 if tickets else 1
        (self.queue_dir / f"{next_seq:010d}-{task}").touch()

    def drop_ticket(self, task: str) -> None:
        for seq, name in self.tickets():
            if name == task:
                (self.queue_dir / f"{seq:010d}-{name}").unlink()

    def requeue_ticket(self, task: str) -> None:
        self.drop_ticket(task)
        self.ensure_ticket(task)

    def read_lock(self) -> dict[str, Any] | None:
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            lock = json.loads(raw)
            if not isinstance(lock, dict) or not isinstance(lock["task"], str):
                raise ValueError("lock shape")
            float(lock["expires_at"])
        except (ValueError, KeyError, TypeError) as exc:
            raise SlotError(
                "corrupt lock file; remove .agent_state/merge-slot/ to reset the slot"
            ) from exc
        return lock

    def write_lock(self, task: str, lease: float) -> dict[str, Any]:
        now = time.time()
        lock = {
            "task": task,
            "pid": os.getpid(),
            "acquired_at": now,
            "expires_at": now + lease,
        }
        self.lock_path.write_text(json.dumps(lock), encoding="utf-8")
        return lock

    def clear_expired_lock(self) -> None:
        """An expired holder loses both the lock and its queue ticket."""
        lock = self.read_lock()
        if lock is not None and float(lock["expires_at"]) <= time.time():
            self.lock_path.unlink()
            self.drop_ticket(lock["task"])


def _claim_once(slot: Slot, task: str, lease: float) -> dict[str, Any]:
    slot.clear_expired_lock()
    slot.ensure_ticket(task)
    lock = slot.read_lock()
    queue = slot.queue()
    if lock is not None:
        if lock["task"] == task:
            return {"status": "held", "expires_at": lock["expires_at"], "queue": queue}
        return {
            "status": "queued",
            "holder": lock["task"],
            "position": queue.index(task) + 1,
            "queue": queue,
        }
    if queue[0] == task:
        lock = slot.write_lock(task, lease)
        return {"status": "acquired", "expires_at": lock["expires_at"], "queue": queue}
    return {
        "status": "queued",
        "holder": None,
        "position": queue.index(task) + 1,
        "queue": queue,
    }


def command_claim(args: argparse.Namespace) -> dict[str, Any]:
    _validate_task_id(args.task)
    deadline = time.time() + args.wait
    while True:
        with Slot(args.root) as slot:
            result = _claim_once(slot, args.task, args.lease)
        if result["status"] != "queued" or time.time() >= deadline:
            return result
        time.sleep(min(WAIT_POLL_SECONDS, max(deadline - time.time(), 0.0)))


def command_renew(args: argparse.Namespace) -> dict[str, Any]:
    _validate_task_id(args.task)
    with Slot(args.root) as slot:
        slot.clear_expired_lock()
        lock = slot.read_lock()
        if lock is None or lock["task"] != args.task:
            raise SlotError(f"{args.task!r} does not hold the merge slot")
        lock = slot.write_lock(args.task, args.lease)
        return {"status": "renewed", "expires_at": lock["expires_at"]}


def command_release(args: argparse.Namespace) -> dict[str, Any]:
    _validate_task_id(args.task)
    with Slot(args.root) as slot:
        lock = slot.read_lock()
        if lock is not None and lock["task"] == args.task:
            slot.lock_path.unlink()
        slot.drop_ticket(args.task)
        return {"status": "released", "queue": slot.queue()}


def command_yield(args: argparse.Namespace) -> dict[str, Any]:
    _validate_task_id(args.task)
    with Slot(args.root) as slot:
        slot.clear_expired_lock()
        lock = slot.read_lock()
        if lock is None or lock["task"] != args.task:
            raise SlotError(f"{args.task!r} does not hold the merge slot")
        slot.lock_path.unlink()
        slot.requeue_ticket(args.task)
        return {"status": "yielded", "queue": slot.queue()}


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    with Slot(args.root) as slot:
        lock = slot.read_lock()
        return {
            "holder": lock,
            "holder_expired": (
                lock is not None and float(lock["expires_at"]) <= time.time()
            ),
            "queue": slot.queue(),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="repo root")
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="read-only slot state")
    status.set_defaults(handler=command_status)

    claim = commands.add_parser("claim", help="take a ticket and try to acquire")
    claim.add_argument("task")
    claim.add_argument(
        "--wait", type=float, default=0.0, help="seconds to keep retrying"
    )
    claim.add_argument("--lease", type=float, default=DEFAULT_LEASE_SECONDS)
    claim.set_defaults(handler=command_claim)

    renew = commands.add_parser("renew", help="extend the held lease")
    renew.add_argument("task")
    renew.add_argument("--lease", type=float, default=DEFAULT_LEASE_SECONDS)
    renew.set_defaults(handler=command_renew)

    release = commands.add_parser("release", help="free the slot and drop the ticket")
    release.add_argument("task")
    release.set_defaults(handler=command_release)

    yield_cmd = commands.add_parser(
        "yield", help="free the slot and move the ticket to the back"
    )
    yield_cmd.add_argument("task")
    yield_cmd.set_defaults(handler=command_yield)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except SlotError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
