"""collab_integration_adopt."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests import _support
from tests._collab_support import (
    commit_agent_state_ignore,
    git,
    invoke,
    last_telemetry_event,
    seed_canonical,
    seed_donor,
    seed_repository,
    seed_task_container,
)

setUpModule = _support.require_pi


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


if __name__ == "__main__":
    unittest.main()
