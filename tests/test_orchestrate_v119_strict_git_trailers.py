from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"
)


class StrictGitTrailerContractTests(unittest.TestCase):
    """Black-box Contract for workflow authority carried by real Git trailers."""

    task_id = "strict-trailer-task"
    wave_id = "strict-wave"

    def git(
        self,
        cwd: Path,
        *args: str,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )
        if check and result.returncode:
            self.fail(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )

    def success_payload(
        self, result: subprocess.CompletedProcess[str]
    ) -> dict[str, object]:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"success was not one JSON object: {result.stdout!r}: {exc}")
        self.assertIsInstance(payload, dict)
        self.assertTrue(payload.get("ok"), payload)
        return payload

    def error_payload(
        self, result: subprocess.CompletedProcess[str]
    ) -> dict[str, object]:
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "", result.stdout)
        try:
            payload = json.loads(result.stderr)
        except json.JSONDecodeError as exc:
            self.fail(
                f"failure was not one JSON error object: {result.stderr!r}: {exc}"
            )
        self.assertIsInstance(payload, dict)
        self.assertFalse(payload.get("ok"), payload)
        self.assertIsInstance(payload.get("error"), dict)
        return payload

    def init_repo(self, root: Path) -> str:
        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "config", "user.name", "Strict Trailer Contract")
        self.git(root, "config", "user.email", "strict-trailer@example.test")
        (root / "README").write_text("base\n", encoding="utf-8")
        self.git(root, "add", "README")
        self.git(root, "commit", "-q", "-m", "base")
        return self.git(root, "rev-parse", "HEAD")

    def create_worktree(self, root: Path, base: str, role: str) -> Path:
        payload = self.success_payload(
            self.cli(
                root,
                "worktree",
                "create",
                "--root",
                str(root),
                "--task-id",
                self.task_id,
                "--wave-id",
                self.wave_id,
                "--role",
                role,
                "--base",
                base,
            )
        )
        return Path(str(payload["worktree"]))

    def commit_file(self, worktree: Path, path: str, content: str, message: str) -> str:
        target = worktree / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(worktree, "add", path)
        self.git(worktree, "commit", "-q", "-m", message)
        return self.git(worktree, "rev-parse", "HEAD")

    def trailer_lines(self, root: Path, sha: str) -> list[str]:
        """Ask Git itself which lines form the commit's final trailer block."""
        trailers = self.git(root, "show", "-s", "--format=%(trailers:only)", sha)
        return trailers.splitlines() if trailers else []

    def merge(self, root: Path, contract: str) -> subprocess.CompletedProcess[str]:
        return self.cli(
            root,
            "contract",
            "merge",
            "--root",
            str(root),
            "--task-id",
            self.task_id,
            "--wave-id",
            self.wave_id,
            "--contract-sha",
            contract,
        )

    def profile(self, root: Path, base: str) -> subprocess.CompletedProcess[str]:
        return self.cli(
            root,
            "profile",
            "report",
            "--root",
            str(root),
            "--task-id",
            self.task_id,
            "--wave-id",
            self.wave_id,
            "--base",
            base,
        )

    def duplicate_message(self, key: str) -> str:
        trailers = [
            f"Wave: {self.wave_id}",
            "Slice: duplicate-trailer",
            "Role: oracle",
        ]
        index = {"Wave": 0, "Slice": 1, "Role": 2}[key]
        trailers.insert(index + 1, trailers[index])
        return "duplicate workflow trailer\n\n" + "\n".join(trailers)

    def test_body_labels_followed_by_prose_are_rejected_without_merge_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.init_repo(root)
            implementation = self.create_worktree(root, base, "implementation")
            oracle = self.create_worktree(root, base, "oracle")
            contract = self.commit_file(
                oracle,
                "contracts/body-labels.txt",
                "not a contract\n",
                "labels in the commit body\n\n"
                f"Wave: {self.wave_id}\n"
                "Slice: body-labels\n"
                "Role: oracle\n"
                "Ordinary prose after the labels makes this body text, not trailers.",
            )
            self.assertEqual(self.trailer_lines(root, contract), [])
            head_before = self.git(implementation, "rev-parse", "HEAD")
            refs_before = self.git(root, "show-ref")

            error = self.error_payload(self.merge(root, contract))

            self.assertRegex(str(error["error"]).lower(), r"trailer|contract")
            self.assertEqual(self.git(implementation, "rev-parse", "HEAD"), head_before)
            self.assertEqual(self.git(root, "show-ref"), refs_before)
            self.assertFalse((implementation / "contracts/body-labels.txt").exists())
            merge_head = Path(
                self.git(implementation, "rev-parse", "--git-path", "MERGE_HEAD")
            )
            self.assertFalse(merge_head.exists())

    def test_profile_ignores_body_labels_but_classifies_a_final_git_trailer_block(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.init_repo(root)
            oracle = self.create_worktree(root, base, "oracle")
            body_only = self.commit_file(
                oracle,
                "contracts/body-only.txt",
                "body only\n",
                "body labels\n\n"
                f"Wave: {self.wave_id}\n"
                "Slice: body-only\n"
                "Role: oracle\n"
                "This final prose line prevents Git from recognizing a trailer block.",
            )
            valid = self.commit_file(
                oracle,
                "contracts/valid.txt",
                "valid\n",
                "compact valid publication\n\n"
                f"Wave: {self.wave_id}\n"
                "Slice: final-block\n"
                "Role: oracle",
            )
            self.assertEqual(self.trailer_lines(root, body_only), [])
            self.assertEqual(
                self.trailer_lines(root, valid),
                [f"Wave: {self.wave_id}", "Slice: final-block", "Role: oracle"],
            )

            report = self.success_payload(self.profile(root, base))

            self.assertEqual(set(report["slices"]), {"final-block"})
            attempt = report["slices"]["final-block"]["attempts"][0]
            self.assertEqual(attempt["oracle_sha"], valid)
            self.assertNotIn(body_only, json.dumps(report, sort_keys=True))

    def test_final_git_trailer_block_remains_mergeable_and_profiled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.init_repo(root)
            self.create_worktree(root, base, "implementation")
            oracle = self.create_worktree(root, base, "oracle")
            contract = self.commit_file(
                oracle,
                "contracts/final-block.txt",
                "public contract\n",
                f"publish\n\nWave: {self.wave_id}\nSlice: final-block\nRole: oracle",
            )
            self.assertEqual(
                self.trailer_lines(root, contract),
                [f"Wave: {self.wave_id}", "Slice: final-block", "Role: oracle"],
            )

            merged = self.success_payload(self.merge(root, contract))
            report = self.success_payload(self.profile(root, base))

            self.assertEqual(merged["contract_sha"], contract)
            attempt = report["slices"]["final-block"]["attempts"][0]
            self.assertEqual(attempt["oracle_sha"], contract)
            self.assertEqual(attempt["contract_merge_sha"], merged["merge_sha"])

    def test_duplicate_actual_trailers_reject_contract_merge_machine_readably(
        self,
    ) -> None:
        for key in ("Wave", "Slice", "Role"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base = self.init_repo(root)
                implementation = self.create_worktree(root, base, "implementation")
                oracle = self.create_worktree(root, base, "oracle")
                contract = self.commit_file(
                    oracle,
                    f"contracts/duplicate-{key.lower()}.txt",
                    "ambiguous\n",
                    self.duplicate_message(key),
                )
                actual = self.trailer_lines(root, contract)
                self.assertEqual(sum(line.startswith(f"{key}:") for line in actual), 2)
                head_before = self.git(implementation, "rev-parse", "HEAD")
                refs_before = self.git(root, "show-ref")

                error = self.error_payload(self.merge(root, contract))

                self.assertRegex(
                    str(error["error"]).lower(), r"duplicate|ambiguous|trailer"
                )
                self.assertEqual(
                    self.git(implementation, "rev-parse", "HEAD"), head_before
                )
                self.assertEqual(self.git(root, "show-ref"), refs_before)
                self.assertFalse(
                    Path(
                        self.git(
                            implementation, "rev-parse", "--git-path", "MERGE_HEAD"
                        )
                    ).exists()
                )

    def test_duplicate_actual_trailers_make_profile_report_fail_machine_readably(
        self,
    ) -> None:
        for key in ("Wave", "Slice", "Role"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base = self.init_repo(root)
                oracle = self.create_worktree(root, base, "oracle")
                commit = self.commit_file(
                    oracle,
                    f"contracts/profile-duplicate-{key.lower()}.txt",
                    "ambiguous profile milestone\n",
                    self.duplicate_message(key),
                )
                actual = self.trailer_lines(root, commit)
                self.assertEqual(sum(line.startswith(f"{key}:") for line in actual), 2)

                error = self.error_payload(self.profile(root, base))

                self.assertRegex(
                    str(error["error"]).lower(), r"duplicate|ambiguous|trailer"
                )


if __name__ == "__main__":
    unittest.main()
