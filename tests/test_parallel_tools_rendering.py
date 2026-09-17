"""Observable rendering contract for the parallel Pi extension."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "home/.pi/agent/extensions/parallel-tools.ts"
HARNESS = ROOT / "tests/parallel_tools_render_harness.mjs"
PI_PACKAGE = Path("/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js")


class ParallelToolsRenderingTests(unittest.TestCase):
    maxDiff = None

    def render(self, *, width: int = 80, expanded: bool = False) -> list[str]:
        completed = subprocess.run(
            [
                "node",
                str(HARNESS),
                str(PI_PACKAGE),
                str(EXTENSION),
                str(ROOT),
                str(width),
                str(expanded).lower(),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)["lines"]

    def test_collapsed_pairs_inputs_with_bounded_actual_output(self) -> None:
        lines = self.render()
        rendered = "\n".join(lines)

        self.assertEqual(rendered.count("parallel"), 1)
        for input_marker in (
            "unique-read-input",
            "unique-shell-input",
            "unique-failed-input",
            "unique-empty-input",
        ):
            self.assertEqual(rendered.count(input_marker), 1, rendered)

        self.assertLess(rendered.index("unique-read-input"), rendered.index("READ-L1"))
        self.assertLess(rendered.index("READ-L5"), rendered.index("unique-shell-input"))
        self.assertLess(rendered.index("unique-shell-input"), rendered.index("BASH-L3"))
        self.assertLess(rendered.index("BASH-L7"), rendered.index("unique-failed-input"))
        self.assertLess(rendered.index("unique-failed-input"), rendered.index("BROKEN-L1"))
        self.assertLess(rendered.index("BROKEN-L2"), rendered.index("unique-empty-input"))

        for marker in ("READ-L1", "READ-L2", "READ-L3", "READ-L4", "READ-L5"):
            self.assertIn(marker, rendered)
        for marker in ("READ-L6", "READ-L7", "BASH-L1", "BASH-L2"):
            self.assertNotIn(marker, rendered)
        for marker in ("BASH-L3", "BASH-L4", "BASH-L5", "BASH-L6", "BASH-L7"):
            self.assertIn(marker, rendered)
        self.assertIn("(no output)", rendered)

        output_lines = [
            line
            for line in lines
            if any(prefix in line for prefix in ("READ-L", "BASH-L", "BROKEN-L"))
        ]
        self.assertTrue(output_lines)
        self.assertTrue(all(line.startswith("      ") for line in output_lines), rendered)

    def test_narrow_collapsed_inputs_stay_on_one_visual_line(self) -> None:
        lines = self.render(width=46)
        shell_lines = [line for line in lines if "unique-shell-input" in line]
        self.assertEqual(len(shell_lines), 1, "\n".join(lines))
        self.assertLessEqual(len(shell_lines[0]), 46)
        self.assertTrue(shell_lines[0].endswith("…"), shell_lines[0])

    def test_expanded_shows_complete_child_inputs_and_outputs(self) -> None:
        rendered = "\n".join(self.render(expanded=True))

        self.assertEqual(rendered.count("parallel"), 1)
        for marker in (
            "READ-L1",
            "READ-L7",
            "BASH-L1",
            "BASH-L7",
            "BROKEN-L1",
            "BROKEN-L2",
            "unique-shell-input-with-a-command-that-must-not-wrap-across-visual-rows",
        ):
            self.assertIn(marker, rendered)
        self.assertIn("(no output)", rendered)


if __name__ == "__main__":
    unittest.main()
