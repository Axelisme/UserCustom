from __future__ import annotations

import atexit
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


atexit.register(close_harnesses)


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def invoke(repository: Path, request: dict[str, object]) -> dict[str, object]:
    for stale in [path for path in _HARNESSES if not path.exists()]:
        close_harness(_HARNESSES.pop(stale))

    key = repository.resolve()
    process = _HARNESSES.get(key)
    if process is None or process.poll() is not None:
        if process is not None:
            close_harness(process)
        process = subprocess.Popen(
            ["node", str(HARNESS), str(PI_PACKAGE), str(EXTENSION), str(key)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _HARNESSES[key] = process

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
    git(repository, "update-ref", f"refs/orchestrate/{task_id}/landed", base)
    return {
        "base": base,
        "integration_head": integration_head,
        "integration": str(integration.resolve()),
        "lane": str(lane.resolve()),
    }


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


def seed_migratable_legacy(repository: Path, task_id: str = "demo") -> dict[str, str]:
    """Build a quiescent legacy task: exact T003 resources, the live seed lane
    retired, and the recognized legacy accepted/acceptance-open/user-accepted
    refs, one orphan lane-base ref, and the canonical detached acceptance
    worktree. The accepted ref deliberately differs from the integration head."""
    expected = seed_managed_task(repository, task_id)
    dropped = invoke(
        repository,
        {"method": "lane_drop", "task_id": task_id, "lane_id": "writer-1"},
    )
    assert not dropped["is_error"], dropped
    git(repository, "update-ref", f"refs/orchestrate/{task_id}/accepted", expected["base"])
    git(
        repository,
        "update-ref",
        f"refs/orchestrate/{task_id}/user-accepted",
        expected["base"],
    )
    git(
        repository,
        "update-ref",
        f"refs/orchestrate/{task_id}/writer-1/base",
        expected["base"],
    )
    git(
        repository,
        "update-ref",
        f"refs/orchestrate/{task_id}/acceptance-open",
        expected["integration_head"],
    )
    acceptance = repository / f".agent_state/worktrees/{task_id}/acceptance"
    git(
        repository,
        "worktree",
        "add",
        "--detach",
        str(acceptance),
        expected["integration_head"],
    )
    expected["acceptance"] = str(acceptance.resolve())
    return expected


def migration_sentinel_ref(task_id: str = "demo") -> str:
    return f"refs/orchestrate/{task_id}/migration"


def sentinel_oid(repository: Path, task_id: str = "demo") -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--verify", "--quiet", migration_sentinel_ref(task_id)],
        text=True,
        capture_output=True,
    )
    return result.stdout.strip() or None


def descriptor_dict(
    expected: dict[str, str],
    task_id: str = "demo",
    *,
    acceptance_present: bool = True,
    acceptance_sha: str | None = None,
    nonce: str = "00000000-0000-4000-8000-000000000001",
    legacy_refs: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """Canonical descriptor fields in canonical key order; the default records
    the seeded legacy state (acceptance-open == integration head, legacy
    accepted values differing from integration)."""
    if legacy_refs is None:
        legacy_refs = [
            {"ref": f"refs/orchestrate/{task_id}/acceptance-open", "sha": expected["integration_head"]},
            {"ref": f"refs/orchestrate/{task_id}/accepted", "sha": expected["base"]},
            {"ref": f"refs/orchestrate/{task_id}/user-accepted", "sha": expected["base"]},
            {"ref": f"refs/orchestrate/{task_id}/writer-1/base", "sha": expected["base"]},
        ]
    if acceptance_sha is None:
        acceptance_sha = expected["integration_head"] if acceptance_present else None
    return {
        "version": 1,
        "task_id": task_id,
        "nonce": nonce,
        "acceptance_present": acceptance_present,
        "integration_sha": expected["integration_head"],
        "integration_base_sha": expected["base"],
        "persistence_target": "refs/heads/main",
        "landed_sha": expected["base"],
        "acceptance_sha": acceptance_sha,
        "legacy_refs": sorted(legacy_refs, key=lambda item: item["ref"]),
    }


def canonical_descriptor_bytes(descriptor: dict[str, object]) -> bytes:
    # Byte-identical to the extension's canonical JSON serialization plus a
    # trailing newline.
    return (json.dumps(descriptor, separators=(",", ":")) + "\n").encode("utf-8")


def write_descriptor_blob(repository: Path, descriptor: dict[str, object]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "hash-object", "-w", "--stdin"],
        input=canonical_descriptor_bytes(descriptor),
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8").strip()


def commit_migration_transition(
    repository: Path,
    expected: dict[str, str],
    *,
    descriptor: dict[str, object] | None = None,
    delete_legacy: bool = True,
) -> str:
    """Commit the forward transition exactly as the runtime would: the
    sentinel at the descriptor blob and every recorded legacy ref deleted."""
    if descriptor is None:
        descriptor = descriptor_dict(expected)
    blob = write_descriptor_blob(repository, descriptor)
    git(repository, "update-ref", migration_sentinel_ref(), blob)
    if delete_legacy:
        for item in descriptor["legacy_refs"]:
            git(repository, "update-ref", "-d", item["ref"], item["sha"])
    return blob


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
    process = _HARNESSES.pop(repository.resolve(), None)
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

class CollabOpExtensionIntegrationCreateTests(unittest.TestCase):
    def test_create_builds_managed_resources_and_records_active_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            seed_task_container(repository)

            observed = invoke(repository, {"method": "integration_create", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"ok": True, "operation": "integration-create", "tool_version": 1},
            )
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), head)
            self.assertEqual(
                git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"),
                head,
            )
            self.assertEqual(
                git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                "refs/heads/main",
            )
            status_result = invoke(repository, {"method": "status", "task_id": "demo"})["result"]
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

            observed = invoke(repository, {"method": "integration_create", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in item for item in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), git(repository, "rev-parse", "main"))

    def test_create_records_telemetry_in_an_archived_container(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            archive = seed_task_container(repository, archived=True)

            observed = invoke(repository, {"method": "integration_create", "task_id": "demo"})

            self.assertNotIn("warnings", observed["result"])
            self.assertTrue((archive / ".collab_op/telemetry.jsonl").is_file())

    def test_collision_refuses_without_changing_existing_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            root = repository / ".agent_state/worktrees/demo"
            root.mkdir(parents=True)
            sentinel = root / "user.txt"
            sentinel.write_text("preserve\n", encoding="utf-8")

            observed = invoke(repository, {"method": "integration_create", "task_id": "demo"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")

    def test_detached_head_refuses_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            git(repository, "checkout", "--detach", head)

            observed = invoke(repository, {"method": "integration_create", "task_id": "demo"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "detached_head")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")

    def test_symlinked_managed_parent_refuses_without_writing_through_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            outside = base / "outside"
            outside.mkdir()
            (repository / ".agent_state").symlink_to(outside, target_is_directory=True)

            observed = invoke(repository, {"method": "integration_create", "task_id": "demo"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
            self.assertEqual(list(outside.iterdir()), [])

    def test_later_ref_failure_rolls_back_worktree_and_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            lock = repository / ".git/refs/orchestrate/demo/integration/base.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(repository, {"method": "integration_create", "task_id": "demo"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo"),
                "",
            )
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())
            self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock\n")

    def test_adjacent_task_namespace_does_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, head = seed_repository(Path(temporary))
            git(repository, "update-ref", "refs/orchestrate/demo-extra/integration/base", head)
            git(repository, "branch", "wave/demo-extra/integration", head)

            observed = invoke(repository, {"method": "integration_create", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), head)


class CollabOpExtensionIntegrationAdoptTests(unittest.TestCase):
    def test_adoption_dry_run_reports_plan_without_repository_or_telemetry_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            donor, source_sha = seed_donor(repository, base, base_sha)
            seed_task_container(repository)
            branches_before = git(repository, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads")
            refs_before = git(repository, "for-each-ref", "--format=%(refname) %(objectname) %(symref)", "refs/orchestrate")
            worktrees_before = git(repository, "worktree", "list", "--porcelain")
            files_before = snapshot_files(repository)

            observed = invoke(
                repository,
                {
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha,
                    "dry_run": True,
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "operation": "integration-adopt",
                    "tool_version": 1,
                    "dry_run": True,
                    "source_branch": "donor",
                    "source_sha": source_sha,
                    "integration_branch": "wave/demo/integration",
                    "integration_sha": source_sha,
                    "base_sha": base_sha,
                    "persist": "main",
                    "planned": {
                        "create_integration_worktree": True,
                        "create_integration_branch": True,
                        "create_base_ref": True,
                        "create_persistence_ref": True,
                    },
                },
            )
            self.assertEqual(git(repository, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads"), branches_before)
            self.assertEqual(git(repository, "for-each-ref", "--format=%(refname) %(objectname) %(symref)", "refs/orchestrate"), refs_before)
            self.assertEqual(git(repository, "worktree", "list", "--porcelain"), worktrees_before)
            self.assertEqual(snapshot_files(repository), files_before)
            self.assertEqual(telemetry_events(repository), [])
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())
            self.assertEqual(git(donor, "status", "--porcelain=v1"), "?? dirty.txt")

    def test_adoption_rejects_non_boolean_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_donor(repository, base, git(repository, "rev-parse", "HEAD"))
            observed = invoke(
                repository,
                {
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": git(repository, "rev-parse", "HEAD"),
                    "dry_run": "yes",
                },
            )
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "invalid_dry_run")

    def test_adoption_dry_run_and_mutation_share_precondition_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, original_base = seed_repository(base)
            _, source_sha = seed_donor(repository, base, original_base)
            other = base / "other"
            git(repository, "worktree", "add", "-b", "other", str(other), original_base)
            (other / "other.txt").write_text("other\n", encoding="utf-8")
            git(other, "add", "other.txt")
            git(other, "commit", "-m", "other")

            for extra in ({}, {"dry_run": True}):
                request: dict[str, object] = {
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": git(other, "rev-parse", "HEAD"),
                }
                request.update(extra)
                observed = invoke(repository, request)
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "base_not_ancestor")
                self.assertEqual(
                    observed["error"]["error"]["details"]["base_sha"],
                    git(other, "rev-parse", "HEAD"),
                )
                self.assertEqual(observed["error"]["error"]["details"]["source_sha"], source_sha)
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())

    def test_noncanonical_adoption_excludes_and_preserves_dirty_donor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            donor, source_sha = seed_donor(repository, base, base_sha)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha,
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "operation": "integration-adopt",
                    "tool_version": 1,
                    "source_branch": "donor",
                    "source_sha": source_sha,
                    "integration_branch": "wave/demo/integration",
                    "integration_sha": source_sha,
                    "base_sha": base_sha,
                },
            )
            self.assertEqual(git(donor, "rev-parse", "HEAD"), source_sha)
            self.assertEqual(git(donor, "status", "--porcelain=v1"), "?? dirty.txt")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), source_sha)
            integration = repository / ".agent_state/worktrees/demo/integration"
            self.assertEqual(git(integration, "rev-parse", "HEAD"), source_sha)
            self.assertEqual(git(integration, "status", "--porcelain=v1"), "")
            self.assertEqual(git(integration, "rev-parse", "HEAD"), git(donor, "rev-parse", "HEAD"))
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
                        "method": "integration_adopt",
                        "task_id": "demo",
                        "source_branch": "donor",
                        "persist": "main",
                        "base_sha": value,
                    },
                )
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "invalid_base_sha")

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
            git(repository, "update-ref", "refs/heads/other", original_base)

            observed = invoke(
                repository,
                {
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": other_sha,
                },
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "base_not_ancestor")
            self.assertEqual(observed["error"]["error"]["details"]["base_sha"], other_sha)
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
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha,
                },
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"), base_sha)
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
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha,
                },
            )

            self.assertTrue(observed["is_error"])
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
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "donor",
                    "persist": "main",
                    "base_sha": base_sha,
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())

    def test_canonical_adoption_fills_only_missing_refs_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, base_sha = seed_repository(base)
            integration = seed_canonical(repository, base_sha)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "wave/demo/integration",
                    "persist": "main",
                    "base_sha": base_sha,
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "operation": "integration-adopt",
                    "tool_version": 1,
                    "source_branch": "wave/demo/integration",
                    "source_sha": base_sha,
                    "integration_branch": "wave/demo/integration",
                    "integration_sha": base_sha,
                    "base_sha": base_sha,
                },
            )
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

    def test_canonical_adoption_refuses_dirty_or_partial_arrangements(self) -> None:
        for case in ("dirty", "extra_ref", "detached"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                repository, base_sha = seed_repository(base)
                integration = seed_canonical(repository, base_sha)
                if case == "dirty":
                    (integration / "dirty.txt").write_text("preserve\n", encoding="utf-8")
                elif case == "extra_ref":
                    git(repository, "update-ref", "refs/orchestrate/demo/extra", base_sha)
                else:
                    git(integration, "checkout", "--detach")

                observed = invoke(
                    repository,
                    {
                        "method": "integration_adopt",
                        "task_id": "demo",
                        "source_branch": "wave/demo/integration",
                        "persist": "main",
                        "base_sha": base_sha,
                    },
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "task_resource_collision")
                if case == "dirty":
                    self.assertEqual((integration / "dirty.txt").read_text(encoding="utf-8"), "preserve\n")
                elif case == "extra_ref":
                    self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/extra"), base_sha)
                else:
                    self.assertEqual(git(integration, "rev-parse", "HEAD"), base_sha)


class CollabOpExtensionReviewBoundaryTests(unittest.TestCase):
    def test_acceptance_methods_are_not_implemented(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            for method in ("acceptance_start", "acceptance_finish"):
                observed = invoke(repository, {"method": method, "task_id": "demo"})
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "method_not_implemented")
                self.assertEqual(observed["error"]["operation"], method.replace("_", "-"))

    def test_full_lifecycle_keeps_only_new_model_refs_and_no_acceptance_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_task_container(repository)
            self.assertFalse(invoke(repository, {"method": "integration_create", "task_id": "demo"})["is_error"])
            self.assertFalse(invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})["is_error"])
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            integration_head = git(repository, "rev-parse", "wave/demo/integration")
            collected = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer",
                    "sha": lane_sha,
                    "integration_sha": integration_head,
                },
            )
            self.assertFalse(collected["is_error"])
            landed = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})
            self.assertFalse(landed["is_error"])

            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo"),
                "refs/orchestrate/demo/integration/base\nrefs/orchestrate/demo/landed\nrefs/orchestrate/demo/persistence",
            )
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/heads/wave/demo"),
                "refs/heads/wave/demo/integration",
            )
            self.assertFalse((repository / ".agent_state/worktrees/demo/acceptance").exists())
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo/writer"),
                "",
            )

    def test_lane_creation_never_writes_lane_base_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            created = invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})
            self.assertFalse(created["is_error"])
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo"),
                "refs/orchestrate/demo/integration/base\nrefs/orchestrate/demo/landed\nrefs/orchestrate/demo/persistence",
            )
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer"), expected["integration_head"])


