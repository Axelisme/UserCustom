from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = SKILL / "scripts" / "orchestrate.py"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )


class OrchestrateCliTests(unittest.TestCase):
    def test_current_command_inventory(self) -> None:
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "doctor",
            "diff",
            "lane",
            "compose-base",
            "review",
            "land",
            "collect",
            "cleanup",
            "slice",
            "findings",
            "revalidate",
            "reconcile",
            "pin",
            "release",
        ):
            self.assertIn(command, result.stdout)
        for removed in ("packet", "queue", "milestone lint"):
            self.assertNotIn(removed, result.stdout)

    def test_collect_derives_observed_state_but_keeps_authority_explicit(self) -> None:
        result = run_cli("collect", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--integration-worktree", result.stdout)
        self.assertIn("--lane-ref", result.stdout)
        self.assertIn("--authorized-sha", result.stdout)
        self.assertIn("--review-kind", result.stdout)
        self.assertNotIn("--task-ref", result.stdout)
        self.assertNotIn("--expected-lane-sha", result.stdout)
        self.assertNotIn("--root", result.stdout)

    def test_default_skill_dir_builds_recursive_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "manifest.json"
            result = run_cli(
                "release-manifest",
                "--version",
                "95",
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(output.read_text(encoding="utf-8"))
            documents = manifest["documents"]
            self.assertIn("scripts/orchestrate.py", documents)
            self.assertIn("scripts/_orchestrate/cli.py", documents)
            self.assertIn("scripts/_orchestrate/release.py", documents)
            self.assertNotIn("README.md", documents)

    def test_invalid_exact_sha_exits_two_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(
                ["git", "init", "-b", "task/demo"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            result = run_cli(
                "review",
                "audit",
                "--root",
                str(root),
                "--base",
                "HEAD",
                "--subject",
                "HEAD",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("must be an exact hexadecimal commit SHA", result.stderr)
            self.assertFalse((root / ".agent_state").exists())


if __name__ == "__main__":
    unittest.main()
