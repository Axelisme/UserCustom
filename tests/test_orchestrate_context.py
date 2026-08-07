from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from tests._orchestrate_version import SOURCE_SKILL_VERSION
from tests._orchestrate_cli_support import (
    OrchestrateCliRepositoryTestCase,
    VERIFIED_SKILL,
)


class CloseableTracerContractTests(OrchestrateCliRepositoryTestCase):
    """T001 Contract through the shipped subprocess seam."""

    task_id = "closeable-tracer"
    lane_id = "clean-lane"

    @property
    def integration_path(self) -> Path:
        return self.root / ".agent_state" / "worktrees" / self.task_id / "integration"

    @property
    def acceptance_path(self) -> Path:
        return self.root / ".agent_state" / "worktrees" / self.task_id / "acceptance"

    @property
    def lane_path(self) -> Path:
        return (
            self.root
            / ".agent_state"
            / "worktrees"
            / self.task_id
            / "lanes"
            / self.lane_id
        )

    @property
    def telemetry_path(self) -> Path:
        return self.telemetry_for(self.task_id)

    def task_worktree(self, task_id: str, member: str) -> Path:
        return self.root / ".agent_state" / "worktrees" / task_id / member

    def telemetry_for(self, task_id: str) -> Path:
        return self.task_worktree(task_id, "telemetry.jsonl")

    def seed_task_refs(self, task_id: str) -> None:
        self.git(
            self.root,
            "update-ref",
            f"refs/orchestrate/{task_id}/integration/base",
            self.base,
        )
        self.git(self.root, "branch", f"wave/{task_id}/integration", self.base)

    def create_task(self) -> None:
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "create",
                "--task-id",
                self.task_id,
            ),
            "integration-create",
        )

    def agent_acceptance_result(self, task_id: str, outcome: str = "pass") -> dict[str, object]:
        payload = self.success(
            self.cli(
                self.nested,
                "acceptance",
                "result",
                "--task-id",
                task_id,
                "--verifier",
                "agent",
                "--outcome",
                outcome,
            )
        )
        self.assertEqual(payload["operation"], "acceptance-result")
        self.assertEqual(payload["verifier"], "agent")
        return payload

    def assert_task_git_inventory_absent(self) -> None:
        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname)",
                f"refs/orchestrate/{self.task_id}/",
            ),
            "",
        )
        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname)",
                f"refs/heads/wave/{self.task_id}/",
            ),
            "",
        )
        worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        self.assertNotIn(str(self.integration_path), worktrees)
        self.assertNotIn(str(self.acceptance_path), worktrees)
        self.assertNotIn(str(self.lane_path), worktrees)

    def test_help_exposes_only_the_exact_grammar(self) -> None:
        # assert_help_surface compares the command tuple and the long-option
        # set for equality, so a retired option or subcommand cannot survive
        # anywhere in this list.
        self.assert_help_surface(
            (),
            commands=(
                "show",
                "status",
                "lane",
                "integration",
                "acceptance",
                "report",
                "pin",
                "doctor",
                "release",
            ),
            long_options=("--skill-dir", "--version"),
        )
        self.assert_help_surface(("show",))
        self.assert_help_surface(
            ("lane",),
            commands=("create", "check", "sync", "drop", "commit", "comment"),
        )
        self.assert_help_surface(
            ("integration",),
            commands=("create", "collect", "reconcile", "land", "remove"),
        )
        self.assert_help_surface(("acceptance",), commands=("start", "result"))
        self.assert_help_surface(("pin",), commands=("status", "set"))
        self.assert_help_surface(
            ("doctor",), commands=("diff",), long_options=("--path",)
        )
        self.assert_help_surface(
            ("status",), long_options=("--task-id", "--step")
        )
        self.assert_help_surface(
            ("lane", "create"), long_options=("--task-id", "--lane-id", "--comment")
        )
        self.assert_help_surface(
            ("lane", "comment"),
            long_options=("--task-id", "--lane-id", "--text", "--clear"),
        )
        self.assert_help_surface(
            ("lane", "check"),
            long_options=("--task-id", "--lane-id", "--expect-mode"),
        )
        self.assert_help_surface(
            ("lane", "sync"), long_options=("--task-id", "--lane-id")
        )
        self.assert_help_surface(
            ("lane", "drop"), long_options=("--task-id", "--lane-id")
        )
        self.assert_help_surface(
            ("lane", "commit"),
            long_options=(
                "--task-id",
                "--lane-id",
                "--message-file",
                "--contract",
                "--amend-frozen",
            ),
        )
        self.assert_help_surface(
            ("integration", "create"), long_options=("--task-id",)
        )
        self.assert_help_surface(
            ("integration", "collect"),
            long_options=("--task-id", "--lane-id", "--ticket"),
        )
        self.assert_help_surface(
            ("integration", "reconcile"),
            long_options=("--task-id", "--lane-id", "--persist"),
        )
        self.assert_help_surface(
            ("integration", "land"),
            long_options=("--task-id", "--persist", "--message"),
        )
        self.assert_help_surface(
            ("integration", "remove"),
            long_options=(
                "--task-id",
                "--output-dir",
                "--no-report",
                "--abandon",
            ),
        )
        self.assert_help_surface(
            ("acceptance", "start"), long_options=("--task-id", "--sha")
        )
        self.assert_help_surface(
            ("acceptance", "result"),
            long_options=("--task-id", "--outcome", "--verifier"),
        )
        self.assert_help_surface(
            ("report",), long_options=("--task-id", "--output-dir")
        )
        self.assert_help_surface(("pin", "status"))
        self.assert_help_surface(("pin", "set"))
        self.assert_help_surface(("doctor", "diff"), long_options=("--runtime",))
        self.assert_help_surface(
            ("release",), long_options=("--version", "--drop")
        )
        acceptance_result_help = self.assert_help_surface(
            ("acceptance", "result"),
            long_options=("--task-id", "--outcome", "--verifier"),
        )
        self.assertIn("{pass,fail}", acceptance_result_help)
        self.assertIn("{agent,user}", acceptance_result_help)
        doctor_diff_help = self.assert_help_surface(
            ("doctor", "diff"), long_options=("--runtime",)
        )
        self.assertIn("{codex,claude,pi}", doctor_diff_help)

    def test_non_repository_and_parser_failures_use_cli_usage_envelopes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="orchestrate-not-repo-") as tmp:
            self.operational_failure(
                self.cli(Path(tmp), "status"),
                "status",
                "not_git_repository",
            )

        before = self.managed_state_snapshot()
        self.operational_failure(
            self.cli(self.nested, "integration", "create"),
            "cli",
            "cli_usage",
        )
        self.assertEqual(self.managed_state_snapshot(), before)

    def test_repository_status_uses_only_sorted_integration_base_refs(self) -> None:
        for task_id in ("beta", "alpha"):
            self.git(
                self.root,
                "update-ref",
                f"refs/orchestrate/{task_id}/integration/base",
                self.base,
            )
        self.git(self.root, "branch", "wave/branch-only/integration", self.base)
        self.git(
            self.root,
            "update-ref",
            "refs/orchestrate/lane-only/docs/base",
            self.base,
        )
        self.git(
            self.root,
            "update-ref",
            "refs/orchestrate/accepted-only/accepted",
            self.base,
        )
        self.git(
            self.root,
            "update-ref",
            "refs/orchestrate/landed-only/landed",
            self.base,
        )
        worktree_only = self.task_worktree("worktree-only", "integration")
        worktree_only.parent.mkdir(parents=True)
        self.git(
            self.root,
            "worktree",
            "add",
            "-q",
            "--detach",
            str(worktree_only),
            self.base,
        )
        telemetry_only = self.telemetry_for("telemetry-only")
        telemetry_only.parent.mkdir(parents=True, exist_ok=True)
        telemetry_only.write_bytes(b'{"lookalike":true}\n')

        self.assertEqual(
            self.success(self.cli(self.nested, "status")),
            {
                "ok": True,
                "operation": "status",
                "orchestrate_version": self.orchestrate_version,
                "tasks": ["alpha", "beta"],
            },
        )

    def test_task_status_sorts_lanes_and_omits_absent_optional_slots(self) -> None:
        task_id = "status-shape"
        self.seed_task_refs(task_id)
        for lane_id in ("docs", "api"):
            self.git(
                self.root,
                "update-ref",
                f"refs/orchestrate/{task_id}/{lane_id}/base",
                self.base,
            )
            self.git(self.root, "branch", f"wave/{task_id}/{lane_id}", self.base)

        payload = self.success(self.cli(self.nested, "status", "--task-id", task_id))
        self.assertEqual(
            payload,
            {
                "ok": True,
                "operation": "status",
                "orchestrate_version": self.orchestrate_version,
                "task_id": task_id,
                "integration": self.base,
                "lanes": {
                    "api": {"sha": self.base, "uncollected": 0},
                    "docs": {"sha": self.base, "uncollected": 0},
                },
                "pending": 0,
                "collect_rounds": {},
            },
        )
        self.assertEqual(list(payload["lanes"]), ["api", "docs"])
        for omitted in ("acceptance", "accepted", "landed", "warnings", "lane_consumption"):
            self.assertNotIn(omitted, payload)

        acceptance = self.task_worktree(task_id, "acceptance")
        acceptance.parent.mkdir(parents=True, exist_ok=True)
        self.git(
            self.root, "worktree", "add", "-q", "--detach", str(acceptance), self.base
        )
        self.git(
            self.root,
            "update-ref",
            f"refs/orchestrate/{task_id}/accepted",
            self.base,
        )
        self.git(
            self.root,
            "update-ref",
            f"refs/orchestrate/{task_id}/landed",
            self.base,
        )
        self.assertEqual(
            self.success(self.cli(self.nested, "status", "--task-id", task_id)),
            {
                "ok": True,
                "operation": "status",
                "orchestrate_version": self.orchestrate_version,
                "task_id": task_id,
                "integration": self.base,
                "lanes": {
                    "api": {"sha": self.base, "uncollected": 0},
                    "docs": {"sha": self.base, "uncollected": 0},
                },
                "pending": 0,
                "collect_rounds": {},
                "accepted": self.base,
                "landed": self.base,
            },
        )

    def test_task_status_bounds_partial_resource_anomaly_warnings(self) -> None:
        task_id = "status-anomalies"
        self.seed_task_refs(task_id)
        for number in range(25):
            self.git(
                self.root,
                "update-ref",
                f"refs/orchestrate/{task_id}/orphan-{number:02d}/base",
                self.base,
            )

        payload = self.success(self.cli(self.nested, "status", "--task-id", task_id))
        self.assertEqual(
            set(payload),
            {
                "ok",
                "operation",
                "orchestrate_version",
                "task_id",
                "integration",
                "lanes",
                "pending",
                "collect_rounds",
                "warnings",
                "step",
            },
        )
        self.assertEqual(payload["lanes"], {})
        self.assertEqual(payload["pending"], 0)
        self.assertEqual(
            payload["step"],
            {
                "n": 2,
                "open": [
                    "SKILL.md#Step 2 — Create lane",
                    "references/admission.md#S1 — Slice admission",
                    "SKILL.md#Exceptions to the main sequence",
                ],
            },
        )
        self.assertIsInstance(payload["warnings"], list)
        self.assertGreater(len(payload["warnings"]), 0)
        self.assertLessEqual(len(payload["warnings"]), 20)
        self.assertTrue(
            all(isinstance(item, str) and item for item in payload["warnings"])
        )
        self.assertTrue(all(str(self.root) not in item for item in payload["warnings"]))

    def test_task_status_warns_for_direct_lane_branch_without_base_ref(self) -> None:
        task_id = "status-branch-only"
        self.seed_task_refs(task_id)
        self.git(self.root, "branch", f"wave/{task_id}/branch-only", self.base)

        payload = self.success(self.cli(self.nested, "status", "--task-id", task_id))
        expected_keys = {
            "ok",
            "operation",
            "orchestrate_version",
            "task_id",
            "integration",
            "lanes",
            "pending",
            "collect_rounds",
            "warnings",
            "step",
        }
        with self.subTest(assertion="exact-schema"):
            self.assertEqual(set(payload), expected_keys)
        with self.subTest(assertion="required-slots"):
            self.assertEqual(payload.get("task_id"), task_id)
            self.assertEqual(payload.get("integration"), self.base)
            self.assertEqual(payload.get("lanes"), {})
            self.assertEqual(payload.get("pending"), 0)
            self.assertEqual(payload.get("collect_rounds"), {})
            self.assertEqual(
                payload.get("step"),
                {
                    "n": 2,
                    "open": [
                        "SKILL.md#Step 2 — Create lane",
                        "references/admission.md#S1 — Slice admission",
                        "SKILL.md#Exceptions to the main sequence",
                    ],
                },
            )
        for optional in ("acceptance", "accepted", "landed", "lane_consumption"):
            with self.subTest(assertion="optional-slot-omitted", slot=optional):
                self.assertNotIn(optional, payload)
        warnings = payload.get("warnings", [])
        with self.subTest(assertion="bounded-nonempty-warnings"):
            self.assertIsInstance(warnings, list)
            self.assertGreater(len(warnings), 0)
            self.assertLessEqual(len(warnings), 20)
        with self.subTest(assertion="non-path-warning-text"):
            self.assertTrue(
                all(isinstance(item, str) and item for item in warnings)
            )
            self.assertTrue(all(str(self.root) not in item for item in warnings))
            self.assertTrue(all(".agent_state" not in item for item in warnings))
        with self.subTest(assertion="no-fabricated-lane-sha"):
            self.assertNotIn("branch-only", payload.get("lanes", {}))

    def test_base_discriminator_with_invalid_integration_ref_refuses(self) -> None:
        for task_id, dangling in (
            ("missing-integration", False),
            ("dangling-integration", True),
        ):
            with self.subTest(task_id=task_id):
                self.git(
                    self.root,
                    "update-ref",
                    f"refs/orchestrate/{task_id}/integration/base",
                    self.base,
                )
                if dangling:
                    self.git(
                        self.root,
                        "symbolic-ref",
                        f"refs/heads/wave/{task_id}/integration",
                        "refs/heads/does-not-exist",
                    )
                self.operational_failure(
                    self.cli(self.nested, "status", "--task-id", task_id),
                    "status",
                    "task_state_invalid",
                )

    def test_nested_cwd_status_and_create_use_the_exact_compact_contract(self) -> None:
        self.assertEqual(
            self.success(self.cli(self.nested, "status")),
            {
                "ok": True,
                "operation": "status",
                "orchestrate_version": self.orchestrate_version,
                "tasks": [],
            },
        )

        self.create_task()

        self.assertTrue(self.integration_path.is_dir())
        self.assertFalse(self.acceptance_path.exists())
        self.assertEqual(
            self.git(self.integration_path, "rev-parse", "HEAD"), self.base
        )
        self.assertEqual(
            self.git(
                self.root,
                "rev-parse",
                f"refs/orchestrate/{self.task_id}/integration/base",
            ),
            self.base,
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", f"wave/{self.task_id}/integration"),
            self.base,
        )
        self.assertTrue(self.telemetry_path.is_file())
        telemetry_lines = self.telemetry_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(telemetry_lines), 1)
        event = json.loads(telemetry_lines[0])
        self.assertEqual(
            set(event),
            {"event_version", "at", "task_id", "operation", "outcome", "orchestrate_version", "repo_pin"},
        )
        self.assertEqual(event["event_version"], 1)
        self.assertEqual(event["orchestrate_version"], SOURCE_SKILL_VERSION)
        # This repo fixture carries no pin, and the field says so rather than being absent.
        self.assertIsNone(event["repo_pin"])
        self.assertEqual(event["task_id"], self.task_id)
        self.assertEqual(event["operation"], "integration-create")
        self.assertEqual(event["outcome"], "success")
        self.assertIsInstance(event["at"], str)
        self.assertTrue(event["at"])

        self.assertEqual(
            self.success(self.cli(self.nested, "status")),
            {
                "ok": True,
                "operation": "status",
                "orchestrate_version": self.orchestrate_version,
                "tasks": [self.task_id],
            },
        )
        self.assertEqual(
            self.success(self.cli(self.nested, "status", "--task-id", self.task_id)),
            {
                "ok": True,
                "operation": "status",
                "orchestrate_version": self.orchestrate_version,
                "task_id": self.task_id,
                "integration": self.base,
                "lanes": {},
                "pending": 0,
                "collect_rounds": {},
            },
        )

    def test_clean_lane_acceptance_land_and_remove_leave_no_managed_resources(
        self,
    ) -> None:
        self.create_task()
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                self.task_id,
                "--lane-id",
                self.lane_id,
            ),
            "lane-create",
        )
        self.assertTrue(self.lane_path.is_dir())
        self.assertEqual(self.git(self.lane_path, "rev-parse", "HEAD"), self.base)
        self.assertEqual(
            self.git(
                self.root,
                "rev-parse",
                f"refs/orchestrate/{self.task_id}/{self.lane_id}/base",
            ),
            self.base,
        )

        lane_tip = self.commit_lane(self.lane_path)
        self.lane_check_success(
            self.cli(
                self.nested,
                "lane",
                "check",
                "--task-id",
                self.task_id,
                "--lane-id",
                self.lane_id,
            )
        )
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "collect",
                "--task-id",
                self.task_id,
                "--lane-id",
                self.lane_id,
                "--ticket",
                "context-clean-ticket",
            ),
            "integration-collect",
        )

        integration_tip = self.git(
            self.root, "rev-parse", f"wave/{self.task_id}/integration"
        )
        self.assertEqual(
            self.git(self.root, "show", "-s", "--format=%P", integration_tip),
            f"{self.base} {lane_tip}",
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", f"{integration_tip}^{{tree}}"),
            self.git(self.root, "rev-parse", f"{lane_tip}^{{tree}}"),
        )
        collect_trailers = self.git(
            self.root,
            "show",
            "-s",
            "--format=%(trailers:only,unfold)",
            integration_tip,
        ).splitlines()
        self.assertIn(f"Task: {self.task_id}", collect_trailers)
        self.assertIn(f"Lane: {self.lane_id}", collect_trailers)
        self.assertIn("Ticket: context-clean-ticket", collect_trailers)
        self.assertTrue(self.lane_path.is_dir())
        self.assertEqual(
            self.git(
                self.root,
                "show-ref",
                "--verify",
                f"refs/heads/wave/{self.task_id}/{self.lane_id}",
            ),
            f"{lane_tip} refs/heads/wave/{self.task_id}/{self.lane_id}",
        )
        self.assertEqual(
            self.git(
                self.root,
                "show-ref",
                "--verify",
                f"refs/orchestrate/{self.task_id}/{self.lane_id}/base",
            ),
            f"{self.base} refs/orchestrate/{self.task_id}/{self.lane_id}/base",
        )
        self.assertEqual(
            self.success(self.cli(self.nested, "status", "--task-id", self.task_id)),
            {
                "ok": True,
                "operation": "status",
                "orchestrate_version": self.orchestrate_version,
                "task_id": self.task_id,
                "integration": integration_tip,
                "lanes": {
                    self.lane_id: {"sha": lane_tip, "uncollected": 0},
                },
                "pending": 1,
                "collect_rounds": {"context-clean-ticket": 1},
                "step": {
                    "n": 6,
                    "open": [
                        "SKILL.md#Step 6 — Start acceptance",
                        "references/admission.md#S4 — Review and validation",
                    ],
                },
            },
        )

        self.mutation_success(
            self.cli(
                self.nested,
                "acceptance",
                "start",
                "--task-id",
                self.task_id,
            ),
            "acceptance-start",
        )
        self.assertTrue(self.acceptance_path.is_dir())
        self.assertEqual(
            self.git(self.acceptance_path, "rev-parse", "HEAD"), integration_tip
        )
        self.assertEqual(
            self.git(
                self.acceptance_path,
                "symbolic-ref",
                "-q",
                "HEAD",
                check=False,
            ),
            "",
        )
        self.agent_acceptance_result(self.task_id)
        self.assertEqual(
            self.git(
                self.root,
                "rev-parse",
                f"refs/orchestrate/{self.task_id}/accepted",
            ),
            integration_tip,
        )
        # Agent acceptance closes the clean persistent lane before any later
        # landing or task cleanup command runs.
        self.assertFalse(self.lane_path.exists())
        self.assertEqual(
            self.git(
                self.root,
                "show-ref",
                "--verify",
                f"refs/heads/wave/{self.task_id}/{self.lane_id}",
                check=False,
            ),
            "",
        )
        self.assertEqual(
            self.git(
                self.root,
                "show-ref",
                "--verify",
                f"refs/orchestrate/{self.task_id}/{self.lane_id}/base",
                check=False,
            ),
            "",
        )

        before_land = self.git(self.root, "rev-parse", "main")
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "land",
                "--task-id",
                self.task_id,
                "--persist",
                "main",
            ),
            "integration-land",
        )
        landed_commit = self.git(self.root, "rev-parse", "main")
        self.assertNotEqual(landed_commit, before_land)
        self.assertEqual(
            self.git(self.root, "rev-list", "--count", f"{before_land}..main"), "1"
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", "main^{tree}"),
            self.git(self.root, "rev-parse", f"{integration_tip}^{{tree}}"),
        )
        trailers = self.git(
            self.root,
            "show",
            "-s",
            "--format=%(trailers:only,unfold)",
            landed_commit,
        ).splitlines()
        self.assertIn(f"Task: {self.task_id}", trailers)
        self.assertIn(f"Landed: {integration_tip}", trailers)
        self.assertEqual(
            self.git(
                self.root,
                "rev-parse",
                f"refs/orchestrate/{self.task_id}/landed",
            ),
            integration_tip,
        )
        self.assertEqual(
            self.success(self.cli(self.nested, "status", "--task-id", self.task_id)),
            {
                "ok": True,
                "operation": "status",
                "orchestrate_version": self.orchestrate_version,
                "task_id": self.task_id,
                "integration": integration_tip,
                "lanes": {},
                "pending": 0,
                "collect_rounds": {"context-clean-ticket": 1},
                "accepted": integration_tip,
                "landed": integration_tip,
            },
        )

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                self.task_id,
                "--no-report",
            ),
            "integration-remove",
        )
        self.assert_task_git_inventory_absent()
        self.assertFalse(self.integration_path.exists())
        self.assertFalse(self.acceptance_path.exists())
        self.assertFalse(self.telemetry_path.exists())
        self.assertEqual((self.root / "delivered.txt").read_bytes(), b"delivered\n")
        self.assertEqual(self.git(self.root, "status", "--porcelain"), "")

    def test_acceptance_start_ignores_tracked_and_index_dirty_integration(
        self,
    ) -> None:
        for dirt_kind in ("tracked-unstaged", "staged-index"):
            task_id = f"start-{dirt_kind}"
            integration = self.task_worktree(task_id, "integration")
            acceptance = self.task_worktree(task_id, "acceptance")
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
            subject = self.git(integration, "rev-parse", "HEAD")
            tracked = integration / "base.txt"
            tracked_bytes = f"{dirt_kind} integration bytes\n".encode()
            tracked.write_bytes(tracked_bytes)
            if dirt_kind == "staged-index":
                self.git(integration, "add", "base.txt")
            status_before = self.git(integration, "status", "--porcelain")

            self.mutation_success(
                self.cli(
                    self.nested,
                    "acceptance",
                    "start",
                    "--task-id",
                    task_id,
                ),
                "acceptance-start",
            )

            with self.subTest(dirt_kind=dirt_kind):
                self.assertEqual(self.git(acceptance, "rev-parse", "HEAD"), subject)
                self.assertEqual(tracked.read_bytes(), tracked_bytes)
                self.assertEqual(
                    self.git(integration, "status", "--porcelain"), status_before
                )
                self.assertEqual(self.git(acceptance, "status", "--porcelain"), "")

    def test_acceptance_start_uses_managed_ref_when_integration_checkout_switched(
        self,
    ) -> None:
        task_id = "start-wrong-branch"
        integration = self.task_worktree(task_id, "integration")
        acceptance = self.task_worktree(task_id, "acceptance")
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
        subject = self.git(
            self.root, "rev-parse", f"refs/heads/wave/{task_id}/integration"
        )
        wrong_branch = "operator-preserve-acceptance-start"
        self.git(integration, "switch", "-c", wrong_branch)
        branch_before = self.git(integration, "symbolic-ref", "--short", "HEAD")

        self.mutation_success(
            self.cli(
                self.nested,
                "acceptance",
                "start",
                "--task-id",
                task_id,
            ),
            "acceptance-start",
        )

        self.assertEqual(self.git(acceptance, "rev-parse", "HEAD"), subject)
        self.assertEqual(
            self.git(integration, "symbolic-ref", "--short", "HEAD"), branch_before
        )

    def test_acceptance_pass_allows_untracked_and_ignored_runtime_artifacts(
        self,
    ) -> None:
        task_id = "pass-runtime-artifacts"
        integration = self.task_worktree(task_id, "integration")
        acceptance = self.task_worktree(task_id, "acceptance")
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
        (integration / "accepted-subject.txt").write_bytes(b"accepted subject\n")
        self.git(integration, "add", "accepted-subject.txt")
        self.git(integration, "commit", "-q", "-m", "Advance acceptance subject")
        subject = self.git(integration, "rev-parse", "HEAD")
        self.mutation_success(
            self.cli(
                self.nested,
                "acceptance",
                "start",
                "--task-id",
                task_id,
            ),
            "acceptance-start",
        )
        self.assertEqual(self.git(acceptance, "rev-parse", "HEAD"), subject)
        self.assertEqual(
            self.git(acceptance, "symbolic-ref", "-q", "HEAD", check=False),
            "",
        )

        untracked = acceptance / "runtime-output.bin"
        ignored = acceptance / ".agent_state" / "runtime" / "ignored-output.bin"
        untracked_bytes = b"ordinary runtime artifact\x00\xff"
        ignored_bytes = b"ignored runtime artifact\x00\xfe"
        untracked.write_bytes(untracked_bytes)
        ignored.parent.mkdir(parents=True)
        ignored.write_bytes(ignored_bytes)
        self.assertEqual(
            self.git(acceptance, "status", "--porcelain"),
            "?? runtime-output.bin",
        )
        self.assertEqual(
            self.git(
                acceptance,
                "check-ignore",
                ".agent_state/runtime/ignored-output.bin",
            ),
            ".agent_state/runtime/ignored-output.bin",
        )

        result = self.agent_acceptance_result(task_id)

        with self.subTest(assertion="pass-succeeds"):
            self.assertEqual(result["current_sha"], subject)
        with self.subTest(assertion="accepted-is-exact-head"):
            self.assertEqual(
                self.git(
                    self.root,
                    "show-ref",
                    "--hash",
                    f"refs/orchestrate/{task_id}/accepted",
                    check=False,
                ),
                subject,
            )
        with self.subTest(assertion="untracked-bytes-preserved"):
            self.assertTrue(untracked.is_file())
            if untracked.is_file():
                self.assertEqual(untracked.read_bytes(), untracked_bytes)
        with self.subTest(assertion="ignored-bytes-preserved"):
            self.assertTrue(ignored.is_file())
            if ignored.is_file():
                self.assertEqual(ignored.read_bytes(), ignored_bytes)

    def test_acceptance_pass_rejects_tracked_and_index_dirt_without_advancing(
        self,
    ) -> None:
        for dirt_kind in ("tracked-unstaged", "staged-index"):
            task_id = f"pass-{dirt_kind}"
            integration = self.task_worktree(task_id, "integration")
            acceptance = self.task_worktree(task_id, "acceptance")
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
            self.mutation_success(
                self.cli(
                    self.nested,
                    "acceptance",
                    "start",
                    "--task-id",
                    task_id,
                ),
                "acceptance-start",
            )
            self.agent_acceptance_result(task_id)
            accepted_ref = f"refs/orchestrate/{task_id}/accepted"
            accepted_before = self.git(self.root, "show-ref", "--hash", accepted_ref)

            (integration / "new-subject.txt").write_bytes(b"new subject\n")
            self.git(integration, "add", "new-subject.txt")
            self.git(integration, "commit", "-q", "-m", "New validation subject")
            subject = self.git(integration, "rev-parse", "HEAD")
            self.assertNotEqual(subject, accepted_before)
            self.mutation_success(
                self.cli(
                    self.nested,
                    "acceptance",
                    "start",
                    "--task-id",
                    task_id,
                ),
                "acceptance-start",
            )

            tracked = acceptance / "base.txt"
            tracked_bytes = f"{dirt_kind} acceptance bytes\n".encode()
            tracked.write_bytes(tracked_bytes)
            if dirt_kind == "staged-index":
                self.git(acceptance, "add", "base.txt")
            status_before = self.git(acceptance, "status", "--porcelain")
            expected = (
                "M  base.txt" if dirt_kind == "staged-index" else "M base.txt"
            )
            with self.subTest(dirt_kind=dirt_kind, assertion="arranged-dirt"):
                self.assertEqual(status_before, expected)
            before = self.managed_state_snapshot()

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
            after = self.managed_state_snapshot()

            with self.subTest(dirt_kind=dirt_kind, assertion="stable-refusal"):
                self.operational_failure(
                    result,
                    "acceptance-result",
                    "acceptance_subject_invalid",
                )
            with self.subTest(dirt_kind=dirt_kind, assertion="exact-zero-mutation"):
                self.assertEqual(after, before)
            with self.subTest(dirt_kind=dirt_kind, assertion="accepted-preserved"):
                self.assertEqual(
                    self.git(
                        self.root,
                        "show-ref",
                        "--hash",
                        accepted_ref,
                        check=False,
                    ),
                    accepted_before,
                )
            with self.subTest(dirt_kind=dirt_kind, assertion="dirt-preserved"):
                self.assertEqual(tracked.read_bytes(), tracked_bytes)
                self.assertEqual(
                    self.git(acceptance, "status", "--porcelain"),
                    status_before,
                )

    def test_reverted_to_base_task_removes_without_an_empty_landing(self) -> None:
        self.create_task()
        main_before = self.git(self.root, "rev-parse", "main")
        commit_count_before = self.git(self.root, "rev-list", "--count", "main")

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                self.task_id,
                "--no-report",
            ),
            "integration-remove",
            warnings=True,
        )

        self.assert_task_git_inventory_absent()
        self.assertEqual(self.git(self.root, "rev-parse", "main"), main_before)
        self.assertEqual(
            self.git(self.root, "rev-list", "--count", "main"), commit_count_before
        )
        self.assertFalse(self.telemetry_path.exists())

    def test_no_change_remove_refuses_an_active_lane_without_mutation(self) -> None:
        self.create_task()
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                self.task_id,
                "--lane-id",
                self.lane_id,
            ),
            "lane-create",
        )
        sentinel = self.lane_path / "writer-sentinel.bin"
        sentinel_bytes = b"active lane must survive\x00\xff"
        sentinel.write_bytes(sentinel_bytes)
        lane_branch = f"refs/heads/wave/{self.task_id}/{self.lane_id}"
        lane_base = f"refs/orchestrate/{self.task_id}/{self.lane_id}/base"
        lane_branch_before = self.git(self.root, "show-ref", "--hash", lane_branch)
        lane_base_before = self.git(self.root, "show-ref", "--hash", lane_base)
        before = self.managed_state_snapshot()

        result = self.cli(
            self.nested,
            "integration",
            "remove",
            "--task-id",
            self.task_id,
            "--no-report",
        )
        after = self.managed_state_snapshot()

        with self.subTest(assertion="zero-mutation"):
            self.assertEqual(after, before)
        with self.subTest(assertion="stable-refusal"):
            self.operational_failure(result, "integration-remove", "task_incomplete")
        with self.subTest(assertion="lane-worktree"):
            self.assertTrue(self.lane_path.is_dir())
        with self.subTest(assertion="lane-branch"):
            self.assertEqual(
                self.git(
                    self.root,
                    "show-ref",
                    "--hash",
                    lane_branch,
                    check=False,
                ),
                lane_branch_before,
            )
        with self.subTest(assertion="lane-base"):
            self.assertEqual(
                self.git(
                    self.root,
                    "show-ref",
                    "--hash",
                    lane_base,
                    check=False,
                ),
                lane_base_before,
            )
        with self.subTest(assertion="sentinel-bytes"):
            self.assertTrue(sentinel.is_file())
            if sentinel.is_file():
                self.assertEqual(sentinel.read_bytes(), sentinel_bytes)

    def test_explicit_abandon_discards_only_exact_closed_inventory(self) -> None:
        self.create_task()
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                self.task_id,
                "--lane-id",
                self.lane_id,
            ),
            "lane-create",
        )
        (self.lane_path / "writer-dirt.bin").write_bytes(b"discard me\x00")
        unknown_branch = f"refs/heads/wave/{self.task_id}/operator/nested"
        unknown_ref = f"refs/orchestrate/{self.task_id}/operator/nested"
        self.git(self.root, "update-ref", unknown_branch, self.base)
        self.git(self.root, "update-ref", unknown_ref, self.base)
        unknown_branch_before = self.git(
            self.root, "show-ref", "--hash", unknown_branch
        )
        unknown_ref_before = self.git(self.root, "show-ref", "--hash", unknown_ref)
        unknown = (
            self.root
            / ".agent_state"
            / "worktrees"
            / self.task_id
            / "operator"
            / "evidence.bin"
        )
        unknown.parent.mkdir()
        unknown_bytes = b"not orchestrate-owned\x00\xff"
        unknown.write_bytes(unknown_bytes)

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                self.task_id,
                "--no-report",
                "--abandon",
            ),
            "integration-remove",
        )

        for exact_ref in (
            f"refs/orchestrate/{self.task_id}/integration/base",
            f"refs/orchestrate/{self.task_id}/{self.lane_id}/base",
            f"refs/heads/wave/{self.task_id}/integration",
            f"refs/heads/wave/{self.task_id}/{self.lane_id}",
        ):
            with self.subTest(exact_ref=exact_ref):
                self.assertEqual(
                    self.git(
                        self.root,
                        "show-ref",
                        "--verify",
                        exact_ref,
                        check=False,
                    ),
                    "",
                )
        worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        for exact_worktree in (
            self.integration_path,
            self.acceptance_path,
            self.lane_path,
        ):
            with self.subTest(exact_worktree=exact_worktree):
                self.assertNotIn(str(exact_worktree), worktrees)
        with self.subTest(unknown="nested-branch"):
            self.assertEqual(
                self.git(
                    self.root,
                    "show-ref",
                    "--hash",
                    unknown_branch,
                    check=False,
                ),
                unknown_branch_before,
            )
        with self.subTest(unknown="nested-ref"):
            self.assertEqual(
                self.git(
                    self.root,
                    "show-ref",
                    "--hash",
                    unknown_ref,
                    check=False,
                ),
                unknown_ref_before,
            )
        with self.subTest(unknown="task-directory-bytes"):
            self.assertTrue(unknown.is_file())
            if unknown.is_file():
                self.assertEqual(unknown.read_bytes(), unknown_bytes)
        with self.subTest(exact_resource="telemetry"):
            self.assertFalse(self.telemetry_path.exists())

    def test_abandon_discovers_exact_lanes_from_refs_branches_and_worktrees(self) -> None:
        self.create_task()
        lane_ids = ("missing-base", "missing-worktree", "path-only")
        lane_paths = {
            lane_id: self.task_worktree(self.task_id, f"lanes/{lane_id}")
            for lane_id in lane_ids
        }
        for lane_id in lane_ids:
            self.mutation_success(
                self.cli(
                    self.nested,
                    "lane",
                    "create",
                    "--task-id",
                    self.task_id,
                    "--lane-id",
                    lane_id,
                ),
                "lane-create",
            )

        missing_base = lane_paths["missing-base"]
        self.git(
            self.root,
            "update-ref",
            "-d",
            f"refs/orchestrate/{self.task_id}/missing-base/base",
        )
        (missing_base / "writer-dirt.bin").write_bytes(b"discard partial lane\x00")

        self.git(
            self.root,
            "worktree",
            "remove",
            str(lane_paths["missing-worktree"]),
        )

        path_only = lane_paths["path-only"]
        self.git(path_only, "switch", "--detach")
        self.git(self.root, "branch", "-D", f"wave/{self.task_id}/path-only")
        self.git(
            self.root,
            "update-ref",
            "-d",
            f"refs/orchestrate/{self.task_id}/path-only/base",
        )

        unknown_branch = f"refs/heads/wave/{self.task_id}/operator/nested"
        unknown_ref = f"refs/orchestrate/{self.task_id}/operator/nested"
        self.git(self.root, "update-ref", unknown_branch, self.base)
        self.git(self.root, "update-ref", unknown_ref, self.base)
        unknown_branch_before = self.git(
            self.root, "show-ref", "--hash", unknown_branch
        )
        unknown_ref_before = self.git(self.root, "show-ref", "--hash", unknown_ref)
        unknown = self.task_worktree(self.task_id, "operator/evidence.bin")
        unknown.parent.mkdir(parents=True)
        unknown_bytes = b"operator-owned task bytes\x00\xff"
        unknown.write_bytes(unknown_bytes)

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                self.task_id,
                "--no-report",
                "--abandon",
            ),
            "integration-remove",
        )

        exact_refs = [
            f"refs/orchestrate/{self.task_id}/integration/base",
            f"refs/heads/wave/{self.task_id}/integration",
        ]
        for lane_id in lane_ids:
            exact_refs.extend(
                (
                    f"refs/orchestrate/{self.task_id}/{lane_id}/base",
                    f"refs/heads/wave/{self.task_id}/{lane_id}",
                )
            )
        for exact_ref in exact_refs:
            with self.subTest(exact_ref=exact_ref):
                self.assertEqual(
                    self.git(
                        self.root,
                        "show-ref",
                        "--verify",
                        exact_ref,
                        check=False,
                    ),
                    "",
                )

        worktrees = self.git(self.root, "worktree", "list", "--porcelain")
        for exact_path in (self.integration_path, *lane_paths.values()):
            with self.subTest(exact_path=exact_path):
                self.assertNotIn(str(exact_path), worktrees)
        with self.subTest(unknown="nested-branch"):
            self.assertEqual(
                self.git(
                    self.root,
                    "show-ref",
                    "--hash",
                    unknown_branch,
                    check=False,
                ),
                unknown_branch_before,
            )
        with self.subTest(unknown="nested-ref"):
            self.assertEqual(
                self.git(
                    self.root,
                    "show-ref",
                    "--hash",
                    unknown_ref,
                    check=False,
                ),
                unknown_ref_before,
            )
        with self.subTest(unknown="task-directory-bytes"):
            self.assertTrue(unknown.is_file())
            if unknown.is_file():
                self.assertEqual(unknown.read_bytes(), unknown_bytes)
        with self.subTest(exact_resource="telemetry"):
            self.assertFalse(self.telemetry_path.exists())

    def test_two_lane_revert_to_base_tree_removes_without_persistence_commit(
        self,
    ) -> None:
        self.create_task()
        main_before = self.git(self.root, "rev-parse", "main")
        commit_count_before = self.git(self.root, "rev-list", "--count", "main")

        change_lane_id = "add-change"
        change_lane = self.task_worktree(self.task_id, f"lanes/{change_lane_id}")
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                self.task_id,
                "--lane-id",
                change_lane_id,
            ),
            "lane-create",
        )
        self.commit_lane(change_lane)
        self.lane_check_success(
            self.cli(
                self.nested,
                "lane",
                "check",
                "--task-id",
                self.task_id,
                "--lane-id",
                change_lane_id,
            )
        )
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "collect",
                "--task-id",
                self.task_id,
                "--lane-id",
                change_lane_id,
                "--ticket",
                "context-add-change-ticket",
            ),
            "integration-collect",
        )

        revert_lane_id = "revert-change"
        revert_lane = self.task_worktree(self.task_id, f"lanes/{revert_lane_id}")
        self.mutation_success(
            self.cli(
                self.nested,
                "lane",
                "create",
                "--task-id",
                self.task_id,
                "--lane-id",
                revert_lane_id,
            ),
            "lane-create",
        )
        self.git(revert_lane, "rm", "delivered.txt")
        self.git(revert_lane, "commit", "-q", "-m", "Revert delivered tree")
        self.lane_check_success(
            self.cli(
                self.nested,
                "lane",
                "check",
                "--task-id",
                self.task_id,
                "--lane-id",
                revert_lane_id,
            )
        )
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "collect",
                "--task-id",
                self.task_id,
                "--lane-id",
                revert_lane_id,
                "--ticket",
                "context-revert-change-ticket",
            ),
            "integration-collect",
        )

        integration_tip = self.git(
            self.root, "rev-parse", f"wave/{self.task_id}/integration"
        )
        self.assertNotEqual(integration_tip, self.base)
        self.assertEqual(
            self.git(self.root, "rev-parse", f"{integration_tip}^{{tree}}"),
            self.git(self.root, "rev-parse", f"{self.base}^{{tree}}"),
        )
        self.mutation_success(
            self.cli(
                self.nested,
                "acceptance",
                "start",
                "--task-id",
                self.task_id,
            ),
            "acceptance-start",
        )
        self.agent_acceptance_result(self.task_id)

        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "remove",
                "--task-id",
                self.task_id,
                "--no-report",
            ),
            "integration-remove",
            warnings=True,
        )

        self.assert_task_git_inventory_absent()
        self.assertFalse(self.telemetry_path.exists())
        self.assertEqual(self.git(self.root, "rev-parse", "main"), main_before)
        self.assertEqual(
            self.git(self.root, "rev-list", "--count", "main"),
            commit_count_before,
        )

    def test_normal_remove_refuses_clean_wrong_integration_branch_atomically(
        self,
    ) -> None:
        self.create_task()
        wrong_branch = "operator-preserve"
        self.git(self.integration_path, "switch", "-c", wrong_branch)
        self.assertEqual(self.git(self.integration_path, "status", "--porcelain"), "")
        sentinel = self.task_worktree(self.task_id, "operator/evidence.bin")
        sentinel.parent.mkdir(parents=True)
        sentinel_bytes = b"preserve clean wrong-branch evidence\x00\xff"
        sentinel.write_bytes(sentinel_bytes)
        wrong_branch_before = self.git(
            self.root, "show-ref", "--hash", f"refs/heads/{wrong_branch}"
        )
        before = self.managed_state_snapshot()

        result = self.cli(
            self.nested,
            "integration",
            "remove",
            "--task-id",
            self.task_id,
            "--no-report",
        )
        after = self.managed_state_snapshot()

        with self.subTest(assertion="stable-refusal"):
            self.operational_failure(
                result,
                "integration-remove",
                "worktree_identity_mismatch",
            )
        with self.subTest(assertion="zero-mutation"):
            self.assertEqual(after, before)
        with self.subTest(assertion="wrong-branch-preserved"):
            self.assertEqual(
                self.git(
                    self.root,
                    "show-ref",
                    "--hash",
                    f"refs/heads/{wrong_branch}",
                    check=False,
                ),
                wrong_branch_before,
            )
        with self.subTest(assertion="sentinel-bytes"):
            self.assertTrue(sentinel.is_file())
            if sentinel.is_file():
                self.assertEqual(sentinel.read_bytes(), sentinel_bytes)

    def test_normal_remove_refuses_dirty_exact_integration_atomically(self) -> None:
        self.create_task()
        sentinel = self.integration_path / "writer-sentinel.bin"
        sentinel_bytes = b"preserve integration dirt\x00\xff"
        sentinel.write_bytes(sentinel_bytes)
        before = self.managed_state_snapshot()

        result = self.cli(
            self.nested,
            "integration",
            "remove",
            "--task-id",
            self.task_id,
            "--no-report",
        )
        after = self.managed_state_snapshot()

        with self.subTest(assertion="stable-refusal"):
            self.operational_failure(
                result,
                "integration-remove",
                "dirty_worktree",
            )
        with self.subTest(assertion="zero-mutation"):
            self.assertEqual(after, before)
        with self.subTest(assertion="sentinel-bytes"):
            self.assertTrue(sentinel.is_file())
            if sentinel.is_file():
                self.assertEqual(sentinel.read_bytes(), sentinel_bytes)

    def test_integration_create_uses_the_callers_current_head(self) -> None:
        (self.nested / "caller-head.txt").write_text("caller head\n", encoding="utf-8")
        self.git(self.root, "add", "project/nested/caller-head.txt")
        self.git(self.root, "commit", "-q", "-m", "advance caller head")
        caller_head = self.git(self.root, "rev-parse", "HEAD")
        self.assertNotEqual(caller_head, self.base)

        task_id = "caller-head"
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
        integration = self.task_worktree(task_id, "integration")
        self.assertEqual(self.git(integration, "rev-parse", "HEAD"), caller_head)
        self.assertEqual(
            self.git(
                self.root,
                "rev-parse",
                f"refs/orchestrate/{task_id}/integration/base",
            ),
            caller_head,
        )
        self.assertEqual(
            self.git(self.root, "rev-parse", f"wave/{task_id}/integration"),
            caller_head,
        )
        self.assertFalse(self.task_worktree(task_id, "acceptance").exists())
        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname)",
                f"refs/orchestrate/{task_id}/accepted",
                f"refs/orchestrate/{task_id}/landed",
            ),
            "",
        )
        lines = self.telemetry_for(task_id).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            set(json.loads(lines[0])),
            {"event_version", "at", "task_id", "operation", "outcome", "orchestrate_version", "repo_pin"},
        )

    def test_invalid_slug_refuses_with_exact_error_and_zero_mutation(self) -> None:
        invalid = ["Upper", ".leading", "has/slash", "has space", "unicodé", ""]
        for task_id in invalid:
            with self.subTest(task_id=task_id):
                self.operational_failure(
                    self.cli(
                        self.nested,
                        "integration",
                        "create",
                        "--task-id",
                        task_id,
                    ),
                    "integration-create",
                    "invalid_identifier",
                )
                self.assertFalse((self.root / ".agent_state").exists())
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "create",
                "--task-id",
                "a0.valid_slug-1",
            ),
            "integration-create",
        )

    def test_frozen_slug_grammar_accepts_task_and_lane_ids_without_normalizing(
        self,
    ) -> None:
        accepted_task_ids = ("a", "0", "a.b_c-d", "z9._-")
        for task_id in accepted_task_ids:
            with self.subTest(kind="task", identifier=task_id):
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
                self.assertEqual(
                    self.git(self.root, "rev-parse", f"wave/{task_id}/integration"),
                    self.base,
                )

        task_id = "lane-slugs"
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
        for lane_id in ("a", "0", "a.b_c-d", "z9._-"):
            with self.subTest(kind="lane", identifier=lane_id):
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
                self.assertEqual(
                    self.git(self.root, "rev-parse", f"wave/{task_id}/{lane_id}"),
                    self.base,
                )

    def test_task_inventory_collision_refuses_before_any_partial_mutation(self) -> None:
        self.create_task()
        refs_before = self.git(
            self.root,
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            f"refs/orchestrate/{self.task_id}/",
            f"refs/heads/wave/{self.task_id}/",
        )
        worktrees_before = self.git(self.root, "worktree", "list", "--porcelain")
        telemetry_before = self.telemetry_path.read_bytes()

        self.operational_failure(
            self.cli(
                self.nested,
                "integration",
                "create",
                "--task-id",
                self.task_id,
            ),
            "integration-create",
            "task_resource_collision",
        )

        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname) %(objectname)",
                f"refs/orchestrate/{self.task_id}/",
                f"refs/heads/wave/{self.task_id}/",
            ),
            refs_before,
        )
        self.assertEqual(
            self.git(self.root, "worktree", "list", "--porcelain"),
            worktrees_before,
        )
        self.assertEqual(self.telemetry_path.read_bytes(), telemetry_before)

    def test_each_individual_task_inventory_collision_refuses_atomically(self) -> None:
        collision_classes = (
            "integration-base-ref",
            "accepted-ref",
            "landed-ref",
            "lane-base-ref",
            "integration-branch",
            "lane-branch",
            "integration-worktree-path",
            "acceptance-worktree-path",
            "lane-worktree-path",
            "telemetry-path",
        )
        for collision_class in collision_classes:
            task_id = f"collision-{collision_class}"
            with self.subTest(collision_class=collision_class):
                if collision_class == "integration-base-ref":
                    self.git(
                        self.root,
                        "update-ref",
                        f"refs/orchestrate/{task_id}/integration/base",
                        self.base,
                    )
                elif collision_class == "accepted-ref":
                    self.git(
                        self.root,
                        "update-ref",
                        f"refs/orchestrate/{task_id}/accepted",
                        self.base,
                    )
                elif collision_class == "landed-ref":
                    self.git(
                        self.root,
                        "update-ref",
                        f"refs/orchestrate/{task_id}/landed",
                        self.base,
                    )
                elif collision_class == "lane-base-ref":
                    self.git(
                        self.root,
                        "update-ref",
                        f"refs/orchestrate/{task_id}/orphan/base",
                        self.base,
                    )
                elif collision_class == "integration-branch":
                    self.git(
                        self.root,
                        "branch",
                        f"wave/{task_id}/integration",
                        self.base,
                    )
                elif collision_class == "lane-branch":
                    self.git(
                        self.root,
                        "branch",
                        f"wave/{task_id}/orphan",
                        self.base,
                    )
                elif collision_class == "integration-worktree-path":
                    path = self.task_worktree(task_id, "integration")
                    path.mkdir(parents=True)
                    (path / "operator.bin").write_bytes(b"preserve\x00integration")
                elif collision_class == "acceptance-worktree-path":
                    path = self.task_worktree(task_id, "acceptance")
                    path.mkdir(parents=True)
                    (path / "operator.bin").write_bytes(b"preserve\x00acceptance")
                elif collision_class == "lane-worktree-path":
                    path = self.task_worktree(task_id, "lanes/orphan")
                    path.mkdir(parents=True)
                    (path / "operator.bin").write_bytes(b"preserve\x00lane")
                else:
                    path = self.telemetry_for(task_id)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"operator telemetry\x00\xff")

                before = self.managed_state_snapshot()
                self.operational_failure(
                    self.cli(
                        self.nested,
                        "integration",
                        "create",
                        "--task-id",
                        task_id,
                    ),
                    "integration-create",
                    "task_resource_collision",
                )
                self.assertEqual(self.managed_state_snapshot(), before)

    def test_namespace_parent_ref_collisions_refuse_create_atomically(self) -> None:
        for namespace in ("orchestrate-ref", "wave-branch"):
            task_id = f"parent-collision-{namespace}"
            parent_ref = (
                f"refs/orchestrate/{task_id}"
                if namespace == "orchestrate-ref"
                else f"refs/heads/wave/{task_id}"
            )
            with self.subTest(namespace=namespace, phase="arrange"):
                self.git(self.root, "update-ref", parent_ref, self.base)
            before = self.managed_state_snapshot()

            result = self.cli(
                self.nested,
                "integration",
                "create",
                "--task-id",
                task_id,
            )
            after = self.managed_state_snapshot()

            with self.subTest(namespace=namespace, assertion="zero-mutation"):
                self.assertEqual(after, before)
            with self.subTest(namespace=namespace, assertion="stable-refusal"):
                self.operational_failure(
                    result,
                    "integration-create",
                    "task_resource_collision",
                )

    def test_pin_absence_and_version_drift_do_not_block_create(self) -> None:
        pin = self.root / ".agent_state" / "orchestrate" / "version-pin.json"
        self.assertFalse(pin.exists())
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "create",
                "--task-id",
                "missing-pin",
            ),
            "integration-create",
        )

        pin.parent.mkdir(parents=True, exist_ok=True)
        pin.write_text(
            json.dumps(
                {
                    "pin_version": 1,
                    "skill_version": 136,
                    "orchestrate_compat": 136,
                }
            ),
            encoding="utf-8",
        )
        before = pin.read_bytes()
        self.mutation_success(
            self.cli(
                self.nested,
                "integration",
                "create",
                "--task-id",
                "drifted-pin",
            ),
            "integration-create",
        )
        self.assertEqual(pin.read_bytes(), before)
        self.assertEqual(
            self.git(self.root, "rev-parse", "wave/drifted-pin/integration"),
            self.base,
        )

    def test_corrupt_executing_package_refuses_before_repository_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="orchestrate-corrupt-package-") as tmp:
            skill = Path(tmp) / "orchestrate"
            shutil.copytree(VERIFIED_SKILL, skill)
            script = skill / "scripts" / "orchestrate.py"
            with (skill / "SKILL.md").open("a", encoding="utf-8") as stream:
                stream.write("\ncorrupt after manifest\n")

            self.operational_failure(
                self.cli(
                    self.nested,
                    "integration",
                    "create",
                    "--task-id",
                    self.task_id,
                    script=script,
                    skill_dir=skill,
                ),
                "integration-create",
                "package_unhealthy",
            )

        self.assertFalse((self.root / ".agent_state").exists())
        self.assertEqual(
            self.git(
                self.root,
                "for-each-ref",
                "--format=%(refname)",
                f"refs/orchestrate/{self.task_id}/",
                f"refs/heads/wave/{self.task_id}/",
            ),
            "",
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
