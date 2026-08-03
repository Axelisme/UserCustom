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
# never enter a ticket. See dev-flow/SKILL.md "Never create a second ticket store".
AUTHORED_BUDGET = 6000
SECTION_HEADING = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
STANDING_ORDERS_HEADING = "Standing orders"
STANDING_ORDER_ENTRY = re.compile(r"^- +\*\*", re.MULTILINE)
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
        paths: tuple[str, ...] = (),
        version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
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
        error={"code": refusal.code, "message": refusal.message, "paths": list(refusal.paths)},
    )
    raise SystemExit(1)


def relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def validate_task_id(value: str) -> None:
    if not SAFE_ID.fullmatch(value) or not value.isascii():
        raise Refusal("invalid_argument", f"invalid task id: {value!r}")


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
        raise Refusal("unsafe_path", f"path escapes repository: {path}") from exc
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise Refusal(
                "unsafe_path",
                f"symlink is not allowed: {relative(root, current)}",
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
                (relative(root, current),),
            )


def reject_symlink_tree(root: Path, directory: Path) -> None:
    require_directory_components(root, directory)
    if directory.is_symlink() or not directory.is_dir():
        path = relative(root, directory) if directory.exists() or directory.is_symlink() else str(directory)
        raise Refusal("unsafe_path", f"record is not a real directory: {path}", (path,))
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise Refusal(
                "unsafe_path",
                f"symlink is not allowed: {relative(root, path)}",
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
                    (rel,),
                    VALIDATED_VERSION,
                )
        elif disposition is not None:
            raise Refusal(
                "invalid_ticket_disposition",
                f"disposition is only allowed when status is closed: {rel} has status {status!r} "
                f"and disposition {disposition!r}",
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

    Characters are a proxy for the reread cost every resume pays; the sections are reported so the
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
    return {
        "authored_chars": len(authored),
        "budget": AUTHORED_BUDGET,
        "over_budget": len(authored) > AUTHORED_BUDGET,
        "sections": sections,
        "standing_orders": standing_orders,
    }


def set_refreshed_marker(text: str, value: str, separator: str) -> str:
    marker = f"<!-- task-record:refreshed-at:{value} -->"
    if REFRESHED_MARKER.search(text):
        return REFRESHED_MARKER.sub(lambda _match: marker, text, count=1)
    index = text.index(START)
    return text[:index] + marker + separator + text[index:]


def files_projection(directory: Path) -> str:
    lines: list[str] = []

    def regular_file_count(path: Path) -> int:
        return sum(descendant.is_file() for descendant in path.rglob("*"))

    def render(current: Path, depth: int) -> None:
        entries = sorted(current.iterdir(), key=lambda path: path.name)
        direct_files = [entry for entry in entries if entry.is_file()]
        displayed_files = set(direct_files[:10])
        omitted_files = len(direct_files) - len(displayed_files)

        for entry in entries:
            indent = "  " * (depth + 1)
            if entry.is_dir():
                lines.append(f"{indent}{entry.name}/")
                entry_depth = depth + 1
                if entry_depth >= 2:
                    hidden_files = regular_file_count(entry)
                    if hidden_files:
                        lines.append(f"{'  ' * (entry_depth + 1)}...{hidden_files} file")
                else:
                    render(entry, entry_depth)
            elif entry in displayed_files:
                lines.append(f"{indent}{entry.name}")

        if omitted_files:
            lines.append(f"{'  ' * (depth + 1)}...{omitted_files} file")

    render(directory, -1)
    return "\n".join(lines)


def load_for_refresh(root: Path, task_id: str) -> RefreshRecord:
    directory = state_dir(root, "plans", task_id)
    if not directory.exists():
        raise Refusal("record_missing", f"record not found: {task_id}")
    reject_symlink_tree(root, directory)
    index = directory / "INDEX.md"
    if not index.is_file() or index.is_symlink():
        raise Refusal("malformed_index", "INDEX.md is missing", (relative(root, index),))
    try:
        text = index.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise Refusal("malformed_index", "INDEX.md is not readable UTF-8", (relative(root, index),)) from exc

    # The version boundary is deliberately checked before the generated-block markers.
    version = version_from_text(text)
    if version not in SUPPORTED_VERSIONS:
        detail = "missing" if version is None else repr(version)
        raise Refusal(
            "unsupported_record_version",
            f"unsupported record_version: {detail}",
            (relative(root, index),),
            version,
        )
    if text.count(START) != 1 or text.count(END) != 1:
        raise Refusal("malformed_index", "missing or repeated files marker", (relative(root, index),), version)
    start = text.index(START)
    end = text.index(END)
    if start > end:
        raise Refusal("malformed_index", "files markers are out of order", (relative(root, index),), version)
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
        raise Refusal("invalid_argument", "goal must be non-empty text")
    collisions = tuple(
        path
        for location in ("plans", "archives")
        for path in collision_paths(root, location, arguments.task_id)
    )
    if collisions:
        raise Refusal(
            "record_exists",
            f"active or archived record already exists: {arguments.task_id}",
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

    start = record.text.index(START) + len(START)
    end = record.text.index(END, start)
    separator = "\r\n" if record.text[start:].startswith("\r\n") else "\n"
    projection = files_projection(record.directory).replace("\n", separator)
    updated = record.text[:start] + separator + projection + separator + record.text[end:]

    if record.version == VALIDATED_VERSION:
        now = datetime.now(timezone.utc).isoformat()
        updated = set_refreshed_marker(updated, now, separator)

    if updated != record.text:
        atomic_write(record.index, updated)

    extra: dict[str, object] = {}
    if record.version == VALIDATED_VERSION:
        extra["stale"] = stale
        extra["size"] = record_size(updated)
    emit(
        "refresh",
        ok=True,
        version=record.version,
        task_id=arguments.task_id,
        paths=[relative(root, record.index)],
        **extra,
    )


def command_move(root: Path, arguments: argparse.Namespace, operation: str) -> None:
    validate_task_id(arguments.task_id)
    source_location, destination_location = (
        ("plans", "archives") if operation == "archive" else ("archives", "plans")
    )
    source = state_dir(root, source_location, arguments.task_id)
    destination = state_dir(root, destination_location, arguments.task_id)
    require_directory_components(root, source.parent)
    require_directory_components(root, destination.parent)
    reject_symlink_components(root, source)
    reject_symlink_components(root, destination)
    if not source.exists():
        raise Refusal("record_missing", f"source record not found: {arguments.task_id}")
    reject_symlink_tree(root, source)
    collisions = collision_paths(root, destination_location, arguments.task_id)
    if collisions:
        raise Refusal(
            "record_exists",
            f"destination record already exists: {arguments.task_id}",
            tuple(relative(root, path) for path in collisions),
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    require_directory_components(root, destination.parent)
    if source.parent.stat().st_dev != destination.parent.stat().st_dev:
        raise Refusal("cross_device", "source and destination are on different filesystems")
    try:
        os.rename(source, destination)
    except OSError as exc:
        raise Refusal("cross_device", f"atomic directory rename refused: {exc}") from exc
    emit(operation, ok=True, version=None, task_id=arguments.task_id, paths=[relative(root, destination)])


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="operation", required=True)
    create = commands.add_parser("create")
    create.add_argument("task_id")
    create.add_argument("--goal", required=True)
    for name in ("refresh", "archive", "resume"):
        command = commands.add_parser(name)
        command.add_argument("task_id")
    return result


def main() -> None:
    arguments = parser().parse_args()
    root = Path.cwd().resolve()
    try:
        if arguments.operation == "create":
            command_create(root, arguments)
        elif arguments.operation == "refresh":
            command_refresh(root, arguments)
        else:
            command_move(root, arguments, arguments.operation)
    except Refusal as refusal:
        fail(arguments.operation, refusal)


if __name__ == "__main__":
    main()
