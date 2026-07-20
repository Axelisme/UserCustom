from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError, read_json_object, require_identifier, require_json_fields, validate_json_enum
from .git_ops import common_repo_root, exact_commit, is_ancestor, run_git

CLOSES_FINDING_PATTERN = re.compile(r"^Closes-Finding:\s*(\S+)\s*$", re.MULTILINE)


FINDING_SEVERITIES = ("blocker", "major", "minor")


FINDING_PROPAGATIONS = (
    "gates-the-slice",
    "follow-up-to-writer",
    "task-plan",
    "backlog",
)


# One vocabulary for "how did the review end", shared with the milestone envelope.
# Before v102 the ledger took only pass/needs_fix while reviewers were told to close
# with pass|needs_fix|blocked|needs_decision, so an honestly-reported blocked review
# — a gate the sandbox could not run — was rejected outright and fell on the floor.
FINDING_VERDICTS = ("pass", "needs_fix", "blocked", "needs_decision")


FINDING_RECEIPT_REQUIRED = ("subject_sha", "verdict", "findings")


# `id` is mechanical and auto-derived when omitted. `severity` is optional: nothing
# branches on it, so requiring it only made reviewers grade every finding for no
# consumer — it stays available as a human signal. `propagation` is never optional
# and never inferred: it decides whether a finding gates collect, and a tool guessing
# a gating decision would silently weaken the gate.
FINDING_REQUIRED = ("propagation",)


# A review that produced no findings still happened: pass, blocked and needs_decision
# each record one marker row so the outcome has a durable home instead of living only
# in prose. needs_fix is fully represented by its findings and takes no marker.
# Markers carry `kind` and never a `propagation`; finding consumers skip them via
# `dedup_findings`.
REVIEW_PASS_KIND = "review-pass"
MARKER_VERDICTS = ("pass", "blocked", "needs_decision")
MARKER_KINDS = frozenset(f"review-{verdict}" for verdict in MARKER_VERDICTS)


def derived_finding_id(subject: str, raw: dict[str, Any]) -> str:
    """Stable id for a finding that did not name one, keyed on the finding's semantic
    content so distinct findings on one subject never collide and identical ones dedup."""
    # The original identity set, hashed exactly as it always was — including explicit
    # nulls — so ids minted by earlier releases stay reproducible.
    fields: dict[str, Any] = {
        "severity": raw.get("severity"),
        "propagation": raw.get("propagation"),
        "path": raw.get("path"),
        "root_cause": raw.get("root_cause"),
        "sweep_required": bool(raw.get("sweep_required", False)),
    }
    # EVERY field added from here on must go through `widen`, never into the dict
    # above: an unconditional field renumbers every finding recorded before it
    # existed, so a replayed receipt lands a second copy that no Closes-Finding
    # trailer will ever close. That is exactly how this function broke once already.
    def widen(key: str, value: Any) -> None:
        """Join the identity only when actually used, so adding a field separates
        the findings that use it without renumbering the ones that do not."""
        if value is not None and value is not False:
            fields[key] = value

    widen("owner", raw.get("owner"))
    widen("requires_refreshed_review", raw.get("requires_refreshed_review") or None)
    identity = json.dumps(fields, sort_keys=True)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    return f"{subject[:12]}-{digest}"


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
    """First occurrence of each finding id, preserving ledger order. Review-pass
    markers are not findings and are excluded here, so every finding consumer
    (collect gating, worktree cleanup, status) sees only true finding rows."""
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        if rec.get("kind") in MARKER_KINDS:
            continue
        seen.setdefault(rec["id"], rec)
    return seen


