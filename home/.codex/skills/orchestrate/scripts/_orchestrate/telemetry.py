from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .git_ops import run_git
from .primitives import CommandResult, OrchestrateError
from .resources import TaskResources

_EVENT_OPERATIONS = frozenset(
    {
        "integration-create",
        "lane-create",
        "lane-comment",
        "lane-check",
        "lane-commit",
        "lane-sync",
        "lane-drop",
        "integration-collect",
        "integration-reconcile",
        "integration-land",
        "integration-remove",
        "acceptance-start",
        "acceptance-result",
        "timing-pause",
        "timing-resume",
    }
)


_PIN_CACHE: dict[Path, int | None] = {}


def _repo_pin(task: TaskResources) -> int | None:
    """The pin in force while this event was written, or None when the repo has none.

    Cached per control root: a pin cannot change inside one process without the pin command, which
    ends the process. Any read failure answers None — telemetry is observational and never fails
    the operation it is describing.
    """
    root = task.repo.control_root
    if root not in _PIN_CACHE:
        from .release import read_version_pin

        try:
            payload = read_version_pin(root)
        except (OSError, UnicodeError, OrchestrateError):
            payload = None
        _PIN_CACHE[root] = payload.get("skill_version") if payload else None
    return _PIN_CACHE[root]


def _event_bytes(
    task: TaskResources, operation: str, outcome: str, **extra: Any
) -> bytes:
    # Deferred: cli imports this module, so the constant is only reachable once cli has loaded.
    from .cli import ORCHESTRATE_VERSION

    event: dict[str, Any] = {
        "event_version": 1,
        "at": datetime.now(UTC).isoformat(),
        "task_id": task.task_id,
        "operation": operation,
        "outcome": outcome,
        # Which code wrote this line, and which version the repo was pinned to at the time. A
        # report that mixes versions can otherwise not say which behaviour produced which number.
        "orchestrate_version": ORCHESTRATE_VERSION,
        "repo_pin": _repo_pin(task),
    }
    nullable = {"previous_sha", "current_sha", "comment"}
    event.update(
        {
            key: value
            for key, value in extra.items()
            if value is not None or key in nullable
        }
    )
    return (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _append(task: TaskResources, data: bytes) -> None:
    task.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        task.telemetry_path,
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
        0o600,
    )
    try:
        os.write(descriptor, data)
    finally:
        os.close(descriptor)


def record_event(
    task: TaskResources,
    operation: str,
    outcome: str,
    **extra: Any,
) -> tuple[str, ...]:
    """Append one observational event without becoming workflow authority."""
    try:
        _append(task, _event_bytes(task, operation, outcome, **extra))
    except OSError:
        return ("telemetry could not be recorded",)
    return ()


def require_event(
    task: TaskResources,
    operation: str,
    outcome: str,
    **extra: Any,
) -> None:
    """Append an explicitly requested timing transition or fail it."""
    try:
        _append(task, _event_bytes(task, operation, outcome, **extra))
    except OSError as exc:
        raise OrchestrateError(
            "telemetry timing transition could not be recorded",
            "telemetry_write_failed",
        ) from exc


