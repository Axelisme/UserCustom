"""Git-backed lane and task-integration command seams."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .git_ops import exact_commit, managed_worktree_root, run_git, worktree_records
from .primitives import OrchestrateError, require_identifier


def _lane_identity(args: argparse.Namespace) -> tuple[str, str, Path, str]:
    task = require_identifier(str(args.task_id), label="task id")
    lane = require_identifier(str(args.lane_id), label="lane id")
    if lane == "integration":
        raise OrchestrateError("lane id must not be 'integration': that name is reserved for the integration branch")
    root = Path(args.root).resolve()
    branch = f"wave/{task}/{lane}"
    path = managed_worktree_root(root) / f"{task}-{lane}"
    return task, lane, path, branch


def _lane_base_ref(task: str, lane: str) -> str:
    return f"refs/orchestrate/{task}/{lane}/base"


def _lane_base(root: Path, task: str, lane: str) -> str:
    """Read the exact base recorded at ``lane create`` time.

    Stored as a ref, not derived from topology, for the same reason the
    integration base is: it is a property of the lane, not of any one commit,
    and a missing ref must fail closed rather than silently widen the walk
    used to anchor ``Immutable:`` declarations.
    """
    ref = _lane_base_ref(task, lane)
    probe = run_git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    base = probe.stdout.strip()
    if probe.returncode or not base:
        raise OrchestrateError(
            f"lane base ref is missing: {ref}; recreate the lane worktree or "
            f"restore it with git update-ref {ref} <exact base sha>"
        )
    return base


def _branch_exists(root: Path, branch: str) -> bool:
    return run_git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0


def _record_for(root: Path, path: Path) -> dict[str, Any] | None:
    resolved = path.resolve()
    for record in worktree_records(root):
        raw = record.get("worktree")
        if not isinstance(raw, str) or Path(raw).resolve() != resolved:
            continue
        return record
    return None


def _record_branch(record: dict[str, Any]) -> str | None:
    raw = record.get("branch")
    if not isinstance(raw, str) or not raw:
        return None
    return raw.removeprefix("refs/heads/")


def _status(
    root: Path,
    path: Path,
    expected_branch: str,
    *,
    require_expected_branch: bool = False,
    identity_label: str = "implementation worktree",
) -> dict[str, Any]:
    record = _record_for(root, path)
    if record is None:
        return {"ok": True, "operation": "worktree-status", "exists": False, "path": str(path), "branch": expected_branch, "head": None, "tree": None, "clean": False, "changed_paths": []}
    live_branch = _record_branch(record)
    if not path.exists():
        return {"ok": True, "operation": "worktree-status", "exists": False, "path": str(path), "branch": live_branch, "head": record.get("HEAD"), "tree": None, "clean": False, "changed_paths": []}
    if require_expected_branch and live_branch != expected_branch:
        rendered_live = live_branch if live_branch else "detached"
        raise OrchestrateError(
            f"{identity_label} must be attached to exact derived branch {expected_branch}; "
            f"live state is {rendered_live}"
        )
    changed = [line for line in run_git(path, "status", "--porcelain").stdout.splitlines() if line]
    detached = live_branch is None
    return {
        "ok": True,
        "operation": "worktree-status",
        "exists": True,
        "path": str(path),
        "branch": live_branch,
        **({"detached": True} if detached else {}),
        "head": record.get("HEAD"),
        "tree": "dirty" if changed else "clean",
        "clean": not changed,
        "changed_paths": [line[3:] if len(line) >= 4 else line for line in changed],
    }


def command_lane_create(args: argparse.Namespace) -> dict[str, Any]:
    task, lane, path, branch = _lane_identity(args)
    root = Path(args.root).resolve()
    try:
        base = exact_commit(root, str(args.base), label="base")
    except OrchestrateError as exc:
        raise OrchestrateError(f"invalid base: {exc}") from exc
    if _branch_exists(root, branch) or os.path.lexists(path):
        raise OrchestrateError(f"derived worktree path or branch already exists: {path} / {branch}")
    path.parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "worktree", "add", "-b", branch, str(path), base)
    run_git(root, "update-ref", _lane_base_ref(task, lane), base)
    evidence = _status(root, path, branch)
    return {
        "ok": True,
        "operation": "lane-create",
        "task_id": task,
        "lane_id": lane,
        "branch": branch,
        "worktree": str(path),
        "base": base,
        "head": evidence["head"],
        "tree": evidence["tree"],
        "clean": evidence["clean"],
    }


def _lane_status(root: Path, task: str, lane: str) -> dict[str, Any]:
    branch = f"wave/{task}/{lane}"
    path = managed_worktree_root(root) / f"{task}-{lane}"
    state = _status(root, path, branch, identity_label="lane worktree")
    state.update({"operation": "lane-status", "task_id": task, "lane_id": lane})
    return state


def _list_lanes(root: Path, task: str) -> list[str]:
    """List every lane branch of one task from live Git refs, oldest name first."""
    prefix = f"wave/{task}/"
    raw = run_git(root, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{prefix}").stdout
    lanes: list[str] = []
    for line in raw.splitlines():
        if not line.startswith(prefix):
            continue
        remainder = line[len(prefix) :]
        if not remainder or "/" in remainder or remainder == "integration":
            continue
        lanes.append(remainder)
    return sorted(lanes)


def command_lane_status(args: argparse.Namespace) -> dict[str, Any]:
    task = require_identifier(str(args.task_id), label="task id")
    root = Path(args.root).resolve()
    lane_id = getattr(args, "lane_id", None)
    if lane_id:
        lane = require_identifier(str(lane_id), label="lane id")
        return _lane_status(root, task, lane)
    lanes = _list_lanes(root, task)
    return {
        "ok": True,
        "operation": "lane-status",
        "task_id": task,
        "lanes": [_lane_status(root, task, lane) for lane in lanes],
    }


def command_lane_drop(args: argparse.Namespace) -> dict[str, Any]:
    task, lane, path, branch = _lane_identity(args)
    root = Path(args.root).resolve()
    state = _status(root, path, branch, identity_label="lane worktree")
    if not state["exists"]:
        raise OrchestrateError(f"managed lane worktree does not exist: {path}")
    if not state["clean"]:
        raise OrchestrateError(f"cannot remove worktree because it is not clean: {path}")
    run_git(root, "worktree", "remove", str(path))
    return {
        "ok": True,
        "operation": "lane-drop",
        "task_id": task,
        "lane_id": lane,
        "worktree": str(path),
        "branch": branch,
        "removed": True,
    }


def _integration_identity(args: argparse.Namespace) -> tuple[str, Path, str]:
    task = require_identifier(str(args.task_id), label="task id")
    root = Path(args.root).resolve()
    branch = f"wave/{task}/integration"
    path = managed_worktree_root(root) / f"{task}-integration"
    return task, path, branch


def _integration_base_ref(task: str) -> str:
    return f"refs/orchestrate/{task}/integration/base"


def _candidate_ref(task: str) -> str:
    return f"refs/orchestrate/{task}/candidate"


def _acceptance_worktree_path(root: Path, task: str) -> Path:
    return managed_worktree_root(root) / f"{task}-acceptance"


def command_integration_create(args: argparse.Namespace) -> dict[str, Any]:
    task, path, branch = _integration_identity(args)
    root = Path(args.root).resolve()
    try:
        base = exact_commit(root, str(args.base), label="base")
    except OrchestrateError as exc:
        raise OrchestrateError(f"invalid base: {exc}") from exc
    acceptance_path = _acceptance_worktree_path(root, task)
    if _branch_exists(root, branch) or os.path.lexists(path) or os.path.lexists(acceptance_path):
        raise OrchestrateError(
            f"derived worktree path or branch already exists: {path} / {branch} / {acceptance_path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "worktree", "add", "-b", branch, str(path), base)
    run_git(root, "update-ref", _integration_base_ref(task), base)
    # Detached HEAD, not a branch: the acceptance worktree is pinned to
    # whatever exact SHA `publish` last checked out, not to any branch tip.
    acceptance_path.parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "worktree", "add", "--detach", str(acceptance_path), base)
    evidence = _status(root, path, branch)
    acceptance_evidence = _status(root, acceptance_path, "", identity_label="acceptance worktree")
    return {
        "ok": True,
        "operation": "integration-create",
        "task_id": task,
        "base_ref": _integration_base_ref(task),
        "branch": branch,
        "worktree": str(path),
        "base": base,
        "head": evidence["head"],
        "tree": evidence["tree"],
        "clean": evidence["clean"],
        "acceptance_worktree": str(acceptance_path),
        "acceptance_head": acceptance_evidence["head"],
    }


def _integration_base(root: Path, task: str) -> str:
    """Read the exact base recorded at create time.

    The base is a ref rather than a message trailer because it is a property of
    the task, not of any one commit; a reflog would expire and leave the walk
    unbounded, so a missing ref fails closed instead of reporting a wider range.
    """
    ref = _integration_base_ref(task)
    probe = run_git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    base = probe.stdout.strip()
    if probe.returncode or not base:
        raise OrchestrateError(
            f"integration base ref is missing: {ref}; recreate the integration worktree or "
            f"restore it with git update-ref {ref} <exact base sha>"
        )
    return base


def _collected_integrations(root: Path, task: str, branch: str) -> list[dict[str, Any]]:
    if not _branch_exists(root, branch):
        return []
    base = _integration_base(root, task)
    raw = run_git(root, "rev-list", "--first-parent", "--reverse", f"{base}..{branch}").stdout
    collected: list[dict[str, Any]] = []
    for sha in raw.splitlines():
        if not sha:
            continue
        _commit_sha, _timestamp, _subject, trailers = _commit_metadata(root, sha)
        lane = trailers.get("Lane")
        if not lane or trailers.get("Task") != task:
            continue
        parents = run_git(root, "rev-list", "--parents", "-n", "1", sha).stdout.split()
        collected.append(
            {
                "lane": lane,
                "collect_sha": sha,
                "sha": parents[2] if len(parents) >= 3 else None,
            }
        )
    return collected


def _candidate_projection(root: Path, task: str, integration_branch: str) -> dict[str, Any] | None:
    """Project the ready candidate purely from Git: no persisted format beyond the ref.

    ``worktree_ready`` and ``behind_tip`` are re-derived on every call rather
    than cached anywhere, so they can never drift from what Git actually
    holds.  No candidate ref yet is not an error -- it is the normal state
    before the first ``publish``.
    """
    ref = _candidate_ref(task)
    probe = run_git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    sha = probe.stdout.strip()
    if probe.returncode or not sha:
        return None
    acceptance_path = _acceptance_worktree_path(root, task)
    acceptance_state = _status(root, acceptance_path, "", identity_label="acceptance worktree")
    behind = run_git(root, "rev-list", "--count", f"{ref}..{integration_branch}")
    return {
        "sha": sha,
        "worktree_ready": acceptance_state["exists"] and acceptance_state["head"] == sha,
        "behind_tip": int(behind.stdout.strip()),
        "acceptance_worktree": str(acceptance_path),
    }


def command_integration_status(args: argparse.Namespace) -> dict[str, Any]:
    task, path, branch = _integration_identity(args)
    root = Path(args.root).resolve()
    state = _status(root, path, branch)
    state.update(
        {
            "operation": "integration-status",
            "task_id": task,
            "worktree": str(path),
            "base_ref": _integration_base_ref(task),
            "collected": _collected_integrations(root, task, branch),
            "candidate": _candidate_projection(root, task, branch),
        }
    )
    return state


def command_integration_publish(args: argparse.Namespace) -> dict[str, Any]:
    """Publish a gated exact SHA as the ready candidate.

    Order matters for safety: check the acceptance worktree is clean *before*
    doing anything else, then checkout, and only then move the ref.  If the
    worktree is dirty (the user's own leftover test artifacts), nothing below
    this check ever runs -- the ref keeps its old value and the worktree is
    never touched.  If checkout itself fails, the ref still has not moved.
    Only once the worktree genuinely holds --sha does the ref follow it, so
    the ref can never point past what the worktree actually holds.
    """
    task = require_identifier(str(args.task_id), label="task id")
    root = Path(args.root).resolve()
    sha = exact_commit(root, str(args.sha), label="sha")
    acceptance_path = _acceptance_worktree_path(root, task)
    state = _status(root, acceptance_path, "", identity_label="acceptance worktree")
    if not state["exists"]:
        raise OrchestrateError(f"managed acceptance worktree does not exist: {acceptance_path}")
    if not state["clean"]:
        raise OrchestrateError(
            f"acceptance worktree must be clean before publish, candidate left unchanged: {acceptance_path}"
        )
    checkout = run_git(acceptance_path, "checkout", "--detach", sha, check=False)
    if checkout.returncode:
        detail = checkout.stderr.strip() or checkout.stdout.strip()
        raise OrchestrateError(f"git checkout failed while publishing candidate: {detail}")
    run_git(root, "update-ref", _candidate_ref(task), sha)
    return {
        "ok": True,
        "operation": "integration-publish",
        "task_id": task,
        "sha": sha,
        "candidate_ref": _candidate_ref(task),
        "acceptance_worktree": str(acceptance_path),
    }


def _immutable_paths(root: Path, sha: str) -> list[str]:
    """Read the paths one commit declares frozen with a repeatable ``Immutable:`` trailer.

    The declaration lives in the commit object itself, so it cannot be edited
    afterwards without changing the SHA.
    """
    raw = run_git(
        root, "show", "-s", "--format=%(trailers:key=Immutable,valueonly,unfold)", sha
    ).stdout
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _first_declaring_commits(root: Path, base: str, tip: str) -> dict[str, str]:
    """Map each ``Immutable:`` path to the earliest ``base..tip`` commit that declared it.

    A path is only protected starting at the commit that first freezes it:
    commits before that -- including the ordinary commit that first created
    the path -- cannot be "quietly widening an already-frozen contract",
    because the contract did not exist yet at that point in the lane.
    """
    raw = run_git(root, "rev-list", "--reverse", f"{base}..{tip}").stdout
    declarations: dict[str, str] = {}
    for sha in raw.splitlines():
        if not sha:
            continue
        for path in _immutable_paths(root, sha):
            declarations.setdefault(path, sha)
    return declarations


def _verify_immutable_surface(root: Path, base: str, tip: str) -> tuple[list[str], list[str]]:
    """Reject any commit, after a path's first declaration, that changes it without redeclaring.

    Multiple oracle rounds inside one lane are normal, so a Contract path may
    legitimately be rewritten more than once -- the rule this enforces is not
    "never touch it again" but "never touch it quietly, once frozen".  Only
    commits strictly after each path's earliest declaring commit are checked
    (the declaring commit itself, and anything before it, predate the freeze
    and cannot violate it).  Of those, a commit that redeclares the path (an
    oracle rework round) is exempt; a commit that changes it without
    redeclaring (an implementer widening the surface) is a violation.  A path
    never declared anywhere in the range is not tracked at all.
    """
    declarations = _first_declaring_commits(root, base, tip)
    declared = sorted(declarations)
    violations: list[str] = []
    for path in declared:
        declaring_commit = declarations[path]
        raw = run_git(root, "log", "--reverse", "--format=%H", f"{declaring_commit}..{tip}", "--", path).stdout
        for sha in raw.splitlines():
            if not sha:
                continue
            if path not in _immutable_paths(root, sha):
                violations.append(f"{path} changed by {sha} without redeclaring Immutable: {path}")
    return declared, violations


def command_integration_collect(args: argparse.Namespace) -> dict[str, Any]:
    task = require_identifier(str(args.task_id), label="task id")
    lane = require_identifier(str(args.lane_id), label="lane id")
    root = Path(args.root).resolve()
    sha = exact_commit(root, str(args.sha), label="sha")
    lane_branch = f"wave/{task}/{lane}"
    lane_path = managed_worktree_root(root) / f"{task}-{lane}"

    # 1. lane tree clean.
    lane_state = _status(
        root, lane_path, lane_branch, require_expected_branch=True, identity_label="lane worktree"
    )
    if not lane_state["exists"]:
        raise OrchestrateError(f"managed lane worktree does not exist: {lane_path}")
    if not lane_state["clean"]:
        raise OrchestrateError(f"lane worktree must be clean: {lane_path}")

    # 2. --sha is the exact tip of the lane branch.
    tip = run_git(root, "rev-parse", "--verify", lane_branch).stdout.strip()
    if sha != tip:
        raise OrchestrateError(
            f"--sha must be the tip of lane branch {lane_branch}: expected {tip}, got {sha}"
        )

    # 3. every commit that changes a once-declared Immutable: path redeclares it.
    lane_base = _lane_base(root, task, lane)
    declared, violations = _verify_immutable_surface(root, lane_base, tip)
    if violations:
        raise OrchestrateError(
            "lane changed an Immutable-declared path without redeclaring it in the same commit: "
            + "; ".join(violations)
        )

    task_id, integration_path, integration_branch = _integration_identity(args)
    integration_state = _status(
        root,
        integration_path,
        integration_branch,
        require_expected_branch=True,
        identity_label="integration worktree",
    )
    if not integration_state["exists"]:
        raise OrchestrateError(f"managed integration worktree does not exist: {integration_path}")
    if not integration_state["clean"]:
        raise OrchestrateError(f"integration worktree must be clean: {integration_path}")

    merged = run_git(integration_path, "merge", "--no-ff", "--no-commit", tip, check=False)
    if merged.returncode:
        detail = merged.stderr.strip() or merged.stdout.strip() or "integration collect conflict"
        raise OrchestrateError(f"git integration collect failed: {detail}")
    message = f"Collect lane {lane}\n\nTask: {task_id}\nLane: {lane}"
    committed = run_git(integration_path, "commit", "-m", message, check=False)
    if committed.returncode:
        detail = committed.stderr.strip() or committed.stdout.strip()
        raise OrchestrateError(f"git commit failed while recording integration collect: {detail}")
    collect_sha = run_git(integration_path, "rev-parse", "HEAD").stdout.strip()

    run_git(root, "worktree", "remove", str(lane_path))

    return {
        "ok": True,
        "operation": "integration-collect",
        "task_id": task_id,
        "lane_id": lane,
        "sha": sha,
        "collect_sha": collect_sha,
        "immutable_paths_verified": declared,
        "branch": integration_branch,
        "worktree": str(integration_path),
        "lane_worktree_removed": str(lane_path),
    }


def command_integration_remove(args: argparse.Namespace) -> dict[str, Any]:
    task, path, branch = _integration_identity(args)
    root = Path(args.root).resolve()
    state = _status(root, path, branch)
    if not state["exists"]:
        raise OrchestrateError(f"managed integration worktree does not exist: {path}")
    if not state["clean"]:
        raise OrchestrateError(f"cannot remove worktree because it is not clean: {path}")
    acceptance_path = _acceptance_worktree_path(root, task)
    acceptance_state = _status(root, acceptance_path, "", identity_label="acceptance worktree")
    if acceptance_state["exists"] and not acceptance_state["clean"]:
        raise OrchestrateError(f"cannot remove worktree because it is not clean: {acceptance_path}")
    run_git(root, "worktree", "remove", str(path))
    if acceptance_state["exists"]:
        run_git(root, "worktree", "remove", str(acceptance_path))
    candidate_ref = _candidate_ref(task)
    if run_git(root, "rev-parse", "--verify", "--quiet", candidate_ref, check=False).returncode == 0:
        run_git(root, "update-ref", "-d", candidate_ref)
    return {
        "ok": True,
        "operation": "integration-remove",
        "task_id": task,
        "worktree": str(path),
        "acceptance_worktree": str(acceptance_path),
        "branch": branch,
        "removed": True,
    }


_WORKFLOW_TRAILER_KEYS = frozenset({"Wave", "Slice", "Role", "Task", "Lane"})


def _trailers(text: str) -> dict[str, str]:
    """Parse Git's already-interpreted final trailer block.

    The ``trailers:only`` pretty-format is authoritative here: unlike a raw
    commit body walk, it excludes ordinary body colon-lines and only returns
    the final block Git recognizes as trailers.  Keep duplicate detection
    explicit because silently letting the last value win makes workflow
    identity ambiguous.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        canonical = next(
            (candidate for candidate in _WORKFLOW_TRAILER_KEYS if key.casefold() == candidate.casefold()),
            None,
        )
        if canonical is None:
            continue
        if canonical in values:
            raise OrchestrateError(f"ambiguous Git trailer: {canonical}")
        values[canonical] = value.strip()
    return values


def _commit_metadata(root: Path, sha: str) -> tuple[str, str, str, dict[str, str]]:
    """Read commit identity and interpreted trailers in one Git invocation."""
    fields = run_git(
        root,
        "show",
        "-s",
        "--format=%H%x00%ct%x00%s%x00%(trailers:only,unfold)",
        sha,
    ).stdout.split("\x00", 3)
    commit_sha = fields[0] if fields else ""
    timestamp = fields[1] if len(fields) > 1 else ""
    subject = fields[2].strip() if len(fields) > 2 else ""
    trailer_text = fields[3] if len(fields) > 3 else ""
    return commit_sha, timestamp, subject, _trailers(trailer_text)


def _commit_info(root: Path, sha: str) -> dict[str, Any]:
    commit_sha, timestamp, subject, trailers = _commit_metadata(root, sha)
    return {
        "sha": commit_sha,
        "timestamp": int(timestamp),
        "wave": trailers.get("Wave", ""),
        "slice": trailers.get("Slice", ""),
        "role": trailers.get("Role", ""),
        "subject": subject,
    }


def _range_numstat(
    root: Path, start: str | None, end: str
) -> list[tuple[str, int, int]]:
    """Return the net numstat for one topology range.

    Ready trailers identify boundaries, not the only commits to count.  Using a
    range diff includes untrailed work between those boundaries and, unlike
    summing each commit, counts the whole merge-to-ready range exactly once.
    """
    revisions = [end] if start is None else [start, end]
    output = run_git(root, "diff", "--numstat", *revisions).stdout
    result: list[tuple[str, int, int]] = []
    for line in output.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3 or parts[0] == "-" or parts[1] == "-":
            continue
        try:
            result.append((parts[2], int(parts[0]), int(parts[1])))
        except ValueError:
            continue
    return result


def command_profile_report(args: argparse.Namespace) -> dict[str, Any]:
    """Report profile accounting from one global, slice-partitioned topology walk."""
    root = Path(args.root).resolve()
    try:
        base = exact_commit(root, str(args.base), label="base")
    except OrchestrateError as exc:
        raise OrchestrateError(f"invalid base: {exc}") from exc
    task = require_identifier(str(args.task_id), label="task id")
    wave = require_identifier(str(args.wave_id), label="wave id")
    refs = [f"refs/heads/wave/{task}/{wave}/{role}" for role in ("oracle", "implementation")]
    refs = [
        ref for ref in refs
        if run_git(root, "show-ref", "--verify", "--quiet", ref, check=False).returncode == 0
    ]
    raw = (
        run_git(
            root,
            "rev-list",
            "--ancestry-path",
            "--topo-order",
            "--reverse",
            *[f"{base}..{ref}" for ref in refs],
        ).stdout
        if refs
        else ""
    )
    infos: list[dict[str, Any]] = []
    for sha in raw.splitlines():
        info = _commit_info(root, sha)
        if (
            info["wave"] == wave
            and info["slice"]
            and info["role"] in {"oracle", "merge", "implementation"}
        ):
            infos.append(info)

    warnings: list[str] = []

    def interval(after: dict[str, Any], before: dict[str, Any], label: str) -> int | None:
        delta = after["timestamp"] - before["timestamp"]
        if delta < 0:
            warnings.append(
                f"non-monotonic {label} timestamps: {before['sha']} ({before['timestamp']}) "
                f"before {after['sha']} ({after['timestamp']})"
            )
            return None
        return delta

    for before, after in zip(infos, infos[1:]):
        if after["timestamp"] < before["timestamp"]:
            warnings.append(
                f"non-monotonic committer timestamps: {before['sha']} ({before['timestamp']}) "
                f"after {after['sha']} ({after['timestamp']})"
            )

    oracle_intervals: dict[str, int | None] = {}
    previous_oracle: dict[str, Any] | None = None
    for info in infos:
        if info["role"] == "oracle":
            oracle_intervals[info["sha"]] = (
                None if previous_oracle is None else interval(info, previous_oracle, "Oracle-ready")
            )
            previous_oracle = info

    def new_slice() -> dict[str, Any]:
        return {
            "attempts": [],
            "oracle_interval_seconds": None,
            "handoff_interval_seconds": None,
            "implementation_interval_seconds": None,
            "contract_numstat": {"files": 0, "insertions": 0, "deletions": 0},
            "implementation_numstat": {"files": 0, "insertions": 0, "deletions": 0},
        }

    slices: dict[str, dict[str, Any]] = {}
    oracle_records: list[tuple[int, dict[str, Any]]] = []
    merge_records: list[tuple[int, dict[str, Any]]] = []
    endpoint_records: list[tuple[int, dict[str, Any]]] = []
    for position, info in enumerate(infos):
        entry = slices.setdefault(info["slice"], new_slice())
        if info["role"] == "oracle":
            oracle_records.append((position, info))
        elif info["role"] == "merge":
            merge_records.append((position, info))
        else:
            endpoint_records.append((position, info))

    # Every Oracle range is diffed once in global readiness order.  The cached
    # result is partitioned by endpoint Slice and also supplies Wave totals.
    wave_contract_stats = {"files": 0, "insertions": 0, "deletions": 0}
    previous_oracle_sha = base
    for _position, oracle in oracle_records:
        stats = _range_numstat(root, previous_oracle_sha, oracle["sha"])
        slices[oracle["slice"]].setdefault("_contract_stats", []).extend(stats)
        wave_contract_stats["files"] += len(stats)
        wave_contract_stats["insertions"] += sum(item[1] for item in stats)
        wave_contract_stats["deletions"] += sum(item[2] for item in stats)
        previous_oracle_sha = oracle["sha"]

    # Merge windows are traversed per Slice with one monotone endpoint cursor
    # each, so another Slice's later merge can never consume this Slice's
    # endpoint.
    merge_ready_endpoints: dict[int, dict[str, Any]] = {}
    endpoints_by_slice: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for endpoint_position, endpoint in endpoint_records:
        endpoints_by_slice.setdefault(endpoint["slice"], []).append(
            (endpoint_position, endpoint)
        )
    merges_by_slice: dict[str, list[tuple[int, int, dict[str, Any]]]] = {}
    for merge_index, (merge_position, merge) in enumerate(merge_records):
        merges_by_slice.setdefault(merge["slice"], []).append(
            (merge_index, merge_position, merge)
        )
    for slice_id, slice_merges in merges_by_slice.items():
        slice_endpoints = endpoints_by_slice.get(slice_id, [])
        endpoint_cursor = 0
        for order, (merge_index, merge_position, merge) in enumerate(slice_merges):
            next_merge_position = (
                slice_merges[order + 1][1]
                if order + 1 < len(slice_merges)
                else len(infos)
            )
            latest_ready: dict[str, Any] | None = None
            while endpoint_cursor < len(slice_endpoints):
                endpoint_position, endpoint = slice_endpoints[endpoint_cursor]
                if endpoint_position >= next_merge_position:
                    break
                endpoint_cursor += 1
                if endpoint_position <= merge_position:
                    continue
                latest_ready = endpoint
            if latest_ready is None:
                continue
            merge_ready_endpoints[merge_index] = latest_ready
            stats = _range_numstat(root, merge["sha"], latest_ready["sha"])
            slices[merge["slice"]].setdefault("_implementation_stats", []).extend(stats)

    # An endpoint that precedes every Contract merge of its Slice belongs to no
    # attempt window.  Reporting it keeps a misplaced handoff visible instead of
    # leaving the attempt's implementation_sha silently null.
    for slice_id, slice_endpoints in endpoints_by_slice.items():
        slice_merges = merges_by_slice.get(slice_id, [])
        first_merge_position = slice_merges[0][1] if slice_merges else len(infos)
        for endpoint_position, endpoint in slice_endpoints:
            if endpoint_position <= first_merge_position:
                warnings.append(
                    f"unattributed implementation endpoint {endpoint['sha']} in Slice "
                    f"{slice_id}: it precedes every Contract merge of that Slice"
                )

    # Pair attempts within each Slice as before, but consume the endpoint
    # selected by the global merge window above.
    merge_indices_by_slice: dict[str, list[int]] = {}
    for merge_index, (_position, merge) in enumerate(merge_records):
        merge_indices_by_slice.setdefault(merge["slice"], []).append(merge_index)
    oracle_by_slice: dict[str, list[dict[str, Any]]] = {}
    for _position, oracle in oracle_records:
        oracle_by_slice.setdefault(oracle["slice"], []).append(oracle)

    for slice_id, entry in slices.items():
        oracle_list = oracle_by_slice.get(slice_id, [])
        merge_indices = merge_indices_by_slice.get(slice_id, [])
        attempts: list[dict[str, Any]] = []
        for index, oracle in enumerate(oracle_list):
            merge_index = merge_indices[index] if index < len(merge_indices) else None
            merge = merge_records[merge_index][1] if merge_index is not None else None
            implementation = (
                merge_ready_endpoints.get(merge_index)
                if merge_index is not None
                else None
            )
            attempts.append(
                {
                    "attempt": index + 1,
                    "oracle_sha": oracle["sha"],
                    "contract_merge_sha": merge["sha"] if merge else None,
                    "implementation_sha": implementation["sha"] if implementation else None,
                    "oracle_interval_seconds": oracle_intervals.get(oracle["sha"]),
                    "handoff_interval_seconds": (
                        None if merge is None else interval(merge, oracle, "Contract handoff")
                    ),
                    "implementation_interval_seconds": (
                        None
                        if merge is None or implementation is None
                        else interval(implementation, merge, "Implementation")
                    ),
                }
            )
        entry["attempts"] = attempts
        if attempts:
            latest = attempts[-1]
            for key in (
                "oracle_interval_seconds",
                "handoff_interval_seconds",
                "implementation_interval_seconds",
            ):
                entry[key] = latest[key]
        contract_stats = entry.pop("_contract_stats", [])
        entry["contract_numstat"] = {
            "files": len(contract_stats),
            "insertions": sum(item[1] for item in contract_stats),
            "deletions": sum(item[2] for item in contract_stats),
        }
        implementation_stats = entry.pop("_implementation_stats", [])
        if implementation_stats:
            entry["implementation_numstat"] = {
                "files": len({item[0] for item in implementation_stats}),
                "insertions": sum(item[1] for item in implementation_stats),
                "deletions": sum(item[2] for item in implementation_stats),
            }

    wave_impl_stats = {"files": 0, "insertions": 0, "deletions": 0}
    for entry in slices.values():
        current = entry["implementation_numstat"]
        wave_impl_stats["files"] += current["files"]
        wave_impl_stats["insertions"] += current["insertions"]
        wave_impl_stats["deletions"] += current["deletions"]
    first_oracle = oracle_records[0][1] if oracle_records else None
    final_impl = next(
        (item for item in reversed(infos) if item["role"] == "implementation"), None
    )
    return {
        "ok": True,
        "operation": "profile-report",
        "task_id": task,
        "wave_id": wave,
        "base": base,
        "warnings": sorted(set(warnings)),
        "slices": slices,
        "wave": {
            "elapsed_seconds": (
                final_impl["timestamp"] - first_oracle["timestamp"]
                if first_oracle
                and final_impl
                and final_impl["timestamp"] >= first_oracle["timestamp"]
                else None
            ),
            "contract_numstat": wave_contract_stats,
            "implementation_numstat": wave_impl_stats,
        },
    }