class CollabOpExtensionLaneCreateTests(unittest.TestCase):
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
                    "method": "lane_create",
                    "task_id": "demo",
                    "lane_id": "writer",
                    "comment": "  review 🧭  ",
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"ok": True, "operation": "lane-create", "tool_version": 1},
            )
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            self.assertEqual(git(lane, "rev-parse", "HEAD"), committed_tip)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual((integration / "tracked.txt").read_text(encoding="utf-8"), "dirty integration\n")
            self.assertEqual((integration / "untracked.txt").read_text(encoding="utf-8"), "exclude me\n")
            self.assertEqual((integration / "ignored.txt").read_text(encoding="utf-8"), "exclude ignored\n")
            event = json.loads(
                (repository / ".agent_state/plans/demo/.collab_op/telemetry.jsonl")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(event["operation"], "lane-create")
            self.assertEqual(event["lane_id"], "writer")
            self.assertEqual(event["comment"], "review 🧭")
            self.assertEqual(event["lane_sha"], committed_tip)
            self.assertEqual(event["integration_sha"], committed_tip)

    def test_lane_create_rejects_reserved_lane_and_unicode_comment_over_bound(self) -> None:
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
                    "method": "lane_create",
                    "task_id": "demo",
                    "lane_id": lane_id,
                }
                if comment is not None:
                    request["comment"] = comment
                observed = invoke(repository, request)
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], expected_code)
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer").exists())

            valid = invoke(
                repository,
                {
                    "method": "lane_create",
                    "task_id": "demo",
                    "lane_id": "unicode",
                    "comment": "🧭" * 500,
                },
            )
            self.assertFalse(valid["is_error"])

    def test_lane_create_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)

            observed = invoke(
                repository,
                {"method": "lane_create", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())

    def test_lane_create_collisions_refuse_before_mutation(self) -> None:
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
                    {"method": "lane_create", "task_id": "demo", "lane_id": "writer"},
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "lane_resource_collision")
                self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
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
                {"method": "lane_create", "task_id": "demo", "lane_id": "writer"},
            )

            self.assertTrue(observed["is_error"])
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
                    {"method": "lane_create", "task_id": "demo", "lane_id": lane_id},
                )
                self.assertFalse(created["is_error"])
                lane = repository / ".agent_state/worktrees/demo/lanes" / lane_id
                (lane / f"{lane_id}.txt").write_text("work\n", encoding="utf-8")
                git(lane, "add", f"{lane_id}.txt")
                git(lane, "commit", "-m", f"work {lane_id}")

            observed = invoke(
                repository,
                {"method": "lane_create", "task_id": "demo", "lane_id": "writer-final"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("9 or more" in warning for warning in observed["result"]["warnings"]))


class CollabOpExtensionLaneReconcileTests(unittest.TestCase):
    def test_lane_reconcile_noop_preserves_integration_dirt_and_records_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {"method": "lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "operation": "lane-reconcile",
                    "tool_version": 1,
                    "state": "noop",
                    "lane_sha": expected["integration_head"],
                    "integration_sha": expected["integration_head"],
                    "warnings": ["lane already includes latest integration"],
                },
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
                {"method": "lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["operation"], "lane-reconcile")
            self.assertEqual(result["state"], "merged")
            merged_sha = result["lane_sha"]
            self.assertEqual(result["integration_sha"], integration_sha)
            self.assertNotEqual(merged_sha, lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), merged_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertEqual(
                git(repository, "rev-list", "--parents", "-n", "1", merged_sha).split(),
                [merged_sha, lane_sha, integration_sha],
            )
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertTrue(
                git(repository, "merge-base", "--is-ancestor", integration_sha, merged_sha)
                == ""
            )
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
                {"method": "lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "conflicted")
            self.assertEqual(observed["result"]["lane_sha"], lane_sha)
            self.assertEqual(observed["result"]["integration_sha"], integration_sha)
            self.assertEqual(observed["result"]["conflict_paths"], ["tracked.txt"])
            self.assertTrue(any("resolve" in warning for warning in observed["result"]["warnings"]))
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            event = last_telemetry_event(repository)
            self.assertEqual(event["state"], "conflicted")
            self.assertEqual(event["conflict_path_count"], 1)
            self.assertNotIn("conflict_paths", event)

    def test_lane_reconcile_unexpected_merge_failure_restores_exact_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            lane = Path(expected["lane"])
            (integration / "advance.txt").write_text("advance\n", encoding="utf-8")
            git(integration, "add", "advance.txt")
            git(integration, "commit", "-m", "integration advance")
            lane_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            lock = git(lane, "rev-parse", "--git-path", "index.lock")
            lock_path = Path(lock) if Path(lock).is_absolute() else (lane / lock)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"method": "lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "git_error")
            self.assertTrue(observed["error"]["error"]["details"]["rollback"]["restored"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual(lock_path.read_text(encoding="utf-8"), "foreign lock\n")

    def test_lane_reconcile_refuses_lane_dirt_and_identity_mismatches(self) -> None:
        cases = ("dirty", "identity")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                lane = Path(expected["lane"])
                if case == "dirty":
                    (lane / "dirty.txt").write_text("dirty\n", encoding="utf-8")
                else:
                    git(lane, "checkout", "--detach")
                observed = invoke(
                    repository,
                    {"method": "lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
                )
                self.assertTrue(observed["is_error"])
                self.assertEqual(
                    observed["error"]["error"]["code"],
                    "dirty_worktree" if case == "dirty" else "worktree_identity_mismatch",
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
                {"method": "lane_reconcile", "task_id": "demo", "lane_id": "writer-1"},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


class CollabOpExtensionLaneCollectTests(unittest.TestCase):
    def test_ready_collect_advances_integration_to_exact_subject_and_retires_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            integration_before = git(repository, "rev-parse", "wave/demo/integration")

            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "operation": "lane-collect",
                    "tool_version": 1,
                    "state": "collected",
                    "lane_sha": lane_sha,
                    "integration_sha": lane_sha,
                    "judged_integration_sha": expected["integration_head"],
                    "cleanup": {"cleaned": True},
                },
            )
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", f"{lane_sha}^{{tree}}"), git(repository, "rev-parse", "wave/demo/integration^{tree}"))
            self.assertEqual(git(integration, "rev-parse", "HEAD"), lane_sha)
            self.assertEqual(git(integration, "status", "--porcelain=v1"), "")
            self.assertNotEqual(lane_sha, integration_before)
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "lane-collect")
            self.assertEqual(event["state"], "collected")
            self.assertEqual(event["lane_sha"], lane_sha)
            self.assertEqual(event["integration_sha"], lane_sha)
            self.assertTrue(event["cleanup_cleaned"])

    def test_ready_collect_allows_ignored_integration_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore local files")
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            ignored = integration / "ignored.tmp"
            ignored.write_text("preserve\n", encoding="utf-8")
            self.assertEqual(git(integration, "status", "--porcelain=v1"), "")
            self.assertEqual(
                git(integration, "status", "--porcelain=v1", "--ignored=matching"),
                "!! ignored.tmp",
            )

            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertEqual(observed["result"]["integration_sha"], lane_sha)
            self.assertEqual(git(integration, "rev-parse", "HEAD"), lane_sha)
            self.assertEqual(ignored.read_text(encoding="utf-8"), "preserve\n")

    def test_ready_collect_creates_no_additional_content_bearing_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            commits_before = git(repository, "rev-list", "--all", "--count")

            collected = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertEqual(collected["result"]["integration_sha"], lane_sha)
            self.assertEqual(collected["result"]["judged_integration_sha"], expected["integration_head"])
            self.assertEqual(git(repository, "rev-list", "--all", "--count"), commits_before)
            self.assertEqual(
                git(repository, "rev-list", "--parents", "-n", "1", "wave/demo/integration").split(),
                [lane_sha, expected["integration_head"]],
            )

    def test_collect_rejects_imprecise_or_unresolvable_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            for value in ("HEAD", expected["integration_head"][:8], "main"):
                observed = invoke(
                    repository,
                    {
                        "method": "lane_collect",
                        "task_id": "demo",
                        "lane_id": "writer-1",
                        "sha": value,
                        "integration_sha": expected["integration_head"],
                    },
                )
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "invalid_sha")
            for value in ("HEAD", expected["integration_head"][:8], "main"):
                observed = invoke(
                    repository,
                    {
                        "method": "lane_collect",
                        "task_id": "demo",
                        "lane_id": "writer-1",
                        "sha": expected["integration_head"],
                        "integration_sha": value,
                    },
                )
                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "invalid_sha")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), expected["integration_head"])

    def test_collect_rejects_moved_lane_tip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "first.txt").write_text("first\n", encoding="utf-8")
            git(lane, "add", "first.txt")
            git(lane, "commit", "-m", "first")
            first_sha = git(lane, "rev-parse", "HEAD")
            (lane / "second.txt").write_text("second\n", encoding="utf-8")
            git(lane, "add", "second.txt")
            git(lane, "commit", "-m", "second")
            lane_sha = git(lane, "rev-parse", "HEAD")

            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": first_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "lane_sha_mismatch")
            self.assertEqual(observed["error"]["error"]["details"]["lane_sha"], lane_sha)
            self.assertEqual(observed["error"]["error"]["details"]["supplied_sha"], first_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)

    def test_collect_rejects_dirty_or_moved_integration_managed_state(self) -> None:
        cases = ("integration_untracked_dirty", "integration_tracked_dirty", "integration_identity")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                lane = Path(expected["lane"])
                integration = Path(expected["integration"])
                (lane / "work.txt").write_text("work\n", encoding="utf-8")
                git(lane, "add", "work.txt")
                git(lane, "commit", "-m", "work")
                lane_sha = git(lane, "rev-parse", "HEAD")
                if case == "integration_untracked_dirty":
                    (integration / "dirty.txt").write_text("preserve\n", encoding="utf-8")
                elif case == "integration_tracked_dirty":
                    (integration / "tracked.txt").write_text("preserve tracked change\n", encoding="utf-8")
                else:
                    git(integration, "checkout", "--detach")

                observed = invoke(
                    repository,
                    {
                        "method": "lane_collect",
                        "task_id": "demo",
                        "lane_id": "writer-1",
                        "sha": lane_sha,
                        "integration_sha": expected["integration_head"],
                    },
                )

                self.assertTrue(observed["is_error"])
                expected_code = "worktree_identity_mismatch" if case == "integration_identity" else "dirty_worktree"
                self.assertEqual(observed["error"]["error"]["code"], expected_code)
                self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
                self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
                if case == "integration_untracked_dirty":
                    self.assertEqual((integration / "dirty.txt").read_text(encoding="utf-8"), "preserve\n")
                elif case == "integration_tracked_dirty":
                    self.assertEqual(
                        (integration / "tracked.txt").read_text(encoding="utf-8"),
                        "preserve tracked change\n",
                    )

    def test_collect_rejects_lane_with_active_merge_or_conflict_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "tracked.txt").write_text("lane\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane conflict")
            lane_sha = git(lane, "rev-parse", "HEAD")
            (integration / "tracked.txt").write_text("integration\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            conflicted_merge = subprocess.run(
                ["git", "-C", str(lane), "merge", "--no-ff", "--no-commit", "wave/demo/integration"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(conflicted_merge.returncode, 0)

            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), git(repository, "rev-parse", "wave/demo/integration"))

    def test_stale_collect_reconciles_lane_and_stops_before_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            judged_sha = git(lane, "rev-parse", "HEAD")
            integration_before = git(repository, "rev-parse", "wave/demo/integration")
            (integration / "advance.txt").write_text("advance\n", encoding="utf-8")
            git(integration, "add", "advance.txt")
            git(integration, "commit", "-m", "integration advance")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": judged_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "reconciled")
            self.assertFalse(result["collected"])
            self.assertEqual(result["integration_sha"], integration_sha)
            self.assertEqual(result["judged_integration_sha"], expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertNotEqual(integration_sha, integration_before)
            synced_sha = result["lane_sha"]
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), synced_sha)
            self.assertTrue(git(repository, "merge-base", "--is-ancestor", integration_sha, synced_sha) == "")
            self.assertTrue(lane.exists())
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")

            collected = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": synced_sha,
                    "integration_sha": integration_sha,
                },
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertEqual(collected["result"]["integration_sha"], synced_sha)
            self.assertFalse(lane.exists())

    def test_stale_collect_stops_at_conflict_state_in_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            integration = Path(expected["integration"])
            (lane / "tracked.txt").write_text("lane\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane conflict")
            lane_sha = git(lane, "rev-parse", "HEAD")
            (integration / "tracked.txt").write_text("integration\n", encoding="utf-8")
            git(integration, "add", "tracked.txt")
            git(integration, "commit", "-m", "integration conflict")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "conflicted")
            self.assertFalse(result["collected"])
            self.assertEqual(result["conflict_paths"], ["tracked.txt"])
            self.assertEqual(result["integration_sha"], integration_sha)
            self.assertEqual(result["judged_integration_sha"], expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), lane_sha)
            self.assertIn("UU tracked.txt", git(lane, "status", "--porcelain=v1"))

    def test_collect_syncs_when_judged_integration_advanced_through_another_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            judged_integration = expected["integration_head"]
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")
            lane_sha = git(lane, "rev-parse", "HEAD")

            # Another lane collects and advances integration past the judged head.
            self.assertFalse(invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer-2"})["is_error"])
            other = repository / ".agent_state/worktrees/demo/lanes/writer-2"
            (other / "other.txt").write_text("other\n", encoding="utf-8")
            git(other, "add", "other.txt")
            git(other, "commit", "-m", "other lane work")
            other_sha = git(other, "rev-parse", "HEAD")
            collected = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-2",
                    "sha": other_sha,
                    "integration_sha": judged_integration,
                },
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            moved_head = git(repository, "rev-parse", "wave/demo/integration")
            self.assertEqual(moved_head, other_sha)

            # Collecting lane A with its judged comparison point synchronizes and stops.
            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": judged_integration,
                },
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "reconciled")
            self.assertFalse(result["collected"])
            self.assertEqual(result["judged_integration_sha"], judged_integration)
            self.assertEqual(result["integration_sha"], moved_head)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), moved_head)
            synced_sha = result["lane_sha"]
            self.assertNotEqual(synced_sha, lane_sha)
            self.assertTrue(git(repository, "merge-base", "--is-ancestor", moved_head, synced_sha) == "")
            self.assertTrue(lane.exists())

            # Re-judging against the moved head allows the exact collection.
            collected = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": synced_sha,
                    "integration_sha": moved_head,
                },
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertEqual(collected["result"]["integration_sha"], synced_sha)
            self.assertFalse(lane.exists())

    def test_collect_stops_at_unchanged_subject_when_comparison_point_moved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            judged_integration = expected["integration_head"]
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "lane work")

            # Another lane collects and moves integration.
            self.assertFalse(invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer-2"})["is_error"])
            other = repository / ".agent_state/worktrees/demo/lanes/writer-2"
            (other / "other.txt").write_text("other\n", encoding="utf-8")
            git(other, "add", "other.txt")
            git(other, "commit", "-m", "other lane work")
            other_sha = git(other, "rev-parse", "HEAD")
            self.assertFalse(invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-2",
                    "sha": other_sha,
                    "integration_sha": judged_integration,
                },
            )["is_error"])
            moved_head = git(repository, "rev-parse", "wave/demo/integration")

            # Sync the lane so its unchanged subject contains the moved head.
            reconciled = invoke(repository, {"method": "lane_reconcile", "task_id": "demo", "lane_id": "writer-1"})
            self.assertFalse(reconciled["is_error"])
            self.assertEqual(reconciled["result"]["state"], "merged")
            synced_sha = git(repository, "rev-parse", "wave/demo/writer-1")
            self.assertTrue(git(repository, "merge-base", "--is-ancestor", moved_head, synced_sha) == "")

            # The old judged comparison point does not equal current integration:
            # do not collect even though the subject contains current integration.
            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": synced_sha,
                    "integration_sha": judged_integration,
                },
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "comparison_moved")
            self.assertFalse(result["collected"])
            self.assertEqual(result["lane_sha"], synced_sha)
            self.assertEqual(result["judged_integration_sha"], judged_integration)
            self.assertEqual(result["integration_sha"], moved_head)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), moved_head)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer-1"), synced_sha)
            self.assertTrue(lane.exists())

            # Re-judging against the moved head collects the unchanged subject exactly.
            collected = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": synced_sha,
                    "integration_sha": moved_head,
                },
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertEqual(collected["result"]["integration_sha"], synced_sha)
            self.assertFalse(lane.exists())

    def test_collect_preserves_dirty_lane_and_reports_retention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            (lane / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")

            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["state"], "collected")
            self.assertEqual(observed["result"]["integration_sha"], lane_sha)
            self.assertFalse(observed["result"]["cleanup"]["cleaned"])
            self.assertTrue(any("retained: worktree is dirty" in warning for warning in observed["result"]["warnings"]))
            self.assertTrue(lane.exists())
            self.assertEqual((lane / "operator-dirt.txt").read_text(encoding="utf-8"), "preserve\n")
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
            lane_sha = git(lane, "rev-parse", "HEAD")

            observed = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


