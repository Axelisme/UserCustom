from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "planning-with-files"
SCRIPT = SKILL / "scripts" / "plan.py"


def run_plan(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )


def plan_directory(root: Path) -> Path:
    return root / ".agent_state" / "plans" / "demo"


def phase_plan(*, first_status: str = "completed") -> str:
    status_rows = []
    notes = []
    for number in range(1, 12):
        status = first_status if number == 1 else "completed"
        status_rows.append(
            f"| Phase {number} | {status} | Scope {number} | Acceptance {number} |"
        )
        notes.extend(
            [
                f"### Phase {number} — Topic {number}",
                "",
                f"- Conclusion / Commit: Commit {number}",
                f"- Detail: Evidence {number}",
                "",
            ]
        )
    return "\n".join(
        [
            "# demo 任務計劃",
            "",
            "**Last updated:** 2026-01-01",
            "",
            "## Goal",
            "",
            "Keep authority intact.",
            "",
            "## Current State",
            "",
            "- ACTIVE AUTHORITY",
            "",
            "## Phase Status",
            "",
            "| Phase | Status | Scope | Acceptance |",
            "|---|---|---|---|",
            *status_rows,
            "",
            "## Decisions",
            "",
            "| ID | Status | Decision | Supersedes / Authority |",
            "|---|---|---|---|",
            "| D-001 | active | Never discard authority. | none |",
            "",
            "## Historical Phase Summary",
            "",
            "| Phase | Topic | Conclusion / Commit |",
            "|---|---|---|",
            "",
            "## Active Notes",
            "",
            *notes,
        ]
    )


def progress_log(row_count: int) -> str:
    timeline_rows = [
        f"| 2026-01-01T00:{number:02d} | agent | action-{number:03d} | result | next |"
        for number in range(1, row_count + 1)
    ]
    return "\n".join(
        [
            "# demo progress",
            "",
            "**Last updated:** 2026-01-01",
            "",
            "## Timeline",
            "",
            "| Time | Actor | Action | Result | Next |",
            "|---|---|---|---|---|",
            *timeline_rows,
            "",
            "## Verification Log",
            "",
            "| Date | Command | Result |",
            "|---|---|---|",
            "",
        ]
    )


def findings(*, closure: str = "D-002") -> str:
    large_open = "O" * 9000
    large_resolved = "R" * 9000
    return "\n".join(
        [
            "# demo findings",
            "",
            "**Last updated:** 2026-01-01",
            "",
            "## Discoveries",
            "",
            "| ID | Status | Date | Area | Finding | Evidence / Closure |",
            "|---|---|---|---|---|---|",
            f"| F-open | open | 2026-01-01 | core | {large_open} | evidence-open |",
            f"| F-resolved | resolved | 2026-01-01 | core | {large_resolved} | {closure} |",
            "",
            "## Design Notes",
            "",
            "- Durable note.",
            "",
            "## Risks",
            "",
            "- Open risk.",
            "",
            "## Open Questions",
            "",
            "- Open question.",
            "",
        ]
    )


