#!/usr/bin/env python3
"""One patrol pass over an effort map's running tasks.

Usage: python3 patrol.py <map-dir> [--questions]

For every `running` Tasks line it prints the agent's herdr status, the task-flow
frontier and doing tickets, open questions with their tier, the scratch size, and the
size of any Python harness in scratch, flagged past HARNESS_WARN_LINES lines or when it
carries its own tests or pyrightconfig; idle or done agents also get a short tail.
Then come the map's `tidy suggested:` lines, the number of open design questions, and
MemAvailable.

A question's tier is the value of its `Tier:` line (`local`, `simple`, `full`, or
`process`); a file without one is `untiered`. A question counts as answered when it has a
sibling `.ruling.md`, contains `## Ruling`, or a map decision names its file. Every tier
but `process` and `local` (the task's own call, sent back by the coordinator) is a design
question.

With --questions it prints only the open design questions, one per line as
`<tier> <path>`, followed by `  claimed by <name>` when the map's
`scratch/designer-<name>.md` names that path; or `no open design questions`.

Exit status is 0 unless the map is unreadable.
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
MAP_CHECK = Path(__file__).resolve().with_name("check.py")
TIER = re.compile(r"^Tier:\s*(\S+)", re.M)
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


def unanswered(task_dir: Path, decisions_text: str) -> list[tuple[str, Path]]:
    """Open question files of one task as (tier, path)."""
    questions = task_dir / "scratch" / "questions"
    if not questions.is_dir():
        return []
    open_items = []
    for path in sorted(questions.glob("*.md")):
        if path.name.endswith(".ruling.md"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        answered = (
            path.with_name(path.stem + ".ruling.md").exists()
            or "## Ruling" in text
            or path.name in decisions_text
        )
        if not answered:
            tier = TIER.search(text)
            open_items.append((tier.group(1) if tier else "untiered", path))
    return open_items


def claims(map_dir: Path) -> dict[str, str]:
    """Map a claimed question path to the designer whose claim file names it."""
    held: dict[str, str] = {}
    for path in sorted((map_dir / "scratch").glob("designer-*.md")):
        lines = path.read_text(encoding="utf-8", errors="replace").split()
        if lines and lines[0] != "free":
            held[lines[0]] = path.stem.removeprefix("designer-")
    return held


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
    only_questions = "--questions" in argv
    arguments = [argument for argument in argv[1:] if argument != "--questions"]
    if len(arguments) != 1:
        print(__doc__)
        return 2
    map_dir = Path(arguments[0]).resolve()
    map_text = (map_dir / "MAP.md").read_text(encoding="utf-8")
    plans = map_dir.parents[1] / "plans"
    decisions_text = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in (map_dir / "decisions").glob("*.md")
    )
    running = [m for m in map(TASK_LINE.match, map_text.splitlines()) if m and m["state"] == "running"]
    design_questions = [
        (tier, path)
        for match in running
        for tier, path in unanswered(plans / match["task"], decisions_text)
        if tier not in ("process", "local")
    ]
    if only_questions:
        held = claims(map_dir)
        for tier, path in design_questions:
            holder = held.get(str(path))
            print(f"{tier} {path}" + (f"  claimed by {holder}" if holder else ""))
        if not design_questions:
            print("no open design questions")
        return 0
    agents = herdr_agents(herdr)
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
        for tier, question in unanswered(task_dir, decisions_text):
            print(f"   QUESTION {tier} {question}")
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
    for line in run([sys.executable, str(MAP_CHECK), str(map_dir)]).splitlines():
        if line.startswith("tidy suggested:"):
            print(line)
    print(f"design questions open: {len(design_questions)}")
    print(f"MemAvailable {mem_available_gb()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
