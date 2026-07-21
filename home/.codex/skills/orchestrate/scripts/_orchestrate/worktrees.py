from __future__ import annotations

import argparse
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError, require_identifier
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
        # A reviewer's liveness is genuinely unknowable, but the review's *relevance*
        # is not: once the subject is absorbed into a task branch the review is moot,
        # and that is derived from Git alone — no sidecar state that could drift and
        # strand or wrongly delete a checkout someone still holds.
        base["kind"] = "review"
        if not isinstance(head, str):
            base.update({"class": "unknown", "reason": "missing worktree HEAD"})
            return base
        if not path.exists():
            base.update(
                {"class": "unknown", "reason": "worktree directory is missing"}
            )
            return base
        dirty = bool(run_git(path, "status", "--porcelain").stdout.strip())
        base["dirty"] = dirty
        absorbed_into = next(
            (
                candidate
                for candidate in run_git(
                    root,
                    "for-each-ref",
                    "--format=%(refname:short)",
                    "refs/heads/task/",
                ).stdout.split()
                if is_ancestor(root, head, candidate)
            ),
            None,
        )
        base["absorbed_into"] = absorbed_into
        if dirty:
            classification = "active"
            reason = "review worktree is dirty; it may hold a reproducer"
        elif absorbed_into is not None:
            classification = "safe-to-remove"
            reason = f"review subject is absorbed into {absorbed_into}"
        else:
            classification = "active"
            reason = "review subject is not absorbed; a reviewer may still hold it"
        base.update(
            {
                "class": classification,
                "reason": reason,
                "cleanup_eligible": classification == "safe-to-remove" and not dirty,
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
    # Git can prove absorption and dirt, but has no visibility into a runtime
    # fleet's cwd leases. Keep the legacy name as an equal compatibility alias
    # while callers migrate to the explicit Git-only projection.
    git_safe_to_remove = [
        entry["path"] for entry in worktrees if entry["cleanup_eligible"]
    ]
    return {
        "ok": True,
        "operation": "reconcile",
        "read_only": True,
        "runtime_lease_safety": "unchecked",
        "worktrees": worktrees,
        "summary": summary,
        "git_safe_to_remove": git_safe_to_remove,
        "safe_to_remove": git_safe_to_remove,
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
    root = Path(args.root).resolve()
    slice_report = command_slice_status(
        argparse.Namespace(root=args.root, task_ref=task_ref)
    )
    findings_report = command_findings_status(
        argparse.Namespace(root=args.root, task_id=task_id, task_ref=task_ref)
    )
    reconcile_report = command_reconcile(argparse.Namespace(root=args.root))
    reviewed_pass = sorted(
        {
            marker["subject_sha"]
            for marker in findings_report["review_outcomes"]
            if marker.get("verdict") == "pass"
        }
    )
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
        # Derived here rather than carried as its own ledger key: a review that
        # ended blocked is not clean, and one place deciding that cannot drift
        # from another.
        "reviewed_clean": reviewed_pass,
        # The subset of reviewed_clean not yet on the task branch: a subject that
        # passed review but whose SHA is not an ancestor of the task head. This is
        # the resumable "validated, unlanded" state — after a restart or a landing
        # blocked by a tool-permission failure (a cherry-pick escalation limit, a
        # read-only integration checkout), root collects these SHAs without paying
        # for a second review, because the pass marker is a durable ledger row that
        # outlives the interruption. It is a pure derived read of the same markers,
        # never a stored flag, so it cannot drift from reviewed_clean.
        "validated_unlanded": sorted(
            sha for sha in reviewed_pass if not is_ancestor(root, sha, slice_report["task_sha"])
        ),
        # This report only composes Git-derived reads; it cannot inspect a
        # runtime fleet's cwd leases.
        "runtime_lease_safety": "unchecked",
        "git_safe_to_remove": reconcile_report["git_safe_to_remove"],
        "safe_to_remove": reconcile_report["safe_to_remove"],
        # What `cleanup --wave-boundary` would clear right now: this task's lane
        # worktrees, whatever their absorbed/dirty state. It is the trigger for the
        # boundary wrap-up — act on it when it is non-empty, skip the step when it is
        # empty rather than running a tidy that has nothing to tidy.
        "wave_boundary_removable": [
            lane["worktree"]
            for lane in slice_report["lanes"]
            if lane.get("worktree")
        ],
    }
    result = {
        "ok": True,
        "operation": "wave-status",
        "read_only": True,
        "task_ref": task_ref,
        "task_id": task_id,
        "handoff": handoff,
    }
    if getattr(args, "summary", False):
        # The handoff rollup is the summary; the three full reports are what make
        # the default output large enough to crowd a context window.
        return result
    return {
        **result,
        "slice": slice_report,
        "findings": findings_report,
        "reconcile": reconcile_report,
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
        "runtime_lease_safety": "unchecked",
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


def cleanup_wave_boundary(
    args: argparse.Namespace, root: Path, started: float
) -> dict[str, Any]:
    """Remove this task's leftover lane worktrees at a wave boundary root has judged
    safe. Unlike targeted cleanup this does not require each lane absorbed or clean:
    a half-abandoned or forgotten lane is exactly the target, and whether the boundary
    is safe is root's call, not a per-lane proof. What it will not do is guess across
    task boundaries. Task identity comes from the integration checkout's own branch;
    only ``agent/<task>/*`` lane worktrees of that task are removed; the integration
    checkout itself is never touched; and detached review worktrees — which carry no
    task identity in ref or path — are always skipped, never attributed by guess. That
    scoping is what lets this reintroduce a bulk sweep the old absorbed-only sweep had
    to disable, whose hazard was exactly the review worktree it could not attribute."""
    head = run_git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if not head.startswith("task/") or head.count("/") != 1:
        raise OrchestrateError(
            "wave-boundary cleanup derives its task from the integration checkout's"
            f" current branch, which must be task/<task>; got {head!r}"
        )
    task_id = require_identifier(head.split("/", 1)[1], label="task id")
    lane_prefix = f"agent/{task_id}/"
    if not args.dry_run:
        worktree_metadata_writability_preflight(root)
    managed = managed_worktree_root(root).resolve()
    root_path = root.resolve()
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
        if path.resolve() == root_path:
            entry.update(kind="integration", action="skipped",
                         reason="integration checkout is never swept")
            continue
        if "detached" in record:
            entry.update(
                kind="review", action="skipped",
                reason="detached review worktree carries no task identity; remove it"
                " by exact cleanup --worktree --subject-sha",
            )
            continue
        branch = str(record.get("branch", "")).removeprefix("refs/heads/")
        entry.update(kind="lane", branch=branch)
        if not branch.startswith(lane_prefix):
            entry.update(action="skipped", reason=f"not a lane of {head}")
            continue
        exists = path.exists()
        entry["dirty"] = (
            bool(run_git(path, "status", "--porcelain").stdout.strip())
            if exists
            else None
        )
        if args.dry_run:
            entry["action"] = "eligible"
            continue
        if exists:
            # --force because dirty leftovers are the point: at a boundary root
            # declared clean, an uncommitted half-abandoned lane is noise to clear,
            # not work to protect. A deleted branch is reflog-recoverable; only its
            # worktree's uncommitted diff is not, and clearing that is the request.
            run_git(root, "worktree", "remove", "--force", str(path))
        else:
            run_git(root, "worktree", "prune")
            entry["recovered"] = "pruned-stale-metadata"
        run_git(root, "branch", "-D", branch)
        entry["action"] = "removed"
    return {
        "ok": True,
        "operation": "cleanup-wave-boundary",
        "runtime_lease_safety": "unchecked",
        "task_ref": head,
        "dry_run": bool(args.dry_run),
        "entries": entries,
        "removed": sum(1 for entry in entries if entry.get("action") == "removed"),
        "eligible": sum(1 for entry in entries if entry.get("action") == "eligible"),
        "skipped": sum(1 for entry in entries if entry.get("action") == "skipped"),
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_cleanup(args: argparse.Namespace) -> dict[str, Any]:
    """Require an exact target and classifier approval before cleanup mutates state."""
    root = Path(args.root).resolve()
    if getattr(args, "wave_boundary", False):
        if args.worktree:
            raise OrchestrateError(
                "--wave-boundary sweeps this task's lanes; it takes no --worktree"
            )
        return cleanup_wave_boundary(args, root, time.monotonic())
    if not args.worktree:
        reconciliation = command_reconcile(argparse.Namespace(root=str(root)))
        if args.dry_run:
            return {
                "ok": True,
                "operation": "cleanup-dry-run",
                "read_only": True,
                "runtime_lease_safety": "unchecked",
                "bulk_cleanup_disabled": True,
                "worktrees": reconciliation["worktrees"],
                "git_safe_to_remove": reconciliation["git_safe_to_remove"],
                "safe_to_remove": reconciliation["safe_to_remove"],
            }
        git_safe_to_remove = reconciliation["git_safe_to_remove"]
        hint = ", ".join(git_safe_to_remove) if git_safe_to_remove else "none"
        raise OrchestrateError(
            "bulk cleanup is disabled because reviewer liveness is not durable;"
            f" Git-safe-to-remove targets: {hint}; runtime lease safety is unchecked"
            " and requires runtime binding lease preflight; run reconcile, then"
            " cleanup each exact --worktree target"
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
            "runtime_lease_safety": "unchecked",
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
