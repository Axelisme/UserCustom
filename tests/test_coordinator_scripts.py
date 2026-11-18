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
SCRIPTS = ROOT / "home" / ".codex" / "skills" / "coordinator" / "scripts"
CHECK = support.load_script(SCRIPTS / "check.py")
PATROL = support.load_script(SCRIPTS / "patrol.py")


def write_map(
    map_dir: Path,
    task_lines: list[str],
    *,
    roles: tuple[str, ...] = ("Coordinator: co", "Designer: de"),
    follow_ups: str = "",
    extra: str = "",
) -> None:
    (map_dir / "decisions").mkdir(parents=True)
    tasks = "\n".join([*roles, *task_lines])
    (map_dir / "MAP.md").write_text(
        "## Destination\n\nd\n\n## Staircase\n\ns\n\n"
        f"## Tasks\n\n{tasks}\n\n"
        f"## Follow-ups\n\n{follow_ups}\n\n"
        f"## Not yet specified\n\n{extra}\n\n## Out of scope\n\n## Standing orders\n",
        encoding="utf-8",
    )


def map_line(map_dir: Path, text: str) -> int:
    """1-based number of the first MAP.md line starting with text."""
    lines = (map_dir / "MAP.md").read_text(encoding="utf-8").splitlines()
    return next(n for n, line in enumerate(lines, 1) if line.startswith(text))


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

    def test_follow_up_line_of_300_characters_suggests_nothing(self) -> None:
        write_map(self.map_dir, [task_line(1)], follow_ups="- " + "x" * 298)

        result = self.check()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("tidy suggested", result.stdout)

    def test_follow_up_line_over_300_characters_suggests_tidy(self) -> None:
        write_map(self.map_dir, [task_line(1)], follow_ups="- " + "x" * 299)
        line = map_line(self.map_dir, "- xxx")

        result = self.check()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            f"tidy suggested: MAP.md line {line} in Follow-ups is 301 characters (over 300)",
            result.stdout,
        )

    def test_sub_heading_in_the_map_suggests_tidy(self) -> None:
        write_map(self.map_dir, [task_line(1)], extra="### progress log\n\n- note")
        line = map_line(self.map_dir, "### progress log")

        result = self.check()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"tidy suggested: MAP.md line {line} is a sub-heading", result.stdout)

    def test_standing_orders_may_run_long(self) -> None:
        write_map(self.map_dir, [task_line(1)])
        with (self.map_dir / "MAP.md").open("a", encoding="utf-8") as handle:
            handle.write("\n- " + "x" * 900 + "\n")

        result = self.check()

        self.assertNotIn("tidy suggested", result.stdout)

    def test_tasks_without_a_designer_line_is_a_problem(self) -> None:
        write_map(self.map_dir, [task_line(1)], roles=("Coordinator: co",))

        result = self.check()

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "## Tasks does not start with 'Coordinator: <herdr-name>' then 'Designer: <herdr-name>'",
            result.stdout,
        )

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

    def write_question(self, name: str, tier: str | None) -> Path:
        path = self.scratch / "questions" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        head = f"Tier: {tier}\n\n" if tier else ""
        path.write_text(head + "# question\n", encoding="utf-8")
        return path

    def questions(self) -> subprocess.CompletedProcess[str]:
        return support.run_main(
            PATROL.main, ["patrol.py", str(self.map_dir), "--questions"], herdr=fake_herdr
        )

    def test_open_question_is_listed_with_its_tier(self) -> None:
        path = self.write_question("retry.md", "process")

        result = self.patrol()

        self.assertIn(f"QUESTION process {path}", result.stdout)

    def test_question_without_a_tier_is_listed_as_untiered(self) -> None:
        path = self.write_question("shape.md", None)

        result = self.patrol()

        self.assertIn(f"QUESTION untiered {path}", result.stdout)

    def test_patrol_counts_open_design_questions(self) -> None:
        self.write_question("retry.md", "process")
        self.write_question("delete-family.md", "full")
        self.write_question("seam.md", "simple")

        result = self.patrol()

        self.assertIn("design questions open: 2", result.stdout)

    def test_patrol_prints_the_maps_tidy_suggestions(self) -> None:
        with (self.map_dir / "MAP.md").open("a", encoding="utf-8") as handle:
            handle.write("\n### log\n")

        result = self.patrol()

        self.assertIn("tidy suggested: MAP.md line", result.stdout)

    def test_questions_mode_lists_only_design_questions(self) -> None:
        self.write_question("retry.md", "process")
        full = self.write_question("delete-family.md", "full")

        result = self.questions()

        self.assertEqual(result.stdout.strip(), f"full {full}")

    def test_questions_mode_names_the_designer_holding_a_question(self) -> None:
        full = self.write_question("delete-family.md", "full")
        (self.map_dir / "scratch").mkdir()
        (self.map_dir / "scratch" / "designer-de.md").write_text(f"{full}\n", encoding="utf-8")

        result = self.questions()

        self.assertEqual(result.stdout.strip(), f"full {full}  claimed by de")

    def test_questions_mode_reports_an_empty_queue(self) -> None:
        result = self.questions()

        self.assertEqual(result.stdout.strip(), "no open design questions")

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
