from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from tests import _setup_support as support
    from tests._orchestrate_version import SOURCE_SKILL_VERSION
except ImportError:  # Direct test-file execution keeps tests/ on sys.path.
    import _setup_support as support
    from _orchestrate_version import SOURCE_SKILL_VERSION


ROOT = Path(__file__).resolve().parents[1]


class SetupCutoverContractTests(unittest.TestCase):
    def test_release_verification_failure_precedes_retired_removal(self) -> None:
        for logical_layout in ("codex",):
            with (
                self.subTest(logical_layout=logical_layout),
                tempfile.TemporaryDirectory() as temporary,
            ):
                base = Path(temporary)
                source, home = support.seed_source(base)
                retired = support.seed_managed_retired_links(source, home)

                plan = source / "home/.codex/skills/dev-flow/scripts/plan.py"
                real_plan = plan.with_name("plan-real.py")
                plan.rename(real_plan)
                trace = base / "task-record-smoke.log"
                plan.write_text(
                    "#!/usr/bin/env python3\n"
                    "import os, runpy, sys\n"
                    "from pathlib import Path\n"
                    "with Path(os.environ['SETUP_SMOKE_TRACE']).open('a', encoding='utf-8') as stream:\n"
                    "    stream.write(sys.argv[0] + '\\n')\n"
                    "runpy.run_path(str(Path(__file__).with_name('plan-real.py')), run_name='__main__')\n",
                    encoding="utf-8",
                )
                plan.chmod(0o755)

                manifest_path = (
                    source
                    / f"home/.codex/skills/orchestrate/manifests/{SOURCE_SKILL_VERSION}.json"
                )
                self.assertTrue(manifest_path.is_file(), manifest_path)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["documents"]["runtime-pi.md"]["sha256"] = "0" * 64
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                result = support.run_setup(
                    source,
                    home,
                    {"SETUP_SMOKE_TRACE": str(trace)},
                )

                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(
                    f"{logical_layout} release verification failed",
                    result.stderr.lower(),
                )
                self.assertIn(
                    str(home / ".codex/skills/dev-flow/scripts/plan.py"),
                    trace.read_text(encoding="utf-8").splitlines(),
                )
                for path in retired:
                    self.assertTrue(path.is_symlink(), path)
                    self.assertTrue(
                        os.path.samefile(path, source / "home" / path.relative_to(home))
                    )

    def test_replacement_smoke_failure_leaves_planning_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            replacement = source / "home/.codex/skills/dev-flow/scripts/plan.py"
            replacement.parent.mkdir(parents=True, exist_ok=True)
            replacement.write_text(
                "#!/usr/bin/env python3\nraise SystemExit('replacement smoke failed')\n",
                encoding="utf-8",
            )
            replacement.chmod(0o755)
            retired_source = source / "home/.codex/skills/planning-with-files"
            retired_destination = home / ".codex/skills/planning-with-files"
            retired_destination.parent.mkdir(parents=True, exist_ok=True)
            retired_destination.symlink_to(retired_source)

            result = support.run_setup(source, home)

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("replacement smoke", result.stderr)
            self.assertTrue(retired_destination.is_symlink())
            self.assertTrue(os.path.samefile(retired_destination, retired_source))

    def test_foreign_retired_destination_refuses_before_any_home_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            foreign = home / ".pi/agent/skills/planning-with-files"
            foreign.mkdir(parents=True)
            (foreign / "SKILL.md").write_text("foreign planning bytes\n", encoding="utf-8")
            sentinel = home / ".config/private.conf"
            sentinel.parent.mkdir(parents=True)
            sentinel.write_text("private\n", encoding="utf-8")
            before = support.snapshot_home(home)

            result = support.run_setup(source, home)

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("foreign retired destination", result.stderr)
            self.assertEqual(support.snapshot_home(home), before)

    def test_managed_upgrade_removes_retired_authority_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            retired = support.seed_managed_retired_links(source, home)
            private = home / ".codex/skills/private/SKILL.md"
            private.parent.mkdir(parents=True)
            private.write_text("private skill\n", encoding="utf-8")

            first = support.run_setup(source, home)
            first_snapshot = support.snapshot_home(home)
            second = support.run_setup(source, home)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(support.snapshot_home(home), first_snapshot)
            self.assertEqual(private.read_text(encoding="utf-8"), "private skill\n")
            for path in retired:
                self.assertFalse(path.exists() or path.is_symlink(), path)
            for layout in (*support.managed_skill_layouts(), Path(".claude/skills")):
                dev_flow = home / layout / "dev-flow"
                self.assertTrue(dev_flow.is_symlink(), dev_flow)
                self.assertTrue(os.path.samefile(dev_flow, source / "home" / layout / "dev-flow"))
                self.assertFalse((home / layout / "planning-with-files").exists())

    def test_partial_retired_removal_reports_exact_paths_then_normal_rerun_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            retired = support.seed_managed_retired_links(source, home)
            fake_bin = base / "bin"
            fake_bin.mkdir()
            fake_rm = fake_bin / "rm"
            fake_rm.write_text(
                "#!/bin/sh\n"
                "case \" $* \" in *'.pi/agent/skills/planning-with-files'*) "
                "echo 'forced retired removal failure' >&2; exit 1;; esac\n"
                "exec /bin/rm \"$@\"\n",
                encoding="utf-8",
            )
            fake_rm.chmod(0o755)

            failed = support.run_setup(
                source,
                home,
                {"PATH": f"{fake_bin}:{os.environ['PATH']}"},
            )

            self.assertNotEqual(failed.returncode, 0, failed.stdout)
            self.assertIn("retired removal incomplete", failed.stderr)
            self.assertIn("removed:", failed.stderr)
            self.assertIn("remaining:", failed.stderr)
            for path in retired:
                self.assertIn(str(path), failed.stderr)
            self.assertTrue((home / ".codex/skills/dev-flow").is_symlink())

            rerun = support.run_setup(source, home)
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            for path in retired:
                self.assertFalse(path.exists() or path.is_symlink(), path)

    def test_source_derived_unrelated_skill_allowlist_installs_without_destination_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            for layout in (*support.managed_skill_layouts(), Path(".claude/skills")):
                skill = source / "home" / layout / "source-extra"
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text("source extra\n", encoding="utf-8")
            private = home / ".pi/agent/skills/destination-private/SKILL.md"
            private.parent.mkdir(parents=True)
            private.write_text("destination private\n", encoding="utf-8")

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            for layout in (*support.managed_skill_layouts(), Path(".claude/skills")):
                installed = home / layout / "source-extra"
                self.assertTrue(installed.is_symlink(), installed)
            self.assertEqual(private.read_text(encoding="utf-8"), "destination private\n")


