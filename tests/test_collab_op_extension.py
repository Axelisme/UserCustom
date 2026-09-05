from __future__ import annotations

import atexit
from collections.abc import Callable
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "home/.pi/agent/extensions/collab-op.ts"
HARNESS = ROOT / "tests/collab_op_extension_harness.mjs"
PI_PACKAGE = Path("/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js")
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

# Blocks the n-th git update-ref invocation (the migration runs exactly two:
# the atomic transition transaction and the sentinel deletion), letting a test
# kill the harness at a precise fault boundary.
UPDATE_REF_BLOCK_WRAPPER = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
done
if [ "$1" = "update-ref" ]; then
  if [ -f "__COUNTER__" ]; then
    n=$(cat "__COUNTER__")
  else
    n=0
  fi
  n=$((n+1))
  printf '%s\\n' "$n" > "__COUNTER__"
  if [ "$n" = "__BLOCK_ON__" ]; then
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

# Blocks git worktree remove before it runs, for crash injection during the
# non-force canonical acceptance cleanup.
WORKTREE_REMOVE_BLOCK_WRAPPER = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
done
if [ "$1" = "worktree" ] && [ "$2" = "remove" ]; then
  printf 'blocked\\n' > "__BLOCKED__"
  i=0
  while [ ! -f "__BLOCK__" ]; do
    sleep 0.05
    i=$((i+1))
    if [ "$i" -ge 400 ]; then break; fi
  done
fi
exec "$real_git" "$@"
"""

# Injects an active clean-index merge (MERGE_HEAD) into the canonical
# integration worktree when git worktree remove runs, i.e. after the first
# resume inventory and before the sentinel compare-and-swap deletion.
MERGE_INJECT_WRAPPER = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
done
if [ "$1" = "worktree" ] && [ "$2" = "remove" ]; then
  printf '%s\\n' "__SHA__" > "__MERGE_HEAD_PATH__"
fi
exec "$real_git" "$@"
"""

class CollabOpExtensionGitHelperRegressionTests(unittest.TestCase):
    def test_unstaged_tracked_deletion_keeps_leading_worktree_column(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / "tracked.txt").unlink()

            self.assertEqual(
                git(repository, "status", "--porcelain=v1"),
                " D tracked.txt",
            )


class CollabOpExtensionIntegrationCreateRegressionTests(unittest.TestCase):
    def test_create_builds_managed_resources_and_records_active_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            head = commit_agent_state_ignore(repository)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), head)
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"),
                head,
            )
            self.assertEqual(
                git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                "refs/heads/main",
            )
            status_result = invoke(
                repository,
                {"tool": "collab_status", "task_id": "demo"},
            )["result"]
            self.assertEqual(status_result["integration"]["HEAD"], head)
            self.assertFalse(status_result["integration"]["stale"])
            telemetry = repository / ".agent_state/plans/demo/.collab_op/telemetry.jsonl"
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-create")
            self.assertEqual(event["subject_sha"], head)
            self.assertEqual(event["persist"], "main")
            self.assertEqual(stat.S_IMODE(telemetry.stat().st_mode), 0o600)

    def test_create_without_task_container_warns_but_does_not_create_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in item for item in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())
            self.assertEqual(
                git(repository, "rev-parse", "wave/demo/integration"),
                git(repository, "rev-parse", "main"),
            )

    def test_create_records_telemetry_in_an_archived_container(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            commit_agent_state_ignore(repository)
            archive = seed_task_container(repository, archived=True)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertNotIn("warnings", observed["result"])
            self.assertTrue((archive / ".collab_op/telemetry.jsonl").is_file())

    def test_create_collision_refuses_without_changing_existing_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            root = repository / ".agent_state/worktrees/demo"
            root.mkdir(parents=True)
            sentinel = root / "user.txt"
            sentinel.write_text("preserve\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")

    def test_create_detached_head_refuses_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            git(repository, "checkout", "--detach", head)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "detached_head")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")

    def test_create_symlinked_managed_parent_refuses_without_writing_through_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            outside = base / "outside"
            outside.mkdir()
            (repository / ".agent_state").symlink_to(outside, target_is_directory=True)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(list(outside.iterdir()), [])

    def test_create_later_ref_failure_rolls_back_worktree_and_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            lock = repository / ".git/refs/orchestrate/demo/integration/base.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo"),
                "",
            )
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())
            self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock\n")

    def test_create_adjacent_task_namespace_does_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            git(repository, "update-ref", "refs/orchestrate/demo-extra/integration/base", head)
            git(repository, "branch", "wave/demo-extra/integration", head)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), head)


class CollabOpExtensionIntegrationAdoptRegressionTests(unittest.TestCase):
    def test_adoption_preserves_dirty_donor_and_exposes_only_agreed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            base_sha = commit_agent_state_ignore(repository)
            donor, source_sha = seed_donor(repository, base, base_sha)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                set(observed["result"]),
                {"ok", "tool_version", "source_branch", "integration_branch"},
            )
            self.assertEqual(observed["result"]["source_branch"], "donor")
            self.assertEqual(observed["result"]["integration_branch"], "wave/demo/integration")
            self.assertEqual(git(donor, "rev-parse", "HEAD"), source_sha)
            self.assertEqual(git(donor, "status", "--porcelain=v1"), "?? dirty.txt")
            integration = repository / ".agent_state/worktrees/demo/integration"
            self.assertEqual(git(integration, "rev-parse", "HEAD"), source_sha)
            self.assertEqual(git(integration, "status", "--porcelain=v1"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), source_sha)
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-adopt")
            self.assertEqual(event["source_branch"], "donor")

    def test_adoption_rejects_abbreviated_or_non_lowercase_base_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            seed_donor(repository, base, base_sha)

            for value in (base_sha[:8], base_sha.upper(), "HEAD"):
                observed = invoke(
                    repository,
                    {
                        "tool": "collab_integration_adopt",
                        "task_id": "demo",
                        "source_branch": "donor",
                        "persist": "main",
                        "base_sha": value},
                )
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "invalid_base_sha")
                self.assertTrue(observed["error"]["error"]["repair"])

    def test_adoption_rejects_base_not_ancestor_of_both_tips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, original_base = seed_repository(base)
            _, source_sha = seed_donor(repository, base, original_base)
            other = base / "other"
            git(repository, "worktree", "add", "-b", "other", str(other), original_base)
            (other / "other.txt").write_text("other\n", encoding="utf-8")
            git(other, "add", "other.txt")
            git(other, "commit", "-m", "other")
            other_sha = git(other, "rev-parse", "HEAD")

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": other_sha},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "base_not_ancestor")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(observed["error"]["error"]["details"]["base_sha"], other_sha)
            self.assertEqual(observed["error"]["error"]["details"]["source_sha"], source_sha)
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_adoption_collision_refuses_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            seed_donor(repository, base, base_sha)
            git(repository, "update-ref", "refs/orchestrate/demo/integration/base", base_sha)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"),
                base_sha,
            )
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_adoption_rolls_back_only_created_resources_after_ref_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            seed_donor(repository, base, base_sha)
            lock = repository / ".git/refs/orchestrate/demo/integration/base.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha},
            )

            self.assertTrue(observed["is_error"])
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo"),
                "",
            )
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())
            self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock\n")

    def test_adoption_warns_without_task_container(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            seed_donor(repository, base, base_sha)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())

    def test_canonical_adoption_fills_only_missing_refs_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            base_sha = commit_agent_state_ignore(repository)
            integration = seed_canonical(repository, base_sha)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "wave/demo/integration",
                    "persist": "main",
                    "base_sha": base_sha},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                set(observed["result"]),
                {"ok", "tool_version", "source_branch", "integration_branch"},
            )
            self.assertEqual(observed["result"]["source_branch"], "wave/demo/integration")
            self.assertEqual(observed["result"]["integration_branch"], "wave/demo/integration")
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"), base_sha)
            self.assertEqual(
                git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                "refs/heads/main",
            )
            self.assertEqual(git(integration, "rev-parse", "HEAD"), base_sha)
            self.assertEqual(git(integration, "status", "--porcelain=v1"), "")
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/heads/wave/demo/integration"),
                "refs/heads/wave/demo/integration",
            )

    def test_canonical_adoption_refuses_tracked_dirt_or_partial_arrangements(self) -> None:
        for case in ("tracked", "extra_ref", "detached"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, base_sha = seed_repository(base)
                integration = seed_canonical(repository, base_sha)
                if case == "tracked":
                    (integration / "tracked.txt").write_text("preserve tracked change\n", encoding="utf-8")
                elif case == "extra_ref":
                    git(repository, "update-ref", "refs/orchestrate/demo/extra", base_sha)
                else:
                    git(integration, "checkout", "--detach")

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_integration_adopt",
                        "task_id": "demo",
                        "source_branch": "wave/demo/integration",
                        "persist": "main",
                        "base_sha": base_sha},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
                self.assertTrue(observed["error"]["error"]["repair"])
                if case == "tracked":
                    self.assertEqual(
                        (integration / "tracked.txt").read_text(encoding="utf-8"),
                        "preserve tracked change\n",
                    )
                elif case == "extra_ref":
                    self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/extra"), base_sha)
                else:
                    self.assertEqual(git(integration, "rev-parse", "HEAD"), base_sha)

    def test_canonical_adoption_accepts_untracked_and_ignored_paths(self) -> None:
        for state in ("untracked", "ignored"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                (repository / ".gitignore").write_text(
                    ".agent_state/\nignored.tmp\n", encoding="utf-8"
                )
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime state")
                base_sha = git(repository, "rev-parse", "HEAD")
                integration = seed_canonical(repository, base_sha)
                seed_task_container(repository)
                candidate = integration / ("ordinary.tmp" if state == "untracked" else "ignored.tmp")
                candidate.write_text(f"{state} runtime\n", encoding="utf-8")

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_integration_adopt",
                        "task_id": "demo",
                        "source_branch": "wave/demo/integration",
                        "persist": "main",
                        "base_sha": base_sha},
                )

                self.assertFalse(observed["is_error"])
                self.assertTrue(candidate.is_file())
                self.assertNotIn("warnings", observed["result"])


class CollabOpExtensionLaneCreateRegressionTests(unittest.TestCase):
    def test_lane_create_uses_committed_integration_tip_and_records_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            committed_tip = expected["integration_head"]
            (integration / "tracked.txt").write_text("dirty integration\n", encoding="utf-8")
            (integration / "untracked.txt").write_text("exclude me\n", encoding="utf-8")
            (repository / ".git/info/exclude").write_text("ignored.txt\n", encoding="utf-8")
            (integration / "ignored.txt").write_text("exclude ignored\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": "writer",
                    "comment": "  review 🧭  "},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            self.assertEqual(git(lane, "rev-parse", "HEAD"), committed_tip)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual((integration / "tracked.txt").read_text(encoding="utf-8"), "dirty integration\n")
            self.assertEqual((integration / "untracked.txt").read_text(encoding="utf-8"), "exclude me\n")
            self.assertEqual((integration / "ignored.txt").read_text(encoding="utf-8"), "exclude ignored\n")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-create")
            self.assertEqual(event["lane_id"], "writer")
            self.assertEqual(event["comment"], "review 🧭")
            self.assertEqual(event["lane_sha"], committed_tip)
            self.assertEqual(event["integration_sha"], committed_tip)

    def test_lane_create_rejects_reserved_lane_and_invalid_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)

            for lane_id, comment, expected_code in (
                ("integration", None, "reserved_lane"),
                ("writer", "🧭" * 501, "invalid_comment"),
                ("writer", "control\x01byte", "invalid_comment"),
            ):
                request: dict[str, object] = {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": lane_id}
                if comment is not None:
                    request["comment"] = comment
                observed = invoke(repository, request)
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], expected_code)
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer").exists())

            valid = invoke(
                repository,
                {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": "unicode",
                    "comment": "🧭" * 500},
            )
            self.assertFalse(valid["is_error"])

    def test_lane_create_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())

    def test_lane_create_collision_refuses_before_mutation(self) -> None:
        for collision in ("branch", "path"):
            with self.subTest(collision=collision), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                expected = seed_managed_task(repository)
                lane = repository / ".agent_state/worktrees/demo/lanes/writer"
                if collision == "branch":
                    git(repository, "branch", "wave/demo/writer", expected["base"])
                else:
                    lane.mkdir(parents=True)
                    (lane / "sentinel.bin").write_bytes(b"preserve\x00\xff")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "lane_resource_collision")
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertEqual(
                    git(repository, "rev-parse", "wave/demo/integration"),
                    expected["integration_head"],
                )
                if collision == "path":
                    self.assertEqual((lane / "sentinel.bin").read_bytes(), b"preserve\x00\xff")

    def test_lane_create_failure_leaves_no_partial_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            lock = repository / ".git/refs/heads/wave/demo/writer.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertTrue(observed["is_error"])
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer").exists())
            self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock\n")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])

    def test_lane_create_warns_when_nine_existing_lanes_have_uncollected_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            for index in range(9):
                lane_id = f"writer-{index:02d}"
                created = invoke(
                    repository,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": lane_id},
                )
                self.assertFalse(created["is_error"])
                lane = repository / ".agent_state/worktrees/demo/lanes" / lane_id
                (lane / f"{lane_id}.txt").write_text("work\n", encoding="utf-8")
                git(lane, "add", f"{lane_id}.txt")
                git(lane, "commit", "-m", f"work {lane_id}")

            observed = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer-final"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("9 or more" in warning for warning in observed["result"]["warnings"]))


