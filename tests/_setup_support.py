"""Isolated-HOME fixtures for setup_config.sh tests."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "setup_scripts/setup_config.sh"
ORDINARY_FILES = {
    "home/.config/shipped.conf": "shipped config\n",
    "home/.local/include/shipped.h": "/* shipped */\n",
}


def run_setup(
    source: Path, home: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(source / "setup_scripts/setup_config.sh")],
        env={**os.environ, "HOME": str(home), **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def seed_source(base: Path) -> tuple[Path, Path]:
    """Build a realistic shipped source tree plus an empty isolated HOME."""
    source = base / "source"
    home = base / "isolated-home"
    script = source / "setup_scripts/setup_config.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(SETUP_SCRIPT, script)

    # Skills bridged onto the vendored upstream tree are symlinks out of home/, so the
    # vendored tree has to be seeded too or every bridge dangles in the isolated source.
    for relative in (
        "vendor",
        "home/.codex/skills",
        "home/.pi/agent/skills",
        "home/.pi/agent/extensions",
        "home/.claude/skills",
        "home/.codex/agents",
        "home/.pi/agent/agents",
        "home/.claude/agents",
    ):
        shutil.copytree(ROOT / relative, source / relative, symlinks=True)

    for relative in (
        "home/.codex/AGENTS.md",
        "home/.pi/agent/APPEND_SYSTEM.md",
        "home/.pi/agent/settings.json",
        "home/.pi/acp.json",
    ):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    for relative, content in ORDINARY_FILES.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return source, home


def snapshot_home(home: Path) -> dict[str, tuple[str, bytes | str | None]]:
    result: dict[str, tuple[str, bytes | str | None]] = {}
    if not home.exists():
        return result
    for path in sorted(home.rglob("*")):
        relative = path.relative_to(home).as_posix()
        if path.is_symlink():
            result[relative] = ("link", os.readlink(path))
        elif path.is_dir():
            result[relative] = ("dir", None)
        else:
            result[relative] = ("file", path.read_bytes())
    return result
