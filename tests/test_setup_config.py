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

    def test_foreign_standing_order_links_are_replaced_exactly_before_legacy_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            for relative in (
                ".pi/agent/agents/wave-reviewer.md",
                ".codex/agents/wave-reviewer.toml",
                ".claude/agents/wave-reviewer.md",
            ):
                reviewer = source / "home" / relative
                reviewer.parent.mkdir(parents=True, exist_ok=True)
                reviewer.write_text("v119 reviewer profile\n", encoding="utf-8")

            standing_orders = (
                ".codex/AGENTS.md",
                ".pi/agent/APPEND_SYSTEM.md",
            )
            for index, relative in enumerate(standing_orders):
                foreign = base / f"foreign-standing-orders-{index}.md"
                foreign.write_text(f"foreign {index}\n", encoding="utf-8")
                destination = home / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(foreign)

            protected_codex_config = home / ".codex/config.toml"
            protected_codex_config.write_text("user codex config\n", encoding="utf-8")
            protected_pi_settings = home / ".pi/agent/settings.json"
            protected_pi_settings.parent.mkdir(parents=True, exist_ok=True)
            protected_pi_settings.write_text("user pi settings\n", encoding="utf-8")
            protected_config = home / ".config/user-protected.conf"
            protected_config.parent.mkdir(parents=True, exist_ok=True)
            protected_config.write_text("user config\n", encoding="utf-8")

            legacy_profiles = (
                home / ".pi/agent/agents/implementer.md",
                home / ".codex/agents/implementer.toml",
                home / ".claude/agents/implementer.md",
            )
            for legacy in legacy_profiles:
                legacy.parent.mkdir(parents=True, exist_ok=True)
                legacy.write_text("legacy\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)
            self.assertEqual(result.returncode, 0, result.stderr)

            for relative in standing_orders:
                with self.subTest(standing_order=relative):
                    destination = home / relative
                    source_file = source / "home" / relative
                    self.assertTrue(destination.is_file())
                    self.assertTrue(
                        os.path.samefile(destination, source_file),
                        f"{destination} must resolve to the shipped standing-order source",
                    )
                    self.assertEqual(destination.read_bytes(), source_file.read_bytes())

            self.assertEqual(
                protected_codex_config.read_bytes(), b"user codex config\n"
            )
            self.assertEqual(protected_config.read_bytes(), b"user config\n")
            self.assertEqual(
                protected_pi_settings.with_name("settings.json.bak").read_bytes(),
                b"user pi settings\n",
            )
            self.assertTrue(all(not legacy.exists() for legacy in legacy_profiles))

    def test_stale_or_divergent_orchestrate_destinations_are_relinked_before_legacy_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)

            foreign_skill = base / "foreign-orchestrate"
            foreign_skill.mkdir()
            (foreign_skill / "SKILL.md").write_text("stale skill\n", encoding="utf-8")
            skill_destination = home / ".codex/skills/orchestrate"
            skill_destination.parent.mkdir(parents=True, exist_ok=True)
            skill_destination.symlink_to(foreign_skill, target_is_directory=True)

            foreign_profile = base / "foreign-wave-oracle.md"
            foreign_profile.write_text("stale profile\n", encoding="utf-8")
            symlink_destination = home / ".pi/agent/agents/wave-oracle.md"
            symlink_destination.parent.mkdir(parents=True, exist_ok=True)
            symlink_destination.symlink_to(foreign_profile)

            divergent_destination = home / ".codex/agents/wave-implementer.toml"
            divergent_destination.parent.mkdir(parents=True, exist_ok=True)
            divergent_destination.write_text("divergent bytes\n", encoding="utf-8")

            legacy_profiles = (
                home / ".pi/agent/agents/wave-reviewer.md",
                home / ".codex/agents/wave-reviewer.toml",
                home / ".claude/agents/wave-reviewer.md",
            )
            for legacy in legacy_profiles:
                legacy.parent.mkdir(parents=True, exist_ok=True)
                legacy.write_text("legacy\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)
            self.assertEqual(result.returncode, 0, result.stderr)

            source_skill = source / "home/.codex/skills/orchestrate"
            self.assertTrue(skill_destination.is_symlink())
            self.assertEqual(skill_destination.resolve(), source_skill.resolve())
            self.assertEqual(
                (skill_destination / "SKILL.md").read_bytes(),
                (source_skill / "SKILL.md").read_bytes(),
            )

            for relative in (
                ".pi/agent/agents/wave-oracle.md",
                ".codex/agents/wave-implementer.toml",
            ):
                destination = home / relative
                source_profile = source / "home" / relative
                self.assertTrue(destination.is_file())
                self.assertTrue(os.path.samefile(destination, source_profile))
                self.assertEqual(destination.read_bytes(), source_profile.read_bytes())

            self.assertTrue(all(not legacy.exists() for legacy in legacy_profiles))


if __name__ == "__main__":
    unittest.main()
