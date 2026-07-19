#!/usr/bin/env python3
"""Manage explicit repo-local planning artifacts for one task."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
UNFINISHED_PHASE_PATTERN = re.compile(r"\|[^|]+\|\s*(pending|in_progress|blocked)\s*\|")
OPTIONAL_TEMPLATES = {
    "findings.md": "findings.md",
    "progress.md": "progress.md",
}
LIVE_FILE_LIMIT_BYTES = 16_384
HISTORY_FILE_LIMIT_BYTES = 16_384
MAX_DETAILED_PHASES = 10
PHASE_COMPACTION_BATCH = 5
PROGRESS_MAX_ROWS = 40
PROGRESS_KEEP_ROWS = 20
PHASE_HEADING_PATTERN = re.compile(r"^### (Phase [0-9]+) — (.+)$")
HISTORY_FILE_PATTERN = re.compile(
    r"^(?P<number>[0-9]{4})-(?P<kind>task-plan|progress|findings)\.md$"
)
EMPTY_CLOSURE_VALUES = {"", "none", "n/a", "na", "pending", "unknown", "-"}


class PlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarkdownRow:
    index: int
    line: str
    cells: tuple[str, ...]


@dataclass(frozen=True)
class MarkdownTable:
    data_start: int
    data_end: int
    rows: tuple[MarkdownRow, ...]


@dataclass(frozen=True)
class PhaseBlock:
    phase: str
    topic: str
    conclusion: str
    start: int
    end: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class HistorySegment:
    kind: str
    source: str
    body: str


@dataclass
class PreparedCompaction:
    replacements: dict[Path, str] = field(default_factory=dict)
    history: list[HistorySegment] = field(default_factory=list)
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "task_plan_phases": 0,
            "progress_timeline_rows": 0,
            "progress_verification_rows": 0,
            "findings_rows": 0,
        }
    )


def validate_task_id(task_id: str) -> None:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise PlanError(f"task-id must match {TASK_ID_PATTERN.pattern}: {task_id!r}")


def plan_dir(root: Path, task_id: str) -> Path:
    return root / ".agent_state" / "plans" / task_id


def archive_dir(root: Path, task_id: str) -> Path:
    return root / ".agent_state" / "archives" / task_id / "plan"


def reject_symlink_components(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise PlanError(f"planning path escapes repo root: {path}") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise PlanError(f"planning path contains symlink component: {current}")


def reject_symlink_tree(root: Path, directory: Path) -> None:
    reject_symlink_components(root, directory)
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise PlanError(f"planning tree contains symlink: {path}")


def require_plan(root: Path, task_id: str) -> Path:
    path = plan_dir(root, task_id)
    reject_symlink_tree(root, path)
    if not (path / "task_plan.md").is_file():
        raise PlanError(f"plan not found: {path}")
    return path


def template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def render_template(name: str, task_id: str, *, goal: str | None = None) -> str:
    path = template_dir() / name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanError(f"cannot read template {path}: {exc}") from exc
    text = text.replace("<task-id>", task_id).replace(
        "YYYY-MM-DD", date.today().isoformat()
    )
    if goal is not None:
        text = text.replace("<用一段話描述本 task 要達成的具體結果。>", goal)
    return text


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_create(path: Path, text: str) -> None:
    """Create an immutable file without ever replacing an existing path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise PlanError(f"immutable history already exists: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def utf8_size(text: str) -> int:
    return len(text.encode("utf-8"))


def update_last_updated(text: str) -> str:
    replacement = f"**Last updated:** {date.today().isoformat()}"
    updated, count = re.subn(
        r"^\*\*Last updated:\*\* .+$",
        replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise PlanError("planning file must contain exactly one Last updated field")
    return updated


def section_bounds(lines: list[str], heading: str) -> tuple[int, int]:
    matches = [index for index, line in enumerate(lines) if line.strip() == heading]
    if len(matches) != 1:
        raise PlanError(f"planning file must contain exactly one {heading} section")
    start = matches[0] + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return start, end


def table_cells(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        raise PlanError(f"invalid Markdown table row: {line!r}")
    cells: list[str] = []
    current: list[str] = []
    content = stripped[1:-1]
    index = 0
    while index < len(content):
        character = content[index]
        if character == "\\" and index + 1 < len(content) and content[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1
    cells.append("".join(current).strip())
    return tuple(cells)


def markdown_table(
    lines: list[str], heading: str, expected_header: tuple[str, ...]
) -> MarkdownTable:
    start, end = section_bounds(lines, heading)
    table_start = next(
        (index for index in range(start, end) if lines[index].strip().startswith("|")),
        None,
    )
    if table_start is None or table_start + 1 >= end:
        raise PlanError(f"{heading} must contain a Markdown table")
    if table_cells(lines[table_start]) != expected_header:
        raise PlanError(f"{heading} table header does not match the current template")
    separator = table_cells(lines[table_start + 1])
    if len(separator) != len(expected_header) or any(
        not re.fullmatch(r":?-{3,}:?", cell) for cell in separator
    ):
        raise PlanError(f"{heading} table separator is invalid")
    rows: list[MarkdownRow] = []
    index = table_start + 2
    while index < end and lines[index].strip().startswith("|"):
        cells = table_cells(lines[index])
        if len(cells) != len(expected_header):
            raise PlanError(f"{heading} row has the wrong number of columns")
        rows.append(MarkdownRow(index=index, line=lines[index], cells=cells))
        index += 1
    return MarkdownTable(
        data_start=table_start + 2,
        data_end=index,
        rows=tuple(rows),
    )


def phase_blocks(lines: list[str]) -> tuple[PhaseBlock, ...]:
    start, end = section_bounds(lines, "## Active Notes")
    headings: list[tuple[int, re.Match[str]]] = []
    for index in range(start, end):
        if lines[index].startswith("### "):
            match = PHASE_HEADING_PATTERN.fullmatch(lines[index])
            if match is None:
                raise PlanError(
                    "Active Notes phase headings must use '### Phase N — Topic'"
                )
            headings.append((index, match))
    content_before_first = lines[start : headings[0][0] if headings else end]
    if any(line.strip() for line in content_before_first):
        raise PlanError(
            "Active Notes contains unstructured content outside a Phase block"
        )
    blocks: list[PhaseBlock] = []
    for position, (block_start, match) in enumerate(headings):
        block_end = headings[position + 1][0] if position + 1 < len(headings) else end
        conclusion_lines = [
            line.removeprefix("- Conclusion / Commit:").strip()
            for line in lines[block_start + 1 : block_end]
            if line.startswith("- Conclusion / Commit:")
        ]
        if len(conclusion_lines) != 1 or not conclusion_lines[0]:
            raise PlanError(
                f"{match.group(1)} must contain one non-empty Conclusion / Commit field"
            )
        blocks.append(
            PhaseBlock(
                phase=match.group(1),
                topic=match.group(2).strip(),
                conclusion=conclusion_lines[0],
                start=block_start,
                end=block_end,
                lines=tuple(lines[block_start:block_end]),
            )
        )
    phase_ids = [block.phase for block in blocks]
    if len(set(phase_ids)) != len(phase_ids):
        raise PlanError("Active Notes contains duplicate Phase headings")
    return tuple(blocks)


def replace_lines(
    lines: list[str], *, remove: set[int], insert_before: dict[int, list[str]]
) -> str:
    output: list[str] = []
    for index, line in enumerate(lines):
        output.extend(insert_before.get(index, ()))
        if index not in remove:
            output.append(line)
    output.extend(insert_before.get(len(lines), ()))
    return "\n".join(output).rstrip() + "\n"


def history_segments(
    *,
    kind: str,
    source: str,
    section_header: str,
    units: list[str],
    separator: str = "\n\n",
) -> list[HistorySegment]:
    if not units:
        return []
    segments: list[HistorySegment] = []
    current: list[str] = []
    for unit in units:
        candidate = separator.join([section_header, *current, unit]).rstrip() + "\n"
        rendered = render_history(kind=kind, source=source, body=candidate)
        if utf8_size(rendered) <= HISTORY_FILE_LIMIT_BYTES:
            current.append(unit)
            continue
        if not current:
            raise PlanError(
                f"one {kind} history unit exceeds {HISTORY_FILE_LIMIT_BYTES} bytes"
            )
        body = separator.join([section_header, *current]).rstrip() + "\n"
        segments.append(HistorySegment(kind=kind, source=source, body=body))
        current = [unit]
        rendered = render_history(
            kind=kind,
            source=source,
            body=separator.join([section_header, unit]).rstrip() + "\n",
        )
        if utf8_size(rendered) > HISTORY_FILE_LIMIT_BYTES:
            raise PlanError(
                f"one {kind} history unit exceeds {HISTORY_FILE_LIMIT_BYTES} bytes"
            )
    body = separator.join([section_header, *current]).rstrip() + "\n"
    segments.append(HistorySegment(kind=kind, source=source, body=body))
    return segments


def render_history(*, kind: str, source: str, body: str) -> str:
    title = kind.replace("-", " ").title()
    return (
        "---\n"
        "planning_compat: 6\n"
        f"history_kind: {kind}\n"
        f"source: {source}\n"
        "---\n\n"
        f"# Archived {title}\n\n"
        f"{body}"
    )


def git_summary(root: Path) -> dict[str, str]:
    summary: dict[str, str] = {}
    for key, args in {
        "diff_stat": ("diff", "--stat"),
        "status_short": ("status", "--short"),
    }.items():
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            text=True,
            capture_output=True,
        )
        summary[key] = completed.stdout.strip() or completed.stderr.strip()
    return summary


def phase_status_section(text: str) -> str:
    lines = text.splitlines()
    try:
        start = next(
            index
            for index, line in enumerate(lines)
            if line.strip() == "## Phase Status"
        )
    except StopIteration:
        return ""
    section: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        section.append(line)
    return "\n".join(section)


def unfinished_phases(text: str) -> list[str]:
    section = phase_status_section(text)
    return [match.group(1) for match in UNFINISHED_PHASE_PATTERN.finditer(section)]


def markdown_cell(value: str) -> str:
    return " ".join(value.replace("|", r"\|").split())


def validate_last_updated(text: str, *, filename: str) -> None:
    matches = re.findall(r"^\*\*Last updated:\*\* .+$", text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise PlanError(f"{filename} must contain exactly one Last updated field")


def validate_task_plan(text: str) -> None:
    validate_last_updated(text, filename="task_plan.md")
    lines = text.splitlines()
    phase_table = markdown_table(
        lines,
        "## Phase Status",
        ("Phase", "Status", "Scope", "Acceptance"),
    )
    valid_statuses = {"pending", "in_progress", "blocked", "completed"}
    for row in phase_table.rows:
        if row.cells[1] not in valid_statuses:
            raise PlanError(f"phase {row.cells[0]} has invalid status {row.cells[1]!r}")
    markdown_table(
        lines,
        "## Historical Phase Summary",
        ("Phase", "Topic", "Conclusion / Commit"),
    )
    phase_blocks(lines)


def validate_progress(text: str) -> None:
    validate_last_updated(text, filename="progress.md")
    lines = text.splitlines()
    markdown_table(lines, "## Timeline", progress_table_header("## Timeline"))
    markdown_table(
        lines,
        "## Verification Log",
        progress_table_header("## Verification Log"),
    )


def findings_table(text: str) -> tuple[list[str], MarkdownTable]:
    validate_last_updated(text, filename="findings.md")
    lines = text.splitlines()
    header = ("ID", "Status", "Date", "Area", "Finding", "Evidence / Closure")
    table = markdown_table(lines, "## Discoveries", header)
    for row in table.rows:
        if row.cells[1] not in {"open", "resolved"}:
            raise PlanError(
                f"finding {row.cells[0]} has invalid status {row.cells[1]!r}"
            )
        if (
            row.cells[1] == "resolved"
            and row.cells[5].strip().lower() in EMPTY_CLOSURE_VALUES
        ):
            raise PlanError(f"resolved finding lacks closure evidence: {row.cells[0]}")
    return lines, table


def compact_task_plan(text: str) -> tuple[str, list[HistorySegment], int]:
    validate_task_plan(text)
    working = text
    archived_units: list[str] = []
    archived_count = 0
    while True:
        lines = working.splitlines()
        blocks = phase_blocks(lines)
        needs_compaction = (
            len(blocks) > MAX_DETAILED_PHASES
            or utf8_size(working) > LIVE_FILE_LIMIT_BYTES
        )
        if not needs_compaction:
            break
        phase_table = markdown_table(
            lines,
            "## Phase Status",
            ("Phase", "Status", "Scope", "Acceptance"),
        )
        phase_rows = {row.cells[0]: row for row in phase_table.rows}
        if len(phase_rows) != len(phase_table.rows):
            raise PlanError("Phase Status contains duplicate Phase rows")
        # Sealed prefix: only the contiguous run of completed phases at the top
        # may move to history, capped per batch.
        candidates = []
        for block in blocks:
            row = phase_rows.get(block.phase)
            if row is None or row.cells[1] != "completed":
                break
            candidates.append(block)
            if len(candidates) == PHASE_COMPACTION_BATCH:
                break
        if not candidates:
            raise PlanError(
                "task_plan exceeds the live-file budget without an archivable"
                " completed phase prefix"
            )

        summary_table = markdown_table(
            lines,
            "## Historical Phase Summary",
            ("Phase", "Topic", "Conclusion / Commit"),
        )
        summarized = {row.cells[0] for row in summary_table.rows}
        if len(summarized) != len(summary_table.rows):
            raise PlanError("Historical Phase Summary contains duplicate Phase rows")
        if any(block.phase in summarized for block in candidates):
            raise PlanError("phase already exists in Historical Phase Summary")

        remove: set[int] = set()
        summary_rows: list[str] = []
        for block in candidates:
            remove.add(phase_rows[block.phase].index)
            remove.update(range(block.start, block.end))
            summary_rows.append(
                "| "
                + " | ".join(
                    (
                        markdown_cell(block.phase),
                        markdown_cell(block.topic),
                        markdown_cell(block.conclusion),
                    )
                )
                + " |"
            )
            archived_units.append(
                "\n".join(
                    (
                        "```text",
                        phase_rows[block.phase].line,
                        "```",
                        "",
                        *block.lines,
                    )
                ).rstrip()
            )
        working = replace_lines(
            lines,
            remove=remove,
            insert_before={summary_table.data_end: summary_rows},
        )
        working = update_last_updated(working)
        archived_count += len(candidates)

    segments = history_segments(
        kind="task-plan",
        source="task_plan.md",
        section_header="## Archived Phase Notes",
        units=archived_units,
    )
    return working, segments, archived_count


def progress_table_header(heading: str) -> tuple[str, ...]:
    if heading == "## Timeline":
        return ("Time", "Actor", "Action", "Result", "Next")
    if heading == "## Verification Log":
        return ("Date", "Command", "Result")
    raise AssertionError(f"unknown progress heading: {heading}")


def progress_history_header(heading: str, header: tuple[str, ...]) -> str:
    return f"{heading}\n\n| {' | '.join(header)} |\n|{'|'.join('---' for _ in header)}|"


def compact_progress(text: str) -> tuple[str, list[HistorySegment], dict[str, int]]:
    validate_progress(text)
    lines = text.splitlines()
    timeline_header = progress_table_header("## Timeline")
    verification_header = progress_table_header("## Verification Log")
    timeline = markdown_table(lines, "## Timeline", timeline_header)
    verification = markdown_table(lines, "## Verification Log", verification_header)
    over_budget = utf8_size(text) > LIVE_FILE_LIMIT_BYTES
    if (
        not over_budget
        and len(timeline.rows) <= PROGRESS_MAX_ROWS
        and len(verification.rows) <= PROGRESS_MAX_ROWS
    ):
        return (
            text,
            [],
            {
                "progress_timeline_rows": 0,
                "progress_verification_rows": 0,
            },
        )

    remove_timeline = max(0, len(timeline.rows) - PROGRESS_KEEP_ROWS)
    remove_verification = max(0, len(verification.rows) - PROGRESS_KEEP_ROWS)
    if remove_timeline == 0 and remove_verification == 0:
        raise PlanError(
            "progress exceeds the live-file budget within its most recent twenty rows"
        )

    archived_timeline = list(timeline.rows[:remove_timeline])
    archived_verification = list(verification.rows[:remove_verification])
    remove = {row.index for row in [*archived_timeline, *archived_verification]}
    compacted = replace_lines(lines, remove=remove, insert_before={})
    compacted = update_last_updated(compacted)
    if utf8_size(compacted) > LIVE_FILE_LIMIT_BYTES:
        raise PlanError(
            "progress exceeds the live-file budget after retaining its latest twenty rows"
        )

    segments = history_segments(
        kind="progress",
        source="progress.md",
        section_header=progress_history_header("## Timeline", timeline_header),
        units=[row.line for row in archived_timeline],
        separator="\n",
    )
    segments.extend(
        history_segments(
            kind="progress",
            source="progress.md",
            section_header=progress_history_header(
                "## Verification Log", verification_header
            ),
            units=[row.line for row in archived_verification],
            separator="\n",
        )
    )
    return (
        compacted,
        segments,
        {
            "progress_timeline_rows": remove_timeline,
            "progress_verification_rows": remove_verification,
        },
    )


def compact_findings(text: str) -> tuple[str, list[HistorySegment], int]:
    lines, table = findings_table(text)
    if utf8_size(text) <= LIVE_FILE_LIMIT_BYTES:
        return text, [], 0
    header = ("ID", "Status", "Date", "Area", "Finding", "Evidence / Closure")

    resolved = [row for row in table.rows if row.cells[1] == "resolved"]
    remove: set[int] = set()
    archived: list[MarkdownRow] = []
    compacted = text
    for row in resolved:
        remove.add(row.index)
        archived.append(row)
        compacted = replace_lines(lines, remove=remove, insert_before={})
        compacted = update_last_updated(compacted)
        if utf8_size(compacted) <= LIVE_FILE_LIMIT_BYTES:
            break
    if utf8_size(compacted) > LIVE_FILE_LIMIT_BYTES:
        raise PlanError(
            "findings exceeds the live-file budget after every safely resolved row is removed"
        )

    section_header = (
        "## Resolved Discoveries\n\n"
        f"| {' | '.join(header)} |\n"
        f"|{'|'.join('---' for _ in header)}|"
    )
    segments = history_segments(
        kind="findings",
        source="findings.md",
        section_header=section_header,
        units=[row.line for row in archived],
        separator="\n",
    )
    return compacted, segments, len(archived)


def next_history_number(directory: Path) -> int:
    history = directory / "history"
    numbers = [
        int(match.group("number"))
        for path in history.glob("*.md")
        if (match := HISTORY_FILE_PATTERN.fullmatch(path.name)) is not None
    ]
    return max(numbers, default=0) + 1


def write_prepared_compaction(
    directory: Path, prepared: PreparedCompaction
) -> list[str]:
    history_files: list[str] = []
    number = next_history_number(directory)
    for segment in prepared.history:
        filename = f"{number:04d}-{segment.kind}.md"
        destination = directory / "history" / filename
        reject_symlink_components(directory, destination)
        if destination.exists():
            raise PlanError(f"history destination already exists: {destination}")
        rendered = render_history(
            kind=segment.kind,
            source=segment.source,
            body=segment.body,
        )
        if utf8_size(rendered) > HISTORY_FILE_LIMIT_BYTES:
            raise PlanError(f"history segment exceeds byte budget: {filename}")
        atomic_create(destination, rendered)
        history_files.append(f"history/{filename}")
        number += 1
    for path, text in prepared.replacements.items():
        atomic_write(path, text)
    return history_files


def prepare_compaction(directory: Path) -> PreparedCompaction:
    prepared = PreparedCompaction()

    task_plan = directory / "task_plan.md"
    task_text = task_plan.read_text(encoding="utf-8")
    compacted_task, task_history, phase_count = compact_task_plan(task_text)
    if compacted_task != task_text:
        prepared.replacements[task_plan] = compacted_task
    prepared.history.extend(task_history)
    prepared.counts["task_plan_phases"] = phase_count

    progress = directory / "progress.md"
    if progress.is_file():
        progress_text = progress.read_text(encoding="utf-8")
        compacted_progress, progress_history, progress_counts = compact_progress(
            progress_text
        )
        if compacted_progress != progress_text:
            prepared.replacements[progress] = compacted_progress
        prepared.history.extend(progress_history)
        prepared.counts.update(progress_counts)

    findings = directory / "findings.md"
    if findings.is_file():
        findings_text = findings.read_text(encoding="utf-8")
        compacted_findings, findings_history, findings_count = compact_findings(
            findings_text
        )
        if compacted_findings != findings_text:
            prepared.replacements[findings] = compacted_findings
        prepared.history.extend(findings_history)
        prepared.counts["findings_rows"] = findings_count
    return prepared


def run_compaction(args: argparse.Namespace, *, operation: str) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    directory = require_plan(root, args.task_id)
    prepared = prepare_compaction(directory)
    history_files = write_prepared_compaction(directory, prepared)
    return {
        "ok": True,
        "operation": operation,
        "task_id": args.task_id,
        "plan_dir": str(directory),
        "changed": bool(prepared.replacements),
        "compacted": prepared.counts,
        "history_files": history_files,
    }


def command_compact(args: argparse.Namespace) -> dict[str, Any]:
    return run_compaction(args, operation="compact")


def command_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    """Validate current narrative and compact only when thresholds require it."""
    return run_compaction(args, operation="checkpoint")


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    if not args.goal.strip():
        raise PlanError("goal must not be empty")
    destination = plan_dir(root, args.task_id)
    archived = archive_dir(root, args.task_id)
    reject_symlink_components(root, destination)
    reject_symlink_components(root, archived)
    if destination.exists() or archived.exists():
        raise PlanError(f"task planning namespace already exists: {args.task_id}")

    plans_root = destination.parent
    plans_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{args.task_id}.staging-", dir=plans_root))
    try:
        atomic_write(
            staging / "task_plan.md",
            render_template("task_plan.md", args.task_id, goal=args.goal),
        )
        requested_optional = []
        if args.with_findings:
            requested_optional.append("findings.md")
        if args.with_progress:
            requested_optional.append("progress.md")
        for filename in requested_optional:
            atomic_write(
                staging / filename,
                render_template(OPTIONAL_TEMPLATES[filename], args.task_id),
            )
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "ok": True,
        "task_id": args.task_id,
        "plan_dir": str(destination),
        "files": sorted(path.name for path in destination.iterdir()),
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    directory = require_plan(root, args.task_id)
    task_text = (directory / "task_plan.md").read_text(encoding="utf-8")
    optional: dict[str, str] = {}
    for filename in OPTIONAL_TEMPLATES:
        path = directory / filename
        if path.is_file():
            optional[filename] = "\n".join(
                path.read_text(encoding="utf-8").splitlines()[-20:]
            )
    return {
        "ok": True,
        "task_id": args.task_id,
        "plan_dir": str(directory),
        "files": sorted(path.name for path in directory.iterdir() if path.is_file()),
        "unfinished_phases": unfinished_phases(task_text),
        "task_plan_head": "\n".join(task_text.splitlines()[:60]),
        "optional_tails": optional,
        "git": git_summary(root),
    }


def command_check(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    directory = require_plan(root, args.task_id)
    task_text = (directory / "task_plan.md").read_text(encoding="utf-8")
    unfinished = unfinished_phases(task_text)
    if unfinished:
        raise PlanError(
            "plan has unfinished phases: " + ", ".join(sorted(set(unfinished)))
        )
    return {
        "ok": True,
        "task_id": args.task_id,
        "plan_dir": str(directory),
        "complete": True,
    }


def command_archive(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    source = require_plan(root, args.task_id)
    task_text = (source / "task_plan.md").read_text(encoding="utf-8")
    unfinished = unfinished_phases(task_text)
    if unfinished:
        raise PlanError(
            "cannot archive plan with unfinished phases: "
            + ", ".join(sorted(set(unfinished)))
        )
    destination = archive_dir(root, args.task_id)
    reject_symlink_components(root, destination)
    if destination.exists():
        raise PlanError(f"archive destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    return {
        "ok": True,
        "task_id": args.task_id,
        "archive_dir": str(destination),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("task_id")
    init.add_argument("--goal", required=True)
    init.add_argument("--with-findings", action="store_true")
    init.add_argument("--with-progress", action="store_true")
    init.set_defaults(handler=command_init)

    for name, handler in (
        ("status", command_status),
        ("checkpoint", command_checkpoint),
        ("compact", command_compact),
        ("check", command_check),
        ("archive", command_archive),
    ):
        command = commands.add_parser(name)
        command.add_argument("task_id")
        command.set_defaults(handler=handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.handler(args)
    except PlanError as exc:
        parser.exit(2, f"planning error: {exc}\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
