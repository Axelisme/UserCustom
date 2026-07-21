from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def run(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--root", str(root)],
        text=True,
        capture_output=True,
    )


def init_repo(root: Path) -> str:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "receipt")
    git(root, "config", "user.email", "receipt@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    return git(root, "rev-parse", "HEAD")


def receipt(root: Path, **overrides: object) -> Path:
    path = root / "receipt.json"
    path.write_text(
        json.dumps(
            {
                "subject_sha": git(root, "rev-parse", "HEAD"),
                "verdict": "needs_fix",
                "evidence": ["targeted test output"],
                "findings": [
                    {
                        "propagation": "gates-the-slice",
                        "path": "home/example.py",
                        "behavior": "receipt loses evidence",
                        "evidence": ["ledger row lacks field"],
                    }
                ],
                **overrides,
            }
        ),
        encoding="utf-8",
    )
    return path


class ReceiptContractTests(unittest.TestCase):
    def test_validate_is_read_only_for_pass_and_needs_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subject = init_repo(root)
            pass_receipt = receipt(root, verdict="pass", findings=[])
            before = root / ".agent_state"
            result = run(root, "findings", "validate", "--receipt", str(pass_receipt))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(before.exists())
            payload = json.loads(result.stdout)
            self.assertEqual(payload["operation"], "findings-validate")
            self.assertEqual(payload["subject_sha"], subject)
            result = run(root, "findings", "validate", "--receipt", str(receipt(root)))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(before.exists())

    def test_alias_normalizes_to_canonical_ledger_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            path = receipt(root)
            raw = json.loads(path.read_text(encoding="utf-8"))
            finding = raw["findings"][0]
            finding["observable_behavior"] = finding.pop("behavior")
            path.write_text(json.dumps(raw), encoding="utf-8")
            sys.path.insert(0, str(ROOT / "home/.codex/skills/orchestrate/scripts"))
            from _orchestrate.findings import command_findings_record

            result = command_findings_record(
                argparse.Namespace(root=str(root), task_id="demo", receipt=str(path))
            )
            self.assertTrue(result["ok"])
            ledger = root / ".agent_state/orchestrate/findings/demo.jsonl"
            rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            finding_row = next(row for row in rows if row.get("kind") is None)
            marker = next(row for row in rows if row.get("kind") == "review-needs_fix")
            self.assertEqual(finding_row["behavior"], "receipt loses evidence")
            self.assertNotIn("observable_behavior", finding_row)
            self.assertEqual(marker["evidence"], ["targeted test output"])

    def test_rejects_conflicts_aliases_and_missing_nonempty_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            cases = (
                {"outcome": "pass"},
                {"review_findings": []},
                {"findings": [{"P1": True}]},
                {"findings": [{"severity": "P2"}]},
                {"findings": [{"behavior": "canonical", "observable_behavior": "other"}]},
                {"findings": [{"behavior": "", "evidence": [], "path": ""}]},
            )
            for overrides in cases:
                with self.subTest(overrides=overrides):
                    result = run(root, "findings", "validate", "--receipt", str(receipt(root, **overrides)))
                    self.assertNotEqual(result.returncode, 0)

    def test_rejects_type_invalid_fields_with_controlled_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            cases = (
                {"subject_sha": 42},
                {"evidence": []},
                {"findings": [{"id": 42, "propagation": "gates-the-slice", "path": "x.py", "behavior": "bad", "evidence": ["x"]}]},
                {"evidence": "  "},
                {"findings": [{"propagation": "gates-the-slice", "path": {}, "behavior": "bad", "evidence": ["x"]}]},
                {"findings": [{"propagation": "gates-the-slice", "path": "x.py", "behavior": True, "evidence": ["x"]}]},
                {"findings": [{"propagation": "gates-the-slice", "path": " ", "behavior": "bad", "evidence": ["x"]}]},
                {"findings": [{"propagation": "gates-the-slice", "path": "x.py", "behavior": " ", "evidence": ["x"]}]},
                {"findings": [{"propagation": "gates-the-slice", "path": "x.py", "behavior": "bad", "evidence": {}}]},
                {"findings": [{"propagation": "gates-the-slice", "path": "x.py", "behavior": True, "observable_behavior": 1, "evidence": ["x"]}]},
            )
            for overrides in cases:
                with self.subTest(overrides=overrides):
                    result = run(root, "findings", "validate", "--receipt", str(receipt(root, **overrides)))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("orchestrate error:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertNotIn("TypeError", result.stderr)
                    self.assertNotIn("AttributeError", result.stderr)

    def test_evidence_preserves_arbitrary_nonempty_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            receipt_evidence = {"commands": ["test", {"passed": True}], "count": 1}
            finding_evidence = [False, 0, {"detail": "kept"}]
            path = receipt(root, evidence=receipt_evidence)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["findings"][0]["evidence"] = finding_evidence
            path.write_text(json.dumps(raw), encoding="utf-8")
            sys.path.insert(0, str(ROOT / "home/.codex/skills/orchestrate/scripts"))
            from _orchestrate.findings import command_findings_record

            command_findings_record(argparse.Namespace(root=str(root), task_id="demo", receipt=str(path)))
            rows = [json.loads(line) for line in (root / ".agent_state/orchestrate/findings/demo.jsonl").read_text(encoding="utf-8").splitlines()]
            finding_row = next(row for row in rows if row.get("kind") is None)
            marker = next(row for row in rows if row.get("kind") == "review-needs_fix")
            self.assertEqual(finding_row["evidence"], finding_evidence)
            self.assertEqual(marker["evidence"], receipt_evidence)

    def test_duplicate_derived_ids_require_explicit_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            findings = [
                {
                    "propagation": "gates-the-slice",
                    "path": "same.py",
                    "behavior": behavior,
                    "evidence": [behavior],
                }
                for behavior in ("first defect", "second defect")
            ]
            duplicate = run(
                root,
                "findings",
                "validate",
                "--receipt",
                str(receipt(root, findings=findings)),
            )
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("distinct explicit ids", duplicate.stderr)
            for index, finding in enumerate(findings, 1):
                finding["id"] = f"DISTINCT-{index}"
            explicit = run(
                root,
                "findings",
                "validate",
                "--receipt",
                str(receipt(root, findings=findings)),
            )
            self.assertEqual(explicit.returncode, 0, explicit.stderr)

    def test_legacy_marker_replay_deduplicates_by_receipt_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subject = init_repo(root)
            evidence = ["recorded before evidence-hashed marker ids"]
            ledger = root / ".agent_state/orchestrate/findings/demo.jsonl"
            ledger.parent.mkdir(parents=True)
            legacy_id = f"review-pass:{subject}"
            ledger.write_text(
                json.dumps(
                    {
                        "id": legacy_id,
                        "kind": "review-pass",
                        "subject_sha": subject,
                        "verdict": "pass",
                        "evidence": evidence,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            replay = run(
                root,
                "findings",
                "record",
                "--task-id",
                "demo",
                "--receipt",
                str(receipt(root, verdict="pass", evidence=evidence, findings=[])),
            )
            self.assertEqual(replay.returncode, 0, replay.stderr)
            payload = json.loads(replay.stdout)
            self.assertEqual(payload["appended"], [])
            self.assertEqual(payload["skipped_existing"], [legacy_id])
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 1)

    def test_legacy_replay_preserves_json_type_distinctions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subject = init_repo(root)
            ledger = root / ".agent_state/orchestrate/findings/demo.jsonl"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(
                json.dumps(
                    {
                        "id": f"review-pass:{subject}",
                        "kind": "review-pass",
                        "subject_sha": subject,
                        "verdict": "pass",
                        "evidence": [True],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            marker_ids: list[str] = []
            for distinct_evidence in ([1], [1.0]):
                result = run(
                    root,
                    "findings",
                    "record",
                    "--task-id",
                    "demo",
                    "--receipt",
                    str(
                        receipt(
                            root,
                            verdict="pass",
                            evidence=distinct_evidence,
                            findings=[],
                        )
                    ),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                marker_ids.append(json.loads(result.stdout)["appended"][0])
            self.assertNotEqual(marker_ids[0], marker_ids[1])
            replay = run(
                root,
                "findings",
                "record",
                "--task-id",
                "demo",
                "--receipt",
                str(receipt(root, verdict="pass", evidence=[1], findings=[])),
            )
            self.assertEqual(json.loads(replay.stdout)["skipped_existing"], [marker_ids[0]])
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 3)

    def test_distinct_receipt_evidence_is_preserved_and_replay_dedups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            first = receipt(root, verdict="pass", evidence=["first"], findings=[])
            first_result = run(
                root, "findings", "record", "--task-id", "demo", "--receipt", str(first)
            )
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            first_id = json.loads(first_result.stdout)["appended"][0]
            second = receipt(root, verdict="pass", evidence=["second"], findings=[])
            second_result = run(
                root, "findings", "record", "--task-id", "demo", "--receipt", str(second)
            )
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            second_id = json.loads(second_result.stdout)["appended"][0]
            self.assertNotEqual(first_id, second_id)
            replay = run(
                root, "findings", "record", "--task-id", "demo", "--receipt", str(second)
            )
            self.assertEqual(json.loads(replay.stdout)["skipped_existing"], [second_id])
            status = json.loads(
                run(root, "findings", "status", "--task-id", "demo").stdout
            )
            self.assertEqual(
                [marker["evidence"] for marker in status["review_outcomes"]],
                [["first"], ["second"]],
            )

    def test_canonical_behavior_receipt_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            result = run(root, "findings", "validate", "--receipt", str(receipt(root)))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_codex_pi_mirrors_and_coordination_budget(self) -> None:
        codex = ROOT / "home/.codex/skills/orchestrate"
        pi = ROOT / "home/.pi/agent/skills/orchestrate"
        for relative in (
            "scripts/_orchestrate/findings.py",
            "scripts/_orchestrate/cli.py",
            "references/coordination.md",
        ):
            with self.subTest(relative=relative):
                self.assertEqual((codex / relative).read_bytes(), (pi / relative).read_bytes())
        self.assertLessEqual(len((codex / "references/coordination.md").read_bytes()), 16_384)
        self.assertLessEqual(len((pi / "references/coordination.md").read_bytes()), 16_384)


if __name__ == "__main__":
    unittest.main()
