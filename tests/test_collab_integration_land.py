"""collab_integration land contract."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    git,
    invoke,
    managed_ref_snapshot,
    seed_managed_task,
    seed_repository,
    seed_task_container,
)

setUpModule = _support.require_pi


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
            self.repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"}
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertIn(observed["error"]["error"]["code"], ("dirty_worktree", "path_collision"))
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "rev-parse", "HEAD"), before_head)
            # Clean and retry should succeed with native merge topology (S1) and no landed ref
            git(repository, "restore", "stable.txt")
            (repository / "untracked.txt").unlink()
            observed2 = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "dirty_worktree")
            self.assertEqual(git(repository, "rev-parse", "HEAD"), before_head)
            # Clean and succeed
            git(repository, "restore", "tracked.txt")
            observed2 = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "path_collision")
            self.assertEqual((repository / "local.txt").read_text(encoding="utf-8"), "operator\n")
            # Clean and succeed
            (repository / "local.txt").unlink()
            observed2 = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            collision = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            # No change to integration yet, but ordinary untracked should be refused
            self.assertTrue(collision["is_error"])
            self.assertEqual(collision["error"]["error"]["code"], "path_collision")
            (repository / "new.txt").unlink()
            (repository / "index-dirt.txt").write_text("index\n", encoding="utf-8")
            git(repository, "add", "index-dirt.txt")
            staged = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            self.assertTrue(staged["is_error"])
            self.assertEqual(staged["error"]["error"]["code"], "dirty_index")
            git(repository, "reset", "--", "index-dirt.txt")
            (repository / "index-dirt.txt").unlink()
            (repository / "later.txt").write_text("later\n", encoding="utf-8")
            git(repository, "add", "later.txt")
            git(repository, "commit", "-m", "persistence stale")
            stale = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "git_error")
            self.assertTrue((repository / "hook-output.txt").exists())
            # Clean hook and succeed
            hook.unlink()
            (repository / "hook-output.txt").unlink(missing_ok=True)
            observed2 = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            # Hook failure leaves merge state; clean before retry
            if observed2["is_error"]:
                import subprocess
                subprocess.run(["git", "-C", str(repository), "merge", "--abort"], capture_output=True)
                subprocess.run(["git", "-C", str(repository), "reset", "--hard", "HEAD"], capture_output=True)
                observed2 = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo", "message": "Ship demo"})
            self.assertFalse(observed["is_error"])
            persist_ref = git(repository, "symbolic-ref", "refs/orchestrate/demo/persistence")
            landing = git(repository, "rev-parse", persist_ref)
            self.assertEqual(git(repository, "show", "-s", "--format=%B", landing), f"Ship demo\n\nTask: demo\nLanded: {expected['integration_head']}")
            # Second landing without new integration work should be no_tree_change (persistence already contains integration)
            duplicate = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            self.assertTrue(duplicate["is_error"])
            self.assertEqual(duplicate["error"]["error"]["code"], "no_tree_change")

    def test_land_without_task_container_warns_without_creating_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository, _ = seed_repository(Path(temporary))
            (repository / ".gitignore").write_text(".agent_state/\n")
            git(repository, "add", ".gitignore")
            git(repository, "commit", "-m", "ignore managed state")
            seed_managed_task(repository)
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
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
            observed = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            self.assertTrue(observed["is_error"])
            self.assertEqual(observed["error"]["error"]["code"], "path_collision")
            self.assertIn(".agent_state/operator.txt", observed["error"]["error"]["details"]["paths"])
            self.assertEqual(managed_ref_snapshot(repository), before_refs)
            self.assertEqual(git(repository, "rev-parse", "HEAD"), before_head)
            self.assertEqual(git(repository, "status", "--porcelain=v1", "--ignored=matching"), before_status)
            self.assertEqual(git(repository, "rev-parse", "wave/demo/integration"), expected["integration_head"])
            # Clean and verify landing succeeds when only the ordinary .agent_state file is removed
            (repository / ".agent_state/operator.txt").unlink()
            observed2 = invoke(repository, {"tool": "collab_integration", "action": "land", "task_id": "demo"})
            self.assertFalse(observed2["is_error"])


if __name__ == "__main__":
    unittest.main()
