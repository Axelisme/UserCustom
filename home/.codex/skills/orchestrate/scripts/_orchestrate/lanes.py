from __future__ import annotations

import argparse
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError, require_identifier
from .git_ops import absorption_probe, changed_paths_since_fork, exact_commit, is_ancestor, lane_absorption, managed_worktree_root, merge_tree_probe, require_managed_worktree, require_task_lane_refs, run_git, worktree_evidence, worktree_records
from .findings import CLOSES_FINDING_PATTERN, closed_finding_ids, dedup_findings, read_findings_ledger, task_id_from_ref

COLLECT_REVIEW_KINDS = (
    "different-identity",
    "focused",
    "root-spot",
    "mechanical",
)


SEAM_READY_PATTERN = re.compile(r"^Seam-Ready:\s*true\s*$", re.IGNORECASE | re.MULTILINE)


SPECULATIVE_BASE_PATTERN = re.compile(
    r"^Speculative-Base:\s*true\s*$", re.IGNORECASE | re.MULTILINE
)


DEPENDS_LANE_PATTERN = re.compile(
    r"^Depends-Lane:\s*([0-9a-fA-F]{40,64})\s*$", re.MULTILINE
)


ITEM_TRAILER_PATTERN = re.compile(r"^Item:\s*(\S+)\s*$", re.MULTILINE)


def speculative_dependency_records(
    root: Path, revision: str, *, exclude: str | None = None
) -> list[dict[str, Any]]:
    """Extract and normalize Speculative-Base/Depends-Lane evidence from Git history."""
    revision_range = f"{exclude}..{revision}" if exclude else revision
    log = run_git(root, "log", "--format=%H%x1f%B%x1e", revision_range)
    records: list[dict[str, Any]] = []
    for chunk in log.stdout.split("\x1e"):
        sha, _, body = chunk.strip().partition("\x1f")
        if not sha or not SPECULATIVE_BASE_PATTERN.search(body):
            continue
        dependencies = [
            exact_commit(root, dep, label=f"Depends-Lane in {sha[:12]}")
            for dep in DEPENDS_LANE_PATTERN.findall(body)
        ]
        if dependencies:
            records.append({"composite_sha": sha, "dependencies": dependencies})
    return records


def flatten_speculative_dependencies(
    records: list[dict[str, Any]], *, context: str
) -> list[str]:
    dependencies = [
        dependency
        for record in records
        for dependency in record["dependencies"]
    ]
    if len(set(dependencies)) != len(dependencies):
        raise OrchestrateError(f"duplicate speculative dependencies in {context}")
    return dependencies


def compose_dependency_chain(root: Path, composite: str) -> dict[str, Any]:
    """Read only the synthetic first-parent chain created by one compose operation."""
    current = composite
    signature: str | None = None
    commits: list[str] = []
    dependencies: list[str] = []
    while True:
        body = run_git(root, "log", "-1", "--format=%B", current).stdout
        first_line = body.splitlines()[0].strip() if body.splitlines() else ""
        if not SPECULATIVE_BASE_PATTERN.search(body):
            break
        if signature is None:
            signature = first_line
        elif first_line != signature:
            break
        recorded = [
            exact_commit(root, dep, label=f"Depends-Lane in {current[:12]}")
            for dep in DEPENDS_LANE_PATTERN.findall(body)
        ]
        if not recorded:
            raise OrchestrateError(
                f"speculative compose commit {current[:12]} has no Depends-Lane trailer"
            )
        commits.append(current)
        dependencies.extend(recorded)
        parents = run_git(root, "rev-list", "--parents", "-1", current).stdout.split()
        if len(parents) < 2:
            raise OrchestrateError(
                f"speculative compose commit {current[:12]} has no first parent"
            )
        current = parents[1]
    if not commits:
        raise OrchestrateError(
            f"{composite[:12]} is not the head of a compose-base synthetic chain"
        )
    if len(set(dependencies)) != len(dependencies):
        raise OrchestrateError("duplicate dependencies in compose-base synthetic chain")
    return {
        "base": current,
        "signature": signature,
        "commits": commits,
        "dependencies": dependencies,
    }


