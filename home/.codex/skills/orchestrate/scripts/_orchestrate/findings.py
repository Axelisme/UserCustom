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


FINDING_RECEIPT_REQUIRED = ("subject_sha", "verdict", "evidence", "findings")

# These were never receipt vocabulary. Rejecting them rather than guessing an
# interpretation keeps milestone envelopes and review receipts separate.
FORBIDDEN_RECEIPT_KEYS = ("outcome", "review_findings", "P1", "P2")
FORBIDDEN_FINDING_KEYS = ("P1", "P2")


# `id` is mechanical and auto-derived when omitted. `severity` is optional: nothing
# branches on it, so requiring it only made reviewers grade every finding for no
# consumer — it stays available as a human signal. `propagation` is never optional
# and never inferred: it decides whether a finding gates collect, and a tool guessing
# a gating decision would silently weaken the gate.
FINDING_REQUIRED = ("propagation", "behavior", "evidence", "path")


# Every review records exactly one outcome row, whatever its verdict. v102 exempted
# needs_fix on the theory that its findings say everything, but the receipt's own
# evidence — what the reviewer did to reach the verdict — belongs to no single
# finding, so exempting needs_fix silently discarded it in the one case where the
# evidence matters most. Markers carry `kind` and never a `propagation`; finding
# consumers skip them via `dedup_findings`.
REVIEW_PASS_KIND = "review-pass"
MARKER_VERDICTS = FINDING_VERDICTS
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


