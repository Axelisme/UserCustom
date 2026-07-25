"""Milestone admission projection (dev-flow admission standard S3).

Read-only. Reports what Git can prove about an integration range and states plainly
which checks it cannot decide, so a milestone is never admitted on an unanswered
question. It reports; dev-flow enforces.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .git_ops import exact_commit, run_git
from .primitives import OrchestrateError

DEFAULT_SLICE_WAVES = 2
DEFAULT_FAMILY_TOKENS = 1
DEFAULT_SLICE_ADDED = 1500
DEFAULT_FILE_ADDED = 2000
DEFAULT_FOCUS_DAYS = 3

REFUSE = "refuse"
PASS = "pass"
UNDETERMINED = "undetermined"


def _is_test_path(path: str) -> bool:
    tail = path.rsplit("/", 1)[-1]
    return (
        "tests/" in path
        or path.startswith("test/")
        or tail.startswith("test_")
        or tail.endswith("_test.py")
        or tail == "conftest.py"
    )


def _is_under(path: str, roots: list[str]) -> bool:
    normalized = path.removeprefix("./")
    return any(
        normalized == root.rstrip("/")
        or normalized.startswith(root.rstrip("/") + "/")
        for root in roots
    )


def _numstat(root: Path, *args: str) -> list[tuple[int, int, str]]:
    output = run_git(root, "diff", "--numstat", *args).stdout
    rows: list[tuple[int, int, str]] = []
    for line in output.splitlines():
        added, _, rest = line.partition("\t")
        deleted, _, path = rest.partition("\t")
        if added == "-" or deleted == "-" or not path:
            continue  # binary
        rows.append((int(added), int(deleted), path))
    return rows


def _commits(root: Path, base: str, tip: str) -> list[dict[str, Any]]:
    # Merges are kept: a collect is a merge commit, so excluding them hides the
    # very loop this projection exists to count. Line attribution skips them.
    fmt = "%H%x1f%cI%x1f%s%x1f%P%x1f%b%x1e"
    output = run_git(root, "log", f"--format={fmt}", f"{base}..{tip}").stdout
    commits: list[dict[str, Any]] = []
    for record in output.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, date, subject, parents, body = record.split("\x1f")
        slice_id = None
        for line in body.splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() == "slice" and value.strip():
                slice_id = value.strip()
        commits.append(
            {
                "sha": sha,
                "date": date,
                "subject": subject,
                "slice": slice_id,
                "merge": len(parents.split()) > 1,
            }
        )
    return commits


def _family(slice_id: str, tokens: int) -> str:
    # A correction Wave is routinely given a fresh Slice id (`k2-race-fd-correction`
    # after `k2-close-clock-correction`), so counting exact ids reports one Wave per
    # Slice and never sees the loop. Group by the leading tokens instead.
    return "-".join(slice_id.split("-")[:tokens]) or slice_id


def _commit_added(root: Path, sha: str, production_roots: list[str]) -> int:
    output = run_git(
        root, "show", "--numstat", "--format=", sha
    ).stdout
    total = 0
    for line in output.splitlines():
        added, _, rest = line.partition("\t")
        _, _, path = rest.partition("\t")
        if (
            added == "-"
            or not path
            or _is_test_path(path)
            or not _is_under(path, production_roots)
        ):
            continue
        total += int(added)
    return total


def _validate_args(args: argparse.Namespace) -> None:
    positive = {
        "--max-slice-waves": args.max_slice_waves,
        "--max-slice-added": args.max_slice_added,
        "--max-file-added": args.max_file_added,
        "--focus-days": args.focus_days,
        "--slice-family-tokens": args.slice_family_tokens,
    }
    invalid = [name for name, value in positive.items() if value <= 0]
    if invalid:
        raise OrchestrateError(f"must be positive: {', '.join(invalid)}")
    if args.findings is None:
        if args.backlog is not None:
            raise OrchestrateError("--backlog requires --findings")
    elif args.findings < 0:
        raise OrchestrateError("--findings must be non-negative")
    elif args.backlog is not None and not 0 <= args.backlog <= args.findings:
        raise OrchestrateError("--backlog must be between 0 and --findings")
    if args.burndown_previous is not None and args.burndown is None:
        raise OrchestrateError("--burndown-previous requires --burndown")


def _check(
    identifier: str, status: str, *, value: Any = None, threshold: Any = None,
    question: str | None = None, detail: Any = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": identifier, "status": status}
    if value is not None:
        entry["value"] = value
    if threshold is not None:
        entry["threshold"] = threshold
    if question is not None:
        entry["question"] = question
    if detail is not None:
        entry["detail"] = detail
    return entry


def command_admission(args: argparse.Namespace) -> dict[str, Any]:
    _validate_args(args)
    root = Path(args.root).resolve()
    base = exact_commit(root, args.base, label="--base")
    tip = exact_commit(root, args.tip, label="--tip")
    production_roots = args.production_path or []

    rows = _numstat(root, f"{base}..{tip}")
    production = [
        row
        for row in rows
        if _is_under(row[2], production_roots) and not _is_test_path(row[2])
    ]
    deletions = sum(deleted for _, deleted, _ in production)
    checks = [
        _check(
            "deletion",
            (PASS if deletions else REFUSE) if production_roots else UNDETERMINED,
            value=deletions,
            threshold=1,
            question=(
                "supply --production-path; docs, config, and fixtures cannot prove a"
                " production deletion (S3.2)"
                if not production_roots
                else "which production path does this milestone delete? pure addition"
                " accumulates unreachable code (S1.2)"
            ),
            detail={"production_paths": production_roots},
        )
    ]

    commits = _commits(root, base, tip)
    added_per_family: dict[str, int] = {}
    unattributed = 0
    for commit in commits:
        if commit["merge"]:
            continue
        added = _commit_added(root, commit["sha"], production_roots)
        if commit["slice"] is None:
            unattributed += added
            continue
        family = _family(commit["slice"], args.slice_family_tokens)
        added_per_family[family] = added_per_family.get(family, 0) + added

    loops: dict[str, int] = {}
    for commit in commits:
        if not commit["subject"].startswith("Collect Wave"):
            continue
        name = commit["slice"] or commit["subject"].removeprefix("Collect Wave").strip()
        family = _family(name, args.slice_family_tokens)
        loops[family] = loops.get(family, 0) + 1
    worst_loop = max(loops.values(), default=0)
    checks.append(
        _check(
            "slice_loop",
            REFUSE if worst_loop > args.max_slice_waves else PASS,
            value=worst_loop,
            threshold=args.max_slice_waves,
            question="a Slice past its cycle cap is a scope event, not an"
            " implementation event (S4.1/S4.2)",
            detail=dict(sorted(loops.items(), key=lambda item: -item[1])[:5]),
        )
    )

    worst_slice = max(added_per_family.items(), key=lambda item: item[1], default=("", 0))
    checks.append(
        _check(
            "slice_size",
            (
                REFUSE if worst_slice[1] > args.max_slice_added else PASS
            ) if production_roots else UNDETERMINED,
            value=worst_slice[1],
            threshold=args.max_slice_added,
            question=(
                "a Slice over budget is recut before dispatch, not after (S1.3)"
                if production_roots
                else "supply --production-path to measure non-test production size (S1.3)"
            ),
            detail={"family": worst_slice[0] or None, "unattributed": unattributed},
        )
    )

    if args.reachability_cmd:
        probe = subprocess.run(
            args.reachability_cmd, cwd=root, shell=True, capture_output=True, text=True
        )
        reachability_status = PASS if probe.returncode == 0 else REFUSE
        reachability_value: int | None = probe.returncode
        reachability_detail = (probe.stderr or probe.stdout).strip()[:400] or None
    else:
        reachability_status = UNDETERMINED
        reachability_value = None
        reachability_detail = None

    worst_file = max(production, key=lambda row: row[0], default=(0, 0, ""))
    oversized_files = [row for row in production if row[0] > args.max_file_added]
    file_reachability: dict[str, int] = {}
    if args.file_reachability_cmd:
        for _, _, path in oversized_files:
            probe = subprocess.run(
                args.file_reachability_cmd,
                cwd=root,
                shell=True,
                capture_output=True,
                text=True,
                env={**os.environ, "ORCHESTRATE_PRODUCTION_PATH": path},
            )
            file_reachability[path] = probe.returncode
    mass_status = (
        UNDETERMINED
        if not production_roots or (oversized_files and not args.file_reachability_cmd)
        else REFUSE
        if any(returncode != 0 for returncode in file_reachability.values())
        else PASS
    )
    checks.append(
        _check(
            "file_mass",
            mass_status,
            value=worst_file[0],
            threshold=args.max_file_added,
            question=(
                "supply --production-path and --file-reachability-cmd to decide each"
                " oversized production file (S3.4)"
                if mass_status == UNDETERMINED
                else "one file this large inside an unreachable subsystem is the"
                " signature of hardening admitted as interface (S2.1)"
            ),
            detail={
                "largest": worst_file[2] or None,
                "file_reachability": file_reachability,
            },
        )
    )

    horizon = datetime.now(UTC) - timedelta(days=args.focus_days)
    recent = [
        commit
        for commit in commits
        if datetime.fromisoformat(commit["date"]) >= horizon
    ]
    attributed_recent = [commit for commit in recent if commit["slice"]]
    recent_slices = {
        _family(commit["slice"], args.slice_family_tokens)
        for commit in attributed_recent
    }
    focus_refuses = bool(attributed_recent) and len(recent_slices) == 1
    checks.append(
        _check(
            "focus",
            REFUSE if focus_refuses else PASS,
            value=sorted(recent_slices) or None,
            threshold=(
                f">1 Slice across {len(attributed_recent)} attributed commits in"
                f" {args.focus_days}d"
            ),
            question="every recent commit on one Slice is what a correction loop"
            " looks like from outside",
        )
    )

    checks.append(
        _check(
            "reachability",
            reachability_status,
            value=reachability_value,
            question=(
                "does a production entrypoint reach this milestone's new modules? (S3.1)"
                if args.reachability_cmd
                else "supply --reachability-cmd; an unanswered reachability question"
                " is not a pass (S3.1)"
            ),
            detail=reachability_detail,
        )
    )

    if args.burndown:
        path = Path(args.burndown)
        if not path.is_file():
            checks.append(
                _check("burndown", REFUSE, value=str(path), question="no burn-down"
                       " projection exists; narrative is not state (S3.6)")
            )
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if args.burndown_previous is None:
                status = UNDETERMINED
                question = "supply --burndown-previous; movement needs two digests (S3.6)"
            else:
                status = REFUSE if args.burndown_previous == digest else PASS
                question = "the burn-down did not move this milestone (S3.6)"
            checks.append(
                _check(
                    "burndown",
                    status,
                    value=digest,
                    question=question,
                )
            )
    else:
        checks.append(
            _check("burndown", UNDETERMINED, question="supply --burndown <path> to"
                   " the Slice x status projection (S3.6)")
        )

    if args.findings is None:
        checks.append(
            _check("downgrade", UNDETERMINED, question="supply --findings/--backlog"
                   " from the review round (S4.3)")
        )
    else:
        backlog = args.backlog or 0
        checks.append(
            _check(
                "downgrade",
                REFUSE if args.findings > 0 and backlog == 0 else PASS,
                value=[args.findings, backlog],
                question="a round where every finding blocks means the spec is wide"
                " enough to justify anything (S4.3)",
            )
        )

    statuses = {entry["status"] for entry in checks}
    verdict = (
        REFUSE if REFUSE in statuses
        else "incomplete" if UNDETERMINED in statuses
        else "admit"
    )
    return {
        # ok tracks the verdict, so a refused or incomplete milestone exits non-zero
        # without being reported as a command failure (which exits 2).
        "ok": verdict == "admit",
        "operation": "admission",
        "read_only": True,
        "verdict": verdict,
        "base": base,
        "tip": tip,
        "commits": len(commits),
        "checks": checks,
        "stall_watch": [
            entry["id"] for entry in checks
            if entry["id"] in {"reachability", "deletion"} and entry["status"] != PASS
        ],
    }
