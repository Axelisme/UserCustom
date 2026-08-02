from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
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


def generated_projection(index: Path) -> str:
    text = index.read_text(encoding="utf-8")
    start = "<!-- task-record:files:start -->"
    end = "<!-- task-record:files:end -->"
    start_index = text.index(start) + len(start)
    return text[start_index : text.index(end, start_index)].strip("\r\n")


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
        self.assertEqual(set(error), {"code", "message", "paths"})
        self.assertEqual(error["code"], code)
        self.assertEqual(error["paths"], sorted(error["paths"]))
        return body

    def test_interface_has_exactly_four_commands(self) -> None:
        done = run_plan(Path(tempfile.gettempdir()), "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        command_line = next(line for line in done.stdout.splitlines() if "{create," in line)
        for command in ("create", "refresh", "archive", "resume"):
            self.assertIn(command, command_line)
        for retired in ("ticket-create", "check", "init", "status", "show", "set", "phase", "log", "checkpoint", "migrate", "validate"):
            self.assertNotIn(retired, command_line)

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
            self.assertIn("| record_version | 3 |", index.read_text(encoding="utf-8"))
            self.assertIn("<!-- task-record:files:start -->\nINDEX.md\ntickets/\n<!-- task-record:files:end -->", index.read_text(encoding="utf-8"))
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
            self.assertIn(
                "INDEX.md\ndecisions.md\nevidence/\n  raw.bin\ntickets/\n  T001-any-name.md",
                after,
            )
            # Refresh always re-stamps, so a second call still exits clean even though the stamp
            # itself advances (it is not byte-for-byte idempotent, by design: see (b) staleness).
            second = self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertIsNone(second["stale"])

    def test_refresh_bounds_large_file_tree_by_depth_and_direct_file_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)

            # Build this in reverse order so the generated projection must impose its own
            # deterministic lexical order. INDEX.md is itself a direct regular file.
            for number in reversed(range(11)):
                (task / f"root-{number:02d}.md").write_text("root\n", encoding="utf-8")

            first = task / "a-dir"
            first.mkdir()
            for number in reversed(range(11)):
                (first / f"first-{number:02d}.md").write_text("first\n", encoding="utf-8")

            nested = first / "nested"
            nested.mkdir()
            (nested / "inside.md").write_text("inside\n", encoding="utf-8")
            deep = nested / "z-deep"
            deep.mkdir()
            (deep / "deep-a.md").write_text("deep\n", encoding="utf-8")
            deeper = deep / "deeper"
            deeper.mkdir()
            (deeper / "deep-b.md").write_text("deeper\n", encoding="utf-8")

            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertEqual(
                generated_projection(task / "INDEX.md"),
                "\n".join(
                    [
                        "INDEX.md",
                        "a-dir/",
                        "  first-00.md",
                        "  first-01.md",
                        "  first-02.md",
                        "  first-03.md",
                        "  first-04.md",
                        "  first-05.md",
                        "  first-06.md",
                        "  first-07.md",
                        "  first-08.md",
                        "  first-09.md",
                        "  nested/",
                        "    inside.md",
                        "    z-deep/",
                        "      ...2 file",
                        "  ...1 file",
                        "root-00.md",
                        "root-01.md",
                        "root-02.md",
                        "root-03.md",
                        "root-04.md",
                        "root-05.md",
                        "root-06.md",
                        "root-07.md",
                        "root-08.md",
                        "tickets/",
                        "...2 file",
                    ]
                ),
            )

    def test_refresh_omits_zero_file_metadata_for_level_three_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)

            empty = task / "empty" / "branch" / "leaf"
            empty.mkdir(parents=True)
            empty_subtree = task / "empty-subtree" / "branch" / "leaf"
            empty_subtree.mkdir(parents=True)
            (empty_subtree / "child").mkdir()

            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh")
            self.assertEqual(
                generated_projection(task / "INDEX.md"),
                "\n".join(
                    [
                        "INDEX.md",
                        "empty/",
                        "  branch/",
                        "    leaf/",
                        "empty-subtree/",
                        "  branch/",
                        "    leaf/",
                        "tickets/",
                    ]
                ),
            )

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
            self.assert_ok(run_plan(root, "refresh", "demo"), "refresh", version=2)
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
            self.assertIn("T001-legacy.md", index.read_text(encoding="utf-8"))

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
                "Current": ("verified", "authority", "do not"),
                "Next": ("next", "owner", "do not"),
                "Envelope": ("minimum", "out-of-envelope", "do not"),
                "Standing orders": ("verbatim", "issued", "do not"),
            }
            comments: list[str] = []
            for heading, (following, initial_fact) in sections.items():
                start = created.index(f"## {heading}\n") + len(f"## {heading}\n")
                end = created.index(f"\n## {following}", start) if following else created.index(
                    "\n<!-- task-record:files:start -->", start
                )
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

    def test_worked_example_tree_and_skill_link_are_absent(self) -> None:
        example = ROOT / "home" / ".codex" / "skills" / "dev-flow" / "references" / "example-record"
        self.assertFalse(example.exists())
        skill = (ROOT / "home" / ".codex" / "skills" / "dev-flow" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("references/example-record", skill)

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


if __name__ == "__main__":
    unittest.main()
