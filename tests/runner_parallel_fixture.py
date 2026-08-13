from __future__ import annotations

import os
from pathlib import Path
import time
import unittest


class RunnerParallelFixture(unittest.TestCase):
    """Fixture whose cases pass only when the suite runner overlaps them."""

    def wait_for_peer(self) -> None:
        barrier = Path(os.environ["TEST_RUNNER_BARRIER"])
        barrier.mkdir(parents=True, exist_ok=True)
        (barrier / self.id()).touch()

        deadline = time.monotonic() + 5
        while len(list(barrier.iterdir())) < 2:
            if time.monotonic() >= deadline:
                self.fail("runner serialized independent test cases")
            time.sleep(0.01)

    def test_first_worker_reaches_barrier(self) -> None:
        self.wait_for_peer()

    def test_second_worker_reaches_barrier(self) -> None:
        self.wait_for_peer()
