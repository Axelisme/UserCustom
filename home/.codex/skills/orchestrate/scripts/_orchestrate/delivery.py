from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from .git_ops import (
    changed_paths,
    direct_commit_ref,
    exact_commit,
    run_git,
    worktree_records,
)
from .primitives import CommandResult, OrchestrateError
from .resources import RepositoryContext, TaskResources, worktree_state
from .telemetry import record_event


def _task(repo: RepositoryContext, task_id: str) -> TaskResources:
    return TaskResources.derive(repo, task_id)


def _ref(repo: RepositoryContext, ref: str) -> str | None:
    probe = run_git(
        repo.worktree_root,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{ref}^{{commit}}",
        check=False,
    )
    return probe.stdout.strip() if probe.returncode == 0 else None


def _tree(repo: RepositoryContext, commit: str) -> str:
    return run_git(repo.worktree_root, "rev-parse", f"{commit}^{{tree}}").stdout.strip()


def _is_ancestor(repo: RepositoryContext, ancestor: str, descendant: str) -> bool:
    return (
        run_git(
            repo.worktree_root,
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
            check=False,
        ).returncode
        == 0
    )


def _authority_ref(repo: RepositoryContext, ref: str, *, label: str) -> str | None:
    return direct_commit_ref(repo.worktree_root, ref, label=label)


def _on_integration_first_parent(
    repo: RepositoryContext, integration: str, subject: str
) -> bool:
    history = run_git(
        repo.worktree_root, "rev-list", "--first-parent", integration
    ).stdout.splitlines()
    return subject in history


def _acceptance_subject(
    repo: RepositoryContext,
    task: TaskResources,
    requested_sha: str | None,
) -> str:
    integration = _authority_ref(
        repo,
        f"refs/heads/{task.integration_branch}",
        label="integration branch authority slot",
    )
    if integration is None:
        raise OrchestrateError("task integration is missing", "task_not_found")
    if requested_sha is None:
        return integration
    try:
        subject = exact_commit(
            repo.worktree_root,
            requested_sha,
            label="acceptance SHA",
        )
    except OrchestrateError as exc:
        raise OrchestrateError(str(exc), "acceptance_subject_invalid") from exc
    if not _on_integration_first_parent(repo, integration, subject):
        raise OrchestrateError(
            "acceptance SHA must be an integration first-parent commit",
            "acceptance_subject_invalid",
        )
    return subject


def acceptance_start(
    repo: RepositoryContext,
    task_id: str,
    requested_sha: str | None = None,
) -> CommandResult:
    task = _task(repo, task_id)
    accepted = _authority_ref(repo, task.accepted_ref, label="accepted authority slot")
    subject = _acceptance_subject(repo, task, requested_sha)
    prior = worktree_state(repo, task.acceptance_path)
    superseded = (
        bool(prior["exists"])
        and isinstance(prior["head"], str)
        and prior["head"] != accepted
    )

    if prior["exists"]:
        run_git(
            repo.worktree_root,
            "worktree",
            "remove",
            "--force",
            str(task.acceptance_path),
        )
    elif os.path.lexists(task.acceptance_path):
        if task.acceptance_path.is_dir() and not task.acceptance_path.is_symlink():
            shutil.rmtree(task.acceptance_path)
        else:
            task.acceptance_path.unlink()

    task.acceptance_path.parent.mkdir(parents=True, exist_ok=True)
    run_git(
        repo.worktree_root,
        "worktree",
        "add",
        "--detach",
        str(task.acceptance_path),
        subject,
    )
    start_outcome = "superseded" if superseded else "success"
    return CommandResult(
        True,
        {},
        record_event(task, "acceptance-start", start_outcome, subject_sha=subject),
    )


def _acceptance_tracked_state_is_clean(path: Path) -> bool:
    for args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        probe = run_git(path, *args, check=False)
        if probe.returncode not in (0, 1):
            raise OrchestrateError(
                "cannot inspect acceptance tracked state", "git_error"
            )
        if probe.returncode != 0:
            return False
    return True


