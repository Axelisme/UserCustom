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
import subprocess
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
DEFERRED_ACCEPTANCE_HEADING = "## Deferred user acceptance"
PHASE_FIELDS = ("Status", "Scope", "Decisions made", "Conclusion", "Commit", "Evidence")
DEFERRED_COLUMNS = (
    "Slice",
    "observable",
    "entrypoint",
    "steps",
    "expected",
    "verifier",
    "state",
    "accepted SHA",
)
DEFERRED_VERIFIERS = ("user", "agent")
DEFERRED_STATES = ("pending", "passed", "failed", "blocked", "accepted", "superseded")
# The retired 14-column header this schema replaces. Detected only to report a
# migration requirement — never parsed, converted, or otherwise accommodated.
RETIRED_14_COLUMN_HEADER_LENGTH = 14
FULL_SHA_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
ANGLE_TOKEN_PATTERN = re.compile(r"<(?P<content>[^<>\n]+)>")
# HTML tags are shipped content, unlike the skill's named/template prompt slots.
HTML_TAG_NAMES = frozenset({
    "a", "abbr", "article", "aside", "b", "blockquote", "body", "br", "button",
    "code", "dd", "details", "div", "dl", "dt", "em", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header",
    "html", "i", "img", "input", "label", "li", "link", "main", "meta", "nav",
    "ol", "p", "pre", "script", "section", "small", "span", "strong", "style",
    "summary", "table", "tbody", "td", "th", "thead", "title", "tr", "ul",
})
VERIFY_CLASSIFICATIONS = ("green", "baseline-debt", "environment-blocked")
LIVE_GIT_LABEL_PATTERN = re.compile(
    r"(?:^|[\s*`_-])(HEAD|tree|branch)(?:(?:\s*[:=]\s*)|(?:\s+))([^\s,;]+)",
    re.IGNORECASE,
)


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


def git_snapshot(root: Path) -> dict[str, Any] | None:
    """Derive HEAD/branch/tree/clean straight from git, or None outside a work tree.

    The point is to never hand-copy a current SHA into INDEX: read it live here.
    """

    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", *args], cwd=root, text=True, capture_output=True, check=False
            )
        except (OSError, ValueError):
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    head = git("rev-parse", "HEAD")
    if head is None:
        return None  # git absent, or root is not inside a work tree
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    porcelain = git("status", "--porcelain")
    return {
        "head": head,
        "branch": None if branch == "HEAD" else branch,
        "tree": tree,
        "clean": porcelain == "",
    }


def git_repository_identity(path: Path) -> tuple[Path, Path] | None:
    """Return the worktree root and shared common directory for a Git checkout."""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            text=True,
            capture_output=True,
            check=False,
        )
        common = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=path,
            text=True,
            capture_output=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if top.returncode != 0 or common.returncode != 0:
        return None
    git_root = Path(top.stdout.strip()).resolve()
    common_path = Path(common.stdout.strip())
    if not common_path.is_absolute():
        common_path = git_root / common_path
    return git_root, common_path.resolve()


def resolve_worktree(root: Path, requested: str) -> Path:
    """Resolve and validate a real Git worktree in root's repository."""
    raw = Path(requested).expanduser()
    path = Path(os.path.abspath(root / raw if not raw.is_absolute() else raw))
    if not path.exists() or not path.is_dir():
        raise PlanError(f"worktree is not an existing directory: {path}")
    resolved = path.resolve()
    if path != resolved:
        raise PlanError(f"worktree path contains a symlink: {path}")
    selected_identity = git_repository_identity(resolved)
    if selected_identity is None:
        raise PlanError(f"worktree is not a Git worktree: {resolved}")
    git_root, selected_common = selected_identity
    if git_root != resolved:
        raise PlanError(f"worktree must be its Git worktree root: {resolved}")
    root_identity = git_repository_identity(root)
    if root_identity is None or root_identity[1] != selected_common:
        raise PlanError(f"worktree belongs to an unrelated Git repository: {resolved}")
    return resolved


