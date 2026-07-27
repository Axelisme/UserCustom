from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn, Sequence

from .admission import (
    DEFAULT_FAMILY_TOKENS,
    DEFAULT_FILE_ADDED,
    DEFAULT_FOCUS_DAYS,
    DEFAULT_SLICE_ADDED,
    DEFAULT_SLICE_WAVES,
    command_admission,
)
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
    command_integration_collect,
    command_integration_create,
    command_integration_publish,
    command_integration_remove,
    command_integration_status,
    command_lane_create,
    command_lane_drop,
    command_lane_status,
    command_profile_report,
)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise OrchestrateError(message)


def add_root(command: argparse.ArgumentParser) -> None:
    command.add_argument("--root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[2]))
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)

    lane = commands.add_parser("lane", help="Git-backed lane lifecycle")
    lane_commands = lane.add_subparsers(dest="lane_command", required=True, parser_class=JsonArgumentParser)

    lane_create = lane_commands.add_parser("create")
    add_root(lane_create)
    lane_create.add_argument("--task-id", required=True)
    lane_create.add_argument("--lane-id", required=True)
    lane_create.add_argument("--base", required=True)
    lane_create.set_defaults(handler=command_lane_create)

    lane_status = lane_commands.add_parser("status")
    add_root(lane_status)
    lane_status.add_argument("--task-id", required=True)
    lane_status.add_argument("--lane-id", help="omit to list every lane of the task")
    lane_status.set_defaults(handler=command_lane_status)

    lane_drop = lane_commands.add_parser("drop")
    add_root(lane_drop)
    lane_drop.add_argument("--task-id", required=True)
    lane_drop.add_argument("--lane-id", required=True)
    lane_drop.set_defaults(handler=command_lane_drop)

    integration = commands.add_parser("integration", help="Git-backed task integration lifecycle")
    integration_commands = integration.add_subparsers(dest="integration_command", required=True, parser_class=JsonArgumentParser)
    for operation, handler in (
        ("create", command_integration_create),
        ("status", command_integration_status),
        ("collect", command_integration_collect),
        ("publish", command_integration_publish),
        ("remove", command_integration_remove),
    ):
        operation_parser = integration_commands.add_parser(operation)
        add_root(operation_parser)
        operation_parser.add_argument("--task-id", required=True)
        if operation == "create":
            operation_parser.add_argument("--base", required=True)
        elif operation == "collect":
            operation_parser.add_argument("--lane-id", required=True)
            operation_parser.add_argument("--sha", required=True)
        elif operation == "publish":
            operation_parser.add_argument("--sha", required=True)
        operation_parser.set_defaults(handler=handler)

    profile = commands.add_parser("profile", help="read-only Git profile projections")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True, parser_class=JsonArgumentParser)
    report = profile_commands.add_parser("report")
    add_root(report)
    report.add_argument("--task-id", required=True)
    report.add_argument("--wave-id", required=True)
    report.add_argument("--base", required=True)
    report.set_defaults(handler=command_profile_report)

    admission = commands.add_parser("admission", help="dev-flow S3 milestone admission projection")
    add_root(admission)
    admission.add_argument("--base", required=True)
    admission.add_argument("--tip", required=True)
    admission.add_argument("--max-slice-waves", type=int, default=DEFAULT_SLICE_WAVES)
    admission.add_argument("--max-slice-added", type=int, default=DEFAULT_SLICE_ADDED)
    admission.add_argument("--max-file-added", type=int, default=DEFAULT_FILE_ADDED)
    admission.add_argument("--focus-days", type=int, default=DEFAULT_FOCUS_DAYS)
    admission.add_argument("--slice-family-tokens", type=int, default=DEFAULT_FAMILY_TOKENS, help="leading Slice-id tokens that identify one Slice family across renamed correction Waves")
    admission.add_argument("--production-path", action="append", help="production source root; repeat for multiple roots")
    admission.add_argument("--reachability-cmd", help="shell command; exit 0 means a production entrypoint reaches the new modules")
    admission.add_argument("--file-reachability-cmd", help="shell command run per oversized file; reads ORCHESTRATE_PRODUCTION_PATH and exits 0 when that file is reachable")
    admission.add_argument("--burndown", help="path to the Slice x status projection")
    admission.add_argument("--burndown-previous", help="its sha256 at the previous milestone")
    admission.add_argument("--findings", type=int, help="review findings raised this round")
    admission.add_argument("--backlog", type=int, help="of those, how many were downgraded")
    admission.set_defaults(handler=command_admission)

    doctor = commands.add_parser("doctor", help="verify shipped manifest, hashes, and read budgets")
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
