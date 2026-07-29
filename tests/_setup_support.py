"""Isolated-HOME fixtures shared by setup_config.sh Contract tests."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "setup_scripts/setup_config.sh"
PROFILE_LAYOUTS = {
    "codex": Path(".codex/agents"),
    "claude": Path(".claude/agents"),
    "pi": Path(".pi/agent/agents"),
}
ADAPTER_RELATIVE = Path(".pi/agent/extensions/orchestrate-pi.ts")
ORDINARY_FILES = {
    "home/.config/shipped.conf": "shipped config\n",
    "home/.local/include/shipped.h": "/* shipped */\n",
}


def _script_array(name: str) -> tuple[str, ...]:
    match = re.search(
        rf"(?m)^{re.escape(name)}=\(([^)]*)\)", SETUP_SCRIPT.read_text(encoding="utf-8")
    )
    if match is None:
        raise AssertionError(f"setup_config.sh no longer declares {name}")
    return tuple(shlex.split(match.group(1)))


def managed_skill_layouts() -> tuple[Path, ...]:
    return tuple(Path(entry) for entry in _script_array("CURRENT_SKILL_LAYOUTS"))


def active_skill_names() -> tuple[str, ...]:
    return _script_array("ACTIVE_LIFECYCLE_SKILLS")


def retired_skill_names() -> tuple[str, ...]:
    return _script_array("RETIRED_LIFECYCLE_SKILLS")


def shipped_profile_relatives() -> tuple[Path, ...]:
    relatives: list[Path] = []
    for layout in PROFILE_LAYOUTS.values():
        for path in sorted((ROOT / "home" / layout).iterdir()):
            if path.is_file():
                relatives.append(layout / path.name)
    return tuple(relatives)


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

    for relative in (
        "home/.codex/skills",
        "home/.pi/agent/skills",
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
        f"home/{ADAPTER_RELATIVE.as_posix()}",
    ):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    for relative, content in ORDINARY_FILES.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return source, home


def seed_managed_retired_links(source: Path, home: Path) -> tuple[Path, ...]:
    destinations: list[Path] = []
    for layout in (*managed_skill_layouts(), Path(".claude/skills")):
        for skill in retired_skill_names():
            shipped = source / "home" / layout / skill
            if not shipped.exists():
                continue
            destination = home / layout / skill
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(shipped)
            destinations.append(destination)
    return tuple(destinations)


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


def seed_destination(base: Path, destination: Path, state: str) -> tuple[bytes | None, str | None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if state == "stale":
        content = b"stale user copy\n"
        destination.write_bytes(content)
        return content, None

    if state == "foreign":
        target = base / f"foreign-{destination.name}"
        target.write_text("foreign profile\n", encoding="utf-8")
    elif state == "dangling":
        target = base / f"missing-{destination.name}"
    else:
        raise AssertionError(f"unknown destination state: {state}")
    destination.symlink_to(target)
    return None, str(target)
