from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PLANNERS = {
    "codex": Path(".codex/agents/contract-planner.toml"),
    "claude": Path(".claude/agents/contract-planner.md"),
    "pi": Path(".pi/agent/agents/contract-planner.md"),
}
WAVE_PROFILES = {
    ".codex/agents": ".toml",
    ".claude/agents": ".md",
    ".pi/agent/agents": ".md",
}


class Final475ContractPlannerSetupContractTests(unittest.TestCase):
    """Isolated-HOME Contract for exact contract-planner profile refresh."""

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

        for runtime, relative in CONTRACT_PLANNERS.items():
            target = source / "home" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"shipped {runtime} contract planner\n", encoding="utf-8")

        # Seed both the pre-correction and reviewed profile sets so this test isolates
        # contract-planner replacement rather than failing setup's other validation gates.
        for directory, suffix in WAVE_PROFILES.items():
            for role in (
                "wave-oracle",
                "wave-implementer",
                "wave-reviewer",
                "integration-reviewer",
            ):
                target = source / "home" / directory / f"{role}{suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"shipped {directory} {role}\n", encoding="utf-8")
        return source, home

    def seed_destination(
        self, base: Path, destination: Path, state: str
    ) -> tuple[bytes | None, str | None]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if state == "stale":
            content = b"stale user copy\n"
            destination.write_bytes(content)
            return content, None

        if state == "foreign":
            target = base / "foreign-contract-planner"
            target.write_text("foreign profile\n", encoding="utf-8")
        elif state == "dangling":
            target = base / "missing-contract-planner"
            self.assertFalse(target.exists())
        else:  # pragma: no cover - frozen table controls states
            self.fail(f"unknown destination state: {state}")
        destination.symlink_to(target)
        return None, str(target)

    def guarded_rm(
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
        marker = base / "legacy-retirement-started"
        real_rm = shutil.which("rm")
        self.assertIsNotNone(real_rm)

        checks: list[str] = []
        for relative in CONTRACT_PLANNERS.values():
            shipped = source / "home" / relative
            installed = home / relative
            message = (
                "contract-planner destination was not exact-replaced and validated "
                f"before legacy retirement: {installed}"
            )
            checks.append(
                f"if ! [ {shlex.quote(str(installed))} -ef {shlex.quote(str(shipped))} ] "
                f"|| ! [ -f {shlex.quote(str(installed))} ]; then "
                f"printf '%s\\n' {shlex.quote(message)} >&2; exit 91; fi"
            )

        backup = changed_destination.with_name(changed_destination.name + ".bak")
        if prior_bytes is not None:
            expected = base / "expected-stale-profile"
            expected.write_bytes(prior_bytes)
            backup_check = (
                f"if ! cmp -s {shlex.quote(str(backup))} {shlex.quote(str(expected))}; then "
                f"printf '%s\\n' 'contract-planner stale backup missing before legacy retirement' >&2; "
                "exit 92; fi"
            )
        else:
            self.assertIsNotNone(prior_link)
            backup_check = (
                f"if ! [ -L {shlex.quote(str(backup))} ] || "
                f'[ "$(readlink {shlex.quote(str(backup))})" != {shlex.quote(prior_link)} ]; then '
                f"printf '%s\\n' 'contract-planner link backup missing before legacy retirement' >&2; "
                "exit 93; fi"
            )

        wrapper = guard_bin / "rm"
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            "set -e\n"
            + "\n".join(checks)
            + "\n"
            + backup_check
            + "\n"
            + f"printf 'validated before retirement\\n' >> {shlex.quote(str(marker))}\n"
            + f'exec {shlex.quote(str(real_rm))} "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        return guard_bin, marker

    def test_contract_planners_replace_stale_foreign_and_dangling_destinations(
        self,
    ) -> None:
        for runtime, relative in CONTRACT_PLANNERS.items():
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
                    settings = home / ".pi/agent/settings.json"
                    settings.parent.mkdir(parents=True, exist_ok=True)
                    settings.write_bytes(b'{"private": true}\n')
                    legacy = home / ".codex/agents/implementer.toml"
                    legacy.parent.mkdir(parents=True, exist_ok=True)
                    legacy.write_text("legacy identity\n", encoding="utf-8")

                    guard_bin, marker = self.guarded_rm(
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
                    self.assertFalse(legacy.exists())
                    for planner_relative in CONTRACT_PLANNERS.values():
                        installed = home / planner_relative
                        shipped = source / "home" / planner_relative
                        self.assertTrue(installed.is_file())
                        self.assertTrue(os.path.samefile(installed, shipped))
                    for path, content in unrelated_profiles.items():
                        self.assertEqual(path.read_bytes(), content)
                    self.assertEqual(
                        settings.with_name("settings.json.bak").read_bytes(),
                        b'{"private": true}\n',
                    )

    def test_contract_planner_validation_precedes_legacy_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_source(base)
            script = source / "setup_scripts/setup_config.sh"
            original = script.read_text(encoding="utf-8")
            validation_boundary = (
                "validate_orchestrate_profile_destinations\n"
                "remove_obsolete_orchestrate_profiles"
            )
            self.assertEqual(original.count(validation_boundary), 1)
            drifted = home / CONTRACT_PLANNERS["codex"]
            missing = base / "missing-after-install"
            injection = (
                f"rm -f {shlex.quote(str(drifted))}\n"
                f"ln -s {shlex.quote(str(missing))} {shlex.quote(str(drifted))}\n"
                + validation_boundary
            )
            script.write_text(
                original.replace(validation_boundary, injection), encoding="utf-8"
            )

            legacy = home / ".codex/agents/implementer.toml"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text("legacy identity\n", encoding="utf-8")
            result = self.run_setup(source, home)

            self.assertNotEqual(
                result.returncode,
                0,
                "setup accepted a drifted contract-planner destination and retired legacy",
            )
            self.assertIn("contract-planner", result.stderr)
            self.assertTrue(legacy.is_file(), "validation must fail before retirement")


if __name__ == "__main__":
    unittest.main()
