from __future__ import annotations

import contextlib
import dataclasses
import importlib.util
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "dev-flow" / "scripts" / "plan.py"


def load_plan():
    """Import the script as a module so its commands run in-process."""
    specification = importlib.util.spec_from_file_location("dev_flow_plan", SCRIPT)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


plan = load_plan()


@dataclasses.dataclass(frozen=True)
class Outcome:
    """What one command reported: its exit status and the streams it wrote."""

    returncode: int
    stdout: str
    stderr: str


def run_plan(root: Path, *arguments: str) -> Outcome:
    """Call the real entry point in-process, from `root`, exactly as the shell would.

    Running inside `root` rather than passing it keeps `main`'s own working-directory
    resolution under test; only the process boundary is dropped.
    Historic CWD-as-root tests run outside Git; they are preserved by injecting
    --repo when the directory is not inside a Git worktree. Discovery and
    repository_not_found branches are exercised via run_production which does
    not inject.
    """
    args = list(arguments)
    if "--repo" not in args and "--help" not in args and "-h" not in args:
        if not args or args[0] in ("create", "archive", "list", "locate"):
            # Check Git worktree membership without side effects
            try:
                probe = subprocess.run(
                    ["/usr/bin/git", "rev-parse", "--show-toplevel"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                outside_git = probe.returncode != 0
            except Exception:
                outside_git = True
            if outside_git:
                args = ["--repo", str(root), *args]
    out = io.StringIO()
    err = io.StringIO()
    status = 0
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            plan.main(args)
        except SystemExit as exit_status:  # a refusal, or argparse rejecting the arguments
            status = int(exit_status.code or 0)
    return Outcome(status, out.getvalue(), err.getvalue())


def run_production(root: Path, *arguments: str) -> Outcome:
    """Invoke the shipped plan.py via the authorized interpreter without injection.

    This exercises the production entrypoint exactly as a user would, including
    Git discovery and repository_not_found refusal, without the historic
    --repo injection that masks those branches.
    """
    proc = subprocess.run(
        ["/usr/bin/python3", str(SCRIPT), *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return Outcome(proc.returncode, proc.stdout, proc.stderr)


def payload(done: Outcome) -> dict[str, object]:
    return json.loads(done.stdout)


def record(root: Path, task_id: str = "demo") -> Path:
    return root / ".agent_state" / "plans" / task_id


def ticket(ticket_id: str, state: str, body: str = "") -> str:
    return f"---\nid: {ticket_id}\nstate: {state}\n---\n# arbitrary narrative\n{body}"


def write_ticket(tickets: Path, ticket_id: str, state: str, body: str = "") -> Path:
    """Place one lifecycle ticket in its own directory, as the record shape requires."""
    owner = tickets / ticket_id
    owner.mkdir(parents=True, exist_ok=True)
    path = owner / "ticket.md"
    path.write_text(ticket(ticket_id, state, body), encoding="utf-8")
    return path


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
    def assert_ok(self, done: Outcome, operation: str) -> dict[str, object]:
        self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
        body = payload(done)
        self.assertIs(body["ok"], True)
        self.assertEqual(body["operation"], operation)
        self.assertNotIn("error", body)
        return body

    def assert_refusal(
        self, done: Outcome, operation: str, code: str
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

    def test_interface_has_only_the_owned_container_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            overall = run_plan(root, "--help")
            self.assertEqual(overall.returncode, 0, overall.stderr)

            choices = re.search(r"\{([^{}]+)\}", overall.stdout)
            self.assertIsNotNone(choices, overall.stdout)
            assert choices is not None
            self.assertEqual(
                tuple(part.strip() for part in choices.group(1).split(",")),
                ("create", "archive", "list", "locate"),
            )

            listing = run_plan(root, "list", "--help")
            self.assertEqual(listing.returncode, 0, listing.stderr)
            self.assertNotIn("task_id", listing.stdout)

            self.assertEqual(snapshot(root), {}, "reading the interface must not write")

    def test_list_missing_and_empty_plans_succeed_without_writes(self) -> None:
        for plans_exist in (False, True):
            with self.subTest(plans_exist=plans_exist), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                if plans_exist:
                    (root / ".agent_state" / "plans").mkdir(parents=True)
                before = snapshot(root)

                listed = self.assert_ok(run_plan(root, "list"), "list")

                self.assertEqual(snapshot(root), before, "list must not write")
                self.assertNotIn("record_version", listed)
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
                (task / "tickets" / "T001").mkdir(parents=True)
                (task / "tickets" / "T001" / "ticket.md").write_bytes(b"\x00\xff SECRET-TICKET")
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

    def test_create_materializes_the_task_template_and_nothing_else(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            body = self.assert_ok(run_plan(root, "create", "demo"), "create")
            self.assertEqual(
                body["paths"],
                [
                    ".agent_state/plans/demo/INDEX.md",
                    ".agent_state/plans/demo/decisions",
                    ".agent_state/plans/demo/research",
                    ".agent_state/plans/demo/scripts",
                    ".agent_state/plans/demo/spec",
                    ".agent_state/plans/demo/standing-orders",
                    ".agent_state/plans/demo/tickets",
                ],
            )
            for scaffolded in ("tickets", "spec", "research", "decisions", "standing-orders"):
                self.assertTrue((record(root) / scaffolded).is_dir(), scaffolded)
                self.assertEqual(list((record(root) / scaffolded).iterdir()), [], scaffolded)
            self.assertFalse((record(root) / "artifacts").exists())
            self.assertEqual(
                sorted(path.name for path in record(root).iterdir()),
                ["INDEX.md", "decisions", "research", "scripts", "spec", "standing-orders", "tickets"],
            )
            created = (record(root) / "INDEX.md").read_text(encoding="utf-8")
            frontmatter = created.split("---", 2)[1].strip().splitlines()
            self.assertEqual(frontmatter, ["task_id: demo", "spec: none"])
            self.assertNotIn("{{", created, "every placeholder the script owns must be substituted")

            create_help = run_plan(root, "create", "--help")
            self.assertEqual(create_help.returncode, 0, create_help.stderr)
            for narrative_argument in ("--spec", "--goal"):
                self.assertNotIn(
                    narrative_argument,
                    create_help.stdout,
                    "the script owns container lifecycle, not narrative content",
                )

    def test_main_resolves_its_root_from_the_working_directory_and_reports_exit_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "nested"
            nested.mkdir()

            self.assert_ok(run_plan(root, "create", "demo"), "create")
            self.assertTrue(record(root).is_dir())

            # Run from a sibling directory: the record must follow the working directory, not the
            # previous call's root, and must not reach back up into it.
            created = self.assert_ok(run_plan(nested, "create", "demo"), "create")
            self.assertEqual(created["paths"][0], ".agent_state/plans/demo/INDEX.md")
            self.assertTrue((nested / ".agent_state" / "plans" / "demo").is_dir())

            refused = run_plan(root, "create", "demo")
            self.assert_refusal(refused, "create", "record_exists")
            self.assertEqual(refused.returncode, 1, "a refusal must exit non-zero")
            self.assertEqual(run_plan(root, "list").returncode, 0, "success must exit zero")

    def test_created_container_mirrors_the_task_template_exactly(self) -> None:
        source = SCRIPT.parent.parent / "templates" / "task"
        expected = {
            path.relative_to(source).as_posix()
            for path in source.rglob("*")
            if path.name != ".gitkeep"
        }
        self.assertTrue(expected, "the task template must not be empty")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo"), "create")
            produced = {
                path.relative_to(record(root)).as_posix() for path in record(root).rglob("*")
            }

            self.assertEqual(
                produced,
                expected,
                "templates/task/ and the container create produces must stay identical",
            )
            self.assertFalse(
                any(path.name == ".gitkeep" for path in record(root).rglob("*")),
                "the git placeholder must not reach a task record",
            )

    def test_per_ticket_templates_are_not_shipped_inside_the_task_template(self) -> None:
        templates = SCRIPT.parent.parent / "templates"
        for name in ("ticket.md", "evidence.md"):
            self.assertTrue((templates / "ticket" / name).is_file(), name)
        # A shipped ticket.md would be parsed by locate, and its placeholder id fails validation:
        # one unreadable ticket makes every count null, degrading orientation from birth.
        self.assertEqual(list((templates / "task" / "tickets").glob("*.md")), [])
        self.assertEqual(list((templates / "task").rglob("ticket.md")), [])

    def test_a_ticket_is_its_directory_and_evidence_beside_it_is_not_counted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo"), "create")
            tickets = record(root) / "tickets"
            write_ticket(tickets, "q13-feed", "pending")
            for kind in ("admission", "validation", "acceptance"):
                (tickets / "q13-feed" / f"{kind}.md").write_text("evidence", encoding="utf-8")
            (tickets / "q13-feed" / "gate-20260814T120000Z.log").write_text("log", encoding="utf-8")

            located = self.assert_ok(run_plan(root, "locate", "demo"), "locate")
            self.assertEqual(
                located["tickets"],
                {"pending": 1, "closed": 0, "total": 1, "unreadable": 0},
                "evidence sharing the ticket directory is not itself a ticket",
            )

    def test_a_ticket_directory_without_a_matching_ticket_file_is_unreadable(self) -> None:
        cases = {
            "missing ticket.md": lambda owner: owner.mkdir(parents=True),
            "id disagreeing with the directory": lambda owner: write_ticket(
                owner.parent, owner.name, "pending"
            ).write_text(ticket("other-id", "pending"), encoding="utf-8"),
        }
        for label, prepare in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.assert_ok(run_plan(root, "create", "demo"), "create")
                prepare(record(root) / "tickets" / "q13-feed")

                located = self.assert_ok(run_plan(root, "locate", "demo"), "locate")
                self.assertEqual(
                    located["tickets"],
                    {"pending": None, "closed": None, "total": None, "unreadable": 1},
                )
                self.assertEqual(located["orientation"], "partial")

    def test_locate_counts_new_and_legacy_ticket_bodies_from_frontmatter_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assert_ok(run_plan(root, "create", "demo"), "create")
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
            write_ticket(task / "tickets", "T001-first", "pending", legacy_body)
            write_ticket(task / "tickets", "T002-done", "closed", new_body)
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
                self.assert_ok(run_plan(root, "create", "demo"), "create")
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
            self.assert_ok(run_plan(root, "create", "demo"), "create")
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
            self.assert_ok(run_plan(root, "create", "demo"), "create")
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
            self.assert_ok(run_plan(root, "create", "demo"), "create")
            task = record(root)
            (task / "INDEX.md").write_bytes(
                b"---\ntask_id: demo\nspec: artifacts/spec.md\n---\nopaque:\xff\x00body"
            )
            (task / "tickets" / "T001").mkdir(parents=True)
            (task / "tickets" / "T001" / "ticket.md").write_bytes(
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
                write_ticket(task / "tickets", "T001", "pending")
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
            self.assert_ok(run_plan(root, "create", "demo"), "create")
            tickets = record(root) / "tickets"
            write_ticket(tickets, "T001", "pending")
            (tickets / "T002").mkdir(parents=True)
            (tickets / "T002" / "ticket.md").write_text(
                "state: closed in prose only\n", encoding="utf-8"
            )

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
            self.assert_ok(run_plan(root, "create", "demo"), "create")
            tickets = record(root) / "tickets"
            write_ticket(tickets, "T001", "pending")
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
            self.assert_ok(run_plan(root, "create", "demo"), "create")
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
                        run_plan(root, "create", task_id),
                        "create",
                        "invalid_argument",
                    )
                    self.assert_refusal(
                        run_plan(root, "locate", task_id), "locate", "invalid_argument"
                    )
            self.assert_ok(run_plan(root, "create", "Demo"), "create")
            self.assert_refusal(
                run_plan(root, "create", "demo"), "create", "record_exists"
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
            self.assert_ok(run_plan(root, "create", "source"), "create")
            destination = root / ".agent_state" / "archives" / "SOURCE"
            destination.mkdir(parents=True)
            source_before = snapshot(record(root, "source"))
            refusal = self.assert_refusal(
                run_plan(root, "archive", "source"), "archive", "record_exists"
            )
            self.assertEqual(refusal["error"]["paths"], [".agent_state/archives/SOURCE"])
            self.assertEqual(snapshot(record(root, "source")), source_before)
            self.assertTrue(destination.is_dir())

    def test_explicit_repo_inaccessible_directory_is_invalid_argument_without_control_root(self) -> None:
        for mode, label in ((0, "mode-000"), (0o400, "mode-0400")):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                candidate = root / "candidate"
                candidate.mkdir()
                # Make candidate inaccessible. This must be refused during
                # root selection as invalid_argument without a claimed control_root,
                # without reaching task-path inspection.
                candidate.chmod(mode)
                try:
                    # Effective inaccessibility: do not assume mode bits alone
                    # make the path inaccessible for every caller. POSIX ACLs
                    # may grant effective R_OK|X_OK, and root bypasses DAC.
                    # Only assert refusal when the current process is effectively
                    # denied read+traverse and enumeration.
                    try:
                        has_eff = os.access(candidate, os.R_OK | os.X_OK, effective_ids=True)
                    except TypeError:
                        has_eff = os.access(candidate, os.R_OK | os.X_OK)
                    if has_eff:
                        self.skipTest(f"candidate remains effectively accessible as {label} for caller {os.getuid()}")
                    # Do not skip solely on scandir success: a mode-0400 directory
                    # is still effectively inaccessible for read+traverse (needs X)
                    # even though listing may succeed. Only effective R_OK|X_OK
                    # determines genuine inaccessibility for --repo selection.
                    before = snapshot(root)
                    done = run_plan(root, "--repo", str(candidate), "list")
                    body = self.assert_refusal(done, "list", "invalid_argument")
                    self.assertNotIn("control_root", body, "inaccessible explicit root must not claim control_root")
                    self.assertNotIn("start_path", body)
                    self.assertEqual(body["error"]["paths"], [str(candidate)])
                    # No task-path inspection should have occurred: snapshot unchanged
                    self.assertEqual(snapshot(root), before, "inaccessible root must be refused before task-path inspection")
                    self.assertEqual(len(done.stdout.splitlines()), 1)
                    self.assertEqual(done.stderr, "")
                finally:
                    candidate.chmod(0o700)


class RootSelectionProductionTests(unittest.TestCase):
    """Production-entrypoint coverage for S1-S3 omitted by the in-process helper.

    run_production invokes the shipped plan.py via /usr/bin/python3 without
    injecting --repo, so Git discovery and repository_not_found branches are
    exercised exactly as a user would. These tests do not assert prose wording.
    """

    def assert_ok(self, done: Outcome, operation: str) -> dict[str, object]:
        self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
        body = json.loads(done.stdout)
        self.assertIs(body["ok"], True)
        self.assertEqual(body["operation"], operation)
        self.assertNotIn("error", body)
        return body

    def assert_refusal(self, done: Outcome, operation: str, code: str) -> dict[str, object]:
        self.assertEqual(done.returncode, 1, done.stderr or done.stdout)
        self.assertEqual(done.stderr, "")
        body = json.loads(done.stdout)
        self.assertIs(body["ok"], False)
        self.assertEqual(body["operation"], operation)
        error = body["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["code"], code)
        self.assertEqual(error["paths"], sorted(error["paths"]))
        self.assertTrue(error["repair"])
        return body

    def test_explicit_repo_from_another_cwd_uses_direct_directory_without_git_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_repo, tempfile.TemporaryDirectory() as tmp_cwd:
            repo = Path(tmp_repo)
            other = Path(tmp_cwd)
            # Explicit --repo from another CWD must use that directory directly even though
            # the CWD itself is outside Git and contains no record.
            done = run_production(other, "--repo", str(repo), "create", "demo")
            body = self.assert_ok(done, "create")
            self.assertEqual(body["control_root"], str(repo.resolve()))
            self.assertTrue((repo / ".agent_state/plans/demo").is_dir())
            self.assertFalse((other / ".agent_state").exists())
            # List from another CWD with explicit --repo
            listed = self.assert_ok(run_production(other, "--repo", str(repo), "list"), "list")
            self.assertEqual(listed["control_root"], str(repo.resolve()))
            self.assertEqual(listed["location"], "active")
            # Locate from another CWD with explicit --repo
            located = self.assert_ok(run_production(other, "--repo", str(repo), "locate", "demo"), "locate")
            self.assertEqual(located["control_root"], str(repo.resolve()))
            self.assertEqual(located["location"], "active")
            # Even when the CWD is itself a Git worktree, explicit --repo still wins and
            # does not silently redirect to the CWD's worktree root.
            subprocess.run(["/usr/bin/git", "init", "-q", str(other)], check=True)
            located2 = self.assert_ok(run_production(other, "--repo", str(repo), "locate", "demo"), "locate")
            self.assertEqual(located2["control_root"], str(repo.resolve()))

    def test_nested_git_discovery_selects_worktree_root_via_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            subprocess.run(["/usr/bin/git", "init", "-q", str(repo)], check=True)
            nested = repo / "nested" / "deep"
            nested.mkdir(parents=True)
            # Without --repo, CWD inside nested directory must discover the worktree root.
            created = self.assert_ok(run_production(nested, "create", "demo"), "create")
            self.assertEqual(created["control_root"], str(repo.resolve()))
            self.assertTrue((repo / ".agent_state/plans/demo").is_dir())
            self.assertFalse((nested / ".agent_state").exists())
            listed = self.assert_ok(run_production(nested, "list"), "list")
            self.assertEqual(listed["control_root"], str(repo.resolve()))
            located = self.assert_ok(run_production(nested, "locate", "demo"), "locate")
            self.assertEqual(located["control_root"], str(repo.resolve()))
            # Archive family also discovers via Git from nested CWD.
            archived = self.assert_ok(run_production(nested, "archive", "demo"), "archive")
            self.assertEqual(archived["control_root"], str(repo.resolve()))
            self.assertTrue((repo / ".agent_state/archives/demo").is_dir())
            restored = self.assert_ok(run_production(nested, "archive", "demo", "--undo"), "archive")
            self.assertEqual(restored["control_root"], str(repo.resolve()))
            self.assertTrue((repo / ".agent_state/plans/demo").is_dir())

    def test_outside_git_without_repo_returns_repository_not_found_via_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            probe = subprocess.run(
                ["/usr/bin/git", "rev-parse", "--show-toplevel"],
                cwd=outside,
                capture_output=True,
                text=True,
                check=False,
            )
            if probe.returncode == 0:
                self.skipTest("outside dir unexpectedly inside Git")
            for op in ("list", "create", "locate"):
                with self.subTest(operation=op):
                    args = [op] if op == "list" else [op, "someid"]
                    done = run_production(outside, *args)
                    body = self.assert_refusal(done, op, "repository_not_found")
                    self.assertNotIn("control_root", body)
                    self.assertIn("start_path", body)
                    self.assertEqual(body["start_path"], str(outside.resolve()))
                    self.assertEqual(len(done.stdout.splitlines()), 1)
                    self.assertEqual(done.stderr, "")

    def test_success_and_refusal_control_root_attribution_via_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["/usr/bin/git", "init", "-q", str(repo)], check=True)
            # Success payloads include absolute control_root.
            created = self.assert_ok(run_production(repo, "create", "demo"), "create")
            self.assertEqual(created["control_root"], str(repo.resolve()))
            listed = self.assert_ok(run_production(repo, "list"), "list")
            self.assertEqual(listed["control_root"], str(repo.resolve()))
            located = self.assert_ok(run_production(repo, "locate", "demo"), "locate")
            self.assertEqual(located["control_root"], str(repo.resolve()))
            archived = self.assert_ok(run_production(repo, "archive", "demo"), "archive")
            self.assertEqual(archived["control_root"], str(repo.resolve()))
            restored = self.assert_ok(run_production(repo, "archive", "demo", "--undo"), "archive")
            self.assertEqual(restored["control_root"], str(repo.resolve()))
            # Ordinary refusal after root selection includes control_root.
            dup = self.assert_refusal(run_production(repo, "create", "demo"), "create", "record_exists")
            self.assertEqual(dup["control_root"], str(repo.resolve()))
            self.assertNotIn("start_path", dup)
            bad = self.assert_refusal(run_production(repo, "create", "../bad"), "create", "invalid_argument")
            self.assertEqual(bad["control_root"], str(repo.resolve()))
            # Explicit --repo success also attributes control_root even when CWD is elsewhere.
            with tempfile.TemporaryDirectory() as tmp2:
                other = Path(tmp2)
                explicit_ok = self.assert_ok(run_production(other, "--repo", str(repo), "locate", "demo"), "locate")
                self.assertEqual(explicit_ok["control_root"], str(repo.resolve()))
                # Refusal via explicit --repo still attributes that explicit root.
                explicit_refused = self.assert_refusal(
                    run_production(other, "--repo", str(repo), "create", "demo"), "create", "record_exists"
                )
                self.assertEqual(explicit_refused["control_root"], str(repo.resolve()))
            # Repository-not-found refusal does not claim a selected root.
            with tempfile.TemporaryDirectory() as tmp3:
                outside = Path(tmp3) / "outside2"
                outside.mkdir()
                fail = self.assert_refusal(run_production(outside, "locate", "demo"), "locate", "repository_not_found")
                self.assertNotIn("control_root", fail)
                self.assertIn("start_path", fail)
                self.assertEqual(fail["start_path"], str(outside.resolve()))

    def test_archive_family_through_production_entrypoint_with_explicit_and_discovered_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["/usr/bin/git", "init", "-q", str(repo)], check=True)
            with tempfile.TemporaryDirectory() as tmp_cwd:
                other = Path(tmp_cwd)
                # Create via explicit --repo from another CWD, outside Git.
                self.assert_ok(run_production(other, "--repo", str(repo), "create", "todelete"), "create")
                self.assertTrue((repo / ".agent_state/plans/todelete").is_dir())
                # Archive via discovered root (CWD = repo).
                arch = self.assert_ok(run_production(repo, "archive", "todelete"), "archive")
                self.assertEqual(arch["control_root"], str(repo.resolve()))
                self.assertEqual(arch["paths"], [".agent_state/archives/todelete"])
                self.assertFalse((repo / ".agent_state/plans/todelete").exists())
                self.assertTrue((repo / ".agent_state/archives/todelete").is_dir())
                # Undo via explicit --repo from another CWD.
                undone = self.assert_ok(run_production(other, "--repo", str(repo), "archive", "todelete", "--undo"), "archive")
                self.assertEqual(undone["control_root"], str(repo.resolve()))
                self.assertTrue((repo / ".agent_state/plans/todelete").is_dir())
                self.assertFalse((repo / ".agent_state/archives/todelete").exists())
                # Archive again via explicit --repo.
                arch2 = self.assert_ok(run_production(other, "--repo", str(repo), "archive", "todelete"), "archive")
                self.assertEqual(arch2["control_root"], str(repo.resolve()))
                self.assertTrue((repo / ".agent_state/archives/todelete").is_dir())
                # Locate archived record via production still attributes control_root.
                located_archived = self.assert_ok(run_production(other, "--repo", str(repo), "locate", "todelete"), "locate")
                self.assertEqual(located_archived["control_root"], str(repo.resolve()))
                self.assertEqual(located_archived["location"], "archived")


if __name__ == "__main__":
    unittest.main()
