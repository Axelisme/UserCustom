from __future__ import annotations

import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError, require_identifier

HEX_OBJECT_ID_PATTERN = re.compile(r"^[0-9a-fA-F]+$")


def run_git(
    root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise OrchestrateError(f"git {' '.join(args)} failed: {detail}")
    return completed


def object_id_length(root: Path) -> int:
    object_format = run_git(root, "rev-parse", "--show-object-format").stdout.strip()
    if object_format == "sha1":
        return 40
    if object_format == "sha256":
        return 64
    raise OrchestrateError(f"unsupported git object format: {object_format!r}")


def exact_commit(root: Path, value: str, *, label: str) -> str:
    expected_length = object_id_length(root)
    if (
        len(value) != expected_length
        or HEX_OBJECT_ID_PATTERN.fullmatch(value) is None
    ):
        probe = run_git(
            root, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}", check=False
        )
        resolved = probe.stdout.strip()
        hint = (
            f"; resolved full SHA: {resolved} — retry with this value"
            if probe.returncode == 0 and resolved
            else ""
        )
        raise OrchestrateError(
            f"{label} must be a full {expected_length}-character hexadecimal commit SHA"
            + hint
        )
    resolved = run_git(
        root, "rev-parse", "--verify", f"{value}^{{commit}}"
    ).stdout.strip()
    if resolved.lower() != value.lower():
        raise OrchestrateError(f"{label} does not identify one exact commit: {value}")
    return resolved


def changed_paths_since_fork(root: Path, base: str, head: str) -> list[str]:
    fork = run_git(root, "merge-base", base, head).stdout.strip()
    output = run_git(root, "diff", "--name-only", fork, head).stdout
    return [line.strip() for line in output.splitlines() if line.strip()]


def common_repo_root(root: Path) -> Path:
    common = Path(
        run_git(
            root, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).stdout.strip()
    )
    return common.parent if common.name == ".git" else common


def managed_worktree_root(root: Path) -> Path:
    return common_repo_root(root) / ".agent_state" / "worktrees"


def require_managed_worktree(root: Path, target: Path, *, kind: str) -> Path:
    managed = managed_worktree_root(root).resolve()
    resolved = target.resolve()
    try:
        relative = resolved.relative_to(managed)
    except ValueError as exc:
        raise OrchestrateError(f"{kind} worktree must be below {managed}") from exc
    if len(relative.parts) != 1:
        raise OrchestrateError(f"{kind} worktree must be a direct child of {managed}")
    return resolved


def require_task_lane_refs(task_ref: str, lane_ref: str) -> None:
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    if not lane_ref.startswith("agent/") or lane_ref.count("/") != 2:
        raise OrchestrateError(f"lane ref must use agent/<task>/<lane>: {lane_ref!r}")
    task_id = task_ref.split("/", 1)[1]
    _, lane_task, lane_name = lane_ref.split("/", 2)
    require_identifier(task_id, label="task ref id")
    require_identifier(lane_task, label="lane task id")
    require_identifier(lane_name, label="lane name")
    if task_id != lane_task:
        raise OrchestrateError("task and lane refs name different tasks")


def worktree_records(root: Path) -> list[dict[str, Any]]:
    output = run_git(root, "worktree", "list", "--porcelain").stdout
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value if value else True
    return records


def worktree_evidence(path: Path, *, started: float) -> dict[str, Any]:
    head = run_git(path, "rev-parse", "HEAD").stdout.strip()
    tree = run_git(path, "rev-parse", "HEAD^{tree}").stdout.strip()
    branch = run_git(path, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    status = run_git(path, "status", "--porcelain").stdout
    return {
        "path": str(path.resolve()),
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "head": head,
        "tree": tree,
        "clean": not bool(status.strip()),
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return (
        run_git(
            root, "merge-base", "--is-ancestor", ancestor, descendant, check=False
        ).returncode
        == 0
    )


def merge_tree_probe(root: Path, first: str, second: str) -> dict[str, Any]:
    """Run a read-only two-parent merge-tree probe with explicit tree evidence."""
    probe = run_git(
        root, "merge-tree", "--write-tree", first, second, check=False
    )
    if probe.returncode != 0:
        detail = probe.stderr.strip() or probe.stdout.strip()
        return {
            "clean": False,
            "tree": None,
            "first": first,
            "second": second,
            "error": detail or "merge-tree reported a conflict",
        }
    tree = next((line.strip() for line in probe.stdout.splitlines() if line.strip()), None)
    object_length = object_id_length(root)
    if (
        tree is None
        or len(tree) != object_length
        or HEX_OBJECT_ID_PATTERN.fullmatch(tree) is None
    ):
        return {
            "clean": False,
            "tree": None,
            "first": first,
            "second": second,
            "error": "merge-tree returned no valid tree",
        }
    second_tree = run_git(root, "rev-parse", f"{second}^{{tree}}").stdout.strip()
    first_tree = run_git(root, "rev-parse", f"{first}^{{tree}}").stdout.strip()
    return {
        "clean": True,
        "tree": tree,
        "first": first,
        "second": second,
        "first_tree": first_tree,
        "second_tree": second_tree,
        "tree_identity_with_first": tree == first_tree,
        "tree_identity_with_second": tree == second_tree,
    }


def absorption_probe(root: Path, source: str, target: str) -> str | None:
    if is_ancestor(root, source, target):
        return "ancestor"
    probe = merge_tree_probe(root, source, target)
    if probe.get("clean") and probe.get("tree_identity_with_second"):
        return "tree-identity"
    return None


def lane_absorption(root: Path, lane_sha: str, task_sha: str) -> str | None:
    return absorption_probe(root, lane_sha, task_sha)


def worktree_metadata_writability_preflight(root: Path) -> None:
    # A sandbox that can delete the directory but not .git/worktrees leaves
    # half-removed state; refuse before any mutation.
    metadata_dir = (
        root / run_git(root, "rev-parse", "--git-common-dir").stdout.strip()
    ).resolve() / "worktrees"
    if metadata_dir.exists() and not os.access(metadata_dir, os.W_OK):
        raise OrchestrateError(
            f"worktree metadata is not writable: {metadata_dir}; grant write"
            " access before cleanup — nothing was removed"
        )