def _decode_events(raw: bytes) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    invalid = 0
    for line in raw.splitlines():
        try:
            value = json.loads(line.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            if value.get("event_version") != 1:
                raise ValueError
            if not all(
                isinstance(value.get(key), str) and value[key]
                for key in ("at", "task_id", "operation", "outcome")
            ):
                raise ValueError
            if value["operation"] not in _EVENT_OPERATIONS:
                raise ValueError
            parsed = datetime.fromisoformat(value["at"])
            if parsed.tzinfo is None:
                raise ValueError
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            invalid += 1
            continue
        events.append(value)
    return events, invalid


def _read_raw(task: TaskResources) -> tuple[bytes, list[str]]:
    try:
        return task.telemetry_path.read_bytes(), []
    except FileNotFoundError:
        return b"", ["telemetry is missing"]
    except OSError as exc:
        raise OrchestrateError(
            f"cannot read telemetry: {exc}", "report_read_failed"
        ) from exc


def _time(event: Mapping[str, object]) -> datetime:
    value = event["at"]
    assert isinstance(value, str)
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    return parsed


def _seconds(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds())


def _pause_intervals(
    events: list[dict[str, object]], now: datetime
) -> list[tuple[datetime, datetime, str, str | None]]:
    intervals: list[tuple[datetime, datetime, str, str | None]] = []
    opened: tuple[datetime, str] | None = None
    for event in events:
        operation = event["operation"]
        outcome = event["outcome"]
        if operation == "timing-pause" and outcome == "success" and opened is None:
            opened = (_time(event), str(event["at"]))
        elif operation == "timing-resume" and outcome == "success" and opened is not None:
            end = _time(event)
            intervals.append((opened[0], end, opened[1], str(event["at"])))
            opened = None
    if opened is not None:
        intervals.append((opened[0], now, opened[1], None))
    return intervals


def _recorded_seconds(
    start: datetime,
    end: datetime,
    pauses: list[tuple[datetime, datetime, str, str | None]],
) -> float:
    paused = 0.0
    for pause_start, pause_end, _start_text, _end_text in pauses:
        overlap_start = max(start, pause_start)
        overlap_end = min(end, pause_end)
        if overlap_end > overlap_start:
            paused += (overlap_end - overlap_start).total_seconds()
    return max(0.0, _seconds(start, end) - paused)


def _marker(
    event: Mapping[str, object],
    kind: str,
    identity: str,
    *,
    include_comment: bool = False,
) -> dict[str, object]:
    marker: dict[str, object] = {
        "type": "marker",
        "kind": kind,
        "identity": identity,
        "outcome": event["outcome"],
        "at": event["at"],
    }
    if include_comment and "comment" in event:
        marker["comment"] = event["comment"]
    return marker


def _lane_durations(timeline: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Total lane time, kept apart by how the lane ended.

    A dropped lane's span is the wall time from creation to the batch drop that cleared it, which
    is mostly time nobody was working on it. Summed together with collected lanes it inflates the
    figure a reader takes for "how long a lane takes"; kept apart, both numbers stay usable.
    """
    totals: dict[str, dict[str, float]] = {
        "collected": {"lanes": 0.0, "elapsed_seconds": 0.0, "recorded_seconds": 0.0},
        "dropped": {"lanes": 0.0, "elapsed_seconds": 0.0, "recorded_seconds": 0.0},
    }
    for entry in timeline:
        disposition = entry.get("disposition")
        if entry.get("kind") != "lane" or disposition not in totals:
            continue
        bucket = totals[str(disposition)]
        bucket["lanes"] += 1
        bucket["elapsed_seconds"] += float(entry.get("elapsed_seconds", 0.0))
        bucket["recorded_seconds"] += float(entry.get("recorded_seconds", 0.0))
    return totals


def compute_report(
    snapshot: Mapping[str, object],
    events: list[dict[str, object]],
    now: datetime,
) -> dict[str, Any]:
    """Pure finite calculator for the version-one lifecycle report."""
    counts = {
        "lifecycle_events": len(events),
        "lanes_created": 0,
        "lanes_collected": 0,
        "lanes_dropped": 0,
        "sync_attempts": 0,
        "sync_conflicts": 0,
        "collect_attempts": 0,
        "collect_conflicts": 0,
        "acceptance_passes": 0,
        "acceptance_failures": 0,
        "reconciliation_attempts": 0,
        "reconciliation_noops": 0,
        "reconciliation_clean": 0,
        "reconciliation_conflicts": 0,
        "landing_attempts": 0,
        "landing_successes": 0,
        "landing_stale": 0,
        "landing_nothing_to_land": 0,
        "invalid_telemetry_lines": int(snapshot.get("invalid_telemetry_lines", 0)),
    }
    pauses = _pause_intervals(events, now)
    timeline: list[dict[str, object]] = []
    lane_starts: dict[str, tuple[datetime, str]] = {}
    acceptance_starts: dict[str, tuple[datetime, str]] = {}
    task_start: tuple[datetime, str] | None = None
    task_end: tuple[datetime, str] | None = None

    for event in events:
        operation = str(event["operation"])
        outcome = str(event["outcome"])
        at = _time(event)
        at_text = str(event["at"])
        lane_id = event.get("lane_id")
        subject = event.get("subject_sha")
        persist = event.get("persist")
        if operation == "integration-create" and outcome == "success" and task_start is None:
            task_start = (at, at_text)
        elif operation == "integration-remove" and outcome == "success":
            task_end = (at, at_text)
        elif operation == "lane-create" and outcome == "success" and isinstance(lane_id, str):
            counts["lanes_created"] += 1
            lane_starts[lane_id] = (at, at_text)
            if isinstance(event.get("comment"), str):
                timeline.append(_marker(event, "comment", lane_id, include_comment=True))
        elif operation == "lane-drop" and outcome == "success" and isinstance(lane_id, str):
            counts["lanes_dropped"] += 1
            start = lane_starts.pop(lane_id, None)
            if start is not None:
                elapsed = _seconds(start[0], at)
                timeline.append({
                    "type": "span", "kind": "lane", "identity": lane_id,
                    "outcome": "success", "disposition": "dropped",
                    "started_at": start[1], "ended_at": at_text,
                    "elapsed_seconds": elapsed,
                    "recorded_seconds": _recorded_seconds(start[0], at, pauses),
                })
        elif operation == "lane-comment" and isinstance(lane_id, str):
            timeline.append(_marker(event, "comment", lane_id, include_comment=True))
        elif operation == "lane-sync":
            counts["sync_attempts"] += 1
            if outcome == "conflict":
                counts["sync_conflicts"] += 1
            if isinstance(lane_id, str):
                timeline.append(_marker(event, "sync", lane_id))
        elif operation == "integration-collect":
            counts["collect_attempts"] += 1
            if outcome == "conflict":
                counts["collect_conflicts"] += 1
            if isinstance(lane_id, str):
                timeline.append(_marker(event, "collect", lane_id))
                if outcome == "success":
                    counts["lanes_collected"] += 1
                    start = lane_starts.pop(lane_id, None)
                    if start is not None:
                        elapsed = _seconds(start[0], at)
                        timeline.append({
                            "type": "span", "kind": "lane", "identity": lane_id,
                            "outcome": "success", "disposition": "collected",
                            "started_at": start[1], "ended_at": at_text,
                            "elapsed_seconds": elapsed,
                            "recorded_seconds": _recorded_seconds(start[0], at, pauses),
                        })
        elif operation == "acceptance-start" and outcome in {"success", "superseded"} and isinstance(subject, str):
            acceptance_starts[subject] = (at, at_text)
        elif operation == "acceptance-result":
            if outcome == "pass":
                counts["acceptance_passes"] += 1
            elif outcome == "fail":
                counts["acceptance_failures"] += 1
            if outcome in {"pass", "fail"} and isinstance(subject, str):
                start = acceptance_starts.get(subject)
                if start is not None:
                    elapsed = _seconds(start[0], at)
                    entry = {
                        "type": "span", "kind": "acceptance", "identity": subject,
                        "outcome": "success" if outcome == "pass" else "fail",
                        "started_at": start[1], "ended_at": at_text,
                        "elapsed_seconds": elapsed,
                        "recorded_seconds": _recorded_seconds(start[0], at, pauses),
                    }
                    verifier = event.get("verifier")
                    if isinstance(verifier, str):
                        entry["verifier"] = verifier
                    timeline.append(entry)
        elif operation == "integration-reconcile":
            counts["reconciliation_attempts"] += 1
            if outcome == "noop":
                counts["reconciliation_noops"] += 1
            elif outcome == "success":
                counts["reconciliation_clean"] += 1
            elif outcome == "conflict":
                counts["reconciliation_conflicts"] += 1
            if isinstance(persist, str):
                timeline.append(_marker(event, "reconcile", persist))
        elif operation == "integration-land":
            counts["landing_attempts"] += 1
            if outcome == "success":
                counts["landing_successes"] += 1
            elif outcome == "stale":
                counts["landing_stale"] += 1
            elif outcome == "nothing_to_land":
                counts["landing_nothing_to_land"] += 1
            if isinstance(persist, str):
                timeline.append(_marker(event, "land", persist))

    for start, end, start_text, end_text in pauses:
        entry: dict[str, object] = {
            "type": "span", "kind": "pause", "identity": "pause",
            "started_at": start_text, "ended_at": end_text or now.isoformat(),
            "elapsed_seconds": _seconds(start, end), "recorded_seconds": 0.0,
        }
        if end_text is not None:
            entry["outcome"] = "success"
        timeline.append(entry)

    timing: dict[str, float] | None = None
    if task_start is not None:
        end = task_end or (now, now.isoformat())
        wall = _seconds(task_start[0], end[0])
        recorded = _recorded_seconds(task_start[0], end[0], pauses)
        timing = {
            "wall_seconds": wall,
            "paused_seconds": max(0.0, wall - recorded),
            "recorded_seconds": recorded,
        }
        timeline.append({
            "type": "span", "kind": "task", "identity": str(snapshot["task_id"]),
            "outcome": "success" if task_end is not None else "active",
            "started_at": task_start[1], "ended_at": end[1],
            "elapsed_seconds": wall, "recorded_seconds": recorded,
        })

    timeline.sort(
        key=lambda entry: (
            str(entry.get("at", entry.get("started_at"))),
            str(entry["type"]),
            str(entry["kind"]),
            str(entry["identity"]),
        )
    )
    rates: dict[str, float] = {}
    denominators = (
        ("lane_collection_rate", counts["lanes_collected"], counts["lanes_created"]),
        ("sync_conflict_rate", counts["sync_conflicts"], counts["sync_attempts"]),
        ("collect_conflict_rate", counts["collect_conflicts"], counts["collect_attempts"]),
        ("acceptance_pass_rate", counts["acceptance_passes"], counts["acceptance_passes"] + counts["acceptance_failures"]),
        ("reconciliation_conflict_rate", counts["reconciliation_conflicts"], counts["reconciliation_attempts"]),
        ("landing_success_rate", counts["landing_successes"], counts["landing_attempts"]),
    )
    for name, numerator, denominator in denominators:
        if denominator:
            rates[name] = numerator / denominator
    diff = dict(snapshot["integration_diff"])  # type: ignore[arg-type]
    if timing is not None:
        for suffix, seconds in (
            ("wall", timing["wall_seconds"]),
            ("recorded", timing["recorded_seconds"]),
        ):
            if seconds > 0:
                rates[f"events_per_{suffix}_hour"] = len(events) * 3600.0 / seconds
                rates[f"churn_per_{suffix}_hour"] = int(diff["churn"]) * 3600.0 / seconds

    report: dict[str, Any] = {
        "report_version": 1,
        "lane_durations": _lane_durations(timeline),
        "task_id": snapshot["task_id"],
        "generated_at": now.isoformat(),
        "warnings": list(snapshot.get("warnings", [])),
        "counts": counts,
        "rates": rates,
        "integration_diff": diff,
        "authorities": dict(snapshot.get("authorities", {})),
        "timeline": timeline,
    }
    if timing is not None:
        report["timing"] = timing
    return report


def lane_comments(task: TaskResources) -> dict[str, str | None]:
    """Return the latest annotation event for each lane id.

    Telemetry is the sole current annotation store. A successful lane create
    starts a fresh annotation lifetime, comment set/clear appends a replacement,
    and terminal lane events retire that lifetime. Status still filters this
    map through its live projected lane inventory.
    """
    try:
        raw = task.telemetry_path.read_bytes()
    except OSError:
        raw = b""
    events, _invalid = _decode_events(raw)
    comments: dict[str, str | None] = {}
    for event in events:
        operation = event["operation"]
        outcome = event["outcome"]
        lane_id = event.get("lane_id")
        if not isinstance(lane_id, str) or not lane_id:
            continue
        if operation == "lane-create" and outcome == "success":
            value = event.get("comment")
            comments[lane_id] = value if isinstance(value, str) else None
        elif operation == "lane-comment" and outcome == "success":
            value = event.get("comment")
            comments[lane_id] = value if isinstance(value, str) else None
        elif operation in {"lane-drop", "integration-collect"} and outcome == "success":
            comments.pop(lane_id, None)
    return comments


def timing_state(task: TaskResources) -> str:
    try:
        raw = task.telemetry_path.read_bytes()
    except OSError:
        raw = b""
    events, _invalid = _decode_events(raw)
    state = "recording"
    for event in events:
        if event["operation"] == "timing-pause" and event["outcome"] == "success":
            state = "paused"
        elif event["operation"] == "timing-resume" and event["outcome"] == "success":
            state = "recording"
    return state


def timing_transition(task: TaskResources, *, pause: bool) -> CommandResult:
    if task.ref(task.integration_base_ref) is None:
        raise OrchestrateError("task does not exist", "task_not_found")
    desired = "paused" if pause else "recording"
    operation = "timing-pause" if pause else "timing-resume"
    if timing_state(task) == desired:
        return CommandResult(True, {}, (f"timing is already {desired}",))
    require_event(task, operation, "success")
    return CommandResult(True, {})


def auto_resume(task: TaskResources) -> tuple[tuple[str, ...], bool]:
    if timing_state(task) != "paused":
        return (), False
    warnings = record_event(task, "timing-resume", "success", auto=True)
    return warnings, not warnings


def _integration_diff(task: TaskResources) -> dict[str, int]:
    base = task.ref(task.integration_base_ref)
    tip = task.ref(task.integration_branch)
    if base is None or tip is None:
        raise OrchestrateError("task integration is missing", "task_not_found")
    raw = run_git(
        task.repo.worktree_root,
        "diff",
        "--numstat",
        "--no-renames",
        base,
        tip,
    ).stdout
    files = binary = additions = deletions = 0
    for line in raw.splitlines():
        added, separator, remainder = line.partition("\t")
        deleted, separator2, path = remainder.partition("\t")
        if not separator or not separator2 or not path:
            continue
        files += 1
        if added == "-" or deleted == "-":
            binary += 1
        else:
            additions += int(added)
            deletions += int(deleted)
    return {
        "files": files,
        "binary_files": binary,
        "additions": additions,
        "deletions": deletions,
        "churn": additions + deletions,
    }


def _report_inputs(
    task: TaskResources,
    *,
    project_terminal_remove: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    raw, warnings = _read_raw(task)
    events, invalid = _decode_events(raw)
    if invalid:
        warnings.append(f"ignored {invalid} invalid telemetry line(s)")
    authorities = {
        key: value
        for key, value in (
            ("accepted", task.ref(task.accepted_ref)),
            ("user_accepted", task.ref(task.user_accepted_ref)),
            ("landed", task.ref(task.landed_ref)),
        )
        if value is not None
    }
    snapshot: dict[str, object] = {
        "task_id": task.task_id,
        "warnings": warnings,
        "invalid_telemetry_lines": invalid,
        "integration_diff": _integration_diff(task),
        "authorities": authorities,
    }
    now = datetime.now(UTC)
    if project_terminal_remove:
        events.append(
            {
                "event_version": 1,
                "at": now.isoformat(),
                "task_id": task.task_id,
                "operation": "integration-remove",
                "outcome": "success",
            }
        )
    return raw, compute_report(snapshot, events, now)


def write_report(
    task: TaskResources,
    output_dir: Path,
    *,
    project_terminal_remove: bool = False,
) -> CommandResult:
    raw, report = _report_inputs(
        task,
        project_terminal_remove=project_terminal_remove,
    )
    report_bytes = (
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode()
    report_path = output_dir / "orchestrate-report.json"
    raw_path = output_dir / "orchestrate-telemetry.jsonl"
    for target in (report_path, raw_path):
        if os.path.lexists(target) and (target.is_dir() or target.is_symlink()):
            raise OrchestrateError(
                "report artifact target is not a regular file",
                "report_write_failed",
            )
    temporary: list[Path] = []
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if not output_dir.is_dir():
            raise OSError("output path is not a directory")
        for target, data in ((report_path, report_bytes), (raw_path, raw)):
            descriptor, name = tempfile.mkstemp(
                prefix=f".{target.name}.", dir=output_dir
            )
            temp_path = Path(name)
            temporary.append(temp_path)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary[0], report_path)
        temporary.pop(0)
        os.replace(temporary[0], raw_path)
        temporary.pop(0)
    except OSError as exc:
        raise OrchestrateError(
            f"cannot write report artifacts: {exc}", "report_write_failed"
        ) from exc
    finally:
        for path in temporary:
            try:
                path.unlink()
            except OSError:
                pass
    return CommandResult(True, {})