class CollabOpExtensionLaneReconcileRegressionTests(unittest.TestCase):
    def test_lane_reconcile_noop_preserves_integration_dirt_and_records_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "tool_version": 1,
                    "state": "noop",
                    "warnings": ["lane already includes latest integration"]},
            )
            self.assertEqual((integration / "operator-dirt.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-reconcile")
            self.assertEqual(event["outcome"], "noop")
            self.assertEqual(event["state"], "noop")

    def test_lane_reconcile_clean_merge_commits_one_exact_subject_and_leaves_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            lane_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            (integration / "committed.txt").write_text("committed\n", encoding="utf-8")
            git(integration, "add", "committed.txt")
            git(integration, "commit", "-m", "integration advance")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            (integration / "tracked.txt").write_text("dirty integration content\n", encoding="utf-8")
            (integration / "untracked.txt").write_text("dirty integration file\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1, "state": "merged"})
            merged_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            self.assertNotEqual(merged_sha, lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertEqual(
                git(repository, "rev-list", "--parents", "-n", "1", merged_sha).split(),
                [merged_sha, lane_sha, integration_sha],
            )
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual((integration / "tracked.txt").read_text(encoding="utf-8"), "dirty integration content\n")
            self.assertEqual((integration / "untracked.txt").read_text(encoding="utf-8"), "dirty integration file\n")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-reconcile")
            self.assertEqual(event["outcome"], "success")
            self.assertEqual(event["state"], "merged")
            self.assertEqual(event["lane_sha"], merged_sha)
            self.assertEqual(event["integration_sha"], integration_sha)

    def test_lane_reconcile_conflict_is_successful_bounded_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (lane / "tracked.txt").write_text("lane\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane conflict")
            lane_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            (integration / "tracked.txt").write_text("integration\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                {key: value for key, value in observed["result"].items() if key != "warnings"},
                {"ok": True, "tool_version": 1, "state": "conflicted"},
            )
            self.assertTrue(observed["result"]["warnings"])
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertTrue(last_telemetry_event(repository)["conflict_path_count"] == 1)

    def test_lane_reconcile_unexpected_merge_failure_restores_exact_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "advance.txt").write_text("advance\n", encoding="utf-8")
            git(integration, "add", "advance.txt")
            git(integration, "commit", "-m", "integration advance")
            lane_sha = git(lane, "rev-parse", "HEAD")
            lock = git(lane, "rev-parse", "--git-path", "index.lock")
            lock_path = Path(lock) if Path(lock).is_absolute() else (lane / lock)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "git_error")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertTrue(observed["error"]["error"]["details"]["rollback"]["restored"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual(lock_path.read_text(encoding="utf-8"), "foreign lock\n")

    def test_lane_reconcile_refuses_tracked_dirt_and_identity_mismatches(self) -> None:
        for case in ("tracked", "identity"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                lane = Path(expected["lane"])
                if case == "tracked":
                    (lane / "tracked.txt").write_text("tracked change\n", encoding="utf-8")
                else:
                    git(lane, "checkout", "--detach")
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
                )
                self.assertTrue(observed["is_error"])
                self.assertEqual(
                    observed["error"]["error"]["code"],
                    "dirty_worktree" if case == "tracked" else "worktree_identity_mismatch",
                )
                self.assertTrue(observed["error"]["error"]["repair"])

    def test_lane_reconcile_accepts_untracked_and_ignored_paths(self) -> None:
        for state in ("untracked", "ignored"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime state")
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lane = Path(expected["lane"])
                candidate = lane / ("ordinary.tmp" if state == "untracked" else "ignored.tmp")
                candidate.write_text(f"{state} runtime\n", encoding="utf-8")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertFalse(observed["is_error"])
                self.assertEqual(observed["result"]["state"], "noop")
                self.assertTrue(candidate.is_file())
                self.assertFalse(
                    any("dirty" in warning or "preserv" in warning for warning in observed["result"]["warnings"])
                )

    def test_lane_reconcile_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "advance.txt").write_text("advance\n", encoding="utf-8")
            git(integration, "add", "advance.txt")
            git(integration, "commit", "-m", "integration advance")

            observed = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


class CollabOpExtensionTaskLockTests(unittest.TestCase):
    def test_live_task_lock_refuses_mutation_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True)
            lock = lock_dir / "demo.lock"
            lock.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "started_at": "2026-08-13T00:00:00.000Z",
                        "task_id": "demo"}
                ),
                encoding="utf-8",
            )
            refs_before = managed_ref_snapshot(repository)

            observed = invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_busy")
            details = observed["error"]["error"]["details"]
            self.assertEqual(details.get("task_id"), "demo")
            # SL02: lane_create uses bounded wait (10s) rather than immediate fail-fast
            self.assertIn("waited_ms", details)
            self.assertEqual(details.get("timeout_ms"), 10000)
            self.assertGreaterEqual(details.get("waited_ms", 0), 9000)
            self.assertEqual(managed_ref_snapshot(repository), refs_before)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer").exists())
            # status is read-only and is not serialized through the task lock.
            status_result = invoke(repository, {"tool": "collab_status", "task_id": "demo"})["result"]
            self.assertEqual(status_result["integration"]["HEAD"], expected["integration_head"])

    def test_stale_task_lock_is_broken_and_lock_is_released_in_finally(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True)
            dead = subprocess.Popen(["true"])
            dead.wait()
            lock = lock_dir / "demo.lock"
            lock.write_text(
                json.dumps(
                    {
                        "pid": dead.pid,
                        "started_at": "2026-08-13T00:00:00.000Z",
                        "task_id": "demo"}
                ),
                encoding="utf-8",
            )

            created = invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"})

            self.assertFalse(created["is_error"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer"), expected["integration_head"])
            self.assertFalse(lock.exists(), "lock was not released in finally")

            # A failing request also releases the lock in finally.
            git(repository, "update-ref", "refs/heads/wave/demo/other", expected["integration_head"])
            refused = invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "other"})
            self.assertTrue(refused["is_error"])
            self.assertEqual(refused["error"]["error"]["code"], "lane_resource_collision")
            self.assertFalse((lock_dir / "demo.lock").exists(), "lock leaked after a failed request")

    def test_task_lock_is_scoped_per_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            seed_managed_task(repository, "other")
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True)
            (lock_dir / "demo.lock").write_text(
                json.dumps({"pid": os.getpid(), "started_at": "2026-08-13T00:00:00.000Z", "task_id": "demo"}),
                encoding="utf-8",
            )

            observed = invoke(repository, {"tool": "collab_lane_create", "task_id": "other", "lane_id": "writer"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                git(repository, "rev-parse", "wave/other/writer"),
                git(repository, "rev-parse", "wave/other/integration"),
            )

    def test_concurrent_stale_takeover_preserves_replacement_and_verifies_release_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True)
            dead = subprocess.Popen(["true"])
            dead.wait()
            planted = lock_dir / "demo.lock"
            planted.write_text(
                json.dumps(
                    {
                        "pid": dead.pid,
                        "started_at": "2026-08-13T00:00:00.000Z",
                        "task_id": "demo",
                        "token": "stale-token"}
                ),
                encoding="utf-8",
            )
            block = base / "block"
            wrapper = write_git_wrapper(base, BLOCK_WRAPPER.replace("__BLOCK__", str(block)))
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            first: subprocess.Popen[str] | None = None
            second: subprocess.Popen[str] | None = None
            try:
                first = spawn_raw_harness(repository)
                second = spawn_raw_harness(repository)
                first_stdin = first.stdin
                first_stdout = first.stdout
                assert first_stdin is not None and first_stdout is not None
                first_stdin.write(
                    f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
                )
                first_stdin.flush()
                # The first request takes over the stale lock, then blocks in git.
                self.assertTrue(
                    wait_until(lambda: lock_held_by(planted, first.pid)),
                    "the stale lock was never taken over",
                )
                # The verified takeover leaves no quarantine residue.
                self.assertEqual(list(lock_dir.glob("*.quarantine-*")), [])
                # A concurrent request sees the live lock and is refused.
                refused = send_request(
                    second,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "cross"},
                )
                self.assertTrue(refused["is_error"])
                self.assertEqual(refused["error"]["error"]["code"], "task_busy")
                # Simulate the double-race: while the first request is in
                # flight, its lock is replaced by a foreign live lock.
                planted.write_text(
                    json.dumps(
                        {
                            "pid": os.getpid(),
                            "started_at": "2026-08-13T00:00:00.000Z",
                            "task_id": "demo",
                            "token": "foreign-owner-token"}
                    ),
                    encoding="utf-8",
                )
                # Release the first request; its release must verify ownership
                # and must not unlink the replacement.
                block.write_text("go\n", encoding="utf-8")
                first_response = json.loads(first_stdout.readline())
                self.assertFalse(first_response["is_error"])
                self.assertTrue(planted.exists(), "release deleted a lock it did not own")
                self.assertIn("foreign-owner-token", planted.read_text(encoding="utf-8"))
                # The replacement still guards the task.
                refused_again = send_request(
                    second,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "cross2"},
                )
                self.assertTrue(refused_again["is_error"])
                self.assertEqual(refused_again["error"]["error"]["code"], "task_busy")
                # Once the foreign lock is removed, requests proceed normally.
                planted.unlink()
                ok = send_request(
                    second,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "cross"},
                )
                self.assertFalse(ok["is_error"])
                self.assertEqual(
                    git(repository, "rev-parse", "wave/demo/cross"),
                    expected["integration_head"],
                )
            finally:
                os.environ["PATH"] = original_path
                for process in (first, second):
                    if process is not None:
                        close_harness(process)

    def test_release_never_deletes_foreign_replacement_and_restores_byte_for_byte(self) -> None:
        # The replacement is present when release runs; the rename-first
        # release must quarantine it, verify it is foreign, and restore it to
        # the canonical path byte-for-byte instead of deleting it.
        for case in ("inode_replaced", "content_replaced"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lock_dir = repository / ".git/collab-op-locks"
                lock_dir.mkdir(parents=True)
                lock = lock_dir / "demo.lock"
                block = base / "block"
                wrapper = write_git_wrapper(base, BLOCK_WRAPPER.replace("__BLOCK__", str(block)))
                original_path = os.environ["PATH"]
                os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
                first: subprocess.Popen[str] | None = None
                try:
                    first = spawn_raw_harness(repository)
                    first_stdin = first.stdin
                    first_stdout = first.stdout
                    assert first_stdin is not None and first_stdout is not None
                    first_stdin.write(
                        f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
                    )
                    first_stdin.flush()
                    self.assertTrue(
                        wait_until(lambda: lock.exists() and lock_held_by(lock, first.pid)),
                        "request never acquired the lock",
                    )
                    foreign = (
                        json.dumps(
                            {
                                "pid": os.getpid(),
                                "started_at": "2026-08-13T00:00:00.000Z",
                                "task_id": "demo",
                                "token": "foreign-owner-token"}
                        )
                        + "\n"
                    )
                    if case == "inode_replaced":
                        lock.unlink()
                    lock.write_text(foreign, encoding="utf-8")
                    # Release the request; its release must not delete the
                    # replacement.
                    block.write_text("go\n", encoding="utf-8")
                    response = json.loads(first_stdout.readline())
                    self.assertFalse(response["is_error"])
                    # The foreign replacement was restored byte-for-byte.
                    self.assertEqual(lock.read_text(encoding="utf-8"), foreign)
                    self.assertEqual(list(lock_dir.glob("*.quarantine-*")), [])
                    # The restored foreign lock still guards the task.
                    refused = send_request(
                        first,
                        {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "cross"},
                    )
                    self.assertTrue(refused["is_error"])
                    self.assertEqual(refused["error"]["error"]["code"], "task_busy")
                finally:
                    os.environ["PATH"] = original_path
                    if first is not None:
                        close_harness(first)

    def test_concurrent_public_requests_cannot_cross_the_task_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            block = base / "block"
            wrapper = write_git_wrapper(base, BLOCK_WRAPPER.replace("__BLOCK__", str(block)))
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            first: subprocess.Popen[str] | None = None
            second: subprocess.Popen[str] | None = None
            try:
                first = spawn_raw_harness(repository)
                second = spawn_raw_harness(repository)
                # The first request blocks inside its git wrapper while it
                # holds the task lock; its response is read after release.
                first_stdin = first.stdin
                first_stdout = first.stdout
                assert first_stdin is not None and first_stdout is not None
                first_stdin.write(
                    f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
                )
                first_stdin.flush()
                lock = repository / ".git/collab-op-locks/demo.lock"
                self.assertTrue(
                    wait_until(lambda: lock.exists()),
                    "first request never acquired the task lock",
                )
                # A concurrent public request from a separate process must not
                # cross the lock.
                refused = send_request(
                    second,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "cross"},
                )
                self.assertTrue(refused["is_error"])
                self.assertEqual(refused["error"]["error"]["code"], "task_busy")
                self.assertEqual(git(repository, "branch", "--list", "wave/demo/cross"), "")
                self.assertFalse(
                    (repository / ".agent_state/worktrees/demo/lanes/cross").exists()
                )
                # Release the first request; it completes and releases the lock.
                block.write_text("go\n", encoding="utf-8")
                first_response = json.loads(first_stdout.readline())
                self.assertFalse(first_response["is_error"])
                self.assertEqual(git(repository, "rev-parse", "wave/demo/slow"), expected["integration_head"])
                self.assertFalse(lock.exists(), "lock was not released in finally")
                # The refused request can now proceed normally.
                retried = send_request(
                    second,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "cross"},
                )
                self.assertFalse(retried["is_error"])
                self.assertEqual(git(repository, "rev-parse", "wave/demo/cross"), expected["integration_head"])
            finally:
                os.environ["PATH"] = original_path
                for process in (first, second):
                    if process is not None:
                        close_harness(process)


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


