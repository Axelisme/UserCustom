from __future__ import annotations

import argparse
import fcntl
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import ID_PATTERN, OrchestrateError, read_json_object, require_json_fields, sha256_bytes, validate_json_enum
from .git_ops import exact_commit, run_git

LANDING_VERSION = 1


LANDING_POLICIES = (
    "validate-only",
    "land-with-confirmation",
    "commit-authorized",
    "publish-authorized",
)


LANDING_REQUIRED = ("landing_version", "task_id", "policy", "target_ref")


LANDING_FIELDS = set(LANDING_REQUIRED) | {"details"}


def validate_landing_declaration(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require_json_fields(payload, LANDING_REQUIRED, errors)
    unexpected = sorted(payload.keys() - LANDING_FIELDS)
    if unexpected:
        errors.append(f"unexpected fields: {', '.join(unexpected)}")
    if payload.get("landing_version") != LANDING_VERSION:
        errors.append(f"landing_version must be {LANDING_VERSION}")
    task_id = payload.get("task_id")
    if task_id is not None and (
        not isinstance(task_id, str) or not ID_PATTERN.fullmatch(task_id)
    ):
        errors.append("task_id must be a stable identifier")
    validate_json_enum(payload, "policy", LANDING_POLICIES, errors)
    target = payload.get("target_ref")
    if target is not None and (
        not isinstance(target, str)
        or not target.strip()
        or target.startswith(("task/", "agent/"))
    ):
        errors.append(
            "target_ref must name a persistence branch, never task/ or agent/"
        )
    details = payload.get("details")
    if details is not None and not isinstance(details, dict):
        errors.append("details must be an object when supplied")
    return errors


def read_landing_declaration(path: str) -> tuple[dict[str, Any], bytes]:
    payload, data = read_json_object(path, label="landing declaration")
    errors = validate_landing_declaration(payload)
    if errors:
        raise OrchestrateError("invalid landing declaration: " + "; ".join(errors))
    return payload, data


def landing_task_id(task_ref: str, declaration: dict[str, Any]) -> str:
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    task_id = task_ref.split("/", 1)[1]
    if task_id != declaration["task_id"]:
        raise OrchestrateError(
            f"declaration task_id is {declaration['task_id']!r},"
            f" but --task-ref names {task_id!r}"
        )
    return task_id


def landing_checkout_dirt(root: Path) -> tuple[list[str], list[str]]:
    """Split porcelain status into staged paths and user-owned dirty paths."""
    staged: list[str] = []
    dirty: list[str] = []
    for line in run_git(root, "status", "--porcelain").stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(" -> ")[-1].strip()
        if line[0] not in " ?":
            staged.append(path)
        else:
            dirty.append(path)
    return staged, dirty


_HELD_LOCKS: list[Any] = []


def acquire_landing_lock(root: Path) -> None:
    """Serialize the landing critical section within this repo, non-blocking.

    The handle is held until process exit so the flock outlives this frame.
    """
    git_common_dir = Path(
        run_git(
            root, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).stdout.strip()
    )
    lock_path = git_common_dir / "orchestrate-land.lock"
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise OrchestrateError(
            f"another landing holds the lock: {lock_path}; wait for it to finish"
        ) from exc
    _HELD_LOCKS.append(handle)


def rollback_landing_publication(
    root: Path,
    *,
    target_full_ref: str,
    target_sha: str,
    landed_sha: str,
    reason: str,
) -> None:
    rollback = run_git(
        root, "update-ref", target_full_ref, target_sha, landed_sha, check=False
    )
    if rollback.returncode != 0:
        raise OrchestrateError(
            "durability uncertain: landing publication and compensating ref rollback"
            f" both failed ({reason}); reconcile before retry"
        )
    checkout = run_git(root, "reset", "--hard", target_sha, check=False)
    head = run_git(root, "rev-parse", "HEAD", check=False).stdout.strip()
    staged, dirty = landing_checkout_dirt(root)
    if checkout.returncode != 0 or head != target_sha or staged or dirty:
        raise OrchestrateError(
            "landing publication was rolled back but checkout compensation is"
            f" incomplete ({reason}); inspect the target checkout before retry"
        )
    raise OrchestrateError(
        f"landing publication was rolled back after {reason}; retry from the clean target"
    )


def command_land_status(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    declaration, decl_data = read_landing_declaration(args.declaration)
    task_id = landing_task_id(args.task_ref, declaration)
    policy = declaration["policy"]
    target_ref = declaration["target_ref"]
    task_sha = run_git(root, "rev-parse", f"{args.task_ref}^{{commit}}").stdout.strip()
    target_sha = run_git(root, "rev-parse", f"{target_ref}^{{commit}}").stdout.strip()
    branch = run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    on_target = branch.returncode == 0 and branch.stdout.strip() == target_ref
    staged, dirty = landing_checkout_dirt(root)
    changed = [
        line.strip()
        for line in run_git(
            root, "diff", "--name-only", target_sha, task_sha
        ).stdout.splitlines()
        if line.strip()
    ]
    dirty_overlap = sorted(set(dirty) & set(changed))
    landed = (
        run_git(root, "diff", "--quiet", task_sha, target_sha, check=False).returncode
        == 0
    )
    based = (
        run_git(
            root, "merge-base", "--is-ancestor", target_sha, task_sha, check=False
        ).returncode
        == 0
    )
    lanes = [
        line.strip()
        for line in run_git(
            root,
            "for-each-ref",
            "--format=%(refname:short)",
            f"refs/heads/agent/{task_id}/",
        ).stdout.splitlines()
        if line.strip()
    ]
    authority_state = (
        "forbidden"
        if policy == "validate-only"
        else "requires-user-confirmation"
        if policy == "land-with-confirmation"
        else "authorized"
    )
    steps = {
        "landing_authority": {"policy": policy, "state": authority_state},
        "landing_lock": {
            "state": "built-in",
            "hint": "land finish takes the landing lock itself",
        },
        "squash_landing": {
            "state": "done" if landed else "pending",
            "based_on_target": based,
            "on_target_checkout": on_target,
            "staged_paths": staged,
            "dirty_overlap": dirty_overlap,
        },
        "tree_identity": {"state": "proved" if landed else "pending"},
        "lane_cleanup": {
            "state": "done" if not lanes else "pending",
            "remaining_lanes": lanes,
        },
    }
    if policy == "validate-only":
        next_step = (
            "policy is validate-only: report the validated task branch; landing"
            " needs a new user-authorized declaration"
        )
    elif landed and lanes:
        next_step = (
            "run reconcile, cleanup each safe-to-remove exact --worktree target,"
            " then delete the task branch"
        )
    elif landed:
        next_step = "delete the task branch (tree identity already holds)"
    elif not based:
        next_step = "rebase the task onto the target tip, rerun the gate"
    else:
        next_step = "land finish"
    return {
        "ok": True,
        "operation": "land-status",
        "read_only": True,
        "task_ref": args.task_ref,
        "target_ref": target_ref,
        "policy": policy,
        "task_sha": task_sha,
        "target_sha": target_sha,
        "declaration_sha256": sha256_bytes(decl_data),
        "steps": steps,
        "next": next_step,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_land_finish(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    declaration, decl_data = read_landing_declaration(args.declaration)
    task_id = landing_task_id(args.task_ref, declaration)
    policy = declaration["policy"]
    if policy == "validate-only":
        raise OrchestrateError(
            "declared landing policy is validate-only: landing is out of contract;"
            " get user authority and write a new declaration first"
        )
    if policy == "land-with-confirmation" and not args.confirmed:
        raise OrchestrateError(
            "policy land-with-confirmation requires --confirmed after an explicit"
            " user confirmation for this landing"
        )
    target_ref = declaration["target_ref"]
    expected = exact_commit(root, args.task_sha, label="task SHA")
    task_head = run_git(root, "rev-parse", f"{args.task_ref}^{{commit}}").stdout.strip()
    if task_head != expected:
        raise OrchestrateError(f"task head drifted: {task_head} != {expected}")
    evidence = {
        "operation": "land-finish",
        "task_ref": args.task_ref,
        "target_ref": target_ref,
        "policy": policy,
        "task_sha": expected,
        "declaration_sha256": sha256_bytes(decl_data),
    }
    target_sha = run_git(root, "rev-parse", f"{target_ref}^{{commit}}").stdout.strip()
    if (
        run_git(root, "diff", "--quiet", expected, target_sha, check=False).returncode
        == 0
    ):
        branch = run_git(
            root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False
        )
        if branch.returncode != 0 or branch.stdout.strip() != target_ref:
            raise OrchestrateError(
                "landing commit exists but target checkout cannot be verified;"
                " run land status from the target checkout"
            )
        staged, dirty = landing_checkout_dirt(root)
        if staged or dirty:
            raise OrchestrateError(
                "landing commit exists but checkout synchronization is incomplete: "
                + ", ".join(sorted(set(staged) | set(dirty))[:20])
            )
        if run_git(root, "rev-parse", "HEAD").stdout.strip() != target_sha:
            raise OrchestrateError(
                "landing commit exists but target checkout HEAD is not synchronized"
            )
        return {
            "ok": True,
            "recovered": "already-landed",
            "landed_sha": target_sha,
            "tree_identity": True,
            **evidence,
            "observed_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    git_dir = Path(run_git(root, "rev-parse", "--absolute-git-dir").stdout.strip())
    if (git_dir / "MERGE_HEAD").exists():
        raise OrchestrateError(
            "unfinished merge in progress: resolve it or run `git merge --abort`,"
            " then rerun land finish"
        )
    current_branch = run_git(root, "symbolic-ref", "--short", "HEAD").stdout.strip()
    if current_branch != target_ref:
        raise OrchestrateError(
            f"landing checkout is {current_branch}, expected {target_ref}"
        )
    staged, dirty = landing_checkout_dirt(root)
    if staged or dirty:
        paths = sorted(set(staged) | set(dirty))
        raise OrchestrateError(
            "landing checkout must be fully clean before atomic publication: "
            + ", ".join(paths[:20])
        )
    acquire_landing_lock(root)
    task_head = run_git(root, "rev-parse", f"{args.task_ref}^{{commit}}").stdout.strip()
    if task_head != expected:
        raise OrchestrateError(
            f"task head drifted while acquiring landing lock: {task_head} != {expected}"
        )
    target_sha = run_git(root, "rev-parse", f"{target_ref}^{{commit}}").stdout.strip()
    if (
        run_git(
            root, "merge-base", "--is-ancestor", target_sha, expected, check=False
        ).returncode
        != 0
    ):
        raise OrchestrateError(
            "task head is not based on the current target tip: rebase off-lock,"
            " then rerun land finish"
        )
    message = args.message or f"land {task_id}: squash of {expected[:12]}"
    candidate_tree = run_git(root, "rev-parse", f"{expected}^{{tree}}").stdout.strip()
    landed = run_git(
        root,
        "commit-tree",
        candidate_tree,
        "-p",
        target_sha,
        "-m",
        message,
    ).stdout.strip()
    if run_git(root, "diff", "--quiet", expected, landed, check=False).returncode != 0:
        raise OrchestrateError(
            f"candidate tree identity proof failed before publication: {expected} vs {landed}"
        )
    target_full_ref = (
        target_ref if target_ref.startswith("refs/") else f"refs/heads/{target_ref}"
    )
    run_git(root, "update-ref", target_full_ref, landed, target_sha)
    try:
        run_git(root, "reset", "--hard", landed)
    except OrchestrateError:
        rollback_landing_publication(
            root,
            target_full_ref=target_full_ref,
            target_sha=target_sha,
            landed_sha=landed,
            reason="checkout synchronization failed",
        )
    synced_head = run_git(root, "rev-parse", "HEAD").stdout.strip()
    synced_staged, synced_dirty = landing_checkout_dirt(root)
    if synced_head != landed or synced_staged or synced_dirty:
        rollback_landing_publication(
            root,
            target_full_ref=target_full_ref,
            target_sha=target_sha,
            landed_sha=landed,
            reason="checkout verification failed",
        )
    next_steps = [
        "run reconcile, then cleanup each safe-to-remove exact --worktree target",
        f"git branch -D {args.task_ref} (authorized by this tree identity proof)",
    ]
    if policy == "publish-authorized":
        next_steps.append(f"git push <remote> {target_ref}")
    return {
        "ok": True,
        "landed_sha": landed,
        "tree_identity": True,
        "message": message,
        "next": next_steps,
        **evidence,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
