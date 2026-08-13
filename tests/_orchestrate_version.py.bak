"""The shipped orchestrate version, parsed once from the source SKILL.md.

Kept free of side effects so any test module can read the current version
without paying for a package copy, and so a release never edits a test.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SKILL = ROOT / "home/.codex/skills/orchestrate/SKILL.md"
_MATCH = re.search(
    r"(?m)^skill_version: (\d+)$", _SKILL.read_text(encoding="utf-8")
)
if _MATCH is None:
    raise RuntimeError(f"orchestrate SKILL.md has no skill_version: {_SKILL}")

SOURCE_SKILL_VERSION = int(_MATCH.group(1))
