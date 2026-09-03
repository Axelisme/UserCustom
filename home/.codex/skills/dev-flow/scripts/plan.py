#!/usr/bin/env python3
"""Durable task-container lifecycle and orientation command line interface."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import NoReturn

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
INDEX_FIELDS = ("task_id", "spec")
TICKET_FIELDS = ("id", "state")
TICKET_STATES = ("drafted", "pending", "cutoff", "closed")
FRONTMATTER_MAX_BYTES = 16 * 1024
TICKET_FILE = "ticket.md"


class Refusal(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        repair: str,
        paths: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.repair = repair
        self.paths = tuple(sorted(paths))


def emit(operation: str, *, ok: bool, **values: object) -> None:
    body: dict[str, object] = {
        "ok": ok,
        "operation": operation,
    }
    body.update(values)
    print(json.dumps(body, ensure_ascii=True, separators=(",", ":")))


def fail(operation: str, refusal: Refusal, *, control_root: str | None = None, start_path: str | None = None) -> NoReturn:
    body: dict[str, object] = {
        "ok": False,
        "operation": operation,
        "error": {
            "code": refusal.code,
            "message": refusal.message,
            "paths": list(refusal.paths),
            "repair": refusal.repair,
        },
    }
    if control_root is not None:
        body["control_root"] = control_root
    if start_path is not None:
        body["start_path"] = start_path
    # Also include start_path inside error for compatibility if test expects it there?
    # But spec says repository_not_found with start_path; include at top-level.
    print(json.dumps(body, ensure_ascii=True, separators=(",", ":")))
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


def copy_task_template(container: Path, task_id: str) -> list[str]:
    """Materialize templates/task/ into a staged container.

    The template directory is the single source of the container's shape: its directories are
    the frame every task gets, and `.gitkeep` exists only so git carries the empty ones here.
    Only the task id is substituted, because `locate` refuses an INDEX whose `task_id` does not
    equal its container; every other section stays a placeholder the Orchestrator authors.
    """
    source = Path(__file__).resolve().parent.parent / "templates" / "task"
    scaffolded: list[str] = []
    for path in sorted(source.rglob("*")):
        relative_path = path.relative_to(source)
        if path.name == ".gitkeep":
            continue
        target = container / relative_path
        if path.is_dir():
            target.mkdir(parents=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, path.read_text(encoding="utf-8").replace("{{TASK_ID}}", task_id))
        scaffolded.append(relative_path.as_posix())
    return scaffolded


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


def require_directory_components(root: Path, path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    try:
        parts = absolute.relative_to(root).parts
    except ValueError as exc:
        raise Refusal(
            "unsafe_path",
            f"path escapes repository: {path}",
            "Use a path contained by the repository root.",
        ) from exc
    for length in range(1, len(parts) + 1):
        current = root.joinpath(*parts[:length])
        current_path = relative(root, current)
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise Refusal(
                "unsafe_path",
                f"path component cannot be inspected: {current_path}",
                "Make the named path component accessible and a real directory.",
                (current_path,),
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise Refusal(
                "unsafe_path",
                f"symlink is not allowed: {current_path}",
                "Replace the named symlink with a real path component.",
                (current_path,),
            )
        if not stat.S_ISDIR(metadata.st_mode):
            raise Refusal(
                "unsafe_path",
                f"path component is not a directory: {current_path}",
                "Make the named path component a directory.",
                (current_path,),
            )
    return True


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


def collision_paths(root: Path, location: str, task_id: str) -> tuple[Path, ...]:
    parent = root / ".agent_state" / location
    require_directory_components(root, parent)
    if not parent.is_dir():
        return ()
    return tuple(
        sorted(
            (entry for entry in parent.iterdir() if entry.name.casefold() == task_id.casefold()),
            key=lambda path: path.name,
        )
    )


def resolve_control_root(arguments: argparse.Namespace) -> Path:
    """Select the repository control root per S1/S2.

    - When --repo is present, resolve that path directly without Git discovery.
    - When absent, use `git rev-parse --show-toplevel` from CWD.
    Raises Refusal with repository_not_found (including start_path) or invalid_argument.
    """
    cwd = Path.cwd()
    repo_arg: str | None = getattr(arguments, "repo", None)
    if repo_arg is not None:
        raw = repo_arg
        # Expand ~ and resolve against cwd
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        # Resolve to canonical absolute (strict=False)
        try:
            candidate = candidate.resolve()
        except OSError as exc:
            raise Refusal(
                "invalid_argument",
                f"--repo path cannot be resolved: {raw}: {exc}",
                "Provide an existing directory for --repo.",
                (raw,),
            ) from exc
        # Require accessible directory
        try:
            st = candidate.stat()
        except FileNotFoundError as exc:
            raise Refusal(
                "invalid_argument",
                f"--repo path does not exist: {raw}",
                "Provide an existing directory for --repo.",
                (raw,),
            ) from exc
        except OSError as exc:
            raise Refusal(
                "invalid_argument",
                f"--repo path cannot be accessed: {raw}: {exc}",
                "Provide an existing directory for --repo.",
                (raw,),
            ) from exc
        if not stat.S_ISDIR(st.st_mode):
            raise Refusal(
                "invalid_argument",
                f"--repo path is not a directory: {raw}",
                "Provide an existing directory for --repo.",
                (raw,),
            )
        # Verify the directory is effectively accessible for the current process.
        # Use os.access with effective IDs so POSIX ACLs and other extended
        # permissions are honored, rather than reconstructing DAC from
        # owner/group/other mode bits which would reject an ACL-granted
        # directory (e.g., mode 000 with ACL r-x for the caller).
        # Real stat/type checks above and enumeration via scandir below are retained.
        try:
            has_effective_access = os.access(candidate, os.R_OK | os.X_OK, effective_ids=True)
        except TypeError:
            # Fallback for platforms lacking effective_ids (not expected in lane)
            has_effective_access = os.access(candidate, os.R_OK | os.X_OK)
        if not has_effective_access:
            raise Refusal(
                "invalid_argument",
                f"--repo path is not accessible: {raw}",
                "Provide an existing directory for --repo.",
                (raw,),
            )
        try:
            with os.scandir(candidate):
                pass
        except OSError as exc:
            raise Refusal(
                "invalid_argument",
                f"--repo path is not accessible: {raw}: {exc}",
                "Provide an existing directory for --repo.",
                (raw,),
            ) from exc
        # Also ensure it's a real directory (not symlink? allow symlink to directory? Followed stat already, but if symlink to file would not be dir)
        # If candidate is symlink to directory, stat follows and says dir, but we may want to allow it. The spec says use directly, so allow.
        return candidate
    # No explicit --repo: discover via git
    # Use the authorized git executable; fall back to "git" in PATH
    git_bin = "/usr/bin/git"
    if not Path(git_bin).exists():
        git_bin = "git"
    result = subprocess.run(
        [git_bin, "rev-parse", "--show-toplevel"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        start_path = str(cwd.resolve())
        # Raise with repository_not_found; caller will handle start_path
        err = Refusal(
            "repository_not_found",
            f"not inside a Git worktree: {start_path}",
            "Run inside a Git repository or provide --repo PATH.",
        )
        # Attach start_path for caller to emit
        err.start_path = start_path  # type: ignore[attr-defined]
        raise err
    root_str = result.stdout.strip()
    if not root_str:
        start_path = str(cwd.resolve())
        err = Refusal(
            "repository_not_found",
            f"Git discovery returned empty result from {start_path}",
            "Run inside a Git repository or provide --repo PATH.",
        )
        err.start_path = start_path  # type: ignore[attr-defined]
        raise err
    return Path(root_str).resolve()


def command_create(root: Path, arguments: argparse.Namespace, *, control_root: str) -> None:
    validate_task_id(arguments.task_id)
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
        scaffolded = copy_task_template(temporary, arguments.task_id)
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
        control_root=control_root,
        task_id=arguments.task_id,
        paths=[relative(root, destination / entry) for entry in scaffolded],
    )


def _scalar_suffix_is_comment(suffix: str) -> bool:
    return not suffix or (suffix[0].isspace() and suffix.lstrip().startswith("#"))


def _flat_yaml_scalar(source: str) -> str:
    value = source.strip()
    if not value:
        raise ValueError("frontmatter contains an empty scalar")
    if value.startswith('"'):
        try:
            decoded, end = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError as exc:
            raise ValueError("frontmatter contains an invalid quoted scalar") from exc
        if not isinstance(decoded, str) or not decoded or not _scalar_suffix_is_comment(value[end:]):
            raise ValueError("frontmatter contains an invalid quoted scalar")
        return decoded
    if value.startswith("'"):
        decoded: list[str] = []
        index = 1
        while index < len(value):
            if value[index] != "'":
                decoded.append(value[index])
                index += 1
                continue
            if index + 1 < len(value) and value[index + 1] == "'":
                decoded.append("'")
                index += 2
                continue
            if not decoded or not _scalar_suffix_is_comment(value[index + 1 :]):
                raise ValueError("frontmatter contains an invalid quoted scalar")
            return "".join(decoded)
        raise ValueError("frontmatter contains an invalid quoted scalar")

    for index, character in enumerate(value):
        if character == "#" and index > 0 and value[index - 1].isspace():
            value = value[:index].rstrip()
            break
    if not value:
        raise ValueError("frontmatter contains an empty scalar")
    if (
        value[0] in "-?:,[]{}#&*!|>'\"%@`"
        or value in {"~", "null", "Null", "NULL"}
        or re.search(r":\s", value)
    ):
        raise ValueError("frontmatter contains an unsupported scalar")
    return value


def _plain_yaml_frontmatter(text: str, expected_fields: tuple[str, ...]) -> dict[str, str]:
    """Read the owned flat-scalar YAML subset.

    This remains a standard-library parser because the repository has no Python dependency
    manifest and setup does not install PyYAML. Unsupported YAML is rejected as unavailable.
    """
    normalized = text.replace("\r\n", "\n")
    lines = normalized.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("frontmatter opening delimiter is missing")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("frontmatter closing delimiter is missing") from exc
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line != line.lstrip() or ":" not in line:
            raise ValueError("frontmatter contains an unsupported entry")
        key, source = line.split(":", 1)
        if key != key.strip() or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            raise ValueError("frontmatter contains an unsupported key")
        if key in values:
            raise ValueError("frontmatter contains a duplicate field")
        values[key] = _flat_yaml_scalar(source)
    if set(values) != set(expected_fields):
        raise ValueError(f"frontmatter fields must be exactly {', '.join(expected_fields)}")
    return values


def _read_yaml_frontmatter(path: Path, expected_fields: tuple[str, ...]) -> dict[str, str]:
    """Read only the bounded UTF-8 frontmatter; the narrative body remains opaque bytes."""
    chunks: list[bytes] = []
    remaining = FRONTMATTER_MAX_BYTES
    with path.open("rb") as stream:
        while True:
            line = stream.readline(remaining + 1)
            if not line:
                raise ValueError("frontmatter closing delimiter is missing")
            if len(line) > remaining:
                raise ValueError("frontmatter exceeds the byte limit")
            chunks.append(line)
            remaining -= len(line)
            if len(chunks) > 1 and line.rstrip(b"\r\n") == b"---":
                return _plain_yaml_frontmatter(b"".join(chunks).decode("utf-8"), expected_fields)


def _read_index(directory: Path) -> tuple[str | None, str | None, dict[str, object] | None]:
    index = directory / "INDEX.md"
    if index.is_symlink() or not index.is_file():
        return None, None, {"code": "index_frontmatter_unavailable", "message": "INDEX.md is not a regular file"}
    try:
        values = _read_yaml_frontmatter(index, INDEX_FIELDS)
    except (OSError, UnicodeError, ValueError) as exc:
        return None, None, {"code": "index_frontmatter_unavailable", "message": str(exc)}
    if not SAFE_ID.fullmatch(values["task_id"]) or not values["task_id"].isascii():
        return None, None, {
            "code": "index_frontmatter_unavailable",
            "message": "task id is invalid",
        }
    if values["task_id"] != directory.name:
        return None, None, {
            "code": "index_frontmatter_unavailable",
            "message": "task id does not match its container",
        }
    return values["task_id"], values["spec"], None


def _empty_ticket_counts(*, unknown: bool = False) -> dict[str, int | None]:
    value = None if unknown else 0
    counts: dict[str, int | None] = dict.fromkeys(TICKET_STATES, value)
    counts["total"] = value
    counts["unreadable"] = 0
    return counts


def _unavailable_ticket_counts(
    code: str, unreadable: int | None
) -> tuple[dict[str, int | None], dict[str, object]]:
    error: dict[str, object] = {"code": code}
    if unreadable is not None:
        error["count"] = unreadable
    counts: dict[str, int | None] = dict.fromkeys(TICKET_STATES, None)
    counts["total"] = None
    counts["unreadable"] = unreadable
    return counts, error


def _ticket_counts(directory: Path) -> tuple[dict[str, int | None], dict[str, object] | None]:
    tickets = directory / "tickets"
    try:
        metadata = tickets.lstat()
    except FileNotFoundError:
        return _empty_ticket_counts(), None
    except OSError:
        return _unavailable_ticket_counts("ticket_directory_unreadable", None)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return _unavailable_ticket_counts("ticket_headers_unreadable", 1)

    try:
        with os.scandir(tickets) as entries:
            directories = sorted(
                (Path(entry.path) for entry in entries if not entry.name.startswith(".")),
                key=lambda path: path.name,
            )
    except OSError:
        return _unavailable_ticket_counts("ticket_directory_unreadable", None)

    counted = dict.fromkeys(TICKET_STATES, 0)
    unreadable = 0
    for owner in directories:
        path = owner / TICKET_FILE
        try:
            if owner.is_symlink() or not owner.is_dir():
                raise ValueError("ticket is not a real directory")
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"{TICKET_FILE} is not a regular file")
            values = _read_yaml_frontmatter(path, TICKET_FIELDS)
            if not SAFE_ID.fullmatch(values["id"]) or not values["id"].isascii():
                raise ValueError("ticket id is invalid")
            if values["id"] != owner.name:
                raise ValueError("ticket id does not match its directory")
            if values["state"] not in TICKET_STATES:
                raise ValueError(f"ticket state is not one of {', '.join(TICKET_STATES)}")
        except (OSError, UnicodeError, ValueError):
            unreadable += 1
            continue
        counted[values["state"]] += 1
    if unreadable:
        return _unavailable_ticket_counts("ticket_headers_unreadable", unreadable)
    counts: dict[str, int | None] = dict(counted)
    counts["total"] = sum(counted.values())
    counts["unreadable"] = 0
    return counts, None


def command_list(root: Path, _arguments: argparse.Namespace, *, control_root: str) -> None:
    """List narrow references to active containers without reading their contents."""
    plans = root / ".agent_state" / "plans"
    if not require_directory_components(root, plans):
        emit("list", ok=True, control_root=control_root, location="active", records=[])
        return

    unsafe: list[str] = []
    records: list[dict[str, str]] = []
    try:
        with os.scandir(plans) as entries:
            for entry in entries:
                path = Path(entry.path)
                entry_path = relative(root, path)
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError:
                    unsafe.append(entry_path)
                    continue
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or not stat.S_ISDIR(metadata.st_mode)
                    or not SAFE_ID.fullmatch(entry.name)
                    or not entry.name.isascii()
                ):
                    unsafe.append(entry_path)
                    continue
                records.append(
                    {
                        "lookup_id": entry.name,
                        "container": entry_path,
                        "index": relative(root, path / "INDEX.md"),
                    }
                )
    except OSError as exc:
        plans_path = relative(root, plans)
        raise Refusal(
            "unsafe_path",
            f"active plans directory cannot be read: {plans_path}",
            "Make the active plans directory a readable real directory.",
            (plans_path,),
        ) from exc

    if unsafe:
        raise Refusal(
            "unsafe_path",
            "active plans contains unsafe entries",
            "Make every immediate entry a real directory with an ASCII SAFE_ID name.",
            tuple(unsafe),
        )
    records.sort(key=lambda record: (record["lookup_id"].casefold(), record["lookup_id"]))
    emit("list", ok=True, control_root=control_root, location="active", records=records)


def command_locate(root: Path, arguments: argparse.Namespace, *, control_root: str) -> None:
    """Resolve a container and expose only its narrow frontmatter orientation."""
    validate_task_id(arguments.task_id)
    matches = [
        ("active" if location == "plans" else "archived", path)
        for location in ("plans", "archives")
        for path in collision_paths(root, location, arguments.task_id)
    ]
    if not matches:
        expected = state_dir(root, "plans", arguments.task_id)
        emit(
            "locate",
            ok=True,
            control_root=control_root,
            location="missing",
            container=relative(root, expected),
            index=relative(root, expected / "INDEX.md"),
            task_id=None,
            spec=None,
            tickets=_empty_ticket_counts(unknown=True),
            orientation="unavailable",
            parse_errors=[],
        )
        return
    if len(matches) > 1:
        candidates = [
            {
                "location": location,
                "container": relative(root, path),
                "index": relative(root, path / "INDEX.md"),
            }
            for location, path in matches
        ]
        emit(
            "locate",
            ok=True,
            control_root=control_root,
            location="ambiguous",
            container=None,
            index=None,
            candidates=candidates,
            task_id=None,
            spec=None,
            tickets=_empty_ticket_counts(unknown=True),
            orientation="unavailable",
            parse_errors=[],
        )
        return

    location, directory = matches[0]
    require_directory_components(root, directory)
    if directory.is_symlink() or not directory.is_dir():
        raise Refusal(
            "unsafe_path",
            f"record is not a real directory: {relative(root, directory)}",
            "Make the named record path a real directory.",
            (relative(root, directory),),
        )
    task_id, spec, index_error = _read_index(directory)
    tickets, ticket_error = _ticket_counts(directory)
    errors = [error for error in (index_error, ticket_error) if error is not None]
    orientation = "unavailable" if index_error else "partial" if ticket_error else "available"
    emit(
        "locate",
        ok=True,
        control_root=control_root,
        location=location,
        container=relative(root, directory),
        index=relative(root, directory / "INDEX.md"),
        task_id=task_id,
        spec=spec,
        tickets=tickets,
        orientation=orientation,
        parse_errors=errors,
    )


def command_move(root: Path, arguments: argparse.Namespace, operation: str, *, control_root: str) -> None:
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
        control_root=control_root,
        task_id=arguments.task_id,
        undo=undo,
        paths=[relative(root, destination)],
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--repo",
        dest="repo",
        metavar="PATH",
        help="explicit repository root directory",
    )
    commands = result.add_subparsers(dest="operation", required=True)
    create = commands.add_parser("create")
    create.add_argument("task_id")
    archive = commands.add_parser("archive")
    archive.add_argument("task_id")
    archive.add_argument(
        "--undo",
        action="store_true",
        help="move the record back from archives to plans",
    )
    commands.add_parser("list")
    locate = commands.add_parser("locate")
    locate.add_argument("task_id")
    return result


def main(argv: list[str] | None = None) -> None:
    """Route one parsed operation against the working directory; a refusal exits non-zero."""
    arguments = parser().parse_args(argv)
    # Root selection precedes any task operation
    try:
        root = resolve_control_root(arguments)
    except Refusal as refusal:
        if refusal.code == "repository_not_found":
            # Include start_path without control_root
            start_path = getattr(refusal, "start_path", str(Path.cwd().resolve()))  # type: ignore[attr-defined]
            fail(arguments.operation, refusal, start_path=start_path)
        else:
            # Explicit --repo invalid_argument: no control_root, no start_path
            fail(arguments.operation, refusal)
    control_root_str = str(root.resolve())
    try:
        if arguments.operation == "create":
            command_create(root, arguments, control_root=control_root_str)
        elif arguments.operation == "list":
            command_list(root, arguments, control_root=control_root_str)
        elif arguments.operation == "locate":
            command_locate(root, arguments, control_root=control_root_str)
        else:
            command_move(root, arguments, arguments.operation, control_root=control_root_str)
    except Refusal as refusal:
        fail(arguments.operation, refusal, control_root=control_root_str)


if __name__ == "__main__":
    main()
