from __future__ import annotations

import argparse
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError
from .git_ops import exact_commit, is_ancestor, lane_absorption, managed_worktree_root, require_managed_worktree, run_git, worktree_metadata_writability_preflight, worktree_records
from .findings import (
    closed_finding_ids,
    command_findings_status,
    dedup_findings,
    read_findings_ledger,
    task_id_from_ref,
)
from .lanes import command_slice_status, speculative_dependency_records

WORKTREE_CLASSES = (
    "safe-to-remove",
    "held-by-review-debt",
    "active-run-ahead-base",
    "active",
    "orphaned",
    "unknown",
)


def _open_gating_findings(
    root: Path, task_id: str, head: str
) -> list[dict[str, Any]]:
    closed = closed_finding_ids(root, head)
    open_findings: list[dict[str, Any]] = []
    for fid, record in dedup_findings(read_findings_ledger(root, task_id)).items():
        if record.get("propagation") != "gates-the-slice" or fid in closed:
            continue
        subject = record.get("subject_sha")
        if subject and not is_ancestor(root, subject, head):
            continue
        open_findings.append({**record, "id": fid})
    return open_findings


def classify_worktree(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Classify one worktree and expose the evidence used by cleanup."""
    raw_path = record.get("worktree")
    if not isinstance(raw_path, str):
        return {
            "class": "unknown",
            "cleanup_eligible": False,
            "reason": "worktree record has no path",
        }
    path = Path(raw_path).resolve()
    managed = managed_worktree_root(root).resolve()
    try:
        relative = path.relative_to(managed)
    except ValueError:
        return {
            "class": "unknown",
            "cleanup_eligible": False,
            "path": str(path),
            "reason": "worktree is outside managed root",
        }
    if len(relative.parts) != 1:
        return {
            "class": "unknown",
            "cleanup_eligible": False,
            "path": str(path),
            "reason": "worktree is not a managed direct child",
        }
    branch_value = record.get("branch")
    branch = (
        str(branch_value).removeprefix("refs/heads/")
        if isinstance(branch_value, str)
        else None
    )
    head = record.get("HEAD")
    base: dict[str, Any] = {
        "path": str(path),
        "branch": branch,
        "head": head,
        "cleanup_eligible": False,
    }
    if "detached" in record or branch is None:
        base.update(
            {
                "class": "unknown",
                "kind": "review",
                "reason": "detached review liveness is unknowable from Git",
            }
        )
        return base
    lane_match = re.fullmatch(r"agent/([^/]+)/([^/]+)", branch)
    if lane_match is None:
        base.update(
            {
                "class": "orphaned",
                "kind": "lane",
                "reason": "not a full agent lane ref",
            }
        )
        return base
    task_id = lane_match.group(1)
    task_ref = f"task/{task_id}"
    base["task_ref"] = task_ref
    if (
        run_git(
            root,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{task_ref}",
            check=False,
        ).returncode
        != 0
    ):
        base.update(
            {"class": "orphaned", "kind": "lane", "reason": "missing task ref"}
        )
        return base
    if not isinstance(head, str):
        base.update(
            {
                "class": "unknown",
                "kind": "lane",
                "reason": "missing worktree HEAD",
            }
        )
        return base
    if not path.exists():
        base.update(
            {
                "class": "unknown",
                "kind": "lane",
                "reason": "worktree directory is missing",
            }
        )
        return base
    dirty = bool(run_git(path, "status", "--porcelain").stdout.strip())
    base["dirty"] = dirty
    task_head = run_git(root, "rev-parse", f"{task_ref}^{{commit}}").stdout.strip()
    base["task_head"] = task_head
    findings = _open_gating_findings(root, task_id, head)
    base["open_gating_findings"] = [finding["id"] for finding in findings]
    speculative = speculative_dependency_records(root, head)
    base["speculative_history"] = speculative
    prerequisite_ids = {
        finding["id"]
        for finding in findings
        if any(
            finding.get("subject_sha")
            and is_ancestor(root, finding["subject_sha"], dependency)
            for record_entry in speculative
            for dependency in record_entry["dependencies"]
        )
    }
    base["speculative_prerequisite_findings"] = sorted(prerequisite_ids)
    absorption = lane_absorption(root, head, task_head)
    base["lane_absorption"] = absorption
    if prerequisite_ids:
        classification = "active-run-ahead-base"
        reason = "speculative successor carries an open prerequisite finding"
    elif findings:
        classification = "held-by-review-debt"
        reason = "open gating finding is reachable from the lane"
    elif dirty:
        classification = "active"
        reason = "worktree is dirty"
    elif absorption is not None:
        classification = "safe-to-remove"
        reason = f"lane absorbed by {task_ref} via {absorption}"
    else:
        classification = "active"
        reason = "lane is not absorbed by its task ref"
    base.update(
        {
            "class": classification,
            "kind": "lane",
            "reason": reason,
            "cleanup_eligible": classification == "safe-to-remove" and not dirty,
        }
    )
    return base


def command_reconcile(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    worktrees: list[dict[str, Any]] = []
    managed = managed_worktree_root(root).resolve()
    for record in worktree_records(root):
        raw_path = record.get("worktree")
        if not isinstance(raw_path, str):
            continue
        try:
            relative = Path(raw_path).resolve().relative_to(managed)
        except ValueError:
            continue
        if len(relative.parts) != 1:
            continue
        worktrees.append(classify_worktree(root, record))
    summary: dict[str, int] = {name: 0 for name in WORKTREE_CLASSES}
    for entry in worktrees:
        summary[entry["class"]] += 1
    return {
        "ok": True,
        "operation": "reconcile",
        "read_only": True,
        "worktrees": worktrees,
        "summary": summary,
        "safe_to_remove": [
            entry["path"] for entry in worktrees if entry["cleanup_eligible"]
        ],
    }


def command_wave_status(args: argparse.Namespace) -> dict[str, Any]:
    """Read-only wave rollup: compose the derived reads a wave boundary already needs
    (slice states, finding ledger, worktree reconciliation) into one report plus a
    restart-oriented handoff summary. It never dispatches, lands, or writes the task
    plan — those stay root's decision; this only saves hand-stitching the same reads."""
    task_ref = args.task_ref
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    task_id = task_id_from_ref(task_ref)
    slice_report = command_slice_status(
        argparse.Namespace(root=args.root, task_ref=task_ref)
    )
    findings_report = command_findings_status(
        argparse.Namespace(root=args.root, task_id=task_id, task_ref=task_ref)
    )
    reconcile_report = command_reconcile(argparse.Namespace(root=args.root))
    handoff = {
        "task_ref": task_ref,
        "task_sha": slice_report["task_sha"],
        "lanes": [
            {"lane_ref": lane["lane_ref"], "head": lane["head"], "state": lane["state"]}
            for lane in slice_report["lanes"]
        ],
        "write_set_overlaps": slice_report["write_set_overlaps"],
        "open_findings": [rec["id"] for rec in findings_report["open"]],
        "gating_open": findings_report["gating_open"],
        "collect_blocked": findings_report["collect_blocked"],
        "reviewed_clean": findings_report["reviewed_clean"],
        "safe_to_remove": reconcile_report["safe_to_remove"],
    }
    return {
        "ok": True,
        "operation": "wave-status",
        "read_only": True,
        "task_ref": task_ref,
        "task_id": task_id,
        "slice": slice_report,
        "findings": findings_report,
        "reconcile": reconcile_report,
        "handoff": handoff,
    }


def cleanup_single_worktree(
    args: argparse.Namespace, root: Path, started: float
) -> dict[str, Any]:
    target = require_managed_worktree(root, Path(args.worktree).resolve(), kind="any")
    record = next(
        (
            record
            for record in worktree_records(root)
            if record.get("worktree") == str(target)
        ),
        None,
    )
    result: dict[str, Any] = {
        "ok": True,
        "operation": "cleanup",
        "path": str(target),
    }
    if record is None:
        if target.exists():
            raise OrchestrateError(f"not a registered worktree: {target}")
        result["recovered"] = "already-removed"
    else:
        worktree_metadata_writability_preflight(root)
        if not target.exists():
            run_git(root, "worktree", "prune")
            result["recovered"] = "pruned-stale-metadata"
        elif "detached" in record:
            result["kind"] = "review"
            if run_git(target, "status", "--porcelain").stdout.strip():
                raise OrchestrateError("review worktree is dirty")
            head = run_git(target, "rev-parse", "HEAD").stdout.strip()
            if args.subject_sha:
                subject = exact_commit(root, args.subject_sha, label="subject SHA")
                if head != subject:
                    raise OrchestrateError(
                        f"review checkout HEAD drifted: {head} != {subject};"
                        " evidence bound to that SHA is void — investigate before"
                        " removing manually"
                    )
            result["head"] = head
            run_git(root, "worktree", "remove", str(target))
        else:
            result["kind"] = "lane"
            branch = str(record.get("branch", "")).removeprefix("refs/heads/")
            match = re.fullmatch(r"agent/([^/]+)/[^/]+", branch)
            if match is None:
                raise OrchestrateError(f"not an agent lane branch: {branch!r}")
            task_ref = f"task/{match.group(1)}"
            if run_git(target, "status", "--porcelain").stdout.strip():
                raise OrchestrateError("lane worktree is dirty")
            lane_sha = run_git(root, "rev-parse", f"{branch}^{{commit}}").stdout.strip()
            task_sha = run_git(
                root, "rev-parse", f"{task_ref}^{{commit}}"
            ).stdout.strip()
            absorption = lane_absorption(root, lane_sha, task_sha)
            if absorption is None:
                raise OrchestrateError(
                    f"lane is not absorbed by {task_ref} (ancestry or tree identity)"
                )
            run_git(root, "worktree", "remove", str(target))
            run_git(root, "branch", "-D", branch)
            result.update(
                branch=branch,
                lane_sha=lane_sha,
                task_ref=task_ref,
                absorption=absorption,
            )
    return {
        **result,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_cleanup_absorbed(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    if args.worktree:
        return cleanup_single_worktree(args, root, started)
    if not args.absorbed:
        raise OrchestrateError(
            "pass --worktree for one target or --absorbed to authorize the sweep"
        )
    if not args.dry_run:
        worktree_metadata_writability_preflight(root)
    managed = managed_worktree_root(root).resolve()
    entries: list[dict[str, Any]] = []
    for record in worktree_records(root):
        raw = record.get("worktree")
        if not isinstance(raw, str):
            continue
        path = Path(raw)
        try:
            relative = path.resolve().relative_to(managed)
        except ValueError:
            continue
        if len(relative.parts) != 1:
            continue
        entry: dict[str, Any] = {"path": str(path)}
        entries.append(entry)
        if "detached" in record:
            entry["kind"] = "review"
            if not path.exists():
                entry.update(
                    action="rejected",
                    reason="directory missing; run cleanup --worktree to prune metadata",
                )
            elif run_git(path, "status", "--porcelain").stdout.strip():
                entry.update(action="rejected", reason="worktree is dirty")
            else:
                entry["head"] = run_git(path, "rev-parse", "HEAD").stdout.strip()
                if args.dry_run:
                    entry["action"] = "eligible"
                else:
                    run_git(root, "worktree", "remove", str(path))
                    entry["action"] = "removed"
            continue
        branch = str(record.get("branch", "")).removeprefix("refs/heads/")
        entry["kind"] = "lane"
        entry["branch"] = branch
        match = re.fullmatch(r"agent/([^/]+)/[^/]+", branch)
        if match is None:
            entry.update(action="rejected", reason="not an agent lane branch")
            continue
        task_ref = f"task/{match.group(1)}"
        if (
            run_git(
                root,
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{task_ref}",
                check=False,
            ).returncode
            != 0
        ):
            entry.update(
                action="rejected", reason=f"missing integration branch {task_ref}"
            )
            continue
        if not path.exists():
            entry.update(
                action="rejected",
                reason="directory missing; run cleanup --worktree to recover",
            )
            continue
        if run_git(path, "status", "--porcelain").stdout.strip():
            entry.update(action="rejected", reason="worktree is dirty")
            continue
        lane_sha = run_git(root, "rev-parse", f"{branch}^{{commit}}").stdout.strip()
        task_sha = run_git(root, "rev-parse", f"{task_ref}^{{commit}}").stdout.strip()
        absorption = lane_absorption(root, lane_sha, task_sha)
        if absorption is None:
            entry.update(action="rejected", reason=f"not absorbed by {task_ref}")
            continue
        entry.update(lane_sha=lane_sha, task_ref=task_ref, absorption=absorption)
        if args.dry_run:
            entry["action"] = "eligible"
        else:
            run_git(root, "worktree", "remove", str(path))
            run_git(root, "branch", "-D", branch)
            entry["action"] = "removed"
    return {
        "ok": True,
        "operation": "cleanup-absorbed",
        "dry_run": bool(args.dry_run),
        "entries": entries,
        "removed": sum(1 for entry in entries if entry.get("action") == "removed"),
        "rejected": sum(1 for entry in entries if entry.get("action") == "rejected"),
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_cleanup(args: argparse.Namespace) -> dict[str, Any]:
    """Require an exact target and classifier approval before cleanup mutates state."""
    root = Path(args.root).resolve()
    if not args.worktree:
        reconciliation = command_reconcile(argparse.Namespace(root=str(root)))
        if args.dry_run:
            return {
                "ok": True,
                "operation": "cleanup-dry-run",
                "read_only": True,
                "bulk_cleanup_disabled": True,
                "worktrees": reconciliation["worktrees"],
                "safe_to_remove": reconciliation["safe_to_remove"],
            }
        safe = reconciliation["safe_to_remove"]
        hint = ", ".join(safe) if safe else "none"
        raise OrchestrateError(
            "bulk cleanup is disabled because reviewer liveness is not durable; run"
            f" reconcile, then cleanup each exact --worktree target (safe: {hint})"
        )
    target = require_managed_worktree(root, Path(args.worktree).resolve(), kind="any")
    record = next(
        (
            candidate
            for candidate in worktree_records(root)
            if candidate.get("worktree") == str(target)
        ),
        None,
    )
    if args.dry_run:
        classification = (
            classify_worktree(root, record)
            if record is not None
            else {
                "path": str(target),
                "class": "unknown",
                "cleanup_eligible": False,
                "reason": "worktree is not registered",
            }
        )
        return {
            "ok": True,
            "operation": "cleanup-dry-run",
            "read_only": True,
            "worktree": classification,
        }
    if record is not None and target.exists():
        if "detached" in record:
            if not args.subject_sha:
                raise OrchestrateError(
                    "targeted review cleanup requires --subject-sha because Git cannot"
                    " prove reviewer liveness"
                )
        else:
            classification = classify_worktree(root, record)
            if not classification.get("cleanup_eligible"):
                raise OrchestrateError(
                    "classifier rejected lane cleanup: "
                    + str(classification.get("reason", "unknown state"))
                )
    return cleanup_single_worktree(args, root, time.monotonic())
