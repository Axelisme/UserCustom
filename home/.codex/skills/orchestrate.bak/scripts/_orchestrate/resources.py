from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .git_ops import branch_for, run_git, worktree_for
from .primitives import OrchestrateError, require_identifier


def lexical_path(path: Path) -> Path:
    """Return an absolute path without following any symlink."""
    return Path(os.path.abspath(path))


def resolved_path(path: Path) -> Path:
    """Return the effective path after resolving existing symlinks."""
    return path.resolve(strict=False)


@dataclass(frozen=True)
class RepositoryContext:
    worktree_root: Path
    control_root: Path
    git_common_dir: Path

    @classmethod
    def discover(cls, path: Path) -> "RepositoryContext":
        probe = run_git(path, "rev-parse", "--show-toplevel", check=False)
        if probe.returncode:
            raise OrchestrateError("current directory is not a Git repository", "not_git_repository")
        root = Path(probe.stdout.strip()).resolve()
        common_dir = Path(run_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()).resolve()
        control = common_dir.parent if common_dir.name == ".git" else common_dir
        return cls(root, control, common_dir)


@dataclass(frozen=True)
class LaneResources:
    task: "TaskResources"
    lane_id: str

    @property
    def branch(self) -> str:
        return f"wave/{self.task.task_id}/{self.lane_id}"

    @property
    def base_ref(self) -> str:
        return f"refs/orchestrate/{self.task.task_id}/{self.lane_id}/base"

    @property
    def path(self) -> Path:
        return self.task.root / "lanes" / self.lane_id


@dataclass(frozen=True)
class TaskResources:
    repo: RepositoryContext
    task_id: str

    @classmethod
    def derive(cls, repo: RepositoryContext, task_id: str) -> "TaskResources":
        return cls(repo, require_identifier(task_id, label="task id"))

    @property
    def root(self) -> Path:
        return self.repo.control_root / ".agent_state" / "worktrees" / self.task_id

    @property
    def integration_branch(self) -> str:
        return f"wave/{self.task_id}/integration"

    @property
    def integration_base_ref(self) -> str:
        return f"refs/orchestrate/{self.task_id}/integration/base"

    @property
    def accepted_ref(self) -> str:
        return f"refs/orchestrate/{self.task_id}/accepted"

    @property
    def acceptance_open_ref(self) -> str:
        return f"refs/orchestrate/{self.task_id}/acceptance-open"

    @property
    def user_accepted_ref(self) -> str:
        return f"refs/orchestrate/{self.task_id}/user-accepted"

    @property
    def landed_ref(self) -> str:
        return f"refs/orchestrate/{self.task_id}/landed"

    @property
    def integration_path(self) -> Path:
        return self.root / "integration"

    @property
    def acceptance_path(self) -> Path:
        return self.root / "acceptance"

    @property
    def telemetry_path(self) -> Path:
        return self.root / "telemetry.jsonl"

    def lane(self, lane_id: str) -> LaneResources:
        lane = require_identifier(lane_id, label="lane id")
        if lane == "integration":
            raise OrchestrateError("lane id 'integration' is reserved", "invalid_identifier")
        return LaneResources(self, lane)

    def known_inventory(self) -> tuple[Path, ...]:
        return (self.integration_path, self.acceptance_path, self.root / "lanes", self.telemetry_path)

    def branch_exists(self, branch: str) -> bool:
        return run_git(self.repo.worktree_root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0

    def ref(self, name: str) -> str | None:
        probe = run_git(self.repo.worktree_root, "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}", check=False)
        value = probe.stdout.strip()
        return value if probe.returncode == 0 and value else None

    def snapshot(self) -> dict[str, Any]:
        integration = self.ref(self.integration_branch)
        if integration is None:
            raise OrchestrateError("integration branch cannot be resolved", "task_state_invalid")
        return {"integration": integration}

    def collision(self) -> bool:
        root = self.repo.control_root
        orchestrate_parent = run_git(
            root,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/orchestrate/{self.task_id}",
            check=False,
        ).returncode == 0
        wave_parent = run_git(
            root,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/wave/{self.task_id}",
            check=False,
        ).returncode == 0
        refs = run_git(root, "for-each-ref", "--format=%(refname)", f"refs/orchestrate/{self.task_id}/").stdout.splitlines()
        branches = run_git(root, "for-each-ref", "--format=%(refname)", f"refs/heads/wave/{self.task_id}/").stdout.splitlines()
        return bool(
            orchestrate_parent
            or wave_parent
            or refs
            or branches
            or os.path.lexists(self.root)
        )


def ref_value(repo: RepositoryContext, ref: str) -> str | None:
    probe = run_git(repo.worktree_root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    return probe.stdout.strip() if probe.returncode == 0 else None


def active_task_ids(repo: RepositoryContext) -> list[str]:
    prefix = "refs/orchestrate/"
    suffix = "/integration/base"
    raw = run_git(repo.worktree_root, "for-each-ref", "--format=%(refname)", "refs/orchestrate/").stdout.splitlines()
    values = []
    for value in raw:
        if value.startswith(prefix) and value.endswith(suffix):
            task = value[len(prefix):-len(suffix)]
            if "/" not in task:
                values.append(task)
    return sorted(values)


def worktree_state(repo: RepositoryContext, path: Path) -> dict[str, Any]:
    record = worktree_for(repo.worktree_root, path)
    if record is None or not path.exists():
        return {"exists": False, "clean": False, "branch": None, "head": None}
    changed = run_git(path, "status", "--porcelain").stdout.splitlines()
    return {"exists": True, "clean": not changed, "branch": branch_for(record), "head": record.get("HEAD"), "changed": changed}