def acceptance_result(
    repo: RepositoryContext,
    task_id: str,
    outcome: str,
    verifier: str,
) -> CommandResult:
    task = _task(repo, task_id)
    verifier_refs = {
        "agent": (task.accepted_ref, "accepted authority slot"),
        "user": (task.user_accepted_ref, "user-accepted authority slot"),
    }
    if verifier not in verifier_refs:
        raise OrchestrateError("unsupported acceptance verifier", "cli_usage")
    authority_ref, label = verifier_refs[verifier]
    previous = _authority_ref(repo, authority_ref, label=label)
    state = worktree_state(repo, task.acceptance_path)
    if not state["exists"]:
        raise OrchestrateError("acceptance workspace is missing", "acceptance_missing")
    head = run_git(task.acceptance_path, "rev-parse", "HEAD").stdout.strip()

    integration = _authority_ref(
        repo,
        f"refs/heads/{task.integration_branch}",
        label="integration branch authority slot",
    )
    valid = (
        state["branch"] is None
        and integration is not None
        and _on_integration_first_parent(repo, integration, head)
        and _acceptance_tracked_state_is_clean(task.acceptance_path)
    )
    if not valid:
        raise OrchestrateError(
            "acceptance subject is not a clean detached integration first-parent",
            "acceptance_subject_invalid",
        )

    regressed = False
    ref_updated = False
    current = previous
    if outcome == "pass":
        regressed = (
            previous is not None
            and previous != head
            and _is_ancestor(repo, head, previous)
        )
        if previous != head:
            run_git(repo.worktree_root, "update-ref", authority_ref, head)
            ref_updated = True
        current = head
    elif outcome == "fail":
        if previous == head:
            run_git(repo.worktree_root, "update-ref", "-d", authority_ref, head)
            ref_updated = True
            current = None
    else:
        raise OrchestrateError("unsupported acceptance outcome", "cli_usage")

    warnings: tuple[str, ...] = ()
    if regressed:
        warnings = (
            f"{verifier} acceptance authority regressed from {previous} to {head}",
        )
    telemetry_warnings = record_event(
        task,
        "acceptance-result",
        outcome,
        subject_sha=head,
        verifier=verifier,
        previous_sha=previous,
        current_sha=current,
        ref_updated=ref_updated,
        regressed=regressed,
    )
    return CommandResult(
        True,
        {
            "verifier": verifier,
            "subject_sha": head,
            "previous_sha": previous,
            "current_sha": current,
            "ref_updated": ref_updated,
            "regressed": regressed,
        },
        (*warnings, *telemetry_warnings),
    )


def _persistence_worktree(
    repo: RepositoryContext, branch_ref: str
) -> tuple[Path, str]:
    tip = _ref(repo, branch_ref)
    if tip is None:
        raise OrchestrateError(
            "persistence branch is unavailable", "persistence_unavailable"
        )
    paths = [
        Path(str(record["worktree"]))
        for record in worktree_records(repo.worktree_root)
        if record.get("branch") == branch_ref
        and isinstance(record.get("worktree"), str)
    ]
    if len(paths) != 1 or not paths[0].is_dir():
        raise OrchestrateError(
            "persistence branch must have exactly one checkout",
            "persistence_unavailable",
        )
    path = paths[0]
    if run_git(path, "rev-parse", "HEAD").stdout.strip() != tip:
        raise OrchestrateError(
            "persistence checkout is not at its branch tip",
            "persistence_unavailable",
        )
    return path, tip


