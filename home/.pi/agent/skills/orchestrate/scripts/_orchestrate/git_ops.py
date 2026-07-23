from __future__ import annotations

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
        raise OrchestrateError(f"git {' '.join(args)} failed: {detail}")
    return result


def object_id_length(root: Path) -> int:
    value = run_git(root, "rev-parse", "--show-object-format").stdout.strip()
    if value == "sha1":
        return 40
    if value == "sha256":
        return 64
    raise OrchestrateError(f"unsupported git object format: {value!r}")


def exact_commit(root: Path, value: str, *, label: str) -> str:
    length = object_id_length(root)
    if len(value) != length or HEX_OBJECT_ID_PATTERN.fullmatch(value) is None:
        probe = run_git(root, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}", check=False)
        hint = f"; resolved full SHA: {probe.stdout.strip()} — retry with this value" if probe.returncode == 0 else ""
        raise OrchestrateError(f"{label} must be a full {length}-character hexadecimal commit SHA{hint}")
    resolved = run_git(root, "rev-parse", "--verify", f"{value}^{{commit}}").stdout.strip()
    if resolved.lower() != value.lower():
        raise OrchestrateError(f"{label} does not identify one exact commit: {value}")
    return resolved


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
