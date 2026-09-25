"""Shared harness, git helpers, seeders, and fault wrappers for the collab extension tests.

Tests drive home/.pi/agent/extensions/collab-op.ts through the node harness in
tests/collab_op_extension_harness.mjs against temporary git repositories.
"""

from __future__ import annotations

import atexit
from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

try:
    from tests import _support as support
except ImportError:  # Direct test-file execution keeps tests/ on sys.path.
    import _support as support


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "home/.pi/agent/extensions/collab-op.ts"
HARNESS = ROOT / "tests/collab_op_extension_harness.mjs"
PI_PACKAGE = support.PI_PACKAGE
_HARNESSES: dict[Path, subprocess.Popen[str]] = {}
_HARNESS_SUPPORT: dict[Path, Path | None] = {}


def close_harness(process: subprocess.Popen[str]) -> None:
    if process.stdin:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    finally:
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


def close_harnesses() -> None:
    for process in _HARNESSES.values():
        close_harness(process)
    _HARNESSES.clear()
    _HARNESS_SUPPORT.clear()


atexit.register(close_harnesses)


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        text=True,
        capture_output=True,
        check=True,
    )
    # Remove only trailing line terminators so leading porcelain status
    # columns and other meaningful output content survive normalization.
    return result.stdout.rstrip("\r\n")


def invoke(
    repository: Path,
    request: dict[str, object],
    *,
    support_extension: Path | None = None,
) -> dict[str, object]:
    for stale in [key for key in _HARNESSES if not key.exists()]:
        close_harness(_HARNESSES.pop(stale))
        _HARNESS_SUPPORT.pop(stale, None)

    key = repository.resolve()
    support = support_extension.resolve() if support_extension is not None else None
    process = _HARNESSES.get(key)
    if process is not None and _HARNESS_SUPPORT.get(key) != support:
        close_harness(process)
        _HARNESSES.pop(key, None)
        _HARNESS_SUPPORT.pop(key, None)
        process = None
    if process is None or process.poll() is not None:
        if process is not None:
            close_harness(process)
        command = ["node", str(HARNESS), str(PI_PACKAGE), str(EXTENSION), str(key)]
        if support is not None:
            command.append(str(support))
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _HARNESSES[key] = process
        _HARNESS_SUPPORT[key] = support

    stdin = process.stdin
    stdout = process.stdout
    if stdin is None or stdout is None:
        raise AssertionError("harness pipes are unavailable")
    stdin.write(f"{json.dumps(request)}\n")
    stdin.flush()
    response = stdout.readline()
    if not response:
        stderr = process.stderr.read() if process.stderr else ""
        raise AssertionError(f"harness failed ({process.poll()}): {stderr}")
    return json.loads(response)