def canonical_json_identity(value: Any) -> bytes:
    """Keep JSON type distinctions that Python equality conflates (true/1, 1/1.0)."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def review_marker_id(subject: str, verdict: str, evidence: Any) -> str:
    """Deduplicate an exact receipt replay without discarding a distinct review."""
    digest = hashlib.sha256(canonical_json_identity(evidence)).hexdigest()[:12]
    return f"review-{verdict}:{subject}:{digest}"


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


def _nonempty_json(value: Any) -> bool:
    """Require meaningful JSON without constraining evidence's JSON shape."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def normalize_finding_receipt(root: Path, payload: dict[str, Any]) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Validate the canonical receipt and return canonical finding dictionaries.

    Record and validate deliberately call this one parser so validation cannot bless a
    receipt that recording would interpret differently.
    """
    if not isinstance(payload, dict):
        raise OrchestrateError("finding receipt JSON must be an object")
    errors: list[str] = []
    for key in FORBIDDEN_RECEIPT_KEYS:
        if key in payload:
            errors.append(f"noncanonical receipt field: {key}")
    require_json_fields(payload, FINDING_RECEIPT_REQUIRED, errors)
    if "subject_sha" in payload and not isinstance(payload["subject_sha"], str):
        errors.append("receipt subject_sha must be a string")
    if "evidence" in payload and not _nonempty_json(payload["evidence"]):
        errors.append("receipt evidence must be non-empty")
    validate_json_enum(payload, "verdict", FINDING_VERDICTS, errors)
    if errors:
        raise OrchestrateError("invalid finding receipt: " + "; ".join(errors))
    subject = exact_commit(root, payload["subject_sha"], label="receipt subject_sha")
    findings = payload["findings"]
    if not isinstance(findings, list):
        raise OrchestrateError("finding receipt 'findings' must be a list")
    if not findings and payload["verdict"] == "needs_fix":
        raise OrchestrateError("finding receipt 'findings' must be a non-empty list when verdict is 'needs_fix'")

    normalized: list[dict[str, Any]] = []
    finding_ids: set[str] = set()
    for raw in findings:
        if not isinstance(raw, dict):
            raise OrchestrateError("each finding must be an object")
        canonical = dict(raw)
        if "observable_behavior" in canonical:
            alias = canonical.pop("observable_behavior")
            if "behavior" in canonical and (
                type(canonical["behavior"]) is not type(alias)
                or canonical["behavior"] != alias
            ):
                raise OrchestrateError("invalid finding: behavior conflicts with observable_behavior")
            canonical.setdefault("behavior", alias)
        ferrors: list[str] = []
        for key in FORBIDDEN_FINDING_KEYS:
            if key in canonical:
                ferrors.append(f"noncanonical finding field: {key}")
        require_json_fields(canonical, FINDING_REQUIRED, ferrors)
        for key in ("behavior", "path"):
            if key in canonical and (
                not isinstance(canonical[key], str) or not canonical[key].strip()
            ):
                ferrors.append(f"finding {key} must be a non-empty string")
        if "evidence" in canonical and not _nonempty_json(canonical["evidence"]):
            ferrors.append("finding evidence must be non-empty")
        if "id" in canonical and not isinstance(canonical["id"], str):
            ferrors.append("finding id must be a string")
        validate_json_enum(canonical, "severity", FINDING_SEVERITIES, ferrors)
        validate_json_enum(canonical, "propagation", FINDING_PROPAGATIONS, ferrors)
        sweep_required = bool(canonical.get("sweep_required", False))
        if sweep_required and canonical.get("propagation") != "gates-the-slice":
            ferrors.append("sweep_required finding must use propagation 'gates-the-slice'")
        if ferrors:
            raise OrchestrateError("invalid finding: " + "; ".join(ferrors))
        finding_id = (
            require_identifier(canonical["id"], label="finding id")
            if "id" in canonical
            else derived_finding_id(subject, canonical)
        )
        if finding_id in finding_ids:
            raise OrchestrateError(
                "invalid finding receipt: duplicate finding id "
                f"{finding_id!r}; provide distinct explicit ids"
            )
        finding_ids.add(finding_id)
        canonical["id"] = finding_id
        normalized.append(canonical)
    return subject, payload, normalized


def command_findings_validate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    payload, _ = read_json_object(args.receipt, label="finding receipt")
    subject, canonical_receipt, findings = normalize_finding_receipt(root, payload)
    return {
        "ok": True,
        "operation": "findings-validate",
        "read_only": True,
        "subject_sha": subject,
        "verdict": canonical_receipt["verdict"],
        "finding_count": len(findings),
    }


def command_findings_record(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    task_id = require_identifier(task_id_from_ref(args.task_id), label="task-id")
    payload, _ = read_json_object(args.receipt, label="finding receipt")
    subject, payload, findings = normalize_finding_receipt(root, payload)
    normalized: list[dict[str, Any]] = []
    verdict = payload["verdict"]
    ledger_records = read_findings_ledger(root, task_id)
    replayed_marker_id: str | None = None
    if verdict in MARKER_VERDICTS:
        marker = {
            "id": review_marker_id(subject, verdict, payload["evidence"]),
            "kind": f"review-{verdict}",
            "subject_sha": subject,
            "verdict": verdict,
            "evidence": payload["evidence"],
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        replayed_marker = next(
            (
                rec
                for rec in ledger_records
                if rec.get("kind") == marker["kind"]
                and rec.get("subject_sha") == subject
                and rec.get("verdict") == verdict
                and canonical_json_identity(rec.get("evidence"))
                == canonical_json_identity(payload["evidence"])
            ),
            None,
        )
        if replayed_marker is None:
            normalized.append(marker)
        else:
            replayed_marker_id = replayed_marker["id"]
    for raw in findings:
        sweep_required = bool(raw.get("sweep_required", False))
        normalized.append(
            {
                "id": raw["id"],
                "severity": raw.get("severity"),
                "propagation": raw["propagation"],
                "owner": raw.get("owner", "original-writer"),
                "path": raw["path"],
                "behavior": raw["behavior"],
                "evidence": raw["evidence"],
                "root_cause": raw.get("root_cause"),
                "sweep_required": sweep_required,
                "requires_refreshed_review": bool(raw.get("requires_refreshed_review", False)),
                "subject_sha": subject,
                "verdict": verdict,
                "opened_at": datetime.now(UTC).isoformat(),
            }
        )
    existing = {rec["id"] for rec in ledger_records}
    path = findings_ledger_path(root, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    appended: list[str] = []
    skipped: list[str] = [replayed_marker_id] if replayed_marker_id else []
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


def _finding_touches(rec: dict[str, Any], query_paths: list[str]) -> bool:
    """A finding matches a query path when they name the same file, or one is a
    directory containing the other — so a reviewer's changed file finds findings on
    that file, on its directory, and vice versa."""
    path = (rec.get("path") or "").strip().strip("/")
    if not path:
        return False
    for raw in query_paths:
        query = raw.strip().strip("/")
        if not query:
            continue
        if path == query or path.startswith(query + "/") or query.startswith(path + "/"):
            return True
    return False


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
    review_outcomes = list(dedup_review_pass(records).values())
    # Only what the caller cannot compute from the lists above is reported. Every
    # extra projection is another view that can disagree with its source — which is
    # exactly how a subject once appeared as both clean and incomplete at once.
    # `slice_blocking` stays because it needs git ancestry, which the caller lacks:
    # a gating finding on another lane does not block this slice, and the test
    # mirrors what collect itself gates on so display can never contradict the gate.
    slice_blocking: list[str] | None = None
    slice_sha = getattr(args, "slice_sha", None)
    if slice_sha:
        subject = exact_commit(root, slice_sha, label="slice SHA")
        slice_blocking = [
            rec["id"]
            for rec in open_recs
            if rec["propagation"] == "gates-the-slice"
            and (
                not rec.get("subject_sha")
                or is_ancestor(root, rec["subject_sha"], subject)
            )
        ]
    # Directed pull for a reviewer inheriting a surface across waves: the ledger is
    # task-long, so a finding an earlier wave logged on a file is still here — the
    # reviewer just needs to find it without reading the whole ledger. Its own diff's
    # paths are the query key (bounded by diff size, relevant by construction), and
    # `--sweep` finds the cross-cutting root-cause patterns a path query cannot. This
    # is a projection over the same open/closed rows, never a second source: gating
    # still reads the full set, so a filter can never weaken the gate.
    query_paths = getattr(args, "path", None)
    sweep_only = getattr(args, "sweep", False)
    matched: list[dict[str, Any]] | None = None
    if query_paths or sweep_only:
        matched = [
            rec
            for rec in (*open_recs, *closed_recs)
            if (not sweep_only or rec.get("sweep_required"))
            and (not query_paths or _finding_touches(rec, query_paths))
        ]
    return {
        "ok": True,
        "operation": "findings-status",
        "read_only": True,
        "task_id": task_id,
        "reachable_from": reachable,
        "open": open_recs,
        "closed": closed_recs,
        "gating_open": gating_open,
        "collect_blocked": bool(gating_open),
        "slice_blocking": slice_blocking,
        "matched": matched,
        "review_outcomes": review_outcomes,
    }
