from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "planning-with-files"
SCRIPT = SKILL / "scripts" / "plan.py"
PI_SCRIPT = ROOT / "home" / ".pi" / "agent" / "skills" / "planning-with-files" / "scripts" / "plan.py"


def run_plan(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def plan_dir(root: Path, task_id: str = "demo") -> Path:
    return root / ".agent_state" / "plans" / task_id


class LifecycleTests(unittest.TestCase):
    def test_init_creates_entry_and_phases_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_plan(root, "init", "demo", "--goal", "重構記憶系統", "--with-findings")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(set(payload(result)["created"]), {"INDEX.md", "phases/", "findings.md"})
            index = (plan_dir(root) / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn("**Goal:** 重構記憶系統", index)
            self.assertTrue((plan_dir(root) / "phases").is_dir())

    def test_skill_describes_mutable_phase_records_and_append_only_progress(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("phase records 在完成前可變", text)
        self.assertIn("completed 後 sealed and immutable", text)
        self.assertIn("progress append-only", text)
        self.assertNotIn("stores(phase 檔、progress)只增不改", text)
        self.assertEqual(SCRIPT.read_bytes(), PI_SCRIPT.read_bytes())

    def test_init_refuses_second_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            again = run_plan(root, "init", "demo", "--goal", "g")
            self.assertEqual(again.returncode, 1)
            self.assertIn("already exists", again.stdout)

    def test_phase_start_creates_record_and_board_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            first = run_plan(root, "phase-start", "demo", "--topic", "schema and templates")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(payload(first)["phase"], "01")
            self.assertEqual(payload(first)["record"], "phases/01-schema-and-templates.md")
            second = run_plan(root, "phase-start", "demo", "--topic", "重寫", "--slug", "rewrite")
            self.assertEqual(payload(second)["phase"], "02")
            index = (plan_dir(root) / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn("| 01 | in_progress | phases/01-schema-and-templates.md |", index)
            self.assertIn("| 02 | in_progress | phases/02-rewrite.md |", index)

    def test_non_ascii_topic_needs_explicit_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            result = run_plan(root, "phase-start", "demo", "--topic", "重寫核心")
            self.assertEqual(result.returncode, 1)
            self.assertIn("--slug", result.stdout)

    def test_seal_requires_commit_and_conclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            bare = run_plan(root, "phase-set", "demo", "--phase", "1", "--status", "completed")
            self.assertEqual(bare.returncode, 1)
            self.assertIn("Commit SHA and a Conclusion", bare.stdout)
            ok = run_plan(
                root, "phase-set", "demo", "--phase", "1", "--status", "completed",
                "--commit", "abc1234", "--conclusion", "done",
            )
            self.assertEqual(ok.returncode, 0, ok.stderr)
            record = (plan_dir(root) / "phases" / "01-x.md").read_text(encoding="utf-8")
            self.assertIn("- **Status:** completed", record)
            self.assertIn("- **Commit:** abc1234", record)
            index = (plan_dir(root) / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn("| 01 | completed | phases/01-x.md |", index)

    def test_completed_phase_is_sealed_against_every_phase_set_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            complete = run_plan(
                root,
                "phase-set",
                "demo",
                "--phase",
                "1",
                "--status",
                "completed",
                "--commit",
                "abc1234",
                "--conclusion",
                "done",
            )
            self.assertEqual(complete.returncode, 0, complete.stdout)
            phase = plan_dir(root) / "phases" / "01-x.md"
            index = plan_dir(root) / "INDEX.md"
            phase_bytes = phase.read_bytes()
            index_bytes = index.read_bytes()
            mutations = (
                ("--note", "late note"),
                ("--status", "pending"),
                ("--status", "in_progress"),
                ("--status", "blocked"),
                ("--status", "completed"),
                ("--commit", "late-sha"),
                ("--conclusion", "late conclusion"),
            )
            for mutation in mutations:
                with self.subTest(mutation=mutation):
                    result = run_plan(root, "phase-set", "demo", "--phase", "1", *mutation)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("sealed after completion", result.stdout)
                    self.assertEqual(phase.read_bytes(), phase_bytes)
                    self.assertEqual(index.read_bytes(), index_bytes)

    def test_log_appends_events_and_verifications(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "log", "demo", "--actor", "root", "--action", "wrote", "--result", "ok")
            run_plan(root, "log", "demo", "--verify", "--command", "pytest", "--result", "94 pass", "--sha", "deadbeef")
            rows = [
                json.loads(line)
                for line in (plan_dir(root) / "progress.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(rows[0]["kind"], "event")
            self.assertEqual(rows[0]["action"], "wrote")
            self.assertEqual(rows[1]["kind"], "verify")
            self.assertEqual(rows[1]["sha"], "deadbeef")

    def test_check_blocks_open_phases_then_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            index_path = plan_dir(root) / "INDEX.md"
            index_path.write_text(
                re.sub(r"<[^<>\n]+>", "filled", index_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            phase_path = plan_dir(root) / "phases" / "01-x.md"
            phase_path.write_text(
                re.sub(r"<[^<>\n]+>", "filled", phase_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            blocked = run_plan(root, "check", "demo")
            self.assertEqual(blocked.returncode, 1)
            self.assertIn("open phases", blocked.stdout)
            run_plan(root, "phase-set", "demo", "--phase", "1", "--status", "completed", "--commit", "a", "--conclusion", "c")
            self.assertEqual(run_plan(root, "check", "demo").returncode, 0)

    def test_archive_moves_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            first = run_plan(root, "archive", "demo")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue((root / ".agent_state" / "archives" / "demo" / "plan" / "INDEX.md").is_file())
            run_plan(root, "init", "demo", "--goal", "g")
            second = run_plan(root, "archive", "demo")
            self.assertEqual(second.returncode, 1)
            self.assertIn("already exists", second.stdout)


class CheckpointTests(unittest.TestCase):
    def test_init_checkpoint_permits_template_slots_and_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            self.assertEqual(run_plan(root, "checkpoint", "demo").returncode, 0)
            # Corrupt the INDEX: drop a required section.
            index_path = plan_dir(root) / "INDEX.md"
            text = index_path.read_text(encoding="utf-8").replace("## Decisions", "## Choices")
            index_path.write_text(text, encoding="utf-8")
            broken = run_plan(root, "checkpoint", "demo")
            self.assertEqual(broken.returncode, 1)
            self.assertIn("Decisions", broken.stdout)

    def test_started_phase_rejects_untouched_template_slots_at_checkpoint_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            checkpoint = run_plan(root, "checkpoint", "demo")
            self.assertEqual(checkpoint.returncode, 1)
            self.assertIn("unresolved", checkpoint.stdout)
            complete = run_plan(root, "check", "demo")
            self.assertEqual(complete.returncode, 1)
            self.assertIn("unresolved", complete.stdout)

    def test_fully_populated_started_plan_passes_checkpoint_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            run_plan(
                root, "phase-set", "demo", "--phase", "1", "--status", "completed",
                "--commit", "abc1234", "--conclusion", "done",
            )
            index_path = plan_dir(root) / "INDEX.md"
            index_path.write_text(
                re.sub(r"<[^<>\n]+>", "filled", index_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            phase_path = plan_dir(root) / "phases" / "01-x.md"
            phase_path.write_text(
                re.sub(r"<[^<>\n]+>", "filled", phase_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            self.assertEqual(run_plan(root, "checkpoint", "demo").returncode, 0)
            self.assertEqual(run_plan(root, "check", "demo").returncode, 0)

    def test_rejects_board_record_disagreement_and_invalid_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            index_path = plan_dir(root) / "INDEX.md"
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace(
                    "| 01 | in_progress |", "| 01 | pending |"
                ),
                encoding="utf-8",
            )
            disagreement = run_plan(root, "checkpoint", "demo")
            self.assertEqual(disagreement.returncode, 1)
            self.assertIn("disagrees", disagreement.stdout)

            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace(
                    "| 01 | pending |", "| 01 | <choose status> |"
                ),
                encoding="utf-8",
            )
            invalid = run_plan(root, "checkpoint", "demo")
            self.assertEqual(invalid.returncode, 1)
            self.assertIn("invalid status", invalid.stdout)

            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace(
                    "| 01 | <choose status> |", "| 01 | in_progress |"
                ),
                encoding="utf-8",
            )
            phase_path = plan_dir(root) / "phases" / "01-x.md"
            phase_path.write_text(
                phase_path.read_text(encoding="utf-8").replace(
                    "- **Status:** in_progress", "- **Status:** <choose status>"
                ),
                encoding="utf-8",
            )
            record_invalid = run_plan(root, "checkpoint", "demo")
            self.assertEqual(record_invalid.returncode, 1)
            self.assertIn("invalid Status", record_invalid.stdout)

    def test_rejects_empty_active_and_completed_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            for path in (plan_dir(root) / "INDEX.md", plan_dir(root) / "phases" / "01-x.md"):
                path.write_text(re.sub(r"<[^<>\n]+>", "filled", path.read_text(encoding="utf-8")), encoding="utf-8")
            phase_path = plan_dir(root) / "phases" / "01-x.md"
            phase_path.write_text(
                phase_path.read_text(encoding="utf-8").replace("- **Scope:** filled", "- **Scope:**"),
                encoding="utf-8",
            )
            result = run_plan(root, "checkpoint", "demo")
            self.assertEqual(result.returncode, 1)
            self.assertIn("empty required field 'Scope'", result.stdout)
            phase_path.write_text(
                phase_path.read_text(encoding="utf-8").replace("- **Scope:**", "- **Scope:** filled"),
                encoding="utf-8",
            )
            run_plan(
                root, "phase-set", "demo", "--phase", "1", "--status", "completed",
                "--commit", "abc1234", "--conclusion", "done",
            )
            phase_path.write_text(
                phase_path.read_text(encoding="utf-8").replace("- **Evidence:** filled", "- **Evidence:**"),
                encoding="utf-8",
            )
            completed = run_plan(root, "check", "demo")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("empty required field 'Evidence'", completed.stdout)

    def test_shipped_angle_bracket_content_is_not_a_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            index_path = plan_dir(root) / "INDEX.md"
            phase_path = plan_dir(root) / "phases" / "01-x.md"
            for path in (index_path, phase_path):
                path.write_text(re.sub(r"<[^<>\n]+>", "filled", path.read_text(encoding="utf-8")), encoding="utf-8")
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace(
                    "- filled\n- **Next gate:** filled",
                    "- <https://example.com/spec>\n- <span>shipped</span>\n- Result<T>\n- **Next gate:** proceed",
                ),
                encoding="utf-8",
            )
            self.assertEqual(run_plan(root, "checkpoint", "demo").returncode, 0)

    def test_only_index_is_budgeted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            # A huge phase record (a store) never trips the budget: it is never loaded whole.
            index_path = plan_dir(root) / "INDEX.md"
            index_path.write_text(
                re.sub(r"<[^<>\n]+>", "filled", index_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            (plan_dir(root) / "phases" / "01-x.md").write_text(
                "# Phase 01 — x\n\n- **Status:** in_progress\n- **Scope:** s\n"
                "- **Decisions made:** none\n- **Conclusion:** pending\n- **Commit:** none\n"
                "- **Evidence:** none\n\n## Notes\n\n" + "x" * 40_000 + "\n",
                encoding="utf-8",
            )
            self.assertEqual(run_plan(root, "checkpoint", "demo").returncode, 0)
            # An oversized INDEX does trip it.
            index_path = plan_dir(root) / "INDEX.md"
            index_path.write_text(index_path.read_text(encoding="utf-8") + "\n<!-- " + "z" * 20_000 + " -->\n", encoding="utf-8")
            over = run_plan(root, "checkpoint", "demo")
            self.assertEqual(over.returncode, 1)
            self.assertIn("budget", over.stdout)
            actual_size = len(index_path.read_bytes())
            self.assertIn(f"{actual_size - 16_384} bytes over", over.stdout)


class MigrationTests(unittest.TestCase):
    OLD_PLAN = "\n".join([
        "# legacy 任務計劃", "", "**Last updated:** 2026-07-01", "",
        "## Goal", "", "遷移到新格式。", "",
        "## Current State", "", "- 在 dev 分支", "",
        "## Architecture Baseline", "", "- ADR-003", "",
        "## Active Domain Packets", "", "### auth", "", "- Domain: auth", "",
        "## Phase Status", "",
        "| Phase | Status | Scope | Acceptance |", "|---|---|---|---|",
        "| Phase 1 | completed | schema | tests |",
        "| Phase 2 | in_progress | rewrite | pytest |", "",
        "## Decisions", "",
        "| ID | Status | Decision | Supersedes / Authority |", "|---|---|---|---|",
        "| D-001 | active | 用 jsonl | none |", "",
        "## Historical Phase Summary", "",
        "| Phase | Topic | Conclusion / Commit |", "|---|---|---|",
        "| Phase 1 | schema | done at abc1234def |", "",
        "## Active Notes", "", "### Phase 2 — rewrite plan.py", "",
        "- Conclusion / Commit: pending", "- Detail: 正在重寫。", "",
    ])
    OLD_PROGRESS = "\n".join([
        "# legacy progress", "", "## Timeline", "",
        "| Time | Actor | Action | Result | Next |", "|---|---|---|---|---|",
        "| 2026-07-01 | root | 開工 | ok | schema |", "",
        "## Verification Log", "",
        "| Date | Command | Result |", "|---|---|---|",
        "| 2026-07-01 | pytest | 10 pass |", "",
    ])

    def _seed(self, root: Path) -> Path:
        plan = plan_dir(root, "legacy")
        plan.mkdir(parents=True)
        (plan / "task_plan.md").write_text(self.OLD_PLAN, encoding="utf-8")
        (plan / "progress.md").write_text(self.OLD_PROGRESS, encoding="utf-8")
        (plan / "domains").mkdir()
        (plan / "domains" / "auth.md").write_text("packet", encoding="utf-8")
        return plan

    def test_migrate_scaffolds_new_format_and_preserves_originals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = self._seed(root)
            result = run_plan(root, "migrate", "legacy")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = payload(result)
            self.assertEqual(len(data["phases"]), 2)
            self.assertEqual(data["progress_rows"], 2)
            self.assertTrue(data["punch_list"])
            index = (plan / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn("**Goal:** 遷移到新格式。", index)
            self.assertIn("| 01 | completed | phases/01-schema.md |", index)
            self.assertIn("| 02 | in_progress | phases/02-rewrite-plan-py.md |", index)
            self.assertIn("| D-001 | active | 用 jsonl | none |", index)
            # Commit SHA lifted out of the historical conclusion.
            phase1 = (plan / "phases" / "01-schema.md").read_text(encoding="utf-8")
            self.assertIn("- **Commit:** abc1234def", phase1)
            # progress converted to jsonl.
            rows = [json.loads(line) for line in (plan / "progress.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual({r["kind"] for r in rows}, {"event", "verify"})
            # Nothing deleted: originals live under pre-migration.
            preserved = plan / "history" / "pre-migration"
            self.assertTrue((preserved / "task_plan.md").is_file())
            self.assertTrue((preserved / "progress.md").is_file())
            self.assertTrue((preserved / "domains").is_dir())
            self.assertFalse((plan / "task_plan.md").exists())

    def test_migration_recovery_is_one_checkpoint_and_check_never_exempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = self._seed(root)
            run_plan(root, "migrate", "legacy")
            # A completed migrated plan must never pass the completion gate on its marker.
            complete = run_plan(root, "check", "legacy")
            self.assertEqual(complete.returncode, 1)
            self.assertIn("unresolved", complete.stdout)
            # One successful checkpoint is the explicit recovery window and consumes it.
            self.assertEqual(run_plan(root, "checkpoint", "legacy").returncode, 0)
            self.assertNotIn("migration-punch-list", (plan / "INDEX.md").read_text(encoding="utf-8"))
            repeated = run_plan(root, "checkpoint", "legacy")
            self.assertEqual(repeated.returncode, 1)
            self.assertIn("unresolved", repeated.stdout)

    def test_migrate_refuses_when_index_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = self._seed(root)
            (plan / "INDEX.md").write_text("# legacy\n", encoding="utf-8")
            result = run_plan(root, "migrate", "legacy")
            self.assertEqual(result.returncode, 1)
            self.assertIn("already exists", result.stdout)

    def test_migrate_fast_fails_without_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = plan_dir(root, "legacy")
            plan.mkdir(parents=True)
            (plan / "task_plan.md").write_text("# legacy\n\n## Current State\n\n- x\n", encoding="utf-8")
            result = run_plan(root, "migrate", "legacy")
            self.assertEqual(result.returncode, 1)
            self.assertIn("Goal", result.stdout)


class StatusGitTests(unittest.TestCase):
    def test_status_derives_git_snapshot_inside_a_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
            (root / "seed").write_text("x", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
            run_plan(root, "init", "demo", "--goal", "g")
            snap = payload(run_plan(root, "status", "demo"))["git"]
            self.assertRegex(snap["head"], r"^[0-9a-f]{7,64}$")
            self.assertRegex(snap["tree"], r"^[0-9a-f]{7,64}$")
            self.assertFalse(snap["clean"])  # the plan dir is untracked
            self.assertIsInstance(snap["branch"], str)

    def test_status_git_is_none_outside_a_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            self.assertIsNone(payload(run_plan(root, "status", "demo"))["git"])


class SkillContractTests(unittest.TestCase):
    def test_skill_declares_version_and_mental_model(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("skill_version: 11", text)
        for phrase in ("refs vs object log", "只讀 `INDEX.md`", "指標不抄本", "migrate"):
            self.assertIn(phrase, text)

    def test_templates_are_the_new_set(self) -> None:
        names = {p.name for p in (SKILL / "templates").glob("*.md")}
        self.assertEqual(names, {"INDEX.md", "phase.md", "findings.md"})

    def test_runtime_script_mirrors_are_identical(self) -> None:
        pi_script = ROOT / "home" / ".pi" / "agent" / "skills" / "planning-with-files" / "scripts" / "plan.py"
        self.assertEqual(SCRIPT.read_bytes(), pi_script.read_bytes())


if __name__ == "__main__":
    unittest.main()
