#!/usr/bin/env python3
"""Check an advisor map directory's closed structure and list rulings awaiting the user's review."""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOP_LEVEL = {"MAP.md", "design.md", "design", "decisions", "retired", "scratch"}
MAP_SECTIONS = (
    "Destination",
    "Staircase",
    "Tasks",
    "Not yet specified",
    "Out of scope",
    "Standing orders",
)
DECISION_NAME = re.compile(r"^\d{4}-[a-z0-9-]+\.md$")
TASK_LINE = re.compile(
    r"^- (\S+) — step \d+ — Base: \S+ — herdr: \S+ — (planned|running|landed)$"
)


def header(text: str) -> dict[str, str]:
    """Return the `Key: value` lines before the first blank line."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            break
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check.py <map-dir>", file=sys.stderr)
        return 2
    effort = Path(sys.argv[1])
    problems: list[str] = []
    extra = sorted(entry.name for entry in effort.iterdir() if entry.name not in TOP_LEVEL)
    if extra:
        problems.append(f"files outside the map layout: {extra}")

    map_file = effort / "MAP.md"
    tasks: list[tuple[str, str]] = []
    if not map_file.is_file():
        problems.append("MAP.md is missing")
    else:
        text = map_file.read_text()
        sections = re.findall(r"^## (.+?)\s*$", text, re.M)
        if sections != list(MAP_SECTIONS):
            problems.append(f"MAP.md sections must be exactly {MAP_SECTIONS} in order: {sections}")
        block = re.search(r"^## Tasks\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        lines = [line for line in (block.group(1) if block else "").splitlines() if line.strip()]
        if not lines or not lines[0].startswith("Advisor: "):
            problems.append("## Tasks does not start with 'Advisor: <herdr-name>'")
        for line in lines[1:]:
            match = TASK_LINE.match(line)
            if match:
                tasks.append((match.group(1), match.group(2)))
            else:
                problems.append(f"## Tasks line does not match the task format: {line!r}")

    pending: list[str] = []
    for path in sorted((effort / "decisions").glob("*")):
        if not DECISION_NAME.match(path.name):
            problems.append(f"decisions/{path.name}: name is not NNNN-<slug>.md")
            continue
        fields = header(path.read_text())
        if "Supersedes" not in fields:
            problems.append(f"decisions/{path.name}: header has no 'Supersedes:'")
        if "Ruled-by" in fields:
            review = fields.get("Review")
            if review not in ("pending", "accepted"):
                problems.append(f"decisions/{path.name}: proxy ruling needs 'Review: pending|accepted'")
            if review == "pending":
                pending.append(path.name)

    for task, state in tasks:
        print(f"task: {task} {state}")
    print(f"pending review: {pending or 'none'}")
    for problem in problems:
        print(f"problem: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
