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


def ticket(ticket_id: str, state: str, body: str = "") -> str:
    return f"---\nid: {ticket_id}\nstate: {state}\n---\n# arbitrary narrative\n{body}"


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
    def assert_ok(self, done: subprocess.CompletedProcess[str], operation: str) -> dict[str, object]:
        self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
        body = payload(done)
        self.assertIs(body["ok"], True)
        self.assertEqual(body["operation"], operation)
        self.assertNotIn("error", body)
        return body

    def assert_refusal(
        self, done: subprocess.CompletedProcess[str], operation: str, code: str
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 1, done.stderr or done.stdout)
        self.assertEqual(done.stderr, "")
        body = payload(done)
        self.assertIs(body["ok"], False)
        self.assertEqual(body["operation"], operation)
        error = body["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["code"], code)
        self.assertEqual(error["paths"], sorted(error["paths"]))
        self.assertTrue(error["repair"])
        return body

    def test_interface_has_only_create_archive_list_and_locate(self) -> None:
        done = run_plan(Path(tempfile.gettempdir()), "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        choices = re.search(r"\{([^{}]+)\}", done.stdout)
        self.assertIsNotNone(choices, done.stdout)
        assert choices is not None
        self.assertEqual(
            tuple(part.strip() for part in choices.group(1).split(",")),
            ("create", "archive", "list", "locate"),
        )

        list_help = run_plan(Path(tempfile.gettempdir()), "list", "--help")
        self.assertEqual(list_help.returncode, 0, list_help.stderr)
        self.assertNotIn("task_id", list_help.stdout)

    def test_list_missing_and_empty_plans_succeed_without_writes(self) -> None:
        for plans_exist in (False, True):
            with self.subTest(plans_exist=plans_exist), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                if plans_exist:
                    (root / ".agent_state" / "plans").mkdir(parents=True)
                before = snapshot(root)

                listed = self.assert_ok(run_plan(root, "list"), "list")

                self.assertEqual(snapshot(root), before, "list must not write")
                self.assertEqual(listed["record_version"], None)
                self.assertEqual(listed["location"], "active")
                self.assertEqual(listed["records"], [])

    def test_list_is_deterministic_active_only_and_exposes_narrow_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plans = root / ".agent_state" / "plans"
            archives = root / ".agent_state" / "archives"
            for name in ("beta", "Alpha", "alpha", "Zulu"):
                (plans / name).mkdir(parents=True)
            (archives / "archived-only").mkdir(parents=True)
            before = snapshot(root)

            listed = self.assert_ok(run_plan(root, "list"), "list")

            self.assertEqual(snapshot(root), before, "list must not write")
            self.assertEqual(
                listed["records"],
                [
                    {
                        "lookup_id": "Alpha",
                        "container": ".agent_state/plans/Alpha",
                        "index": ".agent_state/plans/Alpha/INDEX.md",
                    },
                    {
                        "lookup_id": "alpha",
                        "container": ".agent_state/plans/alpha",
                        "index": ".agent_state/plans/alpha/INDEX.md",
                    },
                    {
                        "lookup_id": "beta",
                        "container": ".agent_state/plans/beta",
                        "index": ".agent_state/plans/beta/INDEX.md",
                    },
                    {
                        "lookup_id": "Zulu",
                        "container": ".agent_state/plans/Zulu",
                        "index": ".agent_state/plans/Zulu/INDEX.md",
                    },
                ],
            )
            rendered = json.dumps(listed)
            self.assertNotIn("archived-only", rendered)
            for entry in listed["records"]:
                self.assertEqual(set(entry), {"lookup_id", "container", "index"})
            for forbidden in (
                "task_id",
                "spec",
                "tickets",
                "orientation",
                "parse_errors",
                "current",
                "next",
                "health",
            ):
                self.assertNotIn(forbidden, rendered.casefold())

    def test_list_does_not_read_malformed_legacy_or_binary_record_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contents = {
                "binary": b"\x00\xff narrative SECRET-BINARY",
                "legacy": b"# old INDEX\n## Current\nSECRET-LEGACY\n",
                "malformed": b"---\ntask_id: nope\nSECRET-MALFORMED",
            }
            for name, index_bytes in contents.items():
                task = record(root, name)
                (task / "tickets").mkdir(parents=True)
                (task / "INDEX.md").write_bytes(index_bytes)
                (task / "tickets" / "T001.md").write_bytes(b"\x00\xff SECRET-TICKET")
            before = snapshot(root)

            listed = self.assert_ok(run_plan(root, "list"), "list")

            self.assertEqual(snapshot(root), before, "list must not write")
            self.assertEqual(
                [entry["lookup_id"] for entry in listed["records"]],
                ["binary", "legacy", "malformed"],
            )
            rendered = json.dumps(listed)
            self.assertNotIn("SECRET", rendered)
            self.assertNotIn("ticket", rendered.casefold())
            self.assertNotIn("current", rendered.casefold())

    def test_list_fails_closed_for_unsafe_parent_children_and_names(self) -> None:
        parent_setups = (
            ("state-file", lambda root: (root / ".agent_state").write_text("unsafe")),
            (
                "plans-file",
                lambda root: (
                    (root / ".agent_state").mkdir(),
                    (root / ".agent_state" / "plans").write_text("unsafe"),
                ),
            ),
            (
                "plans-symlink",
                lambda root: (
                    (root / ".agent_state").mkdir(),
                    (root / ".agent_state" / "plans").symlink_to(root, target_is_directory=True),
                ),
            ),
        )
        for label, setup in parent_setups:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                setup(root)
                before = snapshot(root)

                refused = self.assert_refusal(run_plan(root, "list"), "list", "unsafe_path")

                self.assertEqual(snapshot(root), before, "list refusal must not write")
                self.assertTrue(refused["error"]["paths"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plans = root / ".agent_state" / "plans"
            plans.mkdir(parents=True)
            (plans / "valid").mkdir()
            (plans / "regular-file").write_text("unsafe")
            (plans / "linked").symlink_to(plans / "valid", target_is_directory=True)
            (plans / "bad name").mkdir()
            (plans / "é").mkdir()
            before = snapshot(root)

            refused = self.assert_refusal(run_plan(root, "list"), "list", "unsafe_path")

            self.assertEqual(snapshot(root), before, "list refusal must not write")
            self.assertEqual(
                refused["error"]["paths"],
                [
                    ".agent_state/plans/bad name",
                    ".agent_state/plans/linked",
                    ".agent_state/plans/regular-file",
                    ".agent_state/plans/é",
                ],
            )
            self.assertNotIn("records", refused)

    def test_list_refuses_inaccessible_state_ancestors_without_writes(self) -> None:
        for inaccessible_name in (".agent_state", "plans"):
            with (
                self.subTest(inaccessible_name=inaccessible_name),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                plans = root / ".agent_state" / "plans"
                plans.mkdir(parents=True)
                before = snapshot(root)
                inaccessible = (
                    root / ".agent_state"
                    if inaccessible_name == ".agent_state"
                    else plans
                )
                inaccessible.chmod(0)
                try:
                    try:
                        with os.scandir(inaccessible) as entries:
                            list(entries)
                    except PermissionError:
                        pass
                    else:
                        self.skipTest("executing account can enumerate a mode-000 directory")

                    done = run_plan(root, "list")
                    refused = self.assert_refusal(done, "list", "unsafe_path")
                    self.assertEqual(len(done.stdout.splitlines()), 1)
                    self.assertEqual(refused["error"]["paths"], [".agent_state/plans"])
                finally:
                    inaccessible.chmod(0o700)

                self.assertEqual(snapshot(root), before, "list refusal must not write")

    def test_list_refusal_serializes_undecodable_entry_name_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plans = root / ".agent_state" / "plans"
            plans.mkdir(parents=True)
            undecodable_name = os.fsdecode(b"\xff")
            os.mkdir(os.path.join(os.fsencode(plans), b"\xff"))
            before = snapshot(root)

            done = run_plan(root, "list")
            refused = self.assert_refusal(done, "list", "unsafe_path")

            self.assertEqual(len(done.stdout.splitlines()), 1)
            self.assertEqual(refused["error"]["paths"], [f".agent_state/plans/{undecodable_name}"])
            self.assertEqual(snapshot(root), before, "list refusal must not write")

    def test_create_emits_required_task_scaffold_without_validation_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            body = self.assert_ok(
                run_plan(root, "create", "demo", "--goal", "Ship one durable record."), "create"
            )
            self.assertEqual(
                body["paths"],
                [
                    ".agent_state/plans/demo/INDEX.md",
                    ".agent_state/plans/demo/tickets",
                    ".agent_state/plans/demo/artifacts",
                ],
            )
            for scaffolded in ("tickets", "artifacts"):
                self.assertTrue((record(root) / scaffolded).is_dir(), scaffolded)
            self.assertFalse((record(root) / "validation").exists())
            created = (record(root) / "INDEX.md").read_text(encoding="utf-8")
            frontmatter = created.split("---", 2)[1].strip().splitlines()
            self.assertEqual(frontmatter, ["task_id: demo", "spec: none"])
            self.assertIn("Ship one durable record.", created)

            create_help = run_plan(root, "create", "--help")
            self.assertEqual(create_help.returncode, 0, create_help.stderr)
            self.assertNotIn("--spec", create_help.stdout)

    def test_locate_counts_new_and_legacy_ticket_bodies_from_frontmatter_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            (task / "INDEX.md").write_text(
                "---\ntask_id: demo\nspec: none\n---\nNo conventional narrative sections.\n",
                encoding="utf-8",
            )
            legacy_body = (
                "**Resolve by:** someone else\n"
                "## Validation\n../validation/T001-first.md\n"
                "## Current\nMisleading lifecycle claim: closed.\n"
            )
            new_body = (
                "## Acceptance\n- [ ] **A1** — deliberately unchecked\n"
                "## Resolution\nPending. Misleading lifecycle claim: pending.\n"
            )
            (task / "tickets" / "T001-first.md").write_text(
                ticket("T001-first", "pending", legacy_body), encoding="utf-8"
            )
            (task / "tickets" / "T002-done.md").write_text(
                ticket("T002-done", "closed", new_body), encoding="utf-8"
            )
            before = snapshot(task)

            located = self.assert_ok(run_plan(root, "locate", "DEMO"), "locate")

            self.assertEqual(snapshot(task), before, "locate must not write")
            self.assertEqual(located["location"], "active")
            self.assertEqual(located["container"], ".agent_state/plans/demo")
            self.assertEqual(located["index"], ".agent_state/plans/demo/INDEX.md")
            self.assertEqual(located["task_id"], "demo")
            self.assertEqual(located["spec"], "none")
            self.assertEqual(
                located["tickets"],
                {"pending": 1, "closed": 1, "total": 2, "unreadable": 0},
            )
            self.assertEqual(located["orientation"], "available")
            self.assertEqual(located["parse_errors"], [])
            rendered = json.dumps(located)
            self.assertNotIn("T001-first.md", rendered)
            self.assertNotIn("depends_on", rendered)
            for forbidden in ("health", "current", "artifacts", "then_run", "lint", "stale"):
                self.assertNotIn(forbidden, located)

    def test_locate_reads_comments_and_hashes_in_flat_scalar_frontmatter(self) -> None:
        cases = (
            ("artifacts/spec.md # frozen pointer", "artifacts/spec.md"),
            ('"artifacts/spec#v1.md" # frozen pointer', "artifacts/spec#v1.md"),
            ("'artifacts/spec#v2.md' # frozen pointer", "artifacts/spec#v2.md"),
        )
        for source, expected in cases:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
                index = record(root) / "INDEX.md"
                index.write_text(
                    index.read_text(encoding="utf-8").replace("spec: none", f"spec: {source}"),
                    encoding="utf-8",
                )

                located = self.assert_ok(run_plan(root, "locate", "demo"), "locate")

                self.assertEqual(located["spec"], expected)
                self.assertEqual(located["orientation"], "available")

    def test_unsupported_yaml_degrades_orientation_instead_of_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            index.write_text(
                index.read_text(encoding="utf-8").replace("spec: none", "spec: [artifacts/spec.md]"),
                encoding="utf-8",
            )

            located = self.assert_ok(run_plan(root, "locate", "demo"), "locate")

            self.assertIsNone(located["task_id"])
            self.assertIsNone(located["spec"])
            self.assertEqual(located["orientation"], "unavailable")
            self.assertEqual(
                located["parse_errors"][0]["code"], "index_frontmatter_unavailable"
            )

    def test_invalid_index_task_id_keeps_location_but_degrades_orientation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            index = record(root) / "INDEX.md"
            index.write_text(
                index.read_text(encoding="utf-8").replace("task_id: demo", "task_id: ../escape"),
                encoding="utf-8",
            )

            located = self.assert_ok(run_plan(root, "locate", "demo"), "locate")

            self.assertEqual(located["location"], "active")
            self.assertEqual(located["container"], ".agent_state/plans/demo")
            self.assertEqual(located["index"], ".agent_state/plans/demo/INDEX.md")
            self.assertIsNone(located["task_id"])
            self.assertIsNone(located["spec"])
            self.assertEqual(located["orientation"], "unavailable")
            self.assertEqual(
                located["parse_errors"][0]["code"], "index_frontmatter_unavailable"
            )

    def test_locate_reads_only_frontmatter_and_leaves_binary_bodies_opaque(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            task = record(root)
            (task / "INDEX.md").write_bytes(
                b"---\ntask_id: demo\nspec: artifacts/spec.md\n---\nopaque:\xff\x00body"
            )
            (task / "tickets" / "T001.md").write_bytes(
                b"---\nid: T001\nstate: pending\n---\nopaque:\xff\x00body"
            )

            located = self.assert_ok(run_plan(root, "locate", "demo"), "locate")

            self.assertEqual(located["orientation"], "available")
            self.assertEqual(located["spec"], "artifacts/spec.md")
            self.assertEqual(
                located["tickets"],
                {"pending": 1, "closed": 0, "total": 1, "unreadable": 0},
            )
            self.assertEqual(located["parse_errors"], [])

    def test_malformed_and_legacy_indexes_still_locate_without_rewrite(self) -> None:
        for label, index_text in (
            ("malformed", "---\ntask_id: malformed\nno closing marker\n"),
            ("legacy", "# legacy\n| task_id | legacy |\n## Current\nDo not parse me.\n"),
            ("mismatched", "---\ntask_id: other\nspec: none\n---\n"),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                task = record(root, label)
                (task / "tickets").mkdir(parents=True)
                (task / "tickets" / "T001.md").write_text(
                    ticket("T001", "pending"), encoding="utf-8"
                )
                index = task / "INDEX.md"
                index.write_text(index_text, encoding="utf-8")
                before = snapshot(task)

                located = self.assert_ok(run_plan(root, "locate", label), "locate")

                self.assertEqual(snapshot(task), before)
                self.assertEqual(located["location"], "active")
                self.assertEqual(located["orientation"], "unavailable")
                self.assertIsNone(located["task_id"])
                self.assertIsNone(located["spec"])
                self.assertEqual(
                    located["tickets"],
                    {"pending": 1, "closed": 0, "total": 1, "unreadable": 0},
                )
                self.assertEqual(len(located["parse_errors"]), 1)
                self.assertEqual(
                    located["parse_errors"][0]["code"], "index_frontmatter_unavailable"
                )

    def test_one_unreadable_ticket_makes_all_counts_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            tickets = record(root) / "tickets"
            (tickets / "T001.md").write_text(ticket("T001", "pending"), encoding="utf-8")
            (tickets / "T002.md").write_text("state: closed in prose only\n", encoding="utf-8")

            located = self.assert_ok(run_plan(root, "locate", "demo"), "locate")

            self.assertEqual(located["orientation"], "partial")
            self.assertEqual(
                located["tickets"],
                {"pending": None, "closed": None, "total": None, "unreadable": 1},
            )
            self.assertEqual(
                located["parse_errors"], [{"code": "ticket_headers_unreadable", "count": 1}]
            )
            self.assertNotIn("T002.md", json.dumps(located))

    def test_permission_denied_ticket_directory_never_fabricates_zero_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            tickets = record(root) / "tickets"
            (tickets / "T001.md").write_text(ticket("T001", "pending"), encoding="utf-8")
            tickets.chmod(0)
            try:
                try:
                    with os.scandir(tickets) as entries:
                        list(entries)
                except PermissionError:
                    pass
                else:
                    self.skipTest("executing account can enumerate a mode-000 directory")

                located = self.assert_ok(run_plan(root, "locate", "demo"), "locate")

                self.assertEqual(located["orientation"], "partial")
                self.assertEqual(
                    located["tickets"],
                    {"pending": None, "closed": None, "total": None, "unreadable": None},
                )
                self.assertEqual(
                    located["parse_errors"], [{"code": "ticket_directory_unreadable"}]
                )
            finally:
                tickets.chmod(0o700)

    def test_locate_reports_archived_missing_and_ambiguous_locations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo", "--goal", "g"), "create")
            self.assert_ok(run_plan(root, "archive", "demo"), "archive")
            archived = self.assert_ok(run_plan(root, "locate", "demo"), "locate")
            self.assertEqual(archived["location"], "archived")
            self.assertEqual(archived["container"], ".agent_state/archives/demo")
            self.assertEqual(archived["index"], ".agent_state/archives/demo/INDEX.md")

            missing = self.assert_ok(run_plan(root, "locate", "absent"), "locate")
            self.assertEqual(missing["location"], "missing")
            self.assertEqual(missing["container"], ".agent_state/plans/absent")
            self.assertEqual(missing["index"], ".agent_state/plans/absent/INDEX.md")
            self.assertEqual(missing["orientation"], "unavailable")

            active_collision = root / ".agent_state" / "plans" / "DEMO"
            active_collision.mkdir(parents=True)
            ambiguous = self.assert_ok(run_plan(root, "locate", "demo"), "locate")
            self.assertEqual(ambiguous["location"], "ambiguous")
            self.assertIsNone(ambiguous["container"])
            self.assertEqual(
                ambiguous["candidates"],
                [
                    {
                        "location": "active",
                        "container": ".agent_state/plans/DEMO",
                        "index": ".agent_state/plans/DEMO/INDEX.md",
                    },
                    {
                        "location": "archived",
                        "container": ".agent_state/archives/demo",
                        "index": ".agent_state/archives/demo/INDEX.md",
                    },
                ],
            )

    def test_archive_and_undo_are_opaque_atomic_moves(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = record(root)
            (task / "tickets").mkdir(parents=True)
            (task / "INDEX.md").write_bytes(b"\x00legacy malformed bytes\xff")
            (task / "tickets" / "anything.bin").write_bytes(b"\x00\xff")
            before = snapshot(task)

            archived = self.assert_ok(run_plan(root, "archive", "demo"), "archive")
            destination = root / ".agent_state" / "archives" / "demo"
            self.assertEqual(archived["paths"], [".agent_state/archives/demo"])
            self.assertFalse(task.exists())
            self.assertEqual(snapshot(destination), before)

            restored = self.assert_ok(run_plan(root, "archive", "demo", "--undo"), "archive")
            self.assertEqual(restored["paths"], [".agent_state/plans/demo"])
            self.assertEqual(snapshot(task), before)
            self.assertFalse(destination.exists())

    def test_invalid_arguments_collisions_and_symlinks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for task_id in ("", "../escape", "a/b", "a" * 65, "é"):
                with self.subTest(task_id=task_id):
                    self.assert_refusal(
                        run_plan(root, "create", task_id, "--goal", "g"),
                        "create",
                        "invalid_argument",
                    )
                    self.assert_refusal(
                        run_plan(root, "locate", task_id), "locate", "invalid_argument"
                    )
            self.assert_refusal(
                run_plan(root, "create", "demo", "--goal", "  "),
                "create",
                "invalid_argument",
            )
            self.assert_ok(run_plan(root, "create", "Demo", "--goal", "g"), "create")
            self.assert_refusal(
                run_plan(root, "create", "demo", "--goal", "g"), "create", "record_exists"
            )

            unsafe = record(root, "Demo")
            (unsafe / "link").symlink_to(root / "missing")
            before = snapshot(unsafe)
            self.assert_refusal(run_plan(root, "archive", "Demo"), "archive", "unsafe_path")
            self.assertEqual(snapshot(unsafe), before)

    def test_locate_rejects_symlinked_container_and_parent_without_following(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as external:
            root = Path(temporary)
            outside = Path(external)
            plans = root / ".agent_state" / "plans"
            plans.mkdir(parents=True)

            container = plans / "demo"
            container.symlink_to(outside, target_is_directory=True)
            self.assert_refusal(run_plan(root, "locate", "demo"), "locate", "unsafe_path")
            self.assertTrue(container.is_symlink())

            container.unlink()
            plans.rmdir()
            plans.symlink_to(outside, target_is_directory=True)
            self.assert_refusal(run_plan(root, "locate", "demo"), "locate", "unsafe_path")
            self.assertTrue(plans.is_symlink())

    def test_move_collision_preserves_both_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "source", "--goal", "g"), "create")
            destination = root / ".agent_state" / "archives" / "SOURCE"
            destination.mkdir(parents=True)
            source_before = snapshot(record(root, "source"))
            refusal = self.assert_refusal(
                run_plan(root, "archive", "source"), "archive", "record_exists"
            )
            self.assertEqual(refusal["error"]["paths"], [".agent_state/archives/SOURCE"])
            self.assertEqual(snapshot(record(root, "source")), source_before)
            self.assertTrue(destination.is_dir())


if __name__ == "__main__":
    unittest.main()