class CollabOpExtensionLaneDropTests(unittest.TestCase):
    def test_lane_drop_retires_clean_collected_lane_and_records_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            created = invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})
            self.assertFalse(created["is_error"])
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            lane_sha = git(lane, "rev-parse", "HEAD")
            integration_sha = git(repository, "rev-parse", "wave/demo/integration")

            observed = invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "writer"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "operation": "lane-drop",
                    "tool_version": 1,
                    "lane_sha": lane_sha,
                    "disposition": "retired",
                },
            )
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), integration_sha)
            telemetry = repository / ".agent_state/plans/demo/.collab_op/telemetry.jsonl"
            events = [json.loads(line) for line in telemetry.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[-1]["operation"], "lane-drop")
            self.assertEqual(events[-1]["disposition"], "retired")
            self.assertEqual(events[-1]["lane_sha"], lane_sha)

    def test_lane_drop_refuses_when_branch_cleanup_fails_and_leaves_lane_intact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            lane_sha = git(lane, "rev-parse", "HEAD")
            lock = repository / ".git/refs/heads/wave/demo/writer.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("foreign lock\n", encoding="utf-8")

            observed = invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "writer"})

            self.assertTrue(observed["is_error"])
            self.assertTrue(lane.is_dir())
            self.assertEqual(git(lane, "rev-parse", "HEAD"), lane_sha)
            self.assertEqual(git(lane, "status", "--porcelain=v1"), "")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer"), lane_sha)
            self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock\n")

    def test_lane_drop_refuses_dirty_and_uncollected_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "dirty"})
            dirty_lane = repository / ".agent_state/worktrees/demo/lanes/dirty"
            (dirty_lane / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "dirty"})
            self.assertTrue(dirty["is_error"])
            self.assertEqual(dirty["error"]["error"]["code"], "dirty_worktree")
            self.assertTrue(dirty_lane.exists())

            invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "uncollected"})
            uncollected_lane = repository / ".agent_state/worktrees/demo/lanes/uncollected"
            (uncollected_lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(uncollected_lane, "add", "work.txt")
            git(uncollected_lane, "commit", "-m", "uncollected work")
            uncollected = invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "uncollected"})
            self.assertTrue(uncollected["is_error"])
            self.assertEqual(uncollected["error"]["error"]["code"], "lane_uncollected")
            self.assertTrue(uncollected_lane.exists())

    def test_lane_drop_abandon_discards_dirty_uncollected_lane_with_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "uncollected work")
            (lane / "dirty.txt").write_text("discard\n", encoding="utf-8")

            observed = invoke(
                repository,
                {"method": "lane_drop", "task_id": "demo", "lane_id": "writer", "abandon": True},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["disposition"], "abandoned")
            self.assertIn("lane_sha", observed["result"])
            self.assertTrue(any("discarded dirty" in warning for warning in observed["result"]["warnings"]))
            self.assertTrue(any("discarded uncollected" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")

    def test_lane_drop_abandon_unlinks_symlink_and_preserves_aliased_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            git(repository, "worktree", "remove", "--force", str(lane))
            unrelated = base / "unrelated-worktree"
            git(repository, "branch", "operator-preserve", git(repository, "rev-parse", "main"))
            git(repository, "worktree", "add", str(unrelated), "operator-preserve")
            (unrelated / "operator.txt").write_text("preserve\n", encoding="utf-8")
            lane.symlink_to(unrelated, target_is_directory=True)

            observed = invoke(
                repository,
                {"method": "lane_drop", "task_id": "demo", "lane_id": "writer", "abandon": True},
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["disposition"], "abandoned")
            self.assertTrue(any("incomplete" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse(lane.exists())
            self.assertTrue(unrelated.is_dir())
            self.assertEqual((unrelated / "operator.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertEqual(
                git(repository, "rev-parse", "operator-preserve"),
                git(unrelated, "rev-parse", "HEAD"),
            )

    def test_lane_drop_refuses_incomplete_inventory_but_abandon_warns_and_cleans_safe_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            seed_managed_task(repository)
            invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})
            lane = repository / ".agent_state/worktrees/demo/lanes/writer"
            git(repository, "update-ref", "--no-deref", "-d", "refs/heads/wave/demo/writer")

            normal = invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "writer"})
            self.assertTrue(normal["is_error"])
            self.assertEqual(normal["error"]["error"]["code"], "lane_inventory_incomplete")
            self.assertTrue(lane.exists())

            abandoned = invoke(
                repository,
                {"method": "lane_drop", "task_id": "demo", "lane_id": "writer", "abandon": True},
            )
            self.assertFalse(abandoned["is_error"])
            self.assertEqual(abandoned["result"]["disposition"], "abandoned")
            self.assertTrue(any("incomplete" in warning for warning in abandoned["result"]["warnings"]))
            self.assertFalse(lane.exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")


class CollabOpExtensionIntegrationReconcileTests(unittest.TestCase):
    def test_reconcile_rejects_persist_mismatch_before_creating_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            git(repository, "branch", "other", "main")

            observed = invoke(
                repository,
                {
                    "method": "integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair",
                    "persist": "other",
                },
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "persistence_mismatch")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/repair"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_reconcile_requires_clean_and_identity_matching_integration(self) -> None:
        for case in ("dirty", "identity"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                integration = Path(expected["integration"])
                if case == "dirty":
                    (integration / "dirty.txt").write_text("preserve\n", encoding="utf-8")
                else:
                    git(integration, "checkout", "--detach")

                observed = invoke(
                    repository,
                    {
                        "method": "integration_reconcile",
                        "task_id": "demo",
                        "lane_id": "repair",
                        "persist": "main",
                    },
                )

                self.assertTrue(observed["is_error"])
                expected_code = "dirty_worktree" if case == "dirty" else "worktree_identity_mismatch"
                self.assertEqual(observed["error"]["error"]["code"], expected_code)
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_reconcile_requires_one_persistence_checkout_at_direct_branch_tip(self) -> None:
        cases = ("head", "count")
        for case in cases:
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
                        "method": "integration_reconcile",
                        "task_id": "demo",
                        "lane_id": "repair",
                        "persist": "main",
                    },
                )

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "persistence_identity_mismatch")
                self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/repair").exists())

    def test_reconcile_noop_warns_exactly_and_records_telemetry_without_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            seed_task_container(repository)

            observed = invoke(
                repository,
                {
                    "method": "integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair",
                    "persist": "main",
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "ok": True,
                    "operation": "integration-reconcile",
                    "tool_version": 1,
                    "state": "noop",
                    "integration_sha": expected["integration_head"],
                    "persistence_sha": expected["base"],
                    "warnings": ["persistence is already included in integration"],
                },
            )
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/repair"), "")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-reconcile")
            self.assertEqual(event["outcome"], "noop")
            self.assertEqual(event["state"], "noop")
            self.assertEqual(event["persist"], "main")

    def test_reconcile_clean_merge_creates_ordinary_lane_and_leaves_integration(self) -> None:
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
                    "method": "integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair",
                    "persist": "main",
                },
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["operation"], "integration-reconcile")
            self.assertEqual(result["state"], "merged")
            self.assertEqual(result["integration_sha"], expected["integration_head"])
            self.assertEqual(result["persistence_sha"], persistence_sha)
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
            self.assertTrue(
                git(repository, "merge-base", "--is-ancestor", persistence_sha, lane_sha) == ""
            )
            self.assertTrue(
                git(repository, "merge-base", "--is-ancestor", expected["integration_head"], lane_sha) == ""
            )
            self.assertEqual((persistence / "operator-dirt.txt").read_text(encoding="utf-8"), "preserve\n")
            event = last_telemetry_event(repository)
            self.assertEqual(event["operation"], "integration-reconcile")
            self.assertEqual(event["outcome"], "success")
            self.assertEqual(event["state"], "merged")
            self.assertEqual(event["persistence_sha"], persistence_sha)

            collected = invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "repair",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )
            self.assertFalse(collected["is_error"])
            self.assertEqual(collected["result"]["state"], "collected")
            self.assertEqual(collected["result"]["integration_sha"], lane_sha)
            self.assertFalse(
                invoke(repository, {"method": "status", "task_id": "demo"})["result"]["integration"]["stale"]
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
                    "method": "integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair",
                    "persist": "main",
                },
            )

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "conflicted")
            self.assertEqual(result["conflict_paths"], ["tracked.txt"])
            self.assertEqual(result["integration_sha"], integration_sha)
            self.assertEqual(result["persistence_sha"], persistence_sha)
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
                    "method": "integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair",
                    "persist": "main",
                },
            )

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "lane_resource_collision")
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
                    "method": "integration_reconcile",
                    "task_id": "demo",
                    "lane_id": "repair",
                    "persist": "main",
                },
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue(any("telemetry" in warning for warning in observed["result"]["warnings"]))
            self.assertFalse((repository / ".agent_state/plans/demo").exists())


