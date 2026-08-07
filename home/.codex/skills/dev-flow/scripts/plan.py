#!/usr/bin/env python3
"""Workflow-neutral durable task-record command line kernel."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

CURRENT_VERSION = 3
VALIDATED_VERSION = 3
SUPPORTED_VERSIONS = (2, 3)
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
VERSION_ROW = re.compile(r"^\|\s*record_version\s*\|\s*([^|\r\n]*)\s*\|\s*$", re.MULTILINE)
START = "<!-- task-record:files:start -->"
END = "<!-- task-record:files:end -->"
REFRESHED_MARKER = re.compile(r"<!-- task-record:refreshed-at:([^>\r\n]*) -->")

# Ticket status is exactly this closed enum. It replaces harness Task-tool vocabulary
# (`pending`, `in_progress`, `completed`, ...) which is a non-authoritative projection and must
# never enter a ticket. See dev-flow/SKILL.md "One task record".
AUTHORED_BUDGET = 6000
SECTION_HEADING = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
STANDING_ORDERS_HEADING = "Standing orders"
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Sections scanned for frozen commit-ish tokens carry a live judgement and nothing else.
# `Standing orders` and `Envelope` are excluded from that scan because verbatim quotes and frozen
# dates are legitimate there; separate custody rules below validate their structure.
LINTED_SECTIONS = ("Current", "Next")
# A commit-ish token. Only this rule is shipped: it measured zero false positives on real records,
# while counts and ref names did not converge (a bare year and ordinary English words match).
FROZEN_STATE_RULES = (("hex", re.compile(r"\b[0-9a-f]{7,40}\b")),)
STANDING_ORDER_ENTRY = re.compile(r"^- +\*\*", re.MULTILINE)
STANDING_ORDER_BLOCK = re.compile(r"^- +\*\*.*?(?=^- +\*\*|\Z)", re.MULTILINE | re.DOTALL)
STANDING_ORDER_DATE = re.compile(r"^- +\*\*\d{4}-\d{2}-\d{2} +—")
STANDING_ORDER_QUOTE = re.compile(r"^- +\*\*[^*\r\n]+:\*\* +「.+」\s*$", re.MULTILINE)
STANDING_ORDER_QUOTE_START = re.compile(r"^- +\*\*[^*\r\n]+:\*\* +「")
STANDING_ORDER_LAPSE = re.compile(r"^ +Lapses: +\S", re.MULTILINE)
TICKET_STATUSES = frozenset({"open", "active", "closed"})
# Required exactly when status is `closed`; distinguishes a resolved ticket from one ruled out of
# scope, superseded, or hard-stopped after its rework budget was exhausted.
TICKET_DISPOSITIONS = frozenset({"resolved", "superseded", "out-of-scope", "hard-stop"})
TICKET_STATUS_ROW = re.compile(r"^\|\s*status\s*\|\s*([^|\r\n]*)\|\s*$", re.MULTILINE)
TICKET_DISPOSITION_ROW = re.compile(r"^\|\s*disposition\s*\|\s*([^|\r\n]*)\|\s*$", re.MULTILINE)


class Refusal(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        repair: str,
        paths: tuple[str, ...] = (),
        version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.repair = repair
        self.paths = tuple(sorted(paths))
        self.version = version


@dataclass(frozen=True)
class RefreshRecord:
    directory: Path
    index: Path
    text: str
    version: int


def emit(operation: str, *, ok: bool, version: int | None, **values: object) -> None:
    body: dict[str, object] = {"ok": ok, "operation": operation, "record_version": version}
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
            "repair": refusal.repair,
        },
    )
    raise SystemExit(1)


def relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def validate_task_id(value: str) -> None:
    if not SAFE_ID.fullmatch(value) or not value.isascii():
        raise Refusal(
            "invalid_argument",
            f"invalid task id: {value!r}",
            f"Use an ASCII task id matching {SAFE_ID.pattern}.",
        )


def state_dir(root: Path, location: str, task_id: str) -> Path:
    return root / ".agent_state" / location / task_id


def template(name: str) -> str:
    return (Path(__file__).resolve().parent.parent / "templates" / name).read_text(encoding="utf-8")


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
        raise Refusal(
            "unsafe_path",
            f"path escapes repository: {path}",
            "Use a path contained by the repository root.",
        ) from exc
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise Refusal(
                "unsafe_path",
                f"symlink is not allowed: {relative(root, current)}",
                "Replace the named symlink with a real path component.",
                (relative(root, current),),
            )


def require_directory_components(root: Path, path: Path) -> None:
    reject_symlink_components(root, path)
    absolute = Path(os.path.abspath(path))
    for length in range(1, len(absolute.relative_to(root).parts) + 1):
        current = root.joinpath(*absolute.relative_to(root).parts[:length])
        if current.exists() and not current.is_dir():
            raise Refusal(
                "unsafe_path",
                f"path component is not a directory: {relative(root, current)}",
                "Make the named path component a directory.",
                (relative(root, current),),
            )


def reject_symlink_tree(root: Path, directory: Path) -> None:
    require_directory_components(root, directory)
    if directory.is_symlink() or not directory.is_dir():
        path = relative(root, directory) if directory.exists() or directory.is_symlink() else str(directory)
        raise Refusal(
            "unsafe_path",
            f"record is not a real directory: {path}",
            "Make the named record path a real directory.",
            (path,),
        )
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise Refusal(
                "unsafe_path",
                f"symlink is not allowed: {relative(root, path)}",
                "Remove the named symlink from the record tree.",
                (relative(root, path),),
            )


def version_from_text(text: str) -> int | None:
    rows = VERSION_ROW.findall(text)
    if len(rows) != 1:
        return None
    try:
        return int(rows[0].strip())
    except ValueError:
        return None


def single_row_value(text: str, pattern: re.Pattern[str]) -> str | None:
    rows = pattern.findall(text)
    if len(rows) != 1:
        return None
    return rows[0].strip()


def validate_ticket_records(root: Path, directory: Path) -> None:
    """Hold v3 tickets to the closed status enum and the disposition rule (D-012).

    Grandfathered records (version < VALIDATED_VERSION) never reach this function.
    """
    tickets_directory = directory / "tickets"
    if not tickets_directory.is_dir():
        return
    for path in sorted(tickets_directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        rel = relative(root, path)
        status = single_row_value(text, TICKET_STATUS_ROW)
        if status not in TICKET_STATUSES:
            raise Refusal(
                "invalid_ticket_status",
                f"ticket status must be one of open, active, closed: {rel} has status {status!r}",
                "Set the named ticket status to open, active, or closed.",
                (rel,),
                VALIDATED_VERSION,
            )
        disposition = single_row_value(text, TICKET_DISPOSITION_ROW)
        if status == "closed":
            if disposition not in TICKET_DISPOSITIONS:
                raise Refusal(
                    "invalid_ticket_disposition",
                    "closed ticket requires a disposition of resolved, superseded, out-of-scope, "
                    f"or hard-stop: {rel} has disposition {disposition!r}",
                    "Set the named closed ticket disposition to resolved, superseded, out-of-scope, or hard-stop.",
                    (rel,),
                    VALIDATED_VERSION,
                )
        elif disposition is not None:
            raise Refusal(
                "invalid_ticket_disposition",
                f"disposition is only allowed when status is closed: {rel} has status {status!r} "
                f"and disposition {disposition!r}",
                "Remove disposition from the named ticket, or set its status to closed.",
                (rel,),
                VALIDATED_VERSION,
            )


def newest_ticket_mutation(directory: Path) -> dict[Path, float]:
    tickets_directory = directory / "tickets"
    if not tickets_directory.is_dir():
        return {}
    return {path: path.stat().st_mtime for path in sorted(tickets_directory.glob("*.md"))}


def staleness(root: Path, directory: Path, previous_stamp: str | None) -> dict[str, object] | None:
    """Compare the stamp left by the previous `refresh` against ticket file mtimes.

    Returns None when the record is not known to be stale (including the first-ever refresh,
    where there is nothing yet to compare the stamp against).
    """
    if previous_stamp is None:
        return None
    try:
        previous = datetime.fromisoformat(previous_stamp)
    except ValueError:
        return None
    newer = [
        relative(root, path)
        for path, mtime in sorted(newest_ticket_mutation(directory).items())
        if datetime.fromtimestamp(mtime, tz=timezone.utc) > previous
    ]
    if not newer:
        return None
    return {"stamped_at": previous_stamp, "newer_ticket_files": newer}


def authored_region(text: str) -> str:
    """Drop the machine-owned parts, which the agent is not free to trim."""
    start = text.find(START)
    if start != -1:
        end = text.find(END, start)
        tail = "" if end == -1 else text[end + len(END) :]
        text = text[:start] + tail
    return REFRESHED_MARKER.sub("", text)


def record_size(text: str) -> dict[str, object]:
    """Measure the record against its budget. Reported, never enforced.

    Characters are a proxy for the reread cost every re-orientation pays; the sections are reported so the
    reader can see where the weight sits, and the standing-order count because that list grows by
    append. This function makes no judgement about what should move.
    """
    authored = authored_region(text)
    sections: dict[str, int] = {}
    standing_orders: int | None = None
    headings = list(SECTION_HEADING.finditer(authored))
    for position, heading in enumerate(headings):
        end = headings[position + 1].start() if position + 1 < len(headings) else len(authored)
        body = authored[heading.start() : end]
        name = heading.group(1)
        sections[name] = len(body)
        if name == STANDING_ORDERS_HEADING:
            standing_orders = len(STANDING_ORDER_ENTRY.findall(body))
    result: dict[str, object] = {
        "authored_chars": len(authored),
        "budget": AUTHORED_BUDGET,
        "over_budget": len(authored) > AUTHORED_BUDGET,
        "sections": sections,
        "standing_orders": standing_orders,
    }
    if len(authored) > AUTHORED_BUDGET:
        overage = len(authored) - AUTHORED_BUDGET
        result["repair"] = f"Remove at least {overage} authored characters from the index."
    return result


def sections(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    headings = list(SECTION_HEADING.finditer(text))
    for position, heading in enumerate(headings):
        end = headings[position + 1].start() if position + 1 < len(headings) else len(text)
        result[heading.group(1)] = text[heading.end() : end]
    return result


def lint_frozen_state(text: str) -> list[dict[str, str]]:
    """Name state written where only a live judgement belongs.

    `Current` and `Next` are reread on every re-orientation and are the two sections that go silently
    wrong: a SHA copied into them still reads as correct long after it stops being true. The
    receipts belong to the gate artifact that produced them, so this reports the token and the
    section and stops there — it never edits, and `refresh` never refuses on it.
    """
    findings: list[dict[str, str]] = []
    body = sections(authored_region(text))
    for name in LINTED_SECTIONS:
        content = HTML_COMMENT.sub("", body.get(name, ""))
        for rule, pattern in FROZEN_STATE_RULES:
            for match in dict.fromkeys(pattern.findall(content)):
                findings.append(
                    {
                        "section": name,
                        "rule": rule,
                        "match": match,
                        "repair": f"Remove {match} from {name}.",
                    }
                )

    envelope = HTML_COMMENT.sub("", body.get("Envelope", "")).strip()
    if not envelope:
        findings.append(
            {
                "section": "Envelope",
                "rule": "blank",
                "repair": "Add non-comment text to Envelope.",
            }
        )

    standing_orders = HTML_COMMENT.sub("", body.get(STANDING_ORDERS_HEADING, ""))
    for entry in STANDING_ORDER_BLOCK.findall(standing_orders):
        entry_heading = entry.splitlines()[0]
        if not STANDING_ORDER_DATE.search(entry):
            findings.append(
                {
                    "section": STANDING_ORDERS_HEADING,
                    "rule": "missing-date",
                    "entry": entry_heading,
                    "repair": "Add a YYYY-MM-DD date to the named standing-order entry.",
                }
            )
        if not STANDING_ORDER_LAPSE.search(entry):
            findings.append(
                {
                    "section": STANDING_ORDERS_HEADING,
                    "rule": "missing-lapse",
                    "entry": entry_heading,
                    "repair": "Add an indented non-empty Lapses: line to the named standing-order entry.",
                }
            )
        if not STANDING_ORDER_QUOTE.search(entry):
            rule = (
                "quote-not-one-line"
                if STANDING_ORDER_QUOTE_START.match(entry_heading) and "」" not in entry_heading
                else "missing-verbatim-quote"
            )
            findings.append(
                {
                    "section": STANDING_ORDERS_HEADING,
                    "rule": rule,
                    "entry": entry_heading,
                    "repair": "Put a 「...」 quote on the standing-order entry's first line.",
                }
            )
    return findings


def set_refreshed_marker(text: str, value: str, separator: str) -> str:
    marker = f"<!-- task-record:refreshed-at:{value} -->"
    if REFRESHED_MARKER.search(text):
        return REFRESHED_MARKER.sub(lambda _match: marker, text, count=1)
    if START in text:
        index = text.index(START)
        return text[:index] + marker + separator + text[index:]
    # No generated block to sit above: the stamp still has to land, because staleness is measured
    # against it and a record that never stamps can never report itself stale.
    tail = "" if text.endswith(separator) else separator
    return text + tail + marker + separator


def load_for_refresh(root: Path, task_id: str) -> RefreshRecord:
    directory = state_dir(root, "plans", task_id)
    if not directory.exists():
        raise Refusal(
            "record_missing",
            f"record not found: {task_id}",
            "Provide the requested record under active plans.",
        )
    reject_symlink_tree(root, directory)
    index = directory / "INDEX.md"
    if not index.is_file() or index.is_symlink():
        raise Refusal(
            "malformed_index",
            "INDEX.md is missing",
            "Provide a regular index file at the named path.",
            (relative(root, index),),
        )
    try:
        text = index.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise Refusal(
            "malformed_index",
            "INDEX.md is not readable UTF-8",
            "Encode the named index file as readable UTF-8.",
            (relative(root, index),),
        ) from exc

    # The version boundary is deliberately checked before the generated-block markers.
    version = version_from_text(text)
    if version not in SUPPORTED_VERSIONS:
        detail = "missing" if version is None else repr(version)
        raise Refusal(
            "unsupported_record_version",
            f"unsupported record_version: {detail}",
            f"Set record_version to {' or '.join(str(item) for item in SUPPORTED_VERSIONS)}.",
            (relative(root, index),),
            version,
        )
    # Current records carry no generated files block, and nothing regenerates one — the filesystem
    # under `artifacts/` is the record's inventory. A record that still has a block is kept
    # in step rather than rewritten out from under its reader, so zero markers and one matched pair
    # are both well formed — only a broken pair is not.
    if text.count(START) != text.count(END) or text.count(START) > 1:
        raise Refusal(
            "malformed_index",
            "missing or repeated files marker",
            "Leave either no files markers or one matched start/end pair.",
            (relative(root, index),),
            version,
        )
    if text.count(START) == 1 and text.index(START) > text.index(END):
        raise Refusal(
            "malformed_index",
            "files markers are out of order",
            "Place the files start marker before the files end marker.",
            (relative(root, index),),
            version,
        )
    return RefreshRecord(directory, index, text, version)


def collision_paths(root: Path, location: str, task_id: str) -> tuple[Path, ...]:
    parent = root / ".agent_state" / location
    require_directory_components(root, parent)
    if not parent.is_dir():
        return ()
    return tuple(sorted((entry for entry in parent.iterdir() if entry.name.casefold() == task_id.casefold()), key=lambda path: path.name))


def command_create(root: Path, arguments: argparse.Namespace) -> None:
    validate_task_id(arguments.task_id)
    if not arguments.goal.strip() or "\x00" in arguments.goal:
        raise Refusal(
            "invalid_argument",
            "goal must be non-empty text",
            "Pass non-empty --goal text without NUL characters.",
        )
    collisions = tuple(
        path
        for location in ("plans", "archives")
        for path in collision_paths(root, location, arguments.task_id)
    )
    if collisions:
        raise Refusal(
            "record_exists",
            f"active or archived record already exists: {arguments.task_id}",
            "Choose a task id with no case-insensitive active or archived collision.",
            tuple(relative(root, path) for path in collisions),
        )

    plans = root / ".agent_state" / "plans"
    require_directory_components(root, plans)
    plans.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{arguments.task_id}.", dir=plans))
    temporary = staging / arguments.task_id
    destination = plans / arguments.task_id
    try:
        (temporary / "tickets").mkdir(parents=True)
        initial = template("INDEX.md").replace("{{TASK_ID}}", arguments.task_id).replace(
            "{{GOAL}}", arguments.goal
        )
        atomic_write(temporary / "INDEX.md", initial)
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            for path in sorted(temporary.rglob("*"), reverse=True):
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            temporary.rmdir()
        staging.rmdir()
    emit(
        "create",
        ok=True,
        version=CURRENT_VERSION,
        task_id=arguments.task_id,
        paths=[relative(root, destination / "INDEX.md"), relative(root, destination / "tickets")],
    )


def command_refresh(root: Path, arguments: argparse.Namespace) -> None:
    validate_task_id(arguments.task_id)
    record = load_for_refresh(root, arguments.task_id)

    stale: dict[str, object] | None = None
    if record.version == VALIDATED_VERSION:
        validate_ticket_records(root, record.directory)
        previous_stamp = single_row_value(record.text, REFRESHED_MARKER)
        stale = staleness(root, record.directory, previous_stamp)

    updated = record.text
    separator = "\r\n" if "\r\n" in record.text else "\n"
    if START in record.text:
        # The current format drops the generated block rather than maintaining it. A projection in
        # the file is one more thing that can be read after it stops being true, and nothing takes
        # its place: `locate` reports the frontier, not the contents. Removal happens here so
        # existing records migrate the first time they refresh.
        start = record.text.index(START)
        end = record.text.index(END, start) + len(END)
        head = record.text[:start].rstrip("\r\n")
        tail = record.text[end:].lstrip("\r\n")
        updated = head + separator + tail

    if record.version == VALIDATED_VERSION:
        now = datetime.now(timezone.utc).isoformat()
        updated = set_refreshed_marker(updated, now, separator)

    if updated != record.text:
        atomic_write(record.index, updated)

    extra: dict[str, object] = {}
    if record.version == VALIDATED_VERSION:
        extra["stale"] = stale
        extra["size"] = record_size(updated)
        extra["lint"] = lint_frozen_state(updated)
    emit(
        "refresh",
        ok=True,
        version=record.version,
        task_id=arguments.task_id,
        paths=[relative(root, record.index)],
        **extra,
    )


def ticket_frontier(root: Path, directory: Path) -> dict[str, object]:
    """Read ticket state straight from the headers, which are the only authority for it.

    Closed tickets are counted, not listed. The frontier is what the reader acts on next; a
    finished ticket's path bears on no current decision, and on a long-lived record the closed
    list was most of what this command printed.
    """
    tickets_directory = directory / "tickets"
    grouped: dict[str, list[str]] = {"active": [], "open": []}
    closed = 0
    if tickets_directory.is_dir():
        for path in sorted(tickets_directory.glob("*.md")):
            status = single_row_value(path.read_text(encoding="utf-8"), TICKET_STATUS_ROW)
            if status == "closed":
                closed += 1
            else:
                grouped.setdefault(status or "unreadable", []).append(relative(root, path))
    return {**grouped, "closed_count": closed}


def command_locate(root: Path, arguments: argparse.Namespace) -> None:
    """Locate the reader. Derived at read time, dev-flow's own data only.

    This says where to look, never what happened: everything here is recomputed from the record on
    each call, so there is nothing that can go quietly out of date. The two commands below are
    printed as literal strings rather than run — orchestrate and candidate-backlog own their own
    answers, and a repo without them should be missing a section, not broken.
    """
    validate_task_id(arguments.task_id)
    record = load_for_refresh(root, arguments.task_id)
    body: dict[str, object] = {
        "task_id": arguments.task_id,
        "read": [relative(root, record.index)],
        "tickets": ticket_frontier(root, record.directory),
    }
    if record.version == VALIDATED_VERSION:
        previous_stamp = single_row_value(record.text, REFRESHED_MARKER)
        body["stale"] = staleness(root, record.directory, previous_stamp)
        body["size"] = record_size(record.text)
        body["lint"] = lint_frozen_state(record.text)
    body["then_run"] = [
        f"orchestrate.py status --task-id {arguments.task_id}",
        "backlog.py list --status inbox",
    ]
    emit("locate", ok=True, version=record.version, **body)


def command_move(root: Path, arguments: argparse.Namespace, operation: str) -> None:
    validate_task_id(arguments.task_id)
    undo = bool(getattr(arguments, "undo", False))
    source_location, destination_location = (
        ("archives", "plans") if undo else ("plans", "archives")
    )
    source = state_dir(root, source_location, arguments.task_id)
    destination = state_dir(root, destination_location, arguments.task_id)
    require_directory_components(root, source.parent)
    require_directory_components(root, destination.parent)
    reject_symlink_components(root, source)
    reject_symlink_components(root, destination)
    if not source.exists():
        raise Refusal(
            "record_missing",
            f"source record not found: {arguments.task_id}",
            f"Provide the requested source record under {source_location}.",
        )
    reject_symlink_tree(root, source)
    collisions = collision_paths(root, destination_location, arguments.task_id)
    if collisions:
        raise Refusal(
            "record_exists",
            f"destination record already exists: {arguments.task_id}",
            "Use a task id with no case-insensitive destination collision.",
            tuple(relative(root, path) for path in collisions),
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    require_directory_components(root, destination.parent)
    if source.parent.stat().st_dev != destination.parent.stat().st_dev:
        raise Refusal(
            "cross_device",
            "source and destination are on different filesystems",
            "Keep source and destination record directories on the same filesystem.",
        )
    try:
        os.rename(source, destination)
    except OSError as exc:
        raise Refusal(
            "cross_device",
            f"atomic directory rename refused: {exc}",
            "Make the source-to-destination directory rename atomic on one filesystem.",
        ) from exc
    emit(
        operation,
        ok=True,
        version=None,
        task_id=arguments.task_id,
        undo=undo,
        paths=[relative(root, destination)],
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="operation", required=True)
    create = commands.add_parser("create")
    create.add_argument("task_id")
    create.add_argument("--goal", required=True)
    for name in ("refresh", "archive", "locate"):
        command = commands.add_parser(name)
        command.add_argument("task_id")
        if name == "archive":
            command.add_argument(
                "--undo",
                action="store_true",
                help="move the record back from archives to plans",
            )
    return result


def main() -> None:
    arguments = parser().parse_args()
    root = Path.cwd().resolve()
    try:
        if arguments.operation == "create":
            command_create(root, arguments)
        elif arguments.operation == "refresh":
            command_refresh(root, arguments)
        elif arguments.operation == "locate":
            command_locate(root, arguments)
        else:
            command_move(root, arguments, arguments.operation)
    except Refusal as refusal:
        fail(arguments.operation, refusal)


if __name__ == "__main__":
    main()
