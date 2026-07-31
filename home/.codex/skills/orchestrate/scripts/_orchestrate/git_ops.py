from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError

HEX_OBJECT_ID_PATTERN = re.compile(r"^[0-9a-fA-F]+$")


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=root, check=False, text=True, capture_output=True)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise OrchestrateError(f"git {' '.join(args)} failed: {detail}", "git_error")
    return result


def object_id_length(root: Path) -> int:
    value = run_git(root, "rev-parse", "--show-object-format").stdout.strip()
    if value == "sha1":
        return 40
    if value == "sha256":
        return 64
    raise OrchestrateError(f"unsupported git object format: {value!r}", "git_error")


def exact_commit(root: Path, value: str, *, label: str) -> str:
    length = object_id_length(root)
    if len(value) != length or HEX_OBJECT_ID_PATTERN.fullmatch(value) is None:
        raise OrchestrateError(f"{label} must be a full {length}-character hexadecimal commit SHA", "git_error")
    resolved = run_git(root, "rev-parse", "--verify", f"{value}^{{commit}}", check=False)
    if resolved.returncode:
        raise OrchestrateError(f"{label} does not identify one exact commit: {value}", "git_error")
    return resolved.stdout.strip()


def common_repo_root(root: Path) -> Path:
    common = Path(run_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    return common.parent if common.name == ".git" else common


def managed_worktree_root(root: Path) -> Path:
    return common_repo_root(root) / ".agent_state" / "worktrees"


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


def worktree_for(root: Path, path: Path) -> dict[str, Any] | None:
    wanted = Path(os.path.abspath(path))
    for record in worktree_records(root):
        raw = record.get("worktree")
        if isinstance(raw, str) and Path(os.path.abspath(raw)) == wanted:
            return record
    return None


def branch_for(record: dict[str, Any]) -> str | None:
    value = record.get("branch")
    return value.removeprefix("refs/heads/") if isinstance(value, str) else None


def ref_exists(root: Path, ref: str) -> bool:
    """Return whether one exact ref exists, even if its target is dangling."""
    return (
        run_git(root, "show-ref", "--verify", "--quiet", ref, check=False).returncode
        == 0
    )


def direct_commit_ref(root: Path, ref: str, *, label: str) -> str | None:
    """Resolve an exact direct commit ref without dereferencing symbolic refs."""
    symbolic = run_git(root, "symbolic-ref", "--quiet", ref, check=False)
    if symbolic.returncode != 1:
        raise OrchestrateError(
            f"{label} is not an exact direct commit ref", "task_state_invalid"
        )

    probe = run_git(
        root,
        "for-each-ref",
        "--format=%(refname)%09%(symref)%09%(objectname)%09%(objecttype)",
        "--",
        ref,
        check=False,
    )
    if probe.returncode:
        raise OrchestrateError(f"cannot inspect {label}", "task_state_invalid")

    exact = [line.split("\t") for line in probe.stdout.splitlines() if line]
    exact = [fields for fields in exact if fields and fields[0] == ref]
    if not exact:
        return None
    if len(exact) != 1 or len(exact[0]) != 4:
        raise OrchestrateError(
            f"{label} is not an exact direct commit ref", "task_state_invalid"
        )

    _name, symbolic_target, object_id, object_type = exact[0]
    if symbolic_target or object_type != "commit" or not object_id:
        raise OrchestrateError(
            f"{label} is not an exact direct commit ref", "task_state_invalid"
        )
    return object_id


def ref_namespace_collision(root: Path, target: str) -> bool:
    """Detect exact and file/directory collisions for a prospective ref."""
    refs = run_git(root, "for-each-ref", "--format=%(refname)").stdout.splitlines()
    return any(
        ref == target
        or ref.startswith(f"{target}/")
        or target.startswith(f"{ref}/")
        for ref in refs
    )


def merge_in_progress(worktree: Path) -> bool:
    return (
        run_git(
            worktree,
            "rev-parse",
            "--verify",
            "--quiet",
            "MERGE_HEAD",
            check=False,
        ).returncode
        == 0
    )


def first_parent_range(root: Path, base: str, tip: str) -> list[str] | None:
    """Return oldest-first first-parent commits after base, or None if unanchored."""
    ancestry = run_git(root, "rev-list", "--first-parent", tip).stdout.splitlines()
    if base not in ancestry:
        return None
    return list(
        reversed(ancestry[: ancestry.index(base)])
    )


def trailer_values(root: Path, sha: str, key: str) -> list[str]:
    """Read repeatable values from Git's interpreted final trailer block."""
    raw = run_git(
        root,
        "show",
        "-s",
        "--format=%(trailers:only,unfold)",
        sha,
    ).stdout
    values: list[str] = []
    for line in raw.splitlines():
        trailer_key, separator, value = line.partition(":")
        if separator and trailer_key.casefold() == key.casefold():
            values.append(value.strip())
    return values


def changed_paths(root: Path, *args: str) -> list[str]:
    raw = run_git(
        root,
        "diff",
        "--name-only",
        "--no-renames",
        "-z",
        *args,
    ).stdout
    return sorted(path for path in raw.split("\0") if path)


def first_parent_changed_paths(root: Path, sha: str) -> list[str]:
    return changed_paths(root, f"{sha}^", sha)
