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
    def test_checkpoint_validates_schema(self) -> None:
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

    def test_only_index_is_budgeted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "init", "demo", "--goal", "g")
            run_plan(root, "phase-start", "demo", "--topic", "x")
            # A huge phase record (a store) never trips the budget: it is never loaded whole.
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
            rows = [json.loads(l) for l in (plan / "progress.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual({r["kind"] for r in rows}, {"event", "verify"})
            # Nothing deleted: originals live under pre-migration.
            preserved = plan / "history" / "pre-migration"
            self.assertTrue((preserved / "task_plan.md").is_file())
            self.assertTrue((preserved / "progress.md").is_file())
            self.assertTrue((preserved / "domains").is_dir())
            self.assertFalse((plan / "task_plan.md").exists())

    def test_migrated_plan_is_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            run_plan(root, "migrate", "legacy")
            self.assertEqual(run_plan(root, "checkpoint", "legacy").returncode, 0)

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
        self.assertIn("skill_version: 10", text)
        for phrase in ("refs vs object log", "只讀 `INDEX.md`", "指標不抄本", "migrate"):
            self.assertIn(phrase, text)

    def test_templates_are_the_new_set(self) -> None:
        names = {p.name for p in (SKILL / "templates").glob("*.md")}
        self.assertEqual(names, {"INDEX.md", "phase.md", "findings.md"})


if __name__ == "__main__":
    unittest.main()
