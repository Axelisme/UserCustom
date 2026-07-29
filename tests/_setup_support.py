"""Isolated-HOME fixtures shared by the setup_config.sh contract tests.

Every fixture here seeds a throwaway source tree and a throwaway ``HOME`` so the
real user configuration is never touched.  The shipped profile and skill names
are read from the repository rather than listed, so adding a profile or a skill
does not require editing a test.
"""

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
    "home/.codex/AGENTS.md": "shipped Codex standing orders\n",
    "home/.pi/agent/APPEND_SYSTEM.md": "shipped Pi standing orders\n",
    "home/.pi/agent/settings.json": '{"shipped": true}\n',
    "home/.pi/agent/extensions/orchestrate-pi.ts": "shipped adapter bytes\n",
    "home/.local/include/shipped.h": "/* shipped */\n",
}


def _script_array(name: str) -> tuple[str, ...]:
    """Read a Bash array literal out of setup_config.sh.

    The script decides which skills and layouts it manages; reading its own
    declaration keeps the fixtures aligned when that set changes.
    """
    match = re.search(
        rf"(?m)^{re.escape(name)}=\(([^)]*)\)", SETUP_SCRIPT.read_text(encoding="utf-8")
    )
    if match is None:
        raise AssertionError(f"setup_config.sh no longer declares {name}")
    return tuple(shlex.split(match.group(1)))


def managed_skill_layouts() -> tuple[Path, ...]:
    return tuple(Path(entry) for entry in _script_array("CURRENT_SKILL_LAYOUTS"))


def managed_skill_names() -> tuple[str, ...]:
    return _script_array("CURRENT_SKILLS")


def shipped_profile_relatives() -> tuple[Path, ...]:
    """Every agent profile this repository actually ships, as HOME-relative paths."""
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
    """Build a source tree carrying every shipped surface, plus an empty HOME."""
    source = base / "source"
    home = base / "isolated-home"
    script = source / "setup_scripts/setup_config.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "setup_scripts/setup_config.sh", script)

    for relative, content in ORDINARY_FILES.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    for relative in shipped_profile_relatives():
        target = source / "home" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"shipped profile {relative.as_posix()}\n", encoding="utf-8")

    for layout in (*managed_skill_layouts(), Path(".claude/skills")):
        for skill in managed_skill_names():
            target = source / "home" / layout / skill / "SKILL.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                f"shipped {layout.as_posix()} {skill}\n", encoding="utf-8"
            )
    return source, home


def seed_destination(base: Path, destination: Path, state: str) -> tuple[bytes | None, str | None]:
    """Put an installed destination into one of the three states setup must repair.

    Returns the prior bytes for a plain file, or the prior link target for a symlink,
    so the caller can assert the backup setup is required to leave behind.
    """
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
    else:  # pragma: no cover - frozen state table
        raise AssertionError(f"unknown destination state: {state}")
    destination.symlink_to(target)
    return None, str(target)
