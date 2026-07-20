from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


def run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--root", str(root)],
        check=False, text=True, capture_output=True,
    )


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, check=False, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def init_repo(root: Path) -> None:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "V105")
    git(root, "config", "user.email", "v105@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")


def record(root: Path, findings: list[dict]) -> subprocess.CompletedProcess[str]:
    subject = git(root, "rev-parse", "HEAD")
    receipt = root / "receipt.json"
    receipt.write_text(json.dumps({"subject_sha": subject, "verdict": "needs_fix", "findings": findings}), encoding="utf-8")
    return run_cli(root, "findings", "record", "--task-id", "demo", "--receipt", str(receipt))


def status(root: Path, *extra: str) -> dict:
    result = run_cli(root, "findings", "status", "--task-id", "demo", *extra)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


class FindingsQueryTests(unittest.TestCase):
    """v105: a reviewer inheriting a surface pulls prior findings from the task-long
    ledger keyed on its own diff's paths (`--path`) or the cross-cutting sweep patterns
    (`--sweep`), without reading the whole ledger and without weakening the gate."""

    def _seed(self, root: Path) -> None:
        init_repo(root)
        # "Wave 1": a finding on auth.py.
        self.assertEqual(record(root, [{"propagation": "follow-up-to-writer", "path": "auth.py", "severity": "major", "behavior": "tenant scope dropped"}]).returncode, 0)
        (root / "c.txt").write_text("c\n", encoding="utf-8")
        git(root, "add", "."); git(root, "commit", "-m", "wave2")
        # "Wave 2": a finding on billing.py and a swept root-cause on util/log.py.
        self.assertEqual(record(root, [{"propagation": "backlog", "path": "billing.py", "severity": "minor"}]).returncode, 0)
        self.assertEqual(record(root, [{"propagation": "gates-the-slice", "path": "util/log.py", "severity": "blocker", "sweep_required": True, "root_cause": "unbounded retry"}]).returncode, 0)

    def test_no_filter_leaves_behavior_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            st = status(root)
            self.assertIsNone(st["matched"])
            self.assertEqual(len(st["open"]), 3)
            self.assertEqual(st["gating_open"], [rec["id"] for rec in st["open"] if rec["propagation"] == "gates-the-slice"])

    def test_path_query_finds_cross_wave_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            matched = status(root, "--path", "auth.py")["matched"]
            self.assertEqual([m["path"] for m in matched], ["auth.py"])

    def test_path_query_matches_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            matched = status(root, "--path", "util")["matched"]
            self.assertEqual([m["path"] for m in matched], ["util/log.py"])

    def test_multiple_paths_union(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            matched = status(root, "--path", "auth.py", "--path", "billing.py")["matched"]
            self.assertEqual(sorted(m["path"] for m in matched), ["auth.py", "billing.py"])

    def test_sweep_isolates_root_cause_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            matched = status(root, "--sweep")["matched"]
            self.assertEqual([(m["path"], m["sweep_required"]) for m in matched], [("util/log.py", True)])

    def test_path_and_sweep_are_conjunctive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            # billing.py is not a sweep, so the conjunction is empty.
            self.assertEqual(status(root, "--path", "billing.py", "--sweep")["matched"], [])
            self.assertEqual([m["path"] for m in status(root, "--path", "util/log.py", "--sweep")["matched"]], ["util/log.py"])


class RetrospectiveContractTests(unittest.TestCase):
    def test_coordination_mandates_three_lens_retro(self) -> None:
        text = (ROOT / "home" / ".codex" / "skills" / "orchestrate" / "references" / "coordination.md").read_text(encoding="utf-8")
        for phrase in ("Write one retrospective every wave", "efficiency", "process-following", "tool-utilization"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
