from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn, Sequence

from .lane_core import (
    command_commit_check,
    command_integration_candidate,
    command_integration_collect,
    command_integration_create,
    command_integration_land,
    command_integration_list,
    command_integration_remove,
    command_integration_status,
    command_lane_create,
    command_lane_drop,
    command_lane_status,
    command_report,
)
from .primitives import OrchestrateError
from .release import (
    command_diff,
    command_doctor,
    command_pin_set,
    command_pin_status,
    command_release,
    require_verified_release,
    skill_version,
)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise OrchestrateError(message)


def add_root(command: argparse.ArgumentParser) -> None:
    command.add_argument("--root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[2]))
    commands = parser.add_subparsers(
        dest="command", required=True, parser_class=JsonArgumentParser
    )

    lane = commands.add_parser("lane", help="Git-backed lane lifecycle")
    lane_commands = lane.add_subparsers(
        dest="lane_command", required=True, parser_class=JsonArgumentParser
    )

    lane_create = lane_commands.add_parser("create")
    add_root(lane_create)
    lane_create.add_argument("--task-id", required=True)
    lane_create.add_argument("--lane-id", required=True)
    lane_create.add_argument("--base", required=True)
    lane_create.set_defaults(handler=command_lane_create, task_mutation=True)

    lane_status = lane_commands.add_parser("status")
    add_root(lane_status)
    lane_status.add_argument("--task-id", required=True)
    lane_status.add_argument("--lane-id", help="omit to list every lane of the task")
    lane_status.set_defaults(handler=command_lane_status)

    lane_drop = lane_commands.add_parser("drop")
    add_root(lane_drop)
    lane_drop.add_argument("--task-id", required=True)
    lane_drop.add_argument("--lane-id", required=True)
    lane_drop.set_defaults(handler=command_lane_drop, task_mutation=True)

    commit_check = commands.add_parser(
        "commit-check", help="read-only whole-range Immutable trailer validation"
    )
    add_root(commit_check)
    commit_check.add_argument("--task-id", required=True)
    commit_check.add_argument("--lane-id", required=True)
    commit_check.add_argument("--sha", required=True)
    commit_check.set_defaults(handler=command_commit_check)

    integration = commands.add_parser(
        "integration", help="Git-backed task integration lifecycle"
    )
    integration_commands = integration.add_subparsers(
        dest="integration_command", required=True, parser_class=JsonArgumentParser
    )
    for operation, handler in (
        ("create", command_integration_create),
        ("status", command_integration_status),
        ("collect", command_integration_collect),
        ("candidate", command_integration_candidate),
        ("remove", command_integration_remove),
        ("land", command_integration_land),
        ("list", command_integration_list),
    ):
        operation_parser = integration_commands.add_parser(operation)
        add_root(operation_parser)
        if operation != "list":
            operation_parser.add_argument("--task-id", required=True)
        if operation == "create":
            operation_parser.add_argument("--base", required=True)
        elif operation == "collect":
            operation_parser.add_argument("--lane-id", required=True)
            operation_parser.add_argument("--sha", required=True)
        elif operation == "candidate":
            operation_parser.add_argument("--sha", required=True)
        elif operation == "remove":
            operation_parser.add_argument(
                "--abandon", action="store_true", default=False
            )
        elif operation == "land":
            operation_parser.add_argument("--persist", required=True)
            operation_parser.add_argument("--final", action="store_true", default=False)
            operation_parser.add_argument("--message")
        operation_parser.set_defaults(
            handler=handler,
            task_mutation=operation not in {"status", "list"},
        )

    report = commands.add_parser(
        "report", help="read-only unified lane, task, checks, and candidate report"
    )
    add_root(report)
    report.add_argument("--task-id", required=True)
    report.set_defaults(handler=command_report)

    doctor = commands.add_parser(
        "doctor", help="verify shipped manifest, hashes, and read budgets"
    )
    doctor.set_defaults(handler=command_doctor)
    diff = commands.add_parser("diff", help="compare bundled release manifests")
    diff.add_argument("old_version", type=int)
    diff.add_argument("new_version", type=int)
    diff.add_argument("--runtime", choices=("codex", "claude", "pi"))
    diff.set_defaults(handler=command_diff)

    pin = commands.add_parser("pin", help="pin a task to the installed release")
    pin_commands = pin.add_subparsers(
        dest="pin_command", required=True, parser_class=JsonArgumentParser
    )
    for name, handler in (
        ("status", command_pin_status),
        ("set", command_pin_set),
    ):
        operation = pin_commands.add_parser(name)
        add_root(operation)
        operation.set_defaults(handler=handler, task_mutation=name == "set")

    release = commands.add_parser(
        "release", help="atomic release: bump version, manifest, doctor"
    )
    release.add_argument("--version", type=int)
    release.set_defaults(handler=command_release)
    return parser


def readable_installed_version(skill_dir: Path) -> int | None:
    try:
        return skill_version(skill_dir)
    except (OSError, UnicodeError, OrchestrateError):
        return None


def main(argv: Sequence[str] | None = None) -> int:
    skill_dir = Path(__file__).resolve().parents[2]
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        selected_skill_dir = Path(args.skill_dir).resolve()
        if selected_skill_dir != skill_dir:
            raise OrchestrateError(
                "--skill-dir must resolve to the executing orchestrate package "
                f"({skill_dir})"
            )
        args.skill_dir = str(skill_dir)
        # Unreadable installed metadata is itself the authoritative CLI error;
        # never emit a successful response with unknowable provenance.
        skill_version(skill_dir)
        if getattr(args, "task_mutation", False):
            args.verified_release = require_verified_release(skill_dir)
        payload = args.handler(args)
    except (OSError, UnicodeError, OrchestrateError) as exc:
        payload = {
            "ok": False,
            "orchestrate_version": readable_installed_version(skill_dir),
            "error": {"type": "orchestrate", "message": str(exc)},
        }
        print(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    payload["orchestrate_version"] = readable_installed_version(skill_dir)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok", False) else 1
