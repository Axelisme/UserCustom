#!/usr/bin/env python3
"""Read anchored sections of Markdown files, and check that anchors resolve."""

from __future__ import annotations

import argparse
import functools
import os
import re
import sys
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
MD_LINK = re.compile(r"\]\((?!\w+:)([^)\s#]+\.(?:md|toml))(#[^)\s]*)?\)")
BARE_LINK = re.compile(r"`([^`\s]+\.(?:md|toml))(#[^`\s]+)?`")
SEARCH_ROOTS = ("~/.codex/skills", "~/.codex/agents", "~/.claude/agents",
                "~/.pi/agent/herdr-subagents/profiles")


def slug(text: str) -> str:
    return re.sub(r"[^\w\s-]", "", text.lower()).strip().replace(" ", "-")


@functools.cache
def headings(path: Path) -> list[tuple[int, int, str, str]]:
    """(line_number, level, title, slug) for every heading outside a fenced block."""
    out: list[tuple[int, int, str, str]] = []
    seen: dict[str, int] = {}
    fence = ""
    for n, line in enumerate(path.read_text().splitlines(), 1):
        f = FENCE.match(line)
        if f:
            fence = "" if fence == f.group(1) else (fence or f.group(1))
            continue
        if fence:
            continue
        m = HEADING.match(line)
        if not m:
            continue
        base = slug(m.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.append((n, len(m.group(1)), m.group(2), base if not count else f"{base}-{count}"))
    return out


def walk(root: Path, follow: bool = True) -> list[Path]:
    """Skill roots are trees of symlinks, which pathlib's `**` declines to enter."""
    return [
        Path(base, name).resolve()
        for base, _, names in os.walk(root, followlinks=follow)
        for name in names
    ]


class Unreadable(Exception):
    """One pointer that cannot be read; the rest of a batch still is."""


@functools.cache
def searchable() -> list[Path]:
    return [p for root in SEARCH_ROOTS for p in walk(Path(root).expanduser())]


def resolve(target: str) -> Path:
    """A pointer is written relative to the document that carries it; find it from anywhere."""
    direct = Path(target).expanduser()
    if direct.is_file():
        return direct
    suffix = Path(*[p for p in Path(target).parts if p not in ("..", ".")])
    hits = sorted({p for p in searchable()
                   if p.name == suffix.name and p.as_posix().endswith(suffix.as_posix())})
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise Unreadable(f"{target}: no such document under {', '.join(SEARCH_ROOTS)}")
    raise Unreadable(f"{target}: ambiguous, matches\n" + "\n".join(f"  {h}" for h in hits))


def read_section(path: Path, anchor: str) -> None:
    heads = headings(path)
    wanted = anchor.lstrip("#")
    match = next((h for h in heads if h[3] == wanted), None)
    if match is None:
        raise Unreadable(
            f"{path}: no heading for anchor '#{wanted}'. Available anchors:\n"
            + "\n".join(f"  #{h[3]}" for h in heads)
        )
    start, level = match[0], match[1]
    lines = path.read_text().splitlines()
    end = next((h[0] - 1 for h in heads if h[0] > start and h[1] <= level), len(lines))
    print(f"== {path}:{start}-{end} #{wanted}")
    print("\n".join(lines[start - 1 : end]).rstrip())


def is_bare_pointer(target: str, anchor: str | None) -> bool:
    """Backticks mean two things, and only one of them is checkable.

    A backticked path is a pointer when it carries an anchor or is rooted at `~/`, and prose naming
    a per-task artifact otherwise — `INDEX.md`, `validation.md`, `research/skill-feedback.md` name
    files a ticket creates at runtime, so demanding they exist would report correct prose as broken.
    """
    return bool(anchor) or target.startswith("~/")


def check(roots: list[Path]) -> None:
    # Only this repository's own documents: a symlinked directory is a vendored skill whose
    # pointers belong upstream. Say how many were skipped so the coverage is never silent.
    found: set[Path] = set()
    skipped = 0
    for r in roots:
        if r.is_file():
            found.add(r)
            continue
        for base, dirs, names in os.walk(r):
            skipped += sum(Path(base, d).is_symlink() for d in dirs)
            found.update(Path(base, name).resolve() for name in names)
    files = sorted(p for p in found if p.suffix in (".md", ".toml"))
    broken = 0
    for f in files:
        text = f.read_text()
        for pattern in (MD_LINK, BARE_LINK):
            for m in pattern.finditer(text):
                if pattern is BARE_LINK and not is_bare_pointer(m.group(1), m.group(2)):
                    continue
                if set("<{") & set(m.group(1)):  # a template's placeholder path
                    continue
                near = (f.parent / m.group(1)).resolve()
                target = near if near.is_file() else Path(m.group(1)).expanduser()
                if not target.is_file():
                    print(f"{f}: missing target {m.group(1)}")
                    broken += 1
                    continue
                if m.group(2) and m.group(2).lstrip("#") not in {h[3] for h in headings(target)}:
                    print(f"{f}: broken anchor {m.group(1)}{m.group(2)}")
                    broken += 1
    note = f"; skipped {skipped} symlinked director{'y' if skipped == 1 else 'ies'}" if skipped else ""
    print(f"checked {len(files)} files: {broken} broken pointer(s){note}")
    if broken:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target", nargs="+",
        help="pointers 'path.md#anchor', read in order; a bare path lists its anchors; roots with --check",
    )
    parser.add_argument("--check", action="store_true", help="verify every pointer under the given roots")
    parser.add_argument("--list", action="store_true", help="list each document's anchors")
    args = parser.parse_args()

    if args.check:
        check([Path(t).expanduser() for t in args.target])
        return

    failed = False
    for target in args.target:
        path, _, anchor = target.partition("#")
        try:
            document = resolve(path)
            if args.list or not anchor:
                print(f"== {document}")
                for n, level, _, s in headings(document):
                    print(f"{n:>5}  {'  ' * (level - 1)}#{s}")
            else:
                read_section(document, anchor)
        except Unreadable as error:
            print(error, file=sys.stderr)
            failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
