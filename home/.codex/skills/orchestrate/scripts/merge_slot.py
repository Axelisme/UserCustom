#!/usr/bin/env python3
"""Ephemeral merge slot: claimant-scoped FIFO queue + owner-authenticated lease.

Coordination primitive only — it records who is waiting and who currently holds
the slot, never task workflow state. Every persistence landing claims the slot.
Only the invocation that receives status=acquired may enter the landing
critical section; later commands must present its unguessable owner token.

Resetting .agent_state/merge-slot/ while quiescent loses only the queue and
lease. Never delete it while a command is running or a holder is inside the
landing critical section: recreating the flock file could admit two holders.

The tool performs no Git operations. The landing recipe (rebase off-slot, run
the repo/risk-required broader gate, claim, verify the owner token, re-read the
persistence tip, squash-merge, prove tree identity, then release) lives in the
orchestrate skill.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from orchestrate import verify_release

DEFAULT_LEASE_SECONDS = 600.0
WAIT_POLL_SECONDS = 2.0
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OWNER_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
OWNER_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TICKET_PATTERN = re.compile(r"^(\d{10})-([0-9a-f]{64})-(.+)$")


class SlotError(RuntimeError):
    pass


def _validate_task_id(task: str) -> None:
    if not TASK_ID_PATTERN.fullmatch(task):
        raise SlotError(f"invalid task id: {task!r}")


def _validate_owner_token(owner_token: str) -> None:
    if not OWNER_TOKEN_PATTERN.fullmatch(owner_token):
        raise SlotError("owner token must be 32-128 URL-safe characters")


def _owner_hash(owner_token: str) -> str:
    _validate_owner_token(owner_token)
    return hashlib.sha256(owner_token.encode()).hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


class Slot:
    """All mutations run inside a short exclusive flock critical section."""

    def __init__(self, root: Path) -> None:
        self.dir = root / ".agent_state" / "merge-slot"
        self.queue_dir = self.dir / "queue"
        self.flock_path = self.dir / ".flock"
        self.lock_path = self.dir / "lock"
        self._flock_file: Any = None

    def __enter__(self) -> Slot:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._flock_file = open(self.flock_path, "a+", encoding="utf-8")
        fcntl.flock(self._flock_file.fileno(), fcntl.LOCK_EX)
        self.queue_dir.mkdir(exist_ok=True)
        return self

    def __exit__(self, *_: object) -> None:
        fcntl.flock(self._flock_file.fileno(), fcntl.LOCK_UN)
        self._flock_file.close()
        self._flock_file = None

    def tickets(self) -> list[tuple[int, str, str]]:
        if not self.queue_dir.is_dir():
            return []
        entries: list[tuple[int, str, str]] = []
        for path in self.queue_dir.iterdir():
            match = TICKET_PATTERN.fullmatch(path.name)
            if match is None:
                raise SlotError(
                    f"unrecognized queue entry {path.name!r}; "
                    "remove .agent_state/merge-slot/ to reset the slot"
                )
            task = match.group(3)
            _validate_task_id(task)
            entries.append((int(match.group(1)), match.group(2), task))
        return sorted(entries)

    def queue(self) -> list[str]:
        return [task for _, _, task in self.tickets()]

    def ensure_ticket(self, task: str, owner_hash: str) -> None:
        tickets = self.tickets()
        if any(
            existing_hash == owner_hash and existing_task == task
            for _, existing_hash, existing_task in tickets
        ):
            return
        next_seq = tickets[-1][0] + 1 if tickets else 1
        (self.queue_dir / f"{next_seq:010d}-{owner_hash}-{task}").touch()

    def drop_ticket(self, task: str, owner_hash: str) -> None:
        for seq, existing_hash, existing_task in self.tickets():
            if existing_hash == owner_hash and existing_task == task:
                (
                    self.queue_dir / f"{seq:010d}-{existing_hash}-{existing_task}"
                ).unlink()

    def requeue_ticket(self, task: str, owner_hash: str) -> None:
        self.drop_ticket(task, owner_hash)
        self.ensure_ticket(task, owner_hash)

    def read_lock(self) -> dict[str, Any] | None:
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            lock = json.loads(raw)
            if (
                not isinstance(lock, dict)
                or not isinstance(lock["task"], str)
                or not isinstance(lock["owner_hash"], str)
                or not OWNER_HASH_PATTERN.fullmatch(lock["owner_hash"])
            ):
                raise ValueError("lock shape")
            _validate_task_id(lock["task"])
            float(lock["acquired_at"])
            float(lock["expires_at"])
        except (ValueError, KeyError, TypeError, SlotError) as exc:
            raise SlotError(
                "corrupt lock file; remove .agent_state/merge-slot/ to reset the slot"
            ) from exc
        return lock

    def write_lock(
        self,
        task: str,
        owner_hash: str,
        lease: float,
        *,
        acquired_at: float | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        lock = {
            "task": task,
            "owner_hash": owner_hash,
            "pid": os.getpid(),
            "acquired_at": now if acquired_at is None else acquired_at,
            "expires_at": now + lease,
        }
        _atomic_write_json(self.lock_path, lock)
        return lock

    def clear_expired_lock(self) -> None:
        """An expired holder loses both its lock and claimant-specific ticket."""
        lock = self.read_lock()
        if lock is not None and float(lock["expires_at"]) <= time.time():
            self.drop_ticket(lock["task"], lock["owner_hash"])
            self.lock_path.unlink()


def _public_lock(lock: dict[str, Any] | None) -> dict[str, Any] | None:
    if lock is None:
        return None
    return {
        "task": lock["task"],
        "owner_fingerprint": lock["owner_hash"][:12],
        "pid": lock["pid"],
        "acquired_at": lock["acquired_at"],
        "expires_at": lock["expires_at"],
    }


def _claim_once(
    slot: Slot,
    task: str,
    owner_token: str,
    lease: float,
) -> dict[str, Any]:
    owner_hash = _owner_hash(owner_token)
    slot.clear_expired_lock()
    slot.ensure_ticket(task, owner_hash)
    lock = slot.read_lock()
    tickets = slot.tickets()
    queue = [queued_task for _, _, queued_task in tickets]
    position = next(
        index
        for index, (_, queued_hash, queued_task) in enumerate(tickets, start=1)
        if queued_hash == owner_hash and queued_task == task
    )
    common = {"owner_token": owner_token, "queue": queue}
    if lock is not None:
        if lock["task"] == task and lock["owner_hash"] == owner_hash:
            return {
                "status": "already_acquired",
                "enter_critical_section": False,
                "expires_at": lock["expires_at"],
                **common,
            }
        return {
            "status": "queued",
            "enter_critical_section": False,
            "holder": lock["task"],
            "position": position,
            **common,
        }
    first = tickets[0]
    if first[1] == owner_hash and first[2] == task:
        lock = slot.write_lock(task, owner_hash, lease)
        return {
            "status": "acquired",
            "enter_critical_section": True,
            "expires_at": lock["expires_at"],
            **common,
        }
    return {
        "status": "queued",
        "enter_critical_section": False,
        "holder": None,
        "position": position,
        **common,
    }


def _require_holder(
    slot: Slot,
    task: str,
    owner_token: str,
) -> dict[str, Any]:
    owner_hash = _owner_hash(owner_token)
    slot.clear_expired_lock()
    lock = slot.read_lock()
    if lock is None or lock["task"] != task or lock["owner_hash"] != owner_hash:
        raise SlotError(f"{task!r} owner token does not hold the merge slot")
    return lock


def command_claim(args: argparse.Namespace) -> dict[str, Any]:
    preflight = verify_release(Path(args.skill_dir))
    if not preflight["ok"]:
        raise SlotError("release preflight failed: " + "; ".join(preflight["errors"]))
    _validate_task_id(args.task)
    owner_token = args.owner_token or f"owner_{secrets.token_urlsafe(32)}"
    _validate_owner_token(owner_token)
    deadline = time.time() + args.wait
    while True:
        with Slot(args.root) as slot:
            result = _claim_once(slot, args.task, owner_token, args.lease)
        if result["status"] != "queued" or time.time() >= deadline:
            return {
                **result,
                "release_preflight": {
                    "skill_version": preflight["skill_version"],
                    "orchestrate_compat": preflight["orchestrate_compat"],
                },
            }
        time.sleep(min(WAIT_POLL_SECONDS, max(deadline - time.time(), 0.0)))


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    _validate_task_id(args.task)
    with Slot(args.root) as slot:
        lock = _require_holder(slot, args.task, args.owner_token)
        return {
            "status": "verified",
            "task": args.task,
            "expires_at": lock["expires_at"],
        }


def command_renew(args: argparse.Namespace) -> dict[str, Any]:
    _validate_task_id(args.task)
    with Slot(args.root) as slot:
        lock = _require_holder(slot, args.task, args.owner_token)
        lock = slot.write_lock(
            args.task,
            lock["owner_hash"],
            args.lease,
            acquired_at=float(lock["acquired_at"]),
        )
        return {"status": "renewed", "expires_at": lock["expires_at"]}


def command_release(args: argparse.Namespace) -> dict[str, Any]:
    _validate_task_id(args.task)
    with Slot(args.root) as slot:
        lock = _require_holder(slot, args.task, args.owner_token)
        slot.drop_ticket(args.task, lock["owner_hash"])
        slot.lock_path.unlink()
        return {"status": "released", "queue": slot.queue()}


def command_yield(args: argparse.Namespace) -> dict[str, Any]:
    _validate_task_id(args.task)
    with Slot(args.root) as slot:
        lock = _require_holder(slot, args.task, args.owner_token)
        slot.requeue_ticket(args.task, lock["owner_hash"])
        slot.lock_path.unlink()
        return {"status": "yielded", "queue": slot.queue()}


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    slot = Slot(args.root)
    if not slot.dir.exists():
        return {"holder": None, "holder_expired": False, "queue": []}
    if not slot.flock_path.is_file():
        if slot.lock_path.exists() or slot.queue_dir.exists():
            raise SlotError(
                "merge-slot data exists without .flock; reset only while quiescent"
            )
        return {"holder": None, "holder_expired": False, "queue": []}
    with open(slot.flock_path, "r", encoding="utf-8") as flock_file:
        fcntl.flock(flock_file.fileno(), fcntl.LOCK_SH)
        try:
            lock = slot.read_lock()
            return {
                "holder": _public_lock(lock),
                "holder_expired": (
                    lock is not None and float(lock["expires_at"]) <= time.time()
                ),
                "queue": slot.queue(),
            }
        finally:
            fcntl.flock(flock_file.fileno(), fcntl.LOCK_UN)


def _add_required_owner_token(command: argparse.ArgumentParser) -> None:
    command.add_argument("--owner-token", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-dir",
        default=str(Path(__file__).resolve().parent.parent),
        help="orchestrate skill directory for claim preflight",
    )
    parser.add_argument("--root", type=Path, required=True, help="repo root")
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="read-only slot state")
    status.set_defaults(handler=command_status)

    claim = commands.add_parser("claim", help="take a claimant-specific FIFO ticket")
    claim.add_argument("task")
    claim.add_argument("--owner-token")
    claim.add_argument(
        "--wait", type=float, default=0.0, help="seconds to keep retrying"
    )
    claim.add_argument("--lease", type=float, default=DEFAULT_LEASE_SECONDS)
    claim.set_defaults(handler=command_claim)

    verify = commands.add_parser(
        "verify", help="verify owner token immediately before persistence mutation"
    )
    verify.add_argument("task")
    _add_required_owner_token(verify)
    verify.set_defaults(handler=command_verify)

    renew = commands.add_parser("renew", help="extend the held lease")
    renew.add_argument("task")
    renew.add_argument("--lease", type=float, default=DEFAULT_LEASE_SECONDS)
    _add_required_owner_token(renew)
    renew.set_defaults(handler=command_renew)

    release = commands.add_parser("release", help="free the slot and drop this ticket")
    release.add_argument("task")
    _add_required_owner_token(release)
    release.set_defaults(handler=command_release)

    yield_cmd = commands.add_parser(
        "yield", help="free the slot and move this ticket to the back"
    )
    yield_cmd.add_argument("task")
    _add_required_owner_token(yield_cmd)
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
