from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests/run.py"


def run_runner(*selection: str, **environment: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *selection],
        cwd=ROOT,
        env={**os.environ, **environment},
        text=True,
        capture_output=True,
        check=False,
    )


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

    def test_failing_node_test_file_fails_the_run_and_shows_its_output(self) -> None:
        result = run_runner("tests/runner_failing_node_fixture.mjs")

        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        self.assertIn("NODE-FIXTURE-FAILURE", result.stderr)
        self.assertRegex(result.stdout, r"node\s+FAILED\s+tests/runner_failing_node_fixture\.mjs")

    def test_failing_repository_check_is_reported_as_a_check(self) -> None:
        result = run_runner("tests.checks.runner_failing_fixture")

        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        self.assertIn("CHECK-FIXTURE-FAILURE", result.stderr)
        self.assertRegex(result.stdout, r"check\s+FAILED\s+tests\.checks\.runner_failing_fixture")

    def test_default_run_discovers_node_tests_and_checks(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--list"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        listed = result.stdout.splitlines()
        self.assertIn("node   tests/herdr_prompt_workaround.test.mjs", listed)
        self.assertTrue(any(line.startswith("check  tests.checks.check_") for line in listed))
        self.assertTrue(any(line.startswith("test   tests.test_") for line in listed))
        self.assertFalse(any("fixture" in line for line in listed))
