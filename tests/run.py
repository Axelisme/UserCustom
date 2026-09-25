#!/usr/bin/env python3
"""Run every test in parallel, one isolated subprocess per case or node test file.

`python3 -m unittest discover -s tests` still works for the Python behavior
tests and remains their reference behavior; this runner exists because that
discovery is serial and covers neither node tests nor repository checks.
Almost all of the suite's wall time is spent launching shipped scripts against
temporary repositories and homes, so independent jobs are scheduled across
CPU cores.

Three kinds of test are discovered and reported separately:

  test   tests/test_*.py          behavior tests, one job per unittest case
  check  tests/checks/check_*.py  repository-data checks, one job per case
  node   tests/*.test.mjs         node:test files, one job per file

Usage: python3 tests/run.py [--list] [selection ...]

A selection is a dotted unittest name (`tests.checks.*` names are checks) or a
path to a `.mjs` file. Without a selection every kind is discovered.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import unittest
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
CHECKS = TESTS / "checks"
KINDS = ("test", "check", "node")


@dataclass(frozen=True)
class Job:
    kind: str
    group: str
    name: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    job: Job
    returncode: int
    duration: float
    skipped: int
    output: str


def discovered_selection() -> list[str]:
    tests = sorted(f"tests.{path.stem}" for path in TESTS.glob("test_*.py"))
    checks = sorted(f"tests.checks.{path.stem}" for path in CHECKS.glob("check_*.py"))
    node = sorted(str(path.relative_to(ROOT)) for path in TESTS.glob("*.test.mjs"))
    return [*tests, *checks, *node]


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


def jobs_for(selection: list[str]) -> list[Job]:
    node_files = [name for name in selection if name.endswith(".mjs")]
    modules = [name for name in selection if not name.endswith(".mjs")]
    jobs = [Job("node", name, name, ("node", "--test", name)) for name in node_files]
    if modules:
        sys.path.insert(0, str(ROOT))
        for test in flatten(unittest.defaultTestLoader.loadTestsFromNames(modules)):
            module = module_for(test.id(), modules)
            kind = "check" if module.startswith("tests.checks.") else "test"
            command = (sys.executable, "-m", "unittest", test.id())
            jobs.append(Job(kind, module, test.id(), command))
    return jobs


def skipped_count(job: Job, output: str) -> int:
    pattern = r"^\S*\s*skipped (\d+)$" if job.kind == "node" else r"skipped=(\d+)"
    return sum(int(count) for count in re.findall(pattern, output, re.MULTILINE))


def run_job(job: Job) -> Result:
    started = time.monotonic()
    result = subprocess.run(
        job.command,
        cwd=ROOT,
        # Node tests load the Pi SDK, which must never reach the network from a test.
        env={**os.environ, "PI_OFFLINE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    output = "".join((result.stdout, result.stderr))
    return Result(job, result.returncode, time.monotonic() - started, skipped_count(job, output), output)


def main(argv: list[str]) -> int:
    listing = "--list" in argv
    selection = [argument for argument in argv if argument != "--list"] or discovered_selection()
    if not selection:
        print("no tests found", file=sys.stderr)
        return 2

    started = time.monotonic()
    jobs = jobs_for(selection)
    if not jobs:
        print("no test cases found", file=sys.stderr)
        return 2
    if listing:
        groups = sorted({(KINDS.index(job.kind), job.kind, job.group) for job in jobs})
        for _order, kind, group in groups:
            print(f"{kind:6s} {group}")
        return 0

    with ThreadPoolExecutor(max_workers=min(len(jobs), os.cpu_count() or 4)) as pool:
        results = list(pool.map(run_job, jobs))

    summaries: dict[tuple[str, str], list[Result]] = defaultdict(list)
    for result in results:
        summaries[(result.job.kind, result.job.group)].append(result)

    for (kind, group), members in sorted(
        summaries.items(),
        key=lambda item: (KINDS.index(item[0][0]), -sum(result.duration for result in item[1])),
    ):
        worker_time = sum(result.duration for result in members)
        status = "ok" if all(result.returncode == 0 for result in members) else "FAILED"
        skipped = sum(result.skipped for result in members)
        note = f"  ({skipped} skipped)" if skipped else ""
        print(
            f"{worker_time:6.1f} worker-s  {len(members):4d} tests  "
            f"{kind:5s}  {status:6s}  {group}{note}"
        )

    failures = [result for result in results if result.returncode != 0]
    for result in failures:
        header = f"[{result.job.kind}] {result.job.name}"
        print(f"\n{'=' * 70}\n{header}\n{'=' * 70}\n{result.output.rstrip()}", file=sys.stderr)

    elapsed = time.monotonic() - started
    counts = ", ".join(
        f"{sum(result.job.kind == kind for result in results)} {kind}"
        for kind in KINDS
        if any(result.job.kind == kind for result in results)
    )
    print(f"\nRan {len(results)} tests ({counts}) in {elapsed:.1f}s across {len(summaries)} groups")
    print("OK" if not failures else f"FAILED ({len(failures)} tests)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
