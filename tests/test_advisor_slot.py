from __future__ import annotations

import os
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
SCRIPT = ROOT / "home" / ".codex" / "skills" / "advisor" / "scripts" / "slot.py"
SLOT = support.load_script(SCRIPT)

setUpModule = support.require_git

# Prints once it runs, then holds its slot until the test closes its stdin.
HOLD = "import sys; print('started', flush=True); sys.stdin.read()"
FOREVER = "import threading; threading.Event().wait()"


def touch(path: Path) -> list[str]:
    return [sys.executable, "-c", f"open({str(path)!r}, 'w').close()"]


class SlotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.locks = self.tmp / "locks"

    def options(self, slots: int, *extra: str) -> list[str]:
        return [
            "--locks", str(self.locks), "--slots", str(slots), "--cores", "1",
            "--min-ram-gb", "0", "--poll", "0.05", *extra,
        ]  # fmt: skip

    def slot(self, options: list[str], command: list[str], **inputs: object):
        return support.run_main(SLOT.main, ["slot.py", *options, "30", "--", *command], **inputs)

    def hold(self, options: list[str], cwd: Path | None = None) -> subprocess.Popen[str]:
        holder = subprocess.Popen(
            [sys.executable, str(SCRIPT), *options, "30", "--", sys.executable, "-c", HOLD],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        self.addCleanup(self.release, holder)
        assert holder.stdout is not None
        self.assertEqual(holder.stdout.readline(), "started\n")
        return holder

    def release(self, holder: subprocess.Popen[str]) -> None:
        assert holder.stdin is not None and holder.stdout is not None
        if not holder.stdin.closed:
            holder.stdin.close()
        holder.wait(timeout=30)
        holder.stdout.close()

    def test_command_runs_pinned_to_its_slot_and_returns_its_status(self) -> None:
        out = self.tmp / "cpus"
        script = (
            "import os, sys; "
            f"open({str(out)!r}, 'w').write(str(sorted(os.sched_getaffinity(0)))); sys.exit(3)"
        )

        result = self.slot(self.options(1), [sys.executable, "-c", script])

        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(out.read_text(), str(sorted(os.sched_getaffinity(0))[:1]))

    def test_busy_slots_turn_a_caller_away_at_its_wait_limit(self) -> None:
        self.hold(self.options(1))
        ran = self.tmp / "ran"

        result = self.slot(self.options(1, "--wait-limit", "0"), touch(ran))

        self.assertEqual(result.returncode, 75)
        self.assertIn("slot", result.stderr)
        self.assertFalse(ran.exists())

    def test_a_free_second_slot_runs_beside_a_held_one(self) -> None:
        self.hold(self.options(2))
        ran = self.tmp / "ran"

        result = self.slot(self.options(2, "--wait-limit", "0"), touch(ran))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(ran.exists())

    def test_a_waiting_caller_runs_once_the_holder_finishes(self) -> None:
        holder = self.hold(self.options(1))
        ran = self.tmp / "ran"
        waiter = subprocess.Popen(
            [sys.executable, str(SCRIPT), *self.options(1), "30", "--", *touch(ran)],
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(waiter.kill)
        assert waiter.stderr is not None
        self.addCleanup(waiter.stderr.close)

        self.assertIn("waiting", waiter.stderr.readline())
        self.assertFalse(ran.exists())
        self.release(holder)

        self.assertEqual(waiter.wait(timeout=30), 0)
        self.assertTrue(ran.exists())

    def test_low_memory_turns_a_caller_away_at_its_wait_limit(self) -> None:
        meminfo = self.tmp / "meminfo"
        meminfo.write_text("MemTotal: 16777216 kB\nMemAvailable: 1048576 kB\n", encoding="utf-8")
        ran = self.tmp / "ran"
        options = [*self.options(1, "--wait-limit", "0"), "--min-ram-gb", "2"]

        result = self.slot(options, touch(ran), meminfo=meminfo)

        self.assertEqual(result.returncode, 75)
        self.assertIn("MemAvailable", result.stderr)
        self.assertFalse(ran.exists())

    def test_a_command_past_its_timeout_is_killed(self) -> None:
        result = support.run_main(
            SLOT.main,
            ["slot.py", *self.options(1), "0.5", "--", sys.executable, "-c", FOREVER],
        )

        self.assertEqual(result.returncode, 124)

    def test_worktrees_share_the_main_checkouts_slots_by_default(self) -> None:
        main = self.tmp / "repo"
        main.mkdir()
        subprocess.run(["git", "-C", str(main), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(main), "commit", "-q", "--allow-empty", "-m", "seed"], check=True)
        worktree = self.tmp / "lane"
        subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(worktree)], check=True)
        shared = ["--slots", "1", "--cores", "1", "--min-ram-gb", "0"]
        self.hold(shared, cwd=main)

        result = support.run_main(
            SLOT.main,
            ["slot.py", *shared, "--wait-limit", "0", "30", "--", sys.executable, "-c", "pass"],
            cwd=worktree,
        )

        self.assertEqual(result.returncode, 75)
        self.assertTrue((main / ".agent_state" / "locks").is_dir())

    def test_process_without_a_command_exits_2(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "30"], text=True, capture_output=True, check=False
        )

        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
