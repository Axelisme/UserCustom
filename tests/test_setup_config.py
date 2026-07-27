from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

import _setup_support as support

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

    def commit_source(self, source: Path) -> None:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        git = ("git", "-C", str(source))
        if not (source / ".git").exists():
            subprocess.run([*git, "init", "-q"], check=True, env=env)
        subprocess.run([*git, "add", "-A"], check=True, env=env)
        subprocess.run([*git, "commit", "-qm", "shipped"], check=True, env=env)

    def backups_under(self, home: Path) -> list[Path]:
        found = [path for path in home.rglob("*.bak")]
        found += [path for path in home.rglob("*.bak~")]
        backup_root = home / ".usercustom-backups"
        if backup_root.is_dir():
            found += [path for path in backup_root.iterdir()]
        return sorted(found)

    def run_setup(
        self, script: Path, home: Path, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(script)],
            env={**os.environ, "HOME": str(home), **(env or {})},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_upgrade_installs_shipped_roles_and_retires_legacy_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            for relative in (
                ".pi/agent/agents/wave-reviewer.md",
                ".codex/agents/wave-reviewer.toml",
                ".claude/agents/wave-reviewer.md",
                ".pi/agent/agents/integration-reviewer.md",
                ".pi/agent/agents/python-module-reviewer.md",
                ".codex/agents/python-module-reviewer.toml",
                ".claude/agents/python-module-reviewer.md",
            ):
                old = home / relative
                old.parent.mkdir(parents=True, exist_ok=True)
                old.write_text("legacy\n", encoding="utf-8")
            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(all((home / relative).is_file() for relative in self.profile_relatives()))
            self.assertFalse((home / ".pi/agent/agents/wave-reviewer.md").exists())
            self.assertFalse((home / ".codex/agents/wave-reviewer.toml").exists())
            for relative in (
                ".pi/agent/agents/python-module-reviewer.md",
                ".codex/agents/python-module-reviewer.toml",
                ".claude/agents/python-module-reviewer.md",
            ):
                retired = home / relative
                self.assertFalse(retired.exists())
                self.assertEqual(
                    retired.with_name(retired.name + ".bak").read_bytes(), b"legacy\n"
                )
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

    def test_dangling_standing_order_links_are_backed_up_and_replaced_before_legacy_retirement(self) -> None:
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
            dangling_targets: dict[str, str] = {}
            for index, relative in enumerate(standing_orders):
                destination = home / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                dangling_target = str(base / f"missing-standing-orders-{index}.md")
                self.assertFalse(Path(dangling_target).exists())
                destination.symlink_to(dangling_target)
                dangling_targets[relative] = dangling_target

            protected_files = {
                home / ".codex/config.toml": b"user codex config\n",
                home / ".pi/agent/user-protected.json": b"user pi data\n",
                home / ".config/user-protected.conf": b"user config\n",
            }
            for protected, content in protected_files.items():
                protected.parent.mkdir(parents=True, exist_ok=True)
                protected.write_bytes(content)

            legacy_profiles = (
                home / ".pi/agent/agents/implementer.md",
                home / ".codex/agents/implementer.toml",
                home / ".claude/agents/implementer.md",
            )
            for legacy in legacy_profiles:
                legacy.parent.mkdir(parents=True, exist_ok=True)
                legacy.write_text("legacy\n", encoding="utf-8")

            retirement_marker = base / "legacy-retirement-started"
            guard_bin = base / "guard-bin"
            guard_bin.mkdir()
            real_rm = shutil.which("rm")
            self.assertIsNotNone(real_rm)
            guarded_rm = guard_bin / "rm"
            guarded_rm.write_text(
                "#!/usr/bin/env bash\n"
                "set -e\n"
                f"test \"$HOME/.codex/AGENTS.md\" -ef \"{source / 'home/.codex/AGENTS.md'}\"\n"
                f"test \"$HOME/.pi/agent/APPEND_SYSTEM.md\" -ef \"{source / 'home/.pi/agent/APPEND_SYSTEM.md'}\"\n"
                "test -L \"$HOME/.codex/AGENTS.md.bak\"\n"
                "test -L \"$HOME/.pi/agent/APPEND_SYSTEM.md.bak\"\n"
                f"printf 'retirement after install\\n' >> \"{retirement_marker}\"\n"
                f"exec \"{real_rm}\" \"$@\"\n",
                encoding="utf-8",
            )
            guarded_rm.chmod(0o755)

            result = self.run_setup(
                source / "setup_scripts/setup_config.sh",
                home,
                env={"PATH": f"{guard_bin}{os.pathsep}{os.environ['PATH']}"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            for relative in standing_orders:
                with self.subTest(standing_order=relative):
                    destination = home / relative
                    source_file = source / "home" / relative
                    backup = destination.with_name(f"{destination.name}.bak")
                    self.assertTrue(destination.is_file())
                    self.assertTrue(
                        os.path.samefile(destination, source_file),
                        f"{destination} must resolve to the shipped standing-order source",
                    )
                    self.assertEqual(destination.read_bytes(), source_file.read_bytes())
                    self.assertTrue(backup.is_symlink(), f"missing link backup: {backup}")
                    self.assertEqual(os.readlink(backup), dangling_targets[relative])

            for protected, content in protected_files.items():
                with self.subTest(protected=protected):
                    self.assertEqual(protected.read_bytes(), content)
            self.assertTrue(retirement_marker.is_file())
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

    def test_setup_refuses_to_run_from_a_linked_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            git = ("git", "-C", str(source))
            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.com",
            }
            subprocess.run([*git, "init", "-q"], check=True, env=env)
            subprocess.run([*git, "add", "-A"], check=True, env=env)
            subprocess.run([*git, "commit", "-qm", "seed"], check=True, env=env)
            worktree = base / "linked-worktree"
            subprocess.run(
                [*git, "worktree", "add", "-q", "--detach", str(worktree)],
                check=True,
                env=env,
            )

            result = self.run_setup(worktree / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("primary checkout", result.stderr)
            self.assertIn(str(source), result.stderr)
            # It must refuse before touching anything under HOME.
            self.assertFalse((home / ".codex/skills/orchestrate").exists())

            primary = self.run_setup(source / "setup_scripts/setup_config.sh", home)
            self.assertEqual(primary.returncode, 0, primary.stderr)
            self.assertTrue((home / ".codex/skills/orchestrate/SKILL.md").is_file())

    def test_replaced_skill_directories_are_retired_outside_the_skill_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            stale = home / ".claude/skills/orchestrate"
            stale.mkdir(parents=True)
            (stale / "SKILL.md").write_text("stale\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            # A `.bak` sibling inside a skills directory is enumerated as a
            # phantom skill by the runtimes, so the old copy moves out of it.
            phantoms = sorted(
                path.name
                for layout in (".claude/skills", ".codex/skills", ".pi/agent/skills")
                for path in (home / layout).glob("*.bak*")
            )
            self.assertEqual(phantoms, [])
            retired = sorted(
                path
                for path in (home / ".usercustom-backups").rglob("SKILL.md")
                if path.read_text(encoding="utf-8") == "stale\n"
            )
            self.assertEqual(len(retired), 1, retired)

    def test_a_checkout_that_only_broke_the_hard_link_refreshes_without_a_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            script = source / "setup_scripts/setup_config.sh"
            self.assertEqual(self.run_setup(script, home).returncode, 0)
            standing_order = source / "home/.codex/AGENTS.md"
            content = standing_order.read_bytes()
            # A checkout or rebase rewrites the file: same content, new inode, so
            # the installed hard link no longer resolves to it.
            standing_order.unlink()
            standing_order.write_bytes(content)
            self.assertFalse(os.path.samefile(standing_order, home / ".codex/AGENTS.md"))

            result = self.run_setup(script, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.backups_under(home), [])
            self.assertTrue(os.path.samefile(standing_order, home / ".codex/AGENTS.md"))

    def test_a_previously_shipped_destination_is_overwritten_without_a_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            shipped = source / "home/.codex/AGENTS.md"
            shipped.write_text("v1 rules\n", encoding="utf-8")
            self.commit_source(source)
            destination = home / ".codex/AGENTS.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("v1 rules\n", encoding="utf-8")
            shipped.write_text("v2 rules\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            # The old content is a blob this repository still has; git is the backup.
            self.assertEqual(self.backups_under(home), [])
            self.assertEqual(destination.read_text(encoding="utf-8"), "v2 rules\n")
            self.assertTrue(os.path.samefile(destination, shipped))

    def test_a_hand_edited_destination_is_still_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            self.commit_source(source)
            destination = home / ".codex/AGENTS.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("my own rules\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            backup = destination.with_name("AGENTS.md.bak")
            self.assertEqual(backup.read_text(encoding="utf-8"), "my own rules\n")
            self.assertTrue(os.path.samefile(destination, source / "home/.codex/AGENTS.md"))

    def test_an_enclosing_repository_never_authorises_deleting_user_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            # The source is not a repository, but it sits inside one — an ordinary
            # shape when $HOME itself is dotfile-managed.  That repository knows
            # nothing about this fleet and must not authorise any deletion.
            unrelated = base / "unrelated.md"
            unrelated.write_text("my own rules\n", encoding="utf-8")
            self.commit_source(base)
            self.assertFalse((source / ".git").exists())
            destination = home / ".codex/AGENTS.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("my own rules\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                destination.with_name("AGENTS.md.bak").read_text(encoding="utf-8"),
                "my own rules\n",
            )

    def test_a_stale_install_link_into_the_source_is_replaced_without_a_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            self.commit_source(source)
            stale = home / ".claude/skills/orchestrate"
            stale.parent.mkdir(parents=True, exist_ok=True)
            # What earlier runs left behind: a link into this same source tree.
            stale.symlink_to(source / "home/.codex/skills/orchestrate")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.backups_under(home), [])
            self.assertEqual(
                stale.resolve(), (source / "home/.claude/skills/orchestrate").resolve()
            )

    def test_a_source_nested_in_someone_elses_worktree_still_installs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outer = base / "outer"
            outer.mkdir()
            (outer / "unrelated.md").write_text("unrelated\n", encoding="utf-8")
            self.commit_source(outer)
            linked = base / "outer-worktree"
            subprocess.run(
                ["git", "-C", str(outer), "worktree", "add", "-q", "--detach", str(linked)],
                check=True,
            )
            # The fleet is not that repository's worktree; it merely sits inside one.
            source, home = self.seed_fixture(linked)

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / ".codex/skills/orchestrate/SKILL.md").is_file())

    def test_a_source_path_containing_a_space_installs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "path with space"
            base.mkdir()
            source, home = self.seed_fixture(base)

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / ".codex/skills/orchestrate/SKILL.md").is_file())

    def test_one_run_writes_its_backups_under_one_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            for layout in (".codex/skills", ".pi/agent/skills"):
                stale = home / layout / "orchestrate"
                stale.mkdir(parents=True)
                (stale / "SKILL.md").write_text("stale\n", encoding="utf-8")
            # A stub clock that moves on every call: one run must read it once.
            stub_bin = base / "stub-bin"
            stub_bin.mkdir()
            counter = base / "clock"
            counter.write_text("0", encoding="utf-8")
            clock = stub_bin / "date"
            clock.write_text(
                "#!/usr/bin/env bash\n"
                f"n=$(cat {counter})\n"
                f"printf '%s' $((n + 1)) > {counter}\n"
                "printf 'stamp-%s\\n' \"$n\"\n",
                encoding="utf-8",
            )
            clock.chmod(0o755)

            result = self.run_setup(
                source / "setup_scripts/setup_config.sh",
                home,
                env={"PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            stamps = sorted(path.name for path in (home / ".usercustom-backups").iterdir())
            self.assertEqual(stamps, ["stamp-0"], stamps)

    def test_an_ordinary_config_directory_keeps_its_sibling_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            shipped = source / "home/.config/nvim/init.lua"
            shipped.parent.mkdir(parents=True, exist_ok=True)
            shipped.write_text("shipped\n", encoding="utf-8")
            existing = home / ".config/nvim"
            existing.mkdir(parents=True)
            (existing / "init.lua").write_text("mine\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            # Only skills directories are enumerated as skills; everything else
            # keeps the sibling backup it has always had.
            self.assertEqual(
                (home / ".config/nvim.bak/init.lua").read_text(encoding="utf-8"), "mine\n"
            )
            self.assertFalse((home / ".usercustom-backups").exists())

    def test_a_staged_but_uncommitted_blob_does_not_authorise_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            self.commit_source(source)
            staged = source / "staged-only.md"
            staged.write_text("only staged\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "staged-only.md"], check=True)
            destination = home / ".codex/AGENTS.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("only staged\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            # `git gc --prune` can drop an unreachable object, so it is no backup.
            self.assertEqual(
                destination.with_name("AGENTS.md.bak").read_text(encoding="utf-8"),
                "only staged\n",
            )

    def test_a_second_directory_backup_rotates_instead_of_nesting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            shipped = source / "home/.config/nvim/init.lua"
            shipped.parent.mkdir(parents=True, exist_ok=True)
            shipped.write_text("shipped\n", encoding="utf-8")
            existing = home / ".config/nvim"
            existing.mkdir(parents=True)
            (existing / "init.lua").write_text("mine\n", encoding="utf-8")
            older = home / ".config/nvim.bak"
            older.mkdir()
            (older / "init.lua").write_text("older\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            # `mv -b` moves a directory *into* an existing `<name>.bak`; the backup
            # must replace it and rotate the older one aside instead.
            self.assertFalse((home / ".config/nvim.bak/nvim").exists())
            self.assertEqual(
                (home / ".config/nvim.bak/init.lua").read_text(encoding="utf-8"), "mine\n"
            )
            rotated = sorted(
                path for path in (home / ".config").glob("nvim.bak.~*~") if path.is_dir()
            )
            self.assertEqual(len(rotated), 1, rotated)
            self.assertEqual(
                (rotated[0] / "init.lua").read_text(encoding="utf-8"), "older\n"
            )

    def test_a_backup_this_run_created_is_not_reported_as_leftover(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            older = home / ".codex/agents/wave-oracle.toml.bak"
            older.parent.mkdir(parents=True, exist_ok=True)
            older.write_text("older profile\n", encoding="utf-8")
            # This one has no backup yet; the run is about to make one.
            hand_edited = home / ".codex/agents/wave-implementer.toml"
            hand_edited.write_text("my own profile\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            fresh = hand_edited.with_name("wave-implementer.toml.bak")
            self.assertEqual(fresh.read_text(encoding="utf-8"), "my own profile\n")
            self.assertIn(str(older), result.stderr)
            # Calling a backup this run just made "leftover" is misleading.
            self.assertNotIn(str(fresh), result.stderr)

    def test_a_backup_rotated_aside_during_the_run_is_still_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            profile = home / ".codex/agents/wave-oracle.toml"
            profile.parent.mkdir(parents=True, exist_ok=True)
            older = profile.with_name("wave-oracle.toml.bak")
            older.write_text("left by an earlier run\n", encoding="utf-8")
            profile.write_text("my edit\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            # `mv -b` renames the pre-existing backup to `<name>.bak~` and puts this
            # run's backup at `<name>.bak`, so a path is not a stable name for a
            # backup across the run: the old data must keep being reported.
            rotated = profile.with_name("wave-oracle.toml.bak~")
            self.assertEqual(
                rotated.read_text(encoding="utf-8"), "left by an earlier run\n"
            )
            self.assertEqual(older.read_text(encoding="utf-8"), "my edit\n")
            self.assertIn(str(rotated), result.stderr)
            self.assertNotIn(f"{older} is", result.stderr)

    def test_a_fresh_hard_link_alias_is_not_reported_as_leftover(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            older = home / ".codex/agents/wave-oracle.toml.bak"
            older.parent.mkdir(parents=True, exist_ok=True)
            older.write_text("shared user profile\n", encoding="utf-8")
            hand_edited = home / ".codex/agents/wave-implementer.toml"
            os.link(older, hand_edited)

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            fresh = hand_edited.with_name("wave-implementer.toml.bak")
            self.assertTrue(os.path.samefile(older, fresh))
            self.assertIn(f"notice: {older} is", result.stderr)
            self.assertNotIn(f"notice: {fresh} is", result.stderr)

    def test_an_unidentifiable_existing_backup_fails_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            backup = home / ".codex/agents/wave-oracle.toml.bak"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text("older profile\n", encoding="utf-8")
            stub_bin = base / "stub-bin"
            stub_bin.mkdir()
            stat = stub_bin / "stat"
            stat.write_text(
                "#!/usr/bin/env bash\n"
                f"if [[ \"$*\" == *{backup}* ]]; then exit 1; fi\n"
                "exec /usr/bin/stat \"$@\"\n",
                encoding="utf-8",
            )
            stat.chmod(0o755)

            result = self.run_setup(
                source / "setup_scripts/setup_config.sh",
                home,
                env={"PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"cannot identify installed backup: {backup}", result.stderr)

    def test_backups_left_in_an_agents_directory_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            leftover = home / ".codex/agents/wave-oracle.toml.bak"
            leftover.parent.mkdir(parents=True, exist_ok=True)
            leftover.write_text("older profile\n", encoding="utf-8")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(leftover), result.stderr)
            self.assertIn("leftover backup", result.stderr)
            self.assertTrue(leftover.is_file())

    def test_backups_left_in_a_skill_tree_by_older_runs_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_fixture(base)
            phantom = home / ".claude/skills/orchestrate.bak"
            phantom.parent.mkdir(parents=True, exist_ok=True)
            phantom.symlink_to(source / "home/.codex/skills/orchestrate")

            result = self.run_setup(source / "setup_scripts/setup_config.sh", home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(phantom), result.stderr)
            self.assertIn("stale skill", result.stderr)
            # Reported, never deleted: it is the user's data.
            self.assertTrue(phantom.is_symlink())


class RefreshBeforeLegacyRetirementTests(unittest.TestCase):
    """Retirement is destructive, so replacements must be installed and validated first.

    Each test shadows ``rm`` to run its assertions at the exact moment legacy
    retirement begins, then re-asserts the end state after setup returns.
    """

    private_profiles = {
        ".codex/agents/user-private.toml": b"private Codex profile\n",
        ".claude/agents/user-private.md": b"private Claude profile\n",
        ".pi/agent/agents/user-private.md": b"private Pi profile\n",
    }

    def seed_untouchables(self, home: Path) -> dict[Path, bytes]:
        """User-owned files setup must carry through without editing or deleting."""
        untouchable = {home / name: content for name, content in self.private_profiles.items()}
        untouchable[home / ".codex/skills/user-private/SKILL.md"] = b"private skill\n"
        untouchable[home / ".config/user-private.conf"] = b"private config\n"
        for path, content in untouchable.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return untouchable

    def seed_legacy(self, home: Path) -> Path:
        legacy = home / ".codex/agents/implementer.toml"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("legacy identity\n", encoding="utf-8")
        return legacy

    def test_every_shipped_profile_is_exact_before_legacy_retirement(self) -> None:
        for runtime, layout in support.PROFILE_LAYOUTS.items():
            suffix = ".toml" if runtime == "codex" else ".md"
            relative = layout / f"repo-investigator{suffix}"
            for state in ("stale", "foreign", "dangling"):
                with (
                    self.subTest(runtime=runtime, state=state),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    base = Path(temporary)
                    source, home = support.seed_source(base)
                    destination = home / relative
                    prior_bytes, prior_link = support.seed_destination(
                        base, destination, state
                    )
                    untouchable = self.seed_untouchables(home)
                    legacy = self.seed_legacy(home)

                    shipped = support.shipped_profile_relatives()
                    checks = [
                        f"if ! [ -f {shlex.quote(str(home / each))} ] || "
                        f"! [ {shlex.quote(str(home / each))} -ef "
                        f"{shlex.quote(str(source / 'home' / each))} ]; then "
                        f"printf '%s\\n' 'profile not exact before retirement: {each}' >&2; "
                        "exit 91; fi"
                        for each in shipped
                    ]
                    checks.append(
                        support.backup_check(base, destination, prior_bytes, prior_link)
                    )
                    guard_bin, marker = support.guard_rm(base, checks)

                    result = support.run_setup(
                        source, home, support.guarded_path(guard_bin)
                    )

                    self.assertEqual(
                        result.returncode,
                        0,
                        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
                    )
                    self.assertTrue(marker.is_file(), "legacy retirement never ran")
                    self.assertFalse(legacy.exists())
                    for each in shipped:
                        installed = home / each
                        self.assertTrue(installed.is_file(), installed)
                        self.assertTrue(
                            os.path.samefile(installed, source / "home" / each),
                            f"{installed} must exact-link to its shipped source",
                        )

                    backup = destination.with_name(destination.name + ".bak")
                    if prior_bytes is not None:
                        self.assertEqual(backup.read_bytes(), prior_bytes)
                    else:
                        self.assertTrue(backup.is_symlink())
                        self.assertEqual(os.readlink(backup), prior_link)
                    for path, content in untouchable.items():
                        self.assertEqual(path.read_bytes(), content, path)

    def test_every_shipped_skill_link_is_exact_before_legacy_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            installed = [
                layout / skill
                for layout in support.managed_skill_layouts()
                for skill in support.managed_skill_names()
            ]

            # Alternate the two ways an installed skill link goes wrong.
            for index, relative in enumerate(installed):
                destination = home / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if index % 2:
                    target = base / f"missing-skill-{index}"
                else:
                    target = base / f"stale-skill-{index}"
                    target.mkdir()
                    (target / "SKILL.md").write_text("stale foreign skill\n", encoding="utf-8")
                destination.symlink_to(target, target_is_directory=True)

            untouchable = self.seed_untouchables(home)
            legacy = self.seed_legacy(home)
            settings = home / ".pi/agent/settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_bytes(b'{"private": true}\n')

            checks = []
            for relative in installed:
                destination = home / relative
                checks.append(
                    f'test {shlex.quote(str(destination))} -ef '
                    f'{shlex.quote(str(source / "home" / relative))}'
                )
                checks.append(f'test -f {shlex.quote(str(destination / "SKILL.md"))}')
            guard_bin, marker = support.guard_rm(base, checks)

            result = support.run_setup(source, home, support.guarded_path(guard_bin))

            self.assertEqual(
                result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
            self.assertTrue(marker.is_file(), "legacy retirement never ran")
            self.assertFalse(legacy.exists())
            for relative in installed:
                with self.subTest(relative=relative.as_posix()):
                    destination = home / relative
                    shipped = source / "home" / relative
                    self.assertTrue(destination.is_symlink())
                    self.assertTrue(os.path.samefile(destination, shipped))
                    self.assertEqual(
                        (destination / "SKILL.md").read_bytes(),
                        (shipped / "SKILL.md").read_bytes(),
                    )
            for path, content in untouchable.items():
                self.assertEqual(path.read_bytes(), content, path)
            self.assertEqual(
                settings.with_name("settings.json.bak").read_bytes(), b'{"private": true}\n'
            )

    def test_a_destination_that_drifts_after_install_fails_before_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            script = source / "setup_scripts/setup_config.sh"
            original = script.read_text(encoding="utf-8")
            boundary = (
                "validate_orchestrate_profile_destinations\n"
                "remove_obsolete_orchestrate_profiles"
            )
            self.assertEqual(original.count(boundary), 1, "setup lost its validation boundary")

            drifted = home / ".codex/agents/contract-planner.toml"
            missing = base / "missing-after-install"
            script.write_text(
                original.replace(
                    boundary,
                    f"rm -f {shlex.quote(str(drifted))}\n"
                    f"ln -s {shlex.quote(str(missing))} {shlex.quote(str(drifted))}\n" + boundary,
                ),
                encoding="utf-8",
            )
            legacy = self.seed_legacy(home)

            result = support.run_setup(source, home)

            self.assertNotEqual(
                result.returncode,
                0,
                "setup accepted a drifted destination and retired legacy anyway",
            )
            self.assertIn("contract-planner", result.stderr)
            self.assertTrue(legacy.is_file(), "validation must fail before retirement")


if __name__ == "__main__":
    unittest.main()
