from __future__ import annotations

import argparse
import json
from importlib import import_module
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._orchestrate_test_support import verified_skill_dir

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPTS = SKILL / "scripts"
ENTRYPOINT = SCRIPTS / "orchestrate.py"
sys.path.insert(0, str(SCRIPTS))

command_collect = import_module("_orchestrate.lanes").command_collect
release = import_module("_orchestrate.release")
document_paths = release.document_paths
profile_paths = release.profile_paths
source_home = release.source_home


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=False, text=True, capture_output=True
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


class OrchestratePackageTests(unittest.TestCase):
    def test_entrypoint_is_thin_and_parser_keeps_current_commands(self) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertLess(len(text.encode()), 512)
        result = subprocess.run(
            [sys.executable, str(ENTRYPOINT), "--help"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("compose-base", "review", "findings", "revalidate", "reconcile"):
            self.assertIn(command, result.stdout)

    def test_manifest_enumerates_nested_package_but_not_readme(self) -> None:
        relative = {
            path.relative_to(SKILL).as_posix() for path in document_paths(SKILL)
        }
        self.assertIn("runtime-pi.md", relative)
        self.assertIn("scripts/orchestrate.py", relative)
        self.assertIn("scripts/_orchestrate/__init__.py", relative)
        self.assertIn("scripts/_orchestrate/cli.py", relative)
        self.assertIn("scripts/_orchestrate/release.py", relative)
        self.assertNotIn("README.md", relative)
        self.assertFalse(any("__pycache__" in path for path in relative))

    def test_verified_cli_fixture_binds_every_shipped_profile(self) -> None:
        fixture = Path(verified_skill_dir(str(SKILL)))
        manifest = json.loads(
            (fixture / "manifests" / "118.json").read_text(encoding="utf-8")
        )
        source_root = source_home(SKILL)
        expected = {
            path.relative_to(source_root).as_posix()
            for path in profile_paths(source_root)
            if path.is_file()
        }
        self.assertEqual(len(expected), 36)
        self.assertEqual(set(manifest["profiles"]), expected)
        self.assertTrue(all(entry["sha256"] for entry in manifest["profiles"].values()))

    def test_collect_parser_derives_task_and_keeps_authority_explicit(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ENTRYPOINT), "collect", "--help"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--integration-worktree", result.stdout)
        self.assertIn("--authorized-sha", result.stdout)
        self.assertIn("--review-kind", result.stdout)
        self.assertNotIn("--expected-lane-sha", result.stdout)
        self.assertNotIn("--task-ref", result.stdout)
        self.assertNotIn("--root", result.stdout)

    def test_collect_derives_task_ref_and_recovers_after_lane_ref_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            git(root, "init", "-b", "main")
            git(root, "config", "user.name", "Package Test")
            git(root, "config", "user.email", "package@example.invalid")
            (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
            (root / "base.txt").write_text("base\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-m", "base")
            git(root, "checkout", "-b", "task/demo")
            base = git(root, "rev-parse", "HEAD")
            git(root, "branch", "agent/demo/a", base)
            lane = root / ".agent_state" / "worktrees" / "demo-a"
            lane.parent.mkdir(parents=True)
            git(root, "worktree", "add", str(lane), "agent/demo/a")
            (lane / "a.txt").write_text("a\n", encoding="utf-8")
            git(lane, "add", "a.txt")
            git(lane, "commit", "-m", "lane")
            authorized = git(root, "rev-parse", "agent/demo/a")
            ledger = root / ".agent_state" / "orchestrate" / "findings" / "demo.jsonl"
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text(json.dumps({"id": "review-pass:demo", "kind": "review-pass",
                                          "subject_sha": authorized, "verdict": "pass",
                                          "evidence": ["package-test"]}) + "\n", encoding="utf-8")
            args = argparse.Namespace(
                root=str(root),
                lane_ref="agent/demo/a",
                authorized_sha=authorized,
                review_kind="different-identity",
            )

            collected = command_collect(args)

            self.assertEqual(collected["task_ref"], "task/demo")
            self.assertEqual(collected["authorized_sha"], authorized)
            self.assertEqual(collected["authorization_source"], "declared")
            self.assertFalse(collected["verdict_inferred"])
            git(root, "worktree", "remove", str(lane))
            git(root, "branch", "-D", "agent/demo/a")
            recovered = command_collect(args)
            self.assertEqual(recovered["recovered"], "already-collected")


if __name__ == "__main__":
    unittest.main()
