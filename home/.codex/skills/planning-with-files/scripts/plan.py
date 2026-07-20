#!/usr/bin/env python3
"""Task-scoped durable memory: a small INDEX entry over append/addressable stores.

The entry file (`INDEX.md`) is the only file read to reorient after a compaction or
handoff, and the only bounded one. Everything else — phase records, the progress log,
investigation findings — is a store: complete, append-structured, addressable, and read
on demand, never loaded whole. This mirrors git's own shape: INDEX is refs, the stores
are the object log.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PHASE_FILE_PATTERN = re.compile(r"^(?P<num>[0-9]{2,})-(?P<slug>[a-z0-9][a-z0-9-]*)\.md$")

INDEX_FILE = "INDEX.md"
PHASES_DIR = "phases"
PROGRESS_FILE = "progress.jsonl"
FINDINGS_FILE = "findings.md"

INDEX_LIMIT_BYTES = 16_384
PHASE_STATUSES = ("pending", "in_progress", "blocked", "completed")
OPEN_STATUSES = ("pending", "in_progress", "blocked")

INDEX_TITLE_PATTERN = re.compile(r"^# (\S.*)$", re.MULTILINE)
GOAL_PATTERN = re.compile(r"^\*\*Goal:\*\*", re.MULTILINE)
REQUIRED_HEADINGS = ("## Current State", "## Decisions", "## Phase board", "## Stores")
BOARD_HEADING = "## Phase board"
PHASE_FIELDS = ("Status", "Scope", "Decisions made", "Conclusion", "Commit", "Evidence")


class PlanError(RuntimeError):
    pass


# ---- paths and safety -------------------------------------------------------


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
    if not (path / INDEX_FILE).is_file():
        raise PlanError(f"plan not found (no {INDEX_FILE}): {path}")
    return path


# ---- io ---------------------------------------------------------------------


def template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


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


def create_new(path: Path, text: str) -> None:
    """Write a file that must not already exist."""
    if path.exists():
        raise PlanError(f"already exists: {path}")
    atomic_write(path, text)


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def utf8_size(text: str) -> int:
    return len(text.encode("utf-8"))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def today() -> str:
    return date.today().isoformat()


def now_ts() -> str:
    return datetime.now(UTC).isoformat()


# ---- INDEX parsing ----------------------------------------------------------


def read_index(plan: Path) -> str:
    return (plan / INDEX_FILE).read_text(encoding="utf-8")


def section_span(lines: list[str], heading: str) -> tuple[int, int]:
    """[start, end) line range of a `## Heading` section, end at the next `## ` or EOF."""
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), -1)
    if start < 0:
        raise PlanError(f"INDEX is missing the '{heading}' section")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return start, end


def row_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def read_board(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start, end = section_span(lines, BOARD_HEADING)
    rows: list[dict[str, str]] = []
    data = [line for line in lines[start:end] if line.lstrip().startswith("|")]
    for line in data[2:]:  # skip header + separator
        cells = row_cells(line)
        if len(cells) >= 3 and cells[0]:
            rows.append({"phase": cells[0], "status": cells[1], "record": cells[2]})
    return rows


def upsert_board_row(text: str, phase: str, status: str, record: str) -> str:
    lines = text.splitlines()
    start, end = section_span(lines, BOARD_HEADING)
    row = f"| {phase} | {status} | {record} |"
    # Replace an existing row for this phase in place.
    for index in range(start, end):
        line = lines[index]
        if line.lstrip().startswith("|"):
            cells = row_cells(line)
            if len(cells) >= 3 and cells[0] == phase and cells[1] not in ("Phase",):
                lines[index] = row
                return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    # Otherwise append after the last table line in the section.
    last_table = start
    for index in range(start, end):
        if lines[index].lstrip().startswith("|"):
            last_table = index
    lines.insert(last_table + 1, row)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# ---- phase files ------------------------------------------------------------


def phases_path(plan: Path) -> Path:
    return plan / PHASES_DIR


def existing_phase_files(plan: Path) -> list[tuple[int, str, Path]]:
    directory = phases_path(plan)
    found: list[tuple[int, str, Path]] = []
    if directory.is_dir():
        for path in directory.iterdir():
            match = PHASE_FILE_PATTERN.match(path.name)
            if match:
                found.append((int(match.group("num")), match.group("slug"), path))
    return sorted(found)


def find_phase_file(plan: Path, phase: str) -> Path:
    number = int(phase)
    for num, _, path in existing_phase_files(plan):
        if num == number:
            return path
    raise PlanError(f"phase {phase} not found under {phases_path(plan)}")


def next_phase_number(plan: Path) -> int:
    files = existing_phase_files(plan)
    return (files[-1][0] + 1) if files else 1


def render_phase(number: str, topic: str) -> str:
    text = (template_dir() / "phase.md").read_text(encoding="utf-8")
    return (
        text.replace("<NN>", number)
        .replace("<topic>", topic)
        .replace("- **Status:** pending", "- **Status:** in_progress")
    )


def set_phase_field(text: str, field: str, value: str) -> str:
    pattern = re.compile(rf"^(- \*\*{re.escape(field)}:\*\*).*$", re.MULTILINE)
    replacement = rf"\1 {value}"
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise PlanError(f"phase record has no '{field}' field")
    return updated


def read_phase_field(text: str, field: str) -> str:
    match = re.search(rf"^- \*\*{re.escape(field)}:\*\* *(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def field_is_unset(value: str) -> bool:
    """True for an empty, placeholder, or not-yet-filled field value."""
    lowered = value.strip().lower()
    return lowered in ("", "none", "pending") or lowered.startswith("<")


# ---- commands ---------------------------------------------------------------


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = plan_dir(root, args.task_id)
    reject_symlink_components(root, plan)
    if plan.exists():
        raise PlanError(f"plan already exists: {plan}")
    index = (
        (template_dir() / INDEX_FILE)
        .read_text(encoding="utf-8")
        .replace("<task-id>", args.task_id)
        .replace(
            "<一段話描述本 task 要達成的具體結果。穩定,少動。>", args.goal
        )
    )
    create_new(plan / INDEX_FILE, index)
    phases_path(plan).mkdir(parents=True, exist_ok=True)
    created = [INDEX_FILE, f"{PHASES_DIR}/"]
    if args.with_findings:
        findings = (
            (template_dir() / FINDINGS_FILE)
            .read_text(encoding="utf-8")
            .replace("<task-id>", args.task_id)
            .replace("YYYY-MM-DD", today())
        )
        create_new(plan / FINDINGS_FILE, findings)
        created.append(FINDINGS_FILE)
    return {"ok": True, "operation": "init", "task_id": args.task_id, "created": created}


def command_phase_start(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    topic = args.topic.strip()
    if not topic:
        raise PlanError("phase topic must be non-empty")
    slug = (args.slug or slugify(topic)).strip()
    if not SLUG_PATTERN.fullmatch(slug):
        raise PlanError(
            f"slug must match {SLUG_PATTERN.pattern}; pass --slug for a non-ASCII topic"
        )
    number = f"{next_phase_number(plan):02d}"
    record = f"{PHASES_DIR}/{number}-{slug}.md"
    create_new(plan / record, render_phase(number, topic))
    atomic_write(
        plan / INDEX_FILE,
        upsert_board_row(read_index(plan), number, "in_progress", record),
    )
    return {
        "ok": True,
        "operation": "phase-start",
        "phase": number,
        "record": record,
    }


def command_phase_set(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    path = find_phase_file(plan, args.phase)
    text = path.read_text(encoding="utf-8")
    if args.status and args.status not in PHASE_STATUSES:
        raise PlanError(f"status must be one of {PHASE_STATUSES}")
    if args.commit:
        text = set_phase_field(text, "Commit", args.commit)
    if args.conclusion:
        text = set_phase_field(text, "Conclusion", args.conclusion)
    if args.note:
        text = text.rstrip("\n") + f"\n- {args.note}\n"
    if args.status:
        if args.status == "completed":
            commit = args.commit or read_phase_field(text, "Commit")
            conclusion = args.conclusion or read_phase_field(text, "Conclusion")
            if field_is_unset(commit) or field_is_unset(conclusion):
                raise PlanError(
                    "completing a phase requires a Commit SHA and a Conclusion"
                )
        text = set_phase_field(text, "Status", args.status)
    atomic_write(path, text)
    number = f"{int(args.phase):02d}"
    record = f"{PHASES_DIR}/{path.name}"
    status = args.status or read_phase_field(text, "Status")
    atomic_write(
        plan / INDEX_FILE,
        upsert_board_row(read_index(plan), number, status, record),
    )
    return {"ok": True, "operation": "phase-set", "phase": number, "status": status}


def command_log(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    if args.verify:
        if not args.command or not args.result:
            raise PlanError("--verify requires --command and --result")
        row: dict[str, Any] = {
            "ts": now_ts(),
            "kind": "verify",
            "command": args.command,
            "result": args.result,
        }
        if args.sha:
            row["sha"] = args.sha
    else:
        if not args.action:
            raise PlanError("an event log requires --action (or use --verify)")
        row = {
            "ts": now_ts(),
            "kind": "event",
            "actor": args.actor or "root",
            "action": args.action,
            "result": args.result or "",
        }
        if args.next:
            row["next"] = args.next
    append_line(plan / PROGRESS_FILE, json.dumps(row, ensure_ascii=False, sort_keys=True))
    return {"ok": True, "operation": "log", "kind": row["kind"]}


def validate_plan(plan: Path) -> list[str]:
    """Structural checks across INDEX and the stores; returns human-readable issues."""
    issues: list[str] = []
    index = read_index(plan)
    if not INDEX_TITLE_PATTERN.search(index):
        issues.append("INDEX has no '# <title>' line")
    if not GOAL_PATTERN.search(index):
        issues.append("INDEX has no '**Goal:**' line")
    for heading in REQUIRED_HEADINGS:
        if heading not in index:
            issues.append(f"INDEX is missing the '{heading}' section")
    board_phases = {row["phase"] for row in read_board(index)} if BOARD_HEADING in index else set()
    for num, _, path in existing_phase_files(plan):
        text = path.read_text(encoding="utf-8")
        for field in PHASE_FIELDS:
            if not re.search(rf"^- \*\*{re.escape(field)}:\*\*", text, re.MULTILINE):
                issues.append(f"{path.name} has no '{field}' field")
        if f"{num:02d}" not in board_phases:
            issues.append(f"{path.name} is not listed on the INDEX phase board")
    progress = plan / PROGRESS_FILE
    if progress.is_file():
        for lineno, line in enumerate(progress.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    issues.append(f"{PROGRESS_FILE}:{lineno} is not valid JSON")
    return issues


# ---- migration (old task_plan.md -> new INDEX + stores) ---------------------


def _old_section_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), -1)
    if start < 0:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start + 1 : end]).strip("\n")


def _old_table_rows(body: str) -> list[list[str]]:
    data = [line for line in body.splitlines() if line.lstrip().startswith("|")]
    rows: list[list[str]] = []
    for line in data:
        cells = row_cells(line)
        joined = "".join(cells)
        if not joined or set(joined) <= set("-: "):
            continue  # header separator or blank
        rows.append(cells)
    return rows[1:] if rows else rows  # drop the header row


def _old_active_notes(text: str) -> dict[str, dict[str, str]]:
    """Parse `### Phase N — topic` blocks under `## Active Notes`."""
    body = _old_section_body(text, "## Active Notes")
    notes: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in body.splitlines():
        heading = re.match(r"^### Phase\s+([0-9]+)\s*[—-]\s*(.*)$", line)
        if heading:
            current = heading.group(1) or ""
            notes[current] = {"topic": (heading.group(2) or "").strip(), "detail": ""}
        elif current is not None:
            notes[current]["detail"] += line + "\n"
    return notes


def replace_section_body(text: str, heading: str, body_lines: list[str]) -> str:
    lines = text.splitlines()
    start, end = section_span(lines, heading)
    new = [lines[start], ""] + body_lines + [""]
    result = lines[:start] + new + lines[end:]
    return "\n".join(result) + ("\n" if text.endswith("\n") else "")


def command_migrate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = plan_dir(root, args.task_id)
    reject_symlink_tree(root, plan)
    old = plan / "task_plan.md"
    if not old.is_file():
        raise PlanError(
            f"no old task_plan.md under {plan} (already migrated, or not a plan)"
        )
    if (plan / INDEX_FILE).exists():
        raise PlanError(f"{INDEX_FILE} already exists; refusing to overwrite")
    text = old.read_text(encoding="utf-8")
    goal = _old_section_body(text, "## Goal").strip()
    if not goal:
        raise PlanError("old task_plan.md has no '## Goal'; migrate by hand")

    punch_list: list[str] = []
    # INDEX scaffold from the template, then surgically filled.
    index = (
        (template_dir() / INDEX_FILE)
        .read_text(encoding="utf-8")
        .replace("<task-id>", args.task_id)
        .replace("<一段話描述本 task 要達成的具體結果。穩定,少動。>", goal)
    )
    # Current State = old Current State + Architecture Baseline (root prunes stale).
    current = _old_section_body(text, "## Current State").splitlines()
    arch = _old_section_body(text, "## Architecture Baseline").strip()
    body = [line for line in current if line.strip()] or ["- (migrated; prune me)"]
    if arch:
        body += ["", "*Architecture baseline (merge or drop):*"] + [
            line for line in arch.splitlines() if line.strip()
        ]
    body += ["- **Next gate:** <填入下一個可機械驗收動作>"]
    index = replace_section_body(index, "## Current State", body)
    punch_list.append("prune Current State to what is still live; set Next gate")

    # Decisions table carried across (old col4 'Supersedes/Authority' -> 'Authority').
    decision_rows = _old_table_rows(_old_section_body(text, "## Decisions"))
    if decision_rows:
        table = ["| ID | Status | Decision | Authority |", "|---|---|---|---|"]
        for cells in decision_rows:
            padded = (cells + ["", "", "", ""])[:4]
            table.append(f"| {padded[0]} | {padded[1]} | {padded[2]} | {padded[3]} |")
        index = replace_section_body(index, "## Decisions", table)
        punch_list.append("confirm each decision's Status (active vs superseded)")

    atomic_write(plan / INDEX_FILE, index)
    phases_path(plan).mkdir(parents=True, exist_ok=True)

    # Phases: union of the Phase Status table and the Active Notes blocks.
    status_rows = _old_table_rows(_old_section_body(text, "## Phase Status"))
    hist_rows = _old_table_rows(_old_section_body(text, "## Historical Phase Summary"))
    notes = _old_active_notes(text)
    hist_concl = {row[0].replace("Phase", "").strip(): row[-1] for row in hist_rows if row}
    created_phases: list[str] = []
    seen: set[str] = set()

    def phase_number(label: str) -> str:
        digits = re.sub(r"[^0-9]", "", label)
        return f"{int(digits):02d}" if digits else ""

    ordered: list[tuple[str, str, str, str]] = []  # (num, topic, status, scope)
    for cells in status_rows:
        num = phase_number(cells[0])
        if not num:
            continue
        topic = notes.get(str(int(num)), {}).get("topic", "") or (
            cells[2] if len(cells) > 2 else ""
        )
        status = cells[1].strip() if len(cells) > 1 else "pending"
        scope = cells[2].strip() if len(cells) > 2 else "none"
        ordered.append((num, topic, status, scope))
    for pnum, note in notes.items():  # notes without a status row
        num = f"{int(pnum):02d}"
        if all(existing[0] != num for existing in ordered):
            ordered.append((num, note.get("topic", ""), "completed", "none"))

    for num, topic, status, scope in sorted(ordered):
        if num in seen:
            continue
        seen.add(num)
        slug = slugify(topic) or f"phase-{int(num)}"
        conclusion = (hist_concl.get(str(int(num)), "") or "").strip() or "pending"
        detail = notes.get(str(int(num)), {}).get("detail", "").strip()
        status = status if status in PHASE_STATUSES else "pending"
        commit_match = re.search(r"\b[0-9a-f]{7,40}\b", conclusion)
        commit = commit_match.group(0) if commit_match else "none"
        record = f"{PHASES_DIR}/{num}-{slug}.md"
        phase_text = (
            f"# Phase {num} — {topic or slug}\n\n"
            f"- **Status:** {status}\n"
            f"- **Scope:** {scope or 'none'}\n"
            f"- **Decisions made:** none\n"
            f"- **Conclusion:** {conclusion}\n"
            f"- **Commit:** {commit}\n"
            f"- **Evidence:** none\n\n"
            f"## Notes\n\n"
            f"{detail or '- (migrated)'}\n"
        )
        create_new(plan / record, phase_text)
        atomic_write(
            plan / INDEX_FILE, upsert_board_row(read_index(plan), num, status, record)
        )
        created_phases.append(record)
    if created_phases:
        punch_list.append("check phase slugs and fill any Conclusion left 'pending'")

    # progress.md tables -> progress.jsonl
    progress_old = plan / "progress.md"
    progress_rows = 0
    if progress_old.is_file():
        ptext = progress_old.read_text(encoding="utf-8")
        for cells in _old_table_rows(_old_section_body(ptext, "## Timeline")):
            padded = (cells + ["", "", "", "", ""])[:5]
            row = {
                "ts": padded[0] or now_ts(),
                "kind": "event",
                "actor": padded[1] or "unknown",
                "action": padded[2],
                "result": padded[3],
            }
            if padded[4]:
                row["next"] = padded[4]
            append_line(plan / PROGRESS_FILE, json.dumps(row, ensure_ascii=False, sort_keys=True))
            progress_rows += 1
        for cells in _old_table_rows(_old_section_body(ptext, "## Verification Log")):
            padded = (cells + ["", "", ""])[:3]
            row = {"ts": padded[0] or now_ts(), "kind": "verify", "command": padded[1], "result": padded[2]}
            append_line(plan / PROGRESS_FILE, json.dumps(row, ensure_ascii=False, sort_keys=True))
            progress_rows += 1

    # Preserve every original under history/pre-migration/ (nothing is deleted).
    preserved = plan / "history" / "pre-migration"
    preserved.mkdir(parents=True, exist_ok=True)
    for name in ("task_plan.md", "progress.md"):
        source = plan / name
        if source.is_file():
            shutil.move(str(source), str(preserved / name))
    for directory in ("domains", "history"):
        source = plan / directory
        if directory == "domains" and source.is_dir():
            shutil.move(str(source), str(preserved / directory))
            punch_list.append(f"merge {directory}/ packets into Current State, then drop")

    return {
        "ok": True,
        "operation": "migrate",
        "task_id": args.task_id,
        "phases": created_phases,
        "progress_rows": progress_rows,
        "preserved_under": str(preserved.relative_to(plan)),
        "punch_list": punch_list,
    }


def command_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    issues = validate_plan(plan)
    if issues:
        raise PlanError("plan is not schema-valid: " + "; ".join(issues))
    size = utf8_size(read_index(plan))
    if size > INDEX_LIMIT_BYTES:
        raise PlanError(
            f"{INDEX_FILE} is {size} bytes over the {INDEX_LIMIT_BYTES} budget; prune"
            " Current State and superseded decisions — phase detail belongs in its"
            " phases/ record, not the entry"
        )
    return {
        "ok": True,
        "operation": args.operation if hasattr(args, "operation") else "checkpoint",
        "task_id": args.task_id,
        "index_bytes": size,
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    index = read_index(plan)
    board = read_board(index)
    progress = plan / PROGRESS_FILE
    progress_rows = (
        sum(1 for line in progress.read_text(encoding="utf-8").splitlines() if line.strip())
        if progress.is_file()
        else 0
    )
    return {
        "ok": True,
        "operation": "status",
        "task_id": args.task_id,
        "index_bytes": utf8_size(index),
        "phases": board,
        "stores": {
            "phases": len(existing_phase_files(plan)),
            "progress_rows": progress_rows,
            "findings": (plan / FINDINGS_FILE).is_file(),
        },
    }


def command_check(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    open_phases = [row["phase"] for row in read_board(read_index(plan)) if row["status"] in OPEN_STATUSES]
    if open_phases:
        raise PlanError(f"phase board still has open phases: {', '.join(open_phases)}")
    return {"ok": True, "operation": "check", "task_id": args.task_id}


def command_archive(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    destination = archive_dir(root, args.task_id)
    reject_symlink_components(root, destination)
    if destination.exists():
        raise PlanError(f"archive destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(plan), str(destination))
    return {"ok": True, "operation": "archive", "task_id": args.task_id, "archived_to": str(destination)}


# ---- cli --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("task_id")
    init.add_argument("--goal", required=True)
    init.add_argument("--with-findings", action="store_true")
    init.set_defaults(handler=command_init)

    status = commands.add_parser("status")
    status.add_argument("task_id")
    status.set_defaults(handler=command_status)

    phase_start = commands.add_parser("phase-start")
    phase_start.add_argument("task_id")
    phase_start.add_argument("--topic", required=True)
    phase_start.add_argument("--slug")
    phase_start.set_defaults(handler=command_phase_start)

    phase_set = commands.add_parser("phase-set")
    phase_set.add_argument("task_id")
    phase_set.add_argument("--phase", required=True)
    phase_set.add_argument("--status")
    phase_set.add_argument("--commit")
    phase_set.add_argument("--conclusion")
    phase_set.add_argument("--note")
    phase_set.set_defaults(handler=command_phase_set)

    log = commands.add_parser("log")
    log.add_argument("task_id")
    log.add_argument("--actor")
    log.add_argument("--action")
    log.add_argument("--result")
    log.add_argument("--next")
    log.add_argument("--verify", action="store_true")
    log.add_argument("--command")
    log.add_argument("--sha")
    log.set_defaults(handler=command_log)

    for name in ("checkpoint", "compact"):
        command = commands.add_parser(name)
        command.add_argument("task_id")
        command.set_defaults(handler=command_checkpoint, operation=name)

    migrate = commands.add_parser("migrate")
    migrate.add_argument("task_id")
    migrate.set_defaults(handler=command_migrate)

    check = commands.add_parser("check")
    check.add_argument("task_id")
    check.set_defaults(handler=command_check)

    archive = commands.add_parser("archive")
    archive.add_argument("task_id")
    archive.set_defaults(handler=command_archive)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.handler(args)
    except PlanError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
