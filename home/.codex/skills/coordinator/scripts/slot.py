#!/usr/bin/env python3
"""Run one heavy command in a shared CPU slot so parallel agents do not oversubscribe the machine.

Usage: slot.py [--slots N] [--cores C] [--min-ram-gb G] [--wait-limit S] [--locks DIR]
               <timeout-seconds> [--] <command> [args...]

The CPUs this process may use split into N slots of C cores each. The command waits until a slot
is free and MemAvailable reaches G GB, then runs pinned to that slot's cores and is killed past the
timeout. Slots are flock files under DIR, by default `.agent_state/locks/` in the main checkout, so
every worktree of a repository shares them. The command inherits its lock, so the slot stays taken
until the command and its children exit, and a crash leaves no stale slot.

Exit status: the command's own; 124 when the timeout kills it; 75 when --wait-limit passes before a
slot frees; 2 on bad usage.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

MEMINFO = Path("/proc/meminfo")
EXIT_NO_SLOT = 75  # EX_TEMPFAIL
EXIT_TIMEOUT = 124  # as timeout(1)
KILL_GRACE_SECONDS = 10


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="slot.py", description="Run a command in a shared CPU slot.")
    parser.add_argument("--slots", type=int, default=3)
    parser.add_argument("--cores", type=int, default=2)
    parser.add_argument("--min-ram-gb", type=float, default=4.0)
    parser.add_argument("--wait-limit", type=float, help="seconds to wait; default waits forever")
    parser.add_argument("--locks", type=Path, help="lock directory shared by every caller")
    parser.add_argument("--poll", type=float, default=5.0, help=argparse.SUPPRESS)
    parser.add_argument("timeout", type=float, help="seconds the command may run")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv[1:])
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command")
    cpus = sorted(os.sched_getaffinity(0))
    if args.slots < 1 or args.cores < 1 or args.slots * args.cores > len(cpus):
        parser.error(f"{args.slots} slots x {args.cores} cores do not fit {len(cpus)} CPUs")
    args.cpus = [cpus[i * args.cores : (i + 1) * args.cores] for i in range(args.slots)]
    return args


def default_locks(cwd: Path | None) -> Path:
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(common).parent / ".agent_state" / "locks"


def mem_available_gb(meminfo: Path) -> float:
    for line in meminfo.read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024 / 1024
    return float("inf")  # no reading to wait on


def try_acquire(locks: Path, slots: int) -> tuple[int, int] | None:
    """Return (slot index, locked fd) for the first free slot, or None when all are held."""
    locks.mkdir(parents=True, exist_ok=True)
    for index in range(slots):
        fd = os.open(locks / f"slot-{index}.lock", os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            continue
        return index, fd
    return None


def wait_for_slot(args: argparse.Namespace, locks: Path, meminfo: Path) -> tuple[int, int] | None:
    deadline = None if args.wait_limit is None else time.monotonic() + args.wait_limit
    reported = ""
    while True:
        have = mem_available_gb(meminfo)
        if have < args.min_ram_gb:
            reason = f"waiting for {args.min_ram_gb:g} GB MemAvailable (have {have:.1f})"
        else:
            held = try_acquire(locks, args.slots)
            if held:
                return held
            reason = f"waiting for one of {args.slots} slots in {locks}"
        if reason != reported:
            print(f"slot.py: {reason}", file=sys.stderr, flush=True)
            reported = reason
        if deadline is not None and time.monotonic() >= deadline:
            return None
        time.sleep(args.poll)


def run(command: list[str], cpus: list[int], fd: int, timeout: float, cwd: Path | None) -> int:
    child = subprocess.Popen(
        command,
        cwd=cwd,
        pass_fds=(fd,),
        start_new_session=True,
        preexec_fn=lambda: os.sched_setaffinity(0, cpus),
    )
    # The child runs in its own session so a timeout can kill its whole tree; forward the signals
    # that would have reached it from the terminal or an agent's kill.
    def forward(signum: int, _frame: object) -> None:
        os.killpg(child.pid, signum)

    previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        code = child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        print(f"slot.py: killed after {timeout:g}s", file=sys.stderr)
        return EXIT_TIMEOUT
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return code if code >= 0 else 128 - code


def main(argv: list[str], cwd: Path | None = None, meminfo: Path = MEMINFO) -> int:
    args = parse(argv)
    try:
        locks = args.locks or default_locks(cwd)
    except subprocess.CalledProcessError:
        print("slot.py: not inside a git repository; pass --locks", file=sys.stderr)
        return 2
    held = wait_for_slot(args, locks, meminfo)
    if held is None:
        return EXIT_NO_SLOT
    index, fd = held
    try:
        return run(args.command, args.cpus[index], fd, args.timeout, cwd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
