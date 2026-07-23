from __future__ import annotations

import json
import shutil
import sys
import tempfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def verified_skill_dir(source: str) -> str:
    """Make a disposable profile-complete release fixture for public CLI tests.

    A task lane may intentionally be ahead of its committed manifest while root owns
    the next release transaction. State-command tests rebuild verification only inside
    this disposable copy; production preflight remains strict.
    """
    source_path = Path(source).resolve()
    temporary_root = Path(tempfile.mkdtemp(prefix="orchestrate-verified-"))
    destination = temporary_root / ".codex" / "skills" / "orchestrate"
    shutil.copytree(source_path, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    scripts = destination / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from _orchestrate.release import build_manifest, profile_paths, skill_version, source_home

        source_root = source_home(source_path)
        for source_profile in profile_paths(source_root):
            if not source_profile.is_file():
                continue
            destination_profile = temporary_root / source_profile.relative_to(source_root)
            destination_profile.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_profile, destination_profile)

        version = skill_version(destination)
        payload = build_manifest(destination, version)
        manifest = destination / "manifests" / f"{version}.json"
        manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        sys.path.pop(0)
    return str(destination)


def cli_command(script: Path, args: list[str]) -> list[str]:
    return [sys.executable, str(script), "--skill-dir", verified_skill_dir(str(script.parent.parent)), *args]
