from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = tempfile.TemporaryDirectory(prefix="orchestrate-cli-tests-")
TEST_HOME = Path(_PACKAGE.name) / "home"
shutil.copytree(ROOT / "home", TEST_HOME)
VERIFIED_SKILL = TEST_HOME / ".codex" / "skills" / "orchestrate"
SCRIPT = VERIFIED_SKILL / "scripts" / "orchestrate.py"

sys.path.insert(0, str(VERIFIED_SKILL / "scripts"))
try:
    release = importlib.import_module("_orchestrate.release")
finally:
    sys.path.pop(0)

_version = release.skill_version(VERIFIED_SKILL)
(VERIFIED_SKILL / f"manifests/{_version}.json").write_text(
    json.dumps(release.build_manifest(VERIFIED_SKILL, _version)),
    encoding="utf-8",
)
