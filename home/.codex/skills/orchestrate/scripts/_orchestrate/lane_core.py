"""Git-backed lane and task-integration command seams."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .admission import compute_checks, is_test_path, numstat
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


def _lane_collect_walk(root: Path, task: str, branch: str, base: str) -> list[dict[str, Any]]:
    """Walk one branch's first-parent history for lane-collect merge commits.

    A collect commit carries ``Task:``/``Lane:`` trailers verbatim (see
    ``command_integration_collect``). A commit that instead carries only the
    retired ``Wave:``/``Role:``/``Slice:`` trailers has no ``Lane:`` trailer
    and is skipped here -- it belongs to no lane under the new trailer
    vocabulary by construction, not by a second read path for the old one.
    """
    if not _branch_exists(root, branch):
        return []
    raw = run_git(root, "rev-list", "--first-parent", "--reverse", f"{base}..{branch}").stdout
    records: list[dict[str, Any]] = []
    for sha in raw.splitlines():
        if not sha:
            continue
        _commit_sha, timestamp, _subject, trailers = _commit_metadata(root, sha)
        lane = trailers.get("Lane")
        if not lane or trailers.get("Task") != task:
            continue
        parents = run_git(root, "rev-list", "--parents", "-n", "1", sha).stdout.split()
        records.append(
            {
                "lane": lane,
                "collect_sha": sha,
                "sha": parents[2] if len(parents) >= 3 else None,
                "timestamp": int(timestamp),
            }
        )
    return records


def _collected_integrations(root: Path, task: str, branch: str) -> list[dict[str, Any]]:
    if not _branch_exists(root, branch):
        return []
    base = _integration_base(root, task)
    return [
        {"lane": record["lane"], "collect_sha": record["collect_sha"], "sha": record["sha"]}
        for record in _lane_collect_walk(root, task, branch, base)
    ]


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


def _trailer_values(root: Path, sha: str, key: str) -> list[str]:
    """Read one repeatable trailer's values straight off one commit object.

    The declaration lives in the commit object itself, so it cannot be
    edited afterwards without changing the SHA.
    """
    raw = run_git(
        root, "show", "-s", f"--format=%(trailers:key={key},valueonly,unfold)", sha
    ).stdout
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _immutable_paths(root: Path, sha: str) -> list[str]:
    """Read the paths one commit declares frozen with a repeatable ``Immutable:`` trailer."""
    return _trailer_values(root, sha, "Immutable")


def _lane_origin(root: Path, base: str, tip: str) -> str | None:
    """The first ``Origin:`` trailer declared by any commit in a lane's own range.

    ``base..tip`` here is the lane's own base ref to its own tip, not the
    task-wide report range: a repair lane declares this on one of its own
    commits to mark itself as user-initiated repair work, which does not
    consume the machine rework budget.
    """
    raw = run_git(root, "rev-list", "--reverse", f"{base}..{tip}").stdout
    for sha in raw.splitlines():
        if not sha:
            continue
        values = _trailer_values(root, sha, "Origin")
        if values:
            return values[0]
    return None


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


_WORKFLOW_TRAILER_KEYS = frozenset({"Task", "Lane"})


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


def _oldest_and_commit_count(root: Path, base: str, tip: str) -> tuple[int, int]:
    """The committer timestamp of the oldest commit in ``base..tip``, and its count.

    One Git call serves both: ``commits`` is how many rework rounds the lane
    took before its collect; the oldest entry's timestamp anchors
    ``span_seconds``. An empty range (a lane collected with no commits of
    its own) falls back to the base commit's own timestamp so span_seconds
    is still well-defined.
    """
    lines = run_git(root, "log", "--format=%ct", "--reverse", f"{base}..{tip}").stdout.splitlines()
    if not lines:
        return int(run_git(root, "show", "-s", "--format=%ct", base).stdout.strip()), 0
    return int(lines[0]), len(lines)


def _report_lane(root: Path, task: str, record: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
    """Build one lane's report entry, plus its (first_commit, collect) timestamps."""
    lane = record["lane"]
    lane_tip = record["sha"]
    collect_ts = record["timestamp"]
    lane_base = _lane_base(root, task, lane)
    if lane_tip is None:
        # A collect merge with no recorded lane-tip parent: nothing to walk.
        first_ts = collect_ts
        commits = 0
        production = {"added": 0, "deleted": 0}
        test = {"added": 0, "deleted": 0}
        origin = None
    else:
        first_ts, commits = _oldest_and_commit_count(root, lane_base, lane_tip)
        production = {"added": 0, "deleted": 0}
        test = {"added": 0, "deleted": 0}
        for added, deleted, path in numstat(root, f"{lane_base}..{lane_tip}"):
            bucket = test if is_test_path(path) else production
            bucket["added"] += added
            bucket["deleted"] += deleted
        origin = _lane_origin(root, lane_base, lane_tip)
    entry: dict[str, Any] = {
        "lane": lane,
        "span_seconds": collect_ts - first_ts,
        "commits": commits,
        "production": production,
        "test": test,
    }
    if origin:
        entry["origin"] = origin
    return entry, first_ts, collect_ts


def _max_concurrent(intervals: list[tuple[int, int]]) -> int:
    """The largest number of lane spans overlapping at any point in time.

    Actual parallelism, not the count of lanes: two lanes whose spans never
    touch never count as more than 1 running at once. Endpoints are
    inclusive -- a lane starting exactly when another collects still counts
    as sharing that instant.
    """
    if not intervals:
        return 0
    best = 0
    for start, end in intervals:
        overlapping = sum(
            1 for other_start, other_end in intervals if start <= other_end and other_start <= end
        )
        best = max(best, overlapping)
    return best


def command_report(args: argparse.Namespace) -> dict[str, Any]:
    """Report everything Git can prove about one task: lanes, checks, and candidate.

    This merges the retired ``profile report`` (per-lane span/output, now
    keyed by lane instead of Oracle/Implementation role), the four cheap
    Git checks that used to gate the retired ``admission`` command, and the
    ready-candidate projection ``integration status`` already exposes. It
    is entirely read-only: nothing here is ever refused, only presented.
    """
    task = require_identifier(str(args.task_id), label="task id")
    root = Path(args.root).resolve()
    try:
        base = exact_commit(root, str(args.base), label="base")
    except OrchestrateError as exc:
        raise OrchestrateError(f"invalid base: {exc}") from exc
    _task_id, _integration_path, integration_branch = _integration_identity(args)
    tip = (
        run_git(root, "rev-parse", "--verify", "--quiet", integration_branch, check=False).stdout.strip()
        or base
    )

    records = _lane_collect_walk(root, task, integration_branch, base)
    lanes: list[dict[str, Any]] = []
    intervals: list[tuple[int, int]] = []
    for record in records:
        entry, first_ts, collect_ts = _report_lane(root, task, record)
        lanes.append(entry)
        intervals.append((first_ts, collect_ts))

    task_span = (
        max(end for _, end in intervals) - min(start for start, _ in intervals)
        if intervals
        else 0
    )
    checks = compute_checks(
        root, base, tip,
        [{"lane": record["lane"], "timestamp": record["timestamp"]} for record in records],
    )
    return {
        "ok": True,
        "operation": "report",
        "read_only": True,
        "lanes": lanes,
        "task": {
            "lanes": len(lanes),
            "max_concurrent": _max_concurrent(intervals),
            "span_seconds": task_span,
        },
        "checks": checks,
        "candidate": _candidate_projection(root, task, integration_branch),
    }
