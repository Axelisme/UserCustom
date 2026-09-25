"""Fixture for tests/test_test_runner.py: one class whose cases share a job, one of them failing."""

from __future__ import annotations

import unittest


class RunnerFailingCaseFixture(unittest.TestCase):
    def test_passing_neighbour(self) -> None:
        pass

    def test_fixture_case_fails(self) -> None:
        self.fail("CASE-FIXTURE-FAILURE")
