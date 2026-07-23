from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .primitives import OrchestrateError
from .release import (
    command_diff,
    command_doctor,
    command_pin_migrate,
    command_pin_set,
    command_pin_status,
    command_release,
    require_release_preflight,
)
from .v119_core import (
    command_contract_merge,
    command_profile_report,
    command_worktree_create,
    command_worktree_remove,
    command_worktree_status,
)


def command_profile_recommend(args: argparse.Namespace) -> dict[str, object]:
    """Return a read-only v119 role recommendation."""
    models = {
        "codex": {
            "oracle": ("wave-oracle", "gpt-5.6-sol", "reasoning_effort"),
            "implementer": ("wave-implementer", "gpt-5.6-luna", "reasoning_effort"),
        },
        "claude": {
            "oracle": ("wave-oracle", "opus", None),
            "implementer": ("wave-implementer", "sonnet", None),
        },
        "pi": {
            "oracle": ("wave-oracle", "openai-codex/gpt-5.6-sol", "thinking"),
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
    if depth != ("high" if risk == "critical" else "low" if risk == "mechanical" else "medium"):
        raise OrchestrateError(
            f"unsupported profile combination: runtime={runtime} role={role} risk={risk} depth={depth}"
        )
    profile, model, thinking_field = models[runtime][role]
    return {
        "ok": True, "operation": "profile-recommend", "read_only": True,
        "spawned": False, "mutated": False, "runtime": runtime, "role": role,
        "risk": risk, "depth": depth, "profile": profile, "profile_name": profile,
        "model": model, "thinking": depth if thinking_field else None,
        "thinking_field": thinking_field,
    }


def add_root(command: argparse.ArgumentParser) -> None:
    command.add_argument("--root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[2]))
    commands = parser.add_subparsers(dest="command", required=True)

    worktree = commands.add_parser("worktree", help="v119 per-role Git worktree lifecycle")
    worktree_commands = worktree.add_subparsers(dest="worktree_command", required=True)
    for operation, handler in (("create", command_worktree_create), ("status", command_worktree_status), ("remove", command_worktree_remove)):
        operation_parser = worktree_commands.add_parser(operation)
        add_root(operation_parser)
        operation_parser.add_argument("--task-id", required=True)
        operation_parser.add_argument("--wave-id", required=True)
        operation_parser.add_argument("--role", choices=("oracle", "implementation"), required=True)
        if operation == "create":
            operation_parser.add_argument("--base", required=True)
        operation_parser.set_defaults(handler=handler)

    contract = commands.add_parser("contract", help="v119 exact Contract handoff")
    merge = contract.add_subparsers(dest="contract_command", required=True).add_parser("merge")
    add_root(merge)
    merge.add_argument("--task-id", required=True)
    merge.add_argument("--wave-id", required=True)
    merge.add_argument("--contract-sha", required=True)
    merge.set_defaults(handler=command_contract_merge)

    profile = commands.add_parser("profile", help="read-only Git profile projections")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    recommend = profile_commands.add_parser("recommend")
    recommend.add_argument("--runtime", required=True)
    recommend.add_argument("--role", choices=("oracle", "implementation"), required=True)
    recommend.add_argument("--risk", "--risk-level", dest="risk", required=True)
    recommend.add_argument("--depth", required=True)
    recommend.set_defaults(handler=command_profile_recommend)
    report = profile_commands.add_parser("report")
    add_root(report)
    report.add_argument("--task-id", required=True)
    report.add_argument("--wave-id", required=True)
    report.add_argument("--base", required=True)
    report.set_defaults(handler=command_profile_report)

    doctor = commands.add_parser("doctor", help="verify v119 manifest, hashes, and read budgets")
    doctor.set_defaults(handler=command_doctor)
    diff = commands.add_parser("diff", help="compare bundled release manifests")
    diff.add_argument("old_version", type=int)
    diff.add_argument("new_version", type=int)
    diff.add_argument("--runtime", choices=("codex", "claude", "pi"))
    diff.set_defaults(handler=command_diff)

    pin = commands.add_parser("pin", help="pin a task to the installed release")
    pin_commands = pin.add_subparsers(dest="pin_command", required=True)
    for name, handler in (("status", command_pin_status), ("set", command_pin_set), ("migrate", command_pin_migrate)):
        operation = pin_commands.add_parser(name)
        add_root(operation)
        operation.set_defaults(handler=handler)

    release = commands.add_parser("release", help="atomic release: bump version, manifest, doctor")
    release.add_argument("--version", type=int)
    release.set_defaults(handler=command_release)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        preflight = require_release_preflight(Path(args.skill_dir)) if getattr(args, "requires_release_preflight", False) else None
        payload = args.handler(args)
        if preflight is not None:
            payload["release_preflight"] = preflight
    except (OSError, UnicodeError, OrchestrateError) as exc:
        print(json.dumps({"ok": False, "error": {"type": "orchestrate", "message": str(exc)}}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok", False) else 1
