from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .primitives import OrchestrateError
from .release import command_diff, command_doctor, command_pin_migrate, command_pin_set, command_pin_status, command_release, command_release_manifest, require_release_preflight
from .findings import command_findings_record, command_findings_status, command_findings_validate
from .feedback import command_feedback_record
from .lanes import COLLECT_REVIEW_KINDS, command_collect, command_compose_base, command_compose_base_revalidate, command_lane_create, command_slice_milestone, command_slice_status
from .review import (
    command_review_audit,
    command_review_checkout,
    command_review_cleanup,
    command_review_cleanup_all,
)
from .worktrees import command_cleanup, command_reconcile, command_wave_status
from .landing import command_land_finish, command_land_status
from .v119_core import (
    command_contract_merge,
    command_profile_report,
    command_worktree_create,
    command_worktree_remove,
    command_worktree_status,
)


def command_profile_recommend(args: argparse.Namespace) -> dict[str, object]:
    """Return a shipped profile projection; never invoke a runtime or mutate state."""
    models = {
        "codex": {
            "reviewer": ("wave-reviewer", "gpt-5.6-sol", "reasoning_effort"),
            "implementer": ("wave-implementer", "gpt-5.6-luna", "reasoning_effort"),
        },
        "claude": {
            "reviewer": ("wave-reviewer", "opus", None),
            "implementer": ("wave-implementer", "sonnet", None),
        },
        "pi": {
            "reviewer": ("wave-reviewer", "openai-codex/gpt-5.6-sol", "thinking"),
            "implementer": ("wave-implementer", "openai-codex/gpt-5.6-luna", "thinking"),
        },
    }
    runtime = str(args.runtime).strip().lower()
    role = str(args.role).strip().lower()
    risk = str(args.risk).strip().lower()
    depth = str(args.depth).strip().lower()
    if runtime not in models:
        raise OrchestrateError(f"unsupported runtime: {runtime}")
    if role not in models[runtime]:
        raise OrchestrateError(f"unsupported role for {runtime}: {role}")
    if risk not in {"mechanical", "normal", "critical"}:
        raise OrchestrateError(f"unsupported risk: {risk}")
    if depth not in {"low", "medium", "high"}:
        raise OrchestrateError(f"unsupported depth: {depth}")
    expected = "high" if risk == "critical" else "low"
    if role == "reviewer" and (risk == "mechanical" or depth != expected):
        raise OrchestrateError(
            f"unsupported profile combination: runtime={runtime} role={role} "
            f"risk={risk} depth={depth}"
        )
    # Mechanical work has a distinct shipped profile per runtime, with different
    # depth knobs (Codex medium, Claude none, Pi low). Do not pretend the generic
    # wave-implementer recommendation is executable for that risk class; fail closed
    # until a caller supplies a runtime-specific mechanical contract.
    if role == "implementer" and risk == "mechanical":
        raise OrchestrateError(
            f"unsupported profile combination: runtime={runtime} role={role} "
            f"risk={risk} depth={depth}"
        )
    if role == "implementer" and depth != "high":
        raise OrchestrateError(
            f"unsupported profile combination: runtime={runtime} role={role} "
            f"risk={risk} depth={depth}"
        )
    profile, model, thinking_field = models[runtime][role]
    return {
        "ok": True,
        "operation": "profile-recommend",
        "read_only": True,
        "spawned": False,
        "mutated": False,
        "runtime": runtime,
        "role": role,
        "risk": risk,
        "depth": depth,
        "profile": profile,
        "profile_name": profile,
        "model": model,
        "thinking": depth if thinking_field else None,
        "thinking_field": thinking_field,
    }

