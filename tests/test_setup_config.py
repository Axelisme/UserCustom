from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from tests import _setup_support as support
except ImportError:  # Direct test-file execution keeps tests/ on sys.path.
    import _setup_support as support


INSTALL_DIRECTORIES = (
    Path(".config"),
    Path(".codex/skills"),
    Path(".pi/agent/skills"),
    Path(".pi/agent/extensions"),
    Path(".claude/skills"),
    Path(".claude/workflows"),
    Path(".codex/agents"),
    Path(".pi/agent/agents"),
    Path(".claude/agents"),
    Path(".local/include"),
)
INSTALL_FILES = (
    Path(".pi/agent/settings.json"),
    Path(".pi/acp.json"),
    Path(".codex/AGENTS.md"),
    Path(".pi/agent/APPEND_SYSTEM.md"),
)


class SetupConfigTests(unittest.TestCase):
    def test_installs_each_configured_source_entry_as_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            for relative in INSTALL_DIRECTORIES:
                source_directory = source / "home" / relative
                for shipped in source_directory.iterdir():
                    destination = home / relative / shipped.name
                    with self.subTest(destination=destination):
                        self.assertTrue(destination.is_symlink(), destination)
                        self.assertTrue(os.path.samefile(destination, shipped))
            for relative in INSTALL_FILES:
                destination = home / relative
                shipped = source / "home" / relative
                with self.subTest(destination=destination):
                    self.assertTrue(destination.is_symlink(), destination)
                    self.assertTrue(os.path.samefile(destination, shipped))

    def test_rerun_leaves_current_symlinks_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))

            first = support.run_setup(source, home)
            before = support.snapshot_home(home)
            second = support.run_setup(source, home)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(support.snapshot_home(home), before)

    def test_existing_file_is_backed_up_before_linking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))
            destination = home / ".codex/agents/mechanical-implementer.toml"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"user edit\n")

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                destination.with_name("mechanical-implementer.toml.bak").read_bytes(),
                b"user edit\n",
            )
            self.assertTrue(
                os.path.samefile(
                    destination,
                    source / "home/.codex/agents/mechanical-implementer.toml",
                )
            )

    def test_existing_directory_is_backed_up_before_linking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))
            destination = home / ".claude/skills/collab"
            destination.mkdir(parents=True)
            (destination / "SKILL.md").write_text("user skill\n", encoding="utf-8")

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            backup = destination.with_name("collab.bak")
            self.assertEqual((backup / "SKILL.md").read_text(encoding="utf-8"), "user skill\n")
            self.assertTrue(
                os.path.samefile(destination, source / "home/.claude/skills/collab")
            )

    def test_foreign_symlink_is_backed_up_before_linking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            destination = home / ".pi/agent/settings.json"
            destination.parent.mkdir(parents=True)
            foreign = base / "foreign-settings.json"
            foreign.write_text("foreign\n", encoding="utf-8")
            destination.symlink_to(foreign)

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            backup = destination.with_name("settings.json.bak")
            self.assertTrue(backup.is_symlink())
            self.assertEqual(backup.resolve(), foreign)
            self.assertTrue(
                os.path.samefile(destination, source / "home/.pi/agent/settings.json")
            )

    def test_every_shipped_skill_is_installed_without_lifecycle_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            collab = home / ".codex/skills/collab"
            self.assertTrue(collab.is_symlink())
            self.assertTrue(
                os.path.samefile(collab, source / "home/.codex/skills/collab")
            )

    def test_setup_runs_from_linked_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            subprocess.run(["git", "-C", str(source), "init"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "Setup Test"],
                check=True,
            )
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-m", "seed setup source"],
                check=True,
                capture_output=True,
            )
            linked = base / "linked"
            subprocess.run(
                ["git", "-C", str(source), "worktree", "add", "--detach", str(linked), "HEAD"],
                check=True,
                capture_output=True,
            )

            result = support.run_setup(linked, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            collab = home / ".codex/skills/collab"
            self.assertTrue(collab.is_symlink())
            self.assertTrue(
                os.path.samefile(
                    collab,
                    linked / "home/.codex/skills/collab",
                )
            )

    def test_setup_disables_destination_only_legacy_agent_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))
            entries = []
            for runtime, extension in (
                (Path(".codex"), ".toml"),
                (Path(".pi/agent"), ".md"),
                (Path(".claude"), ".md"),
            ):
                for profile in ("acceptance-reviewer", "lane-worker"):
                    entries.append(
                        (
                            runtime / "agents" / f"{profile}{extension}",
                            runtime / "disabled-agents" / f"{profile}{extension}.bak",
                            False,
                        )
                    )
            entries.append(
                (
                    Path(".pi/agent/agents/mcp-skill-tester.md"),
                    Path(".pi/agent/disabled-agents/mcp-skill-tester.md.bak"),
                    False,
                )
            )

            for active, _, broken_symlink in entries:
                path = home / active
                path.parent.mkdir(parents=True, exist_ok=True)
                if broken_symlink:
                    path.symlink_to(home / "missing-legacy-skill")
                else:
                    path.write_text("legacy profile\n", encoding="utf-8")

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            for active, disabled, _ in entries:
                with self.subTest(active=active):
                    self.assertFalse(os.path.lexists(home / active))
                    self.assertTrue(os.path.lexists(home / disabled))

    def test_setup_replaces_legacy_contract_reviewer_with_shipped_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))
            for runtime, extension in (
                (Path(".codex"), ".toml"),
                (Path(".pi/agent"), ".md"),
                (Path(".claude"), ".md"),
            ):
                destination = home / runtime / "agents" / f"contract-reviewer{extension}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("legacy profile\n", encoding="utf-8")

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            for runtime, extension in (
                (Path(".codex"), ".toml"),
                (Path(".pi/agent"), ".md"),
                (Path(".claude"), ".md"),
            ):
                relative = runtime / "agents" / f"contract-reviewer{extension}"
                destination = home / relative
                with self.subTest(destination=destination):
                    self.assertTrue(destination.is_symlink())
                    self.assertTrue(os.path.samefile(destination, source / "home" / relative))
                    self.assertEqual(
                        destination.with_name(f"contract-reviewer{extension}.bak").read_text(
                            encoding="utf-8"
                        ),
                        "legacy profile\n",
                    )

    def test_setup_ships_collab(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            collab = home / ".codex/skills/collab"
            self.assertTrue(collab.is_symlink())
            self.assertTrue(os.path.samefile(collab, source / "home/.codex/skills/collab"))

    def test_setup_ships_saved_workflow_through_claude_workflows_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home = support.seed_source(Path(temporary))

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            workflow = home / ".claude/workflows/collab-reviewed-lane.js"
            self.assertTrue(workflow.is_symlink())
            self.assertTrue(
                os.path.samefile(
                    workflow,
                    source / "home/.claude/workflows/collab-reviewed-lane.js",
                )
            )


if __name__ == "__main__":
    unittest.main()
