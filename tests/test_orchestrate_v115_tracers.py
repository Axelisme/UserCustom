from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"
from tests._orchestrate_test_support import cli_command


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cli_command(SCRIPT, [*args, "--root", str(root)]),
        text=True,
        capture_output=True,
        check=False,
    )


class V115ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "v115"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "v115@example.invalid"], cwd=self.root, check=True)
        (self.root / "base").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.root, check=True, capture_output=True)
        self.base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
        # Put one closed row and a large review history in the same task ledger;
        # opt-in projections must not leak either through matched or evidence rows.
        (self.root / "base").write_text("base\nclosed\n", encoding="utf-8")
        subprocess.run(["git", "add", "base"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "close finding", "-m", "Closes-Finding: closed-one"],
            cwd=self.root, check=True, capture_output=True,
        )
        ledger = self.root / ".agent_state" / "orchestrate" / "findings"
        ledger.mkdir(parents=True)
        self.records = [
            {"id": "open-one", "path": "a.py", "propagation": "follow-up-to-writer", "sweep_required": False},
            {"id": "open-two", "path": "b.py", "propagation": "gates-the-slice", "sweep_required": False},
            {"id": "closed-one", "path": "closed.py", "propagation": "backlog", "sweep_required": False},
        ]
        rows = [json.dumps({**r, "subject_sha": self.base_sha}) for r in self.records]
        rows.extend(
            json.dumps({"id": f"review-{i}", "kind": "review-pass", "subject_sha": self.base_sha,
                        "verdict": "pass", "evidence": ["evidence"]})
            for i in range(100)
        )
        (ledger / "demo.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def status(self, *args: str) -> dict:
        result = run(self.root, "findings", "status", "--task-id", "demo", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_summary_has_no_rows_and_preserves_gate_projection(self) -> None:
        payload = self.status("--summary")
        self.assertTrue(payload["read_only"])
        self.assertNotIn("open", payload)
        self.assertNotIn("closed", payload)
        self.assertEqual(payload["counts"]["open"], 2)
        self.assertEqual(payload["counts"]["closed"], 1)
        self.assertEqual(payload["counts"]["review_outcomes"], 100)
        self.assertTrue(payload["gating_open"])
        self.assertTrue(payload["slice_blocking"] is False)
        self.assertTrue(payload["collect_blocked"])
        self.assertLess(len(json.dumps(payload)), 2000)

    def test_ids_and_open_only_are_exact_composable_projections(self) -> None:
        payload = self.status("--open-only", "--ids", "open-two,unknown")
        self.assertEqual([row["id"] for row in payload["open"]], ["open-two"])
        self.assertNotIn("closed", payload)
        self.assertNotIn("review_outcomes", payload)
        self.assertEqual(payload["gating_open"], ["open-two"])

    def test_open_only_path_does_not_leak_closed_rows_or_review_history(self) -> None:
        payload = self.status("--open-only", "--path", "closed.py")
        self.assertEqual(payload["matched"], [])
        self.assertNotIn("closed", payload)
        self.assertNotIn("review_outcomes", payload)

    def test_summary_large_gate_ledger_is_bounded(self) -> None:
        ledger = self.root / ".agent_state" / "orchestrate" / "findings" / "demo.jsonl"
        with ledger.open("a", encoding="utf-8") as handle:
            for i in range(6000):
                handle.write(json.dumps({
                    "id": f"large-gate-{i}", "path": "large.py",
                    "propagation": "gates-the-slice", "subject_sha": self.base_sha,
                }) + "\n")
        result = run(self.root, "findings", "status", "--task-id", "demo", "--summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(len(result.stdout.encode()), 2000)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["gating_open"])
        self.assertEqual(payload["counts"]["gating_open"], 6001)

    def test_unknown_ids_are_empty_without_changing_gate_authority(self) -> None:
        payload = self.status("--summary", "--ids", "missing", "--slice-sha", self.base_sha)
        self.assertEqual(payload["counts"]["open"], 0)
        self.assertTrue(payload["collect_blocked"])
        self.assertTrue(payload["gating_open"])
        self.assertTrue(payload["slice_blocking"])
        self.assertEqual(payload["counts"]["slice_blocking"], 1)

    def test_ids_do_not_hide_slice_blocking_in_full_projection(self) -> None:
        payload = self.status("--ids", "missing", "--slice-sha", self.base_sha)
        self.assertEqual(payload["open"], [])
        self.assertEqual(payload["slice_blocking"], ["open-two"])
        self.assertTrue(payload["collect_blocked"])


class V115ProfileRecommendationTests(unittest.TestCase):
    def recommend(self, runtime: str, role: str, risk: str, depth: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "profile", "recommend", "--runtime", runtime,
             "--role", role, "--risk", risk, "--depth", depth],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_all_supported_runtime_profile_combinations(self) -> None:
        expected = {
            ("codex", "reviewer", "normal", "low"): ("wave-reviewer", "gpt-5.6-sol", "low"),
            ("codex", "reviewer", "critical", "high"): ("wave-reviewer", "gpt-5.6-sol", "high"),
            ("codex", "implementer", "normal", "high"): ("wave-implementer", "gpt-5.6-luna", "high"),
            ("codex", "implementer", "critical", "high"): ("wave-implementer", "gpt-5.6-luna", "high"),
            ("claude", "reviewer", "normal", "low"): ("wave-reviewer", "opus", None),
            ("claude", "reviewer", "critical", "high"): ("wave-reviewer", "opus", None),
            ("claude", "implementer", "normal", "high"): ("wave-implementer", "sonnet", None),
            ("claude", "implementer", "critical", "high"): ("wave-implementer", "sonnet", None),
            ("pi", "reviewer", "normal", "low"): ("wave-reviewer", "openai-codex/gpt-5.6-sol", "low"),
            ("pi", "reviewer", "critical", "high"): ("wave-reviewer", "openai-codex/gpt-5.6-sol", "high"),
            ("pi", "implementer", "normal", "high"): ("wave-implementer", "openai-codex/gpt-5.6-luna", "high"),
            ("pi", "implementer", "critical", "high"): ("wave-implementer", "openai-codex/gpt-5.6-luna", "high"),
        }
        for combination, (profile, model, thinking) in expected.items():
            with self.subTest(combination=combination):
                payload = self.recommend(*combination)
                self.assertEqual((payload["profile"], payload["model"], payload["thinking"]),
                                 (profile, model, thinking))
                self.assertTrue(payload["read_only"])
                self.assertFalse(payload["spawned"])
                self.assertFalse(payload["mutated"])

    def test_mechanical_implementer_fails_closed(self) -> None:
        for runtime in ("codex", "claude", "pi"):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "profile", "recommend", "--runtime", runtime,
                 "--role", "implementer", "--risk", "mechanical", "--depth", "high"],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported profile combination", result.stderr)

    def test_unsupported_depth_fails_closed(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "profile", "recommend", "--runtime", "pi",
             "--role", "reviewer", "--risk", "normal", "--depth", "high"],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported profile combination", result.stderr)


if __name__ == "__main__":
    unittest.main()