def seed_repository(base: Path, object_format: str | None = None) -> tuple[Path, str]:
    repository = base / "repository"
    repository.mkdir()
    init = ["init", "-b", "main"]
    if object_format is not None:
        init.append("--object-format")
        init.append(object_format)
    git(repository, *init)
    git(repository, "config", "user.email", "test@example.com")
    git(repository, "config", "user.name", "Collab Test")
    (repository / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(repository, "add", "tracked.txt")
    git(repository, "commit", "-m", "base")
    return repository, git(repository, "rev-parse", "HEAD")


def seed_task_container(
    repository: Path, task_id: str = "demo", *, archived: bool = False
) -> Path:
    location = "archives" if archived else "plans"
    container = repository / ".agent_state" / location / task_id
    container.mkdir(parents=True, exist_ok=True)
    return container


def telemetry_events(
    repository: Path, task_id: str = "demo", *, archived: bool = False
) -> list[dict[str, object]]:
    container = seed_task_container(repository, task_id, archived=archived)
    telemetry = container / ".collab_op/telemetry.jsonl"
    if not telemetry.exists():
        return []
    return [json.loads(line) for line in telemetry.read_text(encoding="utf-8").splitlines()]


def last_telemetry_event(
    repository: Path, task_id: str = "demo", *, archived: bool = False
) -> dict[str, object]:
    return telemetry_events(repository, task_id, archived=archived)[-1]


def seed_managed_task(repository: Path, task_id: str = "demo") -> dict[str, str]:
    base = git(repository, "rev-parse", "HEAD")
    task_root = repository / ".agent_state/worktrees" / task_id
    integration = task_root / "integration"
    lane = task_root / "lanes/writer-1"
    integration.parent.mkdir(parents=True)

    git(repository, "update-ref", f"refs/orchestrate/{task_id}/integration/base", base)
    git(
        repository,
        "symbolic-ref",
        f"refs/orchestrate/{task_id}/persistence",
        "refs/heads/main",
    )
    git(
        repository,
        "worktree",
        "add",
        "-b",
        f"wave/{task_id}/integration",
        str(integration),
        base,
    )
    (integration / "tracked.txt").write_text("base\nintegration\n", encoding="utf-8")
    git(integration, "add", "tracked.txt")
    git(integration, "commit", "-m", "integration work")
    integration_head = git(integration, "rev-parse", "HEAD")

    lane.parent.mkdir(parents=True)
    git(
        repository,
        "worktree",
        "add",
        "-b",
        f"wave/{task_id}/writer-1",
        str(lane),
        integration_head,
    )
    return {
        "base": base,
        "integration_head": integration_head,
        "integration": str(integration.resolve()),
        "lane": str(lane.resolve())}


def seed_donor(
    repository: Path,
    base: Path,
    base_sha: str,
    branch: str = "donor",
) -> tuple[Path, str]:
    donor = base / "donor-worktree"
    git(repository, "worktree", "add", "-b", branch, str(donor), base_sha)
    (donor / "donor.txt").write_text("donor\n", encoding="utf-8")
    git(donor, "add", "donor.txt")
    git(donor, "commit", "-m", "donor")
    tip = git(donor, "rev-parse", "HEAD")
    (donor / "dirty.txt").write_text("preserve\n", encoding="utf-8")
    return donor, tip


def seed_canonical(repository: Path, source_sha: str, task_id: str = "demo") -> Path:
    integration = repository / ".agent_state/worktrees" / task_id / "integration"
    integration.parent.mkdir(parents=True)
    git(
        repository,
        "worktree",
        "add",
        "-b",
        f"wave/{task_id}/integration",
        str(integration),
        source_sha,
    )
    return integration


def exclude_file(repository: Path) -> Path:
    return repository / ".git/info/exclude"


def exclusion_lines(repository: Path) -> list[str]:
    path = exclude_file(repository)
    if not path.exists():
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() == "/.agent_state/"
    ]


def exclusion_warnings(result: dict[str, object]) -> list[str]:
    return [
        warning
        for warning in result.get("warnings", [])
        if "info/exclude" in warning
    ]


def commit_agent_state_ignore(repository: Path, pattern: str = ".agent_state/") -> str:
    (repository / ".gitignore").write_text(f"{pattern}\n", encoding="utf-8")
    git(repository, "add", ".gitignore")
    git(repository, "commit", "-m", "record ignore rule")
    return git(repository, "rev-parse", "HEAD")


def snapshot_files(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root)
        if relative.parts and relative.parts[0] == ".git":
            continue
        if candidate.is_file():
            snapshot[str(relative)] = candidate.read_bytes()
    return snapshot


def managed_ref_snapshot(repository: Path) -> str:
    return git(
        repository,
        "for-each-ref",
        "--format=%(refname) %(objectname) %(symref)",
        "refs/orchestrate",
        "refs/heads/wave",
    )


def worktree_block(records: str, path: str) -> str | None:
    for block in records.split("\n\n"):
        if block.startswith(f"worktree {path}\n"):
            return block
    return None


@contextmanager
def git_on_path(directory: Path) -> Iterator[None]:
    """Put `directory` (holding a git wrapper) first on PATH for the block, then restore PATH."""
    original = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{directory}:{original}"
    try:
        yield
    finally:
        os.environ["PATH"] = original


