"""Fixture for tests/test_test_runner.py: a repository check that always fails."""

from __future__ import annotations

import unittest


class RunnerFailingCheckFixture(unittest.TestCase):
    def test_fixture_check_fails(self) -> None:
        self.fail("CHECK-FIXTURE-FAILURE")
