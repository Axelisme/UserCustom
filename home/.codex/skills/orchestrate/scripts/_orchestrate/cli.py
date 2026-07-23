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
)
from .v119_core import (
    command_contract_merge,
    command_profile_report,
    command_worktree_create,
    command_worktree_remove,
    command_worktree_status,
)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise OrchestrateError(message)


def add_root(command: argparse.ArgumentParser) -> None:
    command.add_argument("--root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[2]))
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)

    worktree = commands.add_parser("worktree", help="v119 per-role Git worktree lifecycle")
    worktree_commands = worktree.add_subparsers(dest="worktree_command", required=True, parser_class=JsonArgumentParser)
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
    merge = contract.add_subparsers(dest="contract_command", required=True, parser_class=JsonArgumentParser).add_parser("merge")
    add_root(merge)
    merge.add_argument("--task-id", required=True)
    merge.add_argument("--wave-id", required=True)
    merge.add_argument("--contract-sha", required=True)
    merge.set_defaults(handler=command_contract_merge)

    profile = commands.add_parser("profile", help="read-only Git profile projections")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True, parser_class=JsonArgumentParser)
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
    pin_commands = pin.add_subparsers(dest="pin_command", required=True, parser_class=JsonArgumentParser)
    for name, handler in (("status", command_pin_status), ("set", command_pin_set), ("migrate", command_pin_migrate)):
        operation = pin_commands.add_parser(name)
        add_root(operation)
        operation.set_defaults(handler=handler)

    release = commands.add_parser("release", help="atomic release: bump version, manifest, doctor")
    release.add_argument("--version", type=int)
    release.set_defaults(handler=command_release)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        payload = args.handler(args)
    except (OSError, UnicodeError, OrchestrateError) as exc:
        print(json.dumps({"ok": False, "error": {"type": "orchestrate", "message": str(exc)}}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok", False) else 1