def live_git_hints(index: str) -> list[str]:
    """Report only explicitly labeled live Git values in Current State.

    Next-gate text and historical/evidence sections are intentionally excluded;
    this is advisory output, never a rewrite or validation failure.
    """
    lines = index.splitlines()
    try:
        start, end = section_span(lines, "## Current State")
    except PlanError:
        return []
    hints: list[str] = []
    for line in lines[start + 1 : end]:
        lowered = line.lower()
        if "next gate" in lowered or "histor" in lowered:
            continue
        match = LIVE_GIT_LABEL_PATTERN.search(line)
        if match:
            label, value = match.groups()
            hints.append(
                f"Current State contains live {label} {value!r}; status derives it live"
            )
    return hints


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
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [
        cell.replace(r"\|", "|").strip()
        for cell in re.split(r"(?<!\\)\|", row)
    ]


def normalized_cell(cell: str) -> str:
    return cell.strip().strip("`").strip()


def is_none_cell(cell: str) -> bool:
    return normalized_cell(cell).casefold() == "none"


def deferred_row_settled(verifier: str, state: str) -> bool:
    """True when a deferred row needs no further user or repair action.

    `accepted` is always settled. An agent-verified `passed` row is also
    settled: no user ever needs to confirm a repaired SHA for it. Everything
    else — including a user-verified `passed` (not yet reconciled against an
    accepted SHA) and `superseded` (a later lane invalidated the prior pass
    and it must be retested) — is unresolved.
    """
    return state == "accepted" or (verifier == "agent" and state == "passed")


def deferred_acceptance_state(text: str) -> tuple[list[str], list[str]]:
    """Return schema issues and unresolved Slice ids for one phase record.

    The deferred table has exactly one cross-field rule: an `accepted` state
    requires a full-hex `accepted SHA`, every other state requires `none`.
    Nothing else is checked in combination.
    """
    lines = text.splitlines()
    headings = [
        index
        for index, line in enumerate(lines)
        if line.strip() == DEFERRED_ACCEPTANCE_HEADING
    ]
    if not headings:
        return [], []
    if len(headings) != 1:
        return [f"'{DEFERRED_ACCEPTANCE_HEADING}' must appear exactly once"], []

    start, end = section_span(lines, DEFERRED_ACCEPTANCE_HEADING)
    table = [line for line in lines[start:end] if line.lstrip().startswith("|")]
    if len(table) < 3:
        return ["deferred user acceptance requires a header, separator, and data row"], []

    header = tuple(row_cells(table[0]))
    if len(header) == RETIRED_14_COLUMN_HEADER_LENGTH:
        return [
            "deferred user acceptance table uses the retired 14-column schema; "
            "migration required — no automatic conversion. Rewrite it against "
            f"the current {len(DEFERRED_COLUMNS)}-column schema in templates/phase.md"
        ], []
    if header != DEFERRED_COLUMNS:
        return [
            f"deferred user acceptance header must match the {len(DEFERRED_COLUMNS)}-column "
            "schema: " + ", ".join(DEFERRED_COLUMNS)
        ], []

    issues: list[str] = []
    separator = row_cells(table[1])
    if len(separator) != len(DEFERRED_COLUMNS) or any(
        re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator
    ):
        issues.append(f"deferred table separator must contain {len(DEFERRED_COLUMNS)} columns")

    parsed_rows: list[list[str]] = []
    for number, line in enumerate(table[2:], start=1):
        cells = row_cells(line)
        if len(cells) != len(DEFERRED_COLUMNS):
            issues.append(
                f"deferred row {number} must contain {len(DEFERRED_COLUMNS)} columns; "
                f"found {len(cells)}"
            )
            continue
        parsed_rows.append(cells)

    if not parsed_rows:
        issues.append("deferred table requires a placeholder or real data row")
        return issues, []

    placeholder_rows = [row for row in parsed_rows if is_none_cell(row[0])]
    real_rows = [row for row in parsed_rows if not is_none_cell(row[0])]
    for row in placeholder_rows:
        if not all(is_none_cell(cell) for cell in row):
            issues.append("deferred placeholder row must contain only none values")
    if placeholder_rows and real_rows:
        issues.append("deferred placeholder row cannot coexist with real rows")
    if len(placeholder_rows) > 1:
        issues.append("deferred table may contain only one placeholder row")
    if not real_rows:
        return issues, []

    unresolved: list[str] = []
    seen_slices: set[str] = set()
    for row in real_rows:
        record = {
            str(column): normalized_cell(cell)
            for column, cell in zip(DEFERRED_COLUMNS, row, strict=True)
        }
        slice_id = record["Slice"]
        verifier = record["verifier"]
        state = record["state"]
        accepted_sha = record["accepted SHA"]

        if slice_id in seen_slices:
            issues.append(f"duplicate deferred Slice '{slice_id}'")
        seen_slices.add(slice_id)

        if verifier not in DEFERRED_VERIFIERS:
            issues.append(f"{slice_id} has invalid deferred verifier '{verifier}'")
        if state not in DEFERRED_STATES:
            issues.append(f"{slice_id} has invalid deferred state '{state}'")
            continue  # the accepted-SHA rule is undefined for an unknown state

        if state == "accepted":
            if FULL_SHA_PATTERN.fullmatch(accepted_sha) is None:
                issues.append(
                    f"{slice_id} state 'accepted' requires a full 40- or 64-hex accepted SHA"
                )
        elif not is_none_cell(accepted_sha):
            issues.append(f"{slice_id} state '{state}' requires accepted SHA to be none")

        if not deferred_row_settled(verifier, state):
            unresolved.append(f"{slice_id}:{state}")

    return issues, unresolved


