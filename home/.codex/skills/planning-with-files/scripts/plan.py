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
from datetime import date
from pathlib import Path
from typing import Any

TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
UNFINISHED_PHASE_PATTERN = re.compile(r"\|[^|]+\|\s*(pending|in_progress|blocked)\s*\|")
OPTIONAL_TEMPLATES = {
    "findings.md": "findings.md",
    "progress.md": "progress.md",
}


class PlanError(RuntimeError):
    pass


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
