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
        check=False,
        text=True,
        capture_output=True,
    )


def run_collect(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """collect names its checkout --integration-worktree, not --root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "collect", "--integration-worktree", str(root), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=False, text=True, capture_output=True
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def init_repo(root: Path) -> str:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "V100")
    git(root, "config", "user.email", "v100@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")
    return git(root, "rev-parse", "HEAD")


class CollectItemBindingTests(unittest.TestCase):
    """v100 #3: a reused lane ref is git-valid but collects the wrong work."""

    def _lane_with_item(self, root: Path, item: str) -> str:
        git(root, "checkout", "-q", "-b", "agent/demo/a", "task/demo")
        (root / f"{item}.txt").write_text(item, encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-m", f"work\n\nItem: {item}")
        head = git(root, "rev-parse", "HEAD")
        git(root, "checkout", "-q", "task/demo")
        return head

    def test_collect_rejects_a_lane_carrying_another_item(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            head = self._lane_with_item(root, "SH-01B")
            result = run_collect(
                root,
                "--lane-ref",
                "agent/demo/a",
                "--authorized-sha",
                head,
                "--review-kind",
                "different-identity",
                "--item",
                "AI-02C",
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stderr + result.stdout
            self.assertIn("SH-01B", combined)
            self.assertIn("AI-02C", combined)

    def test_collect_accepts_the_matching_item_and_reports_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            head = self._lane_with_item(root, "SH-01B")
            result = run_collect(
                root,
                "--lane-ref",
                "agent/demo/a",
                "--authorized-sha",
                head,
                "--review-kind",
                "different-identity",
                "--item",
                "SH-01B",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["item_id"], "SH-01B")
            self.assertTrue(payload["item_trailer_present"])

    def test_collect_still_works_without_item_but_surfaces_the_lane_item(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            head = self._lane_with_item(root, "SH-01B")
            result = run_collect(
                root,
                "--lane-ref",
                "agent/demo/a",
                "--authorized-sha",
                head,
                "--review-kind",
                "different-identity",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["item_id"], "SH-01B")


class ReviewWorktreeClassificationTests(unittest.TestCase):
    """v100 #7: review relevance is derivable from Git; liveness is not."""

    def test_unabsorbed_review_stays_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            # A commit that never reaches task/demo: its review is still meaningful.
            git(root, "checkout", "-q", "-b", "side", "task/demo")
            (root / "side.txt").write_text("s\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-m", "side")
            side = git(root, "rev-parse", "HEAD")
            git(root, "checkout", "-q", "task/demo")
            managed = root / ".agent_state" / "worktrees"
            managed.mkdir(parents=True)
            git(root, "worktree", "add", "--detach", str(managed / "review-side"), side)

            payload = json.loads(run_cli(root, "reconcile").stdout)
            entry = next(
                item
                for item in payload["worktrees"]
                if item["path"].endswith("review-side")
            )
            self.assertEqual(entry["kind"], "review")
            self.assertEqual(entry["class"], "active")
            self.assertIsNone(entry["absorbed_into"])
            self.assertFalse(entry["cleanup_eligible"])
            self.assertNotIn(entry["path"], payload["safe_to_remove"])


class FindingsScopeAndSchemaTests(unittest.TestCase):
    """v100 #6 scope buckets and #1 receipt-schema normalization."""

    def _record(self, root: Path, findings: list[dict], verdict: str) -> None:
        receipt = root / "receipt.json"
        canonical_findings = [
            {
                "path": "test.py",
                "behavior": "test finding",
                "evidence": ["test evidence"],
                **finding,
            }
            for finding in findings
        ]
        receipt.write_text(
            json.dumps(
                {
                    "subject_sha": git(root, "rev-parse", "HEAD"),
                    "verdict": verdict,
                    "evidence": ["test receipt"],
                    "findings": canonical_findings,
                }
            ),
            encoding="utf-8",
        )
        result = run_cli(
            root, "findings", "record", "--task-id", "demo", "--receipt", str(receipt)
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_id_is_derived_when_omitted_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            finding = {"severity": "major", "propagation": "follow-up-to-writer"}
            self._record(root, [finding], "needs_fix")
            first = json.loads(
                run_cli(root, "findings", "status", "--task-id", "demo").stdout
            )
            self.assertEqual(len(first["open"]), 1)
            derived = first["open"][0]["id"]
            self.assertTrue(derived)
            # Re-recording the same receipt dedups instead of duplicating.
            self._record(root, [finding], "needs_fix")
            second = json.loads(
                run_cli(root, "findings", "status", "--task-id", "demo").stdout
            )
            self.assertEqual([r["id"] for r in second["open"]], [derived])

    def test_distinct_findings_on_one_subject_never_share_a_derived_id(self) -> None:
        # Regression: a position-keyed id let a second receipt's finding collide with
        # the first's, silently dropping it. When the dropped one gated, collect_blocked
        # went false and the gate was defeated.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            self._record(
                root, [{"severity": "minor", "propagation": "backlog"}], "needs_fix"
            )
            self._record(
                root,
                [{"severity": "blocker", "propagation": "gates-the-slice"}],
                "needs_fix",
            )
            status = json.loads(
                run_cli(root, "findings", "status", "--task-id", "demo").stdout
            )
            self.assertEqual(len(status["open"]), 2)
            self.assertEqual(len(status["gating_open"]), 1)
            self.assertTrue(status["collect_blocked"])

    def test_propagation_is_never_inferred(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            receipt = root / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "subject_sha": git(root, "rev-parse", "HEAD"),
                        "verdict": "needs_fix",
                        "evidence": ["test receipt"],
                        "findings": [
                            {
                                "path": "a.py",
                                "behavior": "test finding",
                                "evidence": ["test evidence"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = run_cli(
                root,
                "findings",
                "record",
                "--task-id",
                "demo",
                "--receipt",
                str(receipt),
            )
            self.assertNotEqual(result.returncode, 0)
            # v102: severity became optional (no consumer branches on it), but
            # propagation decides gating and is still never inferred.
            self.assertIn("propagation", result.stderr + result.stdout)

    def test_scope_buckets_separate_unrelated_from_gating(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            self._record(
                root,
                [
                    {
                        "id": "GATE-1",
                        "severity": "major",
                        "propagation": "gates-the-slice",
                    },
                    {
                        "id": "NOTE-1",
                        "severity": "minor",
                        "propagation": "backlog",
                    },
                ],
                "needs_fix",
            )
            status = json.loads(
                run_cli(root, "findings", "status", "--task-id", "demo").stdout
            )
            self.assertEqual(status["gating_open"], ["GATE-1"])
            self.assertEqual(
                [
                    r["id"]
                    for r in status["open"]
                    if r["propagation"] != "gates-the-slice"
                ],
                ["NOTE-1"],
            )
            # Without --slice-sha the slice split is undetermined, not guessed.
            self.assertIsNone(status["slice_blocking"])
            # Gate semantics are unchanged.
            self.assertTrue(status["collect_blocked"])


class WaveSummaryTests(unittest.TestCase):
    """v100 #2: the rollup must be readable without spending a context window."""

    def test_summary_drops_the_three_full_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            full = run_cli(root, "wave", "status", "--task-ref", "task/demo")
            brief = run_cli(
                root, "wave", "status", "--task-ref", "task/demo", "--summary"
            )
            self.assertEqual(full.returncode, 0, full.stderr)
            self.assertEqual(brief.returncode, 0, brief.stderr)
            full_payload = json.loads(full.stdout)
            brief_payload = json.loads(brief.stdout)
            for key in ("slice", "findings", "reconcile"):
                self.assertIn(key, full_payload)
                self.assertNotIn(key, brief_payload)
            self.assertEqual(brief_payload["handoff"], full_payload["handoff"])
            self.assertLess(len(brief.stdout), len(full.stdout))


if __name__ == "__main__":
    unittest.main()
