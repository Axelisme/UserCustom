from __future__ import annotations

import json
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
SCRIPTS = ROOT / "home" / ".codex" / "skills" / "advisor" / "scripts"
CHECK = support.load_script(SCRIPTS / "check.py")
PATROL = support.load_script(SCRIPTS / "patrol.py")


def write_map(map_dir: Path, task_lines: list[str]) -> None:
    (map_dir / "decisions").mkdir(parents=True)
    tasks = "\n".join(["Advisor: adv", *task_lines])
    (map_dir / "MAP.md").write_text(
        "## Destination\n\nd\n\n## Staircase\n\ns\n\n"
        f"## Tasks\n\n{tasks}\n\n"
        "## Not yet specified\n\n## Out of scope\n\n## Standing orders\n",
        encoding="utf-8",
    )


def task_line(n: int, state: str = "landed") -> str:
    return f"- t{n} — step {n} — Base: none — herdr: a{n} — {state}"


def write_decisions(map_dir: Path, count: int) -> None:
    for n in range(1, count + 1):
        (map_dir / "decisions" / f"{n:04d}-d{n}.md").write_text(
            "Supersedes: none\n\nbody\n", encoding="utf-8"
        )


class MapCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.map_dir = Path(self.enterContext(tempfile.TemporaryDirectory())) / "m1"

    def check(self) -> subprocess.CompletedProcess[str]:
        return support.run_main(CHECK.main, ["check.py", str(self.map_dir)])

    def test_map_at_both_limits_suggests_no_hand_off(self) -> None:
        write_map(self.map_dir, [task_line(n) for n in range(1, 10)])
        write_decisions(self.map_dir, 25)

        result = self.check()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("hand-off suggested", result.stdout)

    def test_tenth_task_suggests_hand_off(self) -> None:
        write_map(self.map_dir, [task_line(n) for n in range(1, 11)])

        result = self.check()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("hand-off suggested: 10 tasks (over 9)", result.stdout)

    def test_twenty_sixth_decision_suggests_hand_off(self) -> None:
        write_map(self.map_dir, [task_line(1)])
        write_decisions(self.map_dir, 26)

        result = self.check()

        self.assertIn("hand-off suggested: 26 decisions (over 25)", result.stdout)

    def test_process_exits_nonzero_on_a_broken_map(self) -> None:
        self.map_dir.mkdir()

        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check.py"), str(self.map_dir)],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("MAP.md is missing", result.stdout)


def fake_herdr(args: list[str]) -> str:
    if args[:2] == ["agent", "list"]:
        agent = {"name": "a1", "pane_id": "w1:p1", "agent_status": "working"}
        return json.dumps({"result": {"agents": [agent]}})
    return ""


class PatrolTests(unittest.TestCase):
    def setUp(self) -> None:
        state = Path(self.enterContext(tempfile.TemporaryDirectory())) / ".agent_state"
        self.map_dir = state / "maps" / "m1"
        write_map(self.map_dir, [task_line(1, "running")])
        self.scratch = state / "plans" / "t1" / "scratch"
        self.scratch.mkdir(parents=True)

    def write_harness(self, relative: str, lines: int) -> None:
        path = self.scratch / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n" * lines, encoding="utf-8")

    def patrol(self) -> subprocess.CompletedProcess[str]:
        return support.run_main(PATROL.main, ["patrol.py", str(self.map_dir)], herdr=fake_herdr)

    def harness_line(self, result: subprocess.CompletedProcess[str]) -> str:
        lines = [line for line in result.stdout.splitlines() if "harness" in line]
        self.assertEqual(len(lines), 1, result.stdout)
        return lines[0]

    def test_small_harness_reports_its_size_unflagged(self) -> None:
        self.write_harness("gui/drive.py", 120)

        line = self.harness_line(self.patrol())

        self.assertIn("1 py files, 120 lines", line)
        self.assertNotIn("(", line)

    def test_harness_over_300_lines_is_flagged(self) -> None:
        self.write_harness("gui/drive.py", 200)
        self.write_harness("gui/steps.py", 101)

        line = self.harness_line(self.patrol())

        self.assertIn("2 py files, 301 lines", line)
        self.assertIn("over 300 lines", line)

    def test_harness_with_own_tests_and_pyright_config_is_flagged(self) -> None:
        self.write_harness("gui/drive.py", 50)
        self.write_harness("gui/tests/test_drive.py", 10)
        (self.scratch / "gui" / "pyrightconfig.json").write_text("{}", encoding="utf-8")

        line = self.harness_line(self.patrol())

        self.assertIn("own tests", line)
        self.assertIn("own pyrightconfig", line)

    def test_scratch_without_python_reports_no_harness(self) -> None:
        (self.scratch / "gate.log").write_text("ok\n", encoding="utf-8")

        result = self.patrol()

        self.assertNotIn("harness", result.stdout)

    def test_process_without_a_map_argument_exits_2(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "patrol.py")],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
