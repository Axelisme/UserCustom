from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupConfigMigrationTests(unittest.TestCase):
    def wave_profile_relatives(self) -> tuple[str, ...]:
        return (
            ".pi/agent/agents/wave-implementer.md",
            ".pi/agent/agents/wave-reviewer.md",
            ".codex/agents/wave-implementer.toml",
            ".codex/agents/wave-reviewer.toml",
            ".claude/agents/wave-implementer.md",
            ".claude/agents/wave-reviewer.md",
        )

    def wave_paths(self, home: Path) -> tuple[Path, ...]:
        return tuple(home / relative for relative in self.wave_profile_relatives())

    def seed_fixture(self, base: Path) -> tuple[Path, Path, tuple[str, ...], Path]:
        source = base / "source"
        home = base / "target-home"
        script = source / "setup_scripts" / "setup_config.sh"
        script.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "setup_scripts" / "setup_config.sh", script)

        def write(relative: str, text: str = "source\n") -> None:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        for relative in (
            "home/.config/source.conf",
            "home/.codex/AGENTS.md",
            "home/.codex/skills/orchestrate/SKILL.md",
            "home/.pi/agent/settings.json",
            "home/.pi/agent/APPEND_SYSTEM.md",
            "home/.pi/agent/skills/orchestrate/SKILL.md",
            "home/.claude/skills/orchestrate/SKILL.md",
            "home/.local/include/source.h",
        ):
            write(relative)
        for relative in (
            "home/.pi/agent/agents/wave-implementer.md",
            "home/.pi/agent/agents/wave-reviewer.md",
            "home/.codex/agents/wave-implementer.toml",
            "home/.codex/agents/wave-reviewer.toml",
            "home/.claude/agents/wave-implementer.md",
            "home/.claude/agents/wave-reviewer.md",
        ):
            write(relative, "wave replacement\n")

        old = (
            "target-home/.pi/agent/agents/implementer.md",
            "target-home/.pi/agent/agents/reviewer.md",
            "target-home/.codex/agents/implementer.toml",
            "target-home/.codex/agents/reviewer.toml",
            "target-home/.claude/agents/implementer.md",
            "target-home/.claude/agents/reviewer.md",
        )
        for relative in old:
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("obsolete\n", encoding="utf-8")
        custom = home / ".pi" / "agent" / "agents" / "custom-profile.md"
        custom.parent.mkdir(parents=True, exist_ok=True)
        custom.write_text("user profile\n", encoding="utf-8")
        return source, home, old, custom

    def run_setup(self, script: Path, home: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(script)],
            env={**os.environ, "HOME": str(home)},
            check=False,
            capture_output=True,
            text=True,
        )

    def test_upgrade_removes_only_exact_legacy_orchestrate_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home, old, custom = self.seed_fixture(Path(temporary))
            result = self.run_setup(source / "setup_scripts" / "setup_config.sh", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            for relative in old:
                self.assertFalse((Path(temporary) / relative).exists(), relative)
            for relative in (
                "target-home/.pi/agent/agents/wave-implementer.md",
                "target-home/.pi/agent/agents/wave-reviewer.md",
                "target-home/.codex/agents/wave-implementer.toml",
                "target-home/.codex/agents/wave-reviewer.toml",
                "target-home/.claude/agents/wave-implementer.md",
                "target-home/.claude/agents/wave-reviewer.md",
            ):
                self.assertTrue((Path(temporary) / relative).is_file(), relative)
            self.assertTrue(custom.is_file())
            self.assertEqual(custom.read_text(encoding="utf-8"), "user profile\n")

    def test_each_invalid_wave_directory_symlink_fails_independently(self) -> None:
        for invalid_relative in self.wave_profile_relatives():
            with self.subTest(invalid_relative=invalid_relative):
                with tempfile.TemporaryDirectory() as temporary:
                    base = Path(temporary)
                    source, home, old, custom = self.seed_fixture(base)
                    wave_paths = self.wave_paths(home)
                    invalid_path = home / invalid_relative
                    foreign_directory = base / "foreign-profile-directory"
                    foreign_directory.mkdir()
                    invalid_path.parent.mkdir(parents=True, exist_ok=True)
                    invalid_path.symlink_to(foreign_directory, target_is_directory=True)
                    result = self.run_setup(
                        source / "setup_scripts" / "setup_config.sh", home
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unusable wave profile destination", result.stderr)
                    self.assertIn(str(invalid_path), result.stderr)
                    for relative in old:
                        self.assertTrue((base / relative).is_file(), relative)
                    self.assertTrue(custom.is_file())
                    self.assertEqual(custom.read_text(encoding="utf-8"), "user profile\n")
                    for path in wave_paths:
                        if path == invalid_path:
                            self.assertTrue(path.is_symlink())
                        else:
                            self.assertTrue(path.is_file(), path)

    def test_user_managed_regular_profile_symlink_is_usable_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home, old, _ = self.seed_fixture(base)
            managed = base / "user-managed-wave-implementer.md"
            managed.write_text("user-managed\n", encoding="utf-8")
            managed_path = self.wave_paths(home)[0]
            managed_path.parent.mkdir(parents=True, exist_ok=True)
            managed_path.symlink_to(managed)
            result = self.run_setup(source / "setup_scripts" / "setup_config.sh", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(managed_path.is_symlink())
            self.assertEqual(managed_path.read_text(encoding="utf-8"), "user-managed\n")
            for relative in old:
                self.assertFalse((base / relative).exists(), relative)
            self.assertTrue(all(path.is_file() for path in self.wave_paths(home)))

    def test_failed_upgrade_retains_all_legacy_profiles_until_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, home, old, custom = self.seed_fixture(Path(temporary))
            # Fail after Codex/Pi installation starts but before Claude installation and
            # before the retirement transaction at the end of setup_config.sh.
            blocked_skills = home / ".claude" / "skills"
            blocked_skills.parent.mkdir(parents=True, exist_ok=True)
            blocked_skills.write_text("blocking destination\n", encoding="utf-8")
            result = self.run_setup(source / "setup_scripts" / "setup_config.sh", home)
            self.assertNotEqual(result.returncode, 0)
            for relative in old:
                self.assertTrue((Path(temporary) / relative).is_file(), relative)
            self.assertTrue(
                (home / ".pi" / "agent" / "agents" / "wave-implementer.md").is_file()
            )
            self.assertTrue(custom.is_file())


if __name__ == "__main__":
    unittest.main()
