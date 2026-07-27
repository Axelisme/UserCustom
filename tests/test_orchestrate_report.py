from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


class ReportContractTests(unittest.TestCase):
    """Black-box Contract for the unified ``report`` command.

    ``report`` merges three things that used to be separate: the retired
    ``profile report`` (per-lane span/output accounting -- now keyed by the
    lane model instead of Oracle/Implementation roles), the four cheap Git
    checks that used to live behind the retired ``admission`` gate
    (deletion / loop / mass / focus), and the ready-candidate projection
    already exposed by ``integration status``. Everything is read-only and
    derived from Git; nothing new is persisted. ``report`` always exits 0 --
    a check that comes back "refuse" is presented, never enforced.
    """

    task_id = "report-task"

    def git(
        self, cwd: Path, *args: str, check: bool = True,
        env: dict[str, str] | None = None,
    ) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, text=True, capture_output=True, check=False,
            env={**os.environ, **(env or {})},
        )
        if check and result.returncode:
            self.fail(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def cli(
        self, root: Path, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=root, text=True,
            capture_output=True, check=False, env={**os.environ, **(env or {})},
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"success was not one JSON object: {result.stdout!r}: {exc}")
        self.assertIsInstance(value, dict)
        self.assertTrue(value.get("ok"), value)
        return value

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git(self.root, "init", "-q", "-b", "main")
        self.git(self.root, "config", "user.name", "Report Test")
        self.git(self.root, "config", "user.email", "report@example.test")
        (self.root / "README").write_text("base\n", encoding="utf-8")
        self.git(self.root, "add", "README")
        self.git(
            self.root, "commit", "-q", "-m", "base",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:00:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:00:00+0000",
            },
        )
        self.base = self.git(self.root, "rev-parse", "HEAD")
        self.integration_branch = f"wave/{self.task_id}/integration"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def integration_create(self, base: str | None = None) -> dict[str, Any]:
        return self.payload(self.cli(
            self.root, "integration", "create", "--root", str(self.root),
            "--task-id", self.task_id, "--base", base or self.base,
        ))

    def lane_create(self, lane_id: str, base: str) -> Path:
        created = self.payload(self.cli(
            self.root, "lane", "create", "--root", str(self.root),
            "--task-id", self.task_id, "--lane-id", lane_id, "--base", base,
        ))
        return Path(str(created["worktree"]))

    def commit(
        self, worktree: Path, path: str, content: str, message: str, date: str,
    ) -> str:
        target = worktree / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(worktree, "add", path)
        self.git(
            worktree, "commit", "-q", "-m", message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return self.git(worktree, "rev-parse", "HEAD")

    def collect(self, lane_id: str, sha: str, date: str) -> dict[str, Any]:
        return self.payload(self.cli(
            self.root, "integration", "collect", "--root", str(self.root),
            "--task-id", self.task_id, "--lane-id", lane_id, "--sha", sha,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        ))

    def publish(self, sha: str) -> dict[str, Any]:
        return self.payload(self.cli(
            self.root, "integration", "publish", "--root", str(self.root),
            "--task-id", self.task_id, "--sha", sha,
        ))

    def status(self) -> dict[str, Any]:
        return self.payload(self.cli(
            self.root, "integration", "status", "--root", str(self.root),
            "--task-id", self.task_id,
        ))

    def report(self, base: str | None = None) -> dict[str, Any]:
        return self.payload(self.cli(
            self.root, "report", "--root", str(self.root),
            "--task-id", self.task_id, "--base", base or self.base,
        ))

    def lane_by_id(self, report: dict[str, Any], lane_id: str) -> dict[str, Any]:
        for entry in report["lanes"]:
            if entry["lane"] == lane_id:
                return entry
        self.fail(f"lane {lane_id} missing from report: {report['lanes']}")

    # 1. two lanes each get their own span, commit count, and numstat --
    #    and neither contaminates the other.
    def test_two_lanes_report_isolated_span_commits_and_numstat(self) -> None:
        self.integration_create()

        lane_a = self.lane_create("lane-a", self.base)
        self.commit(
            lane_a, "src/a.py", "one\ntwo\nthree\n",
            "lane a production work", "2025-01-01T00:01:00+0000",
        )
        collect_a = self.collect("lane-a", self.git(lane_a, "rev-parse", "HEAD"), "2025-01-01T00:03:00+0000")

        tip_after_a = collect_a["collect_sha"]
        lane_b = self.lane_create("lane-b", tip_after_a)
        self.commit(
            lane_b, "src/b.py", "one\ntwo\nthree\nfour\n",
            "lane b production work", "2025-01-01T00:10:00+0000",
        )
        self.commit(
            lane_b, "tests/test_b.py", "assert True\nassert True\n",
            "lane b test work", "2025-01-01T00:10:30+0000",
        )
        self.collect("lane-b", self.git(lane_b, "rev-parse", "HEAD"), "2025-01-01T00:11:00+0000")

        report = self.report()
        self.assertEqual(report["operation"], "report")
        self.assertTrue(report["read_only"])
        self.assertEqual(report["task"]["lanes"], 2)

        entry_a = self.lane_by_id(report, "lane-a")
        self.assertEqual(entry_a["commits"], 1)
        self.assertEqual(entry_a["span_seconds"], 120)  # 00:01:00 -> 00:03:00
        self.assertEqual(entry_a["production"], {"added": 3, "deleted": 0})
        self.assertEqual(entry_a["test"], {"added": 0, "deleted": 0})

        entry_b = self.lane_by_id(report, "lane-b")
        self.assertEqual(entry_b["commits"], 2)
        self.assertEqual(entry_b["span_seconds"], 60)  # 00:10:00 -> 00:11:00
        # lane-b must not see lane-a's src/a.py contribution.
        self.assertEqual(entry_b["production"], {"added": 4, "deleted": 0})
        self.assertEqual(entry_b["test"], {"added": 2, "deleted": 0})

    # 2. production and test numstat are computed as two separate buckets,
    #    each with its own added/deleted -- not one merged bucket.
    def test_production_and_test_numstat_are_separate_buckets(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a", self.base)
        self.commit(
            lane, "src/x.py", "1\n2\n3\n4\n5\n",
            "add production work", "2025-01-01T00:01:00+0000",
        )
        self.commit(
            lane, "tests/test_x.py", "a\nb\nc\n",
            "add test file", "2025-01-01T00:01:30+0000",
        )
        # A production deletion: shrink the pre-existing README from one line to none.
        tip = self.commit(
            lane, "README", "",
            "delete production content", "2025-01-01T00:02:00+0000",
        )
        self.collect("lane-a", tip, "2025-01-01T00:03:00+0000")

        report = self.report()
        entry = self.lane_by_id(report, "lane-a")
        self.assertEqual(entry["production"], {"added": 5, "deleted": 1})
        self.assertEqual(entry["test"], {"added": 3, "deleted": 0})

    # 3a. overlapping lane intervals give max_concurrent == 2.
    def test_max_concurrent_is_two_when_lane_intervals_overlap(self) -> None:
        self.integration_create()
        lane_a = self.lane_create("lane-a", self.base)
        lane_b = self.lane_create("lane-b", self.base)
        self.commit(lane_a, "src/a.py", "a\n", "lane a work", "2025-01-01T00:01:00+0000")
        self.commit(lane_b, "src/b.py", "b\n", "lane b work", "2025-01-01T00:03:00+0000")
        self.collect("lane-a", self.git(lane_a, "rev-parse", "HEAD"), "2025-01-01T00:05:00+0000")
        self.collect("lane-b", self.git(lane_b, "rev-parse", "HEAD"), "2025-01-01T00:07:00+0000")
        # lane-a span [00:01,00:05], lane-b span [00:03,00:07] -- they overlap.

        report = self.report()
        self.assertEqual(report["task"]["max_concurrent"], 2)

    # 3b. non-overlapping lane intervals give max_concurrent == 1.
    def test_max_concurrent_is_one_when_lane_intervals_do_not_overlap(self) -> None:
        self.integration_create()
        lane_a = self.lane_create("lane-a", self.base)
        self.commit(lane_a, "src/a.py", "a\n", "lane a work", "2025-01-01T00:01:00+0000")
        collect_a = self.collect("lane-a", self.git(lane_a, "rev-parse", "HEAD"), "2025-01-01T00:02:00+0000")

        lane_b = self.lane_create("lane-b", collect_a["collect_sha"])
        self.commit(lane_b, "src/b.py", "b\n", "lane b work", "2025-01-01T00:10:00+0000")
        self.collect("lane-b", self.git(lane_b, "rev-parse", "HEAD"), "2025-01-01T00:11:00+0000")
        # lane-a span [00:01,00:02], lane-b span [00:10,00:11] -- disjoint.

        report = self.report()
        self.assertEqual(report["task"]["max_concurrent"], 1)

    # 4. a lane carrying an Origin: user_acceptance trailer is marked in the
    #    output; a lane without it has no origin key at all.
    def test_origin_user_acceptance_trailer_is_surfaced_on_its_lane(self) -> None:
        self.integration_create()
        repair_lane = self.lane_create("repair-a", self.base)
        self.commit(
            repair_lane, "src/fix.py", "fixed\n",
            "repair after user acceptance\n\nOrigin: user_acceptance",
            "2025-01-01T00:01:00+0000",
        )
        collect_repair = self.collect(
            "repair-a", self.git(repair_lane, "rev-parse", "HEAD"), "2025-01-01T00:02:00+0000"
        )

        ordinary_lane = self.lane_create("lane-b", collect_repair["collect_sha"])
        self.commit(ordinary_lane, "src/b.py", "b\n", "ordinary work", "2025-01-01T00:03:00+0000")
        self.collect("lane-b", self.git(ordinary_lane, "rev-parse", "HEAD"), "2025-01-01T00:04:00+0000")

        report = self.report()
        self.assertEqual(self.lane_by_id(report, "repair-a")["origin"], "user_acceptance")
        self.assertNotIn("origin", self.lane_by_id(report, "lane-b"))

    # 5. the four checks are always merely presented: a "refuse" verdict on
    #    any of them must not stop `report` from exiting 0.
    def test_checks_present_even_when_refused_and_report_still_exits_zero(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a", self.base)
        # Pure addition, no production deletion anywhere in the range: the
        # deletion check is expected to come back "refuse".
        self.commit(lane, "src/a.py", "only additions\n", "pure addition", "2025-01-01T00:01:00+0000")
        self.collect("lane-a", self.git(lane, "rev-parse", "HEAD"), "2025-01-01T00:02:00+0000")

        result = self.cli(
            self.root, "report", "--root", str(self.root),
            "--task-id", self.task_id, "--base", self.base,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(set(report["checks"]), {"deletion", "loop", "mass", "focus"})
        self.assertEqual(report["checks"]["deletion"]["status"], "refuse")

    # 6. a commit carrying only the retired Wave:/Role:/Slice: trailers is an
    #    ordinary commit with no lane -- it must not be counted anywhere.
    def test_legacy_wave_trailer_commit_is_not_counted_as_a_lane(self) -> None:
        created = self.integration_create()
        integration_path = Path(str(created["worktree"]))

        lane = self.lane_create("lane-a", self.base)
        self.commit(lane, "src/a.py", "a\n", "lane a work", "2025-01-01T00:01:00+0000")
        self.collect("lane-a", self.git(lane, "rev-parse", "HEAD"), "2025-01-01T00:02:00+0000")

        # Directly append a legacy-vocabulary commit straight onto the
        # integration branch, bypassing `integration collect` entirely --
        # this is what a stray v129-style Wave commit would look like.
        (integration_path / "legacy.txt").write_text("legacy\n", encoding="utf-8")
        self.git(integration_path, "add", "legacy.txt")
        self.git(
            integration_path, "commit", "-q", "-m",
            "Collect Wave legacy\n\nWave: legacy-wave\nSlice: legacy-slice\nRole: merge",
            env={
                "GIT_AUTHOR_DATE": "2025-01-01T00:03:00+0000",
                "GIT_COMMITTER_DATE": "2025-01-01T00:03:00+0000",
            },
        )

        report = self.report()
        self.assertEqual(report["task"]["lanes"], 1)
        lane_ids = {entry["lane"] for entry in report["lanes"]}
        self.assertEqual(lane_ids, {"lane-a"})
        self.assertNotIn("legacy-wave", lane_ids)
        self.assertNotIn("legacy-slice", lane_ids)

    # 7. the candidate section is exactly the same projection integration
    #    status already exposes -- report introduces no second read path.
    def test_candidate_section_matches_integration_status_projection(self) -> None:
        self.integration_create()
        lane = self.lane_create("lane-a", self.base)
        self.commit(lane, "src/a.py", "a\n", "lane a work", "2025-01-01T00:01:00+0000")
        collected = self.collect("lane-a", self.git(lane, "rev-parse", "HEAD"), "2025-01-01T00:02:00+0000")
        self.publish(collected["collect_sha"])

        report = self.report()
        status = self.status()
        self.assertIsNotNone(report["candidate"])
        self.assertEqual(report["candidate"], status["candidate"])


if __name__ == "__main__":
    unittest.main()
