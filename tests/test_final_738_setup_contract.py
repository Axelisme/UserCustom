from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "orchestrate",
    "code-review",
    "dev-flow",
    "planning-with-files",
    "to-spec",
    "to-tickets",
)
LAYOUTS = (".codex/skills", ".pi/agent/skills")


class Final738SetupParityContractTests(unittest.TestCase):
    """Isolated-HOME Contract for every skill modified by v119."""

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
        script = source / "setup_scripts" / "setup_config.sh"
        script.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "setup_scripts" / "setup_config.sh", script)

        ordinary_files = {
            "home/.config/shipped.conf": "shipped config\n",
            "home/.codex/AGENTS.md": "shipped standing orders\n",
            "home/.pi/agent/APPEND_SYSTEM.md": "shipped standing orders\n",
            "home/.pi/agent/settings.json": "{\"shipped\": true}\n",
            "home/.local/include/shipped.h": "/* shipped */\n",
        }
        for relative, content in ordinary_files.items():
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        for layout in LAYOUTS:
            for skill in SKILLS:
                target = source / "home" / layout / skill / "SKILL.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"shipped {layout} {skill}\n", encoding="utf-8")

        # Populate all agent trees so setup can install and validate replacement
        # profiles before it invokes legacy-profile retirement.
        profiles = (
            ".codex/agents/wave-oracle.toml",
            ".codex/agents/wave-implementer.toml",
            ".codex/agents/wave-reviewer.toml",
            ".pi/agent/agents/wave-oracle.md",
            ".pi/agent/agents/wave-implementer.md",
            ".pi/agent/agents/wave-reviewer.md",
            ".claude/agents/wave-oracle.md",
            ".claude/agents/wave-implementer.md",
            ".claude/agents/wave-reviewer.md",
        )
        for relative in profiles:
            target = source / "home" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"shipped {relative}\n", encoding="utf-8")
        (source / "home/.claude/skills/orchestrate").mkdir(parents=True)
        (source / "home/.claude/skills/orchestrate/SKILL.md").write_text(
            "shipped claude skill\n", encoding="utf-8"
        )
        return source, home

    def test_stale_and_dangling_v119_skill_links_are_replaced_before_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, home = self.seed_source(base)

            for index, (layout, skill) in enumerate(
                (layout, skill) for layout in LAYOUTS for skill in SKILLS
            ):
                destination = home / layout / skill
                destination.parent.mkdir(parents=True, exist_ok=True)
                if index % 2:
                    raw_target = str(base / f"missing-skill-{index}")
                    self.assertFalse(Path(raw_target).exists())
                else:
                    foreign = base / f"stale-skill-{index}"
                    foreign.mkdir()
                    (foreign / "SKILL.md").write_text(
                        "stale foreign skill\n", encoding="utf-8"
                    )
                    raw_target = str(foreign)
                destination.symlink_to(raw_target, target_is_directory=True)

            unrelated_skill = home / ".codex/skills/user-private/SKILL.md"
            unrelated_skill.parent.mkdir(parents=True)
            unrelated_skill.write_text("private skill\n", encoding="utf-8")
            unrelated_config = home / ".config/user-private.conf"
            unrelated_config.parent.mkdir(parents=True)
            unrelated_config.write_text("private config\n", encoding="utf-8")
            settings = home / ".pi/agent/settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text("{\"private\": true}\n", encoding="utf-8")

            legacy = home / ".codex/agents/implementer.toml"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("legacy profile\n", encoding="utf-8")

            retirement_marker = base / "retirement-started"
            guard_bin = base / "guard-bin"
            guard_bin.mkdir()
            real_rm = shutil.which("rm")
            self.assertIsNotNone(real_rm)
            validation_commands = []
            for layout in LAYOUTS:
                for skill in SKILLS:
                    destination = home / layout / skill
                    shipped = source / "home" / layout / skill
                    validation_commands.append(
                        f'test "{destination}" -ef "{shipped}"'
                    )
                    validation_commands.append(
                        f'test -f "{destination / "SKILL.md"}"'
                    )
            guarded_rm = guard_bin / "rm"
            guarded_rm.write_text(
                "#!/usr/bin/env bash\n"
                "set -e\n"
                + "\n".join(validation_commands)
                + "\n"
                + f'printf "validated before retirement\\n" >> "{retirement_marker}"\n'
                + f'exec "{real_rm}" "$@"\n',
                encoding="utf-8",
            )
            guarded_rm.chmod(0o755)

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
            self.assertTrue(retirement_marker.is_file())
            self.assertFalse(legacy.exists())

            for layout in LAYOUTS:
                for skill in SKILLS:
                    with self.subTest(layout=layout, skill=skill):
                        destination = home / layout / skill
                        shipped = source / "home" / layout / skill
                        self.assertTrue(destination.is_symlink())
                        self.assertTrue(os.path.samefile(destination, shipped))
                        self.assertEqual(
                            (destination / "SKILL.md").read_bytes(),
                            (shipped / "SKILL.md").read_bytes(),
                        )

            self.assertEqual(unrelated_skill.read_bytes(), b"private skill\n")
            self.assertEqual(unrelated_config.read_bytes(), b"private config\n")
            self.assertEqual(
                settings.with_name("settings.json.bak").read_bytes(),
                b'{"private": true}\n',
            )


if __name__ == "__main__":
    unittest.main()
