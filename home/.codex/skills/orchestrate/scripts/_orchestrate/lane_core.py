"""Git-backed lane and task-integration command seams."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .admission import compute_checks, is_test_path, numstat
from .git_ops import exact_commit, managed_worktree_root, run_git, worktree_records
from .primitives import OrchestrateError, require_identifier, sha256_bytes


def _lane_identity(args: argparse.Namespace) -> tuple[str, str, Path, str]:
    task = require_identifier(str(args.task_id), label="task id")
    lane = require_identifier(str(args.lane_id), label="lane id")
    if lane == "integration":
        raise OrchestrateError(
            "lane id must not be 'integration': that name is reserved for the integration branch"
        )
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
    probe = run_git(
        root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False
    )
    base = probe.stdout.strip()
    if probe.returncode or not base:
        raise OrchestrateError(
            f"lane base ref is missing: {ref}; recreate the lane worktree or "
            f"restore it with git update-ref {ref} <exact base sha>"
        )
    return base


def _branch_exists(root: Path, branch: str) -> bool:
    return (
        run_git(
            root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False
        ).returncode
        == 0
    )


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
        return {
            "ok": True,
            "operation": "worktree-status",
            "exists": False,
            "path": str(path),
            "branch": expected_branch,
            "head": None,
            "tree": None,
            "clean": False,
            "changed_paths": [],
        }
    live_branch = _record_branch(record)
    if not path.exists():
        return {
            "ok": True,
            "operation": "worktree-status",
            "exists": False,
            "path": str(path),
            "branch": live_branch,
            "head": record.get("HEAD"),
            "tree": None,
            "clean": False,
            "changed_paths": [],
        }
    if require_expected_branch and live_branch != expected_branch:
        rendered_live = live_branch if live_branch else "detached"
        raise OrchestrateError(
            f"{identity_label} must be attached to exact derived branch {expected_branch}; "
            f"live state is {rendered_live}"
        )
    changed = [
        line
        for line in run_git(path, "status", "--porcelain").stdout.splitlines()
        if line
    ]
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
        raise OrchestrateError(
            f"derived worktree path or branch already exists: {path} / {branch}"
        )
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
    raw = run_git(
        root, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{prefix}"
    ).stdout
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
        raise OrchestrateError(
            f"cannot remove worktree because it is not clean: {path}"
        )
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
    if (
        _branch_exists(root, branch)
        or os.path.lexists(path)
        or os.path.lexists(acceptance_path)
    ):
        raise OrchestrateError(
            f"derived worktree path or branch already exists: {path} / {branch} / {acceptance_path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "worktree", "add", "-b", branch, str(path), base)
    run_git(root, "update-ref", _integration_base_ref(task), base)
    # Detached HEAD, not a branch: the acceptance worktree is pinned to
    # whatever exact SHA `candidate` last checked out, not to any branch tip.
    acceptance_path.parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "worktree", "add", "--detach", str(acceptance_path), base)
    evidence = _status(root, path, branch)
    acceptance_evidence = _status(
        root, acceptance_path, "", identity_label="acceptance worktree"
    )
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
    probe = run_git(
        root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False
    )
    base = probe.stdout.strip()
    if probe.returncode or not base:
        raise OrchestrateError(
            f"integration base ref is missing: {ref}; recreate the integration worktree or "
            f"restore it with git update-ref {ref} <exact base sha>"
        )
    return base


def _lane_collect_walk(
    root: Path, task: str, branch: str, base: str
) -> list[dict[str, Any]]:
    """Walk one branch's first-parent history for lane-collect merge commits.

    A collected lane record is formed only by a commit carrying the matching
    ``Task:`` and ``Lane:`` trailers written by ``command_integration_collect``.
    """
    if not _branch_exists(root, branch):
        return []
    raw = run_git(
        root, "rev-list", "--first-parent", "--reverse", f"{base}..{branch}"
    ).stdout
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
        {
            "lane": record["lane"],
            "collect_sha": record["collect_sha"],
            "sha": record["sha"],
        }
        for record in _lane_collect_walk(root, task, branch, base)
    ]


def _candidate_projection(
    root: Path, task: str, integration_branch: str
) -> dict[str, Any] | None:
    """Project the ready candidate purely from Git: no persisted format beyond the ref.

    ``worktree_ready`` and ``behind_tip`` are re-derived on every call rather
    than cached anywhere, so they can never drift from what Git actually
    holds.  No candidate ref yet is not an error -- it is the normal state
    before the first ``candidate``.
    """
    ref = _candidate_ref(task)
    probe = run_git(
        root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False
    )
    sha = probe.stdout.strip()
    if probe.returncode or not sha:
        return None
    acceptance_path = _acceptance_worktree_path(root, task)
    acceptance_state = _status(
        root, acceptance_path, "", identity_label="acceptance worktree"
    )
    behind = run_git(root, "rev-list", "--count", f"{ref}..{integration_branch}")
    return {
        "sha": sha,
        "worktree_ready": acceptance_state["exists"]
        and acceptance_state["head"] == sha,
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


def _all_task_ids(root: Path) -> list[str]:
    """Every task discovered from ``refs/orchestrate/*/integration/base``.

    That ref is written once, atomically, by ``integration create`` -- it is
    the thing that most precisely means "a task exists here", so no other
    signal (worktree directories, lane branches, ...) is consulted.
    """
    prefix = "refs/orchestrate/"
    suffix = "/integration/base"
    raw = run_git(
        root, "for-each-ref", "--format=%(refname)", f"{prefix}*{suffix}"
    ).stdout
    tasks: list[str] = []
    for line in raw.splitlines():
        if line.startswith(prefix) and line.endswith(suffix):
            tasks.append(line[len(prefix) : -len(suffix)])
    return sorted(tasks)


def _integration_summary(root: Path, task: str) -> dict[str, Any]:
    """One task's shallow row for ``integration list``.

    Reuses the same projections ``report``/``integration status`` already
    compute (``_candidate_projection``, ``_list_lanes``, ``_status``) instead
    of introducing a second read path; `list` differs from `report` only in
    scope (every task, not one) and depth (no lane walk, no compute_checks).
    """
    branch = f"wave/{task}/integration"
    path = managed_worktree_root(root) / f"{task}-integration"
    acceptance_path = _acceptance_worktree_path(root, task)
    branch_exists = _branch_exists(root, branch)
    tip = (
        run_git(root, "rev-parse", "--verify", branch).stdout.strip()
        if branch_exists
        else None
    )
    integration_state = _status(root, path, branch)
    acceptance_state = _status(
        root, acceptance_path, "", identity_label="acceptance worktree"
    )
    return {
        "task_id": task,
        "branch": branch,
        "branch_exists": branch_exists,
        "tip": tip,
        "base": _integration_base(root, task),
        "candidate": _candidate_projection(root, task, branch)
        if branch_exists
        else None,
        "lanes": _list_lanes(root, task),
        "integration_worktree_present": integration_state["exists"],
        "acceptance_worktree_present": acceptance_state["exists"],
    }


def command_integration_list(args: argparse.Namespace) -> dict[str, Any]:
    """Shallow, read-only view of every task in flight in one repository.

    Never refuses and never computes anything expensive: no per-lane walk,
    no ``compute_checks`` -- that depth belongs to ``report``, which is about
    one task, not every task.
    """
    root = Path(args.root).resolve()
    return {
        "ok": True,
        "operation": "integration-list",
        "read_only": True,
        "tasks": [_integration_summary(root, task) for task in _all_task_ids(root)],
    }


def command_integration_candidate(args: argparse.Namespace) -> dict[str, Any]:
    """Gate a exact SHA onto the acceptance stand as the ready candidate.

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
        raise OrchestrateError(
            f"managed acceptance worktree does not exist: {acceptance_path}"
        )
    if not state["clean"]:
        raise OrchestrateError(
            f"acceptance worktree must be clean before candidate, candidate left unchanged: {acceptance_path}"
        )
    checkout = run_git(acceptance_path, "checkout", "--detach", sha, check=False)
    if checkout.returncode:
        detail = checkout.stderr.strip() or checkout.stdout.strip()
        raise OrchestrateError(f"git checkout failed while gating candidate: {detail}")
    run_git(root, "update-ref", _candidate_ref(task), sha)
    return {
        "ok": True,
        "operation": "integration-candidate",
        "task_id": task,
        "sha": sha,
        "candidate_ref": _candidate_ref(task),
        "acceptance_worktree": str(acceptance_path),
    }


def _dirty_paths(worktree: Path) -> list[str]:
    """Unstaged-modified and untracked paths in one worktree, one per file.

    ``-uall`` makes Git list every file inside an untracked directory
    individually instead of collapsing it to one ``?? dir/`` entry: a file a
    user left inside an untracked directory needs the same byte-for-byte
    protection as one sitting directly in the worktree, and collapsing it
    would leave nothing here to hash and compare. ``-z`` NUL-terminates each
    entry with the path left unquoted and unescaped -- the default porcelain
    format quotes and octal-escapes any path with non-ASCII bytes, and this
    repo's own users have non-ASCII filenames, so parsing the quoted form
    would silently produce a path string that never resolves on disk.

    Callers only reach this after confirming the index equals HEAD, so every
    entry here is the user's own work-in-progress -- exactly what landing
    must leave untouched.
    """
    raw = run_git(worktree, "status", "--porcelain", "-uall", "-z").stdout
    return [entry[3:] for entry in raw.split("\0") if entry]


def _path_digest(path: Path) -> str | None:
    """A dirty path's content hash, or ``None`` if it cannot be read as one.

    ``None`` is itself a comparable value, and deliberately covers every
    ``OSError`` (missing, turned into a directory, permission denied, ...)
    rather than only ``FileNotFoundError``: this helper's job is to witness
    content, not to classify why a read failed, and a path readable before
    landing but unreadable after must still fail the equality check just as
    plainly as one whose content changed -- narrowing the guard to one
    specific errno would let every other filesystem surprise crash the
    command instead of being reported as a mismatch.
    """
    try:
        return sha256_bytes(path.read_bytes())
    except OSError:
        return None


def command_integration_land(args: argparse.Namespace) -> dict[str, Any]:
    """Squash the ready candidate onto a local persistence branch as one commit.

    There is deliberately no ``--target``: the only landable SHA is the ready
    candidate (``_candidate_ref``), so "only a gated SHA lands" is true by
    construction instead of by an argument a caller could get wrong. Every
    precondition below is a pure Git fact checked before any mutation; if any
    fails, nothing is touched. Once the squash commit exists, the two
    postconditions are re-asserted rather than trusted -- by then a mutation
    has already happened, so a failure is reported (``ok: false``), not
    raised as a refusal.
    """
    task = require_identifier(str(args.task_id), label="task id")
    root = Path(args.root).resolve()
    persist = str(args.persist)
    final = bool(args.final)

    # 1. the candidate ref exists and resolves to a commit.
    candidate_ref = _candidate_ref(task)
    probe = run_git(
        root,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{candidate_ref}^{{commit}}",
        check=False,
    )
    candidate = probe.stdout.strip()
    if probe.returncode or not candidate:
        raise OrchestrateError(
            f"no ready candidate to land: {candidate_ref} does not resolve to a commit; gate one with "
            "`integration candidate` first"
        )

    # 2. the integration branch exists, and the candidate is an ancestor of its tip.
    _task_id, _integration_path, integration_branch = _integration_identity(args)
    if not _branch_exists(root, integration_branch):
        raise OrchestrateError(
            f"integration branch does not exist: {integration_branch}"
        )
    tip = run_git(root, "rev-parse", "--verify", integration_branch).stdout.strip()
    on_tip = run_git(root, "merge-base", "--is-ancestor", candidate, tip, check=False)
    if on_tip.returncode != 0:
        raise OrchestrateError(
            f"candidate {candidate} is not an ancestor of integration tip {tip} ({integration_branch})"
        )

    # 3. --persist must name a real local branch, never a remote-tracking ref or bare SHA.
    if not _branch_exists(root, persist):
        raise OrchestrateError(
            f"--persist must name a local branch (refs/heads/{persist}); "
            "remote-tracking refs and bare SHAs are refused"
        )

    # 4. that branch is checked out in exactly one worktree; everything below happens there.
    persist_ref = f"refs/heads/{persist}"
    persist_worktrees = [
        Path(str(record["worktree"])).resolve()
        for record in worktree_records(root)
        if record.get("branch") == persist_ref
    ]
    if len(persist_worktrees) != 1:
        raise OrchestrateError(
            f"persist branch {persist} must be checked out in exactly one worktree, found "
            f"{len(persist_worktrees)}; check it out with git worktree add"
        )
    persist_path = persist_worktrees[0]

    # 5. divergence guard: the question is whether the candidate's history
    #    already covers everything on the persist branch -- that is a
    #    disjunction, not an either/or on whether the tip carries a Landed:
    #    trailer:
    #      (a) the persist tip itself is an ancestor of the candidate. This is
    #          the general case: it covers the first landing (the tip is the
    #          branch's own fork point) and it covers a persist tip that was
    #          later merged into this task's integration branch and gated
    #          again as a candidate -- multiple tasks landing to the same branch is
    #          exactly that shape, and after the merge the tip genuinely is
    #          an ancestor again.
    #      (b) only when (a) fails: the persist tip is *this task's own*
    #          landing commit (its Task: trailer equals this task) and that
    #          commit's Landed: SHA is an ancestor of the candidate. This is
    #          the narrow case (a) cannot cover on its own -- a second
    #          partial landing of the same task, where the tip is that task's
    #          own squash commit and so is never, by construction, an
    #          ancestor of anything.
    #    A tip that fails both is either diverged (someone committed to the
    #    branch directly -- exactly what a squash would otherwise silently
    #    overwrite) or blocked behind a *different* task's still-unmerged
    #    landing, which needs a different, actionable message.
    persist_tip = run_git(root, "rev-parse", "--verify", persist_ref).stdout.strip()
    reachable = run_git(
        root, "merge-base", "--is-ancestor", persist_tip, candidate, check=False
    )
    if reachable.returncode != 0:
        _sha, _ts, _subject, persist_trailers = _commit_metadata(root, persist_tip)
        landed_value = persist_trailers.get("Landed")
        landing_task = persist_trailers.get("Task")
        if landed_value is None:
            raise OrchestrateError(
                f"persist branch {persist} has diverged: {persist_tip} is not an ancestor of "
                f"candidate {candidate}; something was committed to {persist} directly since the "
                "last landing"
            )
        if landing_task != task:
            raise OrchestrateError(
                f"persist branch {persist} was already landed for task {landing_task or '<unknown>'} "
                f"at {persist_tip}; open a lane from this task's integration tip, merge {persist} "
                "and resolve any conflict in that lane, collect it, rerun the shared gate order, "
                "gate a candidate again, and land again"
            )
        anchored = run_git(
            root, "merge-base", "--is-ancestor", landed_value, candidate, check=False
        )
        if anchored.returncode != 0:
            raise OrchestrateError(
                f"persist branch {persist} was landed for task {task} at {landed_value}, but that "
                f"SHA is not an ancestor of candidate {candidate}; the integration branch was "
                "rewritten since that landing, which violates append-only integration (S5.5)"
            )

    # 6. index must equal HEAD in the persist worktree. Unstaged and untracked
    #    dirt is the user's own work-in-progress and must survive untouched.
    staged = run_git(persist_path, "diff", "--cached", "--quiet", check=False)
    if staged.returncode not in (0, 1):
        detail = staged.stderr.strip() or staged.stdout.strip()
        raise OrchestrateError(
            f"git diff --cached failed in persist worktree: {detail}"
        )
    if staged.returncode == 1:
        raise OrchestrateError(
            f"persist worktree has staged changes; unstage or commit them first: {persist_path}"
        )
    dirty_paths = _dirty_paths(persist_path)
    dirty_digests = {path: _path_digest(persist_path / path) for path in dirty_paths}

    # 7. dry-run the tree transition. `read-tree -m <old> <new>` (two trees,
    #    not three) is a direct old-tree-to-new-tree application, not a
    #    history-based three-way merge: precondition 5's anchor rule already
    #    proves the persist branch carries nothing outside the candidate's
    #    ancestry, so there is no real divergence here for a three-way merge
    #    to reconcile. `merge --squash`/`merge-tree`, by contrast, compute
    #    their own merge-base -- which, once persist_tip is itself a squash
    #    commit, collapses to the original fork point -- so two lanes that
    #    legitimately touch the same lines in sequence would spuriously
    #    conflict there even though nothing has actually diverged. `-n` dry
    #    runs the same application without touching the index or worktree,
    #    and `-u -m` on its own refuses (leaving both untouched) if a local
    #    modification collides with a path candidate changes -- exactly the
    #    check this precondition needs, for free.
    candidate_tree = run_git(root, "rev-parse", f"{candidate}^{{tree}}").stdout.strip()
    dry_run = run_git(
        persist_path, "read-tree", "-n", "-u", "-m", persist_tip, candidate, check=False
    )
    if dry_run.returncode != 0:
        detail = dry_run.stderr.strip() or dry_run.stdout.strip()
        raise OrchestrateError(f"dry-run landing would not apply cleanly: {detail}")

    # 8. --final claims everything is landed: the candidate must equal the tip.
    if final and candidate != tip:
        raise OrchestrateError(
            f"--final requires the candidate {candidate} to equal the integration tip {tip}; "
            "it is behind the tip"
        )

    # Action: the same two-tree read-tree application, for real this time,
    # then commit exactly what it staged. Never `commit -a`, which would
    # sweep in the unstaged user dirt precondition 6 deliberately permits.
    applied = run_git(
        persist_path, "read-tree", "-u", "-m", persist_tip, candidate, check=False
    )
    if applied.returncode != 0:
        detail = applied.stderr.strip() or applied.stdout.strip()
        raise OrchestrateError(f"git read-tree failed while landing: {detail}")
    subject = str(args.message) if args.message else f"Land {task}"
    message = f"{subject}\n\nTask: {task}\nLanded: {candidate}"
    committed = run_git(persist_path, "commit", "-m", message, check=False)
    if committed.returncode != 0:
        detail = committed.stderr.strip() or committed.stdout.strip()
        raise OrchestrateError(f"git commit failed while recording landing: {detail}")

    # Postconditions: assert, do not trust. A mutation has already happened,
    # so a failure here is reported, not refused.
    landed_sha = run_git(persist_path, "rev-parse", "HEAD").stdout.strip()
    landed_tree = run_git(persist_path, "rev-parse", "HEAD^{tree}").stdout.strip()
    errors: list[str] = []
    if landed_tree != candidate_tree:
        errors.append(
            f"landed tree {landed_tree} does not equal candidate tree {candidate_tree}"
        )
    for path, before in dirty_digests.items():
        after = _path_digest(persist_path / path)
        if after != before:
            errors.append(f"preserved path changed during landing: {path}")

    behind_tip = int(
        run_git(root, "rev-list", "--count", f"{candidate}..{tip}").stdout.strip()
    )
    return {
        "ok": not errors,
        "operation": "integration-land",
        "task_id": task,
        "persist_branch": persist,
        "persist_worktree": str(persist_path),
        "candidate": candidate,
        "landed_sha": landed_sha,
        "tree": landed_tree,
        "final": final,
        "previous_persist_tip": persist_tip,
        "behind_tip": behind_tip,
        "preserved_dirty_paths": dirty_paths,
        "errors": errors,
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


def _verify_immutable_surface(
    root: Path, base: str, tip: str
) -> tuple[list[str], list[str]]:
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

    The walk is ``--first-parent``: it follows only this lane's own line of
    development.  Since a lane now merges the integration tip into itself
    before collecting (the staleness step in `command_integration_collect`),
    another lane's commits enter ``base..tip`` on the merge's second-parent
    side; without ``--first-parent`` every one of those foreign commits that
    happens to touch a path this lane declared ``Immutable:`` would be
    reported as a violation, even though it is not this lane's own edit.
    With ``--first-parent`` only this lane's own commits, plus the merge
    commit itself, are checked -- and the merge commit is checked exactly
    once, against its own first parent: it still appears (and is a genuine
    violation, unless it redeclares) when the incoming work really does
    rewrite the frozen path relative to what this lane already had.
    """
    declarations = _first_declaring_commits(root, base, tip)
    declared = sorted(declarations)
    violations: list[str] = []
    for path in declared:
        declaring_commit = declarations[path]
        raw = run_git(
            root,
            "log",
            "--first-parent",
            "--reverse",
            "--format=%H",
            f"{declaring_commit}..{tip}",
            "--",
            path,
        ).stdout
        for sha in raw.splitlines():
            if not sha:
                continue
            if path not in _immutable_paths(root, sha):
                violations.append(
                    f"{path} changed by {sha} without redeclaring Immutable: {path}"
                )
    return declared, violations


def _conflicted_paths(worktree: Path) -> list[str]:
    """Paths left in an unresolved-conflict state by an aborted-before-commit merge.

    ``git status --porcelain`` reports an in-progress conflict with one of
    the seven ``XY`` codes where both sides are non-space (``UU``, ``AA``,
    ``DD``, ``AU``, ``UA``, ``DU``, ``UD``); every other code is an ordinary
    staged/unstaged change, not a conflict.  ``-z`` matches ``_dirty_paths``
    above for the same reason: unquoted, unescaped paths for this repo's
    non-ASCII filenames.
    """
    conflict_codes = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
    raw = run_git(worktree, "status", "--porcelain", "-z").stdout
    return [
        entry[3:] for entry in raw.split("\0") if entry and entry[:2] in conflict_codes
    ]


def command_integration_collect(args: argparse.Namespace) -> dict[str, Any]:
    """Collect one lane's exact clean tip into the task's integration branch.

    Conflict resolution happens in the lane, not in the shared integration
    worktree -- the same model Git itself uses for pull-then-push: the side
    that is behind integrates first, in its own checkout, and only then does
    the shared branch move.  See the "staleness" step below.
    """
    task = require_identifier(str(args.task_id), label="task id")
    lane = require_identifier(str(args.lane_id), label="lane id")
    root = Path(args.root).resolve()
    sha = exact_commit(root, str(args.sha), label="sha")
    lane_branch = f"wave/{task}/{lane}"
    lane_path = managed_worktree_root(root) / f"{task}-{lane}"

    # 1. lane tree clean.
    lane_state = _status(
        root,
        lane_path,
        lane_branch,
        require_expected_branch=True,
        identity_label="lane worktree",
    )
    if not lane_state["exists"]:
        raise OrchestrateError(f"managed lane worktree does not exist: {lane_path}")
    if not lane_state["clean"]:
        raise OrchestrateError(f"lane worktree must be clean: {lane_path}")

    # 2. --sha is the exact tip of the lane branch, as the caller last saw
    #    it -- checked before any staleness merge, since the caller cannot
    #    assert a SHA that merge has not created yet.
    tip = run_git(root, "rev-parse", "--verify", lane_branch).stdout.strip()
    if sha != tip:
        raise OrchestrateError(
            f"--sha must be the tip of lane branch {lane_branch}: expected {tip}, got {sha}"
        )

    task_id, integration_path, integration_branch = _integration_identity(args)

    # 3. Staleness: if the lane is behind the integration tip, integrate the
    #    integration tip into the lane *first*, in the lane's own worktree --
    #    never in the integration worktree, which must stay pristine, written
    #    only by successful collects.  Skipped when the integration tip is
    #    already part of the lane's own history (the common case: the first
    #    lane collected, or a lane whose base already includes it).
    integration_tip = run_git(
        root, "rev-parse", "--verify", "--quiet", integration_branch, check=False
    ).stdout.strip()
    working_tip = tip
    if (
        integration_tip
        and run_git(
            root, "merge-base", "--is-ancestor", integration_tip, tip, check=False
        ).returncode
        != 0
    ):
        merge = run_git(
            lane_path, "merge", "--no-ff", "--no-commit", integration_tip, check=False
        )
        if merge.returncode:
            conflicts = _conflicted_paths(lane_path)
            detail = (
                ", ".join(conflicts)
                if conflicts
                else (merge.stderr.strip() or merge.stdout.strip())
            )
            raise OrchestrateError(
                "collect refused: the lane is behind the integration tip and merging it in "
                f"conflicted in the lane worktree {lane_path}: {detail}; resolve the conflict in "
                "the lane worktree, commit it there, and re-run collect with the lane's new tip"
            )
        message = f"Merge integration into lane {lane}\n\nTask: {task_id}\nLane: {lane}"
        committed = run_git(lane_path, "commit", "-m", message, check=False)
        if committed.returncode:
            detail = committed.stderr.strip() or committed.stdout.strip()
            raise OrchestrateError(
                f"git commit failed while recording lane staleness merge: {detail}"
            )
        working_tip = run_git(lane_path, "rev-parse", "HEAD").stdout.strip()

    # 4. every commit that changes a once-declared Immutable: path
    #    redeclares it, walking only this lane's own line of development
    #    (first-parent): step 3 may have merged the integration tip in, and
    #    other lanes' commits must not be misattributed to this one.
    lane_base = _lane_base(root, task, lane)
    declared, violations = _verify_immutable_surface(root, lane_base, working_tip)
    if violations:
        raise OrchestrateError(
            "lane changed an Immutable-declared path without redeclaring it in the same commit: "
            + "; ".join(violations)
        )

    integration_state = _status(
        root,
        integration_path,
        integration_branch,
        require_expected_branch=True,
        identity_label="integration worktree",
    )
    if not integration_state["exists"]:
        raise OrchestrateError(
            f"managed integration worktree does not exist: {integration_path}"
        )
    if not integration_state["clean"]:
        raise OrchestrateError(
            f"integration worktree must be clean: {integration_path}"
        )

    # Step 3 guarantees the integration tip is now an ancestor of
    # working_tip, so this is always a fast-forward situation forced to
    # record a collect commit -- its conflict path is unreachable.
    merged = run_git(
        integration_path, "merge", "--no-ff", "--no-commit", working_tip, check=False
    )
    if merged.returncode:
        detail = (
            merged.stderr.strip()
            or merged.stdout.strip()
            or "integration collect conflict"
        )
        raise OrchestrateError(f"git integration collect failed: {detail}")
    message = f"Collect lane {lane}\n\nTask: {task_id}\nLane: {lane}"
    committed = run_git(integration_path, "commit", "-m", message, check=False)
    if committed.returncode:
        detail = committed.stderr.strip() or committed.stdout.strip()
        raise OrchestrateError(
            f"git commit failed while recording integration collect: {detail}"
        )
    collect_sha = run_git(integration_path, "rev-parse", "HEAD").stdout.strip()

    run_git(root, "worktree", "remove", str(lane_path))

    return {
        "ok": True,
        "operation": "integration-collect",
        "task_id": task_id,
        "lane_id": lane,
        "sha": sha,
        "merged_sha": working_tip,
        "collect_sha": collect_sha,
        "immutable_paths_verified": declared,
        "branch": integration_branch,
        "worktree": str(integration_path),
        "lane_worktree_removed": str(lane_path),
    }


def _task_refs(root: Path, task: str) -> list[str]:
    """Every ref under ``refs/orchestrate/<task>/``: integration base, every
    lane base, and the candidate ref, whichever of these currently exist.
    """
    raw = run_git(
        root, "for-each-ref", "--format=%(refname)", f"refs/orchestrate/{task}/"
    ).stdout
    return sorted(line for line in raw.splitlines() if line)


def _task_branches(root: Path, task: str) -> list[str]:
    """Every branch matching ``wave/<task>/*``, including ``wave/<task>/integration``."""
    raw = run_git(
        root, "for-each-ref", "--format=%(refname:short)", f"refs/heads/wave/{task}/"
    ).stdout
    return sorted(line for line in raw.splitlines() if line)


def _find_landing_commit(root: Path, integration_tip: str) -> str | None:
    """Find a local branch's own commit carrying ``Landed: <integration_tip>``.

    S5.7 defines "landed" as "some local branch has a commit whose Landed:
    trailer names the integration tip" -- scoped to ``--branches``
    (``refs/heads/*``) so only a real persistence branch's landing commit can
    satisfy it, never a transient ref under ``refs/orchestrate/``. Each
    branch tip's own first-parent history is walked (not full ancestry, and
    not every commit in the repository): the landing commit `integration
    land` creates always sits on the persist branch's own first-parent
    chain, so this is a cheap, robust proof of "landed" without scanning
    unrelated history.
    """
    branch_tips = [
        line
        for line in run_git(
            root, "for-each-ref", "--format=%(objectname)", "refs/heads/"
        ).stdout.splitlines()
        if line
    ]
    for branch_tip in branch_tips:
        raw = run_git(
            root,
            "log",
            "--first-parent",
            "--format=%H%x00%(trailers:key=Landed,valueonly)",
            branch_tip,
        ).stdout
        for line in raw.splitlines():
            if not line:
                continue
            sha, _, landed = line.partition("\x00")
            if landed.strip() == integration_tip:
                return sha
    return None


def command_integration_remove(args: argparse.Namespace) -> dict[str, Any]:
    """Tear down one task's worktrees, refs, and branches -- the close-out S5.7 requires.

    Safety comes before any mutation (Fast Fail): the integration branch
    must be landed (some local branch carries a commit whose ``Landed:``
    trailer names its tip) and every lane branch must be collected (its tip
    is an ancestor of the integration tip) before anything is deleted.
    Deleting a branch that was never landed or collected destroys work that
    has no other home, so a caller must pass ``--abandon`` to proceed
    anyway; without it, remove refuses and names exactly what is unlanded
    or uncollected.
    """
    task, path, branch = _integration_identity(args)
    root = Path(args.root).resolve()
    abandon = bool(getattr(args, "abandon", False))

    state = _status(root, path, branch)
    if not state["exists"]:
        raise OrchestrateError(f"managed integration worktree does not exist: {path}")
    if not state["clean"] and abandon:
        merge_head = run_git(
            path, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False
        )
        if merge_head.returncode == 0:
            aborted = run_git(path, "merge", "--abort", check=False)
            if aborted.returncode:
                detail = aborted.stderr.strip() or aborted.stdout.strip()
                raise OrchestrateError(
                    f"cannot abandon conflicted integration merge at {path}: {detail}"
                )
            state = _status(root, path, branch)
    if not state["clean"]:
        raise OrchestrateError(
            f"cannot remove worktree because it is not clean: {path}"
        )
    acceptance_path = _acceptance_worktree_path(root, task)
    acceptance_state = _status(
        root, acceptance_path, "", identity_label="acceptance worktree"
    )
    if acceptance_state["exists"] and not acceptance_state["clean"]:
        raise OrchestrateError(
            f"cannot remove worktree because it is not clean: {acceptance_path}"
        )

    integration_tip = run_git(
        root, "rev-parse", "--verify", "--quiet", branch, check=False
    ).stdout.strip()
    unlanded: list[str] = []
    if integration_tip and _find_landing_commit(root, integration_tip) is None:
        unlanded.append(branch)
    uncollected: list[str] = []
    for lane in _list_lanes(root, task):
        lane_branch = f"wave/{task}/{lane}"
        lane_tip = run_git(
            root, "rev-parse", "--verify", "--quiet", lane_branch, check=False
        ).stdout.strip()
        if not lane_tip:
            continue
        collected = (
            bool(integration_tip)
            and run_git(
                root,
                "merge-base",
                "--is-ancestor",
                lane_tip,
                integration_tip,
                check=False,
            ).returncode
            == 0
        )
        if not collected:
            uncollected.append(lane_branch)
    if (unlanded or uncollected) and not abandon:
        parts: list[str] = []
        if unlanded:
            parts.append(f"unlanded: {', '.join(unlanded)}")
        if uncollected:
            parts.append(f"uncollected: {', '.join(uncollected)}")
        raise OrchestrateError(
            "integration remove refused, nothing deleted (" + "; ".join(parts) + "); "
            "pass --abandon to remove anyway if this task's work has no other home"
        )

    run_git(root, "worktree", "remove", str(path))
    if acceptance_state["exists"]:
        run_git(root, "worktree", "remove", str(acceptance_path))

    removed_refs = _task_refs(root, task)
    for ref in removed_refs:
        run_git(root, "update-ref", "-d", ref)
    removed_branches = _task_branches(root, task)
    for removed_branch in removed_branches:
        run_git(root, "branch", "-D", removed_branch)

    return {
        "ok": True,
        "operation": "integration-remove",
        "task_id": task,
        "worktree": str(path),
        "acceptance_worktree": str(acceptance_path),
        "branch": branch,
        "removed": True,
        "removed_refs": removed_refs,
        "removed_branches": removed_branches,
        "abandoned": bool(unlanded or uncollected),
    }


_WORKFLOW_TRAILER_KEYS = frozenset({"Task", "Lane", "Landed"})


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
            (
                candidate
                for candidate in _WORKFLOW_TRAILER_KEYS
                if key.casefold() == candidate.casefold()
            ),
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
    lines = run_git(
        root, "log", "--format=%ct", "--reverse", f"{base}..{tip}"
    ).stdout.splitlines()
    if not lines:
        return int(run_git(root, "show", "-s", "--format=%ct", base).stdout.strip()), 0
    return int(lines[0]), len(lines)


def _report_lane(
    root: Path, task: str, record: dict[str, Any]
) -> tuple[dict[str, Any], int, int]:
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
            1
            for other_start, other_end in intervals
            if start <= other_end and other_start <= end
        )
        best = max(best, overlapping)
    return best


def command_report(args: argparse.Namespace) -> dict[str, Any]:
    """Report everything Git can prove about one task: lanes, checks, and candidate.

    The report combines per-lane span/output, four cheap Git checks, and the
    ready-candidate projection already exposed by ``integration status``. It
    is entirely read-only: nothing here is ever refused, only presented.
    """
    task = require_identifier(str(args.task_id), label="task id")
    root = Path(args.root).resolve()
    base = _integration_base(root, task)
    _task_id, _integration_path, integration_branch = _integration_identity(args)
    tip = (
        run_git(
            root, "rev-parse", "--verify", "--quiet", integration_branch, check=False
        ).stdout.strip()
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
        root,
        base,
        tip,
        [
            {"lane": record["lane"], "timestamp": record["timestamp"]}
            for record in records
        ],
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
