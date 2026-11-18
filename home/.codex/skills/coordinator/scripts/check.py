#!/usr/bin/env python3
"""Check an effort map directory's closed structure and list rulings awaiting the user's review.

Two kinds of advice follow the findings and leave the exit status alone: `tidy suggested:` for a
map entry that has outgrown its line (a sub-heading, or an entry line past ENTRY_WARN_CHARS in a
one-line-per-entry section), and `hand-off suggested:` for a map past HANDOFF_TASKS task lines or
HANDOFF_DECISIONS decisions.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOP_LEVEL = {"MAP.md", "design.md", "design", "decisions", "retired", "scratch"}
MAP_SECTIONS = (
    "Destination",
    "Staircase",
    "Tasks",
    "Follow-ups",
    "Not yet specified",
    "Out of scope",
    "Standing orders",
)
# Sections whose entries are one line each; Standing orders quote the user at any length.
ONE_LINE_SECTIONS = {"Follow-ups", "Not yet specified", "Out of scope"}
ENTRY_WARN_CHARS = 300
ROLE_LINES = ("Coordinator: ", "Designer: ")
DECISION_NAME = re.compile(r"^\d{4}-[^/]+\.md$")
HANDOFF_TASKS = 9
HANDOFF_DECISIONS = 25
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


def tidy_suggestions(text: str) -> list[str]:
    """Advice for MAP.md lines that turn a one-line entry into a log."""
    advice: list[str] = []
    section = ""
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("###"):
            advice.append(f"MAP.md line {number} is a sub-heading")
        elif section in ONE_LINE_SECTIONS and len(line) > ENTRY_WARN_CHARS:
            advice.append(
                f"MAP.md line {number} in {section} is {len(line)} characters"
                f" (over {ENTRY_WARN_CHARS})"
            )
    return advice


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check.py <map-dir>", file=sys.stderr)
        return 2
    effort = Path(argv[1])
    problems: list[str] = []
    advice: list[str] = []
    extra = sorted(entry.name for entry in effort.iterdir() if entry.name not in TOP_LEVEL)
    if extra:
        problems.append(f"files outside the map layout: {extra}")

    map_file = effort / "MAP.md"
    tasks: list[tuple[str, str]] = []
    if not map_file.is_file():
        problems.append("MAP.md is missing")
    else:
        text = map_file.read_text(encoding="utf-8")
        sections = re.findall(r"^## (.+?)\s*$", text, re.M)
        if sections != list(MAP_SECTIONS):
            problems.append(f"MAP.md sections must be exactly {MAP_SECTIONS} in order: {sections}")
        block = re.search(r"^## Tasks\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        lines = [line for line in (block.group(1) if block else "").splitlines() if line.strip()]
        roles = lines[: len(ROLE_LINES)]
        if len(roles) != len(ROLE_LINES) or not all(
            line.startswith(prefix) for line, prefix in zip(roles, ROLE_LINES)
        ):
            problems.append(
                "## Tasks does not start with 'Coordinator: <herdr-name>'"
                " then 'Designer: <herdr-name>'"
            )
        for line in lines:
            if line.startswith(ROLE_LINES):
                continue
            match = TASK_LINE.match(line)
            if match:
                tasks.append((match.group(1), match.group(2)))
            else:
                problems.append(f"## Tasks line does not match the task format: {line!r}")
        advice = tidy_suggestions(text)

    pending: list[str] = []
    decisions = 0
    for path in sorted((effort / "decisions").glob("*")):
        if not DECISION_NAME.match(path.name):
            problems.append(f"decisions/{path.name}: name is not NNNN-<slug>.md")
            continue
        decisions += 1
        fields = header(path.read_text(encoding="utf-8"))
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
    for line in advice:
        print(f"tidy suggested: {line}")
    oversized = []
    if len(tasks) > HANDOFF_TASKS:
        oversized.append(f"{len(tasks)} tasks (over {HANDOFF_TASKS})")
    if decisions > HANDOFF_DECISIONS:
        oversized.append(f"{decisions} decisions (over {HANDOFF_DECISIONS})")
    if oversized:
        print(f"hand-off suggested: {', '.join(oversized)}")
    for problem in problems:
        print(f"problem: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
