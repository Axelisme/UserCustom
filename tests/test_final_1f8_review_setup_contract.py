from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROFILE_LAYOUTS = {
    "codex": Path(".codex/agents"),
    "claude": Path(".claude/agents"),
    "pi": Path(".pi/agent/agents"),
}
PROFILE_NAMES = {
    "codex": (
        "acceptance-reviewer.toml",
        "contract-planner.toml",
        "impl-detail-planner.toml",
        "mcp-skill-tester.toml",
        "mechanical-implementer.toml",
        "plan-item-implementer.toml",
        "python-bug-investigator.toml",
        "repo-investigator.toml",
        "wave-implementer.toml",
        "wave-oracle.toml",
        "web-researcher.toml",
    ),
    "claude": (
        "acceptance-reviewer.md",
        "contract-planner.md",
        "impl-detail-planner.md",
        "mcp-skill-tester.md",
        "mechanical-implementer.md",
        "plan-item-implementer.md",
        "python-bug-investigator.md",
        "repo-investigator.md",
        "wave-implementer.md",
        "wave-oracle.md",
        "web-researcher.md",
    ),
    "pi": (
        "acceptance-reviewer.md",
        "contract-planner.md",
        "impl-detail-planner.md",
        "mcp-skill-tester.md",
        "mechanical-implementer.md",
        "plan-item-implementer.md",
        "python-bug-investigator.md",
        "repo-investigator.md",
        "wave-implementer.md",
        "wave-oracle.md",
        "web-researcher.md",
    ),
}
REPO_INVESTIGATORS = {
    "codex": Path(".codex/agents/repo-investigator.toml"),
    "claude": Path(".claude/agents/repo-investigator.md"),
    "pi": Path(".pi/agent/agents/repo-investigator.md"),
}


