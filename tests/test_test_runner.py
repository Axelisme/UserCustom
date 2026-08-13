from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests/run.py"


class TestRunnerTests(unittest.TestCase):
    def test_independent_test_cases_run_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = {
                **os.environ,
                "TEST_RUNNER_BARRIER": temporary,
            }
            result = subprocess.run(
                [sys.executable, str(RUNNER), "tests.runner_parallel_fixture"],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(
            result.returncode,
            0,
            msg="".join((result.stdout, result.stderr)),
        )
        self.assertIn("Ran 2 tests", result.stdout)