class CollabOpExtensionIntegrationLandTests(unittest.TestCase):
    def test_integration_land_default_commit_preserves_dirt_and_records_landed_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / "stable.txt").write_text("stable\n", encoding="utf-8")
            git(repository, "add", "stable.txt")
            git(repository, "commit", "-m", "stable base")
            expected = seed_managed_task(repository)
            (repository / "stable.txt").write_text("operator unstaged\n", encoding="utf-8")
            (repository / "untracked.txt").write_text("preserve\n", encoding="utf-8")

            observed = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})

            self.assertFalse(observed["is_error"])
            landing = observed["result"]["persistence_sha"]
            self.assertEqual(observed["result"]["operation"], "integration-land")
            self.assertEqual(observed["result"]["integration_sha"], expected["integration_head"])
            self.assertEqual(observed["result"]["landed_sha"], expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/landed"), expected["integration_head"])
            message = git(repository, "show", "-s", "--format=%B", landing)
            self.assertEqual(message, f"Land demo\n\nTask: demo\nLanded: {expected['integration_head']}")
            self.assertEqual(
                git(repository, "rev-parse", f"{landing}^{{tree}}"),
                git(repository, "rev-parse", f"{expected['integration_head']}^{{tree}}"),
            )
            self.assertEqual((repository / "stable.txt").read_text(encoding="utf-8"), "operator unstaged\n")
            self.assertEqual((repository / "untracked.txt").read_text(encoding="utf-8"), "preserve\n")

    def test_integration_land_refuses_stale_index_collision_and_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            (repository / "tracked.txt").write_text("collision\n", encoding="utf-8")
            collision = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})
            self.assertTrue(collision["is_error"])
            self.assertEqual(collision["error"]["error"]["code"], "path_collision")
            git(repository, "restore", "tracked.txt")

            (repository / "index-dirt.txt").write_text("index\n", encoding="utf-8")
            git(repository, "add", "index-dirt.txt")
            staged = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})
            self.assertTrue(staged["is_error"])
            self.assertEqual(staged["error"]["error"]["code"], "dirty_index")
            git(repository, "reset", "--", "index-dirt.txt")
            (repository / "later.txt").write_text("later\n", encoding="utf-8")
            git(repository, "add", "later.txt")
            git(repository, "commit", "-m", "persistence stale")
            stale = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})
            self.assertTrue(stale["is_error"])
            self.assertEqual(stale["error"]["error"]["code"], "stale_persistence")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/landed"), expected["base"])

    def test_integration_land_refuses_ordinary_untracked_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            integration = Path(expected["integration"])
            (integration / "new.txt").write_text("accepted\n", encoding="utf-8")
            git(integration, "add", "new.txt")
            git(integration, "commit", "-m", "add accepted path")
            (repository / "new.txt").write_text("operator\n", encoding="utf-8")

            observed = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "path_collision")
            self.assertEqual((repository / "new.txt").read_text(encoding="utf-8"), "operator\n")

    def test_integration_land_commit_failure_restores_persistence_and_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            before = git(repository, "rev-parse", "main")
            (repository / "operator.txt").write_text("keep\n", encoding="utf-8")
            hook = repository / ".git/hooks/pre-commit"
            hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)

            observed = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "git_error")
            self.assertTrue(observed["error"]["error"]["details"]["rollback"]["restored"])
            self.assertEqual(git(repository, "rev-parse", "main"), before)
            self.assertEqual((repository / "operator.txt").read_text(encoding="utf-8"), "keep\n")
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/landed"), expected["base"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])

    def test_integration_land_refuses_unexpected_tree_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            before = git(repository, "rev-parse", "main")
            hook = repository / ".git/hooks/pre-commit"
            hook.write_text(
                "#!/bin/sh\necho 'hook change' >> tracked.txt\ngit add tracked.txt\n",
                encoding="utf-8",
            )
            hook.chmod(0o755)

            observed = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "git_error")
            self.assertTrue(observed["error"]["error"]["details"]["rollback"]["restored"])
            self.assertEqual(git(repository, "rev-parse", "main"), before)
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/landed"), expected["base"])
            self.assertEqual((repository / "tracked.txt").read_text(encoding="utf-8"), "base\n")
            self.assertEqual(git(repository, "status", "--porcelain=v1"), "?? .agent_state/")

    def test_integration_land_optional_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            observed = invoke(
                repository,
                {"method": "integration_land", "task_id": "demo", "persist": "main", "message": "Ship demo"},
            )
            self.assertFalse(observed["is_error"])
            self.assertEqual(
                git(repository, "show", "-s", "--format=%B", observed["result"]["persistence_sha"]),
                f"Ship demo\n\nTask: demo\nLanded: {expected['integration_head']}",
            )
            git(repository, "update-ref", "refs/heads/main", expected["base"])
            git(repository, "reset", "--hard", expected["base"])
            duplicate = invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})
            self.assertTrue(duplicate["is_error"])
            self.assertEqual(duplicate["error"]["error"]["code"], "duplicate_landing")