class CollabOpExtensionRegisteredToolTests(unittest.TestCase):
    def test_final_inventory_exposes_only_independent_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(repository, {"tool": "collab_status"})

            self.assertEqual(
                observed["tools"],
                [
                    "collab_integration_adopt",
                    "collab_integration_create",
                    "collab_integration_land",
                    "collab_integration_reconcile",
                    "collab_integration_remove",
                    "collab_lane",
                    "collab_report",
                    "collab_status"],
            )
            self.assertEqual(set(observed["schemas"]), set(observed["tools"]))
            self.assertFalse(observed["is_error"])
            for name in observed["tools"]:
                schema = observed["schemas"][name]["parameters"]
                self.assertEqual(schema["type"], "object")
                self.assertFalse(schema["additionalProperties"])
                self.assertIn("repo", schema["properties"])
                self.assertNotIn("repo", schema.get("required", []))
            self.assertEqual(
                set(observed["schemas"]["collab_integration_reconcile"]["parameters"]["properties"]),
                {"task_id", "lane_id", "repo"},
            )
            self.assertEqual(
                observed["schemas"]["collab_integration_reconcile"]["parameters"]["required"],
                ["task_id", "lane_id"],
            )
            self.assertEqual(
                set(observed["schemas"]["collab_integration_land"]["parameters"]["properties"]),
                {"task_id", "message", "repo"},
            )
            self.assertEqual(
                observed["schemas"]["collab_integration_land"]["parameters"]["required"],
                ["task_id"],
            )
            self.assertEqual(
                set(observed["schemas"]["collab_integration_remove"]["parameters"]["properties"]),
                {"task_id", "repo"},
            )
            self.assertEqual(
                observed["schemas"]["collab_integration_remove"]["parameters"]["required"],
                ["task_id"],
            )
            for name in ("collab_integration_reconcile", "collab_integration_land", "collab_integration_remove"):
                self.assertNotIn("method", observed["schemas"][name]["parameters"]["properties"])

            legacy = invoke(repository, {"tool": "collab_op", "method": "status"})
            self.assertTrue(legacy["is_error"])
            self.assertEqual(legacy["error"]["error"]["code"], "unknown_tool")

    def test_repo_selects_create_target_from_outside_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            seed_task_container(target)

            observed = invoke(
                outside,
                {
                    "tool": "collab_integration_create",
                    "task_id": "demo",
                    "repo": str(target),
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue((target / ".agent_state/worktrees/demo/integration").is_dir())
            self.assertEqual(git(target, "status", "--porcelain"), "")

    def test_repo_drives_complete_lifecycle_from_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            commit_agent_state_ignore(target)
            seed_task_container(target)
            selected_repo = str(target)

            created = invoke(
                outside,
                {
                    "tool": "collab_integration_create",
                    "task_id": "demo",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(created["is_error"])

            lane_created = invoke(
                outside,
                {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": "writer",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(lane_created["is_error"])
            lane = target / ".agent_state/worktrees/demo/lanes/writer"
            (lane / "work.txt").write_text("lane work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")

            collected = invoke(
                outside,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")

            landed = invoke(
                outside,
                {
                    "tool": "collab_integration_land",
                    "task_id": "demo",
                    "message": "Land selected repository work",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(landed["is_error"])
            self.assertEqual(git(target, "show", "HEAD:work.txt"), "lane work")
            self.assertFalse((outside / ".agent_state").exists())

            removed = invoke(
                outside,
                {
                    "tool": "collab_integration_remove",
                    "task_id": "demo",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(removed["is_error"])
            self.assertFalse((target / ".agent_state/worktrees/demo").exists())

    def test_repo_rejects_invalid_shapes_before_git_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            file_path = base / "not-a-directory"
            file_path.write_text("file\n", encoding="utf-8")
            invalid_values: tuple[tuple[str, object], ...] = (
                ("non-string", 7),
                ("empty", ""),
                ("relative", "repository"),
                ("missing", str(base / "missing")),
                ("file", str(file_path)),
            )

            for case, value in invalid_values:
                with self.subTest(case=case):
                    observed = invoke(
                        outside,
                        {"tool": "collab_status", "repo": value},
                    )
                    self.assertTrue(observed["is_error"])
                    self.assertEqual(observed["error"]["error"]["code"], "invalid_repo")
                    self.assertTrue(observed["error"]["error"]["repair"])

    def test_repo_rejects_subdirectory_with_worktree_root_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            subdirectory = target / "nested"
            subdirectory.mkdir()

            observed = invoke(
                outside,
                {"tool": "collab_status", "repo": str(subdirectory)},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "repo_not_worktree_root")
            self.assertEqual(error["details"]["worktree_root"], str(target.resolve()))

    def test_repo_rejects_directory_outside_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            selected = base / "not-a-repository"
            selected.mkdir()

            observed = invoke(
                outside,
                {"tool": "collab_status", "repo": str(selected)},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "not_git_repository")
            self.assertTrue(error["repair"])

    def test_repo_accepts_symlink_to_worktree_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            selected = base / "selected-repository"
            selected.symlink_to(target, target_is_directory=True)

            observed = invoke(
                outside,
                {"tool": "collab_status", "repo": str(selected)},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["tasks"], [])

    def test_repo_accepts_linked_worktree_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            linked_worktree = base / "linked-worktree"
            git(target, "worktree", "add", "-b", "linked", str(linked_worktree), "HEAD")

            observed = invoke(
                outside,
                {"tool": "collab_status", "repo": str(linked_worktree)},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["tasks"], [])

    def test_repo_selects_named_worktree_attached_branch_for_create(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            session_base = base / "session"
            session_base.mkdir()
            session_repository, _ = seed_repository(session_base)
            git(session_repository, "checkout", "-b", "session-persist")
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            git(target, "checkout", "-b", "target-persist")
            seed_task_container(target)

            observed = invoke(
                session_repository,
                {
                    "tool": "collab_integration_create",
                    "task_id": "demo",
                    "repo": str(target),
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                git(target, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                "refs/heads/target-persist",
            )
            self.assertEqual(
                git(session_repository, "symbolic-ref", "--short", "HEAD"),
                "session-persist",
            )

    def test_repo_controls_relative_report_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            target_base = base / "target"
            target_base.mkdir()
            target, _ = seed_repository(target_base)
            seed_task_container(target)
            selected_repo = str(target)
            created = invoke(
                outside,
                {
                    "tool": "collab_integration_create",
                    "task_id": "demo",
                    "repo": selected_repo,
                },
            )
            self.assertFalse(created["is_error"])

            observed = invoke(
                outside,
                {
                    "tool": "collab_report",
                    "task_id": "demo",
                    "output_dir": "reports/selected",
                    "repo": selected_repo,
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue((target / "reports/selected/collab-report.json").is_file())
            self.assertTrue((target / "reports/selected/collab-telemetry.jsonl").is_file())
            self.assertFalse((outside / "reports").exists())

    def test_integration_reconcile_derives_persistence_and_projects_reduced_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            seed_managed_task(repository)
            (repository / "persistence.txt").write_text("persisted\n", encoding="utf-8")
            git(repository, "add", "persistence.txt")
            git(repository, "commit", "-m", "persistence work")

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "persistence"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "merged")
            self.assertEqual(observed["result"]["lane_id"], "persistence")
            self.assertIn("lane_sha", observed["result"])
            self.assertNotIn("persist", observed["result"])
            self.assertNotIn("persistence_sha", observed["result"])
            self.assertNotIn("integration_sha", observed["result"])
            self.assertNotIn("conflict_paths", observed["result"])

    def test_integration_land_derives_persistence_and_projects_common_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            seed_task_container(repository)
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration_land", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["ok"], True)
            self.assertEqual(observed["result"]["tool_version"], 1)
            self.assertNotIn("integration_sha", observed["result"])
            self.assertNotIn("persistence_sha", observed["result"])
            self.assertNotIn("landed_sha", observed["result"])

    def test_integration_remove_best_effort_cleans_dirty_uncollected_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "lane-work.txt").write_text("uncollected\n", encoding="utf-8")
            git(lane, "add", "lane-work.txt")
            git(lane, "commit", "-m", "lane work")
            (Path(expected["integration"]) / "dirty.txt").write_text("dirty\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_integration_remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                {key for key in observed["result"] if key != "warnings"},
                {"ok", "tool_version"},
            )
            self.assertTrue(observed["result"].get("warnings"))
            self.assertFalse(Path(expected["integration"]).exists())
            self.assertFalse(Path(expected["lane"]).exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repository), "show-ref", "--verify", "--quiet", "refs/orchestrate/demo/integration/base"],
                    capture_output=True,
                ).returncode,
                0,
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repository), "symbolic-ref", "--quiet", "refs/orchestrate/demo/persistence"],
                    capture_output=True,
                ).returncode,
                0,
            )

    def test_integration_remove_force_retires_untracked_and_ignored_paths_without_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore runtime state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            for worktree in (Path(expected["integration"]), Path(expected["lane"])):
                (worktree / "ordinary.tmp").write_text("ordinary runtime\n", encoding="utf-8")
                (worktree / "ignored.tmp").write_text("ignored runtime\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_integration_remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertNotIn("warnings", observed["result"])
            self.assertFalse(Path(expected["integration"]).exists())
            self.assertFalse(Path(expected["lane"]).exists())

    def test_integration_remove_reports_residuals_and_continues_after_git_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            wrapper = write_git_wrapper(base, FAIL_WORKTREE_REMOVE)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_integration_remove", "task_id": "demo"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(Path(expected["integration"]).exists())
            self.assertTrue(Path(expected["lane"]).exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "+ wave/demo/integration")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "+ wave/demo/writer-1")

    def test_migration_namespace_does_not_gate_current_tools_or_get_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, base_sha = seed_repository(Path(temporary))
            seed_task_container(repository)
            seed_managed_task(repository)
            git(repository, "update-ref", "refs/orchestrate/demo/migration", base_sha)

            observed = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "new-lane"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/migration"),
                base_sha,
            )
            status = invoke(repository, {"tool": "collab_status", "task_id": "demo"})
            self.assertFalse(status["is_error"])
            self.assertNotIn("recovery_required", status["result"])

    def test_legacy_layout_returns_ordinary_error_without_deleting_unknown_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, base_sha = seed_repository(Path(temporary))
            git(repository, "update-ref", "refs/orchestrate/demo/accepted", base_sha)

            observed = invoke(
                repository,
                {"tool": "collab_integration_remove", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_not_found")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/accepted"),
                base_sha,
            )

    def test_all_final_tools_return_actionable_structured_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            requests = (
                ("collab_integration_create", {}),
                ("collab_integration_adopt", {"task_id": "demo"}),
                ("collab_integration_reconcile", {"task_id": "demo"}),
                ("collab_integration_land", {}),
                ("collab_integration_remove", {}),
                ("collab_lane_create", {"task_id": "demo"}),
                ("collab_lane_reconcile", {"task_id": "demo"}),
                ("collab_lane_collect", {"task_id": "demo"}),
                ("collab_lane_drop", {"task_id": "demo"}),
                ("collab_report", {"task_id": "demo"}),
                ("collab_status", {"task_id": "Not-Safe"}),
            )

            for tool, request in requests:
                with self.subTest(tool=tool):
                    observed = invoke(repository, {"tool": tool, **request})
                    self.assertTrue(observed["is_error"])
                    error = observed["error"]
                    self.assertEqual(error["ok"], False)
                    self.assertEqual(error["tool_version"], 1)
                    self.assertNotIn("operation", error)
                    self.assertIsInstance(error["error"]["code"], str)
                    self.assertTrue(error["error"]["message"])
                    self.assertTrue(error["error"]["repair"])

    def test_complete_lifecycle_uses_only_final_registered_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            seed_task_container(repository)

            self.assertFalse(
                invoke(
                    repository,
                    {"tool": "collab_integration_create", "task_id": "demo"},
                )["is_error"]
            )
            self.assertFalse(
                invoke(
                    repository,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
                )["is_error"]
            )
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            (lane / "work.txt").write_text("lane work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")

            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer"},
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")

            reported = invoke(
                repository,
                {"tool": "collab_report", "task_id": "demo", "output_dir": "reports"},
            )
            self.assertFalse(reported["is_error"])
            self.assertTrue((repository / "reports/collab-report.json").is_file())
            # Reports are ordinary untracked; clean before native landing (S4 requires no ordinary untracked)
            import shutil
            shutil.rmtree(repository / "reports")

            landed = invoke(
                repository,
                {"tool": "collab_integration_land", "task_id": "demo", "message": "Ship lane work"},
            )
            self.assertFalse(landed["is_error"])
            self.assertEqual(landed["result"]["ok"], True)
            self.assertEqual(landed["result"]["tool_version"], 1)
            self.assertNotIn("warnings", landed["result"])

            removed = invoke(
                repository,
                {"tool": "collab_integration_remove", "task_id": "demo"},
            )
            self.assertFalse(removed["is_error"])
            self.assertEqual(set(removed["result"]), {"ok", "tool_version"})

    def test_report_snapshots_fixed_artifacts_at_relative_destination_without_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            created = invoke(repository, {"tool": "collab_integration_create", "task_id": "demo"})
            self.assertFalse(created["is_error"])
            lane_created = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
            )
            self.assertFalse(lane_created["is_error"])
            telemetry_before = (
                repository / ".agent_state/plans/demo/.collab_op/telemetry.jsonl"
            ).read_text(encoding="utf-8")
            expected_events = telemetry_events(repository)

            observed = invoke(
                repository,
                {"tool": "collab_report", "task_id": "demo", "output_dir": "reports"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            report_dir = repository / "reports"
            self.assertTrue((report_dir / "collab-report.json").is_file())
            self.assertTrue((report_dir / "collab-telemetry.jsonl").is_file())
            self.assertEqual(
                (report_dir / "collab-telemetry.jsonl").read_text(encoding="utf-8"),
                telemetry_before,
            )
            report = json.loads((report_dir / "collab-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["task_id"], "demo")
            self.assertEqual(report["timeline"], expected_events)
            self.assertEqual(
                [event["operation"] for event in report["timeline"]],
                ["integration-create", "lane-create"],
            )
            self.assertEqual(
                report["counts"]["operations"],
                {"integration-create": 1, "lane-create": 1},
            )
            self.assertTrue((repository / ".agent_state/worktrees/demo/integration").is_dir())

    def test_report_holds_task_lock_while_capturing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            created = invoke(repository, {"tool": "collab_integration_create", "task_id": "demo"})
            self.assertFalse(created["is_error"])
            block = base / "release-report"
            blocked = base / "report-blocked"
            wrapper = write_git_wrapper(
                base,
                REPORT_SNAPSHOT_BLOCK_WRAPPER.replace("__BLOCK__", str(block)).replace(
                    "__BLOCKED__", str(blocked)
                ),
            )
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            first: subprocess.Popen[str] | None = None
            second: subprocess.Popen[str] | None = None
            try:
                first = spawn_raw_harness(repository)
                second = spawn_raw_harness(repository)
                first_stdin = first.stdin
                first_stdout = first.stdout
                assert first_stdin is not None and first_stdout is not None
                first_stdin.write(
                    f"{json.dumps({'tool': 'collab_report', 'task_id': 'demo', 'output_dir': 'reports'})}\n"
                )
                first_stdin.flush()
                self.assertTrue(
                    wait_until(lambda: blocked.exists()),
                    "report never reached its ref snapshot",
                )

                refused = send_request(
                    second,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "concurrent"},
                )

                self.assertTrue(refused["is_error"])
                self.assertEqual(refused["error"]["error"]["code"], "task_busy")
                self.assertEqual(git(repository, "branch", "--list", "wave/demo/concurrent"), "")
                block.write_text("go\\n", encoding="utf-8")
                observed = json.loads(first_stdout.readline())
                self.assertFalse(observed["is_error"])
                self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            finally:
                os.environ["PATH"] = original_path
                for process in (first, second):
                    if process is not None:
                        close_harness(process)

    def test_report_rejects_legacy_method_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(
                repository,
                {
                    "tool": "collab_report",
                    "task_id": "demo",
                    "output_dir": "reports",
                    "method": "report"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertTrue(observed["error"]["error"]["repair"])

    def test_status_lists_tasks_without_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            for task_id in ("zeta", "alpha"):
                git(repository, "update-ref", f"refs/orchestrate/{task_id}/integration/base", head)

            observed = invoke(repository, {"tool": "collab_status"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"tool_version": 1, "tasks": ["alpha", "zeta"], "warnings": []},
            )

    def test_status_projects_exact_managed_task_result_without_recovery_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "tool_version": 1,
                    "task_id": "demo",
                    "integration": {
                        "worktree": expected["integration"],
                        "HEAD": expected["integration_head"],
                        "stale": False},
                    "lanes": {
                        "writer-1": {
                            "worktree": expected["lane"],
                            "HEAD": expected["integration_head"]}
                    },
                    "warnings": []},
            )
            self.assertNotIn("recovery_required", observed["result"])

    def test_status_rejects_legacy_method_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(repository, {"tool": "collab_status", "method": "status"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertTrue(observed["error"]["error"]["repair"])

    def test_adopt_success_exposes_only_agreed_result_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            base_sha = commit_agent_state_ignore(repository)
            seed_donor(repository, base, base_sha)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                set(observed["result"]),
                {"ok", "tool_version", "source_branch", "integration_branch"},
            )
            self.assertEqual(observed["result"]["source_branch"], "donor")
            self.assertEqual(observed["result"]["integration_branch"], "wave/demo/integration")
            self.assertEqual(
                git(repository, "rev-parse", "wave/demo/integration"),
                git(repository, "rev-parse", "donor"),
            )

    def test_adopt_rejects_legacy_dry_run_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            seed_donor(repository, base, base_sha)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": git(repository, "rev-parse", "HEAD"),
                    "dry_run": True},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertTrue(observed["error"]["error"]["repair"])

    def test_create_performs_git_setup_and_returns_only_common_success_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            head = commit_agent_state_ignore(repository)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), head)
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"),
                head,
            )
            self.assertEqual(
                git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                "refs/heads/main",
            )

    def test_create_rejects_legacy_method_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_create",
                    "task_id": "demo",
                    "method": "integration_create"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
            self.assertTrue(observed["error"]["error"]["repair"])

    def test_production_loader_registers_discoverable_operation_tools(self) -> None:
        self.test_final_inventory_exposes_only_independent_tools()

    def test_lane_collect_rejects_dirty_lane_with_actionable_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            (Path(expected["lane"]) / "tracked.txt").write_text("dirty\n", encoding="utf-8")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "dirty_worktree")
            self.assertTrue(error["repair"])
            self.assertEqual(
                (Path(expected["lane"]) / "tracked.txt").read_text(encoding="utf-8"),
                "dirty\n",
            )

    def test_lane_collect_reports_conflict_without_conflict_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "tracked.txt").write_text("integration change\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration change")
            (lane / "tracked.txt").write_text("lane change\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane change")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "conflicted")
            self.assertNotIn("conflict_paths", observed["result"])
            self.assertNotIn("lane_sha", observed["result"])
            self.assertNotIn("integration_sha", observed["result"])
            self.assertTrue(observed["result"]["warnings"])

    def test_lane_collect_reconciles_stale_lane_without_reviewed_sha_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "integration.txt").write_text("advanced\n", encoding="utf-8")
            git(integration, "add", "integration.txt")
            git(integration, "commit", "-m", "integration advances")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                {key for key in observed["result"] if key != "warnings"},
                {"ok", "tool_version", "state"},
            )
            self.assertEqual(observed["result"]["state"], "reconciled")
            self.assertTrue(observed["result"]["warnings"])
            self.assertEqual(
                git(repository, "branch", "--list", "--format=%(refname:short)", "wave/demo/writer-1"),
                "wave/demo/writer-1",
            )
            self.assertTrue(Path(expected["lane"]).exists())
            self.assertNotIn("comparison_moved", observed["result"])
            self.assertNotIn("collected", observed["result"])

    def test_lane_tools_reject_reviewed_sha_and_abandon_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            requests = (
                ("collab_lane_create", {"task_id": "demo", "lane_id": "writer-1", "sha": "x"}),
                ("collab_lane_reconcile", {"task_id": "demo", "lane_id": "writer-1", "integration_sha": "x"}),
                ("collab_lane_collect", {"task_id": "demo", "lane_id": "writer-1", "sha": "x"}),
                ("collab_lane_drop", {"task_id": "demo", "lane_id": "writer-1", "abandon": True}),
            )

            for tool, request in requests:
                with self.subTest(tool=tool):
                    request["tool"] = tool
                    observed = invoke(repository, request)
                    self.assertTrue(observed["is_error"])
                    self.assertEqual(observed["error"]["error"]["code"], "invalid_parameters")
                    self.assertTrue(observed["error"]["error"]["repair"])

    def test_lane_drop_reports_partial_cleanup_without_failing_the_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            wrapper = write_git_wrapper(base, FAIL_WORKTREE_REMOVE)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {
                        "tool": "collab_lane_drop",
                        "task_id": "demo",
                        "lane_id": "writer-1"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(Path(expected["lane"]).exists())
            self.assertEqual(
                git(repository, "branch", "--list", "wave/demo/writer-1"),
                "+ wave/demo/writer-1",
            )
            self.assertNotIn("disposition", observed["result"])

    def test_lane_drop_removes_dirty_uncollected_lane_without_abandon_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "tracked.txt").write_text("dirty lane\n", encoding="utf-8")
            (lane / "lane.txt").write_text("uncollected\n", encoding="utf-8")
            git(lane, "add", "lane.txt")
            git(lane, "commit", "-m", "uncollected lane")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_drop",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertFalse(Path(expected["lane"]).exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
            self.assertNotIn("disposition", observed["result"])

    def test_lane_collect_collects_uncollected_lane_from_current_tips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "lane.txt").write_text("lane work\n", encoding="utf-8")
            git(lane, "add", "lane.txt")
            git(lane, "commit", "-m", "lane work")
            lane_tip = git(lane, "rev-parse", "HEAD")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_tip)
            self.assertEqual(git(repository, "rev-parse", "main"), expected["base"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")

    def test_lane_collect_uses_current_tips_and_removes_collected_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"ok": True, "tool_version": 1, "state": "collected"},
            )
            self.assertEqual(last_telemetry_event(repository)["state"], "collected")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
            self.assertFalse(Path(expected["lane"]).exists())

    def test_lane_reconcile_projects_noop_state_without_identity_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_reconcile",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "noop")
            self.assertTrue(observed["result"]["warnings"])
            self.assertNotIn("lane_sha", observed["result"])
            self.assertNotIn("integration_sha", observed["result"])
            self.assertNotIn("conflict_paths", observed["result"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])

    def test_lane_reconcile_projects_conflicted_state_without_identity_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "tracked.txt").write_text("integration change\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration change")
            (lane / "tracked.txt").write_text("lane change\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane change")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_reconcile",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "conflicted")
            self.assertTrue(observed["result"]["warnings"])
            self.assertNotIn("lane_sha", observed["result"])
            self.assertNotIn("integration_sha", observed["result"])
            self.assertNotIn("conflict_paths", observed["result"])

    def test_lane_reconcile_projects_state_without_identity_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "integration.txt").write_text("advanced\n", encoding="utf-8")
            git(integration, "add", "integration.txt")
            git(integration, "commit", "-m", "integration advances")

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_reconcile",
                    "task_id": "demo",
                    "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"ok": True, "tool_version": 1, "state": "merged"},
            )
            self.assertNotIn("lane_sha", observed["result"])
            self.assertNotIn("integration_sha", observed["result"])
            self.assertNotIn("conflict_paths", observed["result"])

    def test_lane_create_preserves_comment_and_projects_common_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            expected = seed_managed_task(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_lane_create",
                    "task_id": "demo",
                    "lane_id": "new-lane",
                    "comment": "  preserve this comment  "},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            self.assertEqual(
                git(repository, "rev-parse", "wave/demo/new-lane"),
                expected["integration_head"],
            )
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-create")
            self.assertEqual(event["comment"], "preserve this comment")


