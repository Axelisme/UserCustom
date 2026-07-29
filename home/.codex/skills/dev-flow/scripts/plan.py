#!/usr/bin/env python3
"""Workflow-neutral durable task-record v1 command line kernel."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
NUMERIC_ID = re.compile(r"^T([0-9]{3,})$")
TITLE = re.compile(r"^# ([A-Za-z0-9][A-Za-z0-9._-]{0,63}) — ([^\r\n]+)$")
LINK = re.compile(r"\[[^\]\r\n]+\]\(([^)\r\n]+)\)")
POINTER_LINE = re.compile(r"(?:- )?\[[^\]\r\n]+\]\([^)\r\n]+\)")
RECORD_VERSION_FIELD = re.compile(r"^\|\s*record_version\s*\|", re.MULTILINE)
TEMPLATE_FIELD = re.compile(r"{{([A-Z_]+)}}")
URI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
INDEX_LIMIT = 16_384
INDEX_SECTIONS = ("Goal", "Current", "Next", "Active decisions", "Tickets", "Artifacts")
TICKET_SECTIONS = ("Outcome", "Current", "Decisions", "Evidence", "Result")
START = "<!-- task-record:tickets:start -->"
END = "<!-- task-record:tickets:end -->"
TABLE_HEADER = "| ID | Status | Title | Depends on |\n|---|---|---|---|\n"
STATUSES = {"open", "active", "blocked", "closed"}


class Refusal(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        paths: tuple[str, ...] = (),
        version: int | None = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.paths = tuple(sorted(paths))
        self.version = version


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    title: str
    status: str
    dependencies: tuple[str, ...]
    path: Path


@dataclass(frozen=True)
class Record:
    directory: Path
    index: Path
    text: str
    tickets: tuple[Ticket, ...]
    version: int | None


def emit(operation: str, *, ok: bool, version: int | None, **values: object) -> None:
    body: dict[str, object] = {
        "ok": ok,
        "operation": operation,
        "record_version": version,
    }
    body.update(values)
    print(json.dumps(body, ensure_ascii=False, separators=(",", ":")))


def fail(operation: str, refusal: Refusal) -> NoReturn:
    emit(
        operation,
        ok=False,
        version=refusal.version,
        error={
            "code": refusal.code,
            "message": refusal.message,
            "paths": list(refusal.paths),
        },
    )
    raise SystemExit(1)


def validate_id(value: str, kind: str) -> None:
    if not SAFE_ID.fullmatch(value) or not value.isascii():
        raise Refusal(f"invalid_{kind}_id", f"invalid {kind} id: {value!r}")


def state_dir(root: Path, location: str, task_id: str) -> Path:
    return root / ".agent_state" / location / task_id


def relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def template(name: str) -> str:
    return (Path(__file__).resolve().parent.parent / "templates" / name).read_text(
        encoding="utf-8"
    )


def render_template(name: str, **values: str) -> str:
    return TEMPLATE_FIELD.sub(lambda match: values[match.group(1)], template(name))


def atomic_write(path: Path, text: str) -> None:
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


def reject_symlink_components(root: Path, path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    try:
        parts = absolute.relative_to(root).parts
    except ValueError as exc:
        raise Refusal("invalid_pointer", f"path escapes repository: {path}") from exc
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise Refusal("symlink", f"symlink is not allowed: {relative(root, current)}", (relative(root, current),))


def reject_symlink_tree(root: Path, directory: Path) -> None:
    reject_symlink_components(root, directory)
    if directory.is_symlink() or not directory.is_dir():
        raise Refusal("symlink", f"record is not a real directory: {directory}")
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise Refusal("symlink", f"symlink is not allowed: {relative(root, path)}", (relative(directory, path),))


def sections(text: str, expected: tuple[str, ...], code: str) -> dict[str, str]:
    found = list(re.finditer(r"^## ([^\r\n]+)$", text, re.MULTILINE))
    names = tuple(match.group(1) for match in found)
    if names != expected:
        raise Refusal(code, f"required sections must appear exactly once in order: {', '.join(expected)}")
    bodies: dict[str, str] = {}
    for index, match in enumerate(found):
        start = match.end() + 1
        stop = found[index + 1].start() if index + 1 < len(found) else len(text)
        bodies[match.group(1)] = text[start:stop].rstrip("\n")
    return bodies


def table_cells(line: str, count: int) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError(line)
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line[1:-1]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    if len(cells) != count:
        raise ValueError(line)
    return cells


def slug(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    result = "-".join(re.findall(r"[a-z0-9]+", ascii_title.casefold()))[:48].rstrip("-")
    return result or "ticket"


def escaped_cell(value: str) -> str:
    value = re.sub(r"[\r\n]+", " ", value)
    return value.replace("\\", "\\\\").replace("|", "\\|")


def validate_pointers(root: Path, markdown: Path, body: str) -> None:
    targets = LINK.findall(body)
    if len(targets) != len(set(targets)):
        raise Refusal("invalid_pointer", f"duplicate pointer in {relative(root, markdown)}", (relative(root, markdown),))
    for pointer in targets:
        path_text = pointer.split("#", 1)[0]
        if (
            not path_text
            or "\x00" in path_text
            or "\\" in path_text
            or URI.match(path_text)
            or Path(path_text).is_absolute()
        ):
            raise Refusal("invalid_pointer", f"invalid pointer: {pointer}", (relative(root, markdown),))
        lexical = Path(os.path.abspath(markdown.parent / path_text))
        try:
            parts = lexical.relative_to(root).parts
        except ValueError as exc:
            raise Refusal("invalid_pointer", f"pointer escapes repository: {pointer}", (relative(root, markdown),)) from exc
        if ".git" in parts:
            raise Refusal("invalid_pointer", f"pointer enters .git: {pointer}", (relative(root, markdown),))
        try:
            reject_symlink_components(root, lexical)
        except Refusal as refusal:
            refusal.paths = tuple(sorted({*refusal.paths, relative(root, markdown)}))
            raise
        if not lexical.is_file():
            raise Refusal("invalid_pointer", f"pointer target is not a regular file: {pointer}", (relative(root, markdown),))


def legacy(directory: Path) -> bool:
    index = directory / "INDEX.md"
    if not index.is_file() or index.is_symlink():
        return False
    try:
        text = index.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    if RECORD_VERSION_FIELD.search(text):
        return False
    phases = directory / "phases"
    progress = directory / "progress.jsonl"
    return (phases.is_dir() and not phases.is_symlink()) or (progress.is_file() and not progress.is_symlink())


def parse_active_decisions(text: str, path: Path, root: Path) -> None:
    lines = text.splitlines()
    if lines[:2] != ["| ID | Pointer |", "|---|---|"]:
        raise Refusal("malformed_index", "invalid Active decisions table", (relative(root, path),))
    seen: set[str] = set()
    for line in lines[2:]:
        if not line.strip():
            continue
        try:
            decision_id, pointer = table_cells(line, 2)
        except ValueError as exc:
            raise Refusal("malformed_index", "invalid Active decisions row", (relative(root, path),)) from exc
        if not SAFE_ID.fullmatch(decision_id) or not decision_id.isascii() or decision_id.casefold() in seen or not LINK.fullmatch(pointer):
            raise Refusal("malformed_index", f"invalid active decision: {decision_id}", (relative(root, path),))
        seen.add(decision_id.casefold())


def parse_decisions(text: str, path: Path, root: Path) -> None:
    lines = text.splitlines()
    expected = [
        "| ID | Status | Decision | Supersedes |",
        "|---|---|---|---|",
    ]
    if lines[:2] != expected:
        raise Refusal("malformed_decisions", "invalid Decisions table", (relative(root, path),))
    rows: dict[str, tuple[str, str]] = {}
    for line in lines[2:]:
        if not line.strip():
            continue
        try:
            decision_id, status, decision, predecessor = table_cells(line, 4)
        except ValueError as exc:
            raise Refusal("malformed_decisions", "invalid Decisions row", (relative(root, path),)) from exc
        if not SAFE_ID.fullmatch(decision_id) or not decision_id.isascii() or decision_id.casefold() in {item.casefold() for item in rows}:
            raise Refusal("malformed_decisions", f"invalid or duplicate decision id: {decision_id}", (relative(root, path),))
        if status not in {"active", "superseded"} or not decision:
            raise Refusal("malformed_decisions", f"invalid decision {decision_id}", (relative(root, path),))
        rows[decision_id] = (status, predecessor)
    incoming: dict[str, int] = {item: 0 for item in rows}
    for decision_id, (_, predecessor) in rows.items():
        if predecessor == "none":
            continue
        if predecessor == decision_id or predecessor not in rows:
            raise Refusal("malformed_decisions", f"invalid supersession from {decision_id} to {predecessor}", (relative(root, path),))
        incoming[predecessor] += 1
    if any(count > 1 for count in incoming.values()):
        raise Refusal("malformed_decisions", "a decision has multiple replacements", (relative(root, path),))
    for decision_id, (status, _) in rows.items():
        if (status == "active" and incoming[decision_id]) or (status == "superseded" and incoming[decision_id] != 1):
            raise Refusal("malformed_decisions", f"inconsistent decision status: {decision_id}", (relative(root, path),))
    for start in rows:
        seen: set[str] = set()
        current = start
        while rows[current][1] != "none":
            if current in seen:
                raise Refusal("malformed_decisions", "decision supersession cycle", (relative(root, path),))
            seen.add(current)
            current = rows[current][1]


def parse_ticket(root: Path, path: Path) -> Ticket:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Refusal("malformed_ticket", f"unreadable ticket: {path.name}", (relative(root, path),)) from exc
    lines = text.splitlines()
    match = TITLE.fullmatch(lines[0] if lines else "")
    if not match or text.count("\n# ") or "\r" in text:
        raise Refusal("malformed_ticket", f"invalid ticket H1: {path.name}", (relative(root, path),))
    ticket_id, title = match.groups()
    if title != title.strip():
        raise Refusal("malformed_ticket", "ticket H1 title is not canonical", (relative(root, path),))
    expected_name = f"{ticket_id}-{slug(title)}.md"
    if path.name != expected_name:
        raise Refusal("malformed_ticket", f"ticket filename must be {expected_name}", (relative(root, path),))
    field = (
        f"# {ticket_id} — {title}\n\n| Ticket field | Value |\n|---|---|\n"
        f"| id | {ticket_id} |\n| status | "
    )
    if not text.startswith(field):
        raise Refusal("malformed_ticket", "invalid ticket field table", (relative(root, path),))
    metadata = re.match(
        re.escape(field) + r"([^|\r\n]+) \|\n\| depends_on \| ([^|\r\n]+) \|\n\n",
        text,
    )
    if not metadata:
        raise Refusal("malformed_ticket", "invalid ticket metadata", (relative(root, path),))
    status, dependency_text = (value.strip() for value in metadata.groups())
    if status not in STATUSES:
        raise Refusal("malformed_ticket", f"invalid ticket status: {status}", (relative(root, path),))
    body = sections(text[metadata.end():], TICKET_SECTIONS, "malformed_ticket")
    if not body["Outcome"].strip() or not body["Current"].strip():
        raise Refusal("malformed_ticket", "Outcome and Current must be non-empty", (relative(root, path),))
    result = body["Result"].strip()
    if (status == "closed" and (not result or result == "pending")) or (status != "closed" and result != "pending"):
        raise Refusal("malformed_ticket", "ticket status and Result disagree", (relative(root, path),))
    parse_decisions(body["Decisions"], path, root)
    evidence_lines = [line for line in body["Evidence"].splitlines() if line.strip()]
    if any(not POINTER_LINE.fullmatch(line) for line in evidence_lines):
        raise Refusal(
            "malformed_ticket",
            "Evidence must contain Markdown pointers only",
            (relative(root, path),),
        )
    validate_pointers(root, path, body["Evidence"])
    if dependency_text == "none":
        dependencies: tuple[str, ...] = ()
    else:
        dependencies = tuple(item.strip() for item in dependency_text.split(","))
        if any(not item for item in dependencies) or len({item.casefold() for item in dependencies}) != len(dependencies):
            raise Refusal("duplicate_dependency", f"duplicate dependency in {ticket_id}", (relative(root, path),))
        if dependencies != tuple(sorted(dependencies, key=lambda item: (item.casefold(), item))):
            raise Refusal("malformed_ticket", f"dependencies are not sorted in {ticket_id}", (relative(root, path),))
    return Ticket(ticket_id, title, status, dependencies, path)


def graph(tickets: tuple[Ticket, ...], root: Path) -> None:
    by_id: dict[str, Ticket] = {}
    folded: dict[str, str] = {}
    for ticket in tickets:
        key = ticket.ticket_id.casefold()
        if key in folded:
            raise Refusal("duplicate_ticket_id", f"duplicate ticket id: {ticket.ticket_id}", tuple(relative(root, item.path) for item in tickets if item.ticket_id.casefold() == key))
        by_id[ticket.ticket_id] = ticket
        folded[key] = ticket.ticket_id
    for ticket in sorted(tickets, key=lambda item: (item.ticket_id.casefold(), item.ticket_id)):
        for dependency in ticket.dependencies:
            if dependency not in by_id:
                raise Refusal("missing_dependency", f"{ticket.ticket_id} depends on missing ticket {dependency}", (relative(root, ticket.path),))
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(ticket_id: str) -> None:
        if ticket_id in visiting:
            cycle = visiting[visiting.index(ticket_id):] + [ticket_id]
            raise Refusal("dependency_cycle", " -> ".join(cycle), tuple(relative(root, by_id[item].path) for item in set(cycle)))
        if ticket_id in visited:
            return
        visiting.append(ticket_id)
        for dependency in by_id[ticket_id].dependencies:
            visit(dependency)
        visiting.pop()
        visited.add(ticket_id)

    for ticket_id in sorted(by_id, key=lambda item: (item.casefold(), item)):
        visit(ticket_id)


def rendered_table(tickets: tuple[Ticket, ...]) -> str:
    rows = []
    for ticket in sorted(tickets, key=lambda item: (item.ticket_id.casefold(), item.ticket_id)):
        dependencies = ", ".join(ticket.dependencies) or "none"
        rows.append(
            f"| {escaped_cell(ticket.ticket_id)} | {ticket.status} | {escaped_cell(ticket.title)} | {escaped_cell(dependencies)} |\n"
        )
    return TABLE_HEADER + "".join(rows)


def parse_record(root: Path, directory: Path, *, require_parity: bool = True) -> Record:
    if not directory.exists():
        raise Refusal("record_missing", f"record not found: {directory.name}", version=None)
    reject_symlink_tree(root, directory)
    index = directory / "INDEX.md"
    if legacy(directory):
        return Record(directory, index, index.read_text(encoding="utf-8"), (), None)
    if not index.is_file():
        raise Refusal("malformed_index", "INDEX.md is missing", (relative(root, index),), None)
    try:
        raw = index.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise Refusal("malformed_index", "INDEX.md is not readable UTF-8", (relative(root, index),), None) from exc
    version = 1 if "record_version" in text and "| record_version | 1 |" in text else None
    if len(raw) > INDEX_LIMIT or "\r" in text:
        raise Refusal("malformed_index", "INDEX.md exceeds its UTF-8 budget or contains CR", (relative(root, index),), version)
    prefix = (
        f"# {directory.name}\n\n| Record field | Value |\n|---|---|\n"
        f"| record_version | 1 |\n| task_id | {directory.name} |\n\n"
    )
    if not text.startswith(prefix) or text.count("\n# ") or text.count("| Record field | Value |") != 1:
        raise Refusal("malformed_index", "invalid INDEX H1 or record table", (relative(root, index),), version)
    body = sections(text[len(prefix):], INDEX_SECTIONS, "malformed_index")
    if any(not body[name].strip() for name in ("Goal", "Current", "Next")):
        raise Refusal("malformed_index", "Goal, Current and Next must be non-empty", (relative(root, index),))
    ticket_body = body["Tickets"]
    if ticket_body.count(START) != 1 or ticket_body.count(END) != 1 or ticket_body.index(START) > ticket_body.index(END):
        raise Refusal("malformed_markers", "INDEX must contain one ordered ticket marker pair", (relative(root, index),))
    marker_prefix, rest = ticket_body.split(START)
    generated, marker_suffix = rest.split(END)
    if marker_prefix.strip() or marker_suffix.strip():
        raise Refusal("malformed_markers", "ticket markers must bound the complete generated table", (relative(root, index),))
    ticket_dir = directory / "tickets"
    if not ticket_dir.is_dir() or ticket_dir.is_symlink():
        raise Refusal("malformed_index", "tickets must be a real directory", (relative(root, ticket_dir),))
    entries = sorted(ticket_dir.iterdir(), key=lambda item: item.name)
    if any(not item.is_file() or item.is_symlink() or item.suffix != ".md" for item in entries):
        raise Refusal("malformed_ticket", "tickets contains an unsupported entry", tuple(relative(root, item) for item in entries if not item.is_file() or item.is_symlink() or item.suffix != ".md"))
    tickets = tuple(parse_ticket(root, path) for path in entries)
    graph(tickets, root)
    parse_active_decisions(body["Active decisions"], index, root)
    validate_pointers(root, index, body["Active decisions"] + "\n" + body["Artifacts"])
    expected = "\n" + rendered_table(tickets)
    if require_parity and generated != expected:
        raise Refusal("table_mismatch", "generated ticket table does not match ticket files; run refresh", (relative(root, index),))
    return Record(directory, index, text, tickets, 1)


def refresh_record(root: Path, record: Record) -> None:
    start = record.text.index(START) + len(START)
    end = record.text.index(END, start)
    updated = record.text[:start] + "\n" + rendered_table(record.tickets) + record.text[end:]
    if updated != record.text:
        if len(updated.encode("utf-8")) > INDEX_LIMIT:
            raise Refusal("table_mismatch", "refreshed INDEX exceeds its UTF-8 budget", (relative(root, record.index),))
        atomic_write(record.index, updated)


def location_collision(root: Path, location: str, task_id: str) -> bool:
    parent = root / ".agent_state" / location
    reject_symlink_components(root, parent)
    folded = task_id.casefold()
    return parent.is_dir() and any(
        item.name.casefold() == folded for item in parent.iterdir()
    )


def collision(root: Path, task_id: str) -> bool:
    return any(
        location_collision(root, location, task_id)
        for location in ("plans", "archives")
    )


def command_create(root: Path, arguments: argparse.Namespace) -> None:
    validate_id(arguments.task_id, "task")
    if not arguments.goal.strip() or any(character in arguments.goal for character in "\r\x00"):
        raise Refusal("malformed_index", "goal must be non-empty UTF-8 text")
    if collision(root, arguments.task_id):
        raise Refusal("record_exists", f"active or archived record already exists: {arguments.task_id}")
    plans = root / ".agent_state" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{arguments.task_id}.", dir=plans))
    temporary = staging / arguments.task_id
    destination = plans / arguments.task_id
    try:
        (temporary / "tickets").mkdir(parents=True)
        text = render_template(
            "INDEX.md", TASK_ID=arguments.task_id, GOAL=arguments.goal
        )
        atomic_write(temporary / "INDEX.md", text)
        parse_record(root, temporary)
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            try:
                (temporary / "INDEX.md").unlink(missing_ok=True)
                (temporary / "tickets").rmdir()
                temporary.rmdir()
            except OSError:
                pass
        try:
            staging.rmdir()
        except OSError:
            pass
    emit("create", ok=True, version=1, task_id=arguments.task_id, paths=sorted((relative(root, destination / "INDEX.md"), relative(root, destination / "tickets"))))


def command_ticket_create(root: Path, arguments: argparse.Namespace) -> None:
    validate_id(arguments.task_id, "task")
    record = parse_record(root, state_dir(root, "plans", arguments.task_id))
    if record.version is None:
        raise Refusal("legacy_record", "legacy records are diagnostics-only; create a v1 task", version=None)
    title = arguments.title.strip()
    if not title or any(character in arguments.title for character in "\r\n\x00"):
        raise Refusal("malformed_ticket", "title must be one non-empty line")
    if not arguments.outcome.strip() or "\x00" in arguments.outcome:
        raise Refusal("malformed_ticket", "outcome must be non-empty Markdown")
    existing = {ticket.ticket_id.casefold(): ticket for ticket in record.tickets}
    if arguments.ticket_id is None:
        highest = max((int(match.group(1)) for ticket in record.tickets if (match := NUMERIC_ID.fullmatch(ticket.ticket_id))), default=0)
        ticket_id = f"T{highest + 1:03d}"
    else:
        ticket_id = arguments.ticket_id
        validate_id(ticket_id, "ticket")
    if ticket_id.casefold() in existing:
        raise Refusal("duplicate_ticket_id", f"duplicate ticket id: {ticket_id}")
    dependencies = tuple(arguments.depends)
    if len({item.casefold() for item in dependencies}) != len(dependencies):
        raise Refusal("duplicate_dependency", f"duplicate dependency for {ticket_id}")
    by_exact = {ticket.ticket_id for ticket in record.tickets}
    missing = sorted(item for item in dependencies if item not in by_exact)
    if missing:
        raise Refusal("missing_dependency", f"{ticket_id} depends on missing ticket {missing[0]}")
    dependencies = tuple(sorted(dependencies, key=lambda item: (item.casefold(), item)))
    path = record.directory / "tickets" / f"{ticket_id}-{slug(title)}.md"
    text = render_template(
        "ticket.md",
        TICKET_ID=ticket_id,
        TITLE=title,
        DEPENDS_ON=", ".join(dependencies) or "none",
        OUTCOME=arguments.outcome,
    )
    atomic_write(path, text)
    try:
        updated = parse_record(root, record.directory, require_parity=False)
    except Refusal:
        path.unlink(missing_ok=True)
        raise
    refresh_record(root, updated)
    emit("ticket-create", ok=True, version=1, task_id=arguments.task_id, ticket_id=ticket_id, paths=sorted((relative(root, record.index), relative(root, path))))


def command_refresh(root: Path, arguments: argparse.Namespace) -> None:
    validate_id(arguments.task_id, "task")
    record = parse_record(root, state_dir(root, "plans", arguments.task_id), require_parity=False)
    if record.version is None:
        raise Refusal("legacy_record", "legacy records cannot be refreshed", version=None)
    refresh_record(root, record)
    emit("refresh", ok=True, version=1, task_id=arguments.task_id, paths=[relative(root, record.index)])


def command_check(root: Path, arguments: argparse.Namespace) -> None:
    validate_id(arguments.task_id, "task")
    record = parse_record(root, state_dir(root, "plans", arguments.task_id))
    if record.version is None:
        raise Refusal("legacy_record", "legacy record detected; archive/resume only, no automatic migration", (relative(root, record.index),), None)
    emit("check", ok=True, version=1, task_id=arguments.task_id, paths=[relative(root, record.index)])


def command_move(root: Path, arguments: argparse.Namespace, operation: str) -> None:
    validate_id(arguments.task_id, "task")
    source_location, destination_location = (("plans", "archives") if operation == "archive" else ("archives", "plans"))
    source = state_dir(root, source_location, arguments.task_id)
    destination = state_dir(root, destination_location, arguments.task_id)
    reject_symlink_components(root, source)
    reject_symlink_components(root, destination)
    if not source.exists():
        raise Refusal("record_missing", f"source record not found: {arguments.task_id}", version=None)
    if not source.is_dir():
        raise Refusal("symlink", f"record is not a real directory: {source}")
    is_legacy = legacy(source)
    version = None if is_legacy else 1
    if location_collision(root, destination_location, arguments.task_id):
        raise Refusal(
            "record_exists",
            f"destination record already exists: {arguments.task_id}",
            version=version,
        )
    if not is_legacy:
        version = parse_record(root, source).version
    destination.parent.mkdir(parents=True, exist_ok=True)
    reject_symlink_components(root, destination.parent)
    if source.parent.stat().st_dev != destination.parent.stat().st_dev:
        raise Refusal("non_atomic_move", "source and destination are on different filesystems", (relative(root, source), relative(root, destination)), version)
    try:
        os.rename(source, destination)
    except OSError as exc:
        raise Refusal("non_atomic_move", f"atomic directory rename refused: {exc}", (relative(root, source), relative(root, destination)), version) from exc
    emit(operation, ok=True, version=version, task_id=arguments.task_id, paths=[relative(root, destination)])


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="operation", required=True)
    create = commands.add_parser("create")
    create.add_argument("task_id")
    create.add_argument("--goal", required=True)
    ticket = commands.add_parser("ticket-create")
    ticket.add_argument("task_id")
    ticket.add_argument("--title", required=True)
    ticket.add_argument("--outcome", required=True)
    ticket.add_argument("--id", dest="ticket_id")
    ticket.add_argument("--depends", nargs="+", default=[])
    for name in ("refresh", "check", "archive", "resume"):
        command = commands.add_parser(name)
        command.add_argument("task_id")
    return result


def main() -> None:
    arguments = parser().parse_args()
    root = Path.cwd().resolve()
    operation = arguments.operation
    try:
        if operation == "create":
            command_create(root, arguments)
        elif operation == "ticket-create":
            command_ticket_create(root, arguments)
        elif operation == "refresh":
            command_refresh(root, arguments)
        elif operation == "check":
            command_check(root, arguments)
        else:
            command_move(root, arguments, operation)
    except Refusal as refusal:
        fail(operation, refusal)


if __name__ == "__main__":
    main()
