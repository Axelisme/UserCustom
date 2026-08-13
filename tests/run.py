#!/usr/bin/env python3
"""Run every test case in parallel, one isolated subprocess per case.

`python3 -m unittest discover -s tests` still works and remains the reference
behavior; this runner exists only because that discovery is serial. Almost all
of the suite's wall time is spent launching shipped scripts against temporary
repositories and homes, so independent cases are scheduled across CPU cores.

Usage: python3 tests/run.py [module ...]
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent


def discovered_modules() -> list[str]:
    return sorted(f"tests.{path.stem}" for path in TESTS.glob("test_*.py"))


def flatten(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    tests: list[unittest.TestCase] = []
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            tests.extend(flatten(test))
        else:
            tests.append(test)
    return tests


def module_for(test_id: str, modules: list[str]) -> str:
    return next(
        (module for module in modules if test_id == module or test_id.startswith(f"{module}.")),
        test_id.rsplit(".", 2)[0],
    )


def run_case(job: tuple[str, str]) -> tuple[str, str, int, float, str]:
    module, test_id = job
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "unittest", test_id],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = "".join((result.stdout, result.stderr))
    return module, test_id, result.returncode, time.monotonic() - started, output


def main(argv: list[str]) -> int:
    modules = argv or discovered_modules()
    if not modules:
        print("no test modules found", file=sys.stderr)
        return 2

    started = time.monotonic()
    sys.path.insert(0, str(ROOT))
    tests = flatten(unittest.defaultTestLoader.loadTestsFromNames(modules))
    jobs = [(module_for(test.id(), modules), test.id()) for test in tests]
    if not jobs:
        print("no test cases found", file=sys.stderr)
        return 2

    with ThreadPoolExecutor(max_workers=min(len(jobs), os.cpu_count() or 4)) as pool:
        results = list(pool.map(run_case, jobs))

    summaries: dict[str, list[tuple[str, str, int, float, str]]] = defaultdict(list)
    failures = []
    for result in results:
        module, test_id, returncode, _duration, output = result
        summaries[module].append(result)
        if returncode != 0:
            failures.append((test_id, output))

    for module, module_results in sorted(
        summaries.items(), key=lambda item: -sum(result[3] for result in item[1])
    ):
        worker_time = sum(result[3] for result in module_results)
        failed = sum(result[2] != 0 for result in module_results)
        status = "ok" if not failed else "FAILED"
        print(
            f"{worker_time:6.1f} worker-s  {len(module_results):4d} tests  "
            f"{status:6s}  {module}"
        )

    for test_id, output in failures:
        print(f"\n{'=' * 70}\n{test_id}\n{'=' * 70}\n{output.rstrip()}", file=sys.stderr)

    elapsed = time.monotonic() - started
    print(f"\nRan {len(jobs)} tests in {elapsed:.1f}s across {len(summaries)} modules")
    print("OK" if not failures else f"FAILED ({len(failures)} tests)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
