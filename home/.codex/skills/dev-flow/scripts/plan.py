#!/usr/bin/env python3
"""Workflow-neutral durable task-record v2 command line kernel."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

CURRENT_VERSION = 2
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
VERSION_ROW = re.compile(r"^\|\s*record_version\s*\|\s*([^|\r\n]*)\s*\|\s*$", re.MULTILINE)
START = "<!-- task-record:files:start -->"
END = "<!-- task-record:files:end -->"


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


def files_projection(directory: Path) -> str:
    entries = sorted(directory.rglob("*"), key=lambda path: path.relative_to(directory).parts)
    lines = []
    for path in entries:
        parts = path.relative_to(directory).parts
        suffix = "/" if path.is_dir() else ""
        lines.append(f"{'  ' * (len(parts) - 1)}{parts[-1]}{suffix}")
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
    if version != CURRENT_VERSION:
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
    start = record.text.index(START) + len(START)
    end = record.text.index(END, start)
    separator = "\r\n" if record.text[start:].startswith("\r\n") else "\n"
    projection = files_projection(record.directory).replace("\n", separator)
    updated = record.text[:start] + separator + projection + separator + record.text[end:]
    if updated != record.text:
        atomic_write(record.index, updated)
    emit(
        "refresh",
        ok=True,
        version=record.version,
        task_id=arguments.task_id,
        paths=[relative(root, record.index)],
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
