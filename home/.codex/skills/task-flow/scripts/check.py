#!/usr/bin/env python3
"""Check a task-flow task directory's closed structure and print its ticket frontier."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# .collab_op holds the Pi collab tools' telemetry; the tools own it.
TOP_LEVEL = {"INDEX.md", "spec.md", "spec", "decisions", "tickets", "retired", "scratch", ".collab_op"}
INDEX_SECTIONS = ("Goal", "Standing orders")
STATUSES = ("ready", "doing", "done")
TICKET_NAME = re.compile(r"^(\d{2,})-[^/]+\.md$")
DECISION_NAME = re.compile(r"^\d{4}-[^/]+\.md$")


def check_index(task: Path, problems: list[str]) -> None:
    index = task / "INDEX.md"
    if not index.is_file():
        problems.append("INDEX.md is missing")
        return
    sections = re.findall(r"^## (.+?)\s*$", index.read_text(), re.M)
    extra = [name for name in sections if name not in INDEX_SECTIONS]
    if extra:
        problems.append(f"INDEX.md has sections outside {INDEX_SECTIONS}: {extra}")
    if "Goal" not in sections:
        problems.append("INDEX.md has no ## Goal")


def check_decisions(task: Path, problems: list[str]) -> None:
    for path in sorted((task / "decisions").glob("*")):
        if not DECISION_NAME.match(path.name):
            problems.append(f"decisions/{path.name}: name is not NNNN-<slug>.md")
            continue
        first = next((line for line in path.read_text().splitlines() if line.strip()), "")
        if not first.startswith("Supersedes:"):
            problems.append(f"decisions/{path.name}: first line is not 'Supersedes: ...'")


def read_tickets(task: Path, problems: list[str]) -> dict[str, tuple[str, set[str]]]:
    tickets: dict[str, tuple[str, set[str]]] = {}
    for path in sorted((task / "tickets").glob("*")):
        match = TICKET_NAME.match(path.name)
        if not match:
            problems.append(f"tickets/{path.name}: name is not NN-<slug>.md")
            continue
        text = path.read_text()
        if re.search(r"^##+ ", text, re.M):
            problems.append(f"tickets/{path.name}: has sections beyond the to-tickets template")
        status = re.search(r"^\*\*Status:\*\*\s*(\S+)", text, re.M)
        blocked = re.search(r"^\*\*Blocked by:\*\*(.*)$", text, re.M)
        if not status or status.group(1) not in STATUSES:
            problems.append(f"tickets/{path.name}: **Status:** is not one of {STATUSES}")
            continue
        if not blocked:
            problems.append(f"tickets/{path.name}: no **Blocked by:** line")
            continue
        blockers = set(re.findall(r"\b(\d{2,})\b", blocked.group(1)))
        tickets[match.group(1)] = (status.group(1), blockers)
    for number, (_, blockers) in tickets.items():
        unknown = blockers - tickets.keys()
        if unknown:
            problems.append(f"ticket {number}: blocked by unknown tickets {sorted(unknown)}")
    return tickets


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check.py <task-dir>", file=sys.stderr)
        return 2
    task = Path(sys.argv[1])
    problems: list[str] = []
    extra = sorted(entry.name for entry in task.iterdir() if entry.name not in TOP_LEVEL)
    if extra:
        problems.append(f"files outside the task layout: {extra}")
    check_index(task, problems)
    check_decisions(task, problems)
    tickets = read_tickets(task, problems)

    def done(number: str) -> bool:
        return tickets.get(number, ("", set()))[0] == "done"

    frontier = [n for n, (s, b) in tickets.items() if s == "ready" and all(map(done, b))]
    doing = [n for n, (s, _) in tickets.items() if s == "doing"]
    finished = sum(1 for s, _ in tickets.values() if s == "done")
    print(f"frontier: {frontier or 'none'}")
    print(f"doing: {doing or 'none'}")
    print(f"done: {finished}/{len(tickets)}")
    for problem in problems:
        print(f"problem: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