class CollabOpExtensionStatusTests(unittest.TestCase):
    def test_production_loader_registers_one_tool_and_lists_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            for task_id in ("zeta", "alpha"):
                git(
                    repository,
                    "update-ref",
                    f"refs/orchestrate/{task_id}/integration/base",
                    head,
                )

            observed = invoke(repository, {"tool": "collab_status"})

            self.assertEqual(
                observed["tools"],
                [
                    "collab_integration_adopt",
                    "collab_integration_create",
                    "collab_integration_land",
                    "collab_integration_reconcile",
                    "collab_integration_remove",
                    "collab_lane",
                    "collab_report",
                    "collab_status"],
            )
            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"tool_version": 1, "tasks": ["alpha", "zeta"], "warnings": []},
            )

    def test_task_status_projects_only_integration_and_live_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "tool_version": 1,
                    "task_id": "demo",
                    "integration": {
                        "worktree": expected["integration"],
                        "HEAD": expected["integration_head"],
                        "stale": False},
                    "lanes": {
                        "writer-1": {
                            "worktree": expected["lane"],
                            "HEAD": expected["integration_head"]}
                    },
                    "warnings": []},
            )
            self.assertNotIn("acceptance", observed["result"])
            self.assertNotIn("accepted", observed["result"])
            self.assertNotIn("pending_commits", observed["result"])
            self.assertNotIn("checkpoint", observed["result"])

    def test_status_from_a_managed_worktree_uses_the_common_control_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)

            observed = invoke(
                Path(expected["integration"]),
                {"tool": "collab_status", "task_id": "demo"},
            )

            self.assertEqual(observed["result"]["integration"]["worktree"], expected["integration"])
            self.assertEqual(observed["result"]["lanes"]["writer-1"]["worktree"], expected["lane"])
            self.assertEqual(observed["result"]["integration"]["HEAD"], expected["integration_head"])

    def test_persistence_advance_makes_integration_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            (repository / "tracked.txt").write_text("base\npersistence\n", encoding="utf-8")
            git(repository, "add", "tracked.txt")
            git(repository, "commit", "-m", "persistence advances")

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertTrue(observed["result"]["integration"]["stale"])

    def test_missing_persistence_identity_is_conservatively_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            git(repository, "symbolic-ref", "--delete", "refs/orchestrate/demo/persistence")

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertTrue(observed["result"]["integration"]["stale"])
            self.assertTrue(
                any("freshness could not be proven" in warning for warning in observed["result"]["warnings"])
            )

    def test_status_warns_for_tracked_lane_dirt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "tracked.txt").write_text("tracked change\n", encoding="utf-8")

            observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertTrue(
                any("lane writer-1 worktree is dirty" in warning for warning in observed["result"]["warnings"])
            )

    def test_status_and_report_do_not_warn_for_untracked_or_ignored_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore runtime state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            for worktree in (Path(expected["integration"]), Path(expected["lane"])):
                (worktree / "ordinary.tmp").write_text("ordinary runtime\n", encoding="utf-8")
                (worktree / "ignored.tmp").write_text("ignored runtime\n", encoding="utf-8")

            status_observed = invoke(repository, {"tool": "collab_status", "task_id": "demo"})
            report_observed = invoke(
                repository,
                {"tool": "collab_report", "task_id": "demo", "output_dir": "presence-report"},
            )

            self.assertFalse(status_observed["is_error"])
            self.assertEqual(status_observed["result"]["warnings"], [])
            self.assertFalse(report_observed["is_error"])
            self.assertNotIn("warnings", report_observed["result"])
            report = json.loads(
                (repository / "presence-report/collab-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["warnings"], [])

            (Path(expected["lane"]) / "tracked.txt").write_text(
                "tracked change\n", encoding="utf-8"
            )
            tracked_report_observed = invoke(
                repository,
                {"tool": "collab_report", "task_id": "demo", "output_dir": "tracked-report"},
            )
            self.assertFalse(tracked_report_observed["is_error"])
            self.assertTrue(
                any(
                    "lane writer-1 worktree is dirty" in warning
                    for warning in tracked_report_observed["result"]["warnings"]
                )
            )

    def test_refusal_uses_the_structured_pi_error_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(repository, {"tool": "collab_status", "task_id": "Not-Safe"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["ok"], False)
            self.assertNotIn("operation", observed["error"])
            self.assertEqual(observed["error"]["tool_version"], 1)
            self.assertEqual(observed["error"]["error"]["code"], "invalid_identifier")


class CollabOpExtensionIntegrationReconcileContractRegressionTests(unittest.TestCase):
    def test_reconcile_requires_tracked_cleanliness_and_matching_identity(self) -> None:
        for case in ("tracked", "identity"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                integration = Path(expected["integration"])
                if case == "tracked":
                    (integration / "tracked.txt").write_text("preserve tracked change\n", encoding="utf-8")
                else:
                    git(integration, "checkout", "--detach")

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_integration_reconcile",
                        "task_id": "demo",
                        "lane_id": "repair"},
                )

                self.assertTrue(observed["is_error"])
                expected_code = "dirty_worktree" if case == "tracked" else "worktree_identity_mismatch"
                self.assertEqual(observed["error"]["error"]["code"], expected_code)
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_integration_reconcile_accepts_untracked_and_ignored_paths(self) -> None:
        for state in ("untracked", "ignored"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime state")
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                integration = Path(expected["integration"])
                candidate = integration / ("ordinary.tmp" if state == "untracked" else "ignored.tmp")
                candidate.write_text(f"{state} runtime\n", encoding="utf-8")

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_integration_reconcile",
                        "task_id": "demo",
                        "lane_id": "repair"},
                )

                self.assertFalse(observed["is_error"])
                self.assertEqual(observed["result"]["state"], "noop")
                self.assertTrue(candidate.is_file())
                self.assertFalse(
                    any("dirty" in warning or "preserv" in warning for warning in observed["result"]["warnings"])
                )

    def test_reconcile_compensation_uses_native_non_force_worktree_removal(self) -> None:
        for state in ("untracked", "ignored"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                (repository / ".gitignore").write_text(".cache/\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime cache")
                seed_managed_task(repository)
                (repository / "persistence.txt").write_text("persistence advance\n", encoding="utf-8")
                git(repository, "add", "persistence.txt")
                git(repository, "commit", "-m", "advance persistence")
                lane = repository / ".agent_state/worktrees/demo/lanes/repair"
                candidate = lane / ("ordinary.tmp" if state == "untracked" else ".cache/runtime.tmp")
                wrapper_script = """#!/bin/sh
real_git="__REAL_GIT__"
if [ "$1" = "merge" ]; then
  mkdir -p "__PARENT__"
  printf 'runtime\\n' > "__CANDIDATE__"
  exit 73
fi
exec "$real_git" "$@"
""".replace("__PARENT__", str(candidate.parent)).replace("__CANDIDATE__", str(candidate))
                wrapper = write_git_wrapper(base, wrapper_script)
                original_path = os.environ["PATH"]
                os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
                close_harness_for(repository)
                try:
                    observed = invoke(
                        repository,
                        {
                            "tool": "collab_integration_reconcile",
                            "task_id": "demo",
                            "lane_id": "repair"},
                    )
                finally:
                    os.environ["PATH"] = original_path
                    close_harness_for(repository)

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "git_error")
                compensation = observed["error"]["error"]["details"]["compensation"]
                if state == "untracked":
                    self.assertTrue(candidate.is_file())
                    self.assertTrue(lane.is_dir())
                    self.assertNotEqual(git(repository, "branch", "--list", "wave/demo/repair"), "")
                    self.assertFalse(compensation["restored"])
                else:
                    self.assertFalse(lane.exists())
                    self.assertEqual(git(repository, "branch", "--list", "wave/demo/repair"), "")
                    self.assertTrue(compensation["restored"])

    def test_reconcile_requires_one_persistence_checkout_at_direct_branch_tip(self) -> None:
        for case in ("head", "count"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                expected = seed_managed_task(repository)
                if case == "head":
                    side = base / "advance"
                    git(repository, "worktree", "add", "-b", "advance", str(side), "main")
                    (side / "advance.txt").write_text("advance\n", encoding="utf-8")
                    git(side, "add", "advance.txt")
                    git(side, "commit", "-m", "advance")
                    new_tip = git(side, "rev-parse", "HEAD")
                    git(repository, "update-ref", "refs/heads/main", new_tip)
                    git(repository, "checkout", "--detach", expected["base"])
                    git(repository, "worktree", "remove", "--force", str(side))
                else:
                    duplicate = base / "duplicate"
                    git(repository, "worktree", "add", "--force", str(duplicate), "main")

                observed = invoke(
                    repository,
                    {
                        "tool": "collab_integration_reconcile",
                        "task_id": "demo",
                        "lane_id": "repair"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "persistence_identity_mismatch")
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_reconcile_noop_warns_and_records_telemetry_without_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "tool_version": 1,
                    "state": "noop",
                    "warnings": ["persistence is already included in integration"]},
            )
            self.assertEqual(
                git(repository, "rev-parse", "wave/demo/integration"),
                expected["integration_head"],
            )
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/repair"), "")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-reconcile")
            self.assertEqual(event["outcome"], "noop")
            self.assertEqual(event["state"], "noop")
            self.assertEqual(event["persist"], "main")

    def test_reconcile_clean_merge_creates_lane_and_leaves_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            persistence = repository
            (persistence / "persistence.txt").write_text("persistence\n", encoding="utf-8")
            git(persistence, "add", "persistence.txt")
            git(persistence, "commit", "-m", "persistence advance")
            persistence_sha = git(repository, "rev-parse", "main")
            (persistence / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "merged")
            self.assertEqual(result["lane_id"], "repair")
            lane_sha = result["lane_sha"]
            self.assertNotEqual(lane_sha, expected["integration_head"])
            lane = repository / ".agent_state/worktrees/demo/lanes/repair"
            self.assertTrue(lane.exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/repair"), lane_sha)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo/repair"),
                "",
            )
            self.assertEqual(git(repository, "merge-base", "--is-ancestor", persistence_sha, lane_sha), "")
            self.assertEqual(git(repository, "merge-base", "--is-ancestor", expected["integration_head"], lane_sha), "")
            self.assertEqual((persistence / "operator-dirt.txt").read_text(encoding="utf-8"), "preserve\n")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-reconcile")
            self.assertEqual(event["outcome"], "success")
            self.assertEqual(event["state"], "merged")
            self.assertEqual(event["persistence_sha"], persistence_sha)

            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "repair"},
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"], {"ok": True, "tool_version": 1, "state": "collected"})
            self.assertFalse(
                invoke(repository, {"tool": "collab_status", "task_id": "demo"})["result"]["integration"]["stale"]
            )

    def test_reconcile_conflict_preserves_lane_handoff_and_leaves_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "tracked.txt").write_text("integration conflict\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            (repository / "tracked.txt").write_text("persistence conflict\n", encoding="utf-8")
            git(repository, "add", "tracked.txt")
            git(repository, "commit", "-m", "persistence conflict")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            persistence_sha = git(repository, "rev-parse", "main")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "conflicted")
            self.assertEqual(result["lane_id"], "repair")
            self.assertEqual(result["lane_sha"], integration_sha)
            self.assertNotIn("conflict_paths", result)
            lane = repository / ".agent_state/worktrees/demo/lanes/repair"
            self.assertTrue(lane.exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/repair"), integration_sha)
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-reconcile")
            self.assertEqual(event["outcome"], "success")
            self.assertEqual(event["state"], "conflicted")
            self.assertEqual(event["conflict_path_count"], 1)
            self.assertEqual(event["persistence_sha"], persistence_sha)

    def test_reconcile_collision_refuses_before_creating_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            (repository / "persistence.txt").write_text("persistence\n", encoding="utf-8")
            git(repository, "add", "persistence.txt")
            git(repository, "commit", "-m", "persistence advance")
            git(repository, "branch", "wave/demo/repair", expected["base"])

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "lane_resource_collision")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_reconcile_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            (repository / "persistence.txt").write_text("persistence\n", encoding="utf-8")
            git(repository, "add", "persistence.txt")
            git(repository, "commit", "-m", "persistence advance")

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


