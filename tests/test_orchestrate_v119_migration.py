from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = SKILL / "scripts" / "orchestrate.py"


def load_release_module():
    sys.path.insert(0, str(SKILL / "scripts"))
    try:
        from _orchestrate import release
    finally:
        sys.path.pop(0)
    return release


class OrchestrateV119MigrationContractTests(unittest.TestCase):
    """Oracle-owned contract for v118 pin migration into a manual v119 Wave."""

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def shipped_skill_fixture(self, root: Path, release) -> tuple[Path, int]:
        # Copy the shipped package as an installed-package-shaped fixture.  A
        # missing v118 manifest intentionally exercises the documented manual
        # migration path rather than a synthetic private helper.
        home = root / "home"
        shutil.copytree(ROOT / "home", home)
        skill = home / ".codex" / "skills" / "orchestrate"
        version = release.skill_version(skill)
        (skill / "manifests" / "118.json").unlink()
        manifest = release.build_manifest(skill, version)
        (skill / "manifests" / f"{version}.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return skill, version

    def test_pin_migrate_preserves_shape_and_emits_every_crossed_boundary(self) -> None:
        release = load_release_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, "init", "-q", "-b", "main")
            self.git(root, "config", "user.name", "Oracle Test")
            self.git(root, "config", "user.email", "oracle@example.test")
            self.git(root, "commit", "--allow-empty", "-qm", "base")
            skill, version = self.shipped_skill_fixture(root, release)

            # Legacy evidence and state are read-only migration input.  The
            # migration must not attempt to convert or delete either asset.
            evidence = root / ".agent_state" / "legacy" / "findings.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text('{"legacy": true}\n', encoding="utf-8")
            legacy_state = root / ".agent_state" / "legacy-lanes.json"
            legacy_state.write_text('{"lane": "old"}\n', encoding="utf-8")
            pin = root / ".agent_state" / "orchestrate" / "version-pin.json"
            pin.parent.mkdir(parents=True)
            pin.write_text(
                json.dumps(
                    {
                        "pin_version": 1,
                        "skill_version": 118,
                        "orchestrate_compat": 118,
                    }
                ),
                encoding="utf-8",
            )

            result = release.command_pin_migrate(
                argparse.Namespace(root=str(root), skill_dir=str(skill))
            )

            self.assertEqual(
                set(result),
                {
                    "ok",
                    "operation",
                    "from_version",
                    "to_version",
                    "delta",
                    "migration_requirements",
                    "delta_note",
                },
            )
            self.assertEqual(result["operation"], "pin-migrate")
            self.assertEqual(result["from_version"], 118)
            self.assertEqual(result["to_version"], version)
            self.assertIsNone(result["delta"])
            requirements = {block["reason"]: block for block in result["migration_requirements"]}
            restart = requirements["v118-to-v119-manual-restart"]
            self.assertTrue(restart["stop_legacy_dispatch"])
            self.assertTrue(restart["preserve_legacy_evidence"])
            self.assertTrue(restart["select_exact_base"])
            self.assertTrue(restart["create_new_wave"])
            self.assertTrue(restart["continue_as_v119_wave"])
            self.assertFalse(restart["automatic_conversion"])
            # Crossing v120 must also publish what the unchanged Git model does not imply.
            adoption = requirements["v119-to-v120-workflow-adoption"]
            for surface in (
                "adopt_integration_cli",
                "record_integration_base_ref",
                "machine_gates_then_collect_per_wave",
                "milestone_acceptance_replaces_per_wave_review",
                "correction_after_collect_is_a_new_wave",
                "declare_runtime_pipelines_before_enqueue",
                "empty_handoff_after_contract_merge",
                "blocked_reason_enum_replaces_checkpoint",
            ):
                self.assertTrue(adoption[surface], surface)
            self.assertFalse(adoption["automatic_conversion"])
            # Crossing v121 must announce the gate that refuses undeclared Contracts.
            declared = requirements["v120-to-v121-declared-acceptance-surface"]
            for surface in (
                "declare_immutable_trailers_on_contracts",
                "collect_verifies_object_identity",
                "reauthor_contract_to_collect_older_wave",
                "quantified_cost_alarm_with_preserved_sha",
                "fresh_session_when_frozen_input_moved",
            ):
                self.assertTrue(declared[surface], surface)
            self.assertFalse(declared["automatic_conversion"])
            # Crossing v122 must announce the narrowed simplify scope.
            bounded = requirements["v121-to-v122-bounded-simplify"]
            for surface in (
                "simplify_reads_increment_since_last_review",
                "review_keeps_whole_integration_range",
                "simplify_defers_authority_and_sequencing_findings",
                "removal_of_timing_requires_reproduction",
                "simplify_reports_three_triage_groups",
            ):
                self.assertTrue(bounded[surface], surface)
            self.assertFalse(bounded["automatic_conversion"])
            # Crossing v123 must announce that machinery now needs its own red test.
            symmetric = requirements["v122-to-v123-symmetric-mechanism-evidence"]
            for surface in (
                "mechanism_needs_a_red_test_to_enter",
                "unjustified_mechanism_is_a_finding",
                "harden_after_the_interface_is_stable",
            ):
                self.assertTrue(symmetric[surface], surface)
            self.assertFalse(symmetric["automatic_conversion"])
            admission = requirements["v123-to-v124-slice-admission"]
            self.assertNotIn("land_once_per_slice_not_once_per_task", admission)
            self.assertNotIn("report_reachable_behavior_at_every_landing", admission)
            self.assertFalse(admission["automatic_conversion"])
            scheduling = requirements["v124-to-v125-deferred-user-acceptance"]
            for surface in (
                "night_mode_defers_user_acceptance_only",
                "deferred_acceptance_lives_in_phase_record",
                "speculative_dependency_depth_is_ten",
                "user_rework_does_not_consume_machine_cycles",
                "machine_rework_tracks_finding_provenance",
                "landing_still_requires_user_acceptance",
            ):
                self.assertTrue(scheduling[surface], surface)
            self.assertFalse(scheduling["automatic_conversion"])
            # v125 briefly put S5 before the quality gates; v126 supersedes it,
            # so the older requirement must not still instruct that ordering.
            self.assertNotIn("day_mode_accepts_before_quality_gates", scheduling)
            gated = requirements["v125-to-v126-machine-gates-before-user-test"]
            for surface in (
                "user_tests_only_reviewed_shas",
                "day_and_night_share_one_gate_order",
                "rejection_reopens_gates_on_the_next_sha",
            ):
                self.assertTrue(gated[surface], surface)
            self.assertFalse(gated["automatic_conversion"])
            checkpoint = requirements["v126-to-v127-accepted-checkpoint-landing"]
            for surface in (
                "every_slice_keeps_machine_gates_and_s5",
                "accepted_sha_remains_on_append_only_integration",
                "next_slice_bases_on_integration_tip",
                "persistence_is_not_mutated_per_slice",
                "final_landing_requires_current_user_request",
                "partial_landing_requires_explicit_accepted_target",
                "landing_is_fast_forward_only",
                "partial_landing_keeps_task_state",
                "final_landing_then_cleanup_and_close_out",
                "never_push",
            ):
                self.assertTrue(checkpoint[surface], surface)
            self.assertFalse(checkpoint["automatic_conversion"])
            session = requirements["v128-to-v129-coordinated-acceptance-session"]
            for surface in (
                "adopt_planning_v14_deferred_schema",
                "migrate_active_v13_deferred_rows_manually",
                "preserve_completed_v13_phase_records",
                "exercise_latest_reviewed_tip",
                "continue_feedback_after_failure_when_safe",
                "batch_user_findings_once",
                "user_rework_does_not_consume_machine_cycles",
                "repair_with_forward_commits",
                "run_shared_machine_order_after_repair",
                "retest_failed_blocked_and_named_impacted",
                "carry_forward_requires_impact_basis",
                "carry_forward_requires_final_confirmation",
                "stale_or_known_bad_blocks_acceptance_and_landing",
                "feedback_collection_may_continue",
            ):
                self.assertTrue(session[surface], surface)
            self.assertFalse(session["automatic_conversion"])
            self.assertEqual(
                json.loads(pin.read_text(encoding="utf-8"))["skill_version"], version
            )
            self.assertEqual(evidence.read_text(encoding="utf-8"), '{"legacy": true}\n')
            self.assertEqual(legacy_state.read_text(encoding="utf-8"), '{"lane": "old"}\n')

    def test_v128_pin_receives_only_the_v129_session_boundary(self) -> None:
        release = load_release_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, "init", "-q", "-b", "main")
            self.git(root, "config", "user.name", "Oracle Test")
            self.git(root, "config", "user.email", "oracle@example.test")
            self.git(root, "commit", "--allow-empty", "-qm", "base")
            skill, version = self.shipped_skill_fixture(root, release)
            pin = root / ".agent_state" / "orchestrate" / "version-pin.json"
            pin.parent.mkdir(parents=True)
            pin.write_text(
                json.dumps(
                    {
                        "pin_version": 1,
                        "skill_version": 128,
                        "orchestrate_compat": 128,
                    }
                ),
                encoding="utf-8",
            )

            result = release.command_pin_migrate(
                argparse.Namespace(root=str(root), skill_dir=str(skill))
            )

            self.assertEqual(version, 129)
            self.assertEqual(
                [block["reason"] for block in result["migration_requirements"]],
                ["v128-to-v129-coordinated-acceptance-session"],
            )
            self.assertFalse(result["migration_requirements"][0]["automatic_conversion"])

    def test_retained_administration_stays_on_the_root_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("release", "manifest", "doctor", "pin"):
            self.assertIn(command, result.stdout)
        pin_help = subprocess.run(
            [sys.executable, str(SCRIPT), "pin", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(pin_help.returncode, 0, pin_help.stderr)
        self.assertIn("migrate", pin_help.stdout)

    def test_pin_migrate_same_version_keeps_existing_compatibility_response(self) -> None:
        release = load_release_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, "init", "-q", "-b", "main")
            self.git(root, "config", "user.name", "Oracle Test")
            self.git(root, "config", "user.email", "oracle@example.test")
            self.git(root, "commit", "--allow-empty", "-qm", "base")
            skill, version = self.shipped_skill_fixture(root, release)
            pin = root / ".agent_state" / "orchestrate" / "version-pin.json"
            pin.parent.mkdir(parents=True)
            pin.write_text(
                json.dumps({"skill_version": version, "orchestrate_compat": version}),
                encoding="utf-8",
            )

            result = release.command_pin_migrate(
                argparse.Namespace(root=str(root), skill_dir=str(skill))
            )
            self.assertEqual(
                result,
                {
                    "ok": True,
                    "operation": "pin-migrate",
                    "recovered": "already-current",
                    "pinned_version": version,
                },
            )


if __name__ == "__main__":
    unittest.main()
