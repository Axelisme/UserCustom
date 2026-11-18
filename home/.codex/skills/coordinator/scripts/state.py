#!/usr/bin/env python3
"""List what sits outside the workflow's placement rules under a repository's .agent_state.

Usage: python3 state.py <repo> [--allow NAME ...]

It prints one line per finding and never deletes:

- `misplaced:` a loose file, or a directory other than the workflow's own (plans, maps, archives,
  worktrees) and the names given with --allow, at the top of .agent_state;
- `residue:` the topmost directory under worktrees/ that neither is a registered Git worktree nor
  contains one;
- `collected:` a ticket's scratch directory left behind after the ticket reached `done`.

The last line is `state: clean` or `state: <n> findings`. Exit status is 0 unless the arguments are
unusable.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

WORKFLOW_DIRECTORIES = {"plans", "maps", "archives", "worktrees"}


def git_worktrees(repo: Path) -> list[Path]:
    """Paths of the worktrees Git has registered for repo."""
    listing = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return [
        Path(line.removeprefix("worktree "))
        for line in listing.splitlines()
        if line.startswith("worktree ")
    ]


def residue(directory: Path, registered: set[Path]) -> list[Path]:
    """Topmost directories under directory that hold no registered worktree."""
    found: list[Path] = []
    for child in sorted(p for p in directory.iterdir() if p.is_dir() and not p.is_symlink()):
        if child in registered:
            continue
        if any(child in worktree.parents for worktree in registered):
            found.extend(residue(child, registered))
        else:
            found.append(child)
    return found


def collected_scratch(plans: Path) -> list[Path]:
    """Scratch directories of tickets whose Status is done."""
    found: list[Path] = []
    for ticket in sorted(plans.glob("*/tickets/*.md")):
        if "**Status:** done" not in ticket.read_text(encoding="utf-8", errors="replace"):
            continue
        scratch = ticket.parents[1] / "scratch" / ticket.stem
        if scratch.is_dir():
            found.append(scratch)
    return found


def main(argv: list[str], worktrees: Callable[[Path], list[Path]] = git_worktrees) -> int:
    arguments = argv[1:]
    allowed = set(WORKFLOW_DIRECTORIES)
    while "--allow" in arguments:
        at = arguments.index("--allow")
        if at + 1 >= len(arguments):
            print(__doc__)
            return 2
        allowed.add(arguments[at + 1])
        del arguments[at : at + 2]
    if len(arguments) != 1:
        print(__doc__)
        return 2
    repo = Path(arguments[0]).resolve()
    state = repo / ".agent_state"
    findings: list[str] = []
    if state.is_dir():
        for entry in sorted(state.iterdir()):
            if not entry.is_dir() or entry.name not in allowed:
                findings.append(f"misplaced: {entry}")
        if (state / "worktrees").is_dir():
            registered = {path.resolve() for path in worktrees(repo)}
            findings.extend(f"residue: {path}" for path in residue(state / "worktrees", registered))
        if (state / "plans").is_dir():
            findings.extend(f"collected: {path}" for path in collected_scratch(state / "plans"))
    for line in findings:
        print(line)
    print(f"state: {len(findings)} findings" if findings else "state: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
