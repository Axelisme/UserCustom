"""Executable contract tests for the Pi orchestrate runtime adapter."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "fixtures" / "pi_adapter" / "adapter_harness.mjs"


class OrchestratePiAdapterTests(unittest.TestCase):
    maxDiff = None

    def run_scenario(self, name: str, *, strict_unhandled: bool = False) -> None:
        env = os.environ.copy()
        if strict_unhandled:
            env["NODE_OPTIONS"] = " ".join(
                option
                for option in (env.get("NODE_OPTIONS", ""), "--unhandled-rejections=strict")
                if option
            )
        completed = subprocess.run(
            ["node", str(HARNESS), name],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"scenario {name} failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )

    def test_official_loader_registers_only_adapter_tool_without_spawn(self) -> None:
        self.run_scenario("load")

    def test_unknown_version_action_and_fields_fail_closed(self) -> None:
        self.run_scenario("strict")

    def test_canonical_git_mismatch_emits_no_rpc(self) -> None:
        self.run_scenario("git-mismatch")

    def test_incompatible_ping_capabilities_emit_no_spawn_or_profile_preflight(self) -> None:
        self.run_scenario("capability")

    def test_exact_lane_worker_tdd_public_preflight_permits_one_spawn(self) -> None:
        self.run_scenario("profile-success")

    def test_untrusted_project_refuses_before_profile_import_or_spawn(self) -> None:
        self.run_scenario("profile-untrusted")

    def test_profile_package_agent_tdd_and_public_module_failures_emit_no_spawn(self) -> None:
        self.run_scenario("profile-failures")

    def test_profile_preflight_stays_within_exact_selected_package(self) -> None:
        self.run_scenario("profile-package-scope")

    def test_profile_preflight_abort_and_deadline_bound_stalled_resolver(self) -> None:
        self.run_scenario("profile-cancellation", strict_unhandled=True)

    def test_dispatch_returns_exact_structured_receipt(self) -> None:
        self.run_scenario("dispatch")

    def test_dispatch_subscribes_to_advertised_process_channel_before_spawn(self) -> None:
        self.run_scenario("dispatch-process-subscription")

    def test_dispatch_early_event_is_bounded_exact_run_one_shot_wake_only(self) -> None:
        self.run_scenario("dispatch-early-wake")

    def test_rpc_subscribes_before_emit_and_correlates_concurrent_requests(self) -> None:
        self.run_scenario("rpc-correlation")

    def test_rpc_timeout_and_abort_unsubscribe(self) -> None:
        self.run_scenario("rpc-cancel")

    def test_abort_cancels_stalled_git_preflight_without_rpc_leak(self) -> None:
        self.run_scenario("git-preflight-cancel")

    def test_malformed_spawn_receipt_stops_exact_orphan_risk_once(self) -> None:
        self.run_scenario("orphan-risk")

    def test_dispatch_rejects_unattestable_run_component_as_orphan_risk(self) -> None:
        self.run_scenario("dispatch-unattestable-run-id")

    def test_run_timeout_is_optional_and_independent_from_rpc_deadline(self) -> None:
        self.run_scenario("run-timeout")

    def test_explicit_turn_budget_is_validated_normalized_and_dispatched_without_steer_capability(self) -> None:
        self.run_scenario("turn-budget")

    def test_exact_turn_event_attempts_one_nonrecovering_handoff_steer(self) -> None:
        self.run_scenario("turn-handoff")

    def test_spawn_receipt_requires_exact_single_async_correlation(self) -> None:
        self.run_scenario("spawn-correlation")

    def test_attest_run_projects_exact_observed_sidecar(self) -> None:
        self.run_scenario("attest-observed")

    def test_attestation_rejects_unbound_receipt_paths_before_evidence_access(self) -> None:
        self.run_scenario("attest-receipt-paths")

    def test_attestation_keeps_execution_and_process_proof_independent(self) -> None:
        self.run_scenario("attest-independent")

    def test_malformed_or_mismatched_sidecar_never_falls_through_to_safe(self) -> None:
        self.run_scenario("attest-invalid-proof")

    def test_observed_proof_requires_valid_canonical_session_identity(self) -> None:
        self.run_scenario("attest-canonical-session")

    def test_status_overlay_and_active_lease_are_bounded_exact_run_evidence(self) -> None:
        self.run_scenario("attest-status")

    def test_receipt_and_status_require_exact_runtime_correlation(self) -> None:
        self.run_scenario("status-correlation")

    def test_attestation_wait_uses_event_only_to_wake_then_unsubscribes(self) -> None:
        self.run_scenario("attest-wait")

    def test_preaborted_attestation_returns_structured_error_without_process_exit(self) -> None:
        self.run_scenario("attest-preaborted", strict_unhandled=True)

    def test_inflight_abort_after_wait_subscription_returns_structured_error(self) -> None:
        self.run_scenario("attest-inflight-abort", strict_unhandled=True)

    def test_attestation_race_cleanup_never_impersonates_upstream_event(self) -> None:
        self.run_scenario("attest-race-no-emit")

    def test_tool_schema_exposes_only_two_strict_versioned_actions(self) -> None:
        self.run_scenario("schema")

    def test_adapter_never_mutates_git_or_returns_root_authority_verdicts(self) -> None:
        self.run_scenario("authority-boundary")


if __name__ == "__main__":
    unittest.main()
