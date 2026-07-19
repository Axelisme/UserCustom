from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError, read_json_object, require_identifier, require_json_fields, validate_json_enum
from .git_ops import common_repo_root, exact_commit, run_git

CLOSES_FINDING_PATTERN = re.compile(r"^Closes-Finding:\s*(\S+)\s*$", re.MULTILINE)


FINDING_SEVERITIES = ("blocker", "major", "minor")


FINDING_PROPAGATIONS = (
    "gates-the-slice",
    "follow-up-to-writer",
    "task-plan",
    "backlog",
)


FINDING_VERDICTS = ("pass", "needs_fix")


FINDING_RECEIPT_REQUIRED = ("subject_sha", "verdict", "findings")


FINDING_REQUIRED = ("id", "severity", "propagation")


def findings_ledger_path(root: Path, task_id: str) -> Path:
    return (
        common_repo_root(root)
        / ".agent_state"
        / "orchestrate"
        / "findings"
        / f"{task_id}.jsonl"
    )


def task_id_from_ref(task_ref: str) -> str:
    """Derive the task id from a task ref (`task/<id>` -> `<id>`)."""
    return task_ref.split("/", 1)[1] if task_ref.startswith("task/") else task_ref


def read_findings_ledger(root: Path, task_id: str) -> list[dict[str, Any]]:
    path = findings_ledger_path(root, task_id)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            records.append(json.loads(stripped))
    return records


def dedup_findings(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """First occurrence of each finding id, preserving ledger order."""
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        seen.setdefault(rec["id"], rec)
    return seen


def closed_finding_ids(root: Path, reachable_from: str) -> dict[str, str]:
    """Finding id -> closing SHA, derived from ``Closes-Finding`` trailers reachable
    from a ref. Closure is a derived read of git, never a stored status flag, so the
    absence of the fix commit — not a flag someone forgot to flip — is what stays open."""
    log = run_git(root, "log", "--format=%H%x1f%B%x1e", reachable_from, check=False)
    closed: dict[str, str] = {}
    if log.returncode != 0:
        return closed
    for chunk in log.stdout.split("\x1e"):
        sha, _, body = chunk.strip().partition("\x1f")
        if not sha:
            continue
        for fid in CLOSES_FINDING_PATTERN.findall(body):
            closed.setdefault(fid, sha)
    return closed


def command_findings_record(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    payload, _ = read_json_object(args.receipt, label="finding receipt")
    errors: list[str] = []
    require_json_fields(payload, FINDING_RECEIPT_REQUIRED, errors)
    validate_json_enum(payload, "verdict", FINDING_VERDICTS, errors)
    if errors:
        raise OrchestrateError("invalid finding receipt: " + "; ".join(errors))
    subject = exact_commit(root, payload["subject_sha"], label="receipt subject_sha")
    findings = payload["findings"]
    if not isinstance(findings, list) or not findings:
        raise OrchestrateError("finding receipt 'findings' must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    for raw in findings:
        if not isinstance(raw, dict):
            raise OrchestrateError("each finding must be an object")
        ferrors: list[str] = []
        require_json_fields(raw, FINDING_REQUIRED, ferrors)
        validate_json_enum(raw, "severity", FINDING_SEVERITIES, ferrors)
        validate_json_enum(raw, "propagation", FINDING_PROPAGATIONS, ferrors)
        sweep_required = bool(raw.get("sweep_required", False))
        if sweep_required and raw.get("propagation") != "gates-the-slice":
            # A root-cause sweep must block collect until fixed surface-wide;
            # allowing a follow-up/backlog propagation would let a partially
            # swept pattern pass integration with adjacent instances still live.
            ferrors.append(
                "sweep_required finding must use propagation 'gates-the-slice'"
            )
        if ferrors:
            raise OrchestrateError("invalid finding: " + "; ".join(ferrors))
        normalized.append(
            {
                "id": require_identifier(raw["id"], label="finding id"),
                "severity": raw["severity"],
                "propagation": raw["propagation"],
                "owner": raw.get("owner", "original-writer"),
                "path": raw.get("path"),
                "root_cause": raw.get("root_cause"),
                "sweep_required": sweep_required,
                "requires_refreshed_review": bool(
                    raw.get("requires_refreshed_review", False)
                ),
                "subject_sha": subject,
                "verdict": payload["verdict"],
                "opened_at": datetime.now(UTC).isoformat(),
            }
        )
    existing = {rec["id"] for rec in read_findings_ledger(root, task_id)}
    path = findings_ledger_path(root, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    appended: list[str] = []
    skipped: list[str] = []
    with path.open("a", encoding="utf-8") as handle:
        for rec in normalized:
            if rec["id"] in existing:
                skipped.append(rec["id"])
                continue
            handle.write(json.dumps(rec, sort_keys=True) + "\n")
            existing.add(rec["id"])
            appended.append(rec["id"])
    return {
        "ok": True,
        "operation": "findings-record",
        "task_id": task_id,
        "subject_sha": subject,
        "verdict": payload["verdict"],
        "appended": appended,
        "skipped_existing": skipped,
    }


def command_findings_status(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    reachable = args.task_ref or "HEAD"
    closed = closed_finding_ids(root, reachable)
    open_recs: list[dict[str, Any]] = []
    closed_recs: list[dict[str, Any]] = []
    for fid, rec in dedup_findings(read_findings_ledger(root, task_id)).items():
        entry = {**rec, "closed_by": closed.get(fid)}
        (closed_recs if fid in closed else open_recs).append(entry)
    gating_open = [r["id"] for r in open_recs if r["propagation"] == "gates-the-slice"]
    sweep_open = [r["id"] for r in open_recs if r.get("sweep_required")]
    return {
        "ok": True,
        "operation": "findings-status",
        "read_only": True,
        "task_id": task_id,
        "reachable_from": reachable,
        "open": open_recs,
        "closed": closed_recs,
        "gating_open": gating_open,
        "sweep_open": sweep_open,
        "collect_blocked": bool(gating_open),
    }
