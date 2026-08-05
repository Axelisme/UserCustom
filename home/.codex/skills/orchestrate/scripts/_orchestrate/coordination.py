from __future__ import annotations

import os
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .git_ops import (
    changed_paths,
    commit_subject,
    commit_trailer_values,
    first_parent_added_lines,
    first_parent_changed_paths,
    first_parent_range,
    immutable_declarations,
    merge_in_progress,
    reachable_commits,
    ref_exists,
    ref_namespace_collision,
    run_git,
    worktree_for,
    worktree_records,
)
from .primitives import CommandResult, OrchestrateError, require_identifier
from .resources import (
    LaneResources,
    RepositoryContext,
    TaskResources,
    active_task_ids,
    lexical_path,
    resolved_path,
    worktree_state,
)
from .telemetry import lane_comments, record_event, write_report


def _task(repo: RepositoryContext, task_id: str) -> TaskResources:
    return TaskResources.derive(repo, task_id)


def _branch_exists(repo: RepositoryContext, branch: str) -> bool:
    return run_git(repo.worktree_root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0


def _ref(repo: RepositoryContext, ref: str) -> str | None:
    probe = run_git(repo.worktree_root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    return probe.stdout.strip() if probe.returncode == 0 else None


def _error(message: str, code: str) -> None:
    raise OrchestrateError(message, code)


@dataclass(frozen=True)
class _LaneProjection:
    lane: LaneResources
    sha: str
    uncollected: int


@dataclass(frozen=True)
class _TaskProjection:
    integration: str
    lanes: dict[str, _LaneProjection]
    pending: int
    warnings: tuple[str, ...]


def collect_lane_id(
    repo: RepositoryContext,
    task: TaskResources,
    sha: str,
) -> str | None:
    """Recognize one production collect commit without introducing state."""
    task_values = commit_trailer_values(repo.worktree_root, sha, "Task")
    lane_values = commit_trailer_values(repo.worktree_root, sha, "Lane")
    ticket_values = commit_trailer_values(repo.worktree_root, sha, "Ticket")
    if len(task_values) != 1 or task_values[0] != task.task_id:
        return None
    if len(lane_values) != 1 or len(ticket_values) != 1:
        return None
    try:
        lane = task.lane(lane_values[0])
        require_identifier(ticket_values[0], label="ticket")
    except OrchestrateError:
        return None
    if commit_subject(repo.worktree_root, sha) != f"Collect lane {lane.lane_id}":
        return None
    return lane.lane_id


def task_projection(repo: RepositoryContext, task: TaskResources) -> _TaskProjection:
    """Derive lane state, pending work, and warning inputs from Git."""
    base = _ref(repo, task.integration_base_ref)
    if base is None:
        _error("task integration base is missing", "task_not_found")
    integration = _ref(repo, task.integration_branch)
    if integration is None:
        _error("task integration branch is missing", "task_state_invalid")

    lane_ids: set[str] = set()
    base_ids: set[str] = set()
    branch_ids: set[str] = set()
    worktree_ids: set[str] = set()

    def add_lane_id(candidate: str, inventory: set[str]) -> None:
        try:
            task.lane(candidate)
        except OrchestrateError:
            return
        inventory.add(candidate)
        lane_ids.add(candidate)

    ref_prefix = f"refs/orchestrate/{task.task_id}/"
    refs = run_git(
        repo.worktree_root,
        "for-each-ref",
        "--format=%(refname)",
        ref_prefix,
    ).stdout.splitlines()
    for ref in refs:
        suffix = ref.removeprefix(ref_prefix)
        if suffix.count("/") == 1 and suffix.endswith("/base"):
            add_lane_id(suffix.removesuffix("/base"), base_ids)

    branch_prefix = f"refs/heads/wave/{task.task_id}/"
    branches = run_git(
        repo.worktree_root,
        "for-each-ref",
        "--format=%(refname)",
        branch_prefix,
    ).stdout.splitlines()
    for branch in branches:
        suffix = branch.removeprefix(branch_prefix)
        if "/" not in suffix:
            add_lane_id(suffix, branch_ids)

    lanes_root = task.root / "lanes"
    for record in worktree_records(repo.worktree_root):
        raw_path = record.get("worktree")
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path)
        if path.parent == lanes_root:
            add_lane_id(path.name, worktree_ids)

    reachable = reachable_commits(repo.worktree_root, integration)
    warnings: list[str] = []
    lanes: dict[str, _LaneProjection] = {}
    for lane_id in sorted(lane_ids):
        lane = task.lane(lane_id)
        base_value = _ref(repo, lane.base_ref) if lane_id in base_ids else None
        branch_value = _ref(repo, lane.branch) if lane_id in branch_ids else None
        if base_value is None or branch_value is None:
            warnings.append(f"lane resource is incomplete: {lane_id}")
            continue
        commits = first_parent_range(repo.worktree_root, base_value, branch_value)
        if commits is None:
            warnings.append(f"lane base is not on first-parent history: {lane_id}")
            continue
        uncollected = sum(commit not in reachable for commit in commits)
        lanes[lane_id] = _LaneProjection(lane, branch_value, uncollected)

    accepted = _ref(repo, task.accepted_ref)
    lower = accepted if accepted is not None else base
    collect_commits = first_parent_range(repo.worktree_root, lower, integration)
    collected_lanes: set[str] = set()
    if collect_commits is not None:
        for sha in collect_commits:
            lane_id = collect_lane_id(repo, task, sha)
            if lane_id is not None:
                collected_lanes.add(lane_id)
    pending = sum(
        projection.uncollected == 0 and lane_id in collected_lanes
        for lane_id, projection in lanes.items()
    )
    return _TaskProjection(
        integration=integration,
        lanes=lanes,
        pending=pending,
        warnings=tuple(warnings),
    )


def status(repo: RepositoryContext, task_id: str | None = None) -> CommandResult:
    if task_id is None:
        return CommandResult(True, {"tasks": active_task_ids(repo)})
    task = _task(repo, task_id)
    projection = task_projection(repo, task)
    comments = lane_comments(task)
    lanes: dict[str, dict[str, object]] = {}
    for lane_id, lane in projection.lanes.items():
        lane_status: dict[str, object] = {
            "sha": lane.sha,
            "uncollected": lane.uncollected,
        }
        comment = comments.get(lane_id)
        if comment is not None:
            lane_status["comment"] = comment
        lanes[lane_id] = lane_status

    data: dict[str, Any] = {
        "task_id": task.task_id,
        "integration": projection.integration,
        "lanes": lanes,
        "pending": projection.pending,
    }
    for key, ref in (
        ("accepted", task.accepted_ref),
        ("user_accepted", task.user_accepted_ref),
        ("landed", task.landed_ref),
    ):
        value = _ref(repo, ref)
        if value is not None:
            data[key] = value
    if projection.warnings:
        data["warnings"] = list(projection.warnings[:20])
    return CommandResult(True, data)


def integration_create(repo: RepositoryContext, task_id: str) -> CommandResult:
    task = _task(repo, task_id)
    if task.collision():
        _error(f"task {task.task_id} already has managed resources", "task_resource_collision")
    head = run_git(repo.worktree_root, "rev-parse", "HEAD").stdout.strip()
    task.integration_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_git(repo.worktree_root, "worktree", "add", "-b", task.integration_branch, str(task.integration_path), head)
        run_git(repo.worktree_root, "update-ref", task.integration_base_ref, head)
    except OrchestrateError:
        # The preflight makes this path unreachable for the supported local Git envelope.
        raise
    warnings = record_event(task, "integration-create", "success")
    return CommandResult(True, {}, warnings)


def _path_df_collision(path: Path) -> bool:
    if os.path.lexists(path):
        return True
    parent = path.parent
    while parent != parent.parent:
        if os.path.lexists(parent):
            return parent.is_symlink() or not parent.is_dir()
        parent = parent.parent
    return False


def _active_integration_tip(repo: RepositoryContext, task: TaskResources) -> str:
    base = _ref(repo, task.integration_base_ref)
    if base is None:
        _error("task integration base does not exist", "task_not_found")
    integration = _ref(repo, task.integration_branch)
    if integration is None:
        _error("task integration branch does not resolve", "task_state_invalid")
    state = worktree_state(repo, task.integration_path)
    if (
        not state["exists"]
        or state["branch"] != task.integration_branch
        or state["head"] != integration
    ):
        _error("task integration worktree is invalid", "task_state_invalid")
    return integration


def _create_lane_resources(
    repo: RepositoryContext,
    task: TaskResources,
    lane_id: str,
    integration: str,
) -> LaneResources:
    """Create one exact lane inventory after its caller validates integration."""
    lane = task.lane(lane_id)
    branch_ref = f"refs/heads/{lane.branch}"
    if (
        ref_namespace_collision(repo.worktree_root, branch_ref)
        or ref_namespace_collision(repo.worktree_root, lane.base_ref)
        or _path_df_collision(lane.path)
    ):
        _error(
            "lane managed resource collides with existing inventory",
            "lane_resource_collision",
        )
    lane.path.parent.mkdir(parents=True, exist_ok=True)
    run_git(
        repo.worktree_root,
        "worktree",
        "add",
        "-b",
        lane.branch,
        str(lane.path),
        integration,
    )
    run_git(repo.worktree_root, "update-ref", lane.base_ref, integration)
    return lane


def _annotation(value: str) -> str:
    if any(unicodedata.category(character).startswith("C") for character in value):
        _error("lane comment must not contain control characters", "cli_usage")
    normalized = value.strip()
    if not normalized:
        _error("lane comment must not be empty", "cli_usage")
    if len(normalized) > 500:
        _error("lane comment must be at most 500 Unicode characters", "cli_usage")
    return normalized


def lane_create(
    repo: RepositoryContext,
    task_id: str,
    lane_id: str,
    comment: str | None = None,
) -> CommandResult:
    task = _task(repo, task_id)
    normalized = _annotation(comment) if comment is not None else None
    integration = _active_integration_tip(repo, task)
    lane = _create_lane_resources(repo, task, lane_id, integration)
    event_extra: dict[str, object] = {"lane_id": lane.lane_id}
    if normalized is not None:
        event_extra["comment"] = normalized
    event_warnings = record_event(task, "lane-create", "success", **event_extra)
    projection = task_projection(repo, task)
    uncollected_count = sum(
        lane.uncollected > 0 for lane in projection.lanes.values()
    )
    count_warnings = (
        (
            f"task has {uncollected_count} lanes with uncollected work; Root "
            "should collect/drop unneeded lanes",
        )
        if uncollected_count >= 9
        else ()
    )
    return CommandResult(True, {}, (*event_warnings, *count_warnings))


def lane_comment(
    repo: RepositoryContext,
    task_id: str,
    lane_id: str,
    text: str | None,
    clear: bool,
) -> CommandResult:
    task = _task(repo, task_id)
    lane = task.lane(lane_id)
    projected = status(repo, task.task_id).data.get("lanes", {})
    if not isinstance(projected, dict) or lane.lane_id not in projected:
        _error("lane is not a currently projected active lane", "lane_not_found")
    normalized = None if clear else _annotation(text or "")
    current = lane_comments(task).get(lane.lane_id)
    warnings: tuple[str, ...] = ()
    if current == normalized:
        warnings = ("lane comment is already current",)
    event_warnings = record_event(
        task,
        "lane-comment",
        "success",
        lane_id=lane.lane_id,
        comment=normalized,
    )
    return CommandResult(True, {}, (*warnings, *event_warnings))


@dataclass(frozen=True)
class LaneValidation:
    lane: LaneResources
    tip: str | None
    base: str | None
    first_parent_valid: bool
    protected_paths: tuple[str, ...]
    contract_commits: tuple[str, ...]
    ticket_contract_commits: tuple[str, ...]
    ticket_contract_added_lines: int
    diagnostics: tuple[dict[str, str], ...]

    @property
    def ready(self) -> bool:
        return not self.diagnostics


def _diagnostic(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _normalized_immutable_path(value: str) -> bool:
    candidate = PurePosixPath(value)
    return (
        bool(value)
        and "\\" not in value
        and not candidate.is_absolute()
        and value == candidate.as_posix()
        and value not in {".", ".."}
        and ".." not in candidate.parts
        and "//" not in value
        and not value.endswith("/")
    )


def _lane_validation(
    repo: RepositoryContext,
    task: TaskResources,
    lane_id: str,
) -> LaneValidation:
    """One read-only state model shared by check and collect."""
    lane = task.lane(lane_id)
    state = worktree_state(repo, lane.path)
    if not state["exists"]:
        return LaneValidation(
            lane,
            None,
            None,
            False,
            (),
            (),
            (),
            0,
            (_diagnostic("lane_not_found", "lane worktree does not exist"),),
        )

    diagnostics: list[dict[str, str]] = []
    if state["branch"] != lane.branch:
        diagnostics.append(
            _diagnostic(
                "worktree_identity_mismatch",
                "lane worktree is not attached to its managed branch",
            )
        )
    if not state["clean"] or merge_in_progress(lane.path):
        diagnostics.append(_diagnostic("dirty_worktree", "lane worktree is dirty"))

    tip = _ref(repo, lane.branch)
    base = _ref(repo, lane.base_ref)
    if tip is None or base is None:
        diagnostics.append(
            _diagnostic("lane_not_ready", "lane branch or base ref is missing")
        )

    protected: set[str] = set()
    contract_commits: list[str] = []
    ticket_contract: list[str] = []
    ticket_added_lines = 0
    commits = first_parent_range(repo.worktree_root, base, tip) if base and tip else None
    first_parent_valid = commits is not None
    if base and tip and commits is None:
        diagnostics.append(
            _diagnostic("lane_not_ready", "lane tip is not on the lane base first-parent range")
        )
    elif commits is not None:
        immutable_invalid = False
        immutable_violation = False
        for sha in commits:
            if "contract" in commit_trailer_values(repo.worktree_root, sha, "Origin"):
                contract_commits.append(sha)
            declared = immutable_declarations(repo.worktree_root, sha)
            valid = [value for value in declared if _normalized_immutable_path(value)]
            if len(valid) != len(declared):
                immutable_invalid = True
            declared_set = set(valid)
            changed = set(first_parent_changed_paths(repo.worktree_root, sha))
            if (changed & protected) - declared_set:
                immutable_violation = True
            protected.update(declared_set)
        if immutable_invalid or immutable_violation:
            details = []
            if immutable_invalid:
                details.append("malformed Immutable declaration")
            if immutable_violation:
                details.append("protected path changed without redeclaration")
            diagnostics.append(_diagnostic("lane_not_ready", "; ".join(details)))

        # A persistent lane keeps its original base across collect cycles, so its
        # whole first-parent range accumulates every ticket it ever served. The
        # Contract this ticket froze is the part integration has not collected.
        integration = _ref(repo, task.integration_branch)
        collected = (
            reachable_commits(repo.worktree_root, integration)
            if integration is not None
            else frozenset()
        )
        ticket_contract = [sha for sha in contract_commits if sha not in collected]
        ticket_added_lines = sum(
            first_parent_added_lines(repo.worktree_root, sha) for sha in ticket_contract
        )

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in diagnostics:
        identity = (item["code"], item["message"])
        if identity not in seen:
            unique.append(item)
            seen.add(identity)
    return LaneValidation(
        lane,
        tip,
        base,
        first_parent_valid,
        tuple(sorted(protected)),
        tuple(contract_commits),
        tuple(ticket_contract),
        ticket_added_lines,
        tuple(unique[:20]),
    )


def _raise_lane_refusal(validation: LaneValidation) -> None:
    first = validation.diagnostics[0]
    _error(first["message"], first["code"])


def lane_check(
    repo: RepositoryContext,
    task_id: str,
    lane_id: str,
    expect_mode: str | None = None,
) -> CommandResult:
    task = _task(repo, task_id)
    validation = _lane_validation(repo, task, lane_id)
    if not validation.ready:
        return CommandResult(
            False,
            {
                "error": {
                    "code": "lane_not_ready",
                    "message": "lane is not ready for collection",
                }
            },
            diagnostics=validation.diagnostics,
        )
    if expect_mode is not None:
        # Root declares the ticket's admitted mode per call; orchestrate reads
        # the mode it was handed against Git and still stores no task narrative.
        frozen = bool(validation.ticket_contract_commits)
        if expect_mode == "tdd" and not frozen:
            return CommandResult(
                False,
                {
                    "error": {
                        "code": "validation_mode_mismatch",
                        "message": (
                            "lane was admitted TDD and freezes no Contract commit "
                            "for this ticket"
                        ),
                    }
                },
            )
        if expect_mode == "direct" and frozen:
            return CommandResult(
                False,
                {
                    "error": {
                        "code": "validation_mode_mismatch",
                        "message": (
                            "lane was admitted direct and freezes "
                            f"{len(validation.ticket_contract_commits)} Contract "
                            "commits for this ticket"
                        ),
                    }
                },
            )
    lane_tip = validation.tip
    lane_base = validation.base
    assert lane_tip is not None and lane_base is not None
    warnings = list(record_event(task, "lane-check", "success", lane_id=lane_id))
    gate = repo.worktree_root / ".agent_state" / "orchestrate" / task.task_id / "gate.sh"
    if gate.is_file():
        # Factual like the ninth-lane warning: the reminder fires, the check
        # still succeeds, and a repository with no gate script is never nagged.
        warnings.append(
            f"gate script present at {gate.relative_to(repo.worktree_root)}; "
            "S2.5 evidence comes from running it"
        )
    return CommandResult(
        True,
        {
            "sha": lane_tip,
            "base": lane_base,
            "protected_paths": list(validation.protected_paths),
            "contract_commits": list(validation.contract_commits),
            "ticket_contract_commits": list(validation.ticket_contract_commits),
            "ticket_contract_added_lines": validation.ticket_contract_added_lines,
        },
        tuple(warnings),
    )


def _integration_state_ready(repo: RepositoryContext, task: TaskResources) -> None:
    integration_state = worktree_state(repo, task.integration_path)
    if not integration_state["exists"]:
        _error("integration worktree does not exist", "task_state_invalid")
    if integration_state["branch"] != task.integration_branch:
        _error("integration worktree identity mismatch", "worktree_identity_mismatch")
    if not integration_state["clean"] or merge_in_progress(task.integration_path):
        _error("integration worktree is dirty", "dirty_worktree")
    tip = _ref(repo, task.integration_branch)
    if tip is None or integration_state["head"] != tip:
        _error("integration branch is invalid", "task_state_invalid")


def integration_collect(
    repo: RepositoryContext,
    task_id: str,
    lane_id: str,
    ticket: str,
) -> CommandResult:
    task = _task(repo, task_id)
    bounded_ticket = require_identifier(ticket, label="ticket")
    validation = _lane_validation(repo, task, lane_id)
    if not validation.ready:
        _raise_lane_refusal(validation)
    lane = validation.lane
    lane_tip = validation.tip
    assert lane_tip is not None
    _integration_state_ready(repo, task)
    merge = run_git(
        task.integration_path,
        "merge",
        "--no-ff",
        "--no-commit",
        lane_tip,
        check=False,
    )
    if merge.returncode:
        run_git(task.integration_path, "merge", "--abort", check=False)
        _error("integration collect has a merge conflict", "merge_conflict")
    message = (
        f"Collect lane {lane.lane_id}\n\n"
        f"Task: {task.task_id}\n"
        f"Lane: {lane.lane_id}\n"
        f"Ticket: {bounded_ticket}"
    )
    run_git(task.integration_path, "commit", "-m", message)
    warnings = record_event(
        task,
        "integration-collect",
        "success",
        lane_id=lane.lane_id,
        subject_sha=lane_tip,
    )
    return CommandResult(True, {}, warnings)


def _reconcile_integration_subject(
    repo: RepositoryContext, task: TaskResources
) -> str:
    integration = _ref(repo, task.integration_branch)
    if integration is None:
        _error("task integration is missing", "task_not_found")
    state = worktree_state(repo, task.integration_path)
    if (
        not state["exists"]
        or state["branch"] != task.integration_branch
        or state["head"] != integration
    ):
        _error("integration worktree identity mismatch", "worktree_identity_mismatch")
    if not state["clean"]:
        _error("integration worktree is dirty", "dirty_worktree")
    return integration


def _checked_out_persistence_tip(
    repo: RepositoryContext, branch_ref: str
) -> str:
    tip = _ref(repo, branch_ref)
    paths: list[Path] = []
    for record in worktree_records(repo.worktree_root):
        raw = record.get("worktree")
        if record.get("branch") == branch_ref and isinstance(raw, str):
            paths.append(Path(raw))
    if tip is None or len(paths) != 1 or not paths[0].is_dir():
        _error(
            "persistence branch must have exactly one checkout",
            "task_state_invalid",
        )
    head = run_git(paths[0], "rev-parse", "HEAD", check=False)
    if head.returncode or head.stdout.strip() != tip:
        _error(
            "persistence checkout is not at its branch tip", "task_state_invalid"
        )
    return tip


def integration_reconcile(
    repo: RepositoryContext, task_id: str, lane_id: str, persist: str
) -> CommandResult:
    task = _task(repo, task_id)
    integration = _reconcile_integration_subject(repo, task)
    persistence = _checked_out_persistence_tip(
        repo, f"refs/heads/{persist}"
    )

    if run_git(
        repo.worktree_root,
        "merge-base",
        "--is-ancestor",
        persistence,
        integration,
        check=False,
    ).returncode == 0:
        event_warnings = record_event(
            task,
            "integration-reconcile",
            "noop",
            lane_id=lane_id,
            persist=persist,
        )
        return CommandResult(
            True,
            {},
            ("persistence is already included in integration", *event_warnings),
        )

    lane = _create_lane_resources(repo, task, lane_id, integration)
    merged = run_git(
        lane.path,
        "merge",
        "--no-ff",
        "--no-commit",
        persistence,
        check=False,
    )
    if merged.returncode:
        _error("persistence reconciliation has conflicts", "merge_conflict")
    return CommandResult(
        True,
        {},
        record_event(
            task,
            "integration-reconcile",
            "success",
            lane_id=lane_id,
            persist=persist,
            subject_sha=persistence,
        ),
    )


def lane_sync(repo: RepositoryContext, task_id: str, lane_id: str) -> CommandResult:
    task = _task(repo, task_id)
    validation = _lane_validation(repo, task, lane_id)
    sync_blocking = [
        item
        for item in validation.diagnostics
        if item["code"] != "lane_not_ready"
    ]
    if (
        sync_blocking
        or validation.tip is None
        or validation.base is None
        or not validation.first_parent_valid
    ):
        _raise_lane_refusal(validation)
    lane_tip = validation.tip
    assert lane_tip is not None
    integration_tip = _active_integration_tip(repo, task)
    current = run_git(
        repo.worktree_root,
        "merge-base",
        "--is-ancestor",
        integration_tip,
        lane_tip,
        check=False,
    )
    if current.returncode == 0:
        event_warnings = record_event(
            task, "lane-sync", "noop", lane_id=validation.lane.lane_id
        )
        return CommandResult(
            True,
            {},
            ("lane already includes latest integration", *event_warnings),
        )

    merge = run_git(
        validation.lane.path,
        "merge",
        "--no-ff",
        "--no-commit",
        integration_tip,
        check=False,
    )
    if merge.returncode:
        _error("integration sync has a merge conflict", "merge_conflict")

    staged = changed_paths(validation.lane.path, "--cached", lane_tip)
    redeclared = sorted(set(staged) & set(validation.protected_paths))
    message_lines = [
        f"Sync integration into lane {validation.lane.lane_id}",
        "",
        f"Task: {task.task_id}",
        f"Lane: {validation.lane.lane_id}",
        *(f"Immutable: {path}" for path in redeclared),
    ]
    run_git(validation.lane.path, "commit", "-m", "\n".join(message_lines))
    return CommandResult(
        True,
        {},
        record_event(
            task, "lane-sync", "success", lane_id=validation.lane.lane_id
        ),
    )


def lane_drop(repo: RepositoryContext, task_id: str, lane_id: str) -> CommandResult:
    task = _task(repo, task_id)
    lane = task.lane(lane_id)
    branch_ref = f"refs/heads/{lane.branch}"
    worktree = worktree_for(repo.worktree_root, lane.path)
    path_present = worktree is not None or os.path.lexists(lane.path)
    branch_present = ref_exists(repo.worktree_root, branch_ref)
    base_present = ref_exists(repo.worktree_root, lane.base_ref)
    present = (path_present, branch_present, base_present)
    if not any(present):
        _error("lane managed inventory does not exist", "lane_not_found")

    if worktree is not None:
        run_git(
            repo.worktree_root,
            "worktree",
            "remove",
            "--force",
            str(lane.path),
        )
    elif os.path.lexists(lane.path):
        if lane.path.is_dir() and not lane.path.is_symlink():
            shutil.rmtree(lane.path)
        else:
            lane.path.unlink()
    if branch_present:
        run_git(repo.worktree_root, "branch", "-D", lane.branch)
    if base_present:
        run_git(repo.worktree_root, "update-ref", "-d", lane.base_ref)

    warnings = () if all(present) else ("lane managed inventory was incomplete",)
    return CommandResult(
        True,
        {},
        (*warnings, *record_event(task, "lane-drop", "success", lane_id=lane.lane_id)),
    )


@dataclass(frozen=True)
class _WorktreeRemoval:
    path: Path
    force: bool
    registered: bool
    lexical_kind: str
    directory_footprint: Path | None


def _paths_overlap(left: Path, right: Path) -> bool:
    left = lexical_path(left)
    right = lexical_path(right)
    return left == right or left in right.parents or right in left.parents


def _is_same_or_descendant(path: Path, directory: Path) -> bool:
    return path == directory or directory in path.parents


def _preflight_worktree_removals(
    repo: RepositoryContext,
    removals: list[tuple[Path, bool]],
) -> list[_WorktreeRemoval]:
    """Freeze lexical cleanup actions before the first destructive operation."""
    planned: list[_WorktreeRemoval] = []
    for path, force in removals:
        registered = worktree_for(repo.worktree_root, path) is not None
        try:
            if not os.path.lexists(path):
                kind = "absent"
            elif path.is_symlink():
                kind = "symlink"
            elif path.is_dir():
                kind = "directory"
            else:
                kind = "file"
        except OSError as exc:
            raise OrchestrateError(
                f"cannot inspect cleanup inventory: {path}",
                "task_state_invalid",
            ) from exc
        directory_footprint = (
            resolved_path(path) if kind == "directory" else None
        )
        planned.append(
            _WorktreeRemoval(
                path,
                force,
                registered,
                kind,
                directory_footprint,
            )
        )
    return planned


def _remove_worktree(repo: RepositoryContext, removal: _WorktreeRemoval) -> None:
    path = removal.path
    if removal.registered:
        run_git(
            repo.worktree_root,
            "worktree",
            "remove",
            *(["--force"] if removal.force else []),
            str(path),
        )
    elif removal.force and removal.lexical_kind != "absent":
        if removal.lexical_kind == "directory":
            shutil.rmtree(path)
        else:
            path.unlink()


def _closed_lane_inventory(
    repo: RepositoryContext, task: TaskResources
) -> list[Any]:
    lane_ids: set[str] = set()
    ref_prefix = f"refs/orchestrate/{task.task_id}/"
    refs = run_git(
        repo.worktree_root,
        "for-each-ref",
        "--format=%(refname)",
        ref_prefix,
    ).stdout.splitlines()
    for ref in refs:
        suffix = ref.removeprefix(ref_prefix)
        if suffix.count("/") == 1 and suffix.endswith("/base"):
            lane_ids.add(suffix.removesuffix("/base"))

    branch_prefix = f"refs/heads/wave/{task.task_id}/"
    branches = run_git(
        repo.worktree_root,
        "for-each-ref",
        "--format=%(refname)",
        branch_prefix,
    ).stdout.splitlines()
    for branch in branches:
        suffix = branch.removeprefix(branch_prefix)
        if "/" not in suffix:
            lane_ids.add(suffix)

    lanes_root = task.root / "lanes"
    for record in worktree_records(repo.worktree_root):
        raw_path = record.get("worktree")
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path)
        if path.parent == lanes_root:
            lane_ids.add(path.name)

    lanes = []
    for lane_id in sorted(lane_ids):
        if lane_id == "integration":
            continue
        try:
            lanes.append(task.lane(lane_id))
        except OrchestrateError:
            continue
    return lanes


def integration_remove(
    repo: RepositoryContext,
    task_id: str,
    *,
    abandon: bool,
    output_dir: Path | None = None,
) -> CommandResult:
    task = _task(repo, task_id)
    if _ref(repo, task.integration_base_ref) is None:
        _error("task does not exist", "task_not_found")
    integration = _ref(repo, task.integration_branch)
    if integration is None:
        _error("integration branch is missing", "task_state_invalid")
    if not abandon:
        integration_state = worktree_state(repo, task.integration_path)
        if (
            not integration_state["exists"]
            or integration_state["branch"] != task.integration_branch
        ):
            _error("integration worktree identity mismatch", "worktree_identity_mismatch")
        if not integration_state["clean"]:
            _error("integration worktree is dirty", "dirty_worktree")
    lanes = _closed_lane_inventory(repo, task)
    accepted = _ref(repo, task.accepted_ref)
    landed = _ref(repo, task.landed_ref)
    base = _ref(repo, task.integration_base_ref)
    integration_tree = run_git(
        repo.worktree_root, "rev-parse", f"{integration}^{{tree}}"
    ).stdout.strip()
    base_tree = run_git(
        repo.worktree_root, "rev-parse", f"{base}^{{tree}}"
    ).stdout.strip()
    no_change = integration_tree == base_tree
    if lanes and not abandon:
        _error("task has active lanes", "task_incomplete")
    complete = accepted == integration and landed == integration
    if not abandon and not no_change and not complete:
        _error("task is not accepted and landed", "task_incomplete")
    removals = [
        (task.acceptance_path, True),
        *((lane.path, True) for lane in lanes),
        (task.telemetry_path, True),
        (task.integration_path, abandon),
    ]
    cleanup = _preflight_worktree_removals(repo, removals)
    telemetry_cleanup = cleanup[-2]
    if telemetry_cleanup.registered or telemetry_cleanup.lexical_kind == "directory":
        _error("telemetry cleanup inventory is invalid", "task_state_invalid")
    cleanup_paths = [removal.path for removal in cleanup]
    if output_dir is not None:
        resolved_output = resolved_path(output_dir)
        overlaps_cleanup = any(
            _paths_overlap(output_dir, path) for path in cleanup_paths
        ) or any(
            removal.directory_footprint is not None
            and _is_same_or_descendant(
                resolved_output,
                removal.directory_footprint,
            )
            for removal in cleanup
        )
        if overlaps_cleanup:
            _error(
                "report output overlaps cleanup inventory",
                "report_write_failed",
            )
    if output_dir is not None:
        write_report(task, output_dir, project_terminal_remove=True)
    warnings: tuple[str, ...] = ()
    for removal in cleanup:
        _remove_worktree(repo, removal)
    for branch in [task.integration_branch, *(lane.branch for lane in lanes)]:
        if _branch_exists(repo, branch):
            run_git(repo.worktree_root, "branch", "-D", branch)
    for ref in [
        task.integration_base_ref,
        *(lane.base_ref for lane in lanes),
        task.accepted_ref,
        task.user_accepted_ref,
        task.landed_ref,
    ]:
        if _ref(repo, ref) is not None:
            run_git(repo.worktree_root, "update-ref", "-d", ref)
    if no_change and not abandon:
        warnings = ("task reverted to its integration base",)
    if task.root.exists():
        try:
            task.root.rmdir()
        except OSError:
            pass
    return CommandResult(True, {}, warnings)
