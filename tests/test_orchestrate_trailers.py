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
SCRIPT = (
    ROOT / "home" / ".codex" / "skills" / "orchestrate" / "scripts" / "orchestrate.py"
)


class StrictGitTrailerContractTests(unittest.TestCase):
    """Black-box Contract for workflow authority carried by real Git trailers.

    ``profile report`` is the one remaining reader of the Wave/Slice/Role
    trailer vocabulary (lane/integration collect use Task/Lane/Immutable
    instead, and Immutable is read straight from Git's own repeatable-trailer
    format, so it never goes through the ambiguity detector exercised here).
    Fixtures commit directly onto ``wave/<task>/<wave>/<role>`` branches with
    raw Git rather than through a CLI worktree command, since the lane model
    no longer has a role worktree to create.
    """

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
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
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

    def commit_on_oracle_branch(
        self, root: Path, base: str, path: str, content: str, message: str
    ) -> str:
        """Commit directly onto the Oracle role branch profile report reads.

        Raw Git plumbing stands in for the deleted ``worktree create --role
        oracle`` command: profile report only cares about the branch and its
        commits, not about a live worktree.
        """
        branch = f"wave/{self.task_id}/{self.wave_id}/oracle"
        self.git(root, "checkout", "-q", "-B", branch, base)
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git(root, "add", path)
        self.git(root, "commit", "-q", "-m", message)
        sha = self.git(root, "rev-parse", "HEAD")
        self.git(root, "checkout", "-q", "main")
        return sha

    def trailer_lines(self, root: Path, sha: str) -> list[str]:
        """Ask Git itself which lines form the commit's final trailer block."""
        trailers = self.git(root, "show", "-s", "--format=%(trailers:only)", sha)
        return trailers.splitlines() if trailers else []

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

    def mixed_case_duplicate_message(self, key: str) -> str:
        trailers = [
            f"Wave: {self.wave_id}",
            "Slice: mixed-case-duplicate",
            "Role: oracle",
        ]
        index = {"Wave": 0, "Slice": 1, "Role": 2}[key]
        _, value = trailers[index].split(":", 1)
        trailers.insert(index + 1, f"{key.lower()}:{value}")
        return "mixed-case duplicate workflow trailer\n\n" + "\n".join(trailers)

    def test_profile_omits_eof_labels_without_git_trailer_separator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.init_repo(root)
            commit = self.commit_on_oracle_branch(
                root,
                base,
                "contracts/profile-no-separator.txt",
                "not a profile milestone\n",
                "subject\n"
                f"Wave: {self.wave_id}\n"
                "Slice: no-separator\n"
                "Role: oracle",
            )
            self.assertEqual(self.trailer_lines(root, commit), [])

            report = self.success_payload(self.profile(root, base))

            self.assertEqual(report["slices"], {})
            self.assertNotIn(commit, json.dumps(report, sort_keys=True))

    def test_profile_ignores_body_labels_but_classifies_a_final_git_trailer_block(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.init_repo(root)
            body_only = self.commit_on_oracle_branch(
                root,
                base,
                "contracts/body-only.txt",
                "body only\n",
                "body labels\n\n"
                f"Wave: {self.wave_id}\n"
                "Slice: body-only\n"
                "Role: oracle\n"
                "This final prose line prevents Git from recognizing a trailer block.",
            )
            valid = self.commit_on_oracle_branch(
                root,
                base,
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

    def test_duplicate_actual_trailers_make_profile_report_fail_machine_readably(
        self,
    ) -> None:
        for key in ("Wave", "Slice", "Role"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base = self.init_repo(root)
                commit = self.commit_on_oracle_branch(
                    root,
                    base,
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

    def test_mixed_case_semantic_duplicates_reject_profile_authority(self) -> None:
        for key in ("Wave", "Slice", "Role"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base = self.init_repo(root)
                commit = self.commit_on_oracle_branch(
                    root,
                    base,
                    f"contracts/profile-mixed-case-duplicate-{key.lower()}.txt",
                    "ambiguous profile authority\n",
                    self.mixed_case_duplicate_message(key),
                )
                actual = self.trailer_lines(root, commit)
                tokens = [line.split(":", 1)[0].lower() for line in actual]
                self.assertEqual(tokens.count(key.lower()), 2, actual)

                error = self.error_payload(self.profile(root, base))

                self.assertRegex(
                    str(error["error"]).lower(), r"duplicate|ambiguous|trailer"
                )

    def test_single_mixed_case_variants_normalize_for_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.init_repo(root)
            contract = self.commit_on_oracle_branch(
                root,
                base,
                "contracts/single-mixed-case-variants.txt",
                "case-insensitive workflow metadata\n",
                "single semantic trailer per workflow key\n\n"
                f"wAvE: {self.wave_id}\n"
                "sLiCe: normalized-case\n"
                "rOlE: oracle",
            )
            self.assertEqual(
                self.trailer_lines(root, contract),
                [
                    f"wAvE: {self.wave_id}",
                    "sLiCe: normalized-case",
                    "rOlE: oracle",
                ],
            )

            report = self.success_payload(self.profile(root, base))

            attempt = report["slices"]["normalized-case"]["attempts"][0]
            self.assertEqual(attempt["oracle_sha"], contract)


if __name__ == "__main__":
    unittest.main()