def add_root(command: argparse.ArgumentParser) -> None:
    command.add_argument("--root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-dir",
        default=str(Path(__file__).resolve().parents[2]),
        help="orchestrate skill directory (defaults to this script's parent skill)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    worktree = commands.add_parser(
        "worktree", help="v119 per-role Git worktree lifecycle"
    )
    worktree_commands = worktree.add_subparsers(dest="worktree_command", required=True)
    for operation, handler in (
        ("create", command_worktree_create),
        ("status", command_worktree_status),
        ("remove", command_worktree_remove),
    ):
        worktree_operation = worktree_commands.add_parser(operation)
        add_root(worktree_operation)
        worktree_operation.add_argument("--task-id", required=True)
        worktree_operation.add_argument("--wave-id", required=True)
        worktree_operation.add_argument("--role", choices=("oracle", "implementation"), required=True)
        if operation == "create":
            worktree_operation.add_argument("--base", required=True)
        worktree_operation.set_defaults(handler=handler)

    contract = commands.add_parser(
        "contract", help="v119 exact Contract handoff"
    )
    contract_commands = contract.add_subparsers(dest="contract_command", required=True)
    merge = contract_commands.add_parser("merge")
    add_root(merge)
    merge.add_argument("--task-id", required=True)
    merge.add_argument("--wave-id", required=True)
    merge.add_argument("--contract-sha", required=True)
    merge.set_defaults(handler=command_contract_merge)

    doctor = commands.add_parser(
        "doctor", help="verify manifest, compat, hashes, and read budgets"
    )
    doctor.set_defaults(handler=command_doctor)

    diff = commands.add_parser("diff", help="compare two bundled release manifests")
    diff.add_argument("old_version", type=int)
    diff.add_argument("new_version", type=int)
    diff.add_argument("--runtime", choices=("codex", "claude", "pi"))
    diff.set_defaults(handler=command_diff)

    lane = commands.add_parser("lane", help="explicit lane lifecycle guards")
    lane_commands = lane.add_subparsers(dest="lane_command", required=True)
    lane_create = lane_commands.add_parser("create")
    add_root(lane_create)
    lane_create.add_argument("--task-id", required=True)
    lane_create.add_argument("--lane", required=True)
    lane_create.add_argument("--base", required=True)
    lane_create.add_argument("--worktree")
    lane_create.set_defaults(
        handler=command_lane_create, requires_release_preflight=True
    )

    compose = commands.add_parser(
        "compose-base",
        help="merge seam-ready lanes into a marked speculative base (spec/<task>/<name>)",
    )
    add_root(compose)
    compose.add_argument("--task-id", required=True)
    compose.add_argument("--name", required=True)
    compose.add_argument("--base", required=True)
    compose.add_argument(
        "--lane",
        action="append",
        required=True,
        help="seam-ready lane SHA (repeatable)",
    )
    compose.set_defaults(handler=command_compose_base, requires_release_preflight=True)

    review = commands.add_parser("review", help="detached exact-SHA review worktrees")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    for command_name in ("create", "checkout"):
        create = review_commands.add_parser(
            command_name,
            help="create one immutable clean detached worktree for one review job",
        )
        add_root(create)
        create.add_argument("sha")
        create.add_argument("--task-id", required=True)
        create.add_argument("--job-id", required=True)
        create.add_argument("--worktree")
        create.set_defaults(
            handler=command_review_checkout, requires_release_preflight=True
        )
    cleanup_review = review_commands.add_parser(
        "cleanup", help="harvest an external receipt, then remove one exact review job"
    )
    add_root(cleanup_review)
    cleanup_review.add_argument("--task-id", required=True)
    cleanup_review.add_argument("--job-id", required=True)
    cleanup_review.add_argument("--receipt", required=True)
    cleanup_review.add_argument("--pipeline-facts", required=True)
    cleanup_review.add_argument("--owner-session", required=True)
    cleanup_review.set_defaults(
        handler=command_review_cleanup, requires_release_preflight=True
    )
    cleanup_all = review_commands.add_parser(
        "cleanup-all",
        help="remove this task's unreferenced review jobs using public pipeline facts",
    )
    add_root(cleanup_all)
    cleanup_all.add_argument("--task-id", required=True)
    cleanup_all.add_argument("--pipeline-facts", required=True)
    cleanup_all.add_argument("--owner-session", required=True)
    cleanup_all.set_defaults(
        handler=command_review_cleanup_all, requires_release_preflight=True
    )
    audit = review_commands.add_parser(
        "audit", help="read-only AST signals for changed test files"
    )
    add_root(audit)
    audit.add_argument("--base", required=True)
    audit.add_argument("--subject-sha", "--subject", dest="subject", required=True)
    audit.set_defaults(handler=command_review_audit)

    land = commands.add_parser(
        "land", help="declared-policy squash landing with tree-identity proof"
    )
    land_commands = land.add_subparsers(dest="land_command", required=True)
    land_status = land_commands.add_parser("status")
    add_root(land_status)
    land_status.add_argument("--task-ref", required=True)
    land_status.add_argument(
        "--declaration", required=True, help="landing declaration JSON path"
    )
    land_status.set_defaults(handler=command_land_status)
    land_finish = land_commands.add_parser("finish")
    add_root(land_finish)
    land_finish.add_argument("--task-ref", required=True)
    land_finish.add_argument("--task-sha", required=True)
    land_finish.add_argument(
        "--declaration", required=True, help="landing declaration JSON path"
    )
    land_finish.add_argument(
        "--confirmed",
        action="store_true",
        help="record the explicit user confirmation land-with-confirmation requires",
    )
    land_finish.add_argument("--message")
    land_finish.set_defaults(
        handler=command_land_finish, requires_release_preflight=True
    )

    collect = commands.add_parser(
        "collect", help="preflight and merge one explicitly authorized exact lane SHA"
    )
    # Deliberately not spelled --root: task identity is derived from *this* checkout's
    # branch, so the name has to say which checkout it is. Tests pin the distinction.
    collect.add_argument(
        "--integration-worktree",
        dest="root",
        required=True,
        help="integration checkout; task identity is derived from its current branch",
    )
    collect.add_argument("--lane-ref", required=True)
    collect.add_argument(
        "--authorized-sha",
        required=True,
        help="exact immutable review/root authorization checkpoint",
    )
    collect.add_argument(
        "--review-kind", choices=COLLECT_REVIEW_KINDS, required=True
    )
    collect.add_argument(
        "--item",
        help="expected Item id; rejects a reused lane whose head carries another Item",
    )
    collect.set_defaults(handler=command_collect, requires_release_preflight=True)

    sweep = commands.add_parser(
        "cleanup",
        help="remove one exact classifier-approved worktree; bulk cleanup is disabled",
    )
    add_root(sweep)
    sweep.add_argument(
        "--absorbed",
        action="store_true",
        help="authorize the multi-worktree sweep; required unless --worktree names one target",
    )
    sweep.add_argument(
        "--wave-boundary",
        dest="wave_boundary",
        action="store_true",
        help="sweep this task's lane worktrees (from the checkout's task/<task> branch)"
        " regardless of absorbed/dirty; skips detached review worktrees; pair with"
        " --dry-run to preview",
    )
    sweep.add_argument("--dry-run", action="store_true")
    sweep.add_argument(
        "--worktree", help="remove exactly this managed worktree with full proofs"
    )
    sweep.add_argument(
        "--subject-sha",
        "--subject",
        dest="subject_sha",
        help="review targets only: fail fast when the checkout HEAD drifted",
    )
    sweep.set_defaults(handler=command_cleanup)

    slice_parser = commands.add_parser(
        "slice", help="derive read-only slice states from Git alone"
    )
    slice_commands = slice_parser.add_subparsers(dest="slice_command", required=True)
    slice_status = slice_commands.add_parser("status")
    add_root(slice_status)
    slice_status.add_argument("--task-ref", required=True)
    slice_status.set_defaults(handler=command_slice_status)
    slice_milestone = slice_commands.add_parser("milestone")
    add_root(slice_milestone)
    slice_milestone.add_argument("--item", required=True)
    slice_milestone.add_argument("--outcome")
    slice_milestone.set_defaults(handler=command_slice_milestone)

    findings = commands.add_parser(
        "findings", help="machine-readable review finding ledger (git-derived closure)"
    )
    findings_commands = findings.add_subparsers(dest="findings_command", required=True)
    findings_record = findings_commands.add_parser("record")
    add_root(findings_record)
    findings_record.add_argument("--task-id", required=True)
    findings_record.add_argument(
        "--receipt", required=True, help="reviewer JSON receipt path (or - for stdin)"
    )
    findings_record.set_defaults(
        handler=command_findings_record, requires_release_preflight=True
    )
    findings_validate = findings_commands.add_parser(
        "validate", help="read-only: validate and normalize a review receipt"
    )
    add_root(findings_validate)
    findings_validate.add_argument(
        "--receipt", required=True, help="reviewer JSON receipt path (or - for stdin)"
    )
    findings_validate.set_defaults(handler=command_findings_validate)
    findings_status = findings_commands.add_parser("status")
    add_root(findings_status)
    findings_status.add_argument("--task-id", required=True)
    findings_status.add_argument(
        "--task-ref", help="ref whose history supplies Closes-Finding closure (default HEAD)"
    )
    findings_status.add_argument(
        "--slice-sha",
        dest="slice_sha",
        help="also report slice_blocking: the gating findings reachable from this slice",
    )
    findings_status.add_argument(
        "--path",
        action="append",
        help="report `matched`: findings on this file/dir across the whole task"
        " (repeatable; a reviewer passes its diff's paths to inherit prior findings)",
    )
    findings_status.add_argument(
        "--sweep",
        action="store_true",
        help="report `matched`: the sweep_required root-cause patterns, so a reviewer"
        " can check the diff has not reintroduced one",
    )
    findings_status.add_argument(
        "--summary",
        action="store_true",
        help="bounded scalar projection; omit ledger rows and review evidence",
    )
    findings_status.add_argument(
        "--open-only",
        action="store_true",
        help="project only currently open finding rows",
    )
    findings_status.add_argument(
        "--ids",
        action="append",
        metavar="ID[,ID... ]",
        help="project exact finding ids (repeatable or comma-separated)",
    )
    findings_status.set_defaults(handler=command_findings_status)

    profile = commands.add_parser(
        "profile", help="read-only executable profile projections"
    )
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_recommend = profile_commands.add_parser(
        "recommend", help="recommend a shipped profile without spawning or mutating"
    )
    profile_recommend.add_argument("--runtime", required=True)
    profile_recommend.add_argument("--role", required=True)
    profile_recommend.add_argument("--risk", "--risk-level", dest="risk", required=True)
    profile_recommend.add_argument("--depth", required=True)
    profile_recommend.set_defaults(handler=command_profile_recommend)
    profile_report = profile_commands.add_parser(
        "report", help="v119 read-only Git profile report"
    )
    add_root(profile_report)
    profile_report.add_argument("--task-id", required=True)
    profile_report.add_argument("--wave-id", required=True)
    profile_report.add_argument("--base", required=True)
    profile_report.set_defaults(handler=command_profile_report)

    feedback = commands.add_parser(
        "feedback",
        help="append-only subagent process feedback about orchestrate and working under"
        " root; gates nothing, not in wave status — root reads the file on demand",
    )
    feedback_commands = feedback.add_subparsers(dest="feedback_command", required=True)
    feedback_record = feedback_commands.add_parser("record")
    add_root(feedback_record)
    feedback_record.add_argument("--task-id", required=True)
    feedback_record.add_argument(
        "--note", required=True, help="the feedback or suggestion (free text)"
    )
    feedback_record.add_argument(
        "--source", help="recording agent identity (its lane ref or a dispatch label)"
    )
    feedback_record.add_argument(
        "--subject", help="optional exact SHA or item the feedback concerns"
    )
    feedback_record.set_defaults(handler=command_feedback_record)

    revalidate = commands.add_parser(
        "revalidate",
        help="read-only: revalidate a compose-base composite against predecessors'"
        " final SHAs (are follow-ups absorbed, must you recompose)",
    )
    add_root(revalidate)
    revalidate.add_argument(
        "--composite",
        required=True,
        help="exact SHA of the compose-base composite being revalidated",
    )
    revalidate.add_argument(
        "--task-ref", required=True, help="task/<task> the composite must land on"
    )
    revalidate.add_argument(
        "--successor",
        required=True,
        help="exact SHA of the lane stacked on that composite",
    )
    revalidate.add_argument(
        "--lane",
        action="append",
        required=True,
        help="final predecessor exact SHA (repeatable; one per recorded dependency)",
    )
    revalidate.set_defaults(handler=command_compose_base_revalidate)

    reconcile = commands.add_parser(
        "reconcile",
        help="read-only: classify managed worktrees against git + the finding ledger",
    )
    add_root(reconcile)
    reconcile.set_defaults(handler=command_reconcile)

    wave = commands.add_parser(
        "wave", help="read-only wave rollups composed from git-derived reads"
    )
    wave_commands = wave.add_subparsers(dest="wave_command", required=True)
    wave_status = wave_commands.add_parser(
        "status",
        help="read-only: slice + findings + reconcile in one report, with a"
        " restart-oriented handoff summary (never dispatches or lands)",
    )
    add_root(wave_status)
    wave_status.add_argument("--task-ref", required=True)
    wave_status.add_argument(
        "--summary",
        action="store_true",
        help="emit only the handoff rollup, not the three full reports",
    )
    wave_status.set_defaults(handler=command_wave_status)

    pin = commands.add_parser(
        "pin", help="pin a task to the installed orchestrate release"
    )
    pin_commands = pin.add_subparsers(dest="pin_command", required=True)
    pin_status_cmd = pin_commands.add_parser("status")
    add_root(pin_status_cmd)
    pin_status_cmd.set_defaults(handler=command_pin_status)
    pin_set = pin_commands.add_parser("set")
    add_root(pin_set)
    pin_set.set_defaults(handler=command_pin_set)
    pin_migrate = pin_commands.add_parser("migrate")
    add_root(pin_migrate)
    pin_migrate.set_defaults(handler=command_pin_migrate)

    release = commands.add_parser(
        "release",
        help="atomic release: bump skill_version, write the manifest, run doctor",
    )
    release.add_argument(
        "--version",
        type=int,
        help="target version (default: current+1; pass the current version to"
        " finish an aborted release)",
    )
    release.set_defaults(handler=command_release)

    release_manifest = commands.add_parser("release-manifest", help=argparse.SUPPRESS)
    release_manifest.add_argument("--version", required=True, type=int)
    release_manifest.add_argument("--previous-version", type=int)
    release_manifest.add_argument("--output", required=True)
    release_manifest.set_defaults(handler=command_release_manifest)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        release_preflight = None
        cleanup_mutation = (
            args.command == "cleanup"
            and (
                bool(getattr(args, "worktree", None))
                or bool(getattr(args, "wave_boundary", False))
            )
            and not bool(getattr(args, "dry_run", False))
        )
        if cleanup_mutation or getattr(args, "requires_release_preflight", False):
            release_preflight = require_release_preflight(
                Path(args.skill_dir), root=getattr(args, "root", None)
            )
        payload = args.handler(args)
        if release_preflight is not None:
            payload["release_preflight"] = release_preflight
    except (OSError, UnicodeError, OrchestrateError) as exc:
        # Validly parsed commands always fail through the same machine-readable
        # representation; argparse remains responsible only for malformed usage.
        print(
            json.dumps(
                {"ok": False, "error": {"type": "orchestrate", "message": str(exc)}},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok", False) else 1