class Final1f8OrdinaryProfileSetupContractTests(unittest.TestCase):
    """Isolated-HOME Contract for exact refresh of every shipped agent profile."""

    def run_setup(
        self, source: Path, home: Path, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(source / "setup_scripts/setup_config.sh")],
            env={**os.environ, "HOME": str(home), **(env or {})},
            capture_output=True,
            text=True,
            check=False,
        )

    def seed_source(self, base: Path) -> tuple[Path, Path]:
        source = base / "source"
        home = base / "isolated-home"
        script = source / "setup_scripts/setup_config.sh"
        script.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "setup_scripts/setup_config.sh", script)

        ordinary_files = {
            "home/.config/shipped.conf": "shipped config\n",
            "home/.codex/AGENTS.md": "shipped Codex standing orders\n",
            "home/.pi/agent/APPEND_SYSTEM.md": "shipped Pi standing orders\n",
            "home/.pi/agent/settings.json": '{"shipped": true}\n',
            "home/.local/include/shipped.h": "/* shipped */\n",
            "home/.codex/skills/orchestrate/SKILL.md": "shipped Codex skill\n",
            "home/.pi/agent/skills/orchestrate/SKILL.md": "shipped Pi skill\n",
            "home/.claude/skills/orchestrate/SKILL.md": "shipped Claude skill\n",
        }
        for relative, content in ordinary_files.items():
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        for runtime, layout in PROFILE_LAYOUTS.items():
            for name in PROFILE_NAMES[runtime]:
                target = source / "home" / layout / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    f"shipped {runtime} manifest-bound profile {name}\n",
                    encoding="utf-8",
                )
        return source, home

    def shipped_profiles(self, source: Path) -> list[tuple[Path, Path]]:
        profiles: list[tuple[Path, Path]] = []
        for layout in PROFILE_LAYOUTS.values():
            source_directory = source / "home" / layout
            for shipped in sorted(source_directory.iterdir()):
                if shipped.is_file():
                    profiles.append((shipped, layout / shipped.name))
        self.assertGreater(len(profiles), len(PROFILE_LAYOUTS))
        return profiles

    def seed_destination(
        self, base: Path, destination: Path, state: str
    ) -> tuple[bytes | None, str | None]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if state == "stale":
            content = b"stale ordinary profile\n"
            destination.write_bytes(content)
            return content, None

        if state == "foreign":
            target = base / "foreign-repo-investigator"
            target.write_text("foreign ordinary profile\n", encoding="utf-8")
        elif state == "dangling":
            target = base / "missing-repo-investigator"
            self.assertFalse(target.exists())
        else:  # pragma: no cover - frozen state table
            self.fail(f"unknown destination state: {state}")
        destination.symlink_to(target)
        return None, str(target)

    def guard_profile_validation_before_retirement(
        self,
        base: Path,
        source: Path,
        home: Path,
        changed_destination: Path,
        prior_bytes: bytes | None,
        prior_link: str | None,
    ) -> tuple[Path, Path]:
        guard_bin = base / "guard-bin"
        guard_bin.mkdir()
        marker = base / "profile-validation-observed"
        real_rm = shutil.which("rm")
        self.assertIsNotNone(real_rm)

        exact_checks: list[str] = []
        for shipped, relative in self.shipped_profiles(source):
            installed = home / relative
            message = f"shipped profile was not exact before retirement: {installed}"
            exact_checks.append(
                f"if ! [ -f {shlex.quote(str(installed))} ] || "
                f"! [ {shlex.quote(str(installed))} -ef {shlex.quote(str(shipped))} ]; then "
                f"printf '%s\\n' {shlex.quote(message)} >&2; exit 91; fi"
            )

        backup = changed_destination.with_name(changed_destination.name + ".bak")
        if prior_bytes is not None:
            expected = base / "expected-stale-profile"
            expected.write_bytes(prior_bytes)
            backup_check = (
                f"if ! cmp -s {shlex.quote(str(backup))} {shlex.quote(str(expected))}; then "
                "printf '%s\\n' 'ordinary profile backup missing before retirement' >&2; "
                "exit 92; fi"
            )
        else:
            if prior_link is None:
                self.fail("link destination must retain its prior target")
            backup_check = (
                f"if ! [ -L {shlex.quote(str(backup))} ] || "
                f'[ "$(readlink {shlex.quote(str(backup))})" != {shlex.quote(prior_link)} ]; then '
                "printf '%s\\n' 'ordinary profile link backup missing before retirement' >&2; "
                "exit 93; fi"
            )

        wrapper = guard_bin / "rm"
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            "set -e\n"
            + "\n".join(exact_checks)
            + "\n"
            + backup_check
            + "\n"
            + f"printf 'validated before retirement\\n' >> {shlex.quote(str(marker))}\n"
            + f'exec {shlex.quote(str(real_rm))} "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        return guard_bin, marker

    def test_repo_investigator_states_refresh_all_profiles_without_touching_unrelated(
        self,
    ) -> None:
        for runtime, relative in REPO_INVESTIGATORS.items():
            for state in ("stale", "foreign", "dangling"):
                with (
                    self.subTest(runtime=runtime, state=state),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    base = Path(temporary)
                    source, home = self.seed_source(base)
                    destination = home / relative
                    prior_bytes, prior_link = self.seed_destination(
                        base, destination, state
                    )

                    unrelated_profiles = {
                        home
                        / ".codex/agents/user-private.toml": b"private Codex profile\n",
                        home
                        / ".claude/agents/user-private.md": b"private Claude profile\n",
                        home
                        / ".pi/agent/agents/user-private.md": b"private Pi profile\n",
                    }
                    for path, content in unrelated_profiles.items():
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(content)

                    guard_bin, marker = self.guard_profile_validation_before_retirement(
                        base,
                        source,
                        home,
                        destination,
                        prior_bytes,
                        prior_link,
                    )
                    result = self.run_setup(
                        source,
                        home,
                        {"PATH": f"{guard_bin}{os.pathsep}{os.environ['PATH']}"},
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
                    )
                    self.assertTrue(marker.is_file())

                    for shipped, installed_relative in self.shipped_profiles(source):
                        installed = home / installed_relative
                        self.assertTrue(installed.is_file(), installed)
                        self.assertTrue(
                            os.path.samefile(installed, shipped),
                            f"{installed} must exact-link to {shipped}",
                        )
                        self.assertEqual(installed.read_bytes(), shipped.read_bytes())

                    backup = destination.with_name(destination.name + ".bak")
                    if prior_bytes is not None:
                        self.assertEqual(backup.read_bytes(), prior_bytes)
                    else:
                        self.assertTrue(backup.is_symlink())
                        self.assertEqual(os.readlink(backup), prior_link)
                    for path, content in unrelated_profiles.items():
                        self.assertEqual(path.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