class CollabOpExtensionIntegrationRemoveTests(unittest.TestCase):
    def test_integration_remove_requires_exact_report_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            both = invoke(repository, {"method": "integration_remove", "task_id": "demo", "no_report": True, "output_dir": str(Path(temporary) / "report")})
            neither = invoke(repository, {"method": "integration_remove", "task_id": "demo"})
            self.assertTrue(both["is_error"])
            self.assertEqual(both["error"]["error"]["code"], "invalid_report_choice")
            self.assertTrue(neither["is_error"])
            self.assertEqual(neither["error"]["error"]["code"], "invalid_report_choice")

    def test_integration_remove_refuses_active_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            refused = invoke(repository, {"method": "integration_remove", "task_id": "demo", "no_report": True})
            self.assertTrue(refused["is_error"])
            self.assertEqual(refused["error"]["error"]["code"], "active_lanes")
            self.assertTrue(Path(expected["lane"]).exists())
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])

    def test_integration_remove_reports_and_preserves_persistence_after_full_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_managed_task(repository)
            seed_task_container(repository)
            lane = Path(expected["lane"])
            (lane / "work.txt").write_text("work\n", encoding="utf-8")
            git(lane, "add", "work.txt")
            git(lane, "commit", "-m", "work")
            lane_sha = git(lane, "rev-parse", "HEAD")
            self.assertFalse(invoke(
                repository,
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "writer-1",
                    "sha": lane_sha,
                    "integration_sha": expected["integration_head"],
                },
            )["is_error"])
            self.assertFalse(invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})["is_error"])
            report_dir = base / "reports"
            telemetry_before = (
                repository / ".agent_state/plans/demo/.collab_op/telemetry.jsonl"
            ).read_text(encoding="utf-8")

            observed = invoke(
                repository,
                {"method": "integration_remove", "task_id": "demo", "output_dir": str(report_dir)},
            )

            self.assertFalse(observed["is_error"])
            self.assertTrue((report_dir / "collab-report.json").is_file())
            self.assertTrue((report_dir / "collab-telemetry.jsonl").is_file())
            report = json.loads((report_dir / "collab-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["task_id"], "demo")
            self.assertGreaterEqual(report["counts"]["operations"]["lane-collect"], 1)
            self.assertEqual(report["integration_diff"]["base_sha"], expected["base"])
            self.assertGreaterEqual(report["integration_diff"]["commits"], 1)
            self.assertEqual(report["authorities"]["landed"], report["landed_sha"])
            self.assertNotIn("accepted", report["authorities"])
            self.assertNotIn("rates", report)
            self.assertIsInstance(report["lane_durations"], list)
            self.assertIsNotNone(report["task_timing"])
            self.assertGreaterEqual(len(report["timeline"]), 2)
            self.assertEqual(
                (report_dir / "collab-telemetry.jsonl").read_text(encoding="utf-8"),
                telemetry_before,
            )
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(git(repository, "branch", "--list", "main"), "* main")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())
            self.assertTrue((repository / ".agent_state/plans/demo/.collab_op/telemetry.jsonl").is_file())

    def test_integration_remove_refuses_unrecognized_legacy_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "writer-1"})
            self.assertFalse(invoke(repository, {"method": "integration_land", "task_id": "demo", "persist": "main"})["is_error"])
            git(repository, "update-ref", "refs/orchestrate/demo/accepted", expected["integration_head"])

            observed = invoke(repository, {"method": "integration_remove", "task_id": "demo", "no_report": True})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_inventory_incomplete")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/accepted"), expected["integration_head"])

    def test_integration_remove_preserves_dirty_integration_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "writer-1"})
            integration = Path(expected["integration"])
            (integration / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")

            refused = invoke(repository, {"method": "integration_remove", "task_id": "demo", "no_report": True})
            self.assertTrue(refused["is_error"])
            self.assertEqual(refused["error"]["error"]["code"], "dirty_worktree")
            self.assertEqual((integration / "operator-dirt.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])

            abandoned = invoke(
                repository,
                {"method": "integration_remove", "task_id": "demo", "no_report": True, "abandon": True},
            )
            self.assertFalse(abandoned["is_error"])
            self.assertTrue(any("integration retained: worktree is dirty" in warning for warning in abandoned["result"]["warnings"]))
            self.assertTrue(integration.exists())
            self.assertEqual((integration / "operator-dirt.txt").read_text(encoding="utf-8"), "preserve\n")
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            self.assertEqual(git(repository, "branch", "--list", "main"), "* main")

    def test_integration_remove_abandon_cleans_safe_resources_but_never_persistence_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            observed = invoke(
                repository,
                {"method": "integration_remove", "task_id": "demo", "no_report": True, "abandon": True},
            )
            self.assertFalse(observed["is_error"])
            self.assertEqual(observed["result"]["disposition"], "abandoned")
            self.assertEqual(git(repository, "branch", "--list", "main"), "* main")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/integration"), "")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer-1"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo").exists())
            self.assertEqual(git(repository, "rev-parse", "main"), expected["base"])


class CollabOpExtensionMigrationSentinelTests(unittest.TestCase):
    """Interface matrix 1-3: initial success paths and identity preservation."""

    def test_already_current_returns_minimal_result_without_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            self.assertFalse(
                invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "writer-1"})["is_error"]
            )
            refs_before = managed_ref_snapshot(repository)

            first = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
            second = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

            for observed in (first, second):
                self.assertFalse(observed["is_error"])
                result = observed["result"]
                self.assertEqual(result["operation"], "integration-migrate")
                self.assertEqual(result["state"], "already_current")
                self.assertEqual(result["integration_sha"], expected["integration_head"])
                self.assertEqual(
                    set(result.keys()),
                    {"ok", "operation", "tool_version", "state", "integration_sha"},
                )
            self.assertEqual(managed_ref_snapshot(repository), refs_before)
            self.assertIsNone(sentinel_oid(repository))

    def test_acceptance_present_migration_preserves_identities_and_removes_legacy(self) -> None:
        # Acceptance equal to and different from integration, with legacy
        # accepted values differing from integration; canonical integration
        # head stays the sole truth and every fixed identity is preserved.
        for case in ("acceptance_equal", "acceptance_different"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_migratable_legacy(repository)
                if case == "acceptance_different":
                    acceptance = Path(expected["acceptance"])
                    git(repository, "worktree", "remove", str(acceptance))
                    git(repository, "update-ref", "-d", "refs/orchestrate/demo/acceptance-open", expected["integration_head"])
                    git(repository, "worktree", "add", "--detach", str(acceptance), expected["base"])
                    git(repository, "update-ref", "refs/orchestrate/demo/acceptance-open", expected["base"])
                    expected["acceptance"] = str(acceptance.resolve())

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertFalse(observed["is_error"])
                result = observed["result"]
                self.assertEqual(result["operation"], "integration-migrate")
                self.assertEqual(result["state"], "migrated")
                self.assertEqual(result["integration_sha"], expected["integration_head"])
                self.assertEqual(
                    git(repository, "rev-parse", "wave/demo/integration"),
                    expected["integration_head"],
                )
                for ref in (
                    "refs/orchestrate/demo/accepted",
                    "refs/orchestrate/demo/acceptance-open",
                    "refs/orchestrate/demo/user-accepted",
                    "refs/orchestrate/demo/writer-1/base",
                ):
                    self.assertEqual(git(repository, "for-each-ref", "--format=%(refname)", ref), "")
                self.assertIsNone(sentinel_oid(repository))
                self.assertFalse(Path(expected["acceptance"]).exists())
                self.assertNotIn(
                    "acceptance",
                    git(repository, "worktree", "list", "--porcelain"),
                )
                # Fixed identities are preserved exactly.
                self.assertEqual(
                    git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"),
                    expected["base"],
                )
                self.assertEqual(
                    git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                    "refs/heads/main",
                )
                self.assertEqual(
                    git(repository, "rev-parse", "refs/orchestrate/demo/landed"),
                    expected["base"],
                )
                integration = Path(expected["integration"])
                self.assertEqual(git(integration, "rev-parse", "HEAD"), expected["integration_head"])
                self.assertEqual(git(integration, "status", "--porcelain=v1"), "")

    def test_acceptance_absent_migration_removes_exact_legacy_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_migratable_legacy(repository)
            acceptance = Path(expected["acceptance"])
            git(repository, "worktree", "remove", str(acceptance))
            git(repository, "update-ref", "-d", "refs/orchestrate/demo/acceptance-open")

            observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "migrated")
            self.assertEqual(result["integration_sha"], expected["integration_head"])
            self.assertIsNone(sentinel_oid(repository))
            for ref in (
                "refs/orchestrate/demo/accepted",
                "refs/orchestrate/demo/user-accepted",
                "refs/orchestrate/demo/writer-1/base",
            ):
                self.assertEqual(git(repository, "for-each-ref", "--format=%(refname)", ref), "")
            # A canonical worktree is never part of the absent-mode custody;
            # the path stays absent and only new-model refs remain.
            self.assertFalse(acceptance.exists())
            self.assertEqual(
                git(repository, "for-each-ref", "--format=%(refname)", "refs/orchestrate/demo").splitlines(),
                [
                    "refs/orchestrate/demo/integration/base",
                    "refs/orchestrate/demo/landed",
                    "refs/orchestrate/demo/persistence",
                ],
            )


class CollabOpExtensionMigrationPreflightTests(unittest.TestCase):
    """Interface matrix 4-5: every initial refusal and atomic transaction failure."""

    def test_preflight_refuses_every_live_dirty_unknown_and_colliding_state(self) -> None:
        cases = [
            ("full_lane", "active_lanes"),
            ("branch_only", "active_lanes"),
            ("worktree_only", "active_lanes"),
            ("dirty_integration", "dirty_worktree"),
            ("dirty_acceptance", "dirty_worktree"),
            ("unknown_ref", "task_inventory_incomplete"),
            ("root_entry", "task_inventory_incomplete"),
            ("symbolic_legacy", "managed_ref_invalid"),
            ("blob_legacy", "managed_ref_invalid"),
            ("colliding_legacy", "managed_ref_invalid"),
            ("open_without_worktree", "worktree_identity_mismatch"),
            ("worktree_without_open", "worktree_identity_mismatch"),
            ("mismatched_open", "worktree_identity_mismatch"),
            ("missing_persistence", "task_state_invalid"),
            ("symbolic_landed", "managed_ref_invalid"),
        ]
        for case, expected_code in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_managed_task(repository)
                if case != "full_lane":
                    self.assertFalse(
                        invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "writer-1"})["is_error"]
                    )
                git(repository, "update-ref", "refs/orchestrate/demo/accepted", expected["base"])
                if case == "branch_only":
                    git(repository, "update-ref", "refs/heads/wave/demo/writer-1", expected["integration_head"])
                elif case == "worktree_only":
                    git(
                        repository,
                        "worktree",
                        "add",
                        "--detach",
                        str(Path(expected["lane"])),
                        expected["integration_head"],
                    )
                elif case == "dirty_integration":
                    (Path(expected["integration"]) / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")
                elif case == "dirty_acceptance":
                    git(repository, "update-ref", "refs/orchestrate/demo/acceptance-open", expected["integration_head"])
                    git(
                        repository,
                        "worktree",
                        "add",
                        "--detach",
                        str(repository / ".agent_state/worktrees/demo/acceptance"),
                        expected["integration_head"],
                    )
                    (repository / ".agent_state/worktrees/demo/acceptance/operator-dirt.txt").write_text(
                        "preserve\n", encoding="utf-8"
                    )
                elif case == "unknown_ref":
                    git(repository, "update-ref", "refs/orchestrate/demo/unknown", expected["base"])
                elif case == "root_entry":
                    (repository / ".agent_state/worktrees/demo/operator.txt").write_text("keep\n", encoding="utf-8")
                elif case == "symbolic_legacy":
                    git(repository, "update-ref", "-d", "refs/orchestrate/demo/accepted", expected["base"])
                    git(repository, "symbolic-ref", "refs/orchestrate/demo/accepted", "refs/heads/main")
                elif case == "blob_legacy":
                    blob = git(repository, "rev-parse", "HEAD:tracked.txt")
                    git(repository, "update-ref", "refs/orchestrate/demo/accepted", blob)
                elif case == "colliding_legacy":
                    git(repository, "update-ref", "-d", "refs/orchestrate/demo/accepted", expected["base"])
                    git(repository, "update-ref", "refs/orchestrate/demo/accepted/child", expected["base"])
                elif case == "open_without_worktree":
                    git(repository, "update-ref", "refs/orchestrate/demo/acceptance-open", expected["integration_head"])
                elif case == "worktree_without_open":
                    git(repository, "update-ref", "refs/orchestrate/demo/acceptance-open", expected["integration_head"])
                    git(
                        repository,
                        "worktree",
                        "add",
                        "--detach",
                        str(repository / ".agent_state/worktrees/demo/acceptance"),
                        expected["integration_head"],
                    )
                    git(repository, "update-ref", "-d", "refs/orchestrate/demo/acceptance-open")
                elif case == "mismatched_open":
                    git(repository, "update-ref", "refs/orchestrate/demo/acceptance-open", expected["base"])
                    git(
                        repository,
                        "worktree",
                        "add",
                        "--detach",
                        str(repository / ".agent_state/worktrees/demo/acceptance"),
                        expected["integration_head"],
                    )
                elif case == "missing_persistence":
                    git(repository, "symbolic-ref", "--delete", "refs/orchestrate/demo/persistence")
                elif case == "symbolic_landed":
                    landed = git(repository, "rev-parse", "refs/orchestrate/demo/landed")
                    git(repository, "update-ref", "-d", "refs/orchestrate/demo/landed", landed)
                    git(repository, "symbolic-ref", "refs/orchestrate/demo/landed", "refs/heads/main")
                refs_before = managed_ref_snapshot(repository)
                worktrees_before = git(repository, "worktree", "list", "--porcelain")

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], expected_code)
                self.assertEqual(managed_ref_snapshot(repository), refs_before)
                self.assertEqual(git(repository, "worktree", "list", "--porcelain"), worktrees_before)
                self.assertIsNone(sentinel_oid(repository))

    def test_ref_transaction_failure_leaves_refs_and_worktree_intact_without_sentinel(self) -> None:
        for case in ("first_ref", "second_ref"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_migratable_legacy(repository)
                refs_before = managed_ref_snapshot(repository)
                worktrees_before = git(repository, "worktree", "list", "--porcelain")
                locked = "accepted" if case == "first_ref" else "acceptance-open"
                lock = repository / f".git/refs/orchestrate/demo/{locked}.lock"
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text("foreign lock\n", encoding="utf-8")

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "git_error")
                self.assertIsNone(sentinel_oid(repository))
                self.assertEqual(managed_ref_snapshot(repository), refs_before)
                records_after = git(repository, "worktree", "list", "--porcelain")
                self.assertEqual(
                    worktree_block(records_after, expected["acceptance"]),
                    f"worktree {expected['acceptance']}\nHEAD {expected['integration_head']}\ndetached",
                )
                self.assertEqual(
                    worktree_block(records_after, expected["integration"]),
                    worktree_block(worktrees_before, expected["integration"]),
                )
                self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock\n")


