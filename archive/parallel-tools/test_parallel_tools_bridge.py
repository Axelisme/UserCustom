"""Observable dispatch contract for tools other extensions publish for batching."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "home/.pi/agent/extensions/parallel-tools.ts"
HARNESS = ROOT / "tests/parallel_tools_bridge_harness.mjs"
PI_PACKAGE = Path("/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js")

#: Each bridged fake sleeps this long, so a serialised batch takes about twice
#: one call and a concurrent batch takes about one.
SLEEP_MS = 60


class ParallelToolsBridgeTests(unittest.TestCase):
    maxDiff = None

    def run_batch(self, scenario: str) -> dict:
        completed = subprocess.run(
            [
                "node",
                str(HARNESS),
                str(PI_PACKAGE),
                str(EXTENSION),
                str(ROOT),
                scenario,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def test_a_published_tool_is_dispatchable_at_all(self) -> None:
        result = self.run_batch("concurrent")
        self.assertEqual(result["names"], ["fake_reader", "fake_reader_two"])
        self.assertEqual(result["ok"], [True, True])
        self.assertEqual(result["order"], ["fake_reader", "fake_reader_two"])

    def test_a_sequential_entry_orders_the_whole_batch(self) -> None:
        result = self.run_batch("sequential")
        self.assertEqual(result["mode"], "sequential")
        self.assertEqual(result["order"], ["fake_reader", "fake_mutator"])
        # Reported mode is not enough: prove the calls really did not overlap.
        self.assertGreaterEqual(result["elapsedMs"], 2 * SLEEP_MS)

    def test_without_a_sequential_entry_the_batch_still_runs_concurrently(self) -> None:
        result = self.run_batch("concurrent")
        self.assertEqual(result["mode"], "concurrent")
        self.assertLess(
            result["elapsedMs"],
            2 * SLEEP_MS,
            "a batch of published reads must not be serialised by their mere presence",
        )

    def test_an_unpublished_name_reports_what_was_actually_available(self) -> None:
        result = self.run_batch("unknown")
        self.assertEqual(result["ok"], [False])
        self.assertIn('unknown tool "not_published"', result["text"])
        # The built-ins and every published name, so the message never claims a
        # tool that is not loaded nor hides one that is.
        for name in ("read", "bash", "fake_mutator", "fake_reader", "fake_reader_two"):
            self.assertIn(name, result["text"])
        self.assertNotIn("not_published;", result["text"].split("allowed:")[1])

    def test_a_published_tool_cannot_shadow_a_built_in(self) -> None:
        result = self.run_batch("no-shadow")
        self.assertEqual(result["ok"], [True])
        # The fake records every call it serves; an empty log means Pi's own read
        # answered, which is what a batch naming "read" has to reach.
        self.assertEqual(result["order"], [])
        self.assertIn("UserCustom", result["text"])


if __name__ == "__main__":
    unittest.main()