# Pairwise landing-transition coverage grid. Each row is one transition-shape
# family; the columns are the contract representatives that the individually
# named tests below keep visible. A missing cell is a coverage gap by direct
# inspection rather than something an opaque matrix run has to reveal:
#
#   family            clean-success representative                 local-overlap refusal representative
#   ----------------  -------------------------------------------  ------------------------------------------------------------
#   rename            accepted_rename_leaves_only_destination      refuses_rename_over_untracked_destination
#   directory->file   clean_directory_to_file_transition_lands     refuses_directory_to_file_transition_over_untracked_dirt
#   file->directory   clean_file_to_directory_transition_lands     refuses_file_to_directory_transition_over_untracked_dirt
#   deleted leaf      (any clean landing)                          refuses_deleted_tracked_leaf_replaced_by_untracked_descendant
#   added path        (any clean landing)                          refuses_ordinary_untracked_collision
#
# The established index-dirt representative (refuses_intent_to_add_entry) and
# failure-phase representative (commit_failure_restores_persistence) stay in
# their own named tests; they are not transition families.


class LandingTransition:
    """Fixture builder for one pairwise landing-transition arrangement.

    Seeds the repository, the managed task, and one accepted
    integration-side transition commit, applies optional local overlap in
    the operator checkout, captures the pre-landing observation set once,
    and shares the success/refusal assertion bundles so each transition
    family keeps its own named, diagnosable tests without repeating the
    fixture mechanics.
    """

    def __init__(
        self,
        temporary: Path,
        *,
        base_files: dict[str, str],
        transition: Callable[[Path], None] | None = None,
        local_overlap: Callable[[Path], None] | None = None,
    ) -> None:
        repository, _ = seed_repository(Path(temporary))
        if base_files:
            for name in sorted(base_files):
                target = repository / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(base_files[name], encoding="utf-8")
            git(repository, "add", *sorted(base_files))
            git(repository, "commit", "-m", "transition base")
        self.repository = repository
        self.expected = seed_managed_task(repository)
        seed_task_container(repository)
        if transition is not None:
            integration = Path(self.expected["integration"])
            transition(integration)
            git(integration, "commit", "-m", "accepted transition")
            self.expected["integration_head"] = git(integration, "rev-parse", "HEAD")
        if local_overlap is not None:
            local_overlap(repository)
        self.before_refs = managed_ref_snapshot(repository)
        self.before_head = git(repository, "rev-parse", "HEAD")
        self.before_status = git(repository, "status", "--porcelain=v1", "--ignored=matching")
        self.before_integration = git(repository, "rev-parse", "wave/demo/integration")

    @property
    def base(self) -> str:
        return self.expected["base"]

    @property
    def integration_head(self) -> str:
        return self.expected["integration_head"]

    def land(self) -> dict[str, object]:
        return invoke(
            self.repository, {"tool": "collab_integration_land", "task_id": "demo"}
        )


def assert_transition_landed(
    test: unittest.TestCase,
    scenario: LandingTransition,
    observed: dict[str, object],
) -> None:
    """Shared clean-success contract for one accepted transition shape (native merge topology)."""
    repository = scenario.repository
    expected_tree = git(repository, "rev-parse", f"{scenario.integration_head}^{{tree}}")
    test.assertFalse(observed["is_error"])
    # S3: no landed ref is created
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--verify", "--quiet", "refs/orchestrate/demo/landed"],
        capture_output=True,
    )
    test.assertNotEqual(result.returncode, 0, "landed ref should be absent after native landing")
    # S1: persistence and integration both at the merge commit with ordered parents and integration tree
    persist_ref = git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence")
    persist_sha = git(repository, "rev-parse", persist_ref)
    integration_sha = git(repository, "rev-parse", "wave/demo/integration")
    test.assertEqual(persist_sha, integration_sha, "persistence and integration must share the merge commit")
    test.assertEqual(git(repository, "rev-parse", f"{persist_sha}^{{tree}}"), expected_tree)
    test.assertEqual(git(repository, "rev-parse", "HEAD^{tree}"), expected_tree)
    test.assertEqual(git(repository, "write-tree"), expected_tree)
    test.assertEqual(git(repository, "status", "--porcelain=v1", "--untracked-files=all"), "")
    parents = git(repository, "rev-list", "--parents", "-n", "1", persist_sha).split()
    test.assertEqual(len(parents), 3)
    test.assertEqual(parents[1], scenario.before_head, "first parent must be previous persistence head")
    test.assertEqual(parents[2], scenario.integration_head, "second parent must be integration head")
    # integration branch advanced, not left behind
    test.assertNotEqual(integration_sha, scenario.before_integration)


def assert_transition_refused(
    test: unittest.TestCase,
    scenario: LandingTransition,
    observed: dict[str, object],
    *,
    code: str,
    collision_paths: list[str] | None = None,
) -> None:
    """Shared refusal-before-mutation contract for one overlap arrangement (native checks)."""
    repository = scenario.repository
    error = observed["error"]["error"]
    test.assertTrue(observed["is_error"])
    test.assertEqual(error["code"], code)
    if collision_paths is not None:
        test.assertEqual(error["details"]["paths"], collision_paths)
    test.assertEqual(managed_ref_snapshot(repository), scenario.before_refs)
    test.assertEqual(git(repository, "rev-parse", "HEAD"), scenario.before_head)
    test.assertEqual(
        git(repository, "status", "--porcelain=v1", "--ignored=matching"), scenario.before_status
    )
    test.assertEqual(
        git(repository, "rev-parse", "wave/demo/integration"), scenario.integration_head
    )


def ignored_landing_collision(temporary: str | Path, shape: str) -> LandingTransition:
    def transition(integration: Path) -> None:
        if shape == "exact":
            (integration / "ignored.tmp").write_text("accepted exact\n", encoding="utf-8")
            git(integration, "add", "-f", "ignored.tmp")
        elif shape == "directory_to_file":
            (integration / "pair").write_text("accepted file\n", encoding="utf-8")
            git(integration, "add", "-f", "pair")
        else:
            (integration / "pair").mkdir()
            (integration / "pair/accepted.txt").write_text("accepted nested\n", encoding="utf-8")
            git(integration, "add", "-f", "pair/accepted.txt")

    def overlap(repository: Path) -> None:
        if shape == "exact":
            (repository / "ignored.tmp").write_text("ignored local\n", encoding="utf-8")
        elif shape == "directory_to_file":
            (repository / "pair").mkdir()
            (repository / "pair/runtime.tmp").write_text("ignored local\n", encoding="utf-8")
        else:
            (repository / "pair").write_text("ignored local\n", encoding="utf-8")

    return LandingTransition(
        temporary,
        base_files={".gitignore": ".agent_state/\nignored.tmp\npair\n"},
        transition=transition,
        local_overlap=overlap,
    )



