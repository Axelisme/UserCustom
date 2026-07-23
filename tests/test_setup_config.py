from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupConfigMigrationTests(unittest.TestCase):
    def profile_relatives(self) -> tuple[str, ...]:
        return (
            ".pi/agent/agents/wave-oracle.md", ".pi/agent/agents/wave-implementer.md",
            ".codex/agents/wave-oracle.toml", ".codex/agents/wave-implementer.toml",
            ".claude/agents/wave-oracle.md", ".claude/agents/wave-implementer.md",
        )

    def seed_fixture(self, base: Path) -> tuple[Path, Path]:
        source, home = base / "source", base / "target-home"
        script = source / "setup_scripts" / "setup_config.sh"
        script.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "setup_scripts" / "setup_config.sh", script)
        for relative in ("home/.config/source.conf", "home/.codex/AGENTS.md", "home/.pi/agent/APPEND_SYSTEM.md", "home/.codex/skills/orchestrate/SKILL.md", "home/.pi/agent/skills/orchestrate/SKILL.md", "home/.pi/agent/settings.json", "home/.claude/skills/orchestrate/SKILL.md", "home/.local/include/source.h"):
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("source\n", encoding="utf-8")
        for relative in self.profile_relatives():
            target = source / "home" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("v119 profile\n", encoding="utf-8")
        custom = home / ".pi/agent/agents/custom-profile.md"
        custom.parent.mkdir(parents=True, exist_ok=True)
        custom.write_text("user profile\n", encoding="utf-8")
        return source, home

    def run_setup(self, script: Path, home: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(script)], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True, check=False)

    def test_upgrade_installs_v119_roles_and_retires_legacy_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            for relative in (".pi/agent/agents/wave-reviewer.md", ".codex/agents/wave-reviewer.toml", ".claude/agents/wave-reviewer.md", ".pi/agent/agents/integration-reviewer.md"):
                old = home / relative
                old.parent.mkdir(parents=True, exist_ok=True)
                old.write_text("legacy\n", encoding="utf-8")
            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(all((home / relative).is_file() for relative in self.profile_relatives()))
            self.assertFalse((home / ".pi/agent/agents/wave-reviewer.md").exists())
            self.assertFalse((home / ".codex/agents/wave-reviewer.toml").exists())
            self.assertTrue((home / ".pi/agent/agents/custom-profile.md").is_file())

    def test_invalid_v119_profile_destination_fails_without_retiring_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            invalid = home / ".pi/agent/agents/wave-oracle.md"
            foreign = base / "foreign"
            foreign.mkdir()
            invalid.parent.mkdir(parents=True, exist_ok=True)
            invalid.symlink_to(foreign, target_is_directory=True)
            legacy = home / ".pi/agent/agents/wave-reviewer.md"
            legacy.write_text("legacy\n", encoding="utf-8")
            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(str(invalid), result.stderr)
            self.assertTrue(legacy.is_file())

    def test_user_managed_regular_profile_symlink_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            managed = base / "managed-oracle.md"
            managed.write_text("user-managed\n", encoding="utf-8")
            target = home / ".pi/agent/agents/wave-oracle.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(managed)
            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.read_text(encoding="utf-8"), "user-managed\n")


if __name__ == "__main__":
    unittest.main()
