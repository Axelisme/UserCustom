from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import _setup_support as support


ROOT = Path(__file__).resolve().parents[1]


class SetupConfigCurrentContractTests(unittest.TestCase):
    def test_current_surfaces_install_and_private_assets_survive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            private = {
                home / ".codex/agents/private.toml": b"private codex\n",
                home / ".claude/agents/private.md": b"private claude\n",
                home / ".pi/agent/agents/private.md": b"private pi\n",
                home / ".codex/skills/private/SKILL.md": b"private skill\n",
                home / ".config/private.conf": b"private config\n",
            }
            for path, content in private.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            for layout in support.managed_skill_layouts():
                for skill in support.managed_skill_names():
                    destination = home / layout / skill
                    shipped = source / "home" / layout / skill
                    self.assertTrue(destination.is_symlink())
                    self.assertTrue(os.path.samefile(destination, shipped))
            for relative in support.shipped_profile_relatives():
                destination = home / relative
                shipped = source / "home" / relative
                self.assertTrue(os.path.samefile(destination, shipped))
            for path, content in private.items():
                self.assertEqual(path.read_bytes(), content)

    def test_same_content_install_is_idempotent_without_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)

            first = support.run_setup(source, home)
            second = support.run_setup(source, home)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertFalse((home / ".usercustom-backups").exists())
            self.assertEqual(list(home.rglob("*.bak")), [])

    def test_user_modified_current_file_is_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            destination = home / ".codex/agents/lane-worker.toml"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"user edit\n")

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                destination.with_name("lane-worker.toml.bak").read_bytes(), b"user edit\n"
            )
            self.assertTrue(
                os.path.samefile(destination, source / "home/.codex/agents/lane-worker.toml")
            )

    def test_noncurrent_profile_symlink_is_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            destination = home / ".codex/agents/lane-worker.toml"
            destination.parent.mkdir(parents=True, exist_ok=True)
            foreign = base / "foreign-profile.toml"
            foreign.write_text("foreign\n", encoding="utf-8")
            destination.symlink_to(foreign)

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            backup = destination.with_name("lane-worker.toml.bak")
            self.assertTrue(backup.is_symlink())
            self.assertEqual(backup.resolve(), foreign.resolve())
            self.assertTrue(
                os.path.samefile(destination, source / "home/.codex/agents/lane-worker.toml")
            )

    def test_stale_skill_directory_uses_skills_backup_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            destination = home / ".claude/skills/orchestrate"
            destination.mkdir(parents=True)
            (destination / "SKILL.md").write_text("stale\n", encoding="utf-8")

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(list((home / ".claude/skills").glob("*.bak*")))
            backups = [
                path
                for path in (home / ".usercustom-backups").rglob("SKILL.md")
                if path.read_text(encoding="utf-8") == "stale\n"
            ]
            self.assertEqual(len(backups), 1, backups)
            self.assertTrue(os.path.samefile(destination, source / "home/.claude/skills/orchestrate"))

    def test_setup_refuses_linked_worktree_before_touching_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            git = ("git", "-C", str(source))
            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            }
            subprocess.run([*git, "init", "-q"], check=True, env=env)
            subprocess.run([*git, "add", "-A"], check=True, env=env)
            subprocess.run([*git, "commit", "-qm", "seed"], check=True, env=env)
            linked = base / "linked"
            subprocess.run([*git, "worktree", "add", "-q", "--detach", str(linked)], check=True, env=env)

            result = support.run_setup(linked, home)

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("primary checkout", result.stderr)
            self.assertFalse((home / ".codex/skills/orchestrate").exists())

    def test_current_validation_fails_when_shipped_skill_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            (source / "home/.codex/skills/orchestrate/SKILL.md").unlink()

            result = support.run_setup(source, home)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unusable shipped", result.stderr)


if __name__ == "__main__":
    unittest.main()