def dedup_review_pass(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """First occurrence of each review-outcome marker id, preserving ledger order."""
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        if rec.get("kind") in MARKER_KINDS:
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
    task_id = require_identifier(task_id_from_ref(args.task_id), label="task-id")
    payload, _ = read_json_object(args.receipt, label="finding receipt")
    errors: list[str] = []
    require_json_fields(payload, FINDING_RECEIPT_REQUIRED, errors)
    validate_json_enum(payload, "verdict", FINDING_VERDICTS, errors)
    if errors:
        raise OrchestrateError("invalid finding receipt: " + "; ".join(errors))
    subject = exact_commit(root, payload["subject_sha"], label="receipt subject_sha")
    findings = payload["findings"]
    if not isinstance(findings, list):
        raise OrchestrateError("finding receipt 'findings' must be a list")
    verdict = payload["verdict"]
    normalized: list[dict[str, Any]] = []
    if not findings and verdict == "needs_fix":
        # needs_fix is represented entirely by its findings; with none there is
        # nothing to close, so it stays rejected.
        raise OrchestrateError(
            "finding receipt 'findings' must be a non-empty list when verdict is"
            " 'needs_fix'"
        )
    if verdict in MARKER_VERDICTS:
        # The outcome itself is recorded, so a review that ended blocked or
        # undecided has a durable home instead of being dropped for lack of findings.
        normalized.append(
            {
                "id": f"review-{verdict}:{subject}",
                "kind": f"review-{verdict}",
                "subject_sha": subject,
                "verdict": verdict,
                "evidence": payload.get("evidence"),
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )
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
                # Derived from the finding's own content, never its position: two
                # distinct findings recorded against one subject in separate receipts
                # would otherwise share an id, and the second — possibly the gating
                # one — would be silently dropped as a duplicate. Identical content
                # still dedups, which is what makes re-recording a receipt safe.
                "id": require_identifier(
                    raw["id"] if raw.get("id") else derived_finding_id(subject, raw),
                    label="finding id",
                ),
                "severity": raw.get("severity"),
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
    task_id = require_identifier(task_id_from_ref(args.task_id), label="task-id")
    reachable = args.task_ref or "HEAD"
    records = read_findings_ledger(root, task_id)
    closed = closed_finding_ids(root, reachable)
    open_recs: list[dict[str, Any]] = []
    closed_recs: list[dict[str, Any]] = []
    for fid, rec in dedup_findings(records).items():
        entry = {**rec, "closed_by": closed.get(fid)}
        (closed_recs if fid in closed else open_recs).append(entry)
    gating_open = [r["id"] for r in open_recs if r["propagation"] == "gates-the-slice"]
    sweep_open = [r["id"] for r in open_recs if r.get("sweep_required")]
    review_pass = list(dedup_review_pass(records).values())
    reviewed_clean = sorted(
        {r["subject_sha"] for r in review_pass if r.get("verdict") == "pass"}
    )
    # A blocked or undecided review is not a pass: the slice has no complete
    # evidence, and root has to see that rather than infer it from silence. A later
    # pass on the same subject settles it, so the two lists never both claim a sha.
    review_incomplete = sorted(
        {r["subject_sha"] for r in review_pass if r.get("verdict") != "pass"}
        - set(reviewed_clean)
    )
    # Scope buckets answer "does this block *my* slice", which the flat open list
    # cannot: a gating finding on another lane is not this slice's problem. The
    # ancestry test mirrors what collect itself gates on, so the display can never
    # disagree with the gate. `collect_blocked` keeps its task-wide meaning.
    unrelated_open = [
        r["id"] for r in open_recs if r["propagation"] != "gates-the-slice"
    ]
    slice_blocking: list[str] | None = None
    task_wide = list(gating_open)
    slice_sha = getattr(args, "slice_sha", None)
    if slice_sha:
        subject = exact_commit(root, slice_sha, label="slice SHA")
        slice_blocking = []
        task_wide = []
        for rec in open_recs:
            if rec["propagation"] != "gates-the-slice":
                continue
            rec_subject = rec.get("subject_sha")
            if not rec_subject or is_ancestor(root, rec_subject, subject):
                slice_blocking.append(rec["id"])
            else:
                task_wide.append(rec["id"])
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
        "slice_blocking": slice_blocking,
        "task_wide": task_wide,
        "unrelated_open": unrelated_open,
        "review_pass": review_pass,
        "reviewed_clean": reviewed_clean,
        "review_incomplete": review_incomplete,
    }