class CollabOpExtensionMigrationResumeTests(unittest.TestCase):
    """Interface matrix 6-7: forward-only resume and fail-closed preservation."""

    def test_committed_sentinel_resumes_forward_with_exact_clean_removal(self) -> None:
        for custody in ("present", "already_absent"):
            with self.subTest(case=custody), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_migratable_legacy(repository)
                if custody == "already_absent":
                    git(repository, "worktree", "remove", str(Path(expected["acceptance"])))
                commit_migration_transition(repository, expected)

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertFalse(observed["is_error"])
                result = observed["result"]
                self.assertEqual(result["state"], "migrated")
                self.assertEqual(result["integration_sha"], expected["integration_head"])
                self.assertIsNone(sentinel_oid(repository))
                self.assertFalse(Path(expected["acceptance"]).exists())
                for ref in (
                    "refs/orchestrate/demo/accepted",
                    "refs/orchestrate/demo/acceptance-open",
                    "refs/orchestrate/demo/user-accepted",
                    "refs/orchestrate/demo/writer-1/base",
                ):
                    self.assertEqual(git(repository, "for-each-ref", "--format=%(refname)", ref), "")
                self.assertEqual(
                    git(repository, "rev-parse", "refs/orchestrate/demo/integration/base"),
                    expected["base"],
                )
                self.assertEqual(
                    git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence"),
                    "refs/heads/main",
                )
                self.assertEqual(git(repository, "rev-parse", "refs/orchestrate/demo/landed"), expected["base"])

    def test_resume_preserves_dirty_drifted_or_partial_acceptance_custody(self) -> None:
        cases = [
            ("dirty", "dirty"),
            ("head_drift", "drift"),
            ("path_without_registration", "path_only"),
            ("registration_without_path", "registration_only"),
            ("absent_mode_occupant", "absent_occupant"),
        ]
        for case, kind in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_migratable_legacy(repository)
                acceptance = Path(expected["acceptance"])
                if kind == "absent_occupant":
                    git(repository, "worktree", "remove", str(acceptance))
                    git(repository, "update-ref", "-d", "refs/orchestrate/demo/acceptance-open")
                    absent_refs = [
                        {"ref": "refs/orchestrate/demo/accepted", "sha": expected["base"]},
                        {"ref": "refs/orchestrate/demo/user-accepted", "sha": expected["base"]},
                        {"ref": "refs/orchestrate/demo/writer-1/base", "sha": expected["base"]},
                    ]
                    commit_migration_transition(
                        repository,
                        expected,
                        descriptor=descriptor_dict(expected, acceptance_present=False, legacy_refs=absent_refs),
                    )
                    acceptance.mkdir(parents=True)
                    (acceptance / "occupant.txt").write_text("keep\n", encoding="utf-8")
                else:
                    commit_migration_transition(repository, expected)
                    if kind == "dirty":
                        (acceptance / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")
                    elif kind == "drift":
                        git(acceptance, "checkout", "-q", expected["base"])
                    elif kind == "path_only":
                        git(repository, "worktree", "remove", "--force", str(acceptance))
                        acceptance.mkdir(parents=True)
                        (acceptance / "occupant.txt").write_text("keep\n", encoding="utf-8")
                    elif kind == "registration_only":
                        shutil.rmtree(acceptance)
                blob = sentinel_oid(repository)

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "migration_recovery_required")
                # The sentinel is retained and nothing is destroyed.
                self.assertEqual(sentinel_oid(repository), blob)
                if kind in ("dirty", "drift", "path_only", "absent_occupant"):
                    self.assertTrue(acceptance.exists())
                if kind == "dirty":
                    self.assertEqual(
                        (acceptance / "operator-dirt.txt").read_text(encoding="utf-8"),
                        "preserve\n",
                    )
                if kind in ("path_only", "absent_occupant"):
                    self.assertEqual((acceptance / "occupant.txt").read_text(encoding="utf-8"), "keep\n")

    def test_resume_refuses_drift_live_lanes_reappeared_refs_and_unknown_resources(self) -> None:
        cases = [
            ("integration_moved", "integration"),
            ("base_moved", "base"),
            ("persistence_changed", "persistence"),
            ("landed_changed", "landed"),
            ("legacy_reappeared", "legacy"),
            ("live_lane", "lane"),
            ("unknown_ref", "unknown_ref"),
            ("root_entry", "root_entry"),
            ("dirty_integration", "dirty_integration"),
        ]
        for case, kind in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_migratable_legacy(repository)
                commit_migration_transition(repository, expected)
                if kind == "integration":
                    git(repository, "update-ref", "refs/heads/wave/demo/integration", expected["base"])
                elif kind == "base":
                    git(repository, "update-ref", "refs/orchestrate/demo/integration/base", expected["integration_head"])
                elif kind == "persistence":
                    git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence", "refs/heads/other")
                elif kind == "landed":
                    git(repository, "update-ref", "refs/orchestrate/demo/landed", expected["integration_head"])
                elif kind == "legacy":
                    git(repository, "update-ref", "refs/orchestrate/demo/accepted", expected["base"])
                elif kind == "lane":
                    git(repository, "update-ref", "refs/heads/wave/demo/live", expected["integration_head"])
                elif kind == "unknown_ref":
                    git(repository, "update-ref", "refs/orchestrate/demo/unknown", expected["base"])
                elif kind == "root_entry":
                    (repository / ".agent_state/worktrees/demo/operator.txt").write_text("keep\n", encoding="utf-8")
                elif kind == "dirty_integration":
                    (Path(expected["integration"]) / "operator-dirt.txt").write_text("preserve\n", encoding="utf-8")
                blob = sentinel_oid(repository)
                refs_before = managed_ref_snapshot(repository)

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "migration_recovery_required")
                self.assertEqual(sentinel_oid(repository), blob, "the sentinel must be retained")
                self.assertEqual(managed_ref_snapshot(repository), refs_before)
                if kind == "legacy":
                    self.assertEqual(
                        git(repository, "rev-parse", "refs/orchestrate/demo/accepted"),
                        expected["base"],
                    )
                if kind == "root_entry":
                    self.assertEqual(
                        (repository / ".agent_state/worktrees/demo/operator.txt").read_text(encoding="utf-8"),
                        "keep\n",
                    )

    def test_resume_refuses_active_integration_merge_and_completes_after_abort(self) -> None:
        # A clean-index in-progress merge (MERGE_HEAD present while the index
        # and worktree stay clean) must refuse resume exactly like the initial
        # preflight; a genuine conflicted merge is refused through the same
        # shared inventory check (unmerged index entries). Both preserve the
        # sentinel and acceptance custody, and complete after the merge is
        # aborted.
        for case in ("clean_index_merge", "conflicted_merge"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_migratable_legacy(repository)
                commit_migration_transition(repository, expected)
                integration = Path(expected["integration"])
                if case == "clean_index_merge":
                    git(repository, "branch", "same-tree", expected["base"])
                    source = Path(temporary) / "same-tree-work"
                    git(repository, "worktree", "add", str(source), "same-tree")
                    (source / "tracked.txt").write_text("base\nintegration\n", encoding="utf-8")
                    git(source, "add", "tracked.txt")
                    git(source, "commit", "-m", "same tree as integration")
                    git(repository, "worktree", "remove", str(source))
                    # The merge result equals the integration tree, so the
                    # in-progress merge leaves a clean index.
                    git(integration, "merge", "--no-commit", "same-tree")
                    self.assertEqual(git(integration, "status", "--porcelain=v1"), "")
                else:
                    git(repository, "branch", "merge-src", expected["base"])
                    source = Path(temporary) / "merge-src-work"
                    git(repository, "worktree", "add", str(source), "merge-src")
                    (source / "tracked.txt").write_text("base\nsrc\n", encoding="utf-8")
                    git(source, "add", "tracked.txt")
                    git(source, "commit", "-m", "conflicting change")
                    git(repository, "worktree", "remove", str(source))
                    merged = subprocess.run(
                        ["git", "-C", str(integration), "merge", "merge-src"],
                        text=True,
                        capture_output=True,
                    )
                    self.assertNotEqual(merged.returncode, 0)
                    self.assertNotEqual(git(integration, "ls-files", "--unmerged"), "")
                merge_head = git(integration, "rev-parse", "--verify", "MERGE_HEAD")
                blob = sentinel_oid(repository)

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "migration_recovery_required")
                # The in-progress merge marker, the sentinel, and the
                # acceptance custody are all preserved.
                self.assertEqual(
                    git(integration, "rev-parse", "--verify", "--quiet", "MERGE_HEAD"),
                    merge_head,
                )
                self.assertEqual(sentinel_oid(repository), blob)
                self.assertTrue(Path(expected["acceptance"]).exists())
                # After the merge is aborted the resume completes.
                git(integration, "merge", "--abort")
                retried = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
                self.assertFalse(retried["is_error"])
                self.assertEqual(retried["result"]["state"], "migrated")
                self.assertIsNone(sentinel_oid(repository))
                self.assertFalse(Path(expected["acceptance"]).exists())

    def test_resume_refuses_integration_merge_injected_before_sentinel_deletion(self) -> None:
        # The shared inventory check also guards the final phase: a merge
        # state that appears after the acceptance cleanup but before the
        # sentinel compare-and-swap deletion refuses with the sentinel
        # retained.
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_migratable_legacy(repository)
            commit_migration_transition(repository, expected)
            integration = Path(expected["integration"])
            merge_head_path = git(integration, "rev-parse", "--git-path", "MERGE_HEAD")
            close_harness_for(repository)
            wrapper = write_git_wrapper(
                base,
                MERGE_INJECT_WRAPPER.replace("__MERGE_HEAD_PATH__", merge_head_path).replace(
                    "__SHA__", expected["base"]
                ),
            )
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            try:
                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
            finally:
                os.environ["PATH"] = original_path

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "migration_recovery_required")
            # The injected merge marker and the sentinel are retained; the
            # acceptance custody was already removed by this run.
            self.assertEqual(Path(merge_head_path).read_text(encoding="utf-8").strip(), expected["base"])
            self.assertIsNotNone(sentinel_oid(repository))
            # Resolving the merge state lets the resume complete.
            git(integration, "merge", "--abort")
            retried = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
            self.assertFalse(retried["is_error"])
            self.assertEqual(retried["result"]["state"], "migrated")
            self.assertIsNone(sentinel_oid(repository))


