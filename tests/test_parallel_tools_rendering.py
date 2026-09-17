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

    def render(
        self, *, width: int = 80, expanded: bool = False, scenario: str = "standard"
    ) -> list[str]:
        completed = subprocess.run(
            [
                "node",
                str(HARNESS),
                str(PI_PACKAGE),
                str(EXTENSION),
                str(ROOT),
                str(width),
                str(expanded).lower(),
                scenario,
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

        header_lines = [line for line in lines if "parallel" in line]
        self.assertEqual(len(header_lines), 1, rendered)
        for marker in ("4 calls", "sequential", "15ms", "1 failed"):
            self.assertIn(marker, header_lines[0], rendered)

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

        for input_marker, duration in (
            ("unique-read-input", "4ms"),
            ("unique-shell-input", "8ms"),
            ("unique-failed-input", "2ms"),
            ("unique-empty-input", "1ms"),
        ):
            child_line = next(line for line in lines if input_marker in line)
            self.assertIn(duration, child_line, rendered)

        output_lines = [
            line
            for line in lines
            if any(prefix in line for prefix in ("READ-L", "BASH-L", "BROKEN-L"))
        ]
        self.assertTrue(output_lines)
        self.assertTrue(all(line.startswith("      ") for line in output_lines), rendered)

    def test_narrow_collapsed_inputs_stay_on_one_visual_line(self) -> None:
        lines = self.render(width=46)
        rendered = "\n".join(lines)
        shell_lines = [line for line in lines if "unique-shell-input" in line]
        self.assertEqual(len(shell_lines), 1, rendered)
        self.assertLessEqual(len(shell_lines[0]), 46)
        self.assertIn("…", shell_lines[0])
        self.assertTrue(shell_lines[0].endswith("8ms"), shell_lines[0])

        for input_marker, duration in (
            ("unique-read-input", "4ms"),
            ("unique-shell-input", "8ms"),
            ("unique-failed-input", "2ms"),
            ("unique-empty-input", "1ms"),
        ):
            child_line = next(line for line in lines if input_marker in line)
            self.assertIn(duration, child_line, rendered)

    def test_wrapped_outputs_use_visual_line_budget_and_preview_direction(self) -> None:
        lines = self.render(width=30, scenario="wrapped-output")
        rendered = "\n".join(lines)

        read_input = next(index for index, line in enumerate(lines) if "r-wrap" in line)
        bash_input = next(index for index, line in enumerate(lines) if "b-wrap" in line)
        read_lines = [line for line in lines[read_input + 1 : bash_input] if "READ-WRAP" in line]
        bash_lines = [line for line in lines[bash_input + 1 :] if "BASH-WRAP" in line]

        self.assertEqual(len(read_lines), 5, rendered)
        self.assertEqual(len(bash_lines), 5, rendered)
        self.assertTrue(all(line.startswith("      ") for line in read_lines + bash_lines), rendered)
        for index in range(1, 6):
            self.assertIn(f"READ-WRAP-{index:02}", rendered)
        self.assertNotIn("READ-WRAP-06", rendered)
        self.assertNotIn("BASH-WRAP-07", rendered)
        for index in range(8, 13):
            self.assertIn(f"BASH-WRAP-{index:02}", rendered)

    def test_expanded_shows_complete_child_inputs_and_outputs(self) -> None:
        lines = self.render(expanded=True)
        rendered = "\n".join(lines)

        self.assertEqual(rendered.count("parallel"), 1)
        for marker in (
            "READ-L1",
            "READ-L7",
            "BASH-L1",
            "BASH-L7",
            "BROKEN-L1",
            "BROKEN-L2",
            "docs/unique-read-input.md",
            "unique-shell-input-with-a-command-that-must-not-wrap-across-visual-rows",
            "unique-failed-input",
            "unique-grep-root",
            "unique-empty-input",
        ):
            self.assertIn(marker, rendered)
        self.assertTrue(any("✗" in line and "grep" in line for line in lines), rendered)
        self.assertIn("(no output)", rendered)

    def test_expanded_mutation_inputs_are_complete(self) -> None:
        rendered = "\n".join(self.render(expanded=True, scenario="mutations"))

        for marker in (
            "docs/unique-edit-target.md",
            "unique-old-text",
            "unique-new-text",
            "docs/unique-write-target.md",
            "unique-write-content",
            "EDIT-OUTPUT",
            "WRITE-OUTPUT",
        ):
            self.assertIn(marker, rendered)


if __name__ == "__main__":
    unittest.main()
