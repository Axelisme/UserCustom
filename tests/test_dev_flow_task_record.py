from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "dev-flow" / "scripts" / "plan.py"
PI_SCRIPT = ROOT / "home" / ".pi" / "agent" / "skills" / "dev-flow" / "scripts" / "plan.py"


def run_plan(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def payload(done: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(done.stdout)


def record(root: Path, task_id: str = "demo") -> Path:
    return root / ".agent_state" / "plans" / task_id


def snapshot(directory: Path) -> dict[str, tuple[str, bytes | str | None]]:
    result: dict[str, tuple[str, bytes | str | None]] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            result[relative] = ("link", os.readlink(path))
        elif path.is_dir():
            result[relative] = ("dir", None)
        else:
            result[relative] = ("file", path.read_bytes())
    return result


class TaskRecordV2Tests(unittest.TestCase):
    def assert_ok(
        self,
        done: subprocess.CompletedProcess[str],
        operation: str,
        *,
        version: int | None = 2,
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
        body = payload(done)
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["operation"], operation)
        self.assertEqual(body["record_version"], version)
        self.assertNotIn("error", body)
        return body

    def assert_refusal(
        self,
        done: subprocess.CompletedProcess[str],
        operation: str,
        code: str,
        *,
        version: int | None = None,
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 1, done.stderr or done.stdout)
        self.assertEqual(done.stderr, "")
        body = payload(done)
        self.assertEqual(set(body), {"ok", "operation", "record_version", "error"})
        self.assertEqual(body["ok"], False)
        self.assertEqual(body["operation"], operation)
        self.assertEqual(body["record_version"], version)
        error = body["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(set(error), {"code", "message", "paths"})
        self.assertEqual(error["code"], code)
        self.assertEqual(error["paths"], sorted(error["paths"]))
        return body

    def test_interface_has_exactly_four_commands_and_pi_links_to_owner(self) -> None:
        done = run_plan(Path(tempfile.gettempdir()), "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        command_line = next(line for line in done.stdout.splitlines() if "{create," in line)
        for command in ("create", "refresh", "archive", "resume"):
            self.assertIn(command, command_line)
        for retired in ("ticket-create", "check", "init", "status", "show", "set", "phase", "log", "checkpoint", "migrate"):
            self.assertNotIn(retired, command_line)
        self.assertTrue(PI_SCRIPT.is_symlink() or PI_SCRIPT.resolve() == SCRIPT.resolve())
        self.assertEqual(PI_SCRIPT.resolve(), SCRIPT.resolve())

    def test_create_and_refresh_project_the_complete_file_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            created = self.assert_ok(run_plan(root, "create", "demo", "--goal", "Ship one durable record."), "create")
            self.assertEqual(
                created["paths"],
                [".agent_state/plans/demo/INDEX.md", ".agent_state/plans/demo/tickets"],
            )
            task = record(root)
            index = task / "INDEX.md"
            self.assertIn("| record_version | 2 |", index.read_text(encoding="utf-8"))
            self.assertIn("<!-- task-record:files:start -->\nINDEX.md\ntickets/\n<!-- task-record:files:end -->", index.read_text(encoding="utf-8"))
            (task / "decisions.md").write_text("arbitrary decision content\n", encoding="utf-8")
            (task / "tickets" / "T001-any-name.md").write_text("unparsed ticket content\n", encoding="utf-8")
            (task / "evidence").mkdir()
            (task / "evidence" / "raw.bin").write_bytes(b"\x00\xff")
            before = index.read_text(encoding="utf-8")
            refreshed = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertEqual(refreshed["paths"], [".agent_state/plans/demo/INDEX.md"])
            after = index.read_text(encoding="utf-8")
            start = "<!-- task-record:files:start -->\n"
            end = "<!-- task-record:files:end -->"
            self.assertEqual(before.split(start)[0], after.split(start)[0])
            self.assertEqual(before.split(end)[1], after.split(end)[1])
            self.assertIn(
                "INDEX.md\ndecisions.md\nevidence/\n  raw.bin\ntickets/\n  T001-any-name.md",
                after,
            )
            self.assertEqual(run_plan(root, "refresh", "demo").returncode, 0)
            self.assertEqual(after, index.read_text(encoding="utf-8"))

    def test_refresh_is_content_blind_except_version_and_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            index.write_text(
                "arbitrary prose\n| record_version | 2 |\nnot a record schema\n"
                "<!-- task-record:files:start -->\nstale\n<!-- task-record:files:end -->\n",
                encoding="utf-8",
            )
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertIn("INDEX.md\ntickets/", index.read_text(encoding="utf-8"))

    def test_refresh_preserves_crlf_outside_its_generated_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            original = (
                b"outside before\r\n| record_version | 2 |\r\n"
                b"<!-- task-record:files:start -->\r\nstale\r\n"
                b"<!-- task-record:files:end -->\r\noutside after\r\n"
            )
            index.write_bytes(original)
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            updated = index.read_bytes()
            start = b"<!-- task-record:files:start -->"
            end = b"<!-- task-record:files:end -->"
            self.assertEqual(original.split(start)[0], updated.split(start)[0])
            self.assertEqual(original.split(end)[1], updated.split(end)[1])
            self.assertIn(b"INDEX.md\r\ntickets/", updated)

    def test_refresh_checks_version_before_markers_and_never_migrates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = record(root)
            (task / "tickets").mkdir(parents=True)
            index = task / "INDEX.md"
            index.write_text("| record_version | 1 |\n", encoding="utf-8")
            before = index.read_bytes()
            refused = self.assert_refusal(
                run_plan(root, "refresh", "demo"),
                "refresh",
                "unsupported_record_version",
                version=1,
            )
            self.assertEqual(refused["error"].get("paths"), [".agent_state/plans/demo/INDEX.md"])
            self.assertEqual(index.read_bytes(), before)
            index.write_text("| record_version | future |\n", encoding="utf-8")
            self.assert_refusal(run_plan(root, "refresh", "demo"), "refresh", "unsupported_record_version")
            index.write_text("no version\n<!-- task-record:files:start --><!-- task-record:files:end -->", encoding="utf-8")
            self.assert_refusal(run_plan(root, "refresh", "demo"), "refresh", "unsupported_record_version")

    def test_refresh_refuses_only_malformed_index_for_index_access_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            for text in (
                "| record_version | 2 |\n",
                "| record_version | 2 |\n<!-- task-record:files:end --><!-- task-record:files:start -->",
                "| record_version | 2 |\n<!-- task-record:files:start --><!-- task-record:files:start --><!-- task-record:files:end -->",
            ):
                with self.subTest(text=text):
                    index.write_text(text, encoding="utf-8")
                    self.assert_refusal(run_plan(root, "refresh", "demo"), "refresh", "malformed_index", version=2)

    def test_invalid_arguments_and_collisions_have_stable_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for task_id in ("", "../escape", "a/b", "a" * 65, "é"):
                with self.subTest(task_id=task_id):
                    self.assert_refusal(run_plan(root, "create", task_id, "--goal", "g"), "create", "invalid_argument")
            self.assert_refusal(run_plan(root, "create", "demo", "--goal", "  "), "create", "invalid_argument")
            self.assert_ok(run_plan(root, "create", "Demo", "--goal", "g"), "create")
            collision = self.assert_refusal(run_plan(root, "create", "demo", "--goal", "g"), "create", "record_exists")
            self.assertEqual(collision["error"].get("paths"), [".agent_state/plans/Demo"])
            self.assert_ok(run_plan(root, "archive", "Demo"), "archive", version=None)
            collision = self.assert_refusal(run_plan(root, "create", "Demo", "--goal", "g"), "create", "record_exists")
            self.assertEqual(collision["error"].get("paths"), [".agent_state/archives/Demo"])
            self.assert_refusal(run_plan(root, "resume", "missing"), "resume", "record_missing")
            self.assert_ok(run_plan(root, "create", "carriage", "--goal", "first\rsecond"), "create")
            self.assertIn(b"first\rsecond", (record(root, "carriage") / "INDEX.md").read_bytes())

    def test_archive_and_resume_preserve_legacy_and_v1_records_without_version_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for task_id, index_text, expected_version in (
                ("legacy", "legacy bytes\n", None),
                ("v1", "| record_version | 1 |\nold ticket table\n", None),
            ):
                with self.subTest(task_id=task_id):
                    task = record(root, task_id)
                    (task / "tickets").mkdir(parents=True)
                    (task / "INDEX.md").write_text(index_text, encoding="utf-8")
                    before = snapshot(task)
                    self.assert_ok(run_plan(root, "archive", task_id), "archive", version=expected_version)
                    archived = root / ".agent_state" / "archives" / task_id
                    self.assertEqual(snapshot(archived), before)
                    self.assert_ok(run_plan(root, "resume", task_id), "resume", version=expected_version)
                    self.assertEqual(snapshot(task), before)

    def test_move_collisions_report_the_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "archive-source", "--goal", "g"), "create")
            destination = root / ".agent_state" / "archives" / "ARCHIVE-source"
            destination.mkdir(parents=True)
            refused = self.assert_refusal(run_plan(root, "archive", "archive-source"), "archive", "record_exists")
            self.assertEqual(refused["error"].get("paths"), [".agent_state/archives/ARCHIVE-source"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "resume-source", "--goal", "g"), "create")
            self.assert_ok(run_plan(root, "archive", "resume-source"), "archive", version=None)
            destination = root / ".agent_state" / "plans" / "RESUME-source"
            destination.mkdir(parents=True)
            refused = self.assert_refusal(run_plan(root, "resume", "resume-source"), "resume", "record_exists")
            self.assertEqual(refused["error"].get("paths"), [".agent_state/plans/RESUME-source"])

    def test_unsafe_record_trees_fail_closed_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            (task / "unsafe").symlink_to(root / "missing")
            before = snapshot(task)
            refusal = self.assert_refusal(run_plan(root, "archive", "demo"), "archive", "unsafe_path", version=None)
            self.assertTrue(refusal["error"].get("paths"))
            self.assertEqual(snapshot(task), before)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plans = root / ".agent_state" / "plans"
            plans.parent.mkdir(parents=True)
            plans.write_text("not a directory", encoding="utf-8")
            self.assert_refusal(run_plan(root, "create", "demo", "--goal", "g"), "create", "unsafe_path")

    def test_templates_are_v2_containers_without_retired_schema(self) -> None:
        index = (ROOT / "home/.codex/skills/dev-flow/templates/INDEX.md").read_text(encoding="utf-8")
        ticket = (ROOT / "home/.codex/skills/dev-flow/templates/ticket.md").read_text(encoding="utf-8")
        self.assertIn("| record_version | 2 |", index)
        self.assertIn("task-record:files", index)
        for retired in ("Active decisions", "## Tickets", "## Artifacts", "task-record:tickets"):
            self.assertNotIn(retired, index)
        self.assertIn("**Resolve by:**", ticket)
        self.assertIn("## Outcome", ticket)
        self.assertIn("## Current", ticket)
        self.assertIn("| status | open |", ticket)
        self.assertIn("| depends_on |", ticket)
        for retired in ("## Decisions", "## Evidence", "## Result"):
            self.assertNotIn(retired, ticket)


class DocumentationContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_s0_remains_the_single_normative_copy(self) -> None:
        standard = self.read("home/.codex/skills/dev-flow/references/admission-standard.md")
        dev_flow = self.read("home/.codex/skills/dev-flow/SKILL.md")
        orchestrate = self.read("home/.codex/skills/orchestrate/SKILL.md")
        self.assertEqual(standard.count("## S0 — Minimum-complete design admission"), 1)
        for label in (
            "Minimum need first",
            "Start from zero",
            "Breadth before depth",
            "Edge triage",
            "Backlog, not scope expansion",
            "Promotion requires evidence",
        ):
            self.assertIn(label, standard)
            self.assertNotIn(label, dev_flow)
            self.assertNotIn(label, orchestrate)
        for owner in (dev_flow, orchestrate):
            self.assertIn("S0–S5", owner)
            self.assertIn("read", owner.casefold())
            self.assertIn("admission standard", owner.casefold())

    def test_existing_lifecycle_and_review_authority_remain_intact(self) -> None:
        dev_flow = self.read("home/.codex/skills/dev-flow/SKILL.md")
        standard = self.read("home/.codex/skills/dev-flow/references/admission-standard.md")
        self.assertIn("ordinary generic ticket", dev_flow)
        self.assertIn("Machine rework: N/2", standard)
        self.assertIn("candidate Git ref", standard)
        for retired in ("machine_rework_cycles", "deferred row", "accepted SHA", "pre and post review bracket", "acceptance queue"):
            self.assertNotIn(retired, standard)
        for relative in (
            "home/.codex/agents/acceptance-reviewer.toml",
            "home/.pi/agent/agents/acceptance-reviewer.md",
            "home/.claude/agents/acceptance-reviewer.md",
        ):
            text = self.read(relative)
            for phrase in ("exact SHA", "same path", "same branch", "clean", "No collect or mutation"):
                self.assertIn(phrase, text, relative)

    def test_dev_flow_documents_the_v2_route_and_interface(self) -> None:
        dev_flow = self.read("home/.codex/skills/dev-flow/SKILL.md")
        standard = self.read("home/.codex/skills/dev-flow/references/admission-standard.md")
        self.assertIn("`create | archive | resume | refresh`", dev_flow)
        self.assertIn("Current stage", dev_flow)
        self.assertIn("conditional route", dev_flow.casefold())
        self.assertIn("handoff is a decision-authority transfer event", dev_flow)
        self.assertIn("only after\nimplementation completes or the task is explicitly abandoned", dev_flow)
        for retired in ("ticket-create", "green task-record checks", "archive may pause open work"):
            self.assertNotIn(retired, dev_flow)
        self.assertNotIn("copy the final line into Result", standard)
        self.assertIn("It remains\nopen until explicit successful exercise", standard)
        self.assertIn("task-record `refresh`", standard)
        self.assertNotIn("non-pending Result", standard)

    def test_plan_directory_producers_and_mirrors_use_direct_containers(self) -> None:
        for skill in ("wayfinder", "to-tickets"):
            codex = self.read(f"home/.codex/skills/{skill}/SKILL.md")
            pi = self.read(f"home/.pi/agent/skills/{skill}/SKILL.md")
            self.assertEqual(codex, pi)
            self.assertIn("Resolve by", codex)
            self.assertNotIn("ticket-create", codex)
        wayfinder = self.read("home/.codex/skills/wayfinder/SKILL.md")
        self.assertIn("producer-owned\n`decisions.md`", wayfinder)
        self.assertIn("route narrative", wayfinder)

    def test_queries_and_setup_smoke_follow_the_non_validating_model(self) -> None:
        queries = self.read("home/.codex/skills/dev-flow/references/record-queries.md")
        setup = self.read("setup_scripts/setup_config.sh")
        self.assertIn("queries, not validators", queries)
        self.assertIn("ticket header", queries)
        self.assertIn("decisions.md", queries)
        self.assertIn('python "$plan" refresh setup-smoke', setup)
        self.assertNotIn('python "$plan" check setup-smoke', setup)


if __name__ == "__main__":
    unittest.main()
