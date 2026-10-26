#!/usr/bin/env python3
"""One patrol pass over an effort map's running tasks.

Usage: python3 patrol.py <map-dir>

For every `running` Tasks line it prints the agent's herdr status, the task-flow
frontier and doing tickets, unanswered questions, the scratch size, and the size
of any Python harness in scratch, flagged past HARNESS_WARN_LINES lines or when it
carries its own tests or pyrightconfig; idle or done agents also get a short tail. A question counts as answered when it has a
sibling `.ruling.md`, contains `## Ruling`, or a map decision names its file.
The last line reports MemAvailable. Exit status is 0 unless the map is unreadable.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

TASK_LINE = re.compile(
    r"^- (?P<task>\S+) — step \S+ — Base: \S+ — herdr: (?P<name>\S+) — (?P<state>\S+)"
)
CHECK = Path(__file__).resolve().parents[2] / "task-flow" / "scripts" / "check.py"
SCRATCH_WARN_BYTES = 10 * 1024 * 1024
# A one-off acceptance harness fits one 100-200 line script; past this it has grown into a project.
HARNESS_WARN_LINES = 300


def run(args: list[str]) -> str:
    """Return stdout+stderr of args; a missing binary returns its error text."""
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"<{args[0]} failed: {error}>"
    return done.stdout + done.stderr


def herdr_cli(args: list[str]) -> str:
    return run(["herdr", *args])


def herdr_agents(herdr: Callable[[list[str]], str]) -> dict[str, tuple[str, str]]:
    """Map agent name -> (pane, status); empty when herdr is unavailable."""
    try:
        listing = json.loads(herdr(["agent", "list"]))
    except json.JSONDecodeError:
        return {}
    return {
        agent["name"]: (agent.get("pane_id", "?"), agent.get("agent_status", "?"))
        for agent in listing.get("result", {}).get("agents", [])
        if agent.get("name")
    }


def tail(name: str, herdr: Callable[[list[str]], str]) -> list[str]:
    """Last non-empty screen lines; falls back to the visible screen when busy."""
    text = herdr(["agent", "read", name, "--source", "recent-unwrapped", "--lines", "30"])
    if "agent_not_idle" in text:
        text = herdr(["agent", "read", name, "--source", "visible"])
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if not line.startswith(("───", "Cost ", "7d:"))]
    return lines[-6:]


def unanswered(task_dir: Path, decisions_text: str) -> list[str]:
    questions = task_dir / "scratch" / "questions"
    if not questions.is_dir():
        return []
    open_items = []
    for path in sorted(questions.glob("*.md")):
        if path.name.endswith(".ruling.md"):
            continue
        answered = (
            path.with_name(path.stem + ".ruling.md").exists()
            or "## Ruling" in path.read_text(encoding="utf-8", errors="replace")
            or path.name in decisions_text
        )
        if not answered:
            open_items.append(str(path))
    return open_items


def dir_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def harness(scratch: Path) -> str | None:
    """Size of the Python harness in scratch, flagged once it outgrows a one-off script."""
    scripts = [p for p in scratch.rglob("*.py") if p.is_file() and not p.is_symlink()]
    if not scripts:
        return None
    lines = sum(len(p.read_text(encoding="utf-8", errors="replace").splitlines()) for p in scripts)
    flags = []
    if lines > HARNESS_WARN_LINES:
        flags.append(f"over {HARNESS_WARN_LINES} lines")
    if any(p.name.startswith("test_") or "tests" in p.relative_to(scratch).parts for p in scripts):
        flags.append("own tests")
    if any(scratch.rglob("pyrightconfig.json")):
        flags.append("own pyrightconfig")
    note = f"  ({', '.join(flags)})" if flags else ""
    return f"harness {len(scripts)} py files, {lines} lines{note}"


def mem_available_gb() -> str:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return f"{int(line.split()[1]) / 1024 / 1024:.1f} GB"
    return "?"


def main(argv: list[str], herdr: Callable[[list[str]], str] = herdr_cli) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    map_dir = Path(argv[1]).resolve()
    map_text = (map_dir / "MAP.md").read_text(encoding="utf-8")
    plans = map_dir.parents[1] / "plans"
    decisions_text = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in (map_dir / "decisions").glob("*.md")
    )
    agents = herdr_agents(herdr)
    running = [m for m in map(TASK_LINE.match, map_text.splitlines()) if m and m["state"] == "running"]
    if not running:
        print("no running tasks")
    for match in running:
        task, name = match["task"], match["name"]
        pane, status = agents.get(name, ("-", "NAME MISSING: rename the pane"))
        print(f"== {task}  herdr {name} {pane} {status}")
        task_dir = plans / task
        if not task_dir.is_dir():
            print(f"   TASK DIR MISSING {task_dir}")
            continue
        report = run([sys.executable, str(CHECK), str(task_dir)]).strip().splitlines()
        print("   " + " | ".join(report[-3:]))
        for question in unanswered(task_dir, decisions_text):
            print(f"   QUESTION {question}")
        scratch = task_dir / "scratch"
        if scratch.is_dir():
            size = dir_bytes(scratch)
            flag = "  (over 10 MB)" if size > SCRATCH_WARN_BYTES else ""
            print(f"   scratch {size / 1024 / 1024:.1f} MB{flag}")
            report = harness(scratch)
            if report:
                print(f"   {report}")
        if status in ("idle", "done"):
            for line in tail(name, herdr):
                print(f"   | {line[:160]}")
    print(f"MemAvailable {mem_available_gb()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
