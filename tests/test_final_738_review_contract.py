from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
SCRIPT = HOME / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"


class ProfileRangeNumstatContractTests(unittest.TestCase):
    """Black-box Contract for topology-assigned Git range accounting."""

    task_id = "final-review-profile"
    wave_id = "owp04"
    slice_id = "range-accounting"

    def git(
        self, cwd: Path, *args: str, env: dict[str, str] | None = None
    ) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def cli(
        self, root: Path, *args: str, env: dict[str, str] | None = None
    ) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"CLI did not return one JSON object: {result.stdout!r}: {exc}")
        self.assertTrue(payload.get("ok"), payload)
        return payload

    def commit(
        self,
        worktree: Path,
        relative: str,
        content: str,
        subject: str,
        date: str,
        role: str | None = None,
        slice_id: str | None = None,
    ) -> str:
        target = worktree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(worktree, "add", relative)
        message = subject
        if role is not None:
            message += (
                f"\n\nWave: {self.wave_id}\n"
                f"Slice: {slice_id or self.slice_id}\n"
                f"Role: {role}"
            )
        self.git(
            worktree,
            "commit",
            "-q",
            "-m",
            message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return self.git(worktree, "rev-parse", "HEAD")

    def merge_contract(self, repo: Path, oracle_sha: str, date: str) -> str:
        payload = self.cli(
            repo,
            "contract",
            "merge",
            "--root",
            str(repo),
            "--task-id",
            self.task_id,
            "--wave-id",
            self.wave_id,
            "--contract-sha",
            oracle_sha,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )
        return str(payload["merge_sha"])

    def test_report_uses_complete_attempt_ranges_and_checkpoint_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.name", "Range Contract Test")
            self.git(repo, "config", "user.email", "range-contract@example.test")
            (repo / "README").write_text("base\n", encoding="utf-8")
            self.git(repo, "add", "README")
            self.git(
                repo,
                "commit",
                "-q",
                "-m",
                "base",
                env={
                    "GIT_AUTHOR_DATE": "2025-01-01T00:00:00+0000",
                    "GIT_COMMITTER_DATE": "2025-01-01T00:00:00+0000",
                },
            )
            base = self.git(repo, "rev-parse", "HEAD")

            implementation_payload = self.cli(
                repo,
                "worktree",
                "create",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--role",
                "implementation",
                "--base",
                base,
            )
            oracle_payload = self.cli(
                repo,
                "worktree",
                "create",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--role",
                "oracle",
                "--base",
                base,
            )
            implementation = Path(str(implementation_payload["worktree"]))
            oracle = Path(str(oracle_payload["worktree"]))

            # Attempt 1: both ready commits have untrailed work immediately before them.
            self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\n",
                "untrailed Contract draft 1",
                "2025-01-01T00:01:00+0000",
            )
            oracle_1 = self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\n",
                "Contract ready 1",
                "2025-01-01T00:02:00+0000",
                "oracle",
            )
            merge_1 = self.merge_contract(repo, oracle_1, "2025-01-01T00:03:00+0000")
            self.commit(
                implementation,
                "src/attempt_1.txt",
                "draft\n",
                "untrailed Implementation draft 1",
                "2025-01-01T00:04:00+0000",
            )
            implementation_1 = self.commit(
                implementation,
                "src/attempt_1.txt",
                "draft\nready\n",
                "Implementation ready 1",
                "2025-01-01T00:05:00+0000",
                "implementation",
            )

            # Attempt 2 has no ready Implementation. Its latest clean checkpoint before
            # the next Contract merge is the terminal boundary for Implementation numstat.
            self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\nattempt 2 draft\n",
                "untrailed Contract draft 2",
                "2025-01-01T00:06:00+0000",
            )
            oracle_2 = self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\nattempt 2 draft\nattempt 2 ready\n",
                "Contract ready 2",
                "2025-01-01T00:07:00+0000",
                "oracle",
            )
            merge_2 = self.merge_contract(repo, oracle_2, "2025-01-01T00:08:00+0000")
            self.commit(
                implementation,
                "src/attempt_2.txt",
                "draft\n",
                "untrailed blocked Implementation work",
                "2025-01-01T00:09:00+0000",
            )
            checkpoint_2 = self.commit(
                implementation,
                "src/attempt_2.txt",
                "draft\ncounterexample preserved\n",
                "Clean blocked checkpoint 2",
                "2025-01-01T00:10:00+0000",
                "implementation-checkpoint",
            )

            # Attempt 3 has a checkpoint followed by a ready commit. The complete
            # merge-to-ready net range is counted exactly once, not checkpoint + ready.
            self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\nattempt 2 draft\nattempt 2 ready\nattempt 3 draft\n",
                "untrailed Contract draft 3",
                "2025-01-01T00:11:00+0000",
            )
            oracle_3 = self.commit(
                oracle,
                "tests/public_contract.txt",
                "attempt 1 draft\nattempt 1 ready\nattempt 2 draft\nattempt 2 ready\nattempt 3 draft\nattempt 3 ready\n",
                "Contract ready 3",
                "2025-01-01T00:12:00+0000",
                "oracle",
            )
            merge_3 = self.merge_contract(repo, oracle_3, "2025-01-01T00:13:00+0000")
            checkpoint_3 = self.commit(
                implementation,
                "src/attempt_3.txt",
                "checkpoint\n",
                "Clean checkpoint before eventual readiness",
                "2025-01-01T00:14:00+0000",
                "implementation-checkpoint",
            )
            self.commit(
                implementation,
                "src/attempt_3.txt",
                "checkpoint\nuntrailed continuation\n",
                "untrailed continuation after checkpoint",
                "2025-01-01T00:15:00+0000",
            )
            implementation_3 = self.commit(
                implementation,
                "src/attempt_3.txt",
                "checkpoint\nuntrailed continuation\nready\n",
                "Implementation ready 3",
                "2025-01-01T00:16:00+0000",
                "implementation",
            )

            report = self.cli(
                repo,
                "profile",
                "report",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--base",
                base,
            )
            self.assertEqual(report["warnings"], [])
            slice_report = report["slices"][self.slice_id]
            self.assertEqual(
                [
                    (
                        attempt["oracle_sha"],
                        attempt["contract_merge_sha"],
                        attempt["implementation_sha"],
                    )
                    for attempt in slice_report["attempts"]
                ],
                [
                    (oracle_1, merge_1, implementation_1),
                    (oracle_2, merge_2, None),
                    (oracle_3, merge_3, implementation_3),
                ],
            )
            for attempt in slice_report["attempts"]:
                self.assertTrue(
                    {
                        "attempt",
                        "oracle_interval_seconds",
                        "handoff_interval_seconds",
                        "implementation_interval_seconds",
                    }
                    <= set(attempt),
                    attempt,
                )
            self.assertEqual(slice_report["checkpoints"], [checkpoint_2, checkpoint_3])
            self.assertEqual(
                slice_report["contract_numstat"],
                {"files": 3, "insertions": 6, "deletions": 0},
            )
            self.assertEqual(
                slice_report["implementation_numstat"],
                {"files": 3, "insertions": 7, "deletions": 0},
            )
            self.assertEqual(
                report["wave"]["contract_numstat"],
                slice_report["contract_numstat"],
            )
            self.assertEqual(
                report["wave"]["implementation_numstat"],
                slice_report["implementation_numstat"],
            )

    def test_report_isolates_ranges_across_slices_in_one_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.name", "Multi-Slice Contract Test")
            self.git(repo, "config", "user.email", "multi-slice@example.test")
            (repo / "README").write_text("base\n", encoding="utf-8")
            self.git(repo, "add", "README")
            self.git(
                repo,
                "commit",
                "-q",
                "-m",
                "base",
                env={
                    "GIT_AUTHOR_DATE": "2025-02-01T00:00:00+0000",
                    "GIT_COMMITTER_DATE": "2025-02-01T00:00:00+0000",
                },
            )
            base = self.git(repo, "rev-parse", "HEAD")

            implementation_payload = self.cli(
                repo,
                "worktree",
                "create",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--role",
                "implementation",
                "--base",
                base,
            )
            oracle_payload = self.cli(
                repo,
                "worktree",
                "create",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--role",
                "oracle",
                "--base",
                base,
            )
            implementation = Path(str(implementation_payload["worktree"]))
            oracle = Path(str(oracle_payload["worktree"]))

            # Slice A publishes a two-commit Contract range and is merged first.
            self.commit(
                oracle,
                "tests/slice_a_contract.txt",
                "A draft\n",
                "untrailed Slice A Contract work",
                "2025-02-01T00:01:00+0000",
            )
            oracle_a = self.commit(
                oracle,
                "tests/slice_a_contract.txt",
                "A ready one\nA ready two\n",
                "Slice A Contract ready",
                "2025-02-01T00:02:00+0000",
                "oracle",
                slice_id="slice-a",
            )
            merge_a = self.merge_contract(repo, oracle_a, "2025-02-01T00:03:00+0000")

            # Slice B continues the Oracle topology. Its Contract range starts at
            # Oracle A, never at the report base, and is merged after A.
            self.commit(
                oracle,
                "tests/slice_b_contract.txt",
                "B draft\n",
                "untrailed Slice B Contract work",
                "2025-02-01T00:04:00+0000",
            )
            oracle_b = self.commit(
                oracle,
                "tests/slice_b_contract.txt",
                "B ready one\nB ready two\n",
                "Slice B Contract ready",
                "2025-02-01T00:05:00+0000",
                "oracle",
                slice_id="slice-b",
            )
            merge_b = self.merge_contract(repo, oracle_b, "2025-02-01T00:06:00+0000")

            # A deliberately has no endpoint before merge B. Only B owns the
            # complete merge-B-to-checkpoint range, including its untrailed work.
            self.commit(
                implementation,
                "src/slice_b.py",
                "draft = True\n",
                "untrailed Slice B Implementation work",
                "2025-02-01T00:07:00+0000",
            )
            checkpoint_b = self.commit(
                implementation,
                "src/slice_b.py",
                "draft = True\ncheckpoint = True\n",
                "Slice B clean blocked checkpoint",
                "2025-02-01T00:08:00+0000",
                "implementation-checkpoint",
                slice_id="slice-b",
            )

            report = self.cli(
                repo,
                "profile",
                "report",
                "--root",
                str(repo),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--base",
                base,
            )
            self.assertEqual(report["warnings"], [])
            slice_a = report["slices"]["slice-a"]
            slice_b = report["slices"]["slice-b"]

            self.assertEqual(
                [
                    (
                        attempt["oracle_sha"],
                        attempt["contract_merge_sha"],
                        attempt["implementation_sha"],
                    )
                    for attempt in slice_a["attempts"]
                ],
                [(oracle_a, merge_a, None)],
            )
            self.assertEqual(
                [
                    (
                        attempt["oracle_sha"],
                        attempt["contract_merge_sha"],
                        attempt["implementation_sha"],
                    )
                    for attempt in slice_b["attempts"]
                ],
                [(oracle_b, merge_b, None)],
            )
            contract_a = {"files": 1, "insertions": 2, "deletions": 0}
            contract_b = {"files": 1, "insertions": 2, "deletions": 0}
            implementation_a = {"files": 0, "insertions": 0, "deletions": 0}
            implementation_b = {"files": 1, "insertions": 2, "deletions": 0}
            self.assertEqual(
                slice_b["contract_numstat"],
                contract_b,
                "Slice B must exclude Slice A's base-to-Oracle Contract range",
            )
            self.assertEqual(slice_a["contract_numstat"], contract_a)
            self.assertEqual(
                slice_a["implementation_numstat"],
                implementation_a,
                "Slice A must stop at merge B rather than claim B's checkpoint",
            )
            self.assertEqual(
                slice_b["implementation_numstat"],
                implementation_b,
                "Slice B must own its complete merge-to-checkpoint range",
            )
            self.assertEqual(slice_b["checkpoints"], [checkpoint_b])

            for metric in ("contract_numstat", "implementation_numstat"):
                isolated_total = {
                    key: slice_a[metric][key] + slice_b[metric][key]
                    for key in ("files", "insertions", "deletions")
                }
                self.assertEqual(
                    report["wave"][metric],
                    isolated_total,
                    f"Wave {metric} must sum isolated Slice ranges exactly once",
                )


