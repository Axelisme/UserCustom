from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests._orchestrate_version import SOURCE_SKILL_VERSION

ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = tempfile.TemporaryDirectory(prefix="orchestrate-cli-tests-")
TEST_HOME = Path(_PACKAGE.name) / "home"
# Copy only what the package itself binds: the skill under test, and the
# profile roots its manifest projects. Copying all of home/ pulled in every
# other skill for 24MB per process, which the parallel runner multiplies by
# one process per module and a killed run leaves behind in full.
for _relative in (
    ".codex/skills/orchestrate",
    ".codex/agents",
    ".claude/agents",
    ".pi/agent/agents",
):
    shutil.copytree(ROOT / "home" / _relative, TEST_HOME / _relative, symlinks=True)
_APPEND_SYSTEM = TEST_HOME / ".pi/agent/APPEND_SYSTEM.md"
_APPEND_SYSTEM.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / "home/.pi/agent/APPEND_SYSTEM.md", _APPEND_SYSTEM)
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


def run_cli(
    cwd: Path,
    *argv: str,
    script: Path = SCRIPT,
    skill_dir: Path = VERIFIED_SKILL,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the shipped subprocess without hiding its public argv."""
    return subprocess.run(
        [sys.executable, str(script), "--skill-dir", str(skill_dir), *argv],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


def run_git(
    cwd: Path,
    *argv: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run real local Git and leave interpretation to each Contract test."""
    result = subprocess.run(
        ["git", *argv],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **(env or {})},
    )
    if check and result.returncode:
        raise AssertionError(
            f"git {' '.join(argv)} failed ({result.returncode}): {result.stderr}"
        )
    return result


