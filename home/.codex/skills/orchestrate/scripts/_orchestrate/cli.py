from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn, Sequence

from .coordination import (
    integration_collect,
    integration_create,
    integration_reconcile,
    integration_remove,
    lane_check,
    lane_comment,
    lane_commit,
    lane_create,
    lane_drop,
    lane_sync,
    status,
)
from .delivery import (
    acceptance_result,
    acceptance_start,
    integration_land,
)
from .primitives import CommandResult, OrchestrateError
from .release import (
    doctor_diff,
    doctor_package,
    pin_set,
    pin_status,
    release_package,
    require_intact_package,
    show_section,
    require_verified_release,
)
from .resources import RepositoryContext, TaskResources
from .telemetry import write_report

ORCHESTRATE_VERSION = 177


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise OrchestrateError(message, "cli_usage")


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--version", dest="version_query", action="store_true")
    commands = parser.add_subparsers(dest="command", required=False, parser_class=JsonArgumentParser)

    show = commands.add_parser("show")
    show.add_argument("address", metavar="FILE#SECTION")
    show.set_defaults(route="show", mutation=False)

    status_parser = commands.add_parser("status")
    status_parser.add_argument("--task-id")
    status_parser.add_argument("--step", action="store_true")
    status_parser.set_defaults(route="status", mutation=False)

    lane = commands.add_parser("lane")
    lane_commands = lane.add_subparsers(dest="lane_command", required=True, parser_class=JsonArgumentParser)
    for name in ("create", "check", "sync", "drop"):
        op = lane_commands.add_parser(name)
        op.add_argument("--task-id", required=True)
        op.add_argument("--lane-id", required=True)
        if name == "create":
            op.add_argument("--comment")
        if name == "check":
            op.add_argument("--expect-mode", choices=("tdd", "direct"))
        op.set_defaults(route=f"lane-{name}", mutation=True)
    commit = lane_commands.add_parser("commit")
    commit.add_argument("--task-id", required=True)
    commit.add_argument("--lane-id", required=True)
    commit.add_argument("--message-file", required=True)
    commit_mode = commit.add_mutually_exclusive_group()
    commit_mode.add_argument("--contract", action="store_true")
    commit_mode.add_argument("--amend-frozen", action="store_true")
    commit.set_defaults(route="lane-commit", mutation=True)
    comment = lane_commands.add_parser("comment")
    comment.add_argument("--task-id", required=True)
    comment.add_argument("--lane-id", required=True)
    comment_choice = comment.add_mutually_exclusive_group(required=True)
    comment_choice.add_argument("--text")
    comment_choice.add_argument("--clear", action="store_true")
    comment.set_defaults(route="lane-comment", mutation=True)

    integration = commands.add_parser("integration")
    integration_commands = integration.add_subparsers(dest="integration_command", required=True, parser_class=JsonArgumentParser)
    create = integration_commands.add_parser("create")
    create.add_argument("--task-id", required=True)
    create.set_defaults(route="integration-create", mutation=True)
    collect = integration_commands.add_parser("collect")
    collect.add_argument("--task-id", required=True)
    collect.add_argument("--lane-id", required=True)
    collect.add_argument("--ticket", required=True)
    collect.set_defaults(route="integration-collect", mutation=True)
    reconcile = integration_commands.add_parser("reconcile")
    reconcile.add_argument("--task-id", required=True)
    reconcile.add_argument("--lane-id", required=True)
    reconcile.add_argument("--persist", required=True)
    reconcile.set_defaults(route="integration-reconcile", mutation=True)
    land = integration_commands.add_parser("land")
    land.add_argument("--task-id", required=True)
    land.add_argument("--persist", required=True)
    land.add_argument("--message")
    land.set_defaults(route="integration-land", mutation=True)
    remove = integration_commands.add_parser("remove")
    remove.add_argument("--task-id", required=True)
    report_choice = remove.add_mutually_exclusive_group(required=True)
    report_choice.add_argument("--output-dir")
    report_choice.add_argument("--no-report", action="store_true")
    remove.add_argument("--abandon", action="store_true")
    remove.set_defaults(route="integration-remove", mutation=True)

    acceptance = commands.add_parser("acceptance")
    acceptance_commands = acceptance.add_subparsers(dest="acceptance_command", required=True, parser_class=JsonArgumentParser)
    start = acceptance_commands.add_parser("start")
    start.add_argument("--task-id", required=True)
    start.add_argument("--sha")
    start.set_defaults(route="acceptance-start", mutation=True)
    result = acceptance_commands.add_parser("result")
    result.add_argument("--task-id", required=True)
    result.add_argument("--verifier", choices=("agent", "user"), required=True)
    result.add_argument("--outcome", choices=("pass", "fail"), required=True)
    result.set_defaults(route="acceptance-result", mutation=True)

    report = commands.add_parser("report")
    report.add_argument("--task-id", required=True)
    report.add_argument("--output-dir", required=True)
    report.set_defaults(route="report", mutation=False)

    pin = commands.add_parser("pin")
    pin_commands = pin.add_subparsers(dest="pin_command", required=True, parser_class=JsonArgumentParser)
    for name in ("status", "set"):
        op = pin_commands.add_parser(name)
        op.set_defaults(route=f"pin-{name}", mutation=name == "set")

    doctor = commands.add_parser("doctor")
    doctor.add_argument("--path")
    doctor_commands = doctor.add_subparsers(dest="doctor_command", parser_class=JsonArgumentParser)
    diff = doctor_commands.add_parser("diff")
    diff.add_argument("old_version", type=int)
    diff.add_argument("new_version", type=int)
    diff.add_argument("--runtime", choices=("codex", "claude", "pi"))
    diff.set_defaults(route="doctor-diff", mutation=False)
    doctor.set_defaults(route="doctor", mutation=False)

    release = commands.add_parser("release")
    release.add_argument("--version", type=int, required=True)
    release.add_argument("--drop", action="append", default=[], metavar="PATH")
    release.set_defaults(route="release", mutation=True)
    return parser


