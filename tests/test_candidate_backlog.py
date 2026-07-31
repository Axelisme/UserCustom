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
PI_SCRIPT = (
    ROOT
    / "home"
    / ".pi"
    / "agent"
    / "skills"
    / "candidate-backlog"
    / "scripts"
    / "backlog.py"
)

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def backlog_version() -> int:
    match = re.search(
        r"^BACKLOG_VERSION = (\d+)$", SCRIPT.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match is not None
    return int(match.group(1))


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


class CandidateBacklogTests(unittest.TestCase):
    def assert_ok(
        self, done: subprocess.CompletedProcess[str], operation: str
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
        body = payload(done)
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["operation"], operation)
        self.assertEqual(body["backlog_version"], backlog_version())
        self.assertNotIn("error", body)
        return body

    def assert_refusal(
        self, done: subprocess.CompletedProcess[str], operation: str, code: str
    ) -> dict[str, object]:
        self.assertEqual(done.returncode, 1, done.stderr or done.stdout)
        body = payload(done)
        self.assertEqual(body["ok"], False)
        self.assertEqual(body["operation"], operation)
        self.assertEqual(body["backlog_version"], backlog_version())
        error = body["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["code"], code)
        return body

    # --- pi runtime parity ---------------------------------------------

    def test_pi_scripts_dir_is_a_symlink_to_the_codex_owner(self) -> None:
        pi_scripts = PI_SCRIPT.parent
        self.assertTrue(pi_scripts.is_symlink(), pi_scripts)
        self.assertEqual(PI_SCRIPT.resolve(), SCRIPT.resolve())

    # --- envelope shape per command --------------------------------------

    def test_add_envelope_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            body = self.assert_ok(
                run_backlog(root, *add_args(root, "Add shape item")), "add"
            )
            self.assertEqual(body["status"], "inbox")
            self.assertTrue(str(body["id"]).startswith("BL-"))

    def test_list_envelope_shape_uses_items_array(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repo(root)
            self.assert_ok(run_backlog(root, *add_args(root, "List shape item")), "add")
            body = self.assert_ok(
                run_backlog(root, "--root", str(root), "list"), "list"
            )
            self.assertEqual(len(items_of(body)), 1)

    def test_bind_and_close_envelope_shape(self) -> None:
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
            self.assertEqual(bound["status"], "planned")
            self.assertEqual(bound["planned_task"], "T001")
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
            self.assertEqual(closed["status"], "resolved")

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

            listed = self.assert_ok(run_backlog(linked, "list"), "list")
            ids = [item["id"] for item in items_of(listed)]
            self.assertIn(item_id, ids)

    def test_missing_root_outside_a_git_repository_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary)
            self.assert_refusal(
                run_backlog(outside, "list"), "list", "invalid_argument"
            )


if __name__ == "__main__":
    unittest.main()
