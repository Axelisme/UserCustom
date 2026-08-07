from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "dev-flow" / "scripts" / "plan.py"


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


START = "<!-- task-record:files:start -->"
END = "<!-- task-record:files:end -->"


def ticket_text(ticket_id: str, status: str, disposition: str | None = None, depends_on: str = "none") -> str:
    rows = [
        f"| id | {ticket_id} |",
        f"| status | {status} |",
    ]
    if disposition is not None:
        rows.append(f"| disposition | {disposition} |")
    rows.append(f"| depends_on | {depends_on} |")
    header = "\n".join(rows)
    return f"# {ticket_id} — test ticket\n\n| Ticket field | Value |\n|---|---|\n{header}\n\n## Current\n"


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


class TaskRecordTests(unittest.TestCase):
    def assert_ok(
        self,
        done: subprocess.CompletedProcess[str],
        operation: str,
        *,
        version: int | None = 3,
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
        self.assertEqual(set(error), {"code", "message", "paths", "repair"})
        self.assertEqual(error["code"], code)
        self.assertEqual(error["paths"], sorted(error["paths"]))
        repair = error["repair"]
        self.assertIsInstance(repair, str)
        assert isinstance(repair, str)
        self.assertTrue(repair)
        self.assertNotIn("#", repair)
        self.assertNotRegex(repair, r"\b[^ ]+\.md\b")
        return body

    def test_interface_has_exactly_four_commands(self) -> None:
        done = run_plan(Path(tempfile.gettempdir()), "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        choices = re.search(r"\{([^{}]+)\}", done.stdout)
        self.assertIsNotNone(choices, done.stdout)
        assert choices is not None
        # Equality, not membership: a command that is gone cannot hide in a list
        # nobody enumerates, and a new one cannot arrive unannounced.
        self.assertEqual(
            tuple(part.strip() for part in choices.group(1).split(",")),
            ("create", "refresh", "archive", "locate"),
        )

    def test_create_and_refresh_leave_no_generated_projection_behind(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            created = self.assert_ok(run_plan(root, "create", "demo", "--goal", "Ship one durable record."), "create")
            self.assertEqual(
                created["paths"],
                [".agent_state/plans/demo/INDEX.md", ".agent_state/plans/demo/tickets"],
            )
            task = record(root)
            index = task / "INDEX.md"
            self.assertIn("| record_version | 3 |", index.read_text(encoding="utf-8"))
            self.assertNotIn(START, index.read_text(encoding="utf-8"))
            (task / "decisions.md").write_text("arbitrary decision content\n", encoding="utf-8")
            (task / "tickets" / "T001-any-name.md").write_text(
                ticket_text("T001-any-name", "open") + "unparsed prose after the header\n",
                encoding="utf-8",
            )
            (task / "evidence").mkdir()
            (task / "evidence" / "raw.bin").write_bytes(b"\x00\xff")
            goal_before = index.read_text(encoding="utf-8").split("## Goal")[1].split("## Current")[0]
            refreshed = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertEqual(refreshed["paths"], [".agent_state/plans/demo/INDEX.md"])
            # A record with no prior stamp has nothing to compare against yet.
            self.assertIsNone(refreshed["stale"])
            after = index.read_text(encoding="utf-8")
            self.assertEqual(goal_before, after.split("## Goal")[1].split("## Current")[0])
            self.assertNotIn(START, after)
            # Refresh always re-stamps, so a second call still exits clean even though the stamp
            # itself advances (it is not byte-for-byte idempotent, by design: see (b) staleness).
            second = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertIsNone(second["stale"])

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
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh", version=2)
            after = index.read_text(encoding="utf-8")
            self.assertNotIn(START, after)
            self.assertNotIn("stale", after)
            self.assertIn("arbitrary prose", after)
            self.assertIn("not a record schema", after)

    def test_refresh_removes_the_generated_block_preserving_crlf_around_it(self) -> None:
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
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh", version=2)
            updated = index.read_bytes()
            self.assertEqual(
                updated,
                b"outside before\r\n| record_version | 2 |\r\noutside after\r\n",
            )

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
            index.write_text("| record_version | 2 |\n", encoding="utf-8")
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh", version=2)
            for text in (
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
            self.assert_refusal(run_plan(root, "locate", "missing"), "locate", "record_missing")
            self.assert_ok(run_plan(root, "create", "carriage", "--goal", "first\rsecond"), "create")
            self.assertIn(b"first\rsecond", (record(root, "carriage") / "INDEX.md").read_bytes())

    def test_archive_and_undo_preserve_legacy_and_v1_records_without_version_checks(self) -> None:
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
                    self.assert_ok(
                        run_plan(root, "archive", task_id, "--undo"), "archive", version=None
                    )
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
            self.assert_ok(run_plan(root, "create", "undo-source", "--goal", "g"), "create")
            self.assert_ok(run_plan(root, "archive", "undo-source"), "archive", version=None)
            destination = root / ".agent_state" / "plans" / "UNDO-source"
            destination.mkdir(parents=True)
            refused = self.assert_refusal(
                run_plan(root, "archive", "undo-source", "--undo"), "archive", "record_exists"
            )
            self.assertEqual(refused["error"].get("paths"), [".agent_state/plans/UNDO-source"])

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

    def test_v3_ticket_with_foreign_status_fails_naming_file_and_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            ticket = task / "tickets" / "T001-foreign-status.md"
            # `in_progress` is the harness Task-tool vocabulary, not dev-flow's — the exact
            # substitution D-012 documents.
            ticket.write_text(ticket_text("T001-foreign-status", "in_progress"), encoding="utf-8")
            refused = self.assert_refusal(
                run_plan(root, "refresh", "demo"), "refresh", "invalid_ticket_status", version=3
            )
            message = refused["error"]["message"]
            self.assertIn(".agent_state/plans/demo/tickets/T001-foreign-status.md", message)
            self.assertIn("in_progress", message)
            self.assertEqual(refused["error"]["paths"], [".agent_state/plans/demo/tickets/T001-foreign-status.md"])

    def test_v3_closed_ticket_without_disposition_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            ticket = task / "tickets" / "T001-closed.md"
            ticket.write_text(ticket_text("T001-closed", "closed"), encoding="utf-8")
            refused = self.assert_refusal(
                run_plan(root, "refresh", "demo"), "refresh", "invalid_ticket_disposition", version=3
            )
            self.assertIn(".agent_state/plans/demo/tickets/T001-closed.md", refused["error"]["message"])
            self.assertEqual(
                refused["error"]["repair"],
                "Set the named closed ticket disposition to resolved, superseded, out-of-scope, or hard-stop.",
            )
            self.assertEqual(refused["error"]["paths"], [".agent_state/plans/demo/tickets/T001-closed.md"])

    def test_v3_disposition_present_when_not_closed_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            ticket = task / "tickets" / "T001-open-with-disposition.md"
            ticket.write_text(ticket_text("T001-open-with-disposition", "open", disposition="resolved"), encoding="utf-8")
            self.assert_refusal(run_plan(root, "refresh", "demo"), "refresh", "invalid_ticket_disposition", version=3)

    def test_v3_valid_status_and_disposition_combinations_refresh_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            (task / "tickets" / "T001-open.md").write_text(ticket_text("T001-open", "open"), encoding="utf-8")
            (task / "tickets" / "T002-active.md").write_text(ticket_text("T002-active", "active"), encoding="utf-8")
            (task / "tickets" / "T003-closed.md").write_text(
                ticket_text("T003-closed", "closed", disposition="hard-stop"), encoding="utf-8"
            )
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")

    def test_v2_record_with_foreign_status_still_refreshes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = record(root)
            (task / "tickets").mkdir(parents=True)
            (task / "tickets" / "T001-legacy.md").write_text(ticket_text("T001-legacy", "pending"), encoding="utf-8")
            index = task / "INDEX.md"
            index.write_text(
                "| record_version | 2 |\n"
                "<!-- task-record:files:start -->\nstale\n<!-- task-record:files:end -->\n",
                encoding="utf-8",
            )
            refreshed = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh", version=2)
            self.assertNotIn("stale", refreshed)
            self.assertNotIn(START, index.read_text(encoding="utf-8"))
            # A foreign status keeps its own group, so the ticket stays visible instead of being
            # silently counted as finished.
            frontier = self.assert_ok(run_plan(root, "locate", "demo"), "locate", version=2)["tickets"]
            self.assertEqual(
                frontier,
                {
                    "active": [],
                    "open": [],
                    "pending": [".agent_state/plans/demo/tickets/T001-legacy.md"],
                    "closed_count": 0,
                },
            )

    def test_size_reports_sections_and_ignores_the_generated_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            index = task / "INDEX.md"
            index.write_text(
                index.read_text(encoding="utf-8").replace(
                    "None.\n", "- **2026-01-01 — User:** 「a」\n- **2026-01-02 — User:** 「b」\n"
                ),
                encoding="utf-8",
            )
            for name in range(40):
                (task / "tickets" / f"T{name:03d}-filler.md").write_text(
                    ticket_text(f"T{name:03d}-filler", "open"), encoding="utf-8"
                )
            size = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")["size"]
            self.assertIsInstance(size, dict)
            assert isinstance(size, dict)
            self.assertEqual(size["standing_orders"], 2)
            self.assertEqual(size["over_budget"], False)
            self.assertNotIn("repair", size)
            sections = size["sections"]
            assert isinstance(sections, dict)
            self.assertEqual(
                list(sections), ["Goal", "Current", "Next", "Envelope", "Standing orders"]
            )
            # The projected tree is machine-owned, so growing it must not consume the budget.
            authored = size["authored_chars"]
            assert isinstance(authored, int)
            self.assertLess(authored, len(index.read_text(encoding="utf-8")))

    def test_size_reports_over_budget_without_refusing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            index.write_text(
                index.read_text(encoding="utf-8").replace("Task created.", "x" * 7000),
                encoding="utf-8",
            )
            size = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")["size"]
            assert isinstance(size, dict)
            self.assertEqual(size["over_budget"], True)
            self.assertEqual(
                size["repair"],
                f"Remove at least {size['authored_chars'] - size['budget']} authored characters from the index.",
            )
            sections = size["sections"]
            assert isinstance(sections, dict)
            self.assertGreater(sections["Current"], 7000)

    def test_staleness_is_reported_after_hand_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            ticket = task / "tickets" / "T001-open.md"
            ticket.write_text(ticket_text("T001-open", "open"), encoding="utf-8")

            first = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertIsNone(first["stale"])
            index = task / "INDEX.md"
            self.assertRegex(index.read_text(encoding="utf-8"), r"<!-- task-record:refreshed-at:[^>]+ -->")

            # Hand-edit the ticket after the stamp `refresh` just left, without running `refresh`
            # again in between — the scenario this instrument exists to catch. The rewrite alone
            # bumps the file's mtime past the stamp already on disk.
            ticket.write_text(ticket_text("T001-open", "active"), encoding="utf-8")

            second = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertIsNotNone(second["stale"])
            self.assertIn(".agent_state/plans/demo/tickets/T001-open.md", second["stale"]["newer_ticket_files"])

            # Once refreshed again, the stamp catches up and staleness clears.
            third = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertIsNone(third["stale"])

    def test_create_generates_persistent_guidance_without_fabricating_initial_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            goal = "Ship one durable record."
            self.assert_ok(run_plan(root, "create", "demo", "--goal", goal), "create")
            index = record(root) / "INDEX.md"
            created = index.read_text(encoding="utf-8")
            sections = {
                "Goal": ("Current", goal),
                "Current": ("Next", "Task created."),
                "Next": ("Envelope", "Write or select the first ticket."),
                "Envelope": ("Standing orders", "Not yet recorded."),
                "Standing orders": (None, "None."),
            }
            guidance = {
                "Goal": ("user", "goal", "do not"),
                "Current": ("judgement", "receipts", "sha", "not "),
                "Next": ("next", "owner", "do not"),
                "Envelope": ("minimum", "out-of-envelope", "do not"),
                # The template points at Custody rather than restating it, so the
                # comment owes the pointer and the shape of an entry, not a second
                # copy of the rules SKILL.md holds.
                "Standing orders": (
                    "verbatim",
                    "custody",
                    "do not",
                    "lapse",
                ),
            }
            comments: list[str] = []
            for heading, (following, initial_fact) in sections.items():
                start = created.index(f"## {heading}\n") + len(f"## {heading}\n")
                end = created.index(f"\n## {following}", start) if following else len(created)
                body = created[start:end]
                matches = re.findall(r"<!--.*?-->", body, flags=re.DOTALL)
                self.assertEqual(len(matches), 1, heading)
                comment = matches[0].casefold()
                comments.append(matches[0])
                self.assertTrue(body.lstrip().startswith("<!--"), heading)
                for phrase in guidance[heading]:
                    self.assertIn(phrase, comment, heading)
                self.assertNotIn(goal.casefold(), comment)
                self.assertNotIn("config-single-source", comment)
                visible = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
                self.assertEqual(visible, initial_fact, heading)

            self.assertEqual(len(comments), 5)
            filled = created
            for old, new in {
                "Task created.": "Verified: no tickets yet.",
                "Write or select the first ticket.": "Select the first bounded ticket.",
                "Not yet recorded.": "spec.md",
                "None.": "No active orders.",
            }.items():
                filled = filled.replace(old, new)
            index.write_text(filled, encoding="utf-8")
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            refreshed = index.read_text(encoding="utf-8")
            for comment in comments:
                self.assertIn(comment, refreshed)

    def test_v3_refresh_leaves_v2_and_v1_content_untouched_by_new_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = record(root)
            (task / "tickets").mkdir(parents=True)
            index = task / "INDEX.md"
            index.write_text(
                "| record_version | 2 |\n<!-- task-record:files:start --><!-- task-record:files:end -->",
                encoding="utf-8",
            )
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh", version=2)
            self.assertNotIn("task-record:refreshed-at", index.read_text(encoding="utf-8"))

    def test_locate_orients_without_mutating_and_names_the_other_two_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            (task / "tickets" / "T001-first.md").write_text(ticket_text("T001-first", "active"), encoding="utf-8")
            (task / "tickets" / "T002-next.md").write_text(ticket_text("T002-next", "open", depends_on="T001-first"), encoding="utf-8")
            (task / "tickets" / "T003-done.md").write_text(ticket_text("T003-done", "closed", "resolved"), encoding="utf-8")
            before = snapshot(task)

            body = self.assert_ok(run_plan(root, "locate", "demo"), "locate")

            self.assertEqual(snapshot(task), before, "locate must not write")
            self.assertEqual(body["read"], [".agent_state/plans/demo/INDEX.md"])
            self.assertEqual(
                body["tickets"],
                {
                    "active": [".agent_state/plans/demo/tickets/T001-first.md"],
                    "open": [".agent_state/plans/demo/tickets/T002-next.md"],
                    "closed_count": 1,
                },
            )
            # The other two skills answer for themselves; locate points and stops there.
            self.assertEqual(
                body["then_run"],
                ["orchestrate.py status --task-id demo", "backlog.py list --status inbox"],
            )
            self.assertIn("size", body)
            self.assertIn("lint", body)

    def test_locate_omits_the_inventory_and_counts_closed_tickets(self) -> None:
        """An arriving reader pays for what places it, not for what the record contains."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            (task / "artifacts").mkdir()
            for number in range(12):
                (task / "artifacts" / f"receipt-{number:02d}.md").write_text("x", encoding="utf-8")
            (task / "tickets" / "T001-first.md").write_text(ticket_text("T001-first", "active"), encoding="utf-8")
            (task / "tickets" / "T002-next.md").write_text(ticket_text("T002-next", "open"), encoding="utf-8")
            for number in range(3):
                name = f"T1{number:02d}-done"
                (task / "tickets" / f"{name}.md").write_text(
                    ticket_text(name, "closed", "resolved"), encoding="utf-8"
                )

            body = self.assert_ok(run_plan(root, "locate", "demo"), "locate")

            self.assertNotIn("files", body)
            self.assertEqual(
                body["tickets"],
                {
                    "active": [".agent_state/plans/demo/tickets/T001-first.md"],
                    "open": [".agent_state/plans/demo/tickets/T002-next.md"],
                    "closed_count": 3,
                },
            )
            self.assertEqual(body["read"], [".agent_state/plans/demo/INDEX.md"])
            self.assertEqual(
                body["then_run"],
                ["orchestrate.py status --task-id demo", "backlog.py list --status inbox"],
            )
            for key in ("size", "lint", "stale"):
                self.assertIn(key, body)

            self.assertNotIn("files", self.assert_ok(run_plan(root, "refresh", "demo"), "refresh"))

    def test_locate_names_the_specific_malformed_standing_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            text = index.read_text(encoding="utf-8").replace(
                "Not yet recorded.", "Need and boundaries are frozen in spec.md."
            ).replace(
                "None.",
                "- **2026-08-08 — User:** 「Keep this exact.」\n"
                "  Lapses: explicit revocation.\n\n"
                "- **User:** 「Broken order.」\n"
                "  Lapses: explicit revocation.",
            )
            index.write_text(text, encoding="utf-8")

            findings = self.assert_ok(run_plan(root, "locate", "demo"), "locate")["lint"]

            self.assertEqual(
                findings,
                [
                    {
                        "section": "Standing orders",
                        "rule": "missing-date",
                        "entry": "- **User:** 「Broken order.」",
                        "repair": "Add a YYYY-MM-DD date to the named standing-order entry.",
                    }
                ],
            )

    def test_locate_reports_custody_obligation_lint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            created = index.read_text(encoding="utf-8")

            healthy = created.replace("Not yet recorded.", "Need and boundaries are frozen in spec.md.").replace(
                "None.",
                "- **2026-08-08 — User:** 「Keep this exact.」\n  Lapses: explicit revocation.",
            )
            index.write_text(healthy, encoding="utf-8")
            self.assertEqual(self.assert_ok(run_plan(root, "locate", "demo"), "locate")["lint"], [])

            malformed = created.replace("Not yet recorded.", "").replace(
                "None.", "- **User:** 「Keep this exact.」\n  Lapses: explicit revocation."
            )
            index.write_text(malformed, encoding="utf-8")
            findings = self.assert_ok(run_plan(root, "locate", "demo"), "locate")["lint"]
            self.assertEqual(
                findings,
                [
                    {
                        "section": "Envelope",
                        "rule": "blank",
                        "repair": "Add non-comment text to Envelope.",
                    },
                    {
                        "section": "Standing orders",
                        "rule": "missing-date",
                        "entry": "- **User:** 「Keep this exact.」",
                        "repair": "Add a YYYY-MM-DD date to the named standing-order entry.",
                    },
                ],
            )
            before = index.read_text(encoding="utf-8")
            self.assertEqual(self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")["lint"], findings)
            self.assertIn(before, index.read_text(encoding="utf-8"), "refresh may stamp, not repair the record")

            missing_lapse = healthy.replace("\n  Lapses: explicit revocation.", "")
            index.write_text(missing_lapse, encoding="utf-8")
            self.assertEqual(
                self.assert_ok(run_plan(root, "locate", "demo"), "locate")["lint"],
                [
                    {
                        "section": "Standing orders",
                        "rule": "missing-lapse",
                        "entry": "- **2026-08-08 — User:** 「Keep this exact.」",
                        "repair": "Add an indented non-empty Lapses: line to the named standing-order entry.",
                    }
                ],
            )

            not_verbatim = healthy.replace(
                "「Keep this exact.」", "Keep this exact, despite 「incidental punctuation」."
            )
            index.write_text(not_verbatim, encoding="utf-8")
            self.assertEqual(
                self.assert_ok(run_plan(root, "locate", "demo"), "locate")["lint"],
                [
                    {
                        "section": "Standing orders",
                        "rule": "missing-verbatim-quote",
                        "entry": "- **2026-08-08 — User:** Keep this exact, despite 「incidental punctuation」.",
                        "repair": "Put a 「...」 quote on the standing-order entry's first line.",
                    }
                ],
            )

    def test_locate_names_wrapped_and_non_outer_standing_order_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            text = index.read_text(encoding="utf-8").replace(
                "Not yet recorded.", "Need and boundaries are frozen in spec.md."
            ).replace(
                "None.",
                "- **2026-08-08 — User:** 「Keep this exact\n"
                "  across lines。」\n"
                "  Lapses: explicit revocation.\n\n"
                "- **2026-08-09 — User:** Keep this exact, despite 「incidental punctuation」.\n"
                "  Lapses: explicit revocation.",
            )
            index.write_text(text, encoding="utf-8")

            findings = self.assert_ok(run_plan(root, "locate", "demo"), "locate")["lint"]

            self.assertEqual(
                [(finding["rule"], finding["entry"]) for finding in findings],
                [
                    (
                        "quote-not-one-line",
                        "- **2026-08-08 — User:** 「Keep this exact",
                    ),
                    (
                        "missing-verbatim-quote",
                        "- **2026-08-09 — User:** Keep this exact, despite 「incidental punctuation」.",
                    ),
                ],
            )

    def test_every_lint_rule_carries_a_script_bound_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            malformed = index.read_text(encoding="utf-8").replace(
                "Task created.", "Landed ea508fc."
            ).replace(
                "Not yet recorded.", ""
            ).replace(
                "None.", "- **User:** no quote"
            )
            index.write_text(malformed, encoding="utf-8")

            findings = self.assert_ok(run_plan(root, "locate", "demo"), "locate")["lint"]

            self.assertEqual(
                findings,
                [
                    {
                        "section": "Current",
                        "rule": "hex",
                        "match": "ea508fc",
                        "repair": "Remove ea508fc from Current.",
                    },
                    {
                        "section": "Envelope",
                        "rule": "blank",
                        "repair": "Add non-comment text to Envelope.",
                    },
                    {
                        "section": "Standing orders",
                        "rule": "missing-date",
                        "entry": "- **User:** no quote",
                        "repair": "Add a YYYY-MM-DD date to the named standing-order entry.",
                    },
                    {
                        "section": "Standing orders",
                        "rule": "missing-lapse",
                        "entry": "- **User:** no quote",
                        "repair": "Add an indented non-empty Lapses: line to the named standing-order entry.",
                    },
                    {
                        "section": "Standing orders",
                        "rule": "missing-verbatim-quote",
                        "entry": "- **User:** no quote",
                        "repair": "Put a 「...」 quote on the standing-order entry's first line.",
                    },
                ],
            )
            for finding in findings:
                repair = finding["repair"]
                self.assertIsInstance(repair, str)
                assert isinstance(repair, str)
                self.assertTrue(repair)
                self.assertNotIn("#", repair)
                self.assertNotRegex(repair, r"\b[^ ]+\.md\b")

    def test_lint_names_frozen_state_in_current_and_next_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"

            narrative = index.read_text(encoding="utf-8").replace(
                "Task created.",
                "Took the adapter route because the direct one needs a decision we have not made; "
                "skipped the rollout checklist, it belongs to the next slice. Accepted 2026-08-03.",
            )
            index.write_text(narrative, encoding="utf-8")
            clean = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertEqual(clean["lint"], [], "prose, a year and ordinary English must not match")

            index.write_text(
                narrative.replace("Not yet recorded.", "Frozen at ea508fc by the user.").replace(
                    "Write or select the first ticket.", "Review 9db09f9 then land it."
                ),
                encoding="utf-8",
            )
            findings = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")["lint"]
            # `Next` is scanned; `Envelope` is not — a frozen pointer is legitimate content there.
            self.assertEqual(
                findings,
                [
                    {
                        "section": "Next",
                        "rule": "hex",
                        "match": "9db09f9",
                        "repair": "Remove 9db09f9 from Next.",
                    }
                ],
            )

            index.write_text(
                narrative.replace(
                    "Accepted 2026-08-03.", "Accepted at ea508fc, tree 5a83f10, 402 nodes."
                ),
                encoding="utf-8",
            )
            findings = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")["lint"]
            self.assertEqual(
                findings,
                [
                    {
                        "section": "Current",
                        "rule": "hex",
                        "match": "ea508fc",
                        "repair": "Remove ea508fc from Current.",
                    },
                    {
                        "section": "Current",
                        "rule": "hex",
                        "match": "5a83f10",
                        "repair": "Remove 5a83f10 from Current.",
                    },
                ],
                "the count is a known miss: only the hex rule shipped",
            )

    def test_refresh_reports_lint_without_refusing_or_editing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            index.write_text(
                index.read_text(encoding="utf-8").replace("Task created.", "Landed ea508fc."),
                encoding="utf-8",
            )
            refreshed = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertEqual(
                refreshed["lint"],
                [
                    {
                        "section": "Current",
                        "rule": "hex",
                        "match": "ea508fc",
                        "repair": "Remove ea508fc from Current.",
                    }
                ],
            )
            self.assertIn("Landed ea508fc.", index.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