def _operation(args: argparse.Namespace) -> str:
    return str(getattr(args, "route", "cli"))


def _run(
    args: argparse.Namespace,
    repo: RepositoryContext | None,
    skill_dir: Path,
) -> CommandResult:
    route = args.route
    if route == "version":
        return CommandResult(True, {})
    if route == "show":
        return show_section(skill_dir, args.address)
    if route == "pin-status":
        assert repo is not None
        return pin_status(repo.worktree_root, skill_dir)
    if route == "pin-set":
        assert repo is not None
        return pin_set(repo.worktree_root, skill_dir)
    if route == "doctor":
        return doctor_package(skill_dir, repo)
    if route == "doctor-diff":
        return doctor_diff(skill_dir, args.old_version, args.new_version, args.runtime)
    if route == "release":
        return release_package(skill_dir, args.version)
    if repo is None:
        raise OrchestrateError("current directory is not a Git repository", "not_git_repository")
    if route == "status":
        return status(repo, args.task_id, include_step=args.step)
    if route == "integration-create":
        return integration_create(repo, args.task_id)
    if route == "lane-create":
        return lane_create(repo, args.task_id, args.lane_id, args.comment)
    if route == "lane-comment":
        return lane_comment(repo, args.task_id, args.lane_id, args.text, args.clear)
    if route == "lane-check":
        return lane_check(repo, args.task_id, args.lane_id, args.expect_mode)
    if route == "lane-commit":
        return lane_commit(
            repo,
            args.task_id,
            args.lane_id,
            args.message_file,
            contract=args.contract,
            amend_frozen=args.amend_frozen,
        )
    if route == "lane-sync":
        return lane_sync(repo, args.task_id, args.lane_id)
    if route == "lane-drop":
        return lane_drop(repo, args.task_id, args.lane_id)
    if route == "integration-collect":
        return integration_collect(repo, args.task_id, args.lane_id, args.ticket)
    if route == "acceptance-start":
        return acceptance_start(repo, args.task_id, args.sha)
    if route == "acceptance-result":
        return acceptance_result(repo, args.task_id, args.outcome, args.verifier)
    if route == "integration-reconcile":
        return integration_reconcile(repo, args.task_id, args.lane_id, args.persist)
    if route == "integration-land":
        return integration_land(repo, args.task_id, args.persist, args.message)
    if route == "integration-remove":
        return integration_remove(
            repo,
            args.task_id,
            abandon=args.abandon,
            output_dir=Path(args.output_dir) if args.output_dir is not None else None,
        )
    if route == "report":
        return write_report(
            TaskResources.derive(repo, args.task_id), Path(args.output_dir)
        )
    raise OrchestrateError(f"{route} is not implemented in this tracer", "cli_usage")


def main(argv: Sequence[str] | None = None) -> int:
    skill_dir = Path(__file__).resolve().parents[2]
    operation = "cli"
    args: argparse.Namespace | None = None
    repo: RepositoryContext | None = None
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        if getattr(args, "version_query", False):
            if getattr(args, "command", None) is not None:
                raise OrchestrateError("--version cannot be used with a command", "cli_usage")
            args.route = "version"
            args.mutation = False
        elif getattr(args, "command", None) is None:
            raise OrchestrateError("a command is required", "cli_usage")
        operation = _operation(args)
        selected = Path(args.skill_dir).resolve()
        if selected != skill_dir:
            raise OrchestrateError("--skill-dir must resolve to the executing package", "cli_usage")
        if getattr(args, "mutation", False):
            # Publication edits the very documents the current manifest hashes,
            # so it is gated on package integrity rather than on hash equality.
            try:
                if operation == "release":
                    require_intact_package(
                        skill_dir, frozenset(getattr(args, "drop", None) or ())
                    )
                else:
                    require_verified_release(skill_dir)
            except (OSError, UnicodeError, OrchestrateError) as exc:
                raise OrchestrateError(str(exc), "package_unhealthy") from exc
        discovery_path = (
            Path(args.path).resolve()
            if operation == "doctor" and args.path is not None
            else Path.cwd()
        )
        try:
            repo = RepositoryContext.discover(discovery_path)
        except OrchestrateError:
            if operation in {"version", "show", "doctor", "doctor-diff", "release"}:
                repo = None
            else:
                raise
        result = _run(args, repo, skill_dir)
        if operation == "show":
            sys.stdout.write(str(result.data["text"]))
            return 0
        response_version = (
            args.version
            if operation == "release" and result.ok
            else ORCHESTRATE_VERSION
        )
        payload: dict[str, object] = {
            "ok": result.ok,
            "operation": operation,
            "orchestrate_version": response_version,
        }
        payload.update(result.data)
        if result.warnings:
            payload["warnings"] = list(result.warnings)
        if result.diagnostics:
            payload["diagnostics"] = [dict(item) for item in result.diagnostics]
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if result.ok else 1
    except (OSError, UnicodeError, OrchestrateError) as exc:
        code = getattr(exc, "code", "git_error")
        error = {"code": code, "message": str(exc)}
        repair = getattr(exc, "repair", None)
        if repair is not None:
            error["repair"] = repair
        payload = {
            "ok": False,
            "operation": operation,
            "orchestrate_version": ORCHESTRATE_VERSION,
            "error": error,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