def deferred_plan_state(
    phase_texts: list[tuple[str, str]],
) -> tuple[list[str], dict[str, list[str]]]:
    issues: list[str] = []
    unresolved_by_phase: dict[str, list[str]] = {}
    for name, text in phase_texts:
        phase_issues, unresolved = deferred_acceptance_state(text)
        issues.extend(f"{name}: {issue}" for issue in phase_issues)
        unresolved_by_phase[name] = unresolved
    return issues, unresolved_by_phase


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


def has_placeholder(value: str) -> bool:
    """Recognize template slots while preserving shipped angle-bracket syntax.

    A slot is an angle token except a Markdown autolink, a known HTML tag, or a
    type argument attached to an identifier (for example ``Result<T>``).  This
    is structural rather than tied to any translated template prompt.
    """
    for match in ANGLE_TOKEN_PATTERN.finditer(value):
        content = match.group("content").strip()
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>]+", content):
            continue  # Markdown autolink
        tag = re.match(r"/?([A-Za-z][A-Za-z0-9-]*)\b", content)
        if tag and tag.group(1).lower() in HTML_TAG_NAMES:
            continue
        if match.start() and (value[match.start() - 1].isalnum() or value[match.start() - 1] == "_"):
            continue  # generic notation such as Result<T>
        return True
    return False



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
    current_status = read_phase_field(text, "Status")
    if current_status == "completed":
        raise PlanError(
            f"phase {int(args.phase):02d} is sealed after completion; phase-set cannot mutate it"
        )
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
            phase_texts = [
                (
                    other.name,
                    text if other == path else other.read_text(encoding="utf-8"),
                )
                for _, _, other in existing_phase_files(plan)
            ]
            deferred_issues, unresolved_by_phase = deferred_plan_state(phase_texts)
            if deferred_issues:
                raise PlanError(
                    "invalid deferred user acceptance: " + "; ".join(deferred_issues)
                )
            unresolved = unresolved_by_phase.get(path.name, [])
            if unresolved:
                raise PlanError(
                    "completing a phase requires all deferred user acceptance items "
                    "to be accepted: " + ", ".join(unresolved)
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
        structured = any(
            value is not None
            for value in (
                args.subject_result, args.baseline_sha, args.baseline_result, args.classification
            )
        )
        if structured:
            if args.result is not None or args.sha is not None:
                raise PlanError("structured --verify cannot be combined with legacy --result/--sha")
            if not args.command or not args.subject_result or not args.classification:
                raise PlanError(
                    "structured --verify requires --command, --subject-result, and --classification"
                )
            if args.classification not in VERIFY_CLASSIFICATIONS:
                raise PlanError(f"--classification must be one of {VERIFY_CLASSIFICATIONS}")
            if bool(args.baseline_sha) != bool(args.baseline_result):
                raise PlanError("--baseline-sha and --baseline-result must be supplied together")
            if args.classification == "baseline-debt" and not args.baseline_sha:
                raise PlanError("baseline-debt requires --baseline-sha and --baseline-result")
            row = {
                "ts": now_ts(),
                "kind": "verify",
                "classification": args.classification,
                "command": args.command,
                "subject_result": args.subject_result,
            }
            if args.baseline_sha:
                row["baseline_result"] = args.baseline_result
                row["baseline_sha"] = args.baseline_sha
        else:
            if not args.command or not args.result:
                raise PlanError("--verify requires --command and --result")
            row = {
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


def lifecycle_has_started(index: str) -> bool:
    return any(
        row["status"] in ("in_progress", "completed") for row in read_board(index)
    )


def unresolved_placeholder_issues(plan: Path, index: str) -> list[str]:
    """Find live template slots after work begins, without matching translated prompt text."""
    if not lifecycle_has_started(index):
        return []

    issues: list[str] = []
    lines = index.splitlines()
    current_start, current_end = section_span(lines, "## Current State")
    current = lines[current_start + 1 : current_end]
    next_gate = next(
        (line.partition(":")[2].strip() for line in current if "**Next gate:**" in line),
        "",
    )
    if not next_gate or has_placeholder(next_gate):
        issues.append("INDEX Current State has an unresolved Next gate")
    if any(has_placeholder(line) for line in current if "**Next gate:**" not in line):
        issues.append("INDEX Current State has an unresolved placeholder")

    decisions_start, decisions_end = section_span(lines, "## Decisions")
    decision_rows = [line for line in lines[decisions_start:decisions_end] if line.lstrip().startswith("|")]
    for row in decision_rows[2:]:
        cells = row_cells(row)
        if len(cells) >= 4 and cells[1].lower() == "active" and any(has_placeholder(cell) for cell in cells):
            issues.append(f"INDEX active decision '{cells[0]}' has an unresolved placeholder")

    for _, _, path in existing_phase_files(plan):
        text = path.read_text(encoding="utf-8")
        if read_phase_field(text, "Status") not in ("in_progress", "completed"):
            continue
        for field in PHASE_FIELDS:
            value = read_phase_field(text, field)
            if not value:
                issues.append(f"{path.name} has an empty required field '{field}'")
            elif has_placeholder(value):
                issues.append(f"{path.name} has an unresolved placeholder in '{field}'")
    return issues


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
    if all(heading in index for heading in ("## Current State", "## Decisions", BOARD_HEADING)):
        issues.extend(
            unresolved_placeholder_issues(plan, index)
        )
    board_rows = read_board(index) if BOARD_HEADING in index else []
    board_by_phase: dict[str, dict[str, str]] = {}
    for row in board_rows:
        phase = row["phase"]
        if phase in board_by_phase:
            issues.append(f"INDEX phase board has duplicate phase '{phase}'")
        board_by_phase[phase] = row
        if row["status"] not in PHASE_STATUSES:
            issues.append(f"INDEX phase board has invalid status for phase '{phase}'")
    phase_files = {f"{num:02d}": path for num, _, path in existing_phase_files(plan)}
    phase_texts = {
        num: path.read_text(encoding="utf-8") for num, path in phase_files.items()
    }
    deferred_issues, unresolved_by_phase = deferred_plan_state(
        [(phase_files[num].name, text) for num, text in phase_texts.items()]
    )
    issues.extend(deferred_issues)
    for num, path in phase_files.items():
        text = phase_texts[num]
        record_status = read_phase_field(text, "Status")
        for field in PHASE_FIELDS:
            if not re.search(rf"^- \*\*{re.escape(field)}:\*\*", text, re.MULTILINE):
                issues.append(f"{path.name} has no '{field}' field")
        if record_status not in PHASE_STATUSES:
            issues.append(f"{path.name} has invalid Status")
        unresolved = unresolved_by_phase.get(path.name, [])
        if record_status == "completed" and unresolved:
            issues.append(
                f"{path.name} has unresolved deferred user acceptance: "
                + ", ".join(unresolved)
            )
        board = board_by_phase.get(num)
        if board is None:
            issues.append(f"{path.name} is not listed on the INDEX phase board")
        elif board["status"] != record_status:
            issues.append(f"{path.name} Status disagrees with INDEX phase board")
        elif board["record"] != f"{PHASES_DIR}/{path.name}":
            issues.append(f"{path.name} record disagrees with INDEX phase board")
    for phase in board_by_phase:
        if phase not in phase_files:
            issues.append(f"INDEX phase board phase '{phase}' has no phase record")
    progress = plan / PROGRESS_FILE
    if progress.is_file():
        for lineno, line in enumerate(progress.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    issues.append(f"{PROGRESS_FILE}:{lineno} is not valid JSON")
    return issues


def command_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    index = read_index(plan)
    hints = live_git_hints(index)
    issues = validate_plan(plan)
    if issues:
        raise PlanError("plan is not schema-valid: " + "; ".join(issues))
    size = utf8_size(index)
    if size > INDEX_LIMIT_BYTES:
        overage = size - INDEX_LIMIT_BYTES
        raise PlanError(
            f"{INDEX_FILE} is {overage} bytes over the {INDEX_LIMIT_BYTES} budget"
            f" (actual size {size} bytes); prune Current State and superseded decisions —"
            " phase detail belongs in its phases/ record, not the entry"
        )
    return {
        "ok": True,
        "operation": "checkpoint",
        "task_id": args.task_id,
        "index_bytes": size,
        "hints": hints,
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
    worktree = resolve_worktree(root, args.worktree) if args.worktree else None
    snapshot_root = worktree or root
    git = git_snapshot(snapshot_root)
    if worktree is not None and git is not None:
        git["worktree"] = str(worktree)
        git["projection_source"] = str(worktree)
    return {
        "ok": True,
        "operation": "status",
        "task_id": args.task_id,
        "index_bytes": utf8_size(index),
        "phases": board,
        "git": git,
        "stores": {
            "phases": len(existing_phase_files(plan)),
            "progress_rows": progress_rows,
            "findings": (plan / FINDINGS_FILE).is_file(),
        },
    }


def command_archive(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    validate_task_id(args.task_id)
    plan = require_plan(root, args.task_id)
    destination = archive_dir(root, args.task_id)
    reject_symlink_components(root, destination)
    if destination.exists():
        raise PlanError(f"archive destination already exists: {destination}")
    issues = validate_plan(plan)
    if issues:
        raise PlanError("plan is not complete: " + "; ".join(issues))
    open_phases = [row["phase"] for row in read_board(read_index(plan)) if row["status"] in OPEN_STATUSES]
    if open_phases:
        raise PlanError(f"phase board still has open phases: {', '.join(open_phases)}")
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
    status.add_argument("--worktree")
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
    log.add_argument("--subject-result")
    log.add_argument("--baseline-sha")
    log.add_argument("--baseline-result")
    log.add_argument("--classification")
    log.set_defaults(handler=command_log)

    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("task_id")
    checkpoint.set_defaults(handler=command_checkpoint)

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
