from __future__ import annotations

import hashlib
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
        check=False,
        text=True,
        capture_output=True,
    )


def payload(done: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(done.stdout)


def task(root: Path, task_id: str = "demo") -> Path:
    return root / ".agent_state" / "plans" / task_id


def snapshot(directory: Path) -> dict[str, tuple[str, bytes | None]]:
    result: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            result[relative] = ("link", os.readlink(path).encode())
        elif path.is_dir():
            result[relative] = ("dir", None)
        else:
            result[relative] = ("file", path.read_bytes())
    return result


def digest(directory: Path) -> str:
    encoded = repr(snapshot(directory)).encode()
    return hashlib.sha256(encoded).hexdigest()


class TaskRecordContractTests(unittest.TestCase):
    def assert_ok(
        self,
        done: subprocess.CompletedProcess[str],
        operation: str,
        *,
        version: int | None = 1,
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
        body = payload(done)
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["operation"], operation)
        self.assertEqual(body["record_version"], version)
        return body

    def assert_refusal(
        self,
        done: subprocess.CompletedProcess[str],
        operation: str,
        code: str,
        *,
        version: int | None = 1,
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 1, done.stderr or done.stdout)
        self.assertEqual(done.stderr, "")
        body = payload(done)
        self.assertEqual(
            set(body), {"ok", "operation", "record_version", "error"}
        )
        self.assertEqual(body["ok"], False)
        self.assertEqual(body["operation"], operation)
        self.assertEqual(body["record_version"], version)
        error = body["error"]
        assert isinstance(error, dict)
        self.assertEqual(set(error), {"code", "message", "paths"})
        self.assertEqual(error["code"], code)
        self.assertEqual(error["paths"], sorted(error["paths"]))
        return body

    def test_minimum_complete_task_record_tracer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = self.assert_ok(
                run_plan(root, "create", "demo", "--goal", "Ship one durable record."),
                "create",
            )
            self.assertEqual(
                created,
                {
                    "ok": True,
                    "operation": "create",
                    "record_version": 1,
                    "task_id": "demo",
                    "paths": [".agent_state/plans/demo/INDEX.md", ".agent_state/plans/demo/tickets"],
                },
            )
            record = task(root)
            self.assertEqual(
                sorted(path.name for path in record.iterdir()), ["INDEX.md", "tickets"]
            )
            index = record / "INDEX.md"
            initial = index.read_text(encoding="utf-8")
            self.assertIn("| record_version | 1 |", initial)
            self.assertIn("## Current\nTask created.", initial)
            self.assertIn("## Next\nCreate or select the first ticket.", initial)
            self.assertLessEqual(len(index.read_bytes()), 16_384)

            long_title = "x" * 49
            first = self.assert_ok(
                run_plan(
                    root,
                    "ticket-create",
                    "demo",
                    "--title",
                    f"  {long_title}  ",
                    "--outcome",
                    "Contract is frozen.",
                ),
                "ticket-create",
            )
            first_path = record / "tickets" / f"T001-{'x' * 48}.md"
            self.assertEqual(first["ticket_id"], "T001")
            self.assertTrue(first_path.is_file())
            self.assertTrue(first_path.read_text(encoding="utf-8").startswith(f"# T001 — {long_title}\n"))

            second = self.assert_ok(
                run_plan(
                    root,
                    "ticket-create",
                    "demo",
                    "--id",
                    "spec.2",
                    "--title",
                    "Implement | kernel",
                    "--outcome",
                    "A complete tracer is green.",
                    "--depends",
                    "T001",
                ),
                "ticket-create",
            )
            second_path = record / "tickets" / "spec.2-implement-kernel.md"
            self.assertEqual(second["ticket_id"], "spec.2")
            self.assertTrue(second_path.is_file())
            table = index.read_text(encoding="utf-8")
            self.assertLess(table.index("| spec.2 |"), table.index("| T001 |"))
            self.assertIn(r"Implement \| kernel", table)

            first_text = first_path.read_text(encoding="utf-8")
            first_text = first_text.replace("| status | open |", "| status | active |")
            first_text = first_text.replace(
                "|---|---|---|---|\n\n## Evidence\n",
                "|---|---|---|---|\n| D-001 | active | Keep one record. | none |\n\n## Evidence\n",
            )
            first_text = first_text.replace(
                "## Evidence\n\n## Result", "## Evidence\n- [Index](../INDEX.md)\n\n## Result"
            )
            first_path.write_text(first_text, encoding="utf-8")
            humanized = index.read_text(encoding="utf-8").replace(
                "Task created.", "Two tickets describe the current work."
            )
            index.write_text(humanized, encoding="utf-8")
            before_refresh = index.read_bytes()
            refreshed = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertEqual(refreshed["paths"], [".agent_state/plans/demo/INDEX.md"])
            after_refresh = index.read_bytes()
            start = b"<!-- task-record:tickets:start -->\n"
            end = b"<!-- task-record:tickets:end -->"
            self.assertEqual(before_refresh.split(start)[0], after_refresh.split(start)[0])
            self.assertEqual(before_refresh.split(end)[1], after_refresh.split(end)[1])
            self.assertIn(b"Two tickets describe the current work.", after_refresh)
            self.assertEqual(run_plan(root, "refresh", "demo").returncode, 0)
            self.assertEqual(after_refresh, index.read_bytes())

            before_check = digest(record)
            self.assert_ok(run_plan(root, "check", "demo"), "check")
            self.assertEqual(digest(record), before_check)

            active_bytes = snapshot(record)
            self.assert_ok(run_plan(root, "archive", "demo"), "archive")
            archived = root / ".agent_state" / "archives" / "demo"
            self.assertFalse(record.exists())
            self.assertEqual(snapshot(archived), active_bytes)
            self.assert_ok(run_plan(root, "resume", "demo"), "resume")
            self.assertEqual(snapshot(record), active_bytes)

    def test_interface_has_exactly_six_commands_and_pi_links_to_owner(self) -> None:
        done = run_plan(Path(tempfile.gettempdir()), "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        command_line = next(line for line in done.stdout.splitlines() if "{create," in line)
        for command in ("create", "ticket-create", "refresh", "check", "archive", "resume"):
            self.assertIn(command, command_line)
        for retired in ("init", "status", "show", "set", "phase", "log", "checkpoint", "migrate"):
            self.assertNotIn(retired, command_line)
        self.assertTrue(PI_SCRIPT.is_symlink() or PI_SCRIPT.resolve() == SCRIPT.resolve())
        self.assertEqual(PI_SCRIPT.resolve(), SCRIPT.resolve())

    def test_create_refuses_invalid_ids_and_active_or_archive_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for value in ("", "../escape", "a/b", "a" * 65, "é"):
                with self.subTest(value=value):
                    self.assert_refusal(
                        run_plan(root, "create", value, "--goal", "g"),
                        "create",
                        "invalid_task_id",
                    )
            self.assert_ok(run_plan(root, "create", "Demo", "--goal", "g"), "create")
            self.assert_refusal(
                run_plan(root, "create", "Demo", "--goal", "g"),
                "create",
                "record_exists",
            )
            self.assert_ok(run_plan(root, "archive", "Demo"), "archive")
            self.assert_refusal(
                run_plan(root, "create", "Demo", "--goal", "g"),
                "create",
                "record_exists",
            )

    def test_ticket_ids_allocation_dependencies_and_casefold_uniqueness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            self.assert_ok(
                run_plan(root, "ticket-create", "demo", "--id", "T009", "--title", "a", "--outcome", "o"),
                "ticket-create",
            )
            defaulted = self.assert_ok(
                run_plan(root, "ticket-create", "demo", "--title", "b", "--outcome", "o", "--depends", "T009"),
                "ticket-create",
            )
            self.assertEqual(defaulted["ticket_id"], "T010")
            self.assert_refusal(
                run_plan(root, "ticket-create", "demo", "--id", "t009", "--title", "c", "--outcome", "o"),
                "ticket-create",
                "duplicate_ticket_id",
            )
            self.assert_refusal(
                run_plan(root, "ticket-create", "demo", "--title", "c", "--outcome", "o", "--depends", "missing"),
                "ticket-create",
                "missing_dependency",
            )
            self.assert_refusal(
                run_plan(root, "ticket-create", "demo", "--title", "c", "--outcome", "o", "--depends", "T009", "T009"),
                "ticket-create",
                "duplicate_dependency",
            )

    def test_check_detects_table_mismatch_and_refresh_repairs_only_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            self.assert_ok(run_plan(root, "ticket-create", "demo", "--title", "a", "--outcome", "o"), "ticket-create")
            index = task(root) / "INDEX.md"
            changed = index.read_text(encoding="utf-8").replace("| T001 | open | a | none |\n", "")
            index.write_text(changed, encoding="utf-8")
            before = index.read_bytes()
            self.assert_refusal(run_plan(root, "check", "demo"), "check", "table_mismatch")
            self.assertEqual(index.read_bytes(), before)
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertIn("| T001 | open | a | none |", index.read_text(encoding="utf-8"))

    def test_dependency_cycles_fail_closed_without_refresh_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            self.assert_ok(run_plan(root, "ticket-create", "demo", "--title", "a", "--outcome", "o"), "ticket-create")
            self.assert_ok(run_plan(root, "ticket-create", "demo", "--title", "b", "--outcome", "o", "--depends", "T001"), "ticket-create")
            first = task(root) / "tickets" / "T001-a.md"
            first.write_text(first.read_text(encoding="utf-8").replace("| depends_on | none |", "| depends_on | T002 |"), encoding="utf-8")
            before = snapshot(task(root))
            error = self.assert_refusal(run_plan(root, "check", "demo"), "check", "dependency_cycle")
            error_body = error["error"]
            assert isinstance(error_body, dict)
            self.assertIn("T001", error_body["message"])
            self.assert_refusal(run_plan(root, "refresh", "demo"), "refresh", "dependency_cycle")
            self.assertEqual(snapshot(task(root)), before)

    def test_ticket_schema_filename_result_and_decision_chain_are_strict(self) -> None:
        changes = (
            ("| status | open |", "| status | mystery |", "malformed_ticket"),
            ("## Result\npending", "## Result\ndone", "malformed_ticket"),
            ("|---|---|---|---|\n\n## Evidence", "|---|---|---|---|\n| D-001 | superseded | old | none |\n\n## Evidence", "malformed_decisions"),
        )
        for old, new, code in changes:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
                self.assert_ok(run_plan(root, "ticket-create", "demo", "--title", "a", "--outcome", "o"), "ticket-create")
                ticket = task(root) / "tickets" / "T001-a.md"
                ticket.write_text(ticket.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
                self.assert_refusal(run_plan(root, "check", "demo"), "check", code)

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
                self.assert_ok(run_plan(root, "ticket-create", "demo", "--title", "a", "--outcome", "o"), "ticket-create")
                ticket = task(root) / "tickets" / "T001-a.md"
                ticket.rename(ticket.with_name("T001-wrong.md"))
                self.assert_refusal(run_plan(root, "check", "demo"), "check", "malformed_ticket")

    def test_closed_result_and_valid_decision_supersession_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            self.assert_ok(run_plan(root, "ticket-create", "demo", "--title", "a", "--outcome", "o"), "ticket-create")
            ticket = task(root) / "tickets" / "T001-a.md"
            text = ticket.read_text(encoding="utf-8")
            text = text.replace("| status | open |", "| status | closed |")
            text = text.replace("## Result\npending", "## Result\nDone; evidence is above.")
            text = text.replace(
                "|---|---|---|---|\n\n## Evidence",
                "|---|---|---|---|\n| D-001 | superseded | old | none |\n| D-002 | active | new | D-001 |\n\n## Evidence",
            )
            ticket.write_text(text, encoding="utf-8")
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assert_ok(run_plan(root, "check", "demo"), "check")

    def test_pointer_escape_missing_absolute_and_symlinks_are_refused(self) -> None:
        cases = ("[bad](../../../../outside.md)", "[bad](/etc/passwd)", "[bad](missing.md)")
        for pointer in cases:
            with self.subTest(pointer=pointer), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
                index = task(root) / "INDEX.md"
                index.write_text(index.read_text(encoding="utf-8") + f"- {pointer}\n", encoding="utf-8")
                self.assert_refusal(run_plan(root, "check", "demo"), "check", "invalid_pointer")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            target = root / "target.md"
            target.write_text("safe", encoding="utf-8")
            link = root / "linked.md"
            link.symlink_to(target)
            index = task(root) / "INDEX.md"
            index.write_text(index.read_text(encoding="utf-8") + "- [bad](../../../linked.md)\n", encoding="utf-8")
            self.assert_refusal(run_plan(root, "check", "demo"), "check", "symlink")

    def test_malformed_index_markers_budget_and_duplicate_pointers_refuse(self) -> None:
        changes = (
            ("<!-- task-record:tickets:end -->", "", "malformed_markers"),
            ("## Goal\ng", "## Goal\n", "malformed_index"),
        )
        for old, new, code in changes:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
                index = task(root) / "INDEX.md"
                index.write_text(index.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
                self.assert_refusal(run_plan(root, "check", "demo"), "check", code)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = task(root) / "INDEX.md"
            index.write_text(index.read_text(encoding="utf-8") + ("x" * 17_000), encoding="utf-8")
            self.assert_refusal(run_plan(root, "check", "demo"), "check", "malformed_index")

    def test_archive_resume_refuse_collisions_and_symlink_trees_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            archive = root / ".agent_state" / "archives" / "demo"
            archive.mkdir(parents=True)
            before = snapshot(task(root))
            self.assert_refusal(run_plan(root, "archive", "demo"), "archive", "record_exists")
            self.assertEqual(snapshot(task(root)), before)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            (task(root) / "link").symlink_to(root / "missing")
            before = snapshot(task(root))
            self.assert_refusal(run_plan(root, "archive", "demo"), "archive", "symlink")
            self.assertEqual(snapshot(task(root)), before)

    def test_legacy_check_is_read_only_and_archive_resume_are_byte_preserving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = task(root, "legacy")
            (legacy / "phases").mkdir(parents=True)
            (legacy / "INDEX.md").write_bytes(b"# old\n\nlegacy bytes\n")
            (legacy / "progress.jsonl").write_bytes(b'{"event":"old"}\n')
            before = snapshot(legacy)
            self.assert_refusal(
                run_plan(root, "check", "legacy"), "check", "legacy_record", version=None
            )
            self.assertEqual(snapshot(legacy), before)
            archived = self.assert_ok(
                run_plan(root, "archive", "legacy"), "archive", version=None
            )
            self.assertEqual(archived["record_version"], None)
            archive = root / ".agent_state" / "archives" / "legacy"
            self.assertEqual(snapshot(archive), before)
            resumed = self.assert_ok(
                run_plan(root, "resume", "legacy"), "resume", version=None
            )
            self.assertEqual(resumed["record_version"], None)
            self.assertEqual(snapshot(legacy), before)

    def test_present_malformed_version_is_not_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = task(root)
            (record / "phases").mkdir(parents=True)
            (record / "INDEX.md").write_text("# old\n| record_version | x |\n", encoding="utf-8")
            self.assert_refusal(
                run_plan(root, "check", "demo"), "check", "malformed_index", version=None
            )

    def test_create_never_publishes_an_invalid_or_over_budget_index(self) -> None:
        goals = ("g\n\n## Current\nspoof", "x" * 16_384)
        for goal in goals:
            with self.subTest(goal_size=len(goal)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.assert_refusal(
                    run_plan(root, "create", "demo", "--goal", goal),
                    "create",
                    "malformed_index",
                )
                self.assertFalse(task(root).exists())

    def test_placeholder_like_titles_round_trip_and_failed_create_is_atomic(self) -> None:
        for title in ("{{TICKET_ID}}", "{{TITLE}}", "{{DEPENDS_ON}}", "{{OUTCOME}}"):
            with self.subTest(title=title), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
                created = self.assert_ok(
                    run_plan(
                        root,
                        "ticket-create",
                        "demo",
                        "--title",
                        title,
                        "--outcome",
                        "canonical outcome",
                    ),
                    "ticket-create",
                )
                ticket_id = str(created["ticket_id"])
                ticket = next((task(root) / "tickets").iterdir())
                self.assertEqual(ticket.read_text(encoding="utf-8").splitlines()[0], f"# {ticket_id} — {title}")
                self.assert_ok(run_plan(root, "check", "demo"), "check")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            before = snapshot(task(root))
            self.assert_refusal(
                run_plan(
                    root,
                    "ticket-create",
                    "demo",
                    "--title",
                    "safe",
                    "--outcome",
                    "outcome\n\n## Current\ninjected",
                ),
                "ticket-create",
                "malformed_ticket",
            )
            self.assertEqual(snapshot(task(root)), before)

    def test_valid_ticket_survives_index_budget_failure_and_refresh_can_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = task(root) / "INDEX.md"
            index_before_budget = index.read_bytes()
            index.write_bytes(index_before_budget + b"x" * (16_384 - len(index_before_budget)))
            self.assert_ok(run_plan(root, "check", "demo"), "check")

            refused = self.assert_refusal(
                run_plan(
                    root,
                    "ticket-create",
                    "demo",
                    "--title",
                    "preserved evidence",
                    "--outcome",
                    "Keep the published ticket.",
                ),
                "ticket-create",
                "table_mismatch",
            )
            ticket = task(root) / "tickets" / "T001-preserved-evidence.md"
            expected_ticket = (
                "# T001 — preserved evidence\n\n"
                "| Ticket field | Value |\n"
                "|---|---|\n"
                "| id | T001 |\n"
                "| status | open |\n"
                "| depends_on | none |\n\n"
                "## Outcome\n"
                "Keep the published ticket.\n\n"
                "## Current\n"
                "Ticket created.\n\n"
                "## Decisions\n"
                "| ID | Status | Decision | Supersedes |\n"
                "|---|---|---|---|\n\n"
                "## Evidence\n\n"
                "## Result\n"
                "pending\n"
            ).encode()
            self.assertEqual(ticket.read_bytes(), expected_ticket)
            self.assertIn("INDEX.md", str(refused["error"]))
            self.assert_refusal(
                run_plan(root, "check", "demo"), "check", "table_mismatch"
            )
            self.assertEqual(ticket.read_bytes(), expected_ticket)

            index.write_bytes(index_before_budget)
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assert_ok(run_plan(root, "check", "demo"), "check")
            self.assertEqual(ticket.read_bytes(), expected_ticket)
            self.assertIn(
                "| T001 | open | preserved evidence | none |",
                index.read_text(encoding="utf-8"),
            )

    def test_evidence_contains_zero_or_more_markdown_pointers_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            self.assert_ok(
                run_plan(root, "ticket-create", "demo", "--title", "a", "--outcome", "o"),
                "ticket-create",
            )
            ticket = task(root) / "tickets" / "T001-a.md"
            ticket.write_text(
                ticket.read_text(encoding="utf-8").replace(
                    "## Evidence\n\n## Result",
                    "## Evidence\ncontext [Index](../INDEX.md)\n\n## Result",
                ),
                encoding="utf-8",
            )
            self.assert_refusal(
                run_plan(root, "check", "demo"), "check", "malformed_ticket"
            )

    def test_archive_resume_collision_uniqueness_is_case_insensitive(self) -> None:
        cases = (("archive", "plans", "archives"), ("resume", "archives", "plans"))
        for operation, source_location, destination_location in cases:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.assert_ok(run_plan(root, "create", "Demo", "--goal", "g"), "create")
                if operation == "resume":
                    self.assert_ok(run_plan(root, "archive", "Demo"), "archive")
                source = root / ".agent_state" / source_location / "Demo"
                collision = root / ".agent_state" / destination_location / "demo"
                collision.mkdir(parents=True)
                before = snapshot(source)
                self.assert_refusal(
                    run_plan(root, operation, "Demo"), operation, "record_exists"
                )
                self.assertEqual(snapshot(source), before)

    def test_legacy_discriminator_requires_a_record_version_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = task(root, "legacy")
            (legacy / "phases").mkdir(parents=True)
            (legacy / "INDEX.md").write_text(
                "# old\n\nProse mentioning record_version is not a field.\n",
                encoding="utf-8",
            )
            self.assert_refusal(
                run_plan(root, "check", "legacy"),
                "check",
                "legacy_record",
                version=None,
            )

    def test_legacy_moves_do_not_interpret_internal_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = task(root, "legacy")
            (legacy / "phases").mkdir(parents=True)
            (legacy / "INDEX.md").write_text("# old\n", encoding="utf-8")
            (legacy / "opaque-link").symlink_to("missing-target")
            before = snapshot(legacy)
            self.assert_ok(
                run_plan(root, "archive", "legacy"), "archive", version=None
            )
            archived = root / ".agent_state" / "archives" / "legacy"
            self.assertEqual(snapshot(archived), before)
            self.assert_ok(
                run_plan(root, "resume", "legacy"), "resume", version=None
            )
            self.assertEqual(snapshot(legacy), before)

    def test_legacy_collision_refusal_reports_null_record_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = task(root, "legacy")
            (legacy / "phases").mkdir(parents=True)
            (legacy / "INDEX.md").write_text("# old\n", encoding="utf-8")
            (root / ".agent_state" / "archives" / "LEGACY").mkdir(parents=True)
            self.assert_refusal(
                run_plan(root, "archive", "legacy"),
                "archive",
                "record_exists",
                version=None,
            )


class AuthorityCutoverContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_s0_has_one_normative_copy_and_both_owners_always_read_it(self) -> None:
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
        self.assertIn("before wayfinding, spec, or ticket admission", dev_flow)
        self.assertIn("before creating the first lane", orchestrate)

    def test_dev_flow_owns_one_generic_task_lifecycle_without_queue_state(self) -> None:
        dev_flow = self.read("home/.codex/skills/dev-flow/SKILL.md")
        standard = self.read("home/.codex/skills/dev-flow/references/admission-standard.md")
        self.assertIn("scripts/plan.py", dev_flow)
        self.assertIn("ordinary generic ticket", dev_flow)
        self.assertIn("Machine rework: N/2", standard)
        self.assertIn("candidate Git ref", standard)
        self.assertNotIn("planning-with-files", dev_flow)
        for retired in (
            "machine_rework_cycles",
            "deferred row",
            "accepted SHA",
            "pre and post review bracket",
            "acceptance queue",
        ):
            self.assertNotIn(retired, standard)

    def test_plan_directory_callers_share_dev_flow_tickets_and_artifact_pointers(self) -> None:
        expected = {
            "wayfinder": ("dev-flow", "tickets/*.md", "wayfinder-map.md"),
            "to-spec": ("dev-flow", "spec.md", "Artifacts"),
            "to-tickets": ("ticket-create", "tickets/*.md", "depends_on"),
            "prototype": ("generic ticket", "artifact pointer"),
            "candidate-backlog/references/lifecycle": ("dev-flow", "task record"),
        }
        for name, phrases in expected.items():
            codex_relative = f"home/.codex/skills/{name}/SKILL.md"
            if name.endswith("/lifecycle"):
                codex_relative = "home/.codex/skills/candidate-backlog/references/lifecycle.md"
                pi_relative = "home/.pi/agent/skills/candidate-backlog/references/lifecycle.md"
            else:
                pi_relative = f"home/.pi/agent/skills/{name}/SKILL.md"
            codex = self.read(codex_relative)
            for phrase in phrases:
                self.assertIn(phrase, codex, codex_relative)
            for retired in ("planning-with-files", "tickets.md", "task_plan.md"):
                self.assertNotIn(retired, codex, codex_relative)
            self.assertEqual(codex, self.read(pi_relative), pi_relative)

    def test_review_profiles_bind_exact_checkout_without_persisted_brackets(self) -> None:
        paths = (
            "home/.codex/agents/acceptance-reviewer.toml",
            "home/.pi/agent/agents/acceptance-reviewer.md",
            "home/.claude/agents/acceptance-reviewer.md",
        )
        for relative in paths:
            text = self.read(relative)
            for phrase in ("exact SHA", "same path", "same branch", "clean", "No collect or mutation"):
                self.assertIn(phrase, text, relative)
            self.assertNotIn("review bracket", text, relative)
            self.assertNotIn("pre and post", text, relative)
            self.assertNotIn("acceptance record", text, relative)


if __name__ == "__main__":
    unittest.main()
