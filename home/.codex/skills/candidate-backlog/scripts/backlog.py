#!/usr/bin/env python3
"""Manage the repo-local candidate backlog using only the Python stdlib."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

BACKLOG_VERSION = 1

STATUSES = ("inbox", "planned", "resolved", "closed")
KINDS = (
    "defect",
    "missing-capability",
    "design-debt",
    "technical-debt",
    "test-gap",
    "documentation-gap",
    "workflow-friction",
    "observability-gap",
    "performance-opportunity",
    "product-idea",
)
RESOLUTIONS = (
    "implemented",
    "declined",
    "duplicate",
    "obsolete",
    "not-reproducible",
    "out-of-scope",
)
ID_RE = re.compile(r"^BL-\d{8}T\d{12}Z-[a-z0-9]+(?:-[a-z0-9]+)*$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
META_RE = re.compile(r"\A<!-- backlog-metadata\n(.+?)\n-->\n", re.DOTALL)


class Refusal(RuntimeError):
    """A command-level failure carrying the taxonomy code for the JSON error envelope."""

    def __init__(self, code: str, message: str, **extra: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def emit(operation: str, *, ok: bool, **values: object) -> None:
    body: dict[str, object] = {
        "ok": ok,
        "operation": operation,
        "backlog_version": BACKLOG_VERSION,
    }
    body.update(values)
    print(json.dumps(body, ensure_ascii=False, separators=(",", ":")))


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_title(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def required_text(name: str, value: str | None) -> str:
    if value is None or not value.strip():
        raise Refusal("invalid_argument", f"{name} must not be empty")
    return value.strip()


def validate_task_id(value: str) -> str:
    task_id = required_text("task-id", value)
    if not TASK_ID_RE.fullmatch(task_id):
        raise Refusal("invalid_argument", f"invalid task-id: {task_id}")
    return task_id


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    return (slug or "item")[:60].rstrip("-")


# --- Repository root resolution (D5) --------------------------------------
#
# Backlog data must live in the primary checkout's .agent_state/, never in a
# linked worktree: a worktree can be deleted while resolved/closed items are
# meant to be durable. Git itself is the source of truth for which directory
# that is, so we shell out to it rather than reimplement .git file parsing.


def run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise Refusal("invalid_argument", f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


@dataclass(frozen=True)
class RepositoryContext:
    worktree_root: Path
    control_root: Path

    @classmethod
    def discover(cls, path: Path) -> RepositoryContext:
        probe = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            text=True,
            capture_output=True,
            check=False,
        )
        if probe.returncode:
            raise Refusal("invalid_argument", f"not inside a git repository: {path}")
        root = Path(probe.stdout.strip()).resolve()
        common_dir = Path(
            run_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        ).resolve()
        control = common_dir.parent if common_dir.name == ".git" else common_dir
        return cls(root, control)


def resolve_control_root(root_arg: Path | None) -> Path:
    if root_arg is None:
        return RepositoryContext.discover(Path.cwd()).control_root
    candidate = root_arg.resolve()
    if not candidate.is_dir():
        raise Refusal("invalid_argument", f"--root is not a directory: {candidate}")
    context = RepositoryContext.discover(candidate)
    if context.control_root != candidate:
        raise Refusal(
            "invalid_argument",
            "--root must be the primary checkout, not a linked worktree or subdirectory "
            f"(primary checkout is {context.control_root}): {candidate}",
        )
    return context.control_root


# --- Item storage -----------------------------------------------------------


def backlog_root(control_root: Path) -> Path:
    return control_root / ".agent_state" / "backlog"


def ensure_dirs(base: Path) -> None:
    for status in STATUSES:
        (base / status).mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, text: str) -> None:
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as tmp:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def write_new_item(path: Path, text: str) -> None:
    """O_EXCL refuses to clobber an existing file; there is no lock to serialize
    concurrent creation against (D4 accepts that race as out of scope)."""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def render(meta: dict[str, Any]) -> str:
    metadata = json.dumps(
        meta, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    sections = [
        ("Observation", meta["observation"]),
        ("Evidence", meta["evidence"]),
        ("Impact", meta["impact"]),
        ("Desired outcome", meta["desired_outcome"]),
    ]
    for key, heading in (
        ("constraints", "Constraints"),
        ("suggested_direction", "Suggested direction"),
    ):
        if meta.get(key):
            sections.append((heading, meta[key]))
    if meta.get("resolution"):
        sections.append(
            ("Resolution", meta.get("resolution_note") or meta["resolution"])
        )
    body = "\n\n".join(f"## {heading}\n\n{text}" for heading, text in sections)
    return f"<!-- backlog-metadata\n{metadata}\n-->\n\n# {meta['title']}\n\n{body}\n"


def read_item(path: Path) -> dict[str, Any]:
    match = META_RE.match(path.read_text(encoding="utf-8"))
    if match is None:
        raise Refusal("corrupt_item", f"invalid metadata block: {path}")
    data = json.loads(match.group(1))
    if not isinstance(data, dict) or data.get("id") != path.stem:
        raise Refusal("corrupt_item", f"metadata identity mismatch: {path}")
    validate_item(data, path)
    return data


def validate_item(data: dict[str, Any], path: Path) -> None:
    item_id = data.get("id")
    if not isinstance(item_id, str) or not ID_RE.fullmatch(item_id):
        raise Refusal("corrupt_item", f"invalid item id in metadata: {path}")
    for key in (
        "title",
        "source_task",
        "observation",
        "evidence",
        "impact",
        "desired_outcome",
    ):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise Refusal("corrupt_item", f"invalid required field {key}: {path}")
    if data.get("kind") not in KINDS:
        raise Refusal("corrupt_item", f"invalid kind: {path}")
    if data.get("status") not in STATUSES:
        raise Refusal("corrupt_item", f"invalid status: {path}")
    areas = data.get("area")
    if (
        not isinstance(areas, list)
        or not areas
        or not all(isinstance(area, str) and area.strip() for area in areas)
    ):
        raise Refusal("corrupt_item", f"invalid area: {path}")


def all_items(base: Path) -> list[tuple[Path, dict[str, Any]]]:
    ensure_dirs(base)
    result: list[tuple[Path, dict[str, Any]]] = []
    seen: dict[str, Path] = {}
    for status in STATUSES:
        for path in sorted((base / status).glob("BL-*.md")):
            item = read_item(path)
            if item.get("status") != status:
                raise Refusal("corrupt_item", f"status/path mismatch: {path}")
            item_id = item["id"]
            if item_id in seen:
                raise Refusal(
                    "corrupt_item",
                    f"item id present in multiple status directories: {seen[item_id]} and {path}",
                )
            seen[item_id] = path
            result.append((path, item))
    return result


def find_item(base: Path, item_id: str) -> tuple[Path, dict[str, Any]]:
    if not ID_RE.fullmatch(item_id):
        raise Refusal("invalid_argument", f"invalid backlog id: {item_id}")
    matches = [(path, item) for path, item in all_items(base) if item["id"] == item_id]
    if not matches:
        raise Refusal("item_missing", f"backlog item not found: {item_id}")
    return matches[0]


def move_item(base: Path, source: Path, meta: dict[str, Any], status: str) -> None:
    destination = base / status / source.name
    if destination.exists():
        raise Refusal("corrupt_item", f"destination already exists: {destination}")
    meta["status"] = status
    meta["updated_at"] = now()
    atomic_write(destination, render(meta))
    source.unlink()


# --- Commands -----------------------------------------------------------


def command_add(args: argparse.Namespace, base: Path) -> dict[str, Any]:
    title = required_text("title", args.title)
    areas = sorted({required_text("area", area) for area in args.area})
    title_key = normalize_title(title)
    for _, existing in all_items(base):
        if normalize_title(existing["title"]) == title_key:
            raise Refusal(
                "duplicate_title",
                f"duplicate title: {title}",
                existing_id=existing["id"],
            )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    item_id = f"BL-{timestamp}-{slugify(title)}"
    meta: dict[str, Any] = {
        "id": item_id,
        "created_at": now(),
        "updated_at": now(),
        "status": "inbox",
        "kind": args.kind,
        "area": areas,
        "priority_hint": args.priority_hint,
        "source_task": required_text("source-task", args.source_task),
        "title": title,
        "observation": required_text("observation", args.observation),
        "evidence": required_text("evidence", args.evidence),
        "impact": required_text("impact", args.impact),
        "desired_outcome": required_text("desired-outcome", args.desired_outcome),
    }
    if args.constraints:
        meta["constraints"] = args.constraints.strip()
    if args.suggested_direction:
        meta["suggested_direction"] = args.suggested_direction.strip()
    path = base / "inbox" / f"{item_id}.md"
    write_new_item(path, render(meta))
    return meta


def command_list(args: argparse.Namespace, base: Path) -> dict[str, Any]:
    items = [item for _, item in all_items(base)]
    if args.status:
        items = [item for item in items if item["status"] == args.status]
    if args.kind:
        items = [item for item in items if item["kind"] == args.kind]
    if args.area:
        items = [item for item in items if args.area in item["area"]]
    return {"items": items}


def command_bind(args: argparse.Namespace, base: Path) -> dict[str, Any]:
    path, meta = find_item(base, args.item_id)
    if meta["status"] != "inbox":
        raise Refusal("invalid_transition", "only inbox items can be bound")
    task_id = validate_task_id(args.task_id)
    meta["planned_task"] = task_id
    meta["planned_at"] = now()
    move_item(base, path, meta, "planned")
    return meta


def command_close(args: argparse.Namespace, base: Path) -> dict[str, Any]:
    path, meta = find_item(base, args.item_id)
    if meta["status"] not in ("inbox", "planned"):
        raise Refusal("invalid_transition", "only inbox or planned items can be closed")
    if args.resolution == "implemented":
        if not args.task_id:
            raise Refusal(
                "invalid_transition", "implemented resolution requires a task-id"
            )
        task_id = validate_task_id(args.task_id)
        if meta["status"] == "planned" and task_id != meta.get("planned_task"):
            raise Refusal(
                "invalid_transition",
                "implemented resolution requires the bound task-id",
            )
        if not args.commit or not args.validation:
            raise Refusal(
                "invalid_transition",
                "implemented resolution requires commit and validation",
            )
        commits = [required_text("commit", value) for value in args.commit]
        validations = [required_text("validation", value) for value in args.validation]
        # X2 fix: store the validated task_id, not the raw (possibly padded) args.task_id.
        meta["resolved_by_task"] = task_id
        meta["commits"] = commits
        meta["validation"] = validations
        destination = "resolved"
    else:
        destination = "closed"
    if args.resolution == "duplicate":
        if not args.duplicate_of or args.duplicate_of == args.item_id:
            raise Refusal(
                "invalid_argument", "duplicate resolution requires another canonical ID"
            )
        find_item(base, args.duplicate_of)
        meta["duplicate_of"] = args.duplicate_of
    elif args.duplicate_of:
        raise Refusal(
            "invalid_argument", "--duplicate-of is only valid for duplicate resolution"
        )
    meta["resolution"] = args.resolution
    meta["resolution_note"] = args.note or args.resolution
    meta["closed_at"] = now()
    move_item(base, path, meta, destination)
    return meta


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--root", type=Path)
    sub = result.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--kind", choices=KINDS, required=True)
    add.add_argument("--area", action="append", required=True)
    add.add_argument("--source-task", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--observation", required=True)
    add.add_argument("--evidence", required=True)
    add.add_argument("--impact", required=True)
    add.add_argument("--desired-outcome", required=True)
    add.add_argument(
        "--priority-hint", choices=("low", "medium", "high"), default="medium"
    )
    add.add_argument("--constraints")
    add.add_argument("--suggested-direction")
    listing = sub.add_parser("list")
    listing.add_argument("--status", choices=STATUSES)
    listing.add_argument("--kind", choices=KINDS)
    listing.add_argument("--area")
    bind = sub.add_parser("bind")
    bind.add_argument("item_id")
    bind.add_argument("--task-id", required=True)
    close = sub.add_parser("close")
    close.add_argument("item_id")
    close.add_argument("--resolution", choices=RESOLUTIONS, required=True)
    close.add_argument("--task-id")
    close.add_argument("--commit", action="append")
    close.add_argument("--validation", action="append")
    close.add_argument("--duplicate-of")
    close.add_argument("--note")
    return result


def main() -> int:
    args = parser().parse_args()
    operation = args.command
    try:
        control_root = resolve_control_root(args.root)
        base = backlog_root(control_root)
        if operation == "add":
            payload = command_add(args, base)
        elif operation == "list":
            payload = command_list(args, base)
        elif operation == "bind":
            payload = command_bind(args, base)
        else:
            payload = command_close(args, base)
    except Refusal as refusal:
        error: dict[str, object] = {"code": refusal.code, "message": refusal.message}
        error.update(refusal.extra)
        emit(operation, ok=False, error=error)
        return 1
    except json.JSONDecodeError as exc:
        emit(
            operation,
            ok=False,
            error={"code": "corrupt_item", "message": f"invalid metadata JSON: {exc}"},
        )
        return 1
    except OSError as exc:
        emit(operation, ok=False, error={"code": "io_error", "message": str(exc)})
        return 1
    emit(operation, ok=True, **payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
