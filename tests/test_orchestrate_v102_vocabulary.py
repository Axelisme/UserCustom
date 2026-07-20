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


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=False, text=True, capture_output=True
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def init_repo(root: Path) -> str:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "V102")
    git(root, "config", "user.email", "v102@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "branch", "task/demo")
    return git(root, "rev-parse", "HEAD")


def record(
    root: Path, findings: list[dict], verdict: str, **extra: object
) -> subprocess.CompletedProcess[str]:
    receipt = root / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "subject_sha": git(root, "rev-parse", "HEAD"),
                "verdict": verdict,
                "findings": findings,
                **extra,
            }
        ),
        encoding="utf-8",
    )
    return run_cli(
        root, "findings", "record", "--task-id", "demo", "--receipt", str(receipt)
    )


def status(root: Path) -> dict:
    return json.loads(run_cli(root, "findings", "status", "--task-id", "demo").stdout)


class VerdictVocabularyTests(unittest.TestCase):
    """v102: the ledger speaks the same four outcomes as the milestone envelope, so an
    honestly-reported blocked review is recorded instead of rejected."""

    def test_blocked_review_is_recorded_not_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            subject = git(root, "rev-parse", "HEAD")
            result = record(
                root, [], "blocked", evidence=["loopback socket EPERM in sandbox"]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["appended"], [f"review-blocked:{subject}"]
            )
            st = status(root)
            # A blocked review is not a pass: it must not read as clean evidence.
            self.assertEqual(st["review_incomplete"], [subject])
            self.assertEqual(st["reviewed_clean"], [])
            self.assertFalse(st["collect_blocked"])
            marker = st["review_pass"][0]
            self.assertEqual(marker["verdict"], "blocked")
            self.assertEqual(marker["evidence"], ["loopback socket EPERM in sandbox"])

    def test_needs_decision_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            result = record(root, [], "needs_decision", evidence=["contract ambiguous"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(status(root)["review_incomplete"], [git(root, "rev-parse", "HEAD")])

    def test_pass_clean_still_reads_as_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            subject = git(root, "rev-parse", "HEAD")
            self.assertEqual(record(root, [], "pass").returncode, 0)
            st = status(root)
            self.assertEqual(st["reviewed_clean"], [subject])
            self.assertEqual(st["review_incomplete"], [])

    def test_needs_fix_with_no_findings_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            result = record(root, [], "needs_fix")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("needs_fix", result.stderr + result.stdout)


class OptionalSeverityTests(unittest.TestCase):
    """v102: severity has no consumer, so it stops being an obligation."""

    def test_finding_records_without_severity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            result = record(
                root, [{"propagation": "gates-the-slice", "path": "a.py"}], "needs_fix"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            st = status(root)
            self.assertEqual(len(st["gating_open"]), 1)
            self.assertTrue(st["collect_blocked"])

    def test_propagation_is_still_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            result = record(root, [{"severity": "blocker"}], "needs_fix")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("propagation", result.stderr + result.stdout)


class OwnerCollisionTests(unittest.TestCase):
    """v102: closes the residual id collision the v101 review filed."""

    def test_findings_differing_only_in_owner_stay_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            base = {"propagation": "backlog", "path": "a.py"}
            self.assertEqual(record(root, [{**base, "owner": "alice"}], "needs_fix").returncode, 0)
            self.assertEqual(record(root, [{**base, "owner": "bob"}], "needs_fix").returncode, 0)
            owners = sorted(r["owner"] for r in status(root)["open"])
            self.assertEqual(owners, ["alice", "bob"])


class DerivedIdStabilityTests(unittest.TestCase):
    """Finding A: widening the identity set must not renumber findings that do not
    use the new fields, or a replayed receipt lands an unclosed duplicate."""

    def test_default_valued_fields_do_not_enter_the_id(self) -> None:
        sys.path.insert(
            0, str(ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts")
        )
        from _orchestrate.findings import derived_finding_id

        sha = "a" * 40
        bare = {"propagation": "backlog", "path": "b.py"}
        # Explicit defaults and absent keys are the same finding.
        self.assertEqual(
            derived_finding_id(sha, bare),
            derived_finding_id(
                sha, {**bare, "owner": None, "requires_refreshed_review": False}
            ),
        )
        # A real value still separates them.
        self.assertNotEqual(
            derived_finding_id(sha, bare),
            derived_finding_id(sha, {**bare, "owner": "alice"}),
        )


class MarkerOverlapTests(unittest.TestCase):
    """Finding C: a subject cannot be both clean and incomplete."""

    def test_a_later_pass_settles_an_earlier_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            subject = git(root, "rev-parse", "HEAD")
            self.assertEqual(record(root, [], "blocked").returncode, 0)
            self.assertEqual(record(root, [], "pass").returncode, 0)
            st = status(root)
            self.assertEqual(st["reviewed_clean"], [subject])
            self.assertEqual(st["review_incomplete"], [])


if __name__ == "__main__":
    unittest.main()