def write_git_wrapper(base: Path, script: str) -> Path:
    real_git = shutil.which("git")
    assert real_git is not None
    wrapper_dir = base / "bin"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "git"
    wrapper.write_text(script.replace("__REAL_GIT__", real_git), encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def spawn_raw_harness(repository: Path) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        ["node", str(HARNESS), str(PI_PACKAGE), str(EXTENSION), str(repository.resolve())],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _HARNESSES[repository.resolve()] = process
    _HARNESS_SUPPORT[repository.resolve()] = None
    return process


def send_request(process: subprocess.Popen[str], request: dict[str, object]) -> dict[str, object]:
    stdin = process.stdin
    stdout = process.stdout
    if stdin is None or stdout is None:
        raise AssertionError("harness pipes are unavailable")
    stdin.write(f"{json.dumps(request)}\n")
    stdin.flush()
    response = stdout.readline()
    if not response:
        stderr = process.stderr.read() if process.stderr else ""
        raise AssertionError(f"harness failed ({process.poll()}): {stderr}")
    return json.loads(response)


def wait_until(predicate, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def close_harness_for(repository: Path) -> None:
    key = repository.resolve()
    process = _HARNESSES.pop(key, None)
    _HARNESS_SUPPORT.pop(key, None)
    if process is not None:
        close_harness(process)


def lock_held_by(lock: Path, pid: int) -> bool:
    try:
        return json.loads(lock.read_text(encoding="utf-8")).get("pid") == pid
    except (OSError, ValueError):
        return False


BLOCK_WRAPPER = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
done
if [ "$1" = "worktree" ] && [ "$2" = "add" ] && [ "$3" = "-b" ] && printf '%s' "$4" | grep -q '^wave/'; then
  i=0
  while [ ! -f "__BLOCK__" ]; do
    sleep 0.05
    i=$((i+1))
    if [ "$i" -ge 400 ]; then break; fi
  done
fi
exec "$real_git" "$@"
"""


REPOSITORY_LOCK_BLOCK_WRAPPER = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
done
if [ "$1" = "worktree" ] && [ "$2" = "add" ] && [ "$3" = "-b" ]; then
  if [ "$4" = "wave/demo/slow" ]; then
    printf 'entered\\n' > "__FIRST_ENTERED__"
    i=0
    while [ ! -f "__BLOCK__" ]; do
      sleep 0.05
      i=$((i+1))
      if [ "$i" -ge 400 ]; then break; fi
    done
  fi
  if [ "$4" = "wave/other/fast" ]; then
    printf 'entered\\n' > "__SECOND_ENTERED__"
  fi
fi
exec "$real_git" "$@"
"""


# Blocks report's task ref snapshot after the report has acquired its lock.
REPORT_SNAPSHOT_BLOCK_WRAPPER = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
done
if [ "$1" = "for-each-ref" ]; then
  matches=0
  for arg in "$@"; do
    if [ "$arg" = "refs/orchestrate/demo/" ]; then matches=1; fi
  done
  if [ "$matches" = "1" ]; then
    printf 'blocked\\n' > "__BLOCKED__"
    i=0
    while [ ! -f "__BLOCK__" ]; do
      sleep 0.05
      i=$((i+1))
      if [ "$i" -ge 400 ]; then break; fi
    done
  fi
fi
exec "$real_git" "$@"
"""


FAIL_WORKTREE_REMOVE = """#!/bin/sh
real_git=\"__REAL_GIT__\"
for arg in \"$@\"; do
  if [ \"$arg\" = \"-C\" ]; then exec \"$real_git\" \"$@\"; fi
done
if [ \"$1\" = \"worktree\" ] && [ \"$2\" = \"remove\" ]; then
  printf '%s\\n' 'simulated worktree removal failure' >&2
  exit 1
fi
exec \"$real_git\" \"$@\"
"""


FAIL_LANE_BRANCH_REMOVE = """#!/bin/sh
real_git=\"__REAL_GIT__\"
for arg in \"$@\"; do
  if [ \"$arg\" = \"-C\" ]; then exec \"$real_git\" \"$@\"; fi
done
if [ \"$1\" = \"update-ref\" ]; then
  for arg in \"$@\"; do
    if [ \"$arg\" = \"refs/heads/wave/demo/writer-1\" ]; then
      printf '%s\\n' 'simulated lane branch removal failure' >&2
      exit 1
    fi
  done
fi
exec \"$real_git\" \"$@\"
"""


FAIL_STATUS = """#!/bin/sh
real_git=\"__REAL_GIT__\"
for arg in \"$@\"; do
  if [ \"$arg\" = \"status\" ]; then
    printf '%s\\n' 'simulated status classification failure' >&2
    exit 1
  fi
done
exec \"$real_git\" \"$@\"
"""