class PlanningWithFilesCompactionTests(unittest.TestCase):
    def init(self, root: Path, *options: str) -> Path:
        result = run_plan(root, "init", "demo", "--goal", "Test compaction", *options)
        self.assertEqual(result.returncode, 0, result.stderr)
        return plan_directory(root)

    def test_skill_contract_routes_explicit_bounded_compaction(self) -> None:
        text = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("skill_version: 8", text)
        self.assertIn("checkpoint <task-id>", text)
        self.assertIn("compact <task-id>", text)
        self.assertIn("`status`永遠read-only", text)
        self.assertIn("最多16 KiB", text)
        self.assertIn("最舊的", text)
        self.assertIn("最近20筆", text)
        self.assertIn("open finding", text)
        self.assertIn("immutable cold原文", text)

    def test_compact_below_threshold_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-findings", "--with-progress")
            before = {
                path.relative_to(directory): path.read_bytes()
                for path in directory.rglob("*")
                if path.is_file()
            }

            result = run_plan(root, "compact", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["changed"])
            after = {
                path.relative_to(directory): path.read_bytes()
                for path in directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertFalse((directory / "history").exists())

    def test_checkpoint_validates_and_skips_noop_compaction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-findings", "--with-progress")
            before = {
                path.relative_to(directory): path.read_bytes()
                for path in directory.rglob("*")
                if path.is_file()
            }

            result = run_plan(root, "checkpoint", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["operation"], "checkpoint")
            self.assertFalse(payload["changed"])
            after = {
                path.relative_to(directory): path.read_bytes()
                for path in directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertFalse((directory / "history").exists())

    def test_checkpoint_rejects_invalid_optional_schema_below_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-findings")
            path = directory / "findings.md"
            text = path.read_text(encoding="utf-8").replace(
                "|---|---|---|---|---|---|",
                "|---|---|---|---|---|---|\n"
                "| F-001 | maybe | 2026-01-01 | core | bad status | evidence |",
            )
            path.write_text(text, encoding="utf-8")
            before = path.read_bytes()

            result = run_plan(root, "checkpoint", "demo")

            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid status", result.stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_checkpoint_compacts_when_threshold_is_reached(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root)
            (directory / "task_plan.md").write_text(phase_plan(), encoding="utf-8")

            result = run_plan(root, "checkpoint", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["changed"])
            self.assertEqual(payload["compacted"]["task_plan_phases"], 5)
            history = (directory / "history" / "0001-task-plan.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("planning_compat: 6", history)

    def test_compact_archives_oldest_five_completed_phases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root)
            (directory / "task_plan.md").write_text(phase_plan(), encoding="utf-8")

            result = run_plan(root, "compact", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["compacted"]["task_plan_phases"], 5)
            live = (directory / "task_plan.md").read_text(encoding="utf-8")
            self.assertIn("ACTIVE AUTHORITY", live)
            self.assertIn("D-001", live)
            self.assertNotIn("### Phase 1 —", live)
            self.assertIn("### Phase 6 —", live)
            self.assertNotIn("| Phase 1 | completed |", live)
            self.assertIn("| Phase 1 | Topic 1 | Commit 1 |", live)
            history = sorted((directory / "history").glob("*-task-plan.md"))
            self.assertEqual(len(history), 1)
            archived = history[0].read_text(encoding="utf-8")
            self.assertIn("| Phase 1 | completed | Scope 1 | Acceptance 1 |", archived)
            self.assertIn("### Phase 1 — Topic 1", archived)
            self.assertIn("### Phase 5 — Topic 5", archived)
            self.assertLessEqual(len(archived.encode("utf-8")), 16_384)

    def test_compact_fast_fails_before_moving_active_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root)
            task_plan = directory / "task_plan.md"
            task_plan.write_text(
                phase_plan(first_status="in_progress"), encoding="utf-8"
            )
            before = task_plan.read_bytes()

            result = run_plan(root, "compact", "demo")

            self.assertEqual(result.returncode, 2)
            self.assertIn("without an archivable", result.stderr)
            self.assertEqual(task_plan.read_bytes(), before)
            self.assertFalse((directory / "history").exists())

    def test_compact_progress_keeps_recent_twenty_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-progress")
            progress = directory / "progress.md"
            progress.write_text(progress_log(41), encoding="utf-8")

            result = run_plan(root, "compact", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["compacted"]["progress_timeline_rows"], 21)
            live = progress.read_text(encoding="utf-8")
            self.assertNotIn("action-001", live)
            self.assertIn("action-022", live)
            self.assertIn("action-041", live)
            history = sorted((directory / "history").glob("*-progress.md"))
            self.assertEqual(len(history), 1)
            archived = history[0].read_text(encoding="utf-8")
            self.assertIn("action-001", archived)
            self.assertIn("action-021", archived)
            self.assertLessEqual(len(archived.encode("utf-8")), 16_384)

    def test_subsequent_compaction_never_rewrites_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-progress")
            progress = directory / "progress.md"
            progress.write_text(progress_log(41), encoding="utf-8")
            first_result = run_plan(root, "compact", "demo")
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            first_history = directory / "history" / "0001-progress.md"
            first_bytes = first_history.read_bytes()

            new_rows = "\n".join(
                f"| 2026-01-02T00:{number:02d} | agent | action-{number:03d} | result | next |"
                for number in range(42, 63)
            )
            live = progress.read_text(encoding="utf-8").replace(
                "\n\n## Verification Log", f"\n{new_rows}\n\n## Verification Log"
            )
            progress.write_text(live, encoding="utf-8")

            second_result = run_plan(root, "compact", "demo")

            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            second_payload = json.loads(second_result.stdout)
            self.assertEqual(
                second_payload["compacted"]["progress_timeline_rows"],
                21,
                second_payload,
            )
            self.assertEqual(first_history.read_bytes(), first_bytes)
            self.assertIn("history/0002-progress.md", second_payload["history_files"])

    def test_compact_findings_moves_only_resolved_rows_with_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-findings")
            findings_path = directory / "findings.md"
            findings_path.write_text(findings(), encoding="utf-8")

            result = run_plan(root, "compact", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            live = findings_path.read_text(encoding="utf-8")
            self.assertIn("F-open", live)
            self.assertNotIn("F-resolved", live)
            self.assertIn("Durable note", live)
            self.assertIn("Open risk", live)
            self.assertIn("Open question", live)
            history = sorted((directory / "history").glob("*-findings.md"))
            self.assertEqual(len(history), 1)
            archived = history[0].read_text(encoding="utf-8")
            self.assertIn("F-resolved", archived)
            self.assertNotIn("F-open", archived)

    def test_compact_findings_requires_closure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-findings")
            findings_path = directory / "findings.md"
            findings_path.write_text(findings(closure="none"), encoding="utf-8")
            before = findings_path.read_bytes()

            result = run_plan(root, "compact", "demo")

            self.assertEqual(result.returncode, 2)
            self.assertIn("resolved finding lacks closure evidence", result.stderr)
            self.assertEqual(findings_path.read_bytes(), before)
            self.assertFalse((directory / "history").exists())

    def test_compact_findings_never_moves_open_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-findings")
            findings_path = directory / "findings.md"
            open_only = findings().replace(
                "| F-resolved | resolved |", "| F-resolved | open |"
            )
            findings_path.write_text(open_only, encoding="utf-8")
            before = findings_path.read_bytes()

            result = run_plan(root, "compact", "demo")

            self.assertEqual(result.returncode, 2)
            self.assertIn("every safely resolved row is removed", result.stderr)
            self.assertEqual(findings_path.read_bytes(), before)
            self.assertFalse((directory / "history").exists())

    def test_status_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root, "--with-findings", "--with-progress")
            before = {
                path.relative_to(directory): (
                    path.read_bytes(),
                    path.stat().st_mtime_ns,
                )
                for path in directory.rglob("*")
                if path.is_file()
            }

            result = run_plan(root, "status", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            after = {
                path.relative_to(directory): (
                    path.read_bytes(),
                    path.stat().st_mtime_ns,
                )
                for path in directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_status_reports_zombie_audit_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root)
            path = directory / "task_plan.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "| Phase 1 | pending |",
                    "| Phase 1 | pending |\n| Phase 1 | pending |",
                ),
                encoding="utf-8",
            )
            before = path.read_bytes()

            result = run_plan(root, "status", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["zombie_count"], 1)
            self.assertEqual(
                payload["audit"]["issues"][0]["code"], "duplicate-phase-row"
            )
            self.assertEqual(path.read_bytes(), before)

    def test_zombie_audit_blocks_writers_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root)
            path = directory / "task_plan.md"
            path.write_text(phase_plan().replace("Commit 1", "pending"), encoding="utf-8")
            before = path.read_bytes()

            checkpoint = run_plan(root, "checkpoint", "demo")
            self.assertEqual(checkpoint.returncode, 2)
            self.assertIn("completed-phase-placeholder-conclusion", checkpoint.stderr)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((directory / "history").exists())

            check = run_plan(root, "check", "demo")
            self.assertEqual(check.returncode, 2)
            self.assertIn("completed-phase-placeholder-conclusion", check.stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_next_gate_guard_distinguishes_reference_from_direct_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root)
            path = directory / "task_plan.md"
            text = path.read_text(encoding="utf-8").replace(
                "| Phase 1 | pending |", "| Phase 1 | completed |"
            ).replace(
                "- Conclusion / Commit: <完成時填入結論與 exact commit；未完成時寫 pending>",
                "- Conclusion / Commit: completed",
            ).replace(
                "- Next acceptance gate: <下一個可機械驗收的 gate>",
                "- Next acceptance gate: Verify the artifact produced by Phase 1 before release",
            )
            path.write_text(text, encoding="utf-8")

            reference = run_plan(root, "status", "demo")
            self.assertEqual(reference.returncode, 0, reference.stderr)
            self.assertEqual(json.loads(reference.stdout)["zombie_count"], 0)

            prefix_reference = text.replace(
                "Verify the artifact produced by Phase 1 before release",
                "Phase 1 artifact checksum matches the release manifest",
            )
            path.write_text(prefix_reference, encoding="utf-8")
            prefix = run_plan(root, "status", "demo")
            self.assertEqual(json.loads(prefix.stdout)["zombie_count"], 0)

            path.write_text(
                text.replace(
                    "Verify the artifact produced by Phase 1 before release",
                    "Phase 1 — rerun completed work",
                ),
                encoding="utf-8",
            )
            direct = run_plan(root, "status", "demo")
            codes = {
                issue["code"]
                for issue in json.loads(direct.stdout)["audit"]["issues"]
            }
            self.assertIn("next-gate-completed-phase", codes)

    def test_zombie_audit_expands_double_dot_decision_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.init(root)
            path = directory / "task_plan.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "| D-001 | active | <決策與理由。> | <被取代decision或ADR；沒有則寫none> |",
                "\n".join(
                    (
                        "| D-001 | active | First. | none |",
                        "| D-002 | superseded | Second. | D-003 |",
                        "| D-003 | active | Replacement. | none |",
                    )
                ),
            ).replace(
                "- Frozen decisions: <目前生效的決策>",
                "- Frozen decisions: D-001..D-002",
            )
            path.write_text(text, encoding="utf-8")

            result = run_plan(root, "status", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            codes = {issue["code"] for issue in payload["audit"]["issues"]}
            self.assertIn("packet-decision-status-mismatch", codes)


if __name__ == "__main__":
    unittest.main()
