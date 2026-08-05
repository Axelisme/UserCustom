from __future__ import annotations

import json
import os
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Any

from tests._orchestrate_cli_support import OrchestrateCliRepositoryTestCase, run_cli, run_git


class AcceptedDeliveryAndReconciliationContractTests(OrchestrateCliRepositoryTestCase):
    """Contract module C through the shipped subprocess and real local Git."""

    persist = "main"

    def task_root(self, task_id: str) -> Path:
        return self.root / ".agent_state" / "worktrees" / task_id

    def integration_path(self, task_id: str) -> Path:
        return self.task_root(task_id) / "integration"

    def acceptance_path(self, task_id: str) -> Path:
        return self.task_root(task_id) / "acceptance"

    def lane_path(self, task_id: str, lane_id: str) -> Path:
        return self.task_root(task_id) / "lanes" / lane_id

    def accepted_ref(self, task_id: str) -> str:
        return f"refs/orchestrate/{task_id}/accepted"

    def user_accepted_ref(self, task_id: str) -> str:
        return f"refs/orchestrate/{task_id}/user-accepted"

    def landed_ref(self, task_id: str) -> str:
        return f"refs/orchestrate/{task_id}/landed"

    def integration_ref(self, task_id: str) -> str:
        return f"refs/heads/wave/{task_id}/integration"

    def lane_ref(self, task_id: str, lane_id: str) -> str:
        return f"refs/heads/wave/{task_id}/{lane_id}"

    def lane_base_ref(self, task_id: str, lane_id: str) -> str:
        return f"refs/orchestrate/{task_id}/{lane_id}/base"

    def create_task(self, task_id: str) -> Path:
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "create",
                "--task-id",
                task_id,
            ),
            "integration-create",
        )
        return self.integration_path(task_id)

    def start_acceptance(
        self, task_id: str, sha: str | None = None
    ) -> dict[str, Any]:
        argv = ["acceptance", "start", "--task-id", task_id]
        if sha is not None:
            argv.extend(("--sha", sha))
        return self.mutation_success(
            self.cli(self.nested, *argv),
            "acceptance-start",
        )

    def acceptance_result(
        self, task_id: str, outcome: str, verifier: str = "agent"
    ) -> dict[str, Any]:
        payload = self.success(
            self.cli(
                self.nested,
                "acceptance",
                "result",
                "--task-id",
                task_id,
                "--verifier",
                verifier,
                "--outcome",
                outcome,
            )
        )
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["operation"], "acceptance-result")
        self.assertEqual(payload["orchestrate_version"], self.orchestrate_version)
        self.assertEqual(payload["verifier"], verifier)
        self.assertEqual(
            payload["subject_sha"],
            self.git(self.acceptance_path(task_id), "rev-parse", "HEAD"),
        )
        return payload

    def accept_current(self, task_id: str) -> str:
        self.start_acceptance(task_id)
        subject = self.git(self.acceptance_path(task_id), "rev-parse", "HEAD")
        self.acceptance_result(task_id, "pass")
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), subject)
        return subject

    def create_lane(self, task_id: str, lane_id: str) -> Path:
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                task_id,
                "--lane-id",
                lane_id,
            ),
            "lane-create",
        )
        return self.lane_path(task_id, lane_id)

    def collect_lane(
        self,
        task_id: str,
        lane_id: str,
        ticket: str | None = None,
    ) -> None:
        bounded_ticket = ticket or f"ticket-{task_id}-{lane_id}"
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "collect",
                "--task-id",
                task_id,
                "--lane-id",
                lane_id,
                "--ticket",
                bounded_ticket,
            ),
            "integration-collect",
        )

    def assert_lane_closed(self, task_id: str, lane_id: str) -> None:
        lane = self.lane_path(task_id, lane_id)
        self.assertFalse(lane.exists())
        self.assertEqual(self.ref_value(self.lane_ref(task_id, lane_id)), "")
        self.assertEqual(self.ref_value(self.lane_base_ref(task_id, lane_id)), "")
        worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        self.assertNotIn(str(lane), worktrees)
        self.assertNotIn(f"branch {self.lane_ref(task_id, lane_id)}", worktrees)

    def assert_lane_retained(
        self,
        task_id: str,
        lane_id: str,
        original_base: str,
    ) -> None:
        lane = self.lane_path(task_id, lane_id)
        self.assertTrue(lane.is_dir())
        lane_tip = self.git(lane, "rev-parse", "HEAD")
        self.assertEqual(self.ref_value(self.lane_ref(task_id, lane_id)), lane_tip)
        self.assertEqual(
            self.ref_value(self.lane_base_ref(task_id, lane_id)), original_base
        )
        worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        self.assertIn(str(lane), worktrees)
        self.assertIn(f"branch {self.lane_ref(task_id, lane_id)}", worktrees)

    def assert_named_warning(self, payload: dict[str, Any], lane_id: str) -> None:
        warnings = payload.get("warnings", [])
        self.assertIsInstance(warnings, list)
        self.assertTrue(
            any(lane_id in warning for warning in warnings),
            warnings,
        )

    def land(self, task_id: str, persist: str | None = None, message: str | None = None):
        argv = [
            "integration",
            "land",
            "--task-id",
            task_id,
            "--persist",
            persist or self.persist,
        ]
        if message is not None:
            argv.extend(("--message", message))
        return self.cli(self.nested, *argv)

    def reconcile(self, task_id: str, lane_id: str, persist: str | None = None):
        return self.cli(
            self.nested,
            "integration",
            "reconcile",
            "--task-id",
            task_id,
            "--lane-id",
            lane_id,
            "--persist",
            persist or self.persist,
        )

    def telemetry_events(self, task_id: str) -> list[dict[str, Any]]:
        path = (
            self.root
            / ".agent_state"
            / "worktrees"
            / task_id
            / "telemetry.jsonl"
        )
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def authority_snapshot(self) -> dict[str, object]:
        """Exclude warning-only telemetry while freezing authoritative resources."""
        snapshot = self.managed_state_snapshot()
        filesystem = snapshot["filesystem"]
        assert isinstance(filesystem, list)
        snapshot["filesystem"] = [
            item
            for item in filesystem
            if not item[0].endswith("/telemetry.jsonl")
        ]
        snapshot["exact_refs"] = self.git(
            self.root,
            "for-each-ref",
            "--format=%(refname)%09%(symref)%09%(objectname)%09%(objecttype)",
        )
        return snapshot

    def checkout_snapshot(
        self, path: Path, paths: tuple[str, ...] = ()
    ) -> dict[str, object]:
        return {
            "head": self.git(path, "rev-parse", "HEAD"),
            "tree": self.git(path, "rev-parse", "HEAD^{tree}"),
            "status_bytes": run_git(
                path, "status", "--porcelain=v1", "--untracked-files=all"
            ).stdout.encode(),
            "index_bytes": run_git(path, "ls-files", "--stage").stdout.encode(),
            "worktree_bytes": {
                relative: (path / relative).read_bytes()
                if (path / relative).is_file()
                else None
                for relative in paths
            },
        }

    def persistence_snapshot(self, paths: tuple[str, ...] = ()) -> dict[str, object]:
        return {
            **self.checkout_snapshot(self.root, paths),
            "branch": self.git(self.root, "symbolic-ref", "--short", "HEAD"),
            "authority": self.authority_snapshot(),
        }

    def assert_no_retired_delivery_state(self, task_id: str) -> None:
        refs = self.git(
            self.root,
            "for-each-ref",
            "--format=%(refname)",
            f"refs/orchestrate/{task_id}/",
            f"refs/heads/wave/{task_id}/",
        ).splitlines()
        for ref in refs:
            self.assertNotIn("/candidate", ref)
            self.assertNotIn("/rejected", ref)
        self.assertNotIn(f"refs/heads/wave/{task_id}/acceptance", refs)
        self.assertNotIn(f"refs/heads/wave/{task_id}/landed", refs)

    def test_01_acceptance_start_is_lazy_detached_and_replaces_prior_dirt(self) -> None:
        self.assert_help_surface(
            ("integration",),
            commands=("create", "collect", "reconcile", "land", "remove"),
        )
        self.assert_help_surface(("acceptance",), commands=("start", "result"))
        self.assert_help_surface(
            ("acceptance", "start"), long_options=("--task-id", "--sha")
        )
        self.assert_help_surface(
            ("acceptance", "result"),
            long_options=("--task-id", "--outcome", "--verifier"),
        )
        self.assert_help_surface(
            ("integration", "land"),
            long_options=("--task-id", "--persist", "--message"),
        )
        self.assert_help_surface(
            ("integration", "reconcile"),
            long_options=("--task-id", "--lane-id", "--persist"),
        )

        task_id = "lazy-start"
        integration = self.create_task(task_id)
        acceptance = self.acceptance_path(task_id)
        self.assertFalse(acceptance.exists())
        first = self.commit_file(
            integration,
            "subject.txt",
            b"first validation subject\n",
            "First validation subject",
        )
        self.start_acceptance(task_id)
        self.assertEqual(self.git(acceptance, "rev-parse", "HEAD"), first)
        self.assertEqual(
            self.git(acceptance, "symbolic-ref", "-q", "HEAD", check=False), ""
        )
        (acceptance / "runtime.bin").write_bytes(b"discard runtime dirt\x00\xff")
        (acceptance / "base.txt").write_bytes(b"discard tracked diagnostic dirt\n")

        second = self.commit_file(
            integration,
            "new-subject.txt",
            b"second validation subject\n",
            "Second validation subject",
        )
        self.start_acceptance(task_id)

        self.assertEqual(self.git(acceptance, "rev-parse", "HEAD"), second)
        self.assertEqual(
            self.git(acceptance, "symbolic-ref", "-q", "HEAD", check=False), ""
        )
        self.assertEqual(self.git(acceptance, "status", "--porcelain"), "")
        self.assertFalse((acceptance / "runtime.bin").exists())
        self.assertEqual((acceptance / "base.txt").read_bytes(), b"base\n")
        self.assert_no_retired_delivery_state(task_id)

    def test_01b_start_sha_uses_commit_authority_not_integration_worktree(self) -> None:
        task_id = "explicit-subject"
        integration = self.create_task(task_id)
        first = self.commit_file(
            integration, "first.txt", b"first exact subject\n", "First exact subject"
        )
        second = self.commit_file(
            integration, "second.txt", b"second exact subject\n", "Second exact subject"
        )
        (integration / "base.txt").write_bytes(b"uncommitted integration dirt\n")

        self.start_acceptance(task_id)
        self.assertEqual(self.git(self.acceptance_path(task_id), "rev-parse", "HEAD"), second)
        self.git(self.root, "worktree", "remove", "--force", str(integration))
        self.start_acceptance(task_id, first)
        self.assertEqual(self.git(self.acceptance_path(task_id), "rev-parse", "HEAD"), first)

        outside = self.commit_file(
            self.root, "outside.txt", b"outside integration history\n", "Outside task"
        )
        before = self.authority_snapshot()
        for subject in (first[:12], f"{first}^", outside):
            with self.subTest(subject=subject):
                self.operational_failure(
                    self.cli(
                        self.nested,
                        "acceptance",
                        "start",
                        "--task-id",
                        task_id,
                        "--sha",
                        subject,
                    ),
                    "acceptance-start",
                    "acceptance_subject_invalid",
                )
                self.assertEqual(self.authority_snapshot(), before)

        with tempfile.TemporaryDirectory(prefix="orchestrate-sha256-") as temporary:
            sha256_root = Path(temporary)
            run_git(sha256_root, "init", "-q", "--object-format=sha256", "-b", "main")
            run_git(sha256_root, "config", "user.name", "Contract Test")
            run_git(sha256_root, "config", "user.email", "contract@example.invalid")
            (sha256_root / ".gitignore").write_text("/.agent_state/\n", encoding="utf-8")
            (sha256_root / "base.txt").write_text("base\n", encoding="utf-8")
            sha256_nested = sha256_root / "nested"
            sha256_nested.mkdir()
            run_git(sha256_root, "add", ".gitignore", "base.txt")
            run_git(sha256_root, "commit", "-qm", "base")
            self.success(
                run_cli(
                    sha256_nested,
                    "integration",
                    "create",
                    "--task-id",
                    "sha256-subject",
                )
            )
            sha256_integration = (
                sha256_root
                / ".agent_state/worktrees/sha256-subject/integration"
            )
            historical = self.commit_file(
                sha256_integration,
                "historical.txt",
                b"historical sha256 subject\n",
                "Historical SHA-256 subject",
            )
            self.commit_file(
                sha256_integration,
                "current.txt",
                b"current sha256 subject\n",
                "Current SHA-256 subject",
            )
            self.success(
                run_cli(
                    sha256_nested,
                    "acceptance",
                    "start",
                    "--task-id",
                    "sha256-subject",
                    "--sha",
                    historical,
                )
            )
            self.assertEqual(len(historical), 64)
            self.assertEqual(
                self.git(
                    sha256_root
                    / ".agent_state/worktrees/sha256-subject/acceptance",
                    "rev-parse",
                    "HEAD",
                ),
                historical,
            )

    def test_01c_verifier_refs_are_independent_and_may_regress(self) -> None:
        task_id = "verifier-authority"
        integration = self.create_task(task_id)
        first = self.commit_file(
            integration, "first.txt", b"first verifier subject\n", "First verifier subject"
        )
        self.start_acceptance(task_id)

        self.operational_failure(
            self.cli(
                self.nested,
                "acceptance",
                "result",
                "--task-id",
                task_id,
                "--outcome",
                "pass",
            ),
            "cli",
            "cli_usage",
        )
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), "")
        self.assertEqual(self.ref_value(self.user_accepted_ref(task_id)), "")

        agent = self.acceptance_result(task_id, "pass", "agent")
        self.assertEqual(
            {key: agent[key] for key in (
                "previous_sha", "current_sha", "ref_updated", "regressed"
            )},
            {
                "previous_sha": None,
                "current_sha": first,
                "ref_updated": True,
                "regressed": False,
            },
        )
        self.acceptance_result(task_id, "pass", "user")
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), first)
        self.assertEqual(self.ref_value(self.user_accepted_ref(task_id)), first)

        second = self.commit_file(
            integration, "second.txt", b"second verifier subject\n", "Second verifier subject"
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass", "user")
        self.assertEqual(self.ref_value(self.user_accepted_ref(task_id)), second)
        self.start_acceptance(task_id, first)
        regressed = self.acceptance_result(task_id, "pass", "user")
        self.assertIs(regressed["regressed"], True)
        self.assertTrue(regressed["warnings"])
        self.assertEqual(self.ref_value(self.user_accepted_ref(task_id)), first)
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), first)

        failed = self.acceptance_result(task_id, "fail", "user")
        self.assertIs(failed["ref_updated"], True)
        self.assertIsNone(failed["current_sha"])
        self.assertEqual(self.ref_value(self.user_accepted_ref(task_id)), "")
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), first)
        results = [
            event
            for event in self.telemetry_events(task_id)
            if event["operation"] == "acceptance-result"
        ]
        self.assertEqual([event["verifier"] for event in results], ["agent", "user", "user", "user", "user"])
        self.assertIn("previous_sha", results[0])
        self.assertIsNone(results[0]["previous_sha"])
        self.assertIn("current_sha", results[-1])
        self.assertIsNone(results[-1]["current_sha"])

    def test_02_newer_start_preserves_older_accepted_and_records_supersession(self) -> None:
        task_id = "accepted-supersession"
        integration = self.create_task(task_id)
        older = self.commit_file(
            integration, "older.txt", b"older accepted\n", "Older accepted subject"
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass")
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), older)
        pending = self.commit_file(
            integration,
            "pending.txt",
            b"pending validation interval\n",
            "Pending validation subject",
        )
        self.start_acceptance(task_id)
        newer = self.commit_file(
            integration, "newer.txt", b"newer pending\n", "Newer validation subject"
        )

        self.start_acceptance(task_id)

        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), older)
        self.assertEqual(
            self.git(self.acceptance_path(task_id), "rev-parse", "HEAD"), newer
        )
        starts = [
            (event["outcome"], event["subject_sha"])
            for event in self.telemetry_events(task_id)
            if event["operation"] == "acceptance-start"
        ]
        self.assertEqual(
            starts,
            [
                ("success", older),
                ("success", pending),
                ("superseded", newer),
            ],
        )
        self.assert_no_retired_delivery_state(task_id)

    def test_03_pass_uses_detached_first_parent_identity_and_allows_runtime_artifacts(self) -> None:
        task_id = "first-parent-pass"
        integration = self.create_task(task_id)
        accepted_subject = self.commit_file(
            integration,
            "accepted.txt",
            b"accepted first-parent subject\n",
            "Accepted first-parent subject",
        )
        self.start_acceptance(task_id)
        current = self.commit_file(
            integration,
            "current.txt",
            b"newer integration subject\n",
            "Advance integration after validation starts",
        )
        self.assertNotEqual(accepted_subject, current)
        acceptance = self.acceptance_path(task_id)
        untracked = acceptance / "runtime-output.bin"
        ignored = acceptance / ".agent_state" / "runtime" / "ignored.bin"
        untracked_bytes = b"runtime output\x00\xff"
        ignored_bytes = b"ignored output\x00\xfe"
        untracked.write_bytes(untracked_bytes)
        ignored.parent.mkdir(parents=True)
        ignored.write_bytes(ignored_bytes)
        self.assertEqual(
            self.git(acceptance, "status", "--porcelain"), "?? runtime-output.bin"
        )

        self.acceptance_result(task_id, "pass")

        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), accepted_subject)
        self.assertEqual(self.git(acceptance, "rev-parse", "HEAD"), accepted_subject)
        self.assertEqual(
            self.git(acceptance, "symbolic-ref", "-q", "HEAD", check=False), ""
        )
        self.assertEqual(untracked.read_bytes(), untracked_bytes)
        self.assertEqual(ignored.read_bytes(), ignored_bytes)
        self.assert_no_retired_delivery_state(task_id)

    def test_04_pass_refuses_non_first_parent_local_and_dirty_subjects_atomically(self) -> None:
        subjects: list[tuple[str, str]] = [
            ("arbitrary-detached", "arbitrary"),
            ("lane-second-parent", "second-parent"),
            ("acceptance-local", "local"),
            ("staged-index", "staged"),
            ("tracked-dirt", "tracked"),
        ]
        for task_id, kind in subjects:
            with self.subTest(kind=kind):
                self.create_task(task_id)
                accepted_before = self.accept_current(task_id)
                acceptance = self.acceptance_path(task_id)
                if kind == "arbitrary":
                    arbitrary = self.commit_file(
                        self.root,
                        f"{task_id}.txt",
                        b"outside integration history\n",
                        "Arbitrary persistence commit",
                    )
                    self.start_acceptance(task_id)
                    self.git(acceptance, "checkout", "-q", "--detach", arbitrary)
                elif kind == "second-parent":
                    lane_id = "writer"
                    lane = self.create_lane(task_id, lane_id)
                    lane_tip = self.commit_file(
                        lane,
                        "lane-only.txt",
                        b"lane second parent\n",
                        "Lane second-parent subject",
                    )
                    self.collect_lane(task_id, lane_id)
                    self.start_acceptance(task_id)
                    self.git(acceptance, "checkout", "-q", "--detach", lane_tip)
                elif kind == "local":
                    self.start_acceptance(task_id)
                    self.commit_file(
                        acceptance,
                        "local.txt",
                        b"acceptance must not own source commits\n",
                        "Acceptance-local commit",
                    )
                else:
                    self.start_acceptance(task_id)
                    (acceptance / "base.txt").write_bytes(
                        f"{kind} acceptance bytes\n".encode()
                    )
                    if kind == "staged":
                        self.git(acceptance, "add", "base.txt")
                before = self.authority_snapshot()
                result = self.cli(
                    self.nested,
                    "acceptance",
                    "result",
                    "--task-id",
                    task_id,
                    "--outcome",
                    "pass",
                    "--verifier",
                    "agent",
                )
                after = self.authority_snapshot()
                self.operational_failure(
                    result, "acceptance-result", "acceptance_subject_invalid"
                )
                self.assertEqual(after, before)
                self.assertEqual(
                    self.ref_value(self.accepted_ref(task_id)), accepted_before
                )
                self.assert_no_retired_delivery_state(task_id)

    def test_05_fail_preserves_diagnostics_and_revokes_only_equal_accepted(self) -> None:
        equal_task = "fail-equal"
        self.create_task(equal_task)
        equal = self.accept_current(equal_task)
        equal_acceptance = self.acceptance_path(equal_task)
        equal_diagnostic = equal_acceptance / "equal-diagnostic.bin"
        equal_bytes = b"failed exact accepted subject\x00\xff"
        equal_diagnostic.write_bytes(equal_bytes)

        self.acceptance_result(equal_task, "fail")

        self.assertEqual(self.ref_value(self.accepted_ref(equal_task)), "")
        self.assertEqual(self.git(equal_acceptance, "rev-parse", "HEAD"), equal)
        self.assertEqual(equal_diagnostic.read_bytes(), equal_bytes)

        older_task = "fail-newer"
        integration = self.create_task(older_task)
        older = self.accept_current(older_task)
        newer = self.commit_file(
            integration, "newer.txt", b"newer failed subject\n", "Newer failed subject"
        )
        self.start_acceptance(older_task)
        newer_acceptance = self.acceptance_path(older_task)
        diagnostic = newer_acceptance / "diagnostic-δ.bin"
        diagnostic_bytes = b"preserve validator evidence\x00\xfe"
        diagnostic.write_bytes(diagnostic_bytes)

        self.acceptance_result(older_task, "fail")

        self.assertEqual(self.git(newer_acceptance, "rev-parse", "HEAD"), newer)
        self.assertEqual(self.ref_value(self.accepted_ref(older_task)), older)
        self.assertEqual(diagnostic.read_bytes(), diagnostic_bytes)
        failures = [
            event
            for event in self.telemetry_events(older_task)
            if event["operation"] == "acceptance-result"
            and event["outcome"] == "fail"
        ]
        self.assertEqual(failures[-1]["subject_sha"], newer)
        self.assert_no_retired_delivery_state(equal_task)
        self.assert_no_retired_delivery_state(older_task)

    def test_06_repeated_results_record_exact_order_without_rejected_state(self) -> None:
        task_id = "repeat-results"
        integration = self.create_task(task_id)
        first = self.commit_file(
            integration, "first.txt", b"first subject\n", "First repeated subject"
        )
        self.start_acceptance(task_id)
        for outcome in ("pass", "fail", "pass"):
            with self.subTest(outcome=outcome):
                self.acceptance_result(task_id, outcome)
        second = self.commit_file(
            integration, "second.txt", b"second subject\n", "Second repeated subject"
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "fail")

        results = [
            (event["outcome"], event["subject_sha"])
            for event in self.telemetry_events(task_id)
            if event["operation"] == "acceptance-result"
        ]
        self.assertEqual(
            results,
            [("pass", first), ("fail", first), ("pass", first), ("fail", second)],
        )
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), first)
        self.assert_no_retired_delivery_state(task_id)

    def test_06b_user_authority_projects_reports_and_cleans_without_blocking(self) -> None:
        task_id = "user-report-cleanup"
        integration = self.create_task(task_id)
        subject = self.commit_file(
            integration, "delivery.txt", b"reported user evidence\n", "Reported user evidence"
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass", "agent")
        self.acceptance_result(task_id, "pass", "user")

        status = self.success(
            self.cli(self.nested, "status", "--task-id", task_id)
        )
        self.assertEqual(status["accepted"], subject)
        self.assertEqual(status["user_accepted"], subject)
        self.mutation_success(self.land(task_id), "integration-land")

        output = self.root / "user-authority-report"
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                task_id,
                "--output-dir",
                str(output),
            ),
            "integration-remove",
        )
        self.assertEqual(self.ref_value(self.user_accepted_ref(task_id)), "")
        report = json.loads(
            (output / "orchestrate-report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            report["authorities"],
            {"accepted": subject, "landed": subject, "user_accepted": subject},
        )
        verifier_spans = [
            entry["verifier"]
            for entry in report["timeline"]
            if entry["kind"] == "acceptance"
        ]
        self.assertEqual(verifier_spans, ["agent", "user"])

    def test_07_land_requires_accepted_and_exact_single_persistence_checkout(self) -> None:
        no_accepted = "land-no-accepted"
        self.create_task(no_accepted)
        before = self.persistence_snapshot()
        self.operational_failure(
            self.land(no_accepted, "missing-persistence"),
            "integration-land",
            "no_accepted_snapshot",
        )
        self.assertEqual(self.persistence_snapshot(), before)

        parked = "land-parked"
        integration = self.create_task(parked)
        self.commit_file(
            integration, "parked.txt", b"accepted but not checked out\n", "Parked landing"
        )
        self.accept_current(parked)
        self.git(self.root, "branch", "parked-persist", self.base)
        before = self.persistence_snapshot()
        self.operational_failure(
            self.land(parked, "parked-persist"),
            "integration-land",
            "persistence_unavailable",
        )
        self.assertEqual(self.persistence_snapshot(), before)

        duplicate = "land-duplicate-occupancy"
        integration = self.create_task(duplicate)
        self.commit_file(
            integration,
            "duplicate.txt",
            b"duplicate occupancy subject\n",
            "Duplicate occupancy subject",
        )
        self.accept_current(duplicate)
        self.git(self.root, "branch", "double-persist", self.base)
        first_path = self.root / "persist-one"
        second_path = self.root / "persist-two"
        self.git(self.root, "worktree", "add", "-q", str(first_path), "double-persist")
        self.git(
            self.root,
            "worktree",
            "add",
            "-q",
            "--force",
            "--force",
            str(second_path),
            "double-persist",
        )
        occupancy = self.git(self.root, "worktree", "list", "--porcelain")
        self.assertEqual(occupancy.count("branch refs/heads/double-persist"), 2)
        before = self.authority_snapshot()
        result = self.land(duplicate, "double-persist")
        self.operational_failure(
            result, "integration-land", "persistence_unavailable"
        )
        self.assertEqual(self.authority_snapshot(), before)

    def test_08_persistence_dirt_refuses_collisions_and_preserves_noncolliding_bytes(self) -> None:
        staged_task = "land-staged"
        integration = self.create_task(staged_task)
        self.commit_file(
            integration, "staged-delivery.txt", b"accepted staged case\n", "Staged case"
        )
        self.accept_current(staged_task)
        staged = self.root / "operator-staged.bin"
        staged_bytes = b"staged operator bytes\x00\xff"
        staged.write_bytes(staged_bytes)
        self.git(self.root, "add", "operator-staged.bin")
        before = self.persistence_snapshot(("operator-staged.bin",))
        self.operational_failure(
            self.land(staged_task), "integration-land", "persistence_index_dirty"
        )
        self.assertEqual(
            self.persistence_snapshot(("operator-staged.bin",)), before
        )
        self.assertEqual(self.ref_value(self.landed_ref(staged_task)), "")
        self.git(self.root, "restore", "--staged", "operator-staged.bin")
        staged.unlink()

        untracked_task = "land-untracked-collision"
        integration = self.create_task(untracked_task)
        self.commit_file(
            integration,
            "collision.bin",
            b"accepted collision bytes\n",
            "Accepted colliding path",
        )
        self.accept_current(untracked_task)
        collision = self.root / "collision.bin"
        collision_bytes = b"untracked operator collision\x00\xfe"
        collision.write_bytes(collision_bytes)
        before = self.persistence_snapshot(("collision.bin",))
        self.operational_failure(
            self.land(untracked_task), "integration-land", "persistence_collision"
        )
        self.assertEqual(self.persistence_snapshot(("collision.bin",)), before)
        self.assertEqual(self.ref_value(self.landed_ref(untracked_task)), "")
        collision.unlink()

        unstaged_task = "land-unstaged-collision"
        integration = self.create_task(unstaged_task)
        self.commit_file(
            integration,
            "base.txt",
            b"accepted base replacement\n",
            "Accepted tracked replacement",
        )
        self.accept_current(unstaged_task)
        operator_base = b"operator tracked collision\x00\xff"
        (self.root / "base.txt").write_bytes(operator_base)
        before = self.persistence_snapshot(("base.txt",))
        self.operational_failure(
            self.land(unstaged_task), "integration-land", "persistence_collision"
        )
        self.assertEqual(self.persistence_snapshot(("base.txt",)), before)
        self.assertEqual(self.ref_value(self.landed_ref(unstaged_task)), "")
        (self.root / "base.txt").write_bytes(b"base\n")

        safe_task = "land-safe-dirt"
        integration = self.create_task(safe_task)
        accepted = self.commit_file(
            integration,
            "delivered.txt",
            b"accepted delivery\n",
            "Accepted noncolliding delivery",
        )
        self.accept_current(safe_task)
        tracked_bytes = b"operator unstaged bytes\x00\xff"
        unicode_bytes = b"non-ASCII filename bytes\x00\xfe"
        runtime_bytes = b"ordinary untracked bytes\x00\xfd"
        (self.root / "base.txt").write_bytes(tracked_bytes)
        unicode_path = self.root / "验证-δ.bin"
        runtime_path = self.root / "runtime.bin"
        unicode_path.write_bytes(unicode_bytes)
        runtime_path.write_bytes(runtime_bytes)

        self.mutation_success(self.land(safe_task), "integration-land")

        self.assertEqual((self.root / "base.txt").read_bytes(), tracked_bytes)
        self.assertEqual(unicode_path.read_bytes(), unicode_bytes)
        self.assertEqual(runtime_path.read_bytes(), runtime_bytes)
        self.assertEqual((self.root / "delivered.txt").read_bytes(), b"accepted delivery\n")
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD^{tree}"), self.git(self.root, "rev-parse", f"{accepted}^{{tree}}"))
        self.assertEqual(self.ref_value(self.landed_ref(safe_task)), accepted)
        self.assert_no_retired_delivery_state(safe_task)

        # Exercise the full ordinary-dirt matrix before the index-edge refusal.
        intent_task = "land-intent-to-add"
        integration = self.create_task(intent_task)
        self.commit_file(
            integration,
            "intent-delivery.txt",
            b"accepted intent-to-add case\n",
            "Intent-to-add case",
        )
        self.accept_current(intent_task)
        intent = self.root / "operator-intent.bin"
        intent_bytes = b"intent-to-add index bytes\x00\xfc"
        intent.write_bytes(intent_bytes)
        self.git(self.root, "add", "--intent-to-add", "operator-intent.bin")
        self.assertIn("operator-intent.bin", self.git(self.root, "ls-files"))
        before = self.persistence_snapshot(("operator-intent.bin",))
        self.operational_failure(
            self.land(intent_task), "integration-land", "persistence_index_dirty"
        )
        self.assertEqual(
            self.persistence_snapshot(("operator-intent.bin",)), before
        )
        self.assertEqual(self.ref_value(self.landed_ref(intent_task)), "")
        self.git(self.root, "update-index", "--force-remove", "operator-intent.bin")
        intent.unlink()

    def test_09_land_is_one_canonical_squash_and_landed_moves_only_after_success(self) -> None:
        task_id = "canonical-land"
        integration = self.create_task(task_id)
        accepted = self.commit_file(
            integration,
            "canonical.txt",
            b"canonical accepted tree\n",
            "Accepted source history",
        )
        self.accept_current(task_id)
        persist_before = self.git(self.root, "rev-parse", "HEAD")

        self.mutation_success(self.land(task_id), "integration-land")

        landed_commit = self.git(self.root, "rev-parse", "HEAD")
        self.assertEqual(self.git(self.root, "rev-list", "--count", f"{persist_before}..HEAD"), "1")
        self.assertEqual(self.git(self.root, "show", "-s", "--format=%P", landed_commit), persist_before)
        self.assertEqual(self.git(self.root, "show", "-s", "--format=%s", landed_commit), f"Land {task_id}")
        self.assertEqual(
            self.git(
                self.root,
                "show",
                "-s",
                "--format=%(trailers:only,unfold)",
                landed_commit,
            ).splitlines(),
            [f"Task: {task_id}", f"Landed: {accepted}"],
        )
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD^{tree}"), self.git(self.root, "rev-parse", f"{accepted}^{{tree}}"))
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), accepted)

        custom_task = "custom-subject-land"
        custom_integration = self.create_task(custom_task)
        custom_accepted = self.commit_file(
            custom_integration,
            "custom.txt",
            b"custom subject accepted tree\n",
            "Custom accepted history",
        )
        self.accept_current(custom_task)
        self.mutation_success(
            self.land(custom_task, message="Operator supplied subject"),
            "integration-land",
        )
        custom_commit = self.git(self.root, "rev-parse", "HEAD")
        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%s", custom_commit),
            "Operator supplied subject",
        )
        self.assertEqual(
            self.git(
                self.root,
                "show",
                "-s",
                "--format=%(trailers:only,unfold)",
                custom_commit,
            ).splitlines(),
            [f"Task: {custom_task}", f"Landed: {custom_accepted}"],
        )

        blocked_ref_task = "landed-ref-blocked"
        blocked_integration = self.create_task(blocked_ref_task)
        blocked_accepted = self.commit_file(
            blocked_integration,
            "blocked-ref.txt",
            b"landed authority must remain pairable\n",
            "Blocked landed ref subject",
        )
        self.accept_current(blocked_ref_task)
        nested_landed_ref = f"{self.landed_ref(blocked_ref_task)}/operator"
        self.git(self.root, "update-ref", nested_landed_ref, self.base)
        before = self.persistence_snapshot()
        self.operational_failure(
            self.land(blocked_ref_task), "integration-land", "git_error"
        )
        self.assertEqual(self.persistence_snapshot(), before)
        self.assertEqual(self.ref_value(self.landed_ref(blocked_ref_task)), "")
        self.assertEqual(self.ref_value(nested_landed_ref), self.base)
        self.assertEqual(
            self.ref_value(self.accepted_ref(blocked_ref_task)), blocked_accepted
        )

        failure_task = "land-commit-failure"
        integration = self.create_task(failure_task)
        failure_subject = self.commit_file(
            integration, "blocked.txt", b"commit hook blocks landing\n", "Blocked landing"
        )
        self.accept_current(failure_task)
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        head_before = self.git(self.root, "rev-parse", "HEAD")
        result = self.land(failure_task)
        self.operational_failure(result, "integration-land", "git_error")
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), head_before)
        self.assertEqual(self.ref_value(self.landed_ref(failure_task)), "")
        self.assertEqual(self.ref_value(self.accepted_ref(failure_task)), failure_subject)
        self.assert_no_retired_delivery_state(task_id)
        self.assert_no_retired_delivery_state(failure_task)

    def test_10_lagging_accepted_warns_and_duplicate_same_snapshot_refuses(self) -> None:
        task_id = "lag-and-duplicate"
        integration = self.create_task(task_id)
        accepted = self.commit_file(
            integration, "accepted.txt", b"lagging accepted\n", "Lagging accepted"
        )
        self.accept_current(task_id)
        current = self.commit_file(
            integration, "pending.txt", b"not accepted yet\n", "Pending newer integration"
        )
        self.assertNotEqual(accepted, current)

        payload = self.mutation_success(
            self.land(task_id), "integration-land", warnings=True
        )
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), accepted)
        landed_commit = self.git(self.root, "rev-parse", "HEAD")
        before = self.persistence_snapshot()

        self.operational_failure(
            self.land(task_id), "integration-land", "duplicate_landing"
        )

        self.assertEqual(self.persistence_snapshot(), before)
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), landed_commit)
        self.assertTrue(payload["warnings"])

    def test_11_freshness_uses_accepted_ancestry_or_landed_tree_not_history_scan(self) -> None:
        task_id = "landed-tree-current"
        integration = self.create_task(task_id)
        first = self.commit_file(
            integration, "first.txt", b"first accepted tree\n", "First accepted tree"
        )
        self.accept_current(task_id)
        self.mutation_success(self.land(task_id), "integration-land")
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), first)
        second = self.commit_file(
            integration, "second.txt", b"second accepted tree\n", "Second accepted tree"
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass")
        self.git(self.root, "commit", "-q", "--allow-empty", "-m", "Equivalent persistence tree")
        equivalent_tip = self.git(self.root, "rev-parse", "HEAD")
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD^{tree}"), self.git(self.root, "rev-parse", f"{first}^{{tree}}"))
        self.assertNotEqual(equivalent_tip, first)

        with self.subTest(freshness="landed-tree-equality"):
            self.mutation_success(self.land(task_id), "integration-land")
            self.assertEqual(self.ref_value(self.landed_ref(task_id)), second)

        stale_task = "stale-zero-mutation"
        stale_integration = self.create_task(stale_task)
        stale_accepted = self.commit_file(
            stale_integration, "stale-accepted.txt", b"accepted subject\n", "Stale accepted"
        )
        self.accept_current(stale_task)
        self.commit_file(
            self.root,
            "operator-advance.txt",
            b"outside accepted and landed authority\n",
            "Operator persistence advance",
            (f"Landed: {stale_accepted}",),
        )
        before = self.persistence_snapshot(("operator-advance.txt",))

        self.operational_failure(
            self.land(stale_task), "integration-land", "stale_persistence"
        )

        self.assertEqual(
            self.persistence_snapshot(("operator-advance.txt",)), before
        )
        self.assertEqual(self.ref_value(self.landed_ref(stale_task)), "")

    def test_12_reconcile_ancestor_is_warning_noop_before_lane_creation(self) -> None:
        task_id = "reconcile-ancestor"
        lane_id = "absorb-main"
        integration = self.create_task(task_id)
        integration_tip = self.commit_file(
            integration,
            "integration.txt",
            b"integration contains persistence ancestor\n",
            "Advance integration",
        )
        before = self.authority_snapshot()

        self.mutation_success(
            self.reconcile(task_id, lane_id),
            "integration-reconcile",
            warnings=True,
        )

        self.assertEqual(self.git(integration, "rev-parse", "HEAD"), integration_tip)
        self.assertFalse(self.lane_path(task_id, lane_id).exists())
        self.assertEqual(self.ref_value(self.lane_ref(task_id, lane_id)), "")
        self.assertEqual(self.ref_value(self.lane_base_ref(task_id, lane_id)), "")
        after = self.authority_snapshot()
        self.assertEqual(after, before)
        events = self.telemetry_events(task_id)
        self.assertEqual(
            (events[-1]["operation"], events[-1]["outcome"], events[-1]["lane_id"], events[-1]["persist"]),
            ("integration-reconcile", "noop", lane_id, self.persist),
        )

    def test_13_reconcile_leaves_exact_noff_nocommit_clean_or_conflict_state(self) -> None:
        clean_task = "reconcile-clean"
        clean_lane_id = "absorb-clean"
        clean_integration = self.create_task(clean_task)
        integration_tip = self.commit_file(
            clean_integration,
            "integration-only.txt",
            b"integration side\n",
            "Integration side",
        )
        persistence_tip = self.commit_file(
            self.root,
            "persistence-only.txt",
            b"persistence side\n",
            "Persistence side",
        )
        clean_lane = self.lane_path(clean_task, clean_lane_id)

        with self.subTest(state="clean-staged"):
            self.mutation_success(
                self.reconcile(clean_task, clean_lane_id),
                "integration-reconcile",
            )
            self.assertTrue(clean_lane.is_dir())
            if clean_lane.is_dir():
                self.assertEqual(self.git(clean_lane, "rev-parse", "HEAD"), integration_tip)
                self.assertEqual(self.ref_value(self.lane_ref(clean_task, clean_lane_id)), integration_tip)
                self.assertEqual(self.ref_value(self.lane_base_ref(clean_task, clean_lane_id)), integration_tip)
                self.assertEqual(self.merge_head(clean_lane), persistence_tip)
                self.assertEqual(
                    self.git(clean_lane, "diff", "--cached", "--name-status"),
                    "A\tpersistence-only.txt",
                )
                self.assertEqual(self.git(clean_lane, "diff", "--name-only"), "")
                self.assertEqual(self.git(clean_lane, "rev-list", "--count", f"{integration_tip}..HEAD"), "0")

        conflict_task = "reconcile-conflict"
        conflict_lane_id = "absorb-conflict"
        conflict_integration = self.create_task(conflict_task)
        conflict_integration_tip = self.commit_file(
            conflict_integration,
            "base.txt",
            b"integration conflict side\n",
            "Integration conflict side",
        )
        conflict_persist_tip = self.commit_file(
            self.root,
            "base.txt",
            b"persistence conflict side\n",
            "Persistence conflict side",
        )
        conflict_lane = self.lane_path(conflict_task, conflict_lane_id)

        with self.subTest(state="writer-conflict"):
            self.operational_failure(
                self.reconcile(conflict_task, conflict_lane_id),
                "integration-reconcile",
                "merge_conflict",
            )
            self.assertTrue(conflict_lane.is_dir())
            if conflict_lane.is_dir():
                self.assertEqual(self.git(conflict_lane, "rev-parse", "HEAD"), conflict_integration_tip)
                self.assertEqual(self.ref_value(self.lane_ref(conflict_task, conflict_lane_id)), conflict_integration_tip)
                self.assertEqual(self.ref_value(self.lane_base_ref(conflict_task, conflict_lane_id)), conflict_integration_tip)
                self.assertEqual(self.merge_head(conflict_lane), conflict_persist_tip)
                self.assertTrue(self.git(conflict_lane, "ls-files", "--unmerged"))
                self.assertIn(b"<<<<<<< HEAD", (conflict_lane / "base.txt").read_bytes())

    def test_14_writer_reconcile_commit_collect_proves_persistence_accepted_ancestry(self) -> None:
        task_id = "reconcile-collect"
        lane_id = "absorb-persistence"
        integration = self.create_task(task_id)
        integration_before = self.commit_file(
            integration,
            "integration-only.txt",
            b"integration contribution\n",
            "Integration contribution",
        )
        persistence_tip = self.commit_file(
            self.root,
            "persistence-only.txt",
            b"persistence contribution\n",
            "Persistence contribution",
        )
        self.mutation_success(
            self.reconcile(task_id, lane_id), "integration-reconcile"
        )
        lane = self.lane_path(task_id, lane_id)
        if not lane.is_dir():
            self.fail("reconciliation did not create its exact writer lane")
        self.git(lane, "commit", "-q", "-m", "Writer reconciles persistence")
        writer_tip = self.git(lane, "rev-parse", "HEAD")
        self.assertEqual(
            self.git(lane, "show", "-s", "--format=%P", writer_tip),
            f"{integration_before} {persistence_tip}",
        )
        writer_trailers = self.git(
            lane, "show", "-s", "--format=%(trailers:only,unfold)", writer_tip
        )
        self.assertNotIn("Absorbed", writer_trailers)
        self.collect_lane(task_id, lane_id)
        collected = self.git(integration, "rev-parse", "HEAD")
        self.assertEqual(
            self.git(integration, "show", "-s", "--format=%P", collected),
            f"{integration_before} {writer_tip}",
        )
        self.assertEqual(
            self.git(self.root, "merge-base", persistence_tip, collected),
            persistence_tip,
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass")
        accepted = self.ref_value(self.accepted_ref(task_id))
        self.assertEqual(accepted, collected)
        self.assertEqual(
            self.git(self.root, "merge-base", persistence_tip, accepted),
            persistence_tip,
        )
        self.assertNotIn(
            "Absorbed",
            self.git(
                integration,
                "show",
                "-s",
                "--format=%(trailers:only,unfold)",
                collected,
            ),
        )
        self.mutation_success(self.land(task_id), "integration-land")
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), accepted)

    def test_15_equal_tree_accepted_is_nothing_to_land_but_absent_authority_wins(self) -> None:
        absent_task = "no-change-absent"
        absent_integration = self.create_task(absent_task)
        self.commit_file(
            absent_integration,
            "temporary.txt",
            b"temporary change\n",
            "Temporary change",
        )
        self.git(absent_integration, "rm", "temporary.txt")
        self.git(absent_integration, "commit", "-q", "-m", "Revert temporary change")
        before = self.persistence_snapshot()
        self.operational_failure(
            self.land(absent_task),
            "integration-land",
            "no_accepted_snapshot",
        )
        self.assertEqual(self.persistence_snapshot(), before)

        accepted_task = "no-change-accepted"
        accepted_integration = self.create_task(accepted_task)
        self.commit_file(
            accepted_integration,
            "temporary-two.txt",
            b"temporary accepted change\n",
            "Temporary accepted change",
        )
        self.git(accepted_integration, "rm", "temporary-two.txt")
        self.git(
            accepted_integration,
            "commit",
            "-q",
            "-m",
            "Revert accepted change",
        )
        accepted = self.accept_current(accepted_task)
        self.assertNotEqual(accepted, self.base)
        self.assertEqual(
            self.git(self.root, "rev-parse", f"{accepted}^{{tree}}"),
            self.git(self.root, "rev-parse", f"{self.base}^{{tree}}"),
        )
        before = self.persistence_snapshot()

        self.operational_failure(
            self.land(accepted_task), "integration-land", "nothing_to_land"
        )

        self.assertEqual(self.persistence_snapshot(), before)
        self.assertEqual(self.ref_value(self.accepted_ref(accepted_task)), accepted)
        self.assertEqual(self.ref_value(self.landed_ref(accepted_task)), "")
        self.assert_no_retired_delivery_state(absent_task)
        self.assert_no_retired_delivery_state(accepted_task)

    def test_16_failed_landing_rolls_back_forward_transition_and_operator_dirt(
        self,
    ) -> None:
        task_id = "rollback-after-forward-transition"
        integration = self.create_task(task_id)
        first = self.commit_file(
            integration,
            "first-delivery.txt",
            b"first accepted delivery\n",
            "First accepted delivery",
        )
        self.accept_current(task_id)
        self.mutation_success(self.land(task_id), "integration-land")
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), first)

        second = self.commit_file(
            integration,
            "second-delivery.txt",
            b"second accepted delivery\n",
            "Second accepted delivery",
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass")
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), second)
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), first)

        operator_bytes = b"noncolliding tracked operator dirt\x00\xff"
        (self.root / "base.txt").write_bytes(operator_bytes)
        operator_status = run_git(
            self.root, "status", "--porcelain=v1", "--untracked-files=all"
        ).stdout.encode()
        self.assertEqual(operator_status, b" M base.txt\n")
        before = self.persistence_snapshot(
            ("base.txt", "first-delivery.txt", "second-delivery.txt")
        )
        persistence_tip = str(before["head"])
        accepted_before = self.ref_value(self.accepted_ref(task_id))
        landed_before = self.ref_value(self.landed_ref(task_id))

        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        result = self.land(task_id)

        self.operational_failure(result, "integration-land", "git_error")
        self.assertEqual(
            self.persistence_snapshot(
                ("base.txt", "first-delivery.txt", "second-delivery.txt")
            ),
            before,
        )
        self.assertEqual((self.root / "base.txt").read_bytes(), operator_bytes)
        self.assertEqual(
            run_git(
                self.root, "status", "--porcelain=v1", "--untracked-files=all"
            ).stdout.encode(),
            operator_status,
        )
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), accepted_before)
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), landed_before)
        self.assertEqual(
            self.git(self.root, "rev-list", "--count", f"{persistence_tip}..HEAD"),
            "0",
        )
        self.assertFalse((self.root / "second-delivery.txt").exists())

    def test_17_authority_slots_require_exact_direct_commit_refs(self) -> None:
        accepted_task = "symbolic-accepted-slot"
        accepted_integration = self.create_task(accepted_task)
        accepted_subject = self.commit_file(
            accepted_integration,
            "symbolic-accepted.txt",
            b"symbolic accepted slot subject\n",
            "Symbolic accepted slot subject",
        )
        self.start_acceptance(accepted_task)
        accepted_target = "refs/heads/operator-accepted-target"
        self.git(
            self.root,
            "branch",
            accepted_target.removeprefix("refs/heads/"),
            self.base,
        )
        self.git(
            self.root,
            "symbolic-ref",
            self.accepted_ref(accepted_task),
            accepted_target,
        )
        accepted_before = {
            "persistence": self.persistence_snapshot(("base.txt",)),
            "acceptance": self.checkout_snapshot(
                self.acceptance_path(accepted_task),
                ("base.txt", "symbolic-accepted.txt"),
            ),
        }

        with self.subTest(slot="symbolic-accepted-on-pass"):
            self.operational_failure(
                self.cli(
                    self.nested,
                    "acceptance",
                    "result",
                    "--task-id",
                    accepted_task,
                    "--outcome",
                    "pass",
                    "--verifier",
                    "agent",
                ),
                "acceptance-result",
                "task_state_invalid",
            )
            self.assertEqual(
                {
                    "persistence": self.persistence_snapshot(("base.txt",)),
                    "acceptance": self.checkout_snapshot(
                        self.acceptance_path(accepted_task),
                        ("base.txt", "symbolic-accepted.txt"),
                    ),
                },
                accepted_before,
            )
            self.assertEqual(
                self.git(
                    self.root,
                    "symbolic-ref",
                    "-q",
                    self.accepted_ref(accepted_task),
                    check=False,
                ),
                accepted_target,
            )
            self.assertEqual(self.ref_value(accepted_target), self.base)
            self.assertEqual(
                self.git(self.acceptance_path(accepted_task), "rev-parse", "HEAD"),
                accepted_subject,
            )

        landed_task = "symbolic-landed-slot"
        landed_integration = self.create_task(landed_task)
        landed_subject = self.commit_file(
            landed_integration,
            "symbolic-landed.txt",
            b"symbolic landed slot subject\n",
            "Symbolic landed slot subject",
        )
        self.accept_current(landed_task)
        landed_target = "refs/heads/operator-landed-target"
        self.git(
            self.root,
            "branch",
            landed_target.removeprefix("refs/heads/"),
            self.base,
        )
        self.git(
            self.root,
            "symbolic-ref",
            self.landed_ref(landed_task),
            landed_target,
        )
        landed_before = {
            "persistence": self.persistence_snapshot(
                ("base.txt", "symbolic-landed.txt")
            ),
            "acceptance": self.checkout_snapshot(
                self.acceptance_path(landed_task),
                ("base.txt", "symbolic-landed.txt"),
            ),
        }

        with self.subTest(slot="symbolic-landed-on-land"):
            self.operational_failure(
                self.land(landed_task),
                "integration-land",
                "task_state_invalid",
            )
            self.assertEqual(
                {
                    "persistence": self.persistence_snapshot(
                        ("base.txt", "symbolic-landed.txt")
                    ),
                    "acceptance": self.checkout_snapshot(
                        self.acceptance_path(landed_task),
                        ("base.txt", "symbolic-landed.txt"),
                    ),
                },
                landed_before,
            )
            self.assertEqual(
                self.git(
                    self.root,
                    "symbolic-ref",
                    "-q",
                    self.landed_ref(landed_task),
                    check=False,
                ),
                landed_target,
            )
            self.assertEqual(self.ref_value(landed_target), self.base)
            self.assertEqual(
                self.ref_value(self.accepted_ref(landed_task)), landed_subject
            )

        blob_task = "noncommit-landed-slot"
        blob_integration = self.create_task(blob_task)
        blob_subject = self.commit_file(
            blob_integration,
            "blob-landed.txt",
            b"noncommit landed slot subject\n",
            "Noncommit landed slot subject",
        )
        self.accept_current(blob_task)
        blob_source = self.task_root(blob_task) / "authority-slot-blob.bin"
        blob_source.write_bytes(b"operator noncommit authority bytes\x00\xff")
        blob = self.git(self.root, "hash-object", "-w", str(blob_source))
        blob_source.unlink()
        self.git(self.root, "update-ref", self.landed_ref(blob_task), blob)
        blob_before = {
            "persistence": self.persistence_snapshot(("base.txt", "blob-landed.txt")),
            "acceptance": self.checkout_snapshot(
                self.acceptance_path(blob_task),
                ("base.txt", "blob-landed.txt"),
            ),
        }

        with self.subTest(slot="exact-landed-noncommit"):
            self.operational_failure(
                self.land(blob_task),
                "integration-land",
                "task_state_invalid",
            )
            self.assertEqual(
                {
                    "persistence": self.persistence_snapshot(
                        ("base.txt", "blob-landed.txt")
                    ),
                    "acceptance": self.checkout_snapshot(
                        self.acceptance_path(blob_task),
                        ("base.txt", "blob-landed.txt"),
                    ),
                },
                blob_before,
            )
            self.assertEqual(self.ref_value(self.landed_ref(blob_task)), blob)
            self.assertEqual(
                self.git(self.root, "cat-file", "-t", self.landed_ref(blob_task)),
                "blob",
            )
            self.assertEqual(self.ref_value(self.accepted_ref(blob_task)), blob_subject)

    def test_18_reconcile_validates_single_persistence_checkout_before_noop(self) -> None:
        missing_task = "reconcile-missing-persistence"
        missing_lane = "absorb-missing"
        missing_integration = self.create_task(missing_task)
        self.commit_file(
            missing_integration,
            "missing-integration.txt",
            b"integration remains authoritative\n",
            "Integration without named persistence",
        )
        before = self.authority_snapshot()

        with self.subTest(occupancy="missing"):
            result = self.reconcile(missing_task, missing_lane, "missing-persist")
            self.assertEqual(self.authority_snapshot(), before)
            self.operational_failure(
                result,
                "integration-reconcile",
                "task_state_invalid",
            )

        unchecked_task = "reconcile-unchecked-persistence"
        unchecked_lane = "absorb-unchecked"
        unchecked_integration = self.create_task(unchecked_task)
        self.commit_file(
            unchecked_integration,
            "unchecked-integration.txt",
            b"integration contains unchecked persistence\n",
            "Integration above unchecked persistence",
        )
        self.git(self.root, "branch", "unchecked-persist", self.base)
        before = self.authority_snapshot()

        with self.subTest(occupancy="unchecked"):
            result = self.reconcile(
                unchecked_task, unchecked_lane, "unchecked-persist"
            )
            self.assertEqual(self.authority_snapshot(), before)
            self.operational_failure(
                result,
                "integration-reconcile",
                "task_state_invalid",
            )

        duplicate_task = "reconcile-duplicate-persistence"
        duplicate_lane = "absorb-duplicate"
        duplicate_integration = self.create_task(duplicate_task)
        self.commit_file(
            duplicate_integration,
            "duplicate-integration.txt",
            b"integration contains duplicate persistence\n",
            "Integration above duplicate persistence",
        )
        self.git(self.root, "branch", "duplicate-persist", self.base)
        first_path = self.root / "reconcile-persist-one"
        second_path = self.root / "reconcile-persist-two"
        self.git(
            self.root,
            "worktree",
            "add",
            "-q",
            str(first_path),
            "duplicate-persist",
        )
        self.git(
            self.root,
            "worktree",
            "add",
            "-q",
            "--force",
            "--force",
            str(second_path),
            "duplicate-persist",
        )
        self.assertEqual(
            self.git(self.root, "worktree", "list", "--porcelain").count(
                "branch refs/heads/duplicate-persist"
            ),
            2,
        )
        before = self.authority_snapshot()

        with self.subTest(occupancy="duplicate"):
            result = self.reconcile(
                duplicate_task, duplicate_lane, "duplicate-persist"
            )
            self.assertEqual(self.authority_snapshot(), before)
            self.operational_failure(
                result,
                "integration-reconcile",
                "task_state_invalid",
            )

    def test_19_landed_tree_equality_is_independently_current(self) -> None:
        task_id = "independent-landed-tree-current"
        integration = self.create_task(task_id)
        accepted = self.commit_file(
            integration,
            "accepted-only.txt",
            b"accepted divergent delivery\n",
            "Accepted divergent delivery",
        )
        self.accept_current(task_id)
        persistence_tip = self.commit_file(
            self.root,
            "persistence-only.txt",
            b"persistence divergent state\n",
            "Divergent persistence state",
        )
        persistence_tree = self.git(self.root, "rev-parse", "HEAD^{tree}")
        unrelated_landed = self.git(
            self.root,
            "commit-tree",
            persistence_tree,
            "-m",
            "Unrelated landed authority",
        )
        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%P", unrelated_landed),
            "",
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", f"{unrelated_landed}^{{tree}}"),
            persistence_tree,
        )
        self.assertNotEqual(
            run_git(
                self.root,
                "merge-base",
                "--is-ancestor",
                unrelated_landed,
                accepted,
                check=False,
            ).returncode,
            0,
        )
        self.assertEqual(
            self.git(self.root, "merge-base", persistence_tip, accepted), self.base
        )
        self.git(
            self.root,
            "update-ref",
            self.landed_ref(task_id),
            unrelated_landed,
        )

        self.mutation_success(self.land(task_id), "integration-land")

        landed_commit = self.git(self.root, "rev-parse", "HEAD")
        accepted_tree = self.git(self.root, "rev-parse", f"{accepted}^{{tree}}")
        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%P", landed_commit),
            persistence_tip,
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", "HEAD^{tree}"), accepted_tree
        )
        self.assertEqual(self.ref_value("refs/heads/main"), landed_commit)
        self.assertEqual(self.ref_value(self.integration_ref(task_id)), accepted)
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), accepted)
        self.assertEqual(self.ref_value(self.landed_ref(task_id)), accepted)
        self.assertTrue((self.root / "accepted-only.txt").is_file())
        self.assertFalse((self.root / "persistence-only.txt").exists())

    def test_20_agent_pass_with_absent_accepted_closes_clean_named_lane(self) -> None:
        task_id = "cycle-b-clean-close"
        integration = self.create_task(task_id)
        lane_id = "clean-close"
        lane = self.create_lane(task_id, lane_id)
        original_base = self.ref_value(self.lane_base_ref(task_id, lane_id))
        self.assertEqual(original_base, self.base)
        self.commit_file(
            lane,
            "clean.txt",
            b"ready for acceptance closure\n",
            "Clean lane delivery",
        )
        self.collect_lane(task_id, lane_id, "cycle-b-clean-ticket")
        subject = self.git(integration, "rev-parse", "HEAD")
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), "")

        self.start_acceptance(task_id)
        payload = self.acceptance_result(task_id, "pass", "agent")

        self.assertIsNone(payload["previous_sha"])
        self.assertEqual(payload["current_sha"], subject)
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), subject)
        self.assert_lane_closed(task_id, lane_id)

    def test_21_lagging_agent_pass_closes_only_collects_in_forward_interval(self) -> None:
        task_id = "cycle-b-lagging-interval"
        integration = self.create_task(task_id)
        accepted_subject = self.commit_file(
            integration,
            "accepted.txt",
            b"accepted interval lower bound\n",
            "Accepted interval lower bound",
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass", "agent")
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), accepted_subject)

        lanes: list[tuple[str, str]] = []
        for index in range(1, 5):
            lane_id = f"interval-{index:02d}"
            lane = self.create_lane(task_id, lane_id)
            original_base = self.ref_value(self.lane_base_ref(task_id, lane_id))
            self.assertIsNotNone(original_base)
            self.commit_file(
                lane,
                f"{lane_id}.txt",
                f"{lane_id}\n".encode(),
                f"Collect {lane_id}",
            )
            self.collect_lane(task_id, lane_id, f"cycle-b-interval-{index:02d}")
            lanes.append((lane_id, original_base))

        subject = self.git(integration, "rev-parse", "HEAD")
        subject_three = self.git(
            integration,
            "rev-parse",
            "HEAD~1",
        )
        self.start_acceptance(task_id, subject_three)
        payload = self.acceptance_result(task_id, "pass", "agent")

        self.assertEqual(payload["previous_sha"], accepted_subject)
        self.assertEqual(payload["current_sha"], subject_three)
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), subject_three)
        for lane_id, _original_base in lanes[:3]:
            self.assert_lane_closed(task_id, lane_id)
        self.assert_lane_retained(task_id, lanes[3][0], lanes[3][1])
        self.assertNotEqual(subject, subject_three)

    def test_22_agent_pass_retains_tracked_and_untracked_dirty_named_lanes(self) -> None:
        task_id = "cycle-b-dirty-retain"
        integration = self.create_task(task_id)
        lane_ids = ("tracked-dirty", "untracked-dirty")
        original_bases: dict[str, str] = {}
        for lane_id in lane_ids:
            lane = self.create_lane(task_id, lane_id)
            original_base = self.ref_value(self.lane_base_ref(task_id, lane_id))
            assert original_base is not None
            original_bases[lane_id] = original_base
            self.commit_file(
                lane,
                f"{lane_id}.txt",
                f"{lane_id}\n".encode(),
                f"Collect {lane_id}",
            )
            self.collect_lane(task_id, lane_id, f"cycle-b-dirty-{lane_id}")

        subject = self.git(integration, "rev-parse", "HEAD")
        tracked = self.lane_path(task_id, "tracked-dirty")
        untracked = self.lane_path(task_id, "untracked-dirty")
        (tracked / "tracked-dirty.txt").write_bytes(b"tracked dirt\n")
        (untracked / "operator-output.bin").write_bytes(b"untracked dirt\x00\xff")

        self.start_acceptance(task_id)
        payload = self.acceptance_result(task_id, "pass", "agent")

        self.assertTrue(payload["ref_updated"])
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), subject)
        for lane_id in lane_ids:
            self.assert_lane_retained(task_id, lane_id, original_bases[lane_id])
            self.assert_named_warning(payload, lane_id)

    def test_23_agent_pass_retains_named_lane_with_new_uncollected_work(self) -> None:
        task_id = "cycle-b-new-work"
        integration = self.create_task(task_id)
        accepted_subject = self.commit_file(
            integration,
            "accepted.txt",
            b"accepted before lane work\n",
            "Accepted before lane work",
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass", "agent")

        lane_id = "new-work"
        lane = self.create_lane(task_id, lane_id)
        original_base = self.ref_value(self.lane_base_ref(task_id, lane_id))
        assert original_base is not None
        self.commit_file(lane, "initial.txt", b"initial\n", "Initial lane work")
        self.collect_lane(task_id, lane_id, "cycle-b-new-work-collect")
        subject = self.git(integration, "rev-parse", "HEAD")
        self.commit_file(lane, "rework.txt", b"new uncollected work\n", "New lane work")

        self.start_acceptance(task_id, subject)
        payload = self.acceptance_result(task_id, "pass", "agent")

        self.assertEqual(payload["current_sha"], subject)
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), subject)
        self.assert_lane_retained(task_id, lane_id, original_base)
        self.assert_named_warning(payload, lane_id)
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), subject)
        self.assertNotEqual(accepted_subject, subject)

    def test_24_agent_pass_retains_lane_with_newer_collect_beyond_subject(self) -> None:
        task_id = "cycle-b-newer-collect"
        integration = self.create_task(task_id)
        accepted_subject = self.commit_file(
            integration,
            "accepted.txt",
            b"accepted before collect history\n",
            "Accepted before collect history",
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass", "agent")

        lane_id = "newer-collect"
        lane = self.create_lane(task_id, lane_id)
        original_base = self.ref_value(self.lane_base_ref(task_id, lane_id))
        assert original_base is not None
        self.commit_file(lane, "first.txt", b"first\n", "First collect")
        self.collect_lane(task_id, lane_id, "cycle-b-first-collect")
        accepted_interval_subject = self.git(integration, "rev-parse", "HEAD")
        self.commit_file(lane, "second.txt", b"second\n", "Second collect")
        self.collect_lane(task_id, lane_id, "cycle-b-second-collect")
        latest = self.git(integration, "rev-parse", "HEAD")

        self.start_acceptance(task_id, accepted_interval_subject)
        payload = self.acceptance_result(task_id, "pass", "agent")

        self.assertEqual(payload["current_sha"], accepted_interval_subject)
        self.assertEqual(
            self.ref_value(self.accepted_ref(task_id)), accepted_interval_subject
        )
        self.assert_lane_retained(task_id, lane_id, original_base)
        self.assert_named_warning(payload, lane_id)
        self.assertNotEqual(accepted_subject, accepted_interval_subject)
        self.assertNotEqual(latest, accepted_interval_subject)

    def test_25_user_pass_never_closes_a_named_lane(self) -> None:
        task_id = "cycle-b-user-no-close"
        integration = self.create_task(task_id)
        lane_id = "user-keeps"
        lane = self.create_lane(task_id, lane_id)
        original_base = self.ref_value(self.lane_base_ref(task_id, lane_id))
        assert original_base is not None
        self.commit_file(lane, "user.txt", b"user verifier lane\n", "User verifier lane")
        self.collect_lane(task_id, lane_id, "cycle-b-user-ticket")
        subject = self.git(integration, "rev-parse", "HEAD")

        self.start_acceptance(task_id)
        payload = self.acceptance_result(task_id, "pass", "user")

        self.assertEqual(payload["verifier"], "user")
        self.assertEqual(self.ref_value(self.user_accepted_ref(task_id)), subject)
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), "")
        self.assert_lane_retained(task_id, lane_id, original_base)

    def test_26_agent_regression_preserves_warning_and_never_reopens_closed_lane(self) -> None:
        task_id = "cycle-b-regression-no-reopen"
        integration = self.create_task(task_id)
        older = self.commit_file(
            integration,
            "older.txt",
            b"older accepted subject\n",
            "Older accepted subject",
        )
        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass", "agent")

        lane_id = "regression-closed"
        lane = self.create_lane(task_id, lane_id)
        self.commit_file(lane, "closed.txt", b"close me\n", "Close on agent pass")
        self.collect_lane(task_id, lane_id, "cycle-b-regression-ticket")
        newer = self.git(integration, "rev-parse", "HEAD")

        self.start_acceptance(task_id)
        self.acceptance_result(task_id, "pass", "agent")
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), newer)

        self.start_acceptance(task_id, older)
        payload = self.acceptance_result(task_id, "pass", "agent")

        self.assertTrue(payload["regressed"])
        self.assertTrue(any("regressed" in warning for warning in payload["warnings"]))
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), older)
        self.assert_lane_closed(task_id, lane_id)

    def test_27_agent_pass_retains_clean_lane_when_later_cleanup_step_fails(self) -> None:
        task_id = "cycle-c-cleanup-failure"
        integration = self.create_task(task_id)
        lane_id = "cleanup-failure"
        lane = self.create_lane(task_id, lane_id)
        original_base = self.ref_value(self.lane_base_ref(task_id, lane_id))
        self.assertEqual(original_base, self.base)
        self.commit_file(
            lane,
            "retained.bin",
            b"lane bytes before cleanup failure\x00\xff\n",
            "Clean lane ready for failure-safe closure",
        )
        self.collect_lane(task_id, lane_id, "cycle-c-cleanup-failure-ticket")
        subject = self.git(integration, "rev-parse", "HEAD")
        lane_tip = self.git(lane, "rev-parse", "HEAD")
        lane_status = run_git(
            lane, "status", "--porcelain=v1", "--untracked-files=all"
        ).stdout.encode()
        lane_index = run_git(lane, "ls-files", "--stage").stdout.encode()
        lane_bytes = {
            path.relative_to(lane).as_posix(): path.read_bytes()
            for path in sorted(lane.rglob("*"))
            if path.is_file() and path.relative_to(lane).as_posix() != ".git"
        }
        before_worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        before_lane_entry = next(
            entry
            for entry in before_worktrees.split("\n\n")
            if f"worktree {lane}" in entry
        )

        self.start_acceptance(task_id)
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        assert real_git is not None
        with tempfile.TemporaryDirectory(prefix="orchestrate-git-wrapper-") as wrapper_root:
            wrapper = Path(wrapper_root) / "git"
            branch = self.lane_ref(task_id, lane_id).removeprefix("refs/heads/")
            wrapper.write_text(
                "#!/bin/sh\n"
                f'if [ "$#" -eq 3 ] && [ "$1" = "branch" ] && [ "$2" = "-D" ] && [ "$3" = {shlex.quote(branch)} ]; then\n'
                '  printf "%s\\n" "forced branch deletion failure" >&2\n'
                "  exit 71\n"
                "fi\n"
                f"exec {shlex.quote(real_git)} \"$@\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
            result = run_cli(
                self.nested,
                "acceptance",
                "result",
                "--task-id",
                task_id,
                "--verifier",
                "agent",
                "--outcome",
                "pass",
                env={"PATH": f"{wrapper_root}{os.pathsep}{os.environ['PATH']}"},
            )

        payload = self.success(result)
        self.assertEqual(payload["operation"], "acceptance-result")
        self.assertEqual(payload["verifier"], "agent")
        self.assertEqual(payload["subject_sha"], subject)
        self.assertTrue(payload["ref_updated"])
        self.assertEqual(self.ref_value(self.accepted_ref(task_id)), subject)
        self.assert_named_warning(payload, lane_id)

        self.assertTrue(lane.is_dir())
        self.assertEqual(self.ref_value(self.lane_ref(task_id, lane_id)), lane_tip)
        self.assertEqual(self.ref_value(self.lane_base_ref(task_id, lane_id)), original_base)
        self.assertEqual(self.git(lane, "rev-parse", "HEAD"), lane_tip)
        self.assertEqual(
            run_git(lane, "status", "--porcelain=v1", "--untracked-files=all").stdout.encode(),
            lane_status,
        )
        self.assertEqual(run_git(lane, "ls-files", "--stage").stdout.encode(), lane_index)
        self.assertEqual(
            {
                path.relative_to(lane).as_posix(): path.read_bytes()
                for path in sorted(lane.rglob("*"))
                if path.is_file() and path.relative_to(lane).as_posix() != ".git"
            },
            lane_bytes,
        )
        after_worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        self.assertIn(before_lane_entry, after_worktrees)