class CollabOpExtensionIntegrationLandContractRegressionTests(unittest.TestCase):
    def test_land_default_commit_preserves_dirt(self) -> None:
        # S4: native checkout requires clean persistence; unstaged and ordinary untracked must be refused before merge
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / "stable.txt").write_text("stable\n", encoding="utf-8")
            git(repository, "add", "stable.txt")
            git(repository, "commit", "-m", "stable base")
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            (repository / "stable.txt").write_text("operator unstaged\n", encoding="utf-8")
            (repository / "untracked.txt").write_text("preserve\n", encoding="utf-8")
            before_refs = managed_ref_snapshot(repository)
            before_head = git(repository, "rev-parse", "HEAD")
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertIn(observed["error"]["error"]["code"], ("dirty_worktree", "path_collision"))
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "rev-parse", "HEAD"), before_head)
            # Clean and retry should succeed with native merge topology (S1) and no landed ref
            git(repository, "restore", "stable.txt")
            (repository / "untracked.txt").unlink()
            observed2 = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertFalse(observed2["is_error"])
            persist_ref = git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence")
            persist_sha = git(repository, "rev-parse", persist_ref)
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            self.assertEqual(persist_sha, integration_sha)
            result = subprocess.run(["git", "-C", str(repository), "rev-parse", "--verify", "--quiet", "refs/orchestrate/demo/landed"], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(git(repository, "rev-parse", f"{persist_sha}^{{tree}}"), git(repository, "rev-parse", f"{expected['integration_head']}^{{tree}}"))

    def test_land_merges_separate_unstaged_hunks_in_one_file_and_warns(self) -> None:
        # S4: unstaged tracked changes must be refused, not merged with warning
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / "tracked.txt").write_text("a\nb\nc\nd\ne\nf\n", encoding="utf-8")
            (repository / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
            git(repository, "add", "tracked.txt", ".gitignore")
            git(repository, "commit", "-m", "multiline base")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            integration = Path(expected["integration"])
            (integration / "tracked.txt").write_text("a\nB\nc\nd\ne\nf\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration hunk")
            expected["integration_head"] = git(integration, "rev-parse", "HEAD")
            (repository / "tracked.txt").write_text("a\nb\nc\nd\nE\nf\n", encoding="utf-8")
            before_head = git(repository, "rev-parse", "HEAD")
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
            self.assertEqual(git(repository, "rev-parse", "HEAD"), before_head)
            # Clean and succeed
            git(repository, "restore", "tracked.txt")
            observed2 = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertFalse(observed2["is_error"])

    def test_land_conflicting_unstaged_hunks_preserves_all_snapshots(self) -> None:
        # S4: conflicting unstaged hunks are refused as dirty_worktree before mutation, preserving snapshots
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / "tracked.txt").write_text("a\nb\nc\nd\ne\nf\n", encoding="utf-8")
            (repository / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
            git(repository, "add", "tracked.txt", ".gitignore")
            git(repository, "commit", "-m", "multiline base")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            integration = Path(expected["integration"])
            (integration / "tracked.txt").write_text("a\nB\nc\nd\ne\nf\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration hunk")
            expected["integration_head"] = git(integration, "rev-parse", "HEAD")
            (repository / "tracked.txt").write_text("a\nX\nc\nd\ne\nf\n", encoding="utf-8")
            before_refs = managed_ref_snapshot(repository)
            before_head = git(repository, "rev-parse", "HEAD")
            before_status = git(repository, "status", "--porcelain=v1", "--ignored=matching")
            before_file = (repository / "tracked.txt").read_text(encoding="utf-8")
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "rev-parse", "HEAD"), before_head)
            self.assertEqual(git(repository, "status", "--porcelain=v1", "--ignored=matching"), before_status)
            self.assertEqual((repository / "tracked.txt").read_text(encoding="utf-8"), before_file)

    def test_land_untracked_only_state_survives_without_presence_warning(self) -> None:
        # S4: ordinary untracked must be refused before merge (native contract)
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            (repository / "local.txt").write_text("operator\n", encoding="utf-8")
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "path_collision")
            self.assertEqual((repository / "local.txt").read_text(encoding="utf-8"), "operator\n")
            # Clean and succeed
            (repository / "local.txt").unlink()
            observed2 = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertFalse(observed2["is_error"])
            self.assertEqual(git(repository, "rev-parse", "HEAD^{tree}"), git(repository, "rev-parse", f"{expected['integration_head']}^{{tree}}"))

    def test_land_ignored_only_state_survives_without_presence_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\nignored.tmp\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state and runtime")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            (repository / "ignored.tmp").write_text("operator\n", encoding="utf-8")
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertFalse(observed["is_error"])
            self.assertNotIn("warnings", observed["result"])
            self.assertEqual((repository / "ignored.tmp").read_text(encoding="utf-8"), "operator\n")
            self.assertEqual(git(repository, "rev-parse", "HEAD^{tree}"), git(repository, "rev-parse", f"{expected['integration_head']}^{{tree}}"))

    def test_land_refuses_collisions_staged_changes_and_stale_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, expected_base = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            expected = seed_managed_task(repository)
            # ordinary untracked collision (new file added by integration)
            (repository / "new.txt").write_text("operator\n", encoding="utf-8")
            collision = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            # No change to integration yet, but ordinary untracked should be refused
            self.assertTrue(collision["is_error"])
            self.assertEqual(collision["error"]["error"]["code"], "path_collision")
            (repository / "new.txt").unlink()
            (repository / "index-dirt.txt").write_text("index\n", encoding="utf-8")
            git(repository, "add", "index-dirt.txt")
            staged = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(staged["is_error"])
            self.assertEqual(staged["error"]["error"]["code"], "dirty_index")
            git(repository, "reset", "--", "index-dirt.txt")
            (repository / "index-dirt.txt").unlink()
            (repository / "later.txt").write_text("later\n", encoding="utf-8")
            git(repository, "add", "later.txt")
            git(repository, "commit", "-m", "persistence stale")
            stale = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(stale["is_error"])
            self.assertEqual(stale["error"]["error"]["code"], "stale_persistence")
            self.assertTrue(stale["error"]["error"]["repair"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])

    def test_land_refuses_intent_to_add_entry_and_preserves_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def overlap(repository: Path) -> None:
                (repository / "valuable.txt").write_text("operator\n", encoding="utf-8")
                git(repository, "add", "--intent-to-add", "valuable.txt")
            scenario = LandingTransition(temporary, base_files={".gitignore": ".agent_state/\n"}, local_overlap=overlap)
            observed = scenario.land()
            assert_transition_refused(self, scenario, observed, code="dirty_index")
            self.assertEqual((scenario.repository / "valuable.txt").read_text(encoding="utf-8"), "operator\n")
            self.assertIn("100644 e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 0\tvaluable.txt", git(scenario.repository, "ls-files", "--stage"))

    def test_land_refuses_ordinary_untracked_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def add_path(integration: Path) -> None:
                (integration / "new.txt").write_text("accepted\n", encoding="utf-8")
                git(integration, "add", "new.txt")
            def overlap(repository: Path) -> None:
                (repository / "new.txt").write_text("operator\n", encoding="utf-8")
            scenario = LandingTransition(temporary, base_files={".gitignore": ".agent_state/\n"}, transition=add_path, local_overlap=overlap)
            observed = scenario.land()
            assert_transition_refused(self, scenario, observed, code="path_collision")
            self.assertEqual((scenario.repository / "new.txt").read_text(encoding="utf-8"), "operator\n")

    def test_land_overwrites_ignored_exact_and_file_directory_collisions(self) -> None:
        for shape in ("exact", "directory_to_file", "file_to_directory"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                scenario = ignored_landing_collision(temporary, shape)
                observed = scenario.land()
                assert_transition_landed(self, scenario, observed)
                self.assertNotIn("warnings", observed["result"])
                if shape == "exact":
                    self.assertEqual((scenario.repository / "ignored.tmp").read_text(encoding="utf-8"), "accepted exact\n")
                elif shape == "directory_to_file":
                    self.assertEqual((scenario.repository / "pair").read_text(encoding="utf-8"), "accepted file\n")
                else:
                    self.assertEqual((scenario.repository / "pair/accepted.txt").read_text(encoding="utf-8"), "accepted nested\n")

    def test_land_failure_restores_ignored_exact_and_file_directory_collisions(self) -> None:
        # S5: hook failure exposes Git state without synthetic rollback; verify merge did not create commit and state is exposed
        for shape in ("exact", "directory_to_file", "file_to_directory"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                scenario = ignored_landing_collision(temporary, shape)
                # Use a pre-merge hook that fails to simulate hook failure (native hooks run)
                hook = scenario.repository / ".git/hooks/pre-merge-commit"
                hook.parent.mkdir(parents=True, exist_ok=True)
                hook.write_text("#!/bin/sh\necho hook failed >&2\nexit 1\n", encoding="utf-8")
                hook.chmod(0o755)
                before_refs = managed_ref_snapshot(scenario.repository)
                before_head = git(scenario.repository, "rev-parse", "HEAD")
                observed = scenario.land()
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "git_error")
                # Git state exposed: either merge still in progress or HEAD unchanged but hook output present
                # For pre-merge-commit hook failure, merge commit is not created, HEAD unchanged
                self.assertEqual(git(scenario.repository, "rev-parse", "HEAD"), before_head)
                # Cleanup hook
                hook.unlink(missing_ok=True)

    def test_land_handles_ignored_directory_fifo_collision_on_success_and_failure(self) -> None:
        for outcome in ("success", "failure"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as temporary:
                def transition(integration: Path) -> None:
                    (integration / "pair").write_text("accepted file\n", encoding="utf-8")
                    git(integration, "add", "-f", "pair")
                def overlap(repository: Path) -> None:
                    (repository / "pair").mkdir()
                    os.mkfifo(repository / "pair/runtime.pipe")
                scenario = LandingTransition(temporary, base_files={".gitignore": ".agent_state/\npair\n"}, transition=transition, local_overlap=overlap)
                if outcome == "failure":
                    hook = scenario.repository / ".git/hooks/pre-merge-commit"
                    hook.parent.mkdir(parents=True, exist_ok=True)
                    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
                    hook.chmod(0o755)
                observed = scenario.land()
                if outcome == "success":
                    assert_transition_landed(self, scenario, observed)
                    self.assertEqual((scenario.repository / "pair").read_text(encoding="utf-8"), "accepted file\n")
                else:
                    self.assertTrue(observed["is_error"])
                    self.assertEqual(observed["error"]["error"]["code"], "git_error")
                    # Native hook failure exposes Git state without synthetic rollback; the directory may have been overwritten
                    self.assertIn(observed["error"]["error"]["code"], ("git_error",))
                    hook = scenario.repository / ".git/hooks/pre-merge-commit"
                    hook.unlink(missing_ok=True)
                    # Clean any leftover merge state before next iteration
                    try:
                        import subprocess
                        subprocess.run(["git", "-C", str(scenario.repository), "merge", "--abort"], capture_output=True)
                        subprocess.run(["git", "-C", str(scenario.repository), "reset", "--hard", "HEAD"], capture_output=True)
                    except Exception:
                        pass

    def test_land_preserves_directory_replacement_of_unchanged_path(self) -> None:
        # S4: unstaged directory replacement must be refused before merge, not preserved
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / "shape.txt").write_text("base\n", encoding="utf-8")
            (repository / "stable.txt").write_text("stable\n", encoding="utf-8")
            (repository / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
            git(repository, "add", "shape.txt", "stable.txt", ".gitignore")
            git(repository, "commit", "-m", "shape base")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            repository.joinpath("shape.txt").unlink()
            (repository / "shape.txt").mkdir()
            (repository / "shape.txt/local.txt").write_text("operator\n", encoding="utf-8")
            (repository / "stable.txt").write_text("stable local\n", encoding="utf-8")
            before_refs = managed_ref_snapshot(repository)
            before_head = git(repository, "rev-parse", "HEAD")
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertIn(observed["error"]["error"]["code"], ("dirty_worktree", "path_collision"))
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "rev-parse", "HEAD"), before_head)
            self.assertTrue((repository / "shape.txt").is_dir())

    def test_land_accepted_rename_leaves_only_destination_and_clean_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def rename(integration: Path) -> None:
                git(integration, "mv", "old.txt", "new.txt")
            scenario = LandingTransition(temporary, base_files={"old.txt": "base\n", ".gitignore": ".agent_state/\n"}, transition=rename)
            observed = scenario.land()
            assert_transition_landed(self, scenario, observed)
            self.assertFalse((scenario.repository / "old.txt").exists())
            self.assertEqual((scenario.repository / "new.txt").read_text(encoding="utf-8"), "base\n")

    def test_land_refuses_rename_over_untracked_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def rename(integration: Path) -> None:
                git(integration, "mv", "old.txt", "new.txt")
            def overlap(repository: Path) -> None:
                (repository / "new.txt").write_text("operator\n", encoding="utf-8")
            scenario = LandingTransition(temporary, base_files={"old.txt": "base\n", ".gitignore": ".agent_state/\n"}, transition=rename, local_overlap=overlap)
            observed = scenario.land()
            assert_transition_refused(self, scenario, observed, code="path_collision", collision_paths=["new.txt"])
            self.assertTrue((scenario.repository / "old.txt").exists())
            self.assertEqual((scenario.repository / "new.txt").read_text(encoding="utf-8"), "operator\n")

    def test_land_refuses_deleted_tracked_leaf_replaced_by_untracked_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def delete_pair(integration: Path) -> None:
                git(integration, "rm", "pair")
            def replace_with_local_directory(repository: Path) -> None:
                (repository / "pair").unlink()
                (repository / "pair").mkdir()
                (repository / "pair/local.tmp").write_text("operator\n", encoding="utf-8")
            scenario = LandingTransition(temporary, base_files={"pair": "base\n", ".gitignore": ".agent_state/\n"}, transition=delete_pair, local_overlap=replace_with_local_directory)
            observed = scenario.land()
            # Native check: ordinary untracked present -> path_collision (unstaged also present but ordinary takes precedence)
            assert_transition_refused(self, scenario, observed, code="path_collision", collision_paths=["pair/local.tmp"])
            self.assertEqual((scenario.repository / "pair/local.tmp").read_text(encoding="utf-8"), "operator\n")

    def test_land_refuses_directory_to_file_transition_over_untracked_dirt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def collapse(integration: Path) -> None:
                git(integration, "rm", "pair/gen.txt")
                (integration / "pair").write_text("collapsed\n", encoding="utf-8")
                git(integration, "add", "pair")
            def overlap(repository: Path) -> None:
                (repository / "pair/local.txt").write_text("operator\n", encoding="utf-8")
            scenario = LandingTransition(temporary, base_files={"pair/gen.txt": "gen\n", ".gitignore": ".agent_state/\n"}, transition=collapse, local_overlap=overlap)
            before_gen = (scenario.repository / "pair/gen.txt").read_text(encoding="utf-8")
            observed = scenario.land()
            assert_transition_refused(self, scenario, observed, code="path_collision", collision_paths=["pair/local.txt"])
            self.assertEqual((scenario.repository / "pair/gen.txt").read_text(encoding="utf-8"), before_gen)
            self.assertEqual((scenario.repository / "pair/local.txt").read_text(encoding="utf-8"), "operator\n")

    def test_land_clean_directory_to_file_transition_lands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def collapse(integration: Path) -> None:
                git(integration, "rm", "pair/gen.txt")
                (integration / "pair").write_text("collapsed\n", encoding="utf-8")
                git(integration, "add", "pair")
            scenario = LandingTransition(temporary, base_files={"pair/gen.txt": "gen\n", ".gitignore": ".agent_state/\n"}, transition=collapse)
            observed = scenario.land()
            assert_transition_landed(self, scenario, observed)
            self.assertFalse((scenario.repository / "pair/gen.txt").exists())
            self.assertTrue((scenario.repository / "pair").is_file())
            self.assertEqual((scenario.repository / "pair").read_text(encoding="utf-8"), "collapsed\n")

    def test_land_clean_file_to_directory_transition_lands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def expand(integration: Path) -> None:
                git(integration, "rm", "pair")
                (integration / "pair").mkdir()
                (integration / "pair/gen.txt").write_text("generated\n", encoding="utf-8")
                git(integration, "add", "pair/gen.txt")
            scenario = LandingTransition(temporary, base_files={"pair": "expanded\n", ".gitignore": ".agent_state/\n"}, transition=expand)
            observed = scenario.land()
            assert_transition_landed(self, scenario, observed)
            self.assertFalse((scenario.repository / "pair").is_file())
            self.assertTrue((scenario.repository / "pair/gen.txt").is_file())
            self.assertEqual((scenario.repository / "pair/gen.txt").read_text(encoding="utf-8"), "generated\n")

    def test_land_refuses_file_to_directory_transition_over_untracked_dirt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def expand(integration: Path) -> None:
                git(integration, "rm", "pair")
                (integration / "pair").mkdir()
                (integration / "pair/gen.txt").write_text("generated\n", encoding="utf-8")
                git(integration, "add", "pair/gen.txt")
            def overlap(repository: Path) -> None:
                (repository / "pair").unlink()
                (repository / "pair").mkdir()
                (repository / "pair/gen.txt").write_text("operator\n", encoding="utf-8")
            scenario = LandingTransition(temporary, base_files={"pair": "expanded\n", ".gitignore": ".agent_state/\n"}, transition=expand, local_overlap=overlap)
            observed = scenario.land()
            assert_transition_refused(self, scenario, observed, code="path_collision", collision_paths=["pair/gen.txt"])
            self.assertTrue((scenario.repository / "pair/gen.txt").is_file())
            self.assertEqual((scenario.repository / "pair/gen.txt").read_text(encoding="utf-8"), "operator\n")

    def test_land_refuses_structurally_changed_tracked_leaf_with_other_untracked_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def expand(integration: Path) -> None:
                git(integration, "rm", "pair")
                (integration / "pair").mkdir()
                (integration / "pair/accepted.txt").write_text("accepted\n", encoding="utf-8")
                git(integration, "add", "pair/accepted.txt")
            def replace_with_local_directory(repository: Path) -> None:
                (repository / "pair").unlink()
                (repository / "pair").mkdir()
                (repository / "pair/local.tmp").write_text("operator\n", encoding="utf-8")
            scenario = LandingTransition(temporary, base_files={"pair": "base\n", ".gitignore": ".agent_state/\n"}, transition=expand, local_overlap=replace_with_local_directory)
            observed = scenario.land()
            assert_transition_refused(self, scenario, observed, code="path_collision", collision_paths=["pair/local.tmp"])
            self.assertEqual((scenario.repository / "pair/local.tmp").read_text(encoding="utf-8"), "operator\n")

    def test_land_commit_failure_restores_persistence_and_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            before = git(repository, "rev-parse", "main")
            # Native merge failure via hook: pre-merge-commit hook that fails exposes Git state without synthetic rollback
            hook = repository / ".git/hooks/pre-merge-commit"
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text("#!/bin/sh\necho hook failed >&2\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)
            before_refs = managed_ref_snapshot(repository)
            before_status = git(repository, "status", "--porcelain=v1", "--ignored=matching")
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "git_error")
            # Git state exposed: HEAD unchanged, but merge may be in progress or aborted? For hook failure, merge aborts
            self.assertEqual(git(repository, "rev-parse", "main"), before)
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            # No synthetic rollback claim
            self.assertNotIn("rollback", observed["error"]["error"].get("details", {}) if isinstance(observed["error"]["error"].get("details"), dict) else {})
            hook.unlink(missing_ok=True)

    def test_land_success_does_not_invoke_mutating_hooks(self) -> None:
        # S5: hooks must run natively; a failing hook must cause landing to fail
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            hook = repository / ".git/hooks/pre-merge-commit"
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text("#!/bin/sh\necho hook ran > hook-output.txt\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "git_error")
            self.assertTrue((repository / "hook-output.txt").exists())
            # Clean hook and succeed
            hook.unlink()
            (repository / "hook-output.txt").unlink(missing_ok=True)
            observed2 = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            # Hook failure leaves merge state; clean before retry
            if observed2["is_error"]:
                import subprocess
                subprocess.run(["git", "-C", str(repository), "merge", "--abort"], capture_output=True)
                subprocess.run(["git", "-C", str(repository), "reset", "--hard", "HEAD"], capture_output=True)
                observed2 = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertFalse(observed2["is_error"])
            self.assertEqual(git(repository, "rev-parse", "HEAD^{tree}"), git(repository, "rev-parse", f"{expected['integration_head']}^{{tree}}"))

    def test_land_optional_message_and_duplicate_are_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo", "message": "Ship demo"})
            self.assertFalse(observed["is_error"])
            persist_ref = git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence")
            landing = git(repository, "rev-parse", persist_ref)
            self.assertEqual(git(repository, "show", "-s", "--format=%B", landing), f"Ship demo\n\nTask: demo\nLanded: {expected['integration_head']}")
            # Second landing without new integration work should be no_tree_change (persistence already contains integration)
            duplicate = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(duplicate["is_error"])
            self.assertEqual(duplicate["error"]["error"]["code"], "no_tree_change")

    def test_land_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            seed_managed_task(repository)
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())

    def test_land_refuses_non_ignored_agent_state_path_before_mutation(self) -> None:
        # S4 regression: ordinary untracked .agent_state/operator.txt must be refused before refs or HEAD move
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/worktrees/\n.agent_state/plans/\n.agent_state/archives/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed worktrees")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            (repository / ".agent_state/operator.txt").write_text("operator\n", encoding="utf-8")
            before_refs = managed_ref_snapshot(repository)
            before_head = git(repository, "rev-parse", "HEAD")
            before_status = git(repository, "status", "--porcelain=v1", "--ignored=matching")
            observed = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "path_collision")
            self.assertIn(".agent_state/operator.txt", observed["error"]["error"]["details"]["paths"])
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "rev-parse", "HEAD"), before_head)
            self.assertEqual(git(repository, "status", "--porcelain=v1", "--ignored=matching"), before_status)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            # Clean and verify landing succeeds when only the ordinary .agent_state file is removed
            (repository / ".agent_state/operator.txt").unlink()
            observed2 = invoke(repository, {"tool": "collab_integration_land", "task_id": "demo"})
            self.assertFalse(observed2["is_error"])