class CollabOpExtensionMigrationSentinelValidationTests(unittest.TestCase):
    """Interface matrix 8 and 11: malformed sentinel resources and exact OIDs."""

    def test_wrong_type_symbolic_and_colliding_sentinels_refuse_without_mutation(self) -> None:
        # A ref and its descendant cannot coexist in the files backend, so a
        # colliding or multiple sentinel namespace is observable as an extra
        # descendant ref; a sentinel pointing at a commit is wrong-type, and a
        # symbolic sentinel is not a direct ref.
        for case, kind in (
            ("commit_type", "commit"),
            ("symbolic", "symbolic"),
            ("descendant_only", "descendant"),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_migratable_legacy(repository)
                if kind == "commit":
                    git(repository, "update-ref", migration_sentinel_ref(), expected["integration_head"])
                elif kind == "symbolic":
                    git(repository, "symbolic-ref", migration_sentinel_ref(), "refs/heads/main")
                elif kind == "descendant":
                    git(repository, "update-ref", f"{migration_sentinel_ref()}/child", expected["base"])
                refs_before = managed_ref_snapshot(repository)

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "migration_recovery_required")
                self.assertEqual(managed_ref_snapshot(repository), refs_before)
                self.assertEqual(
                    git(repository, "rev-parse", "refs/orchestrate/demo/accepted"),
                    expected["base"],
                )

    def test_malformed_descriptors_refuse_without_mutation(self) -> None:
        def mutate(case: str, descriptor: dict[str, object]) -> dict[str, object]:
            if case == "unknown_key":
                descriptor["authority"] = "forged"
            elif case == "missing_key":
                descriptor.pop("nonce")
            elif case == "wrong_type":
                descriptor["integration_sha"] = 42
            elif case == "oid_41":
                descriptor["integration_sha"] = "a" * 41
            elif case == "base_oid_63":
                descriptor["integration_base_sha"] = "b" * 63
            elif case == "bad_version":
                descriptor["version"] = 2
            elif case == "task_mismatch":
                descriptor["task_id"] = "other"
            elif case == "bad_nonce":
                descriptor["nonce"] = "not-a-uuid"
            elif case == "unsorted_refs":
                descriptor["legacy_refs"] = sorted(
                    descriptor["legacy_refs"], key=lambda item: item["ref"], reverse=True
                )
            elif case == "duplicate_refs":
                first = descriptor["legacy_refs"][0]
                descriptor["legacy_refs"] = [first, first] + descriptor["legacy_refs"][1:]
            elif case == "unknown_ref":
                descriptor["legacy_refs"] = [
                    {"ref": "refs/orchestrate/demo/unknown", "sha": "0" * 40}
                ] + descriptor["legacy_refs"]
            elif case == "empty_refs":
                descriptor["legacy_refs"] = []
            elif case == "inconsistent_acceptance":
                descriptor["acceptance_present"] = True
                descriptor["acceptance_sha"] = None
            elif case == "bad_persistence":
                descriptor["persistence_target"] = "refs/heads/not valid"
            elif case == "reordered":
                descriptor = {key: descriptor[key] for key in reversed(list(descriptor.keys()))}
            else:
                raise AssertionError(f"unknown case {case}")
            return descriptor

        cases = (
            "unknown_key",
            "missing_key",
            "wrong_type",
            "oid_41",
            "base_oid_63",
            "bad_version",
            "task_mismatch",
            "bad_nonce",
            "unsorted_refs",
            "duplicate_refs",
            "unknown_ref",
            "empty_refs",
            "inconsistent_acceptance",
            "bad_persistence",
            "reordered",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                repository, _ = seed_repository(Path(temporary))
                expected = seed_migratable_legacy(repository)
                descriptor = mutate(case, descriptor_dict(expected))
                blob = write_descriptor_blob(repository, descriptor)
                git(repository, "update-ref", migration_sentinel_ref(), blob)
                refs_before = managed_ref_snapshot(repository)
                worktrees_before = git(repository, "worktree", "list", "--porcelain")

                observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

                self.assertTrue(observed["is_error"])
                self.assertEqual(observed["error"]["error"]["code"], "migration_recovery_required")
                self.assertEqual(sentinel_oid(repository), blob, "the malformed sentinel is retained")
                self.assertEqual(managed_ref_snapshot(repository), refs_before)
                self.assertEqual(git(repository, "worktree", "list", "--porcelain"), worktrees_before)


class CollabOpExtensionMigrationGateTests(unittest.TestCase):
    """Interface matrix 9: mutator gating and status while the sentinel exists."""

    def test_other_mutators_gate_and_status_reports_recovery_without_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_migratable_legacy(repository)
            commit_migration_transition(repository, expected)
            refs_before = managed_ref_snapshot(repository)

            for request in (
                {"method": "integration_create", "task_id": "demo"},
                {
                    "method": "integration_adopt",
                    "task_id": "demo",
                    "source_branch": "main",
                    "base_sha": expected["base"],
                },
                {"method": "integration_land", "task_id": "demo", "persist": "main"},
                {"method": "integration_reconcile", "task_id": "demo", "persist": "main"},
                {"method": "integration_remove", "task_id": "demo", "no_report": True},
                {"method": "lane_create", "task_id": "demo", "lane_id": "blocked"},
                {"method": "lane_reconcile", "task_id": "demo", "lane_id": "blocked"},
                {
                    "method": "lane_collect",
                    "task_id": "demo",
                    "lane_id": "blocked",
                    "sha": expected["integration_head"],
                },
                {"method": "lane_drop", "task_id": "demo", "lane_id": "blocked"},
            ):
                observed = invoke(repository, request)
                self.assertTrue(observed["is_error"], request)
                self.assertEqual(observed["error"]["error"]["code"], "task_recovery_required", request)
            self.assertEqual(managed_ref_snapshot(repository), refs_before)
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/blocked").exists())
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/blocked"), "")

            status_result = invoke(repository, {"method": "status", "task_id": "demo"})["result"]
            self.assertTrue(status_result["recovery_required"])
            # Status exposes only that recovery is required, never descriptor
            # internals (task_id is the ordinary status identity, not a
            # descriptor disclosure).
            for hidden in (
                "recovery",
                "nonce",
                "legacy_refs",
                "acceptance_present",
                "integration_sha",
                "version",
                "persistence_target",
                "landed_sha",
            ):
                self.assertNotIn(hidden, status_result)
            self.assertEqual(status_result["integration"]["HEAD"], expected["integration_head"])

            # Only integration_migrate may advance the committed migration.
            migrated = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
            self.assertFalse(migrated["is_error"])
            self.assertEqual(migrated["result"]["state"], "migrated")
            self.assertIsNone(sentinel_oid(repository))

            # Normal T003 mutators work again after the migration completes.
            created = invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})
            self.assertFalse(created["is_error"])
            dropped = invoke(repository, {"method": "lane_drop", "task_id": "demo", "lane_id": "writer"})
            self.assertFalse(dropped["is_error"])

    def test_status_and_mutators_gate_on_malformed_sentinel_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            git(repository, "update-ref", f"{migration_sentinel_ref()}/child", expected["base"])

            status_result = invoke(repository, {"method": "status", "task_id": "demo"})["result"]
            self.assertTrue(status_result["recovery_required"])
            self.assertNotIn("recovery", status_result)

            observed = invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "blocked"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_recovery_required")
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/blocked"), "")