def json_object(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise AssertionError(f"expected one JSON object, got {value!r}")
    return value


class OrchestrateCliRepositoryTestCase(unittest.TestCase):
    """Small public-seam fixture backed by one throwaway real repository."""

    orchestrate_version = SOURCE_SKILL_VERSION

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix=f"orchestrate-v{self.orchestrate_version}-"
        )
        self.root = Path(self.temporary.name)
        run_git(self.root, "init", "-q", "-b", "main")
        run_git(self.root, "config", "user.name", "Contract Test")
        run_git(self.root, "config", "user.email", "contract@example.invalid")
        (self.root / ".gitignore").write_text("/.agent_state/\n", encoding="utf-8")
        self.nested = self.root / "project" / "nested"
        self.nested.mkdir(parents=True)
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        (self.nested / "context.txt").write_text("nested\n", encoding="utf-8")
        run_git(
            self.root, "add", ".gitignore", "base.txt", "project/nested/context.txt"
        )
        run_git(
            self.root,
            "commit",
            "-q",
            "-m",
            "base",
            env={
                "GIT_AUTHOR_DATE": "2026-07-30T12:00:00+00:00",
                "GIT_COMMITTER_DATE": "2026-07-30T12:00:00+00:00",
            },
        )
        self.base = self.git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, cwd: Path, *argv: str, check: bool = True) -> str:
        return run_git(cwd, *argv, check=check).stdout.strip()

    def cli(
        self,
        cwd: Path,
        *argv: str,
        script: Path = SCRIPT,
        skill_dir: Path = VERIFIED_SKILL,
    ) -> subprocess.CompletedProcess[str]:
        return run_cli(cwd, *argv, script=script, skill_dir=skill_dir)

    def success(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json_object(result.stdout)

    def assert_help_surface(
        self,
        argv: tuple[str, ...],
        *,
        commands: tuple[str, ...] | None = None,
        long_options: tuple[str, ...] = (),
    ) -> str:
        """Assert one public argparse help surface without importing the parser."""
        result = self.cli(self.nested, *argv, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.startswith("usage: orchestrate.py "))
        choices = re.search(r"\{([^{}]+)\}", result.stdout)
        if commands is not None:
            self.assertIsNotNone(choices, result.stdout)
            assert choices is not None
            self.assertEqual(
                tuple(part.strip() for part in choices.group(1).split(",")),
                commands,
            )
        observed_options = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", result.stdout))
        observed_options.discard("--help")
        self.assertEqual(observed_options, set(long_options))
        return result.stdout

    def managed_state_snapshot(self) -> dict[str, object]:
        """Capture public Git/filesystem facts used by atomic-refusal tests."""
        state_root = self.root / ".agent_state"
        filesystem: list[tuple[str, str, bytes | str | None]] = []
        if state_root.exists():
            for path in sorted(state_root.rglob("*")):
                relative = path.relative_to(state_root).as_posix()
                if path.is_symlink():
                    filesystem.append((relative, "symlink", os.readlink(path)))
                elif path.is_dir():
                    filesystem.append((relative, "directory", None))
                else:
                    filesystem.append((relative, "file", path.read_bytes()))
        return {
            "refs": self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname) %(objectname)",
                "refs/orchestrate/",
                "refs/heads/wave/",
            ),
            "worktrees": self.git(self.root, "worktree", "list", "--porcelain"),
            "filesystem": filesystem,
        }

    def mutation_success(
        self,
        result: subprocess.CompletedProcess[str],
        operation: str,
        *,
        warnings: bool = False,
    ) -> dict[str, Any]:
        payload = self.success(result)
        required: dict[str, Any] = {
            "ok": True,
            "operation": operation,
            "orchestrate_version": self.orchestrate_version,
        }
        if warnings:
            self.assertEqual(set(payload), {*required, "warnings"})
            self.assertIsInstance(payload["warnings"], list)
            self.assertTrue(payload["warnings"])
        else:
            self.assertEqual(payload, required)
        return payload

    def lane_check_success(
        self,
        result: subprocess.CompletedProcess[str],
    ) -> dict[str, Any]:
        """`lane check` reports the lane it measured, not a bare envelope."""
        payload = self.success(result)
        self.assertEqual(
            set(payload),
            {
                "ok",
                "operation",
                "orchestrate_version",
                "sha",
                "base",
                "protected_paths",
                "contract_commits",
            },
        )
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["operation"], "lane-check")
        self.assertEqual(payload["orchestrate_version"], self.orchestrate_version)
        self.assertRegex(payload["sha"], r"^[0-9a-f]{40}$")
        self.assertRegex(payload["base"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(payload["protected_paths"], list)
        self.assertEqual(payload["protected_paths"], sorted(payload["protected_paths"]))
        for entry in payload["protected_paths"]:
            self.assertIsInstance(entry, str)
            self.assertTrue(entry)
        self.assertIsInstance(payload["contract_commits"], list)
        for entry in payload["contract_commits"]:
            self.assertRegex(entry, r"^[0-9a-f]{40}$")
        return payload

    def operational_failure(
        self,
        result: subprocess.CompletedProcess[str],
        operation: str,
        code: str,
    ) -> dict[str, Any]:
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        payload = json_object(result.stderr)
        self.assertEqual(
            set(payload), {"ok", "operation", "orchestrate_version", "error"}
        )
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["operation"], operation)
        self.assertEqual(payload["orchestrate_version"], self.orchestrate_version)
        self.assertEqual(set(payload["error"]), {"code", "message"})
        self.assertEqual(payload["error"]["code"], code)
        self.assertIsInstance(payload["error"]["message"], str)
        self.assertTrue(payload["error"]["message"])
        return payload

    def commit_file(
        self,
        cwd: Path,
        path: str,
        content: str | bytes,
        subject: str,
        trailers: tuple[str, ...] = (),
    ) -> str:
        """Create one writer-owned commit and return its observed full SHA."""
        target = cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        run_git(cwd, "add", path)
        message = subject
        if trailers:
            message += "\n\n" + "\n".join(trailers)
        run_git(cwd, "commit", "-q", "-m", message)
        return self.git(cwd, "rev-parse", "HEAD")

    def ref_value(self, ref: str) -> str:
        """Resolve an exact ref to a full SHA, or return the empty string."""
        return self.git(self.root, "show-ref", "--hash", ref, check=False)

    def merge_head(self, cwd: Path) -> str:
        """Return the current MERGE_HEAD, or the empty string when idle."""
        return self.git(cwd, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)

    def commit_lane(self, lane: Path, path: str = "delivered.txt") -> str:
        (lane / path).write_text("delivered\n", encoding="utf-8")
        run_git(lane, "add", path)
        run_git(
            lane,
            "commit",
            "-q",
            "-m",
            "Deliver tracer",
            env={
                "GIT_AUTHOR_DATE": "2026-07-30T12:01:00+00:00",
                "GIT_COMMITTER_DATE": "2026-07-30T12:01:00+00:00",
            },
        )
        return self.git(lane, "rev-parse", "HEAD")
