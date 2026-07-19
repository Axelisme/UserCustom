from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .primitives import OrchestrateError
from .release import command_diff, command_doctor, command_pin_migrate, command_pin_set, command_pin_status, command_release, command_release_manifest, require_release_preflight
from .findings import command_findings_record, command_findings_status
from .lanes import COLLECT_REVIEW_KINDS, command_collect, command_compose_base, command_compose_base_revalidate, command_lane_create, command_slice_milestone, command_slice_status
from .review import command_review_advance, command_review_audit, command_review_checkout
from .worktrees import command_cleanup, command_reconcile, command_wave_status
from .landing import command_land_finish, command_land_status

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

    doctor = commands.add_parser(
        "doctor", help="verify manifest, compat, hashes, and read budgets"
    )
    doctor.set_defaults(handler=command_doctor)

    diff = commands.add_parser("diff", help="compare two bundled release manifests")
    diff.add_argument("old_version", type=int)
    diff.add_argument("new_version", type=int)
    diff.add_argument("--runtime", choices=("codex", "claude"))
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
    checkout = review_commands.add_parser("checkout")
    add_root(checkout)
    checkout.add_argument("sha")
    checkout.add_argument("--label")
    checkout.add_argument("--worktree")
    checkout.set_defaults(
        handler=command_review_checkout, requires_release_preflight=True
    )
    advance = review_commands.add_parser("advance")
    add_root(advance)
    advance.add_argument("--worktree", required=True)
    advance.add_argument("--from", dest="from_sha", required=True)
    advance.add_argument("--to", dest="to_sha", required=True)
    advance.set_defaults(
        handler=command_review_advance, requires_release_preflight=True
    )
    audit = review_commands.add_parser(
        "audit", help="read-only AST signals for changed test files"
    )
    add_root(audit)
    audit.add_argument("--base", required=True)
    audit.add_argument("--subject", required=True)
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
    collect.set_defaults(handler=command_collect, requires_release_preflight=True)

    sweep = commands.add_parser(
        "cleanup",
        help="remove one exact classifier-approved worktree; bulk cleanup is disabled",
    )
    add_root(sweep)
    sweep.add_argument(
        "--absorbed",
        action="store_true",
        help="deprecated compatibility flag; only --dry-run is accepted without --worktree",
    )
    sweep.add_argument("--dry-run", action="store_true")
    sweep.add_argument(
        "--worktree", help="remove exactly this managed worktree with full proofs"
    )
    sweep.add_argument(
        "--subject-sha",
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
    findings_status = findings_commands.add_parser("status")
    add_root(findings_status)
    findings_status.add_argument("--task-id", required=True)
    findings_status.add_argument(
        "--task-ref", help="ref whose history supplies Closes-Finding closure (default HEAD)"
    )
    findings_status.set_defaults(handler=command_findings_status)

    revalidate = commands.add_parser(
        "revalidate",
        help="read-only: revalidate a compose-base composite against predecessors'"
        " final SHAs (are follow-ups absorbed, must you recompose)",
    )
    add_root(revalidate)
    revalidate.add_argument("--composite", required=True)
    revalidate.add_argument("--task-ref", required=True)
    revalidate.add_argument("--successor", required=True)
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
            and bool(getattr(args, "worktree", None))
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
        parser.exit(2, f"orchestrate error: {exc}\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok", False) else 1