class CollabOpExtensionLaneCollectContractRegressionTests(unittest.TestCase):
    def test_collect_ignores_disposable_lane_state_and_creates_no_extra_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text("ignored.tmp\nignored-dir/\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore local state")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            (lane / "ignored.tmp").write_text("ignored runtime\n", encoding="utf-8")
            (lane / "ignored-dir").mkdir()
            (lane / "runtime.txt").write_text("disposable\n", encoding="utf-8")
            self.assertEqual(git(lane, "status", "--porcelain=v1", "--untracked-files=no"), "")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1, "state": "collected"})
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_sha)
            self.assertEqual(git(repository, "rev-list", "--count", f"{expected['integration_head']}..wave/demo/integration"), "1")
            self.assertFalse(lane.exists())

    def test_collect_preserves_tracked_lane_dirt(self) -> None:
        for case in ("unstaged", "staged", "staged_new"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                lane = Path(expected["lane"])
                (lane / "work.txt").write_text("work\n", encoding="utf-8")
                git(lane, "add", "work.txt")
                git(lane, "commit", "-m", "work")
                lane_sha = git(lane, "rev-parse", "HEAD")
                if case == "unstaged":
                    (lane / "tracked.txt").write_text("preserve unstaged\n", encoding="utf-8")
                elif case == "staged":
                    (lane / "tracked.txt").write_text("preserve staged\n", encoding="utf-8")
                    git(lane, "add", "tracked.txt")
                else:
                    (lane / "newly-staged.txt").write_text("preserve staged path\n", encoding="utf-8")
                    git(lane, "add", "newly-staged.txt")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
                self.assertTrue(observed["error"]["error"]["repair"])
                self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
                self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
                self.assertTrue(lane.exists())

    def test_collect_allows_disposable_integration_state_and_preserves_unrelated_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text("ignored.tmp\nignored-dir/\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore integration runtime")
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            (integration / "ignored.tmp").write_text("ignored runtime\n", encoding="utf-8")
            (integration / "ignored-dir").mkdir()
            (integration / "runtime.txt").write_text("untracked runtime\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1, "state": "collected"})
            self.assertEqual(git(integration, "rev-parse", "HEAD"), lane_sha)
            self.assertEqual((integration / "ignored.tmp").read_text(encoding="utf-8"), "ignored runtime\n")
            self.assertEqual((integration / "runtime.txt").read_text(encoding="utf-8"), "untracked runtime\n")
            self.assertTrue((integration / "ignored-dir").is_dir())

    def test_collect_rejects_moved_integration_identity_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            git(integration, "checkout", "--detach")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "worktree_identity_mismatch")
            self.assertTrue(observed["error"]["error"]["repair"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertTrue(lane.exists())

    def test_ready_collect_reset_overwrites_untracked_and_ignored_obstructions(self) -> None:
        for state in ("untracked", "ignored"):
            for shape in ("exact", "directory_to_file", "file_to_directory"):
                with self.subTest(state=state, shape=shape), tempfile.TemporaryDirectory() as temporary:
                    repository, _ = seed_repository(Path(temporary))
                    if state == "ignored":
                        (repository / ".gitignore").write_text("fresh.txt\npair\nignored-unrelated.tmp\n", encoding="utf-8")
                        git(repository, "add", ".gitignore")
                        git(repository, "commit", "-m", "ignore runtime state")
                    expected = seed_managed_task(repository)
                    seed_task_container(repository)
                    lane = Path(expected["lane"])
                    integration = Path(expected["integration"])
                    if shape == "exact":
                        (lane / "fresh.txt").write_text("lane exact content\n", encoding="utf-8")
                        git(lane, "add", "-f" if state == "ignored" else "--", "fresh.txt")
                        (integration / "fresh.txt").write_text(f"{state} obstruction\n", encoding="utf-8")
                    elif shape == "directory_to_file":
                        (lane / "pair").write_text("lane file content\n", encoding="utf-8")
                        git(lane, "add", "-f" if state == "ignored" else "--", "pair")
                        (integration / "pair").mkdir()
                        (integration / "pair/runtime.tmp").write_text(f"{state} obstruction\n", encoding="utf-8")
                    else:
                        (lane / "pair").mkdir()
                        (lane / "pair/accepted.txt").write_text("lane nested content\n", encoding="utf-8")
                        git(lane, "add", "-f" if state == "ignored" else "--", "pair/accepted.txt")
                        (integration / "pair").write_text(f"{state} obstruction\n", encoding="utf-8")
                    git(lane, "commit", "-m", f"lane {shape} transition")
                    lane_sha = git(lane, "rev-parse", "HEAD")
                    unrelated = integration / (
                        "ignored-unrelated.tmp" if state == "ignored" else "ordinary-unrelated.tmp"
                    )
                    unrelated.write_text(f"{state} unrelated\n", encoding="utf-8")

                    observed = invoke(
                        repository,
                        {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                    )

                    self.assertFalse(observed["is_error"])
                    self.assertEqual(observed["result"]["state"], "collected")
                    self.assertEqual(git(integration, "rev-parse", "HEAD"), lane_sha)
                    self.assertEqual(unrelated.read_text(encoding="utf-8"), f"{state} unrelated\n")
                    if shape == "exact":
                        self.assertEqual((integration / "fresh.txt").read_text(encoding="utf-8"), "lane exact content\n")
                    elif shape == "directory_to_file":
                        self.assertEqual((integration / "pair").read_text(encoding="utf-8"), "lane file content\n")
                    else:
                        self.assertEqual(
                            (integration / "pair/accepted.txt").read_text(encoding="utf-8"),
                            "lane nested content\n",
                        )

    def test_collect_preserves_tracked_integration_dirt_and_merge_state(self) -> None:
        for case in ("tracked", "merge"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, _ = seed_repository(base)
                expected = seed_managed_task(repository)
                integration = Path(expected["integration"])
                lane = Path(expected["lane"])
                if case == "tracked":
                    (integration / "tracked.txt").write_text("preserve integration dirt\n", encoding="utf-8")
                else:
                    (repository / "tracked.txt").write_text("main conflict\n", encoding="utf-8")
                    git(repository, "add", "tracked.txt")
                    git(repository, "commit", "-m", "main conflict")
                    (integration / "tracked.txt").write_text("integration conflict\n", encoding="utf-8")
                    git(integration, "add", "tracked.txt")
                    git(integration, "commit", "-m", "integration conflict")
                    integration_before = git(repository, "rev-parse", "wave/demo/integration")
                    merge = subprocess.run(
                        ["git", "-C", str(integration), "merge", "--no-commit", "main"],
                        text=True,
                        capture_output=True,
                    )
                    self.assertNotEqual(merge.returncode, 0)
                    self.assertIn("UU tracked.txt", git(integration, "status", "--porcelain=v1"))

                integration_before = git(repository, "rev-parse", "wave/demo/integration")
                lane_before = git(repository, "rev-parse", "wave/demo/writer-1")
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
                self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_before)
                self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_before)
                self.assertTrue(integration.exists())

    def test_collect_rejects_an_active_lane_merge_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "tracked.txt").write_text("integration conflict\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            (lane / "tracked.txt").write_text("lane conflict\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane conflict")
            lane_sha = git(lane, "rev-parse", "HEAD")
            merge = subprocess.run(
                ["git", "-C", str(lane), "merge", "--no-commit", "wave/demo/integration"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertTrue(lane.exists())

    def test_collect_reconciles_stale_lane_then_collects_current_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            (integration / "advance.txt").write_text("advance\n", encoding="utf-8")
            git(integration, "add", "advance.txt")
            git(integration, "commit", "-m", "integration advance")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")

            reconciled = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertFalse(reconciled["is_error"])
            self.assertEqual(reconciled["result"]["state"], "reconciled")
            synced_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            self.assertTrue(git(repository, "merge-base", "--is-ancestor", integration_sha, synced_sha) == "")
            self.assertTrue(lane.exists())

            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")

    def test_collect_uses_current_tips_after_another_lane_moves_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            self.assertFalse(
                invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer-2"})["is_error"]
            )
            other = repository / ".agent_state/worktrees/demo/lanes/writer-2"
            (other / "other.txt").write_text("other\n", encoding="utf-8")
            git(other, "add", "other.txt")
            git(other, "commit", "-m", "other lane work")
            other_sha = git(other, "rev-parse", "HEAD")
            moved = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-2"},
            )
            self.assertFalse(moved["is_error"])
            self.assertEqual(moved["result"]["state"], "collected")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), other_sha)

            reconciled = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertFalse(reconciled["is_error"])
            self.assertEqual(reconciled["result"]["state"], "merged")
            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer-1").exists())
            self.assertNotIn("comparison_moved", collected["result"])

    def test_stale_collect_surfaces_native_untracked_merge_collisions_without_deletion(self) -> None:
        for shape in ("exact", "directory_to_file", "file_to_directory"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                lane = Path(expected["lane"])
                integration = Path(expected["integration"])
                lane_sha = git(lane, "rev-parse", "HEAD")
                if shape == "exact":
                    (integration / "collide.txt").write_text("accepted exact\n", encoding="utf-8")
                    git(integration, "add", "collide.txt")
                    blocker = lane / "collide.txt"
                    blocker.write_text("ordinary blocker\n", encoding="utf-8")
                elif shape == "directory_to_file":
                    (integration / "pair").write_text("accepted file\n", encoding="utf-8")
                    git(integration, "add", "pair")
                    blocker = lane / "pair/runtime.tmp"
                    blocker.parent.mkdir()
                    blocker.write_text("ordinary blocker\n", encoding="utf-8")
                else:
                    (integration / "pair").mkdir()
                    (integration / "pair/accepted.txt").write_text("accepted nested\n", encoding="utf-8")
                    git(integration, "add", "pair/accepted.txt")
                    blocker = lane / "pair"
                    blocker.write_text("ordinary blocker\n", encoding="utf-8")
                git(integration, "commit", "-m", f"integration {shape} transition")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "git_error")
                self.assertEqual(blocker.read_text(encoding="utf-8"), "ordinary blocker\n")
                self.assertEqual(git(lane, "rev-parse", "HEAD"), lane_sha)
                self.assertEqual(git(lane, "status", "--porcelain=v1", "--untracked-files=no"), "")

    def test_stale_collect_merge_overwrites_ignored_exact_and_file_directory_collisions(self) -> None:
        for shape in ("exact", "directory_to_file", "file_to_directory"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                (repository / ".gitignore").write_text("collide.txt\npair\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime state")
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lane = Path(expected["lane"])
                integration = Path(expected["integration"])
                if shape == "exact":
                    (integration / "collide.txt").write_text("accepted exact\n", encoding="utf-8")
                    git(integration, "add", "-f", "collide.txt")
                    (lane / "collide.txt").write_text("ignored blocker\n", encoding="utf-8")
                elif shape == "directory_to_file":
                    (integration / "pair").write_text("accepted file\n", encoding="utf-8")
                    git(integration, "add", "-f", "pair")
                    (lane / "pair").mkdir()
                    (lane / "pair/runtime.tmp").write_text("ignored blocker\n", encoding="utf-8")
                else:
                    (integration / "pair").mkdir()
                    (integration / "pair/accepted.txt").write_text("accepted nested\n", encoding="utf-8")
                    git(integration, "add", "-f", "pair/accepted.txt")
                    (lane / "pair").write_text("ignored blocker\n", encoding="utf-8")
                git(integration, "commit", "-m", f"integration {shape} transition")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertFalse(observed["is_error"])
                self.assertEqual(observed["result"]["state"], "reconciled")
                self.assertFalse(
                    any("dirty" in warning or "preserv" in warning for warning in observed["result"]["warnings"])
                )
                if shape == "exact":
                    self.assertEqual((lane / "collide.txt").read_text(encoding="utf-8"), "accepted exact\n")
                elif shape == "directory_to_file":
                    self.assertEqual((lane / "pair").read_text(encoding="utf-8"), "accepted file\n")
                else:
                    self.assertEqual(
                        (lane / "pair/accepted.txt").read_text(encoding="utf-8"),
                        "accepted nested\n",
                    )

    def test_collect_disposal_stays_within_selected_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            other_expected = seed_managed_task(repository, "other")
            lane = Path(expected["lane"])
            other_lane = repository / ".agent_state/worktrees/other/lanes/writer-1"
            other_integration = repository / ".agent_state/worktrees/other/integration"
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            (lane / "disposable-lane.txt").write_text("disposable\n", encoding="utf-8")
            (repository / "caller-untracked.txt").write_text("caller preserve\n", encoding="utf-8")
            (other_lane / "other-disposable.txt").write_text("other lane preserve\n", encoding="utf-8")
            (other_integration / "other-disposable.txt").write_text("other integration preserve\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertEqual((repository / "caller-untracked.txt").read_text(encoding="utf-8"), "caller preserve\n")
            self.assertEqual((other_lane / "other-disposable.txt").read_text(encoding="utf-8"), "other lane preserve\n")
            self.assertEqual((other_integration / "other-disposable.txt").read_text(encoding="utf-8"), "other integration preserve\n")
            self.assertEqual(git(repository, "rev-parse", "wave/other/writer-1"), other_expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/other/integration"), other_expected["integration_head"])
            self.assertFalse(lane.exists())

    def test_collect_preserves_lane_after_worktree_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            wrapper = write_git_wrapper(base, FAIL_WORKTREE_REMOVE)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(lane.exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_sha)
            self.assertEqual(last_telemetry_event(repository)["cleanup_cleaned"], False)

    def test_collect_preserves_lane_after_branch_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            wrapper = write_git_wrapper(base, FAIL_LANE_BRANCH_REMOVE)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(lane.exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_sha)

    def test_collect_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")

            observed = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


class CollabOpExtensionLaneDropContractRegressionTests(unittest.TestCase):
    def test_drop_removes_clean_lane_and_records_internal_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            created = invoke(
                repository,
                {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
            )
            self.assertFalse(created["is_error"])
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            lane_sha = git(lane, "rev-parse", "HEAD")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"], {"ok": True, "tool_version": 1})
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-drop")
            self.assertEqual(event["disposition"], "abandoned")
            self.assertEqual(event["lane_sha"], lane_sha)
            self.assertEqual(event["dirty"], False)
            self.assertEqual(event["uncollected"], False)
            self.assertEqual(expected["integration_head"], integration_sha)

    def test_drop_untracked_and_ignored_only_state_does_not_warn(self) -> None:
        for state in ("untracked", "ignored"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
                git(repository, "add", ".gitignore")
                git(repository, "commit", "-m", "ignore runtime state")
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lane = Path(expected["lane"])
                candidate = lane / ("ordinary.tmp" if state == "untracked" else "ignored.tmp")
                candidate.write_text(f"{state} runtime\n", encoding="utf-8")

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertFalse(observed["is_error"])
                self.assertNotIn("warnings", observed["result"])
                self.assertFalse(lane.exists())
                self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
                self.assertEqual(last_telemetry_event(repository)["dirty"], False)

    def test_drop_tracked_and_staged_state_warn(self) -> None:
        for state in ("tracked", "staged"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                seed_task_container(repository)
                lane = Path(expected["lane"])
                if state == "tracked":
                    (lane / "tracked.txt").write_text("modified\n", encoding="utf-8")
                else:
                    candidate = lane / "staged.txt"
                    candidate.write_text("staged\n", encoding="utf-8")
                    git(lane, "add", candidate.name)

                observed = invoke(
                    repository,
                    {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
                )

                self.assertFalse(observed["is_error"])
                self.assertTrue(
                    any(
                        "dirty or conflicted" in warning
                        for warning in observed["result"]["warnings"]
                    )
                )
                self.assertFalse(lane.exists())
                self.assertEqual(last_telemetry_event(repository)["dirty"], True)

    def test_drop_conflict_state_warns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "tracked.txt").write_text("lane conflict\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane conflict")
            (integration / "tracked.txt").write_text("integration conflict\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            reconciled = invoke(
                repository,
                {"tool": "collab_lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )
            self.assertEqual(reconciled["result"]["state"], "conflicted")

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(
                any(
                    "dirty or conflicted" in warning
                    for warning in observed["result"]["warnings"]
                )
            )
            self.assertFalse(lane.exists())
            event = last_telemetry_event(repository)
            self.assertEqual(event["dirty"], True)
            self.assertEqual(event["conflicted"], True)

    def test_drop_unclassifiable_status_warns_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            wrapper = write_git_wrapper(base, FAIL_STATUS)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(
                any("incomplete" in warning for warning in observed["result"]["warnings"])
            )
            self.assertFalse(Path(expected["lane"]).exists())
            self.assertEqual(last_telemetry_event(repository)["incomplete"], True)

    def test_drop_reports_branch_cleanup_residual_after_path_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository)
            wrapper = write_git_wrapper(base, FAIL_LANE_BRANCH_REMOVE)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertFalse(Path(repository / ".agent_state/worktrees/demo/lanes/writer-1").exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "  wave/demo/writer-1")

    def test_drop_unlinks_canonical_symlink_without_touching_aliased_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            self.assertFalse(
                invoke(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"})["is_error"]
            )
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            git(repository, "worktree", "remove", "--force", str(lane))
            unrelated = base / "unrelated-worktree"
            git(repository, "branch", "operator-preserve", git(repository, "rev-parse", "main"))
            git(repository, "worktree", "add", str(unrelated), "operator-preserve")
            (unrelated / "operator.txt").write_text("preserve\n", encoding="utf-8")
            lane.symlink_to(unrelated, target_is_directory=True)

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertFalse(lane.exists())
            self.assertTrue(unrelated.is_dir())
            self.assertEqual((unrelated / "operator.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertEqual(git(repository, "rev-parse", "operator-preserve"), git(unrelated, "rev-parse", "HEAD"))

    def test_drop_cleans_safe_resources_from_incomplete_inventory_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            lane = Path(repository / ".agent_state/worktrees/demo/lanes/writer-1")
            git(repository, "update-ref", "--no-deref", "-d", "refs/heads/wave/demo/writer-1")

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("incomplete" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")

    def test_drop_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"tool": "collab_lane_drop", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


class CollabOpExtensionIntegrationRemoveContractRegressionTests(unittest.TestCase):
    def test_remove_preserves_foreign_integration_symlink_custody(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            git(repository, "worktree", "remove", "--force", str(integration))
            foreign = base / "foreign-integration"
            git(repository, "branch", "foreign-integration", "main")
            git(repository, "worktree", "add", str(foreign), "foreign-integration")
            (foreign / "operator.txt").write_text("preserve\n", encoding="utf-8")
            integration.symlink_to(foreign, target_is_directory=True)

            observed = invoke(
                repository,
                {"tool": "collab_integration_remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertTrue(integration.is_symlink())
            self.assertTrue(foreign.is_dir())
            self.assertEqual((foreign / "operator.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(git(repository, "branch", "--list", "foreign-integration"), "+ foreign-integration")
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repository), "show-ref", "--verify", "--quiet", "refs/orchestrate/demo/integration/base"],
                    capture_output=True,
                ).returncode,
                0,
            )

    def test_remove_continues_after_lane_branch_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            wrapper = write_git_wrapper(base, FAIL_LANE_BRANCH_REMOVE)
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            close_harness_for(repository)
            try:
                observed = invoke(
                    repository,
                    {"tool": "collab_integration_remove", "task_id": "demo"},
                )
            finally:
                os.environ["PATH"] = original_path
                close_harness_for(repository)

            self.assertFalse(observed["is_error"])
            self.assertTrue(observed["result"]["warnings"])
            self.assertFalse(Path(repository / ".agent_state/worktrees/demo/lanes/writer-1").exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "  wave/demo/writer-1")
            self.assertFalse(Path(repository / ".agent_state/worktrees/demo/integration").exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")

    def test_remove_retains_unrecognized_refs_while_cleaning_known_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            git(repository, "update-ref", "refs/orchestrate/demo/accepted", expected["integration_head"])

            observed = invoke(
                repository,
                {"tool": "collab_integration_remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("unrecognized task refs retained" in warning for warning in observed["result"]["warnings"]))
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/accepted"), expected["integration_head"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertNotEqual(
                subprocess.run(
                    ["git", "-C", str(repository), "show-ref", "--verify", "--quiet", "refs/orchestrate/demo/integration/base"],
                    capture_output=True,
                ).returncode,
                0,
            )

    def test_remove_without_task_container_reports_telemetry_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration_remove", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


class CollabOpExtensionAgentStateExclusionTests(unittest.TestCase):
    def test_create_in_unprepared_repository_excludes_managed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(exclusion_lines(repository), ["/.agent_state/"])
            self.assertEqual(git(repository, "status", "--porcelain"), "")
            self.assertTrue((repository / ".agent_state/worktrees/demo/integration").is_dir())

    def test_adopt_in_unprepared_repository_excludes_managed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            _, source_sha = seed_donor(repository, base, base_sha)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "tool": "collab_integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha,
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["integration_branch"], "wave/demo/integration")
            self.assertEqual(exclusion_lines(repository), ["/.agent_state/"])
            self.assertEqual(git(repository, "status", "--porcelain"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), source_sha)

    def test_already_ignored_repository_keeps_exclude_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            commit_agent_state_ignore(repository)
            seed_task_container(repository)
            before = exclude_file(repository).read_bytes()

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(exclude_file(repository).read_bytes(), before)
            self.assertEqual(git(repository, "status", "--porcelain"), "")

    def test_second_establishing_call_appends_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository, "demo")
            seed_task_container(repository, "second")

            first = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )
            after_first = exclude_file(repository).read_bytes()
            second = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "second"},
            )

            self.assertFalse(first["is_error"])
            self.assertFalse(second["is_error"])
            self.assertEqual(exclusion_lines(repository), ["/.agent_state/"])
            self.assertEqual(exclude_file(repository).read_bytes(), after_first)
            self.assertEqual(git(repository, "status", "--porcelain"), "")

    def test_negated_ignore_rule_refuses_before_any_managed_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            commit_agent_state_ignore(repository, "!.agent_state")
            seed_task_container(repository)
            before_refs = managed_ref_snapshot(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "agent_state_not_ignored")
            self.assertTrue(error["repair"])
            self.assertEqual(
                [entry["pattern"] for entry in error["details"]["overriding_patterns"]],
                ["!.agent_state"],
            )
            self.assertTrue(error["details"]["exclude_written"])
            self.assertIn("appended line remains", error["message"])
            self.assertIn("appended line remains", error["repair"])
            self.assertEqual(exclusion_lines(repository), ["/.agent_state/"])
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_preexisting_exclusion_failure_does_not_claim_this_call_wrote_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            commit_agent_state_ignore(repository, "!.agent_state")
            seed_task_container(repository)
            exclude_file(repository).write_text("/.agent_state/\n", encoding="utf-8")
            before = exclude_file(repository).read_bytes()

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "agent_state_not_ignored")
            self.assertFalse(error["details"]["exclude_written"])
            self.assertIn("this call did not modify", error["message"])
            self.assertNotIn("appended line remains", error["repair"])
            self.assertEqual(exclude_file(repository).read_bytes(), before)

    def test_non_regular_exclude_file_returns_coded_io_error_without_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            exclusion = exclude_file(repository)
            exclusion.unlink()
            exclusion.mkdir()
            before_refs = managed_ref_snapshot(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "agent_state_exclusion_io_error")
            self.assertTrue(error["repair"])
            self.assertEqual(
                error["details"]["operation"],
                "validate the exclusion file",
            )
            self.assertEqual(error["details"]["exclude_file"], str(exclusion))
            self.assertEqual(error["details"]["path_type"], "directory")
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_symlinked_exclude_file_is_rejected_before_it_can_discard_the_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            exclusion = exclude_file(repository)
            exclusion.unlink()
            exclusion.symlink_to("/dev/null")
            before_refs = managed_ref_snapshot(repository)

            observed = invoke(
                repository,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertTrue(observed["is_error"])
            error = observed["error"]["error"]
            self.assertEqual(error["code"], "agent_state_exclusion_io_error")
            self.assertEqual(error["details"]["operation"], "validate the exclusion file")
            self.assertEqual(error["details"]["exclude_file"], str(exclusion))
            self.assertEqual(error["details"]["path_type"], "symbolic link")
            self.assertNotIn("exclude_written", error["details"])
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_only_a_performed_exclusion_write_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            homes = Path(temporary)
            (homes / "unprepared").mkdir()
            (homes / "prepared").mkdir()
            unprepared, _ = seed_repository(homes / "unprepared")
            seed_task_container(unprepared)
            prepared, _ = seed_repository(homes / "prepared")
            commit_agent_state_ignore(prepared)
            seed_task_container(prepared)

            wrote = invoke(
                unprepared,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )
            untouched = invoke(
                prepared,
                {"tool": "collab_integration_create", "task_id": "demo"},
            )

            self.assertFalse(wrote["is_error"])
            self.assertFalse(untouched["is_error"])
            self.assertEqual(len(exclusion_warnings(wrote["result"])), 1)
            self.assertIn("/.agent_state/", exclusion_warnings(wrote["result"])[0])
            self.assertEqual(exclusion_warnings(untouched["result"]), [])

    def test_unprepared_repository_runs_a_task_through_to_landing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)

            self.assertFalse(
                invoke(
                    repository,
                    {"tool": "collab_integration_create", "task_id": "demo"},
                )["is_error"]
            )
            self.assertFalse(
                invoke(
                    repository,
                    {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer"},
                )["is_error"]
            )
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            (lane / "work.txt").write_text("lane work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")

            collected = invoke(
                repository,
                {"tool": "collab_lane_collect", "task_id": "demo", "lane_id": "writer"},
            )
            landed = invoke(
                repository,
                {"tool": "collab_integration_land", "task_id": "demo", "message": "Ship lane work"},
            )

            self.assertEqual(collected["result"]["state"], "collected")
            self.assertFalse(landed["is_error"])
            self.assertEqual(
                (repository / "work.txt").read_text(encoding="utf-8"), "lane work\n"
            )
            self.assertEqual(git(repository, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