class SetupConfigCurrentContractTests(unittest.TestCase):
    def test_isolated_home_installs_the_exact_release_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            for layout in support.managed_skill_layouts():
                skill = home / layout / "orchestrate"
                source_skill = source / "home" / layout / "orchestrate"
                manifest_path = skill / f"manifests/{SOURCE_SKILL_VERSION}.json"
                self.assertTrue(manifest_path.is_file(), manifest_path)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["skill_version"], SOURCE_SKILL_VERSION)
                self.assertTrue(os.path.samefile(skill, source_skill))
                for document in manifest["documents"]:
                    self.assertTrue(
                        os.path.samefile(skill / document, source_skill / document),
                        document,
                    )
                for profile in manifest["profiles"]:
                    self.assertTrue(
                        os.path.samefile(home / profile, source / "home" / profile),
                        profile,
                    )

            codex_skill = home / ".codex/skills/orchestrate"
            doctor = subprocess.run(
                [
                    sys.executable,
                    str(codex_skill / "scripts/orchestrate.py"),
                    "--skill-dir",
                    str(codex_skill),
                    "doctor",
                ],
                cwd=base,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertTrue(json.loads(doctor.stdout)["ok"])

    def test_current_surfaces_install_and_private_assets_survive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = support.seed_source(base)
            private = {
                home / ".codex/agents/private.toml": b"private codex\n",
                home / ".claude/agents/private.md": b"private claude\n",
                home / ".pi/agent/agents/private.md": b"private pi\n",
                home / ".pi/agent/extensions/private.ts": b"private extension\n",
                home / ".pi/agent/extensions/private-package/index.ts": b"private package\n",
                home / ".codex/skills/private/SKILL.md": b"private skill\n",
                home / ".config/private.conf": b"private config\n",
            }
            for path, content in private.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            result = support.run_setup(source, home)

            self.assertEqual(result.returncode, 0, result.stderr)
            for layout in support.managed_skill_layouts():
                for skill in support.active_skill_names():
                    destination = home / layout / skill
                    shipped = source / "home" / layout / skill
                    self.assertTrue(destination.is_symlink())
                    self.assertTrue(os.path.samefile(destination, shipped))
                for skill in support.retired_skill_names():
                    self.assertFalse((home / layout / skill).exists())
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
