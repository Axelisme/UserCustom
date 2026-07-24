"""Git-backed implementation of the v119 core command seams."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .git_ops import exact_commit, managed_worktree_root, run_git, worktree_records
from .primitives import OrchestrateError, require_identifier


def _worktree_identity(args: argparse.Namespace, *, role: str | None = None) -> tuple[str, str, str, Path, str]:
    task = require_identifier(str(args.task_id), label="task id")
    wave = require_identifier(str(args.wave_id), label="wave id")
    selected_role = str(role if role is not None else args.role)
    if selected_role not in {"oracle", "implementation"}:
        raise OrchestrateError("role must be oracle or implementation")
    root = Path(args.root).resolve()
    branch = f"wave/{task}/{wave}/{selected_role}"
    path = managed_worktree_root(root) / f"{task}-{wave}-{selected_role}"
    return task, wave, selected_role, path, branch


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
            f"implementation worktree must be attached to exact derived branch {expected_branch}; "
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


def command_worktree_create(args: argparse.Namespace) -> dict[str, Any]:
    _, _, role, path, branch = _worktree_identity(args)
    root = Path(args.root).resolve()
    try:
        base = exact_commit(root, str(args.base), label="base")
    except OrchestrateError as exc:
        raise OrchestrateError(f"invalid base: {exc}") from exc
    if _branch_exists(root, branch) or os.path.lexists(path):
        raise OrchestrateError(f"derived worktree path or branch already exists: {path} / {branch}")
    path.parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "worktree", "add", "-b", branch, str(path), base)
    evidence = _status(root, path, branch)
    return {"ok": True, "operation": "worktree-create", "task_id": args.task_id, "wave_id": args.wave_id, "role": role, "branch": branch, "worktree": str(path), "base": base, "head": evidence["head"], "tree": evidence["tree"], "clean": evidence["clean"]}


def command_worktree_status(args: argparse.Namespace) -> dict[str, Any]:
    _, _, _, path, branch = _worktree_identity(args)
    return _status(Path(args.root).resolve(), path, branch)


def command_worktree_remove(args: argparse.Namespace) -> dict[str, Any]:
    _, _, role, path, branch = _worktree_identity(args)
    root = Path(args.root).resolve()
    state = _status(root, path, branch)
    if not state["exists"]:
        raise OrchestrateError(f"managed {role} worktree does not exist: {path}")
    if not state["clean"]:
        raise OrchestrateError(f"cannot remove worktree because it is not clean: {path}")
    run_git(root, "worktree", "remove", str(path))
    return {"ok": True, "operation": "worktree-remove", "task_id": args.task_id, "wave_id": args.wave_id, "role": role, "worktree": str(path), "branch": branch, "removed": True}


def _trailers(body: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in body.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Wave", "Slice", "Role"}:
            values[key] = value.strip()
    return values


def _commit_body(root: Path, sha: str) -> str:
    return run_git(root, "show", "-s", "--format=%B", sha).stdout


def command_contract_merge(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    task, wave_id, _, path, branch = _worktree_identity(args, role="implementation")
    contract = exact_commit(root, str(args.contract_sha), label="contract SHA")
    oracle_branch = f"wave/{task}/{wave_id}/oracle"
    oracle_ref = f"refs/heads/{oracle_branch}"
    if run_git(root, "merge-base", "--is-ancestor", contract, oracle_ref, check=False).returncode != 0:
        raise OrchestrateError(f"Contract SHA is not reachable from Oracle ref: {oracle_branch}")
    state = _status(root, path, branch, require_expected_branch=True)
    if not state["exists"]:
        raise OrchestrateError(f"managed implementation worktree does not exist: {path}")
    if not state["clean"]:
        raise OrchestrateError(f"implementation worktree must be clean: {path}")
    trailers = _trailers(_commit_body(root, contract))
    wave = trailers.get("Wave", "")
    slice_id = trailers.get("Slice", "")
    if wave != str(args.wave_id) or not slice_id or trailers.get("Role") != "oracle":
        raise OrchestrateError("contract SHA must carry matching Wave, non-empty Slice, and Role: oracle trailers")
    merged = run_git(path, "merge", "--no-ff", "--no-commit", contract, check=False)
    if merged.returncode:
        detail = merged.stderr.strip() or merged.stdout.strip() or "contract merge conflict"
        raise OrchestrateError(f"git contract merge failed: {detail}")
    message = f"Merge Contract {contract}\n\nWave: {wave}\nSlice: {slice_id}\nRole: merge"
    committed = run_git(path, "commit", "-m", message, check=False)
    if committed.returncode:
        detail = committed.stderr.strip() or committed.stdout.strip()
        raise OrchestrateError(f"git commit failed while recording contract merge: {detail}")
    merge_sha = run_git(path, "rev-parse", "HEAD").stdout.strip()
    return {"ok": True, "operation": "contract-merge", "task_id": args.task_id, "wave_id": args.wave_id, "contract_sha": contract, "merge_sha": merge_sha, "branch": branch, "worktree": str(path), "slice": slice_id}


def _commit_info(root: Path, sha: str) -> dict[str, Any]:
    fields = run_git(root, "show", "-s", "--format=%H%x00%ct%x00%s%x00%B", sha).stdout.split("\x00", 3)
    body = fields[3] if len(fields) > 3 else ""
    trailers = _trailers(body)
    return {"sha": fields[0], "timestamp": int(fields[1]), "wave": trailers.get("Wave", ""), "slice": trailers.get("Slice", ""), "role": trailers.get("Role", ""), "subject": fields[2].strip() if len(fields) > 2 else ""}


def _range_numstat(
    root: Path, start: str | None, end: str
) -> list[tuple[str, int, int]]:
    """Return the net numstat for one topology range.

    Ready trailers identify boundaries, not the only commits to count.  Using a
    range diff includes untrailed work between those boundaries and, unlike
    summing each commit, counts a checkpoint and its eventual ready commit only
    once when the ready endpoint exists.
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
            and info["role"] in {"oracle", "merge", "implementation", "implementation-checkpoint"}
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
            if info["role"] == "implementation-checkpoint":
                entry.setdefault("_checkpoints", []).append(info)

    # Every Oracle range is diffed once in global readiness order.  The cached
    # result is partitioned by endpoint Slice and also supplies Wave totals.
    contract_ranges: list[list[tuple[str, int, int]]] = []
    previous_oracle_sha = base
    for _position, oracle in oracle_records:
        stats = _range_numstat(root, previous_oracle_sha, oracle["sha"])
        contract_ranges.append(stats)
        slices[oracle["slice"]].setdefault("_contract_stats", []).extend(stats)
        previous_oracle_sha = oracle["sha"]

    # Merge windows are traversed with one monotone endpoint cursor.  A ready
    # Implementation wins over checkpoints in its matching merge Slice; a
    # checkpoint is only a statistics endpoint and does not become a ready
    # attempt endpoint.
    endpoint_cursor = 0
    merge_ready_endpoints: dict[int, dict[str, Any]] = {}
    merge_ranges: dict[int, list[tuple[str, int, int]]] = {}
    for merge_index, (merge_position, merge) in enumerate(merge_records):
        next_merge_position = (
            merge_records[merge_index + 1][0]
            if merge_index + 1 < len(merge_records)
            else len(infos)
        )
        latest_ready: dict[str, Any] | None = None
        latest_checkpoint: dict[str, Any] | None = None
        while endpoint_cursor < len(endpoint_records):
            endpoint_position, endpoint = endpoint_records[endpoint_cursor]
            if endpoint_position >= next_merge_position:
                break
            endpoint_cursor += 1
            if endpoint_position <= merge_position or endpoint["slice"] != merge["slice"]:
                continue
            if endpoint["role"] == "implementation":
                latest_ready = endpoint
            else:
                latest_checkpoint = endpoint
        endpoint = latest_ready or latest_checkpoint
        if endpoint is None:
            continue
        if latest_ready is not None:
            merge_ready_endpoints[merge_index] = latest_ready
        merge_ranges[merge_index] = _range_numstat(root, merge["sha"], endpoint["sha"])
        slices[merge["slice"]].setdefault("_implementation_stats", []).extend(
            merge_ranges[merge_index]
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
        checkpoints = entry.pop("_checkpoints", [])
        if checkpoints:
            entry["checkpoints"] = [checkpoint["sha"] for checkpoint in checkpoints]

    wave_contract_stats = [stat for stats in contract_ranges for stat in stats]
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
            "contract_numstat": {
                "files": len(wave_contract_stats),
                "insertions": sum(item[1] for item in wave_contract_stats),
                "deletions": sum(item[2] for item in wave_contract_stats),
            },
            "implementation_numstat": wave_impl_stats,
        },
    }