def match_final_dependencies(
    root: Path, recorded: list[str], finals: list[str]
) -> dict[str, str]:
    """Match each recorded dependency to exactly one final predecessor SHA."""
    if len(set(finals)) != len(finals):
        raise OrchestrateError("duplicate final predecessor SHAs")
    matches: dict[str, str] = {}
    used: set[str] = set()
    for dependency in recorded:
        candidates = [final for final in finals if is_ancestor(root, dependency, final)]
        if not candidates:
            raise OrchestrateError(
                f"missing final predecessor for recorded dependency {dependency[:12]}"
            )
        if len(candidates) > 1:
            raise OrchestrateError(
                f"ambiguous final predecessors for recorded dependency {dependency[:12]}"
            )
        final = candidates[0]
        matches[dependency] = final
        used.add(final)
    unused = [final for final in finals if final not in used]
    if unused:
        raise OrchestrateError(
            "unused final predecessor SHA(s): " + ", ".join(sha[:12] for sha in unused)
        )
    return matches


def command_lane_create(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    lane = require_identifier(args.lane, label="lane")
    base = exact_commit(root, args.base, label="base")
    branch = f"agent/{task_id}/{lane}"
    target = require_managed_worktree(
        root,
        (
            Path(args.worktree).resolve()
            if args.worktree
            else managed_worktree_root(root) / f"{task_id}-{lane}"
        ),
        kind="lane",
    )
    branch_exists = (
        run_git(
            root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False
        ).returncode
        == 0
    )
    record = next(
        (
            record
            for record in worktree_records(root)
            if record.get("branch") == f"refs/heads/{branch}"
        ),
        None,
    )
    if record is not None:
        # A prior run completed; rerunning after an abort reports instead of failing.
        existing = Path(str(record.get("worktree"))).resolve()
        if existing != target:
            raise OrchestrateError(
                f"lane branch is already checked out elsewhere: {existing}"
            )
        evidence = worktree_evidence(target, started=started)
        if evidence["head"] != base:
            raise OrchestrateError(
                f"existing lane has advanced to {evidence['head']}; it is not a"
                f" recovery of creation at requested base {base}"
            )
        if not evidence["clean"]:
            raise OrchestrateError("existing lane worktree is dirty")
        return {
            "ok": True,
            "operation": "lane-create",
            "base": base,
            "recovered": "already-created",
            **evidence,
        }
    if target.exists():
        raise OrchestrateError(f"worktree path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists:
        # Branch landed but the worktree add aborted: reuse it only at the exact base.
        head = run_git(root, "rev-parse", f"refs/heads/{branch}").stdout.strip()
        if head != base:
            raise OrchestrateError(
                f"lane branch already exists at {head}, not the requested base"
            )
        run_git(root, "worktree", "add", str(target), branch)
        return {
            "ok": True,
            "operation": "lane-create",
            "base": base,
            "recovered": "reused-existing-branch",
            **worktree_evidence(target, started=started),
        }
    run_git(root, "worktree", "add", "-b", branch, str(target), base)
    return {
        "ok": True,
        "operation": "lane-create",
        "base": base,
        **worktree_evidence(target, started=started),
    }


def command_compose_base(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    name = require_identifier(args.name, label="name")
    base = exact_commit(root, args.base, label="base")
    lanes = [
        exact_commit(root, value, label=f"lane[{index}]")
        for index, value in enumerate(args.lane)
    ]
    if len(set(lanes)) != len(lanes):
        raise OrchestrateError("duplicate lane SHAs in compose-base")
    branch = f"spec/{task_id}/{name}"
    ref = f"refs/heads/{branch}"
    if run_git(root, "show-ref", "--verify", "--quiet", ref, check=False).returncode == 0:
        # A prior run completed; verify the same inputs and report instead of failing.
        head = run_git(root, "rev-parse", ref).stdout.strip()
        for required in (base, *lanes):
            if (
                run_git(
                    root, "merge-base", "--is-ancestor", required, head, check=False
                ).returncode
                != 0
            ):
                raise OrchestrateError(
                    f"spec branch {branch} exists but does not contain {required};"
                    " pick a new --name for different inputs"
                )
        chain = compose_dependency_chain(root, head)
        effective_lanes = [lane for lane in lanes if not is_ancestor(root, lane, base)]
        recorded = chain["dependencies"]
        expected_signature = f"compose speculative base {task_id}/{name}"
        if (
            chain["base"] != base
            or chain["signature"] != expected_signature
            or len(recorded) != len(effective_lanes)
            or set(recorded) != set(effective_lanes)
        ):
            raise OrchestrateError(
                f"spec branch {branch} was composed from different lane inputs;"
                " pick a new --name"
            )
        return {
            "ok": True,
            "operation": "compose-base",
            "recovered": "already-composed",
            "spec_ref": branch,
            "composite_sha": head,
            "base": base,
            "lanes": lanes,
            "observed_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    current = base
    for lane_sha in lanes:
        if (
            run_git(
                root, "merge-base", "--is-ancestor", lane_sha, current, check=False
            ).returncode
            == 0
        ):
            continue
        merged = run_git(
            root, "merge-tree", "--write-tree", current, lane_sha, check=False
        )
        if merged.returncode != 0:
            raise OrchestrateError(
                f"lanes textually collide at {lane_sha}: structural hazard —"
                " recut the seam or serialize; compose-base never resolves conflicts"
            )
        tree = merged.stdout.splitlines()[0].strip()
        message = (
            f"compose speculative base {task_id}/{name}\n\n"
            "Speculative-Base: true\n"
            f"Depends-Lane: {lane_sha}\n"
        )
        current = run_git(
            root,
            "commit-tree",
            tree,
            "-p",
            current,
            "-p",
            lane_sha,
            "-m",
            message,
        ).stdout.strip()
    if current == base:
        raise OrchestrateError("all lanes are already contained in the base")
    run_git(root, "branch", branch, current)
    return {
        "ok": True,
        "operation": "compose-base",
        "spec_ref": branch,
        "composite_sha": current,
        "base": base,
        "lanes": lanes,
        "speculative": True,
        "note": "not integrable until every Depends-Lane SHA is on the task branch",
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_compose_base_revalidate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    task_ref = args.task_ref
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    require_identifier(task_ref.split("/", 1)[1], label="task ref id")
    composite = exact_commit(root, args.composite, label="composite")
    successor = exact_commit(root, args.successor, label="successor")
    finals = [
        exact_commit(root, value, label=f"lane[{index}]")
        for index, value in enumerate(args.lane)
    ]
    if not is_ancestor(root, composite, successor):
        raise OrchestrateError("successor must descend from composite")
    task_head = run_git(root, "rev-parse", f"{task_ref}^{{commit}}").stdout.strip()
    recorded = compose_dependency_chain(root, composite)["dependencies"]
    matches = match_final_dependencies(root, recorded, finals)
    deps: list[dict[str, Any]] = []
    followup_files: set[str] = set()
    for dependency in recorded:
        final = matches[dependency]
        paths = (
            sorted(
                path
                for path in run_git(
                    root, "diff", "--name-only", dependency, final
                ).stdout.splitlines()
                if path.strip()
            )
            if final != dependency
            else []
        )
        followup_files.update(paths)
        deps.append(
            {
                "recorded": dependency,
                "final": final,
                "follow_up_present": final != dependency,
                "follow_up_paths": paths,
                "final_on_task": is_ancestor(root, final, task_head),
                "successor_absorption": absorption_probe(root, final, successor),
            }
        )
    successor_files = {
        path
        for path in run_git(
            root, "diff", "--name-only", composite, successor
        ).stdout.splitlines()
        if path.strip()
    }
    successor_overlap = sorted(successor_files & followup_files)
    task_successor_probe = merge_tree_probe(root, task_head, successor)
    missing_from_task = [
        entry
        for entry in deps
        if not entry["final_on_task"] and entry["successor_absorption"] is None
    ]
    recompose_needed = not task_successor_probe["clean"] or bool(missing_from_task)
    return {
        "ok": True,
        "operation": "compose-base-revalidate",
        "read_only": True,
        "task_ref": task_ref,
        "task_head": task_head,
        "composite_sha": composite,
        "successor_sha": successor,
        "deps": deps,
        "follow_ups_landed": any(entry["follow_up_present"] for entry in deps),
        "successor_touches_followups": successor_overlap,
        "task_successor_merge_tree": task_successor_probe,
        "recompose_needed": recompose_needed,
        "required_dep_shas": [entry["final"] for entry in deps],
    }


def command_slice_milestone(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    item_id = require_identifier(args.item, label="item")
    head = run_git(root, "rev-parse", "HEAD").stdout.strip()
    parents = run_git(
        root, "rev-list", "--parents", "-1", head
    ).stdout.strip().split()[1:]
    body = run_git(root, "log", "-1", "--format=%B", head).stdout
    item_match = ITEM_TRAILER_PATTERN.search(body)
    if item_match is not None and item_match.group(1) != item_id:
        raise OrchestrateError(
            f"HEAD carries Item: {item_match.group(1)}, not {item_id};"
            " commit the item's work first or fix the --item"
        )
    evidence = worktree_evidence(root, started=started)
    payload = {
        "ok": True,
        "operation": "slice-milestone",
        "read_only": True,
        "item_id": item_id,
        "subject_sha": head,
        "parents": parents,
        "item_trailer_present": item_match is not None,
        "seam_ready": bool(SEAM_READY_PATTERN.search(body)),
        "closes_findings": CLOSES_FINDING_PATTERN.findall(body),
        "outcome": args.outcome,
        "evidence": None,
        **evidence,
    }
    if not evidence["clean"]:
        payload["warning"] = (
            "worktree is dirty: subject_sha does not carry the uncommitted work"
        )
    return payload


def command_collect(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    if not (args.authorized_sha and args.review_kind):
        raise OrchestrateError(
            "collect requires both --authorized-sha and --review-kind"
        )
    branch = run_git(
        root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False
    )
    task_ref = branch.stdout.strip() if branch.returncode == 0 else ""
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(
            "integration checkout must be on task/<task>; task identity is derived"
            " from the current branch"
        )
    require_task_lane_refs(task_ref, args.lane_ref)
    review_kind = args.review_kind
    authorized = exact_commit(root, args.authorized_sha, label="authorized SHA")
    authorization = {"authorization_source": "declared"}
    task_head = run_git(root, "rev-parse", "HEAD").stdout.strip()
    if is_ancestor(root, authorized, task_head):
        # Recovery precedes lane-ref resolution, so cleanup may already have deleted it.
        return {
            "ok": True,
            "operation": "collect",
            "recovered": "already-collected",
            "task_ref": task_ref,
            "lane_ref": args.lane_ref,
            "authorized_sha": authorized,
            "declared_review_kind": review_kind,
            "verdict_inferred": False,
            **authorization,
            "task_sha": task_head,
            "observed_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    lane_head = run_git(root, "rev-parse", f"{args.lane_ref}^{{commit}}").stdout.strip()
    if lane_head != authorized:
        raise OrchestrateError(
            f"lane target differs from authorized SHA: {lane_head} != {authorized}"
        )
    # A reused lane ref is git-valid but collects the wrong work. Derive the lane's
    # Item so a reuse is always visible, and enforce it when --item names one — the
    # same trailer semantics `slice milestone` already uses.
    lane_item_match = ITEM_TRAILER_PATTERN.search(
        run_git(root, "log", "-1", "--format=%B", lane_head).stdout
    )
    lane_item = lane_item_match.group(1) if lane_item_match is not None else None
    requested = getattr(args, "item", None)
    if requested is not None:
        requested_item = require_identifier(requested, label="item")
        if lane_item is not None and lane_item != requested_item:
            raise OrchestrateError(
                f"lane {args.lane_ref} carries Item: {lane_item}, not {requested_item};"
                " a reused lane ref collects the wrong item — verify the lane or"
                " fix --item"
            )
    speculative_records = speculative_dependency_records(
        root, authorized, exclude=task_head
    )
    speculative_dependencies = flatten_speculative_dependencies(
        speculative_records, context="collect target"
    )
    for record in speculative_records:
        for dependency in record["dependencies"]:
            if not is_ancestor(root, dependency, task_head):
                raise OrchestrateError(
                    f"lane stacks on speculative composite base"
                    f" {record['composite_sha'][:12]} whose dependency"
                    f" {dependency[:12]} is not on {task_ref}; collect that lane first"
                )
    closed_here = closed_finding_ids(root, authorized)
    gating_open: list[str] = []
    for fid, rec in dedup_findings(
        read_findings_ledger(root, task_id_from_ref(task_ref))
    ).items():
        if rec["propagation"] != "gates-the-slice" or fid in closed_here:
            continue
        subject = rec.get("subject_sha")
        if subject and not is_ancestor(root, subject, authorized):
            continue
        gating_open.append(fid)
    if gating_open:
        raise OrchestrateError(
            "open gating finding(s) block collect: "
            + ", ".join(sorted(gating_open))
            + "; land a Closes-Finding commit on the lane, or reroute the finding"
        )
    git_dir = Path(run_git(root, "rev-parse", "--absolute-git-dir").stdout.strip())
    if (git_dir / "MERGE_HEAD").exists():
        raise OrchestrateError(
            "unfinished merge in progress: resolve it or run `git merge --abort`,"
            " then rerun collect"
        )
    if run_git(root, "status", "--porcelain").stdout.strip():
        raise OrchestrateError("integration worktree is dirty")
    preflight = merge_tree_probe(root, task_head, authorized)
    if not preflight["clean"]:
        raise OrchestrateError(
            "merge-tree preflight failed; collect is fail-closed: "
            + str(preflight.get("error", "unknown conflict"))
        )
    lane_head_again = run_git(
        root, "rev-parse", f"{args.lane_ref}^{{commit}}"
    ).stdout.strip()
    if lane_head_again != authorized:
        raise OrchestrateError("lane target drifted after merge preflight")
    run_git(root, "merge", "--no-ff", "--no-edit", authorized)
    evidence = worktree_evidence(root, started=started)
    if not evidence["clean"]:
        raise OrchestrateError("collection left the integration worktree dirty")
    return {
        "ok": True,
        "operation": "collect",
        "task_ref": task_ref,
        "lane_ref": args.lane_ref,
        "authorized_sha": authorized,
        "declared_review_kind": review_kind,
        "verdict_inferred": False,
        "item_id": lane_item,
        "item_trailer_present": lane_item is not None,
        **authorization,
        "before": task_head,
        "speculative_dependencies": speculative_records,
        "speculative_dependency_shas": speculative_dependencies,
        "preflight": preflight,
        "preflight_tree": preflight["tree"],
        **evidence,
    }


def command_slice_status(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_ref = args.task_ref
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    task_id = require_identifier(task_ref.split("/", 1)[1], label="task ref id")
    task_sha = run_git(root, "rev-parse", f"{task_ref}^{{commit}}").stdout.strip()
    worktrees = {
        str(record.get("branch", "")).removeprefix("refs/heads/"): record
        for record in worktree_records(root)
        if isinstance(record.get("branch"), str)
    }
    lanes: list[dict[str, Any]] = []
    lane_changed: dict[str, set[str]] = {}
    refs = run_git(
        root,
        "for-each-ref",
        "--format=%(refname:short) %(objectname)",
        f"refs/heads/agent/{task_id}/",
    ).stdout
    for line in refs.splitlines():
        branch, _, head = line.strip().partition(" ")
        entry: dict[str, Any] = {"lane_ref": branch, "head": head}
        record = worktrees.get(branch)
        if record is not None:
            worktree_path = Path(str(record.get("worktree")))
            entry["worktree"] = str(worktree_path)
            entry["dirty"] = (
                bool(run_git(worktree_path, "status", "--porcelain").stdout.strip())
                if worktree_path.exists()
                else None
            )
        body = run_git(root, "log", "-1", "--format=%B", head).stdout
        entry["seam_ready"] = bool(SEAM_READY_PATTERN.search(body))
        changed = changed_paths_since_fork(root, task_sha, head)
        entry["changed_path_count"] = len(changed)
        lane_changed[branch] = set(changed)
        absorption = lane_absorption(root, head, task_sha)
        if absorption is not None:
            entry["state"] = "absorbed"
            entry["absorption"] = absorption
        else:
            entry["state"] = "writing"
        lanes.append(entry)
    overlaps: list[dict[str, Any]] = []
    names = sorted(lane_changed)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            shared_paths = sorted(lane_changed[first] & lane_changed[second])
            if shared_paths:
                overlaps.append({"lanes": [first, second], "paths": shared_paths})
    return {
        "ok": True,
        "operation": "slice-status",
        "read_only": True,
        "task_ref": task_ref,
        "task_sha": task_sha,
        "write_set_overlaps": overlaps,
        "lanes": lanes,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