def _index_entries(path: Path, commit: str | None = None) -> list[tuple[str, ...]]:
    if commit is None:
        raw = run_git(path, "ls-files", "--stage", "-z").stdout
        entries: list[tuple[str, ...]] = []
        for item in raw.split("\0"):
            if not item:
                continue
            metadata, separator, name = item.partition("\t")
            fields = metadata.split()
            if not separator or len(fields) != 3:
                raise OrchestrateError("cannot inspect persistence index", "git_error")
            mode, object_id, stage = fields
            entries.append((mode, object_id, stage, name))
        return entries

    raw = run_git(path, "ls-tree", "-r", "-z", commit).stdout
    entries = []
    for item in raw.split("\0"):
        if not item:
            continue
        metadata, separator, name = item.partition("\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise OrchestrateError("cannot inspect persistence tree", "git_error")
        mode, _kind, object_id = fields
        entries.append((mode, object_id, "0", name))
    return entries


def _index_is_head(path: Path, head: str) -> bool:
    return _index_entries(path) == _index_entries(path, head)


def _nul_paths(path: Path, *args: str) -> set[str]:
    raw = run_git(path, *args).stdout
    return {value for value in raw.split("\0") if value}


def _dirty_paths(path: Path) -> set[str]:
    paths = _nul_paths(path, "diff", "--name-only", "--no-renames", "-z")
    paths.update(
        _nul_paths(path, "ls-files", "--others", "--exclude-standard", "-z")
    )
    paths.update(
        _nul_paths(
            path,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
        )
    )
    return paths


def _paths_collide(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _landed_ref_namespace_is_available(
    repo: RepositoryContext, landed_ref: str
) -> bool:
    refs = run_git(
        repo.worktree_root, "for-each-ref", "--format=%(refname)"
    ).stdout.splitlines()
    return not any(
        ref != landed_ref
        and (ref.startswith(f"{landed_ref}/") or landed_ref.startswith(f"{ref}/"))
        for ref in refs
    )


def _filesystem_byte_digest(candidate: Path) -> str:
    digest = hashlib.sha256()
    if candidate.is_symlink():
        digest.update(b"symlink\0")
        digest.update(os.fsencode(os.readlink(candidate)))
    elif candidate.is_dir():
        digest.update(b"directory\0")
        for child in sorted(candidate.iterdir(), key=lambda item: os.fsencode(item.name)):
            digest.update(os.fsencode(child.name))
            digest.update(b"\0")
            digest.update(_filesystem_byte_digest(child).encode("ascii"))
            digest.update(b"\0")
    else:
        digest.update(b"file\0")
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _dirt_byte_digests(path: Path, dirt: set[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative in sorted(dirt):
        try:
            digests[relative] = _filesystem_byte_digest(path / relative)
        except OSError as exc:
            raise OrchestrateError(
                f"cannot snapshot persistence dirt: {relative}: {exc}",
                "git_error",
            ) from exc
    return digests


def _verify_dirt_byte_digests(
    path: Path, expected: dict[str, str], *, phase: str
) -> None:
    if _dirt_byte_digests(path, set(expected)) != expected:
        raise OrchestrateError(
            f"persistence dirt changed during landing {phase}", "git_error"
        )


def _restore_persistence(
    path: Path,
    transition_tip: str,
    tip: str,
    dirt_digests: dict[str, str],
) -> None:
    current = run_git(path, "rev-parse", "HEAD", check=False).stdout.strip()
    source = current if current and current != tip else transition_tip
    run_git(path, "read-tree", "-u", "-m", source, tip)
    if current and current != tip:
        branch = run_git(path, "symbolic-ref", "-q", "HEAD").stdout.strip()
        run_git(path, "update-ref", branch, tip, current)
    _verify_dirt_byte_digests(path, dirt_digests, phase="rollback")


def integration_land(
    repo: RepositoryContext,
    task_id: str,
    persist: str,
    message: str | None,
) -> CommandResult:
    task = _task(repo, task_id)
    accepted = _authority_ref(repo, task.accepted_ref, label="accepted authority slot")
    landed = _authority_ref(repo, task.landed_ref, label="landed authority slot")
    if accepted is None:
        raise OrchestrateError("no accepted snapshot", "no_accepted_snapshot")

    branch_ref = f"refs/heads/{persist}"
    persist_path, persist_tip = _persistence_worktree(repo, branch_ref)
    if not _index_is_head(persist_path, persist_tip):
        raise OrchestrateError(
            "persistence index is dirty", "persistence_index_dirty"
        )

    if landed == accepted:
        raise OrchestrateError(
            "accepted snapshot is already landed", "duplicate_landing"
        )
    if not _landed_ref_namespace_is_available(repo, task.landed_ref):
        raise OrchestrateError("landed ref namespace is blocked", "git_error")

    accepted_tree = _tree(repo, accepted)
    persist_tree = _tree(repo, persist_tip)
    if accepted_tree == persist_tree:
        raise OrchestrateError("accepted tree has no changes", "nothing_to_land")

    fresh = _is_ancestor(repo, persist_tip, accepted)
    if not fresh and landed is not None:
        fresh = persist_tree == _tree(repo, landed)
    if not fresh:
        raise OrchestrateError("persistence branch is stale", "stale_persistence")

    transition_paths = set(
        changed_paths(repo.worktree_root, persist_tip, accepted)
    )
    dirt = _dirty_paths(persist_path)
    if any(
        _paths_collide(changed, dirty)
        for changed in transition_paths
        for dirty in dirt
    ):
        raise OrchestrateError(
            "persistence dirt collides with accepted tree", "persistence_collision"
        )

    integration = _ref(repo, task.integration_branch)
    if integration is None:
        raise OrchestrateError("task integration is missing", "task_state_invalid")
    warnings: tuple[str, ...] = ()
    if accepted != integration:
        warnings = ("accepted snapshot lags current integration",)

    proof = run_git(
        persist_path,
        "read-tree",
        "--dry-run",
        "-u",
        "-m",
        persist_tip,
        accepted,
        check=False,
    )
    if proof.returncode or not _index_is_head(persist_path, persist_tip):
        raise OrchestrateError(
            "persistence dirt collides with accepted tree", "persistence_collision"
        )
    dirt_digests = _dirt_byte_digests(persist_path, dirt)

    applied = run_git(
        persist_path,
        "read-tree",
        "-u",
        "-m",
        persist_tip,
        accepted,
        check=False,
    )
    if applied.returncode:
        if not _index_is_head(persist_path, persist_tip):
            _restore_persistence(
                persist_path, accepted, persist_tip, dirt_digests
            )
        else:
            _verify_dirt_byte_digests(
                persist_path, dirt_digests, phase="failed transition"
            )
        raise OrchestrateError(
            "persistence dirt collides with accepted tree", "persistence_collision"
        )
    try:
        _verify_dirt_byte_digests(
            persist_path, dirt_digests, phase="successful transition"
        )
    except OrchestrateError:
        _restore_persistence(persist_path, accepted, persist_tip, dirt_digests)
        raise

    subject = message or f"Land {task.task_id}"
    commit_message = (
        f"{subject}\n\nTask: {task.task_id}\nLanded: {accepted}"
    )
    committed = run_git(
        persist_path, "commit", "-m", commit_message, check=False
    )
    if committed.returncode:
        _restore_persistence(persist_path, accepted, persist_tip, dirt_digests)
        detail = committed.stderr.strip() or committed.stdout.strip()
        raise OrchestrateError(f"landing commit failed: {detail}", "git_error")

    landed_tree = run_git(persist_path, "rev-parse", "HEAD^{tree}").stdout.strip()
    if landed_tree != accepted_tree:
        _restore_persistence(persist_path, accepted, persist_tip, dirt_digests)
        raise OrchestrateError(
            "landed tree differs from accepted tree", "git_error"
        )

    updated = run_git(
        repo.worktree_root,
        "update-ref",
        task.landed_ref,
        accepted,
        *( (landed,) if landed is not None else () ),
        check=False,
    )
    if updated.returncode:
        _restore_persistence(persist_path, accepted, persist_tip, dirt_digests)
        detail = updated.stderr.strip() or updated.stdout.strip()
        raise OrchestrateError(f"cannot record landed snapshot: {detail}", "git_error")

    _verify_dirt_byte_digests(persist_path, dirt_digests, phase="success")
    event_warnings = record_event(
        task,
        "integration-land",
        "success",
        subject_sha=accepted,
        persist=persist,
    )
    return CommandResult(True, {}, (*warnings, *event_warnings))