class CollabOpExtensionMigrationFaultTests(unittest.TestCase):
    """Interface matrix 10: process loss at every observable boundary."""

    def test_fault_before_ref_transaction_retries_from_original_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_migratable_legacy(repository)
            block = base / "block"
            blocked = base / "blocked"
            counter = base / "update-ref-count"
            close_harness_for(repository)
            wrapper = write_git_wrapper(
                base,
                UPDATE_REF_BLOCK_WRAPPER.replace("__BLOCK__", str(block))
                .replace("__BLOCKED__", str(blocked))
                .replace("__COUNTER__", str(counter))
                .replace("__BLOCK_ON__", "1"),
            )
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            outcome: dict[str, object] = {}

            def run_migrate() -> None:
                try:
                    outcome["observed"] = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
                except Exception as error:  # noqa: BLE001
                    outcome["error"] = error

            try:
                worker = threading.Thread(target=run_migrate, daemon=True)
                worker.start()
                self.assertTrue(
                    wait_until(lambda: blocked.exists()),
                    "migration never blocked at the ref transaction",
                )
                process = _HARNESSES.get(repository.resolve())
                self.assertIsNotNone(process)
                process.kill()
                process.wait(timeout=10)
                close_harness_for(repository)
                # Crash before the transaction: the initial state is intact,
                # no sentinel exists, and no legacy resource was touched.
                self.assertIsNone(sentinel_oid(repository))
                self.assertEqual(
                    git(repository, "rev-parse", "refs/orchestrate/demo/accepted"),
                    expected["base"],
                )
                self.assertEqual(
                    worktree_block(git(repository, "worktree", "list", "--porcelain"), expected["acceptance"]),
                    f"worktree {expected['acceptance']}\nHEAD {expected['integration_head']}\ndetached",
                )
                # A retry from the original state with the real Git completes
                # the migration normally.
                os.environ["PATH"] = original_path
                retried = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
                self.assertFalse(retried["is_error"])
                self.assertEqual(retried["result"]["state"], "migrated")
                self.assertEqual(retried["result"]["integration_sha"], expected["integration_head"])
                # The orphaned transaction from the killed run completes later;
                # its compare-and-swap can no longer create the sentinel or
                # delete the already-removed refs, so it aborts atomically.
                block.write_text("go\n", encoding="utf-8")
                self.assertIsNone(sentinel_oid(repository))
                for ref in (
                    "refs/orchestrate/demo/accepted",
                    "refs/orchestrate/demo/acceptance-open",
                    "refs/orchestrate/demo/user-accepted",
                    "refs/orchestrate/demo/writer-1/base",
                ):
                    self.assertEqual(git(repository, "for-each-ref", "--format=%(refname)", ref), "")
            finally:
                os.environ["PATH"] = original_path

    def test_fault_during_cleanup_resumes_forward_after_worktree_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_migratable_legacy(repository)
            block = base / "block"
            blocked = base / "blocked"
            close_harness_for(repository)
            wrapper = write_git_wrapper(
                base,
                WORKTREE_REMOVE_BLOCK_WRAPPER.replace("__BLOCK__", str(block)).replace(
                    "__BLOCKED__", str(blocked)
                ),
            )
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            outcome: dict[str, object] = {}

            def run_migrate() -> None:
                try:
                    outcome["observed"] = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
                except Exception as error:  # noqa: BLE001
                    outcome["error"] = error

            try:
                worker = threading.Thread(target=run_migrate, daemon=True)
                worker.start()
                self.assertTrue(
                    wait_until(lambda: blocked.exists()),
                    "migration never blocked at worktree removal",
                )
                # The transition committed: the sentinel exists, every legacy
                # ref is gone, and the canonical acceptance worktree is still
                # intact (the removal never ran).
                self.assertIsNotNone(sentinel_oid(repository))
                for ref in (
                    "refs/orchestrate/demo/accepted",
                    "refs/orchestrate/demo/acceptance-open",
                    "refs/orchestrate/demo/user-accepted",
                    "refs/orchestrate/demo/writer-1/base",
                ):
                    self.assertEqual(git(repository, "for-each-ref", "--format=%(refname)", ref), "")
                self.assertTrue(Path(expected["acceptance"]).exists())
                process = _HARNESSES.get(repository.resolve())
                self.assertIsNotNone(process)
                process.kill()
                process.wait(timeout=10)
                close_harness_for(repository)
                # The interrupted removal completes after the crash.
                block.write_text("go\n", encoding="utf-8")
                self.assertTrue(
                    wait_until(lambda: not Path(expected["acceptance"]).exists(), timeout=30),
                    "interrupted worktree removal never completed",
                )
                # Resume forward: the committed sentinel drives the remaining
                # custody check and deletion.
                os.environ["PATH"] = original_path
                resumed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
                self.assertFalse(resumed["is_error"])
                self.assertEqual(resumed["result"]["state"], "migrated")
                self.assertEqual(resumed["result"]["integration_sha"], expected["integration_head"])
                self.assertIsNone(sentinel_oid(repository))
            finally:
                os.environ["PATH"] = original_path

    def test_fault_before_sentinel_deletion_and_response_loss_report_already_current(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, _ = seed_repository(base)
            expected = seed_migratable_legacy(repository)
            block = base / "block"
            blocked = base / "blocked"
            counter = base / "update-ref-count"
            close_harness_for(repository)
            wrapper = write_git_wrapper(
                base,
                UPDATE_REF_BLOCK_WRAPPER.replace("__BLOCK__", str(block))
                .replace("__BLOCKED__", str(blocked))
                .replace("__COUNTER__", str(counter))
                .replace("__BLOCK_ON__", "2"),
            )
            original_path = os.environ["PATH"]
            os.environ["PATH"] = f"{wrapper.parent}:{original_path}"
            outcome: dict[str, object] = {}

            def run_migrate() -> None:
                try:
                    outcome["observed"] = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
                except Exception as error:  # noqa: BLE001
                    outcome["error"] = error

            try:
                worker = threading.Thread(target=run_migrate, daemon=True)
                worker.start()
                self.assertTrue(
                    wait_until(lambda: blocked.exists()),
                    "migration never blocked at the sentinel deletion",
                )
                # The transition committed and cleanup completed; only the
                # sentinel deletion remains.
                blob = sentinel_oid(repository)
                self.assertIsNotNone(blob)
                self.assertFalse(Path(expected["acceptance"]).exists())
                process = _HARNESSES.get(repository.resolve())
                self.assertIsNotNone(process)
                process.kill()
                process.wait(timeout=10)
                close_harness_for(repository)
                # The interrupted deletion completes after the crash: the
                # sentinel disappears before the lost response would arrive.
                block.write_text("go\n", encoding="utf-8")
                self.assertTrue(
                    wait_until(lambda: sentinel_oid(repository) is None, timeout=30),
                    "interrupted sentinel deletion never completed",
                )
                # A retry after response loss observes no sentinel or legacy
                # resources and reports already_current.
                os.environ["PATH"] = original_path
                retried = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})
                self.assertFalse(retried["is_error"])
                self.assertEqual(retried["result"]["state"], "already_current")
                self.assertEqual(retried["result"]["integration_sha"], expected["integration_head"])
                self.assertIsNone(sentinel_oid(repository))
            finally:
                os.environ["PATH"] = original_path

    def test_migrate_succeeds_and_validates_exact_oids_in_sha256_repository(self) -> None:
        probe = tempfile.mkdtemp()
        try:
            check = subprocess.run(
                ["git", "init", "-q", "--object-format=sha256", probe],
                text=True,
                capture_output=True,
            )
            if check.returncode != 0:
                self.skipTest("installed Git cannot init --object-format=sha256")
        finally:
            shutil.rmtree(probe, ignore_errors=True)
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary), object_format="sha256")
            self.assertEqual(len(git(repository, "rev-parse", "HEAD")), 64)
            expected = seed_migratable_legacy(repository)

            observed = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            result = observed["result"]
            self.assertEqual(result["state"], "migrated")
            self.assertEqual(len(result["integration_sha"]), 64)
            self.assertIsNone(sentinel_oid(repository))
            for ref in (
                "refs/orchestrate/demo/accepted",
                "refs/orchestrate/demo/acceptance-open",
                "refs/orchestrate/demo/user-accepted",
                "refs/orchestrate/demo/writer-1/base",
            ):
                self.assertEqual(git(repository, "for-each-ref", "--format=%(refname)", ref), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo/acceptance").exists())

            # Exact object-format validation: a descriptor carrying a
            # 63-character object id is malformed in a SHA-256 repository and
            # is refused without mutation.
            descriptor = descriptor_dict(expected)
            descriptor["integration_base_sha"] = "c" * 63
            blob = write_descriptor_blob(repository, descriptor)
            git(repository, "update-ref", migration_sentinel_ref(), blob)
            refs_before = managed_ref_snapshot(repository)

            refused = invoke(repository, {"method": "integration_migrate", "task_id": "demo"})

            self.assertTrue(refused["is_error"])
            self.assertEqual(refused["error"]["error"]["code"], "migration_recovery_required")
            self.assertEqual(sentinel_oid(repository), blob)
            self.assertEqual(managed_ref_snapshot(repository), refs_before)

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
                        "task_id": "demo",
                    }
                ),
                encoding="utf-8",
            )
            refs_before = managed_ref_snapshot(repository)

            observed = invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "task_busy")
            self.assertEqual(
                observed["error"]["error"]["details"]["held_by"]["pid"],
                os.getpid(),
            )
            self.assertEqual(managed_ref_snapshot(repository), refs_before)
            self.assertEqual(git(repository, "branch", "--list", "wave/demo/writer"), "")
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/writer").exists())
            # status is read-only and is not serialized through the task lock.
            status_result = invoke(repository, {"method": "status", "task_id": "demo"})["result"]
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
                        "task_id": "demo",
                    }
                ),
                encoding="utf-8",
            )

            created = invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "writer"})

            self.assertFalse(created["is_error"])
            self.assertEqual(git(repository, "rev-parse", "wave/demo/writer"), expected["integration_head"])
            self.assertFalse(lock.exists(), "lock was not released in finally")

            # A failing request also releases the lock in finally.
            git(repository, "update-ref", "refs/heads/wave/demo/other", expected["integration_head"])
            refused = invoke(repository, {"method": "lane_create", "task_id": "demo", "lane_id": "other"})
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

            observed = invoke(repository, {"method": "lane_create", "task_id": "other", "lane_id": "writer"})

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
                        "token": "stale-token",
                    }
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
                    f"{json.dumps({'method': 'lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
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
                    {"method": "lane_create", "task_id": "demo", "lane_id": "cross"},
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
                            "token": "foreign-owner-token",
                        }
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
                    {"method": "lane_create", "task_id": "demo", "lane_id": "cross2"},
                )
                self.assertTrue(refused_again["is_error"])
                self.assertEqual(refused_again["error"]["error"]["code"], "task_busy")
                # Once the foreign lock is removed, requests proceed normally.
                planted.unlink()
                ok = send_request(
                    second,
                    {"method": "lane_create", "task_id": "demo", "lane_id": "cross"},
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
                        f"{json.dumps({'method': 'lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
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
                                "token": "foreign-owner-token",
                            }
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
                        {"method": "lane_create", "task_id": "demo", "lane_id": "cross"},
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
                    f"{json.dumps({'method': 'lane_create', 'task_id': 'demo', 'lane_id': 'slow'})}\n"
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
                    {"method": "lane_create", "task_id": "demo", "lane_id": "cross"},
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
                    {"method": "lane_create", "task_id": "demo", "lane_id": "cross"},
                )
                self.assertFalse(retried["is_error"])
                self.assertEqual(git(repository, "rev-parse", "wave/demo/cross"), expected["integration_head"])
            finally:
                os.environ["PATH"] = original_path
                for process in (first, second):
                    if process is not None:
                        close_harness(process)


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

            observed = invoke(repository, {"method": "status"})

            self.assertEqual(observed["tools"], ["collab_op"])
            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {"tool_version": 1, "tasks": ["alpha", "zeta"], "warnings": []},
            )

    def test_task_status_projects_only_integration_and_live_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)

            observed = invoke(repository, {"method": "status", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertEqual(
                observed["result"],
                {
                    "tool_version": 1,
                    "task_id": "demo",
                    "integration": {
                        "worktree": expected["integration"],
                        "HEAD": expected["integration_head"],
                        "stale": False,
                    },
                    "lanes": {
                        "writer-1": {
                            "worktree": expected["lane"],
                            "HEAD": expected["integration_head"],
                        }
                    },
                    "warnings": [],
                },
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
                {"method": "status", "task_id": "demo"},
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

            observed = invoke(repository, {"method": "status", "task_id": "demo"})

            self.assertTrue(observed["result"]["integration"]["stale"])

    def test_missing_persistence_identity_is_conservatively_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            seed_managed_task(repository)
            git(repository, "symbolic-ref", "--delete", "refs/orchestrate/demo/persistence")

            observed = invoke(repository, {"method": "status", "task_id": "demo"})

            self.assertTrue(observed["result"]["integration"]["stale"])
            self.assertTrue(
                any("freshness could not be proven" in warning for warning in observed["result"]["warnings"])
            )

    def test_status_warns_for_dirty_lane_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            expected = seed_managed_task(repository)
            lane = Path(expected["lane"])
            (lane / "dirty.txt").write_text("dirty\n", encoding="utf-8")

            observed = invoke(repository, {"method": "status", "task_id": "demo"})

            self.assertFalse(observed["is_error"])
            self.assertTrue(
                any("lane writer-1 worktree is dirty" in warning for warning in observed["result"]["warnings"])
            )

    def test_refusal_uses_the_structured_pi_error_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))

            observed = invoke(repository, {"method": "status", "task_id": "Not-Safe"})

            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["ok"], False)
            self.assertEqual(observed["error"]["operation"], "status")
            self.assertEqual(observed["error"]["tool_version"], 1)
            self.assertEqual(observed["error"]["error"]["code"], "invalid_identifier")


if __name__ == "__main__":
    unittest.main()