class Final738ProfileTextContractTests(unittest.TestCase):
    profile_roots = {
        "codex": (HOME / ".codex" / "agents", ".toml"),
        "claude": (HOME / ".claude" / "agents", ".md"),
        "pi": (HOME / ".pi" / "agent" / "agents", ".md"),
    }

    def normalized(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"missing shipped surface: {path}")
        return " ".join(path.read_text(encoding="utf-8").split())

    def test_blocked_checkpoint_contract_is_bound_in_profiles_and_runtimes(self) -> None:
        surfaces = {
            f"{runtime}-profile": root / f"wave-implementer{suffix}"
            for runtime, (root, suffix) in self.profile_roots.items()
        }
        surfaces.update(
            {
                "codex-binding": HOME
                / ".codex"
                / "skills"
                / "orchestrate"
                / "runtime-codex.md",
                "claude-binding": HOME
                / ".codex"
                / "skills"
                / "orchestrate"
                / "runtime-claude.md",
                "pi-binding": HOME
                / ".pi"
                / "agent"
                / "skills"
                / "orchestrate"
                / "runtime-pi.md",
            }
        )
        for name, path in surfaces.items():
            with self.subTest(surface=name):
                text = self.normalized(path)
                lowered = text.lower()
                self.assertRegex(
                    text,
                    r"(?i)blocked.{0,500}clean (?:git )?checkpoint commit"
                    r"|clean (?:git )?checkpoint commit.{0,500}blocked",
                )
                for trailer in (
                    "Wave: <wave-id>",
                    "Slice: <slice-id>",
                    "Role: implementation-checkpoint",
                ):
                    self.assertIn(trailer, text)
                self.assertNotRegex(text, r"(?i)Role:\s*checkpoint\b")
                self.assertRegex(
                    lowered,
                    r"(?:terminal blocked|blocked (?:output|hold)).{0,500}counterexample"
                    r".{0,300}(?:exact )?checkpoint sha"
                    r"|counterexample.{0,300}(?:exact )?checkpoint sha.{0,500}"
                    r"(?:terminal blocked|blocked (?:output|hold))",
                )

    def test_contract_planner_profiles_publish_dependency_addressable_v119_slices(self) -> None:
        for runtime, (root, suffix) in self.profile_roots.items():
            with self.subTest(runtime=runtime):
                text = self.normalized(root / f"contract-planner{suffix}")
                lowered = text.lower()
                self.assertRegex(text, r"(?i)dependency-addressable Slices?")
                self.assertRegex(
                    text,
                    r"(?i)Oracle.{0,180}executable Contract.{0,180}Root.{0,140}"
                    r"exact merge.{0,180}Implementation",
                )
                self.assertRegex(
                    text,
                    r"(?i)Root.{0,180}(?:chooses|decides).{0,100}Wave (?:grouping|groups)"
                    r".{0,180}queue depth",
                )
                self.assertRegex(
                    text,
                    r"(?i)planning-only|read-only planning",
                )
                self.assertRegex(
                    text,
                    r"(?i)(?:must not|never|does not).{0,100}dispatch",
                )
                self.assertRegex(
                    text,
                    r"(?i)(?:must not|never|does not).{0,100}(?:edit|mutate)",
                )
                for obsolete in (
                    r"\blanes?\b",
                    r"wave-ahead",
                    r"review[- ]envelope",
                    r"\bmilestone\b",
                    r"\benvelope\b",
                ):
                    self.assertNotRegex(lowered, obsolete)


if __name__ == "__main__":
    unittest.main()
