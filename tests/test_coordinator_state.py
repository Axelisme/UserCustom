from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from tests import _support as support
except ImportError:  # Direct test-file execution keeps tests/ on sys.path.
    import _support as support

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "coordinator" / "scripts" / "state.py"
STATE = support.load_script(SCRIPT)


class StateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(self.enterContext(tempfile.TemporaryDirectory())) / "repo"
        self.state = self.repo / ".agent_state"
        for name in ("plans", "maps", "archives", "worktrees"):
            (self.state / name).mkdir(parents=True)
        self.registered: list[Path] = []

    def run_state(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return support.run_main(
            STATE.main,
            ["state.py", str(self.repo), *extra],
            worktrees=lambda repo: list(self.registered),
        )

    def register(self, relative: str) -> Path:
        path = self.state / "worktrees" / relative
        path.mkdir(parents=True)
        (path / "file.txt").write_text("x", encoding="utf-8")
        self.registered.append(path)
        return path

    def test_defined_layout_is_clean(self) -> None:
        self.register("t1/integration")

        result = self.run_state()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.strip(), "state: clean")

    def test_loose_file_and_unknown_directory_are_misplaced(self) -> None:
        (self.state / "handoff.md").write_text("x", encoding="utf-8")
        (self.state / "scratch").mkdir()

        result = self.run_state()

        self.assertIn(f"misplaced: {self.state / 'handoff.md'}", result.stdout)
        self.assertIn(f"misplaced: {self.state / 'scratch'}", result.stdout)
        self.assertIn("state: 2 findings", result.stdout)

    def test_allowed_name_is_not_misplaced(self) -> None:
        (self.state / "backlog").mkdir()

        result = self.run_state("--allow", "backlog")

        self.assertEqual(result.stdout.strip(), "state: clean")

    def test_unregistered_directory_under_worktrees_is_residue(self) -> None:
        self.register("t1/integration")
        (self.state / "worktrees" / "t1" / "lanes" / "01-old").mkdir(parents=True)
        (self.state / "worktrees" / "spike").mkdir()

        result = self.run_state()

        self.assertIn(f"residue: {self.state / 'worktrees' / 't1' / 'lanes'}", result.stdout)
        self.assertIn(f"residue: {self.state / 'worktrees' / 'spike'}", result.stdout)
        self.assertNotIn("01-old", result.stdout)
        self.assertIn("state: 2 findings", result.stdout)

    def test_scratch_of_a_done_ticket_is_listed(self) -> None:
        task = self.state / "plans" / "t1"
        (task / "tickets").mkdir(parents=True)
        (task / "tickets" / "01-add.md").write_text("**Status:** done\n", encoding="utf-8")
        (task / "tickets" / "02-mul.md").write_text("**Status:** doing\n", encoding="utf-8")
        (task / "scratch" / "01-add").mkdir(parents=True)
        (task / "scratch" / "02-mul").mkdir(parents=True)

        result = self.run_state()

        self.assertIn(f"collected: {task / 'scratch' / '01-add'}", result.stdout)
        self.assertNotIn("02-mul", result.stdout)

    def test_process_without_a_repository_argument_exits_2(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], text=True, capture_output=True, check=False
        )

        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
