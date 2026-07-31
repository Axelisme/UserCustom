#!/usr/bin/env python3
"""Run every test module in parallel, one subprocess per module.

`python3 -m unittest discover -s tests` still works and remains the reference
behavior; this runner exists only because that discovery is serial. Almost all
of the suite's wall time is spent launching the shipped scripts as real
subprocesses, so the work parallelizes across modules with no shared state:
each module already builds its own temporary repositories and homes.

Usage: python3 tests/run.py [module ...]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
RAN = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)


def discovered_modules() -> list[str]:
    return sorted(f"tests.{path.stem}" for path in TESTS.glob("test_*.py"))


def run_module(module: str) -> tuple[str, int, float, int, str]:
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "unittest", module],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    match = RAN.search(result.stderr)
    count = int(match.group(1)) if match else 0
    output = "".join((result.stdout, result.stderr))
    return module, result.returncode, time.monotonic() - started, count, output


def main(argv: list[str]) -> int:
    modules = argv or discovered_modules()
    if not modules:
        print("no test modules found", file=sys.stderr)
        return 2

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(len(modules), os.cpu_count() or 4)) as pool:
        results = list(pool.map(run_module, modules))

    total = 0
    failures = []
    for module, returncode, duration, count, output in sorted(
        results, key=lambda item: -item[2]
    ):
        total += count
        status = "ok" if returncode == 0 else "FAILED"
        print(f"{duration:6.1f}s  {count:4d} tests  {status:6s}  {module}")
        if returncode != 0:
            failures.append((module, output))

    for module, output in failures:
        print(f"\n{'=' * 70}\n{module}\n{'=' * 70}\n{output.rstrip()}", file=sys.stderr)

    elapsed = time.monotonic() - started
    print(f"\nRan {total} tests in {elapsed:.1f}s across {len(modules)} modules")
    print("OK" if not failures else f"FAILED ({len(failures)} modules)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
