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
SCRIPT = (
    ROOT / "home" / ".codex" / "skills" / "candidate-backlog" / "scripts" / "backlog.py"
)

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def init_repo(root: Path) -> None:
    git = ("git", "-C", str(root))
    subprocess.run([*git, "init", "-q"], check=True, env=GIT_ENV)
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True, env=GIT_ENV)
    subprocess.run([*git, "commit", "-qm", "seed"], check=True, env=GIT_ENV)


def add_worktree(root: Path, path: Path) -> None:
    git = ("git", "-C", str(root))
    subprocess.run(
        [*git, "worktree", "add", "-q", "--detach", str(path)], check=True, env=GIT_ENV
    )


def run_backlog(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def payload(done: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(done.stdout)


def items_of(body: dict[str, object]) -> list[dict[str, object]]:
    value = body["items"]
    assert isinstance(value, list)
    return value


ADD_FIELDS = [
    "--kind",
    "defect",
    "--area",
    "demo/area",
    "--source-task",
    "standalone",
    "--observation",
    "obs",
    "--evidence",
    "evid",
    "--impact",
    "impact",
    "--desired-outcome",
    "outcome",
]


def add_args(root: Path, title: str) -> list[str]:
    return ["--root", str(root), "add", "--title", title, *ADD_FIELDS]


def custom_add_args(
    root: Path,
    title: str,
    *,
    kind: str,
    areas: tuple[str, ...],
    priority_hint: str,
) -> list[str]:
    area_args = [value for area in areas for value in ("--area", area)]
    return [
        "--root",
        str(root),
        "add",
        "--title",
        title,
        "--kind",
        kind,
        *area_args,
        "--source-task",
        "standalone",
        "--observation",
        "obs",
        "--evidence",
        "evid",
        "--impact",
        "impact",
        "--desired-outcome",
        "outcome",
        "--priority-hint",
        priority_hint,
    ]


class CandidateBacklogTests(unittest.TestCase):
    def assert_ok(
        self, done: subprocess.CompletedProcess[str], operation: str
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
        body = payload(done)
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["operation"], operation)
        self.assertEqual(body["backlog_version"], 2)
        self.assertNotIn("error", body)
        return body

    def assert_refusal(
        self, done: subprocess.CompletedProcess[str], operation: str, code: str
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 1, done.stderr or done.stdout)
        body = payload(done)
        self.assertEqual(body["ok"], False)
        self.assertEqual(body["operation"], operation)
        self.assertEqual(body["backlog_version"], 2)
        error = body["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["code"], code)
        return body

    # --- version 2 projection and receipt shapes -------------------------

    def test_add_returns_only_the_compact_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            body = self.assert_ok(
                run_backlog(root, *add_args(root, "Add shape item")), "add"
            )
            self.assertEqual(
                set(body),
                {"ok", "operation", "backlog_version", "id", "status", "updated_at"},
            )
            self.assertEqual(body["status"], "inbox")
            self.assertTrue(str(body["id"]).startswith("BL-"))
            stored = self.read_meta(
                self.item_path(root, str(body["id"]), "inbox")
            )
            self.assertEqual(stored["title"], "Add shape item")
            self.assertEqual(stored["updated_at"], body["updated_at"])

    def test_all_list_details_filter_before_projection_and_order_deterministically(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            fixtures = (
                ("Zulu defect", "defect", ("zeta", "alpha"), "high"),
                ("Alpha defect", "defect", ("zeta", "alpha"), "high"),
                ("Beta idea", "product-idea", ("alpha",), "low"),
                ("Planned hidden", "defect", ("alpha", "beta"), "medium"),
            )
            added: list[dict[str, object]] = []
            for title, kind, areas, priority_hint in fixtures:
                added.append(
                    self.assert_ok(
                        run_backlog(
                            root,
                            *custom_add_args(
                                root,
                                title,
                                kind=kind,
                                areas=areas,
                                priority_hint=priority_hint,
                            ),
                        ),
                        "add",
                    )
                )
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "bind",
                    str(added[-1]["id"]),
                    "--task-id",
                    "T001",
                ),
                "bind",
            )

            def listing(detail: str) -> subprocess.CompletedProcess[str]:
                return run_backlog(
                    root,
                    "--root",
                    str(root),
                    "list",
                    "--status",
                    "inbox",
                    "--area",
                    "alpha",
                    "--detail",
                    detail,
                )

            overview = self.assert_ok(listing("overview"), "list")
            self.assertEqual(
                overview,
                {
                    "ok": True,
                    "operation": "list",
                    "backlog_version": 2,
                    "detail": "overview",
                    "count": 3,
                    "facets": {
                        "status": {"inbox": 3},
                        "area": {"alpha": 3, "zeta": 2},
                        "kind": {"defect": 2, "product-idea": 1},
                        "priority_hint": {"high": 2, "low": 1},
                    },
                },
            )

            index = self.assert_ok(listing("index"), "list")
            self.assertEqual(
                index,
                {
                    "ok": True,
                    "operation": "list",
                    "backlog_version": 2,
                    "detail": "index",
                    "count": 3,
                    "groups": [
                        {
                            "status": "inbox",
                            "area": "alpha",
                            "kind": "defect",
                            "priority_hint": "high",
                            "titles": ["Alpha defect", "Zulu defect"],
                        },
                        {
                            "status": "inbox",
                            "area": "alpha",
                            "kind": "product-idea",
                            "priority_hint": "low",
                            "titles": ["Beta idea"],
                        },
                        {
                            "status": "inbox",
                            "area": "zeta",
                            "kind": "defect",
                            "priority_hint": "high",
                            "titles": ["Alpha defect", "Zulu defect"],
                        },
                    ],
                },
            )
            self.assertEqual(payload(listing("index")), index)

            summary = self.assert_ok(listing("summary"), "list")
            self.assertEqual(
                set(summary),
                {"ok", "operation", "backlog_version", "detail", "items"},
            )
            self.assertEqual(summary["detail"], "summary")
            summary_items = items_of(summary)
            self.assertEqual(
                [item["id"] for item in summary_items],
                sorted(item["id"] for item in summary_items),
            )
            for item in summary_items:
                self.assertEqual(
                    set(item),
                    {"id", "title", "kind", "area", "status", "priority_hint"},
                )
            self.assertEqual(payload(listing("summary")), summary)

            full = self.assert_ok(listing("full"), "list")
            self.assertEqual(
                set(full),
                {"ok", "operation", "backlog_version", "detail", "items"},
            )
            self.assertEqual(full["detail"], "full")
            self.assertEqual(
                [item["id"] for item in items_of(full)],
                [item["id"] for item in summary_items],
            )
            for item in items_of(full):
                self.assertEqual(
                    set(item),
                    {
                        "id",
                        "created_at",
                        "updated_at",
                        "status",
                        "kind",
                        "area",
                        "priority_hint",
                        "source_task",
                        "title",
                        "observation",
                        "evidence",
                        "impact",
                        "desired_outcome",
                    },
                )

    def test_default_overview_is_bounded_and_index_is_half_summary_size(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            for number in range(41):
                self.assert_ok(
                    run_backlog(root, *add_args(root, f"Representative item {number:02d}")),
                    "add",
                )
            command = ("--root", str(root), "list")
            overview_done = run_backlog(root, *command)
            overview = self.assert_ok(overview_done, "list")
            self.assertEqual(overview["detail"], "overview")
            self.assertEqual(overview["count"], 41)
            self.assertLess(len(overview_done.stdout.encode("utf-8")), 2048)

            index_done = run_backlog(root, *command, "--detail", "index")
            summary_done = run_backlog(root, *command, "--detail", "summary")
            self.assert_ok(index_done, "list")
            self.assert_ok(summary_done, "list")
            self.assertLessEqual(
                len(index_done.stdout.encode("utf-8")) * 2,
                len(summary_done.stdout.encode("utf-8")),
            )

    def test_bind_and_close_return_only_transition_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            added = self.assert_ok(
                run_backlog(root, *add_args(root, "Bind close shape item")), "add"
            )
            item_id = str(added["id"])
            bound = self.assert_ok(
                run_backlog(
                    root, "--root", str(root), "bind", item_id, "--task-id", "T001"
                ),
                "bind",
            )
            self.assertEqual(
                set(bound),
                {
                    "ok",
                    "operation",
                    "backlog_version",
                    "id",
                    "status",
                    "updated_at",
                    "planned_task",
                },
            )
            self.assertEqual(bound["status"], "planned")
            self.assertEqual(bound["planned_task"], "T001")
            planned = self.read_meta(self.item_path(root, item_id, "planned"))
            self.assertEqual(planned["planned_task"], "T001")
            self.assertEqual(planned["updated_at"], bound["updated_at"])

            closed = self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "close",
                    item_id,
                    "--resolution",
                    "implemented",
                    "--task-id",
                    "T001",
                    "--commit",
                    "deadbeef",
                    "--validation",
                    "ran tests",
                ),
                "close",
            )
            self.assertEqual(
                set(closed),
                {
                    "ok",
                    "operation",
                    "backlog_version",
                    "id",
                    "status",
                    "updated_at",
                    "resolution",
                },
            )
            self.assertEqual(closed["status"], "resolved")
            self.assertEqual(closed["resolution"], "implemented")
            resolved = self.read_meta(self.item_path(root, item_id, "resolved"))
            self.assertEqual(resolved["resolution"], "implemented")
            self.assertEqual(resolved["updated_at"], closed["updated_at"])

    def test_standalone_full_flag_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            done = run_backlog(root, "--root", str(root), "list", "--full")
            self.assertEqual(done.returncode, 2)
            self.assertEqual(done.stdout, "")
            self.assertIn("unrecognized arguments: --full", done.stderr)

    # --- exit codes -------------------------------------------------------

    def test_exit_code_is_zero_on_success_and_one_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            ok = run_backlog(root, *add_args(root, "Exit code item"))
            self.assertEqual(ok.returncode, 0)
            failure = run_backlog(
                root, "--root", str(root), "bind", "nonexistent", "--task-id", "T001"
            )
            self.assertEqual(failure.returncode, 1)

    # --- error taxonomy -----------------------------------------------

    def test_duplicate_title_carries_existing_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            first = self.assert_ok(
                run_backlog(root, *add_args(root, "Duplicate title item")), "add"
            )
            body = self.assert_refusal(
                run_backlog(root, *add_args(root, "Duplicate title item")),
                "add",
                "duplicate_title",
            )
            error = body["error"]
            assert isinstance(error, dict)
            self.assertEqual(error["existing_id"], first["id"])

    def test_item_missing_on_unknown_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            self.assert_refusal(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "bind",
                    "BL-20260101T000000000000Z-ghost",
                    "--task-id",
                    "T001",
                ),
                "bind",
                "item_missing",
            )

    def test_invalid_transition_on_bind_from_non_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            added = self.assert_ok(
                run_backlog(root, *add_args(root, "Non inbox bind item")), "add"
            )
            item_id = str(added["id"])
            self.assert_ok(
                run_backlog(
                    root, "--root", str(root), "bind", item_id, "--task-id", "T001"
                ),
                "bind",
            )
            self.assert_refusal(
                run_backlog(
                    root, "--root", str(root), "bind", item_id, "--task-id", "T002"
                ),
                "bind",
                "invalid_transition",
            )

    def test_invalid_argument_on_bad_task_id_format(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            added = self.assert_ok(
                run_backlog(root, *add_args(root, "Bad task id item")), "add"
            )
            item_id = str(added["id"])
            self.assert_refusal(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "bind",
                    item_id,
                    "--task-id",
                    "not a valid id",
                ),
                "bind",
                "invalid_argument",
            )

    def test_corrupt_item_when_same_id_exists_in_two_status_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            added = self.assert_ok(
                run_backlog(root, *add_args(root, "Corrupt item")), "add"
            )
            item_id = str(added["id"])
            backlog = root / ".agent_state" / "backlog"
            inbox_file = backlog / "inbox" / f"{item_id}.md"
            text = inbox_file.read_text(encoding="utf-8")
            # Craft a second copy that claims the same id under "planned", with its
            # metadata status field updated to match the directory it lives in so the
            # per-file status/path check passes and only the cross-directory id
            # collision (D4) is left to trip the corrupt_item guard.
            planted = text.replace('"status":"inbox"', '"status":"planned"', 1)
            (backlog / "planned").mkdir(parents=True, exist_ok=True)
            (backlog / "planned" / f"{item_id}.md").write_text(
                planted, encoding="utf-8"
            )
            self.assert_refusal(
                run_backlog(root, "--root", str(root), "list"), "list", "corrupt_item"
            )

    # --- full lifecycle -----------------------------------------------

    def test_lifecycle_add_bind_close_implemented_lands_in_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            added = self.assert_ok(
                run_backlog(root, *add_args(root, "Implemented lifecycle item")), "add"
            )
            item_id = str(added["id"])
            backlog = root / ".agent_state" / "backlog"
            self.assertTrue((backlog / "inbox" / f"{item_id}.md").exists())
            self.assert_ok(
                run_backlog(
                    root, "--root", str(root), "bind", item_id, "--task-id", "T001"
                ),
                "bind",
            )
            self.assertTrue((backlog / "planned" / f"{item_id}.md").exists())
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "close",
                    item_id,
                    "--resolution",
                    "implemented",
                    "--task-id",
                    "T001",
                    "--commit",
                    "deadbeef",
                    "--validation",
                    "ran tests",
                ),
                "close",
            )
            self.assertTrue((backlog / "resolved" / f"{item_id}.md").exists())
            self.assertFalse((backlog / "planned" / f"{item_id}.md").exists())

    def test_lifecycle_add_close_declined_lands_in_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            added = self.assert_ok(
                run_backlog(root, *add_args(root, "Declined lifecycle item")), "add"
            )
            item_id = str(added["id"])
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "close",
                    item_id,
                    "--resolution",
                    "declined",
                ),
                "close",
            )
            backlog = root / ".agent_state" / "backlog"
            self.assertTrue((backlog / "closed" / f"{item_id}.md").exists())
            self.assertFalse((backlog / "inbox" / f"{item_id}.md").exists())

    # --- root resolution (D5) -----------------------------------------

    def test_root_pointing_at_linked_worktree_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "main"
            root.mkdir()
            init_repo(root)
            linked = base / "linked"
            add_worktree(root, linked)
            body = self.assert_refusal(
                run_backlog(base, "--root", str(linked), "list"),
                "list",
                "invalid_argument",
            )
            error = body["error"]
            assert isinstance(error, dict)
            self.assertIn("primary checkout", str(error["message"]))

    def test_missing_root_is_derived_from_cwd_even_inside_a_linked_worktree(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "main"
            root.mkdir()
            init_repo(root)
            linked = base / "linked"
            add_worktree(root, linked)

            added = self.assert_ok(
                run_backlog(root, "add", "--title", "Derived root item", *ADD_FIELDS),
                "add",
            )
            item_id = str(added["id"])
            self.assertTrue(
                (root / ".agent_state" / "backlog" / "inbox" / f"{item_id}.md").exists()
            )
            self.assertFalse((linked / ".agent_state").exists())

            listed = self.assert_ok(
                run_backlog(linked, "list", "--detail", "summary"), "list"
            )
            ids = [item["id"] for item in items_of(listed)]
            self.assertIn(item_id, ids)

    def test_missing_root_outside_a_git_repository_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary)
            self.assert_refusal(
                run_backlog(outside, "list"), "list", "invalid_argument"
            )


    # --- append-evidence ------------------------------------------------

    def add_item(self, root: Path, title: str) -> str:
        added = self.assert_ok(run_backlog(root, *add_args(root, title)), "add")
        return str(added["id"])

    def read_meta(self, path: Path) -> dict[str, object]:
        match = re.match(
            r"\A<!-- backlog-metadata\n(.+?)\n-->\n",
            path.read_text(encoding="utf-8"),
            re.DOTALL,
        )
        assert match is not None
        return json.loads(match.group(1))

    def item_path(self, root: Path, item_id: str, status: str) -> Path:
        return root / ".agent_state" / "backlog" / status / f"{item_id}.md"

    def test_appends_utc_dated_paragraph_to_inbox_and_planned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            item_id = self.add_item(root, "Append inbox item")
            body = self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "newer observation",
                ),
                "append-evidence",
            )
            self.assertEqual(
                set(body),
                {"ok", "operation", "backlog_version", "id", "status", "updated_at"},
            )
            self.assertEqual(body["status"], "inbox")
            meta = self.read_meta(self.item_path(root, item_id, "inbox"))
            self.assertEqual(meta["updated_at"], body["updated_at"])
            evidence = str(meta["evidence"])
            self.assertRegex(
                evidence,
                r"\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z\] newer observation$",
            )
            self.assert_ok(
                run_backlog(root, "--root", str(root), "bind", item_id,
                            "--task-id", "T001"),
                "bind",
            )
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "planned stage note",
                ),
                "append-evidence",
            )
            meta = self.read_meta(self.item_path(root, item_id, "planned"))
            self.assertTrue(str(meta["evidence"]).endswith("planned stage note"))

    def test_append_preserves_original_evidence_and_task_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            item_id = self.add_item(root, "Preserve fields on append")
            path = self.item_path(root, item_id, "inbox")
            before = dict(self.read_meta(path))
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "append-only note with	interior spacing",
                ),
                "append-evidence",
            )
            after = dict(self.read_meta(path))
            self.assertNotEqual(before["updated_at"], after["updated_at"])
            for key in (
                "id",
                "source_task",
                "status",
                "kind",
                "observation",
                "impact",
                "desired_outcome",
            ):
                self.assertEqual(before[key], after[key], key)
            evidence = str(after["evidence"])
            separator = evidence.index("\n\n[")
            self.assertEqual(evidence[:separator], before["evidence"])

    def test_append_trims_only_leading_trailing_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            item_id = self.add_item(root, "Trim rule on append")
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "  MiXeD case Ｕｎｉｃｏｄｅ and   inner  gaps  ",
                ),
                "append-evidence",
            )
            meta = self.read_meta(self.item_path(root, item_id, "inbox"))
            self.assertTrue(
                str(meta["evidence"]).endswith("MiXeD case Ｕｎｉｃｏｄｅ and   inner  gaps")
            )

    def test_append_requires_existing_item_and_non_empty_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            self.assert_refusal(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    "BL-20260101T000000000000Z-ghost",
                    "--evidence",
                    "x",
                ),
                "append-evidence",
                "item_missing",
            )
            item_id = self.add_item(root, "Empty evidence refusal")
            path = self.item_path(root, item_id, "inbox")
            before = path.read_text(encoding="utf-8")
            for bad in ("", "   \n\t "):
                self.assert_refusal(
                    run_backlog(
                        root,
                        "--root",
                        str(root),
                        "append-evidence",
                        item_id,
                        "--evidence",
                        bad,
                    ),
                    "append-evidence",
                    "invalid_argument",
                )
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_append_refuses_resolved_and_closed_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            resolved_id = self.add_item(root, "Resolved append target")
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "close",
                    resolved_id,
                    "--resolution",
                    "implemented",
                    "--task-id",
                    "T001",
                    "--commit",
                    "deadbeef",
                    "--validation",
                    "ran tests",
                ),
                "close",
            )
            closed_id = self.add_item(root, "Closed append target")
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "close",
                    closed_id,
                    "--resolution",
                    "declined",
                ),
                "close",
            )
            frozen: dict[Path, str] = {}
            for item_id in (resolved_id, closed_id):
                done = run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "late note",
                )
                self.assert_refusal(done, "append-evidence", "invalid_transition")
                for status in ("resolved", "closed"):
                    path = self.item_path(root, item_id, status)
                    if path.exists():
                        frozen[path] = path.read_text(encoding="utf-8")
            self.assertEqual(len(frozen), 2)
            for path, text in frozen.items():
                self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_append_retry_refused_only_on_exact_trimmed_latest_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            item_id = self.add_item(root, "Retry refusal target")
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "same text",
                ),
                "append-evidence",
            )
            self.assert_refusal(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "  same text  ",
                ),
                "append-evidence",
                "duplicate_evidence",
            )
            # Different interior whitespace, case, or Unicode is not a retry.
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "same  text",
                ),
                "append-evidence",
            )
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "Same Text",
                ),
                "append-evidence",
            )
            # Only the latest appended paragraph participates in the comparison.
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "latest note",
                ),
                "append-evidence",
            )
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "same text",
                ),
                "append-evidence",
            )

    def test_append_retry_refuses_identical_multiline_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            item_id = self.add_item(root, "Multiline retry refusal target")
            evidence = "first line\nsecond line"
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    evidence,
                ),
                "append-evidence",
            )
            path = self.item_path(root, item_id, "inbox")
            before_retry = path.read_text(encoding="utf-8")
            self.assert_refusal(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    evidence,
                ),
                "append-evidence",
                "duplicate_evidence",
            )
            self.assertEqual(path.read_text(encoding="utf-8"), before_retry)

    def test_append_retry_refused_when_repeated_text_embeds_marker_shaped_line(
        self,
    ) -> None:
        # A repeated text carrying an embedded timestamp-shaped line must be
        # compared as one whole suffix against the generated paragraph, not
        # split at the interior marker into a non-matching tail.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            item_id = self.add_item(root, "Embedded marker retry target")
            evidence = "first line\n\n[2026-01-02T03:04:05Z] embedded line"
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    evidence,
                ),
                "append-evidence",
            )
            path = self.item_path(root, item_id, "inbox")
            before_retry = path.read_text(encoding="utf-8")
            self.assert_refusal(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    evidence,
                ),
                "append-evidence",
                "duplicate_evidence",
            )
            self.assertEqual(path.read_text(encoding="utf-8"), before_retry)

    def test_append_ignores_timestamp_shaped_lines_in_original_evidence(self) -> None:
        # Original (non-appended) evidence may legitimately contain
        # timestamp-shaped lines; they are not append boundaries, so a first
        # append whose text coincides with one of them is not a retry.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            added = self.assert_ok(
                run_backlog(
                    root,
                    *add_args(root, "Coincidental stamp evidence item"),
                    "--evidence",
                    "[2026-01-02T03:04:05Z] coincidental\n\n"
                    "[2026-01-02T03:04:06Z] second stamped line",
                ),
                "add",
            )
            item_id = str(added["id"])
            path = self.item_path(root, item_id, "inbox")
            original = dict(self.read_meta(path))["evidence"]
            for text in ("coincidental", "second stamped line"):
                self.assert_ok(
                    run_backlog(
                        root,
                        "--root",
                        str(root),
                        "append-evidence",
                        item_id,
                        "--evidence",
                        text,
                    ),
                    "append-evidence",
                )
            meta = self.read_meta(path)
            self.assertTrue(str(meta["evidence"]).startswith(str(original)))

    def test_append_after_paragraph_with_interior_marker_line_compares_whole_suffix(
        self,
    ) -> None:
        # An interior timestamp-shaped line inside the latest appended paragraph
        # does not shorten it: only the full suffix participates in the exact
        # comparison, so a text equal to just that interior line appends.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            item_id = self.add_item(root, "Interior marker boundary target")
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "outer note\n\n[2026-01-02T03:04:05Z] inner stamped line",
                ),
                "append-evidence",
            )
            path = self.item_path(root, item_id, "inbox")
            earlier = dict(self.read_meta(path))["evidence"]
            # The bare interior line alone differs from the whole latest suffix.
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "[2026-01-02T03:04:05Z] inner stamped line",
                ),
                "append-evidence",
            )
            meta = self.read_meta(path)
            evidence = str(meta["evidence"])
            self.assertTrue(evidence.startswith(f"{earlier}\n\n"))
            self.assertTrue(evidence.endswith("[2026-01-02T03:04:05Z] inner stamped line"))
            self.assertIn(
                "\n\n[2026-01-02T03:04:05Z] inner stamped line\n\n", evidence
            )
            # And repeating the now-latest full suffix is still refused.
            self.assert_refusal(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "[2026-01-02T03:04:05Z] inner stamped line",
                ),
                "append-evidence",
                "duplicate_evidence",
            )

    def test_append_keeps_summary_listing_unchanged_and_full_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            item_id = self.add_item(root, "List shape after append")
            self.assert_ok(
                run_backlog(
                    root,
                    "--root",
                    str(root),
                    "append-evidence",
                    item_id,
                    "--evidence",
                    "listed evidence",
                ),
                "append-evidence",
            )
            summary = self.assert_ok(
                run_backlog(
                    root, "--root", str(root), "list", "--detail", "summary"
                ),
                "list",
            )
            [item] = items_of(summary)
            self.assertEqual(
                set(item), {"id", "title", "kind", "area", "status", "priority_hint"}
            )
            full = self.assert_ok(
                run_backlog(root, "--root", str(root), "list", "--detail", "full"),
                "list",
            )
            [detailed] = items_of(full)
            evidence = detailed["evidence"]
            assert isinstance(evidence, str)
            self.assertIn("listed evidence", evidence)
            rendered = self.item_path(root, item_id, "inbox").read_text(encoding="utf-8")
            self.assertIn("listed evidence", rendered)


if __name__ == "__main__":
    unittest.main()
