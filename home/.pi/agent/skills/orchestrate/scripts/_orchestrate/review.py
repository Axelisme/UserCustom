from __future__ import annotations

import argparse
import ast
import fcntl
import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .primitives import OrchestrateError, require_identifier
from .git_ops import common_repo_root, exact_commit, is_ancestor, managed_worktree_root, require_managed_worktree, run_git, worktree_evidence, worktree_records
from .findings import normalize_finding_receipt

def _review_test_path(path: str) -> bool:
    candidate = Path(path)
    name = candidate.name
    return (
        candidate.suffix == ".py"
        and (
            candidate.parts[:1] == ("tests",)
            or name.startswith("test_")
            or name.endswith("_test.py")
        )
    )


def _review_test_metrics(tree: ast.AST) -> dict[str, Any]:
    test_names: set[str] = set()
    test_returns = 0
    skip_calls = 0
    xfail_calls = 0
    parameter_cases = 0
    assertions = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            assertions += 1
        if isinstance(node, ast.Call):
            function = node.func
            name = function.attr if isinstance(function, ast.Attribute) else (
                function.id if isinstance(function, ast.Name) else ""
            )
            if name == "skip" or name.endswith(".skip"):
                skip_calls += 1
            if name == "xfail" or name.endswith(".xfail"):
                xfail_calls += 1
            if name == "parametrize" and len(node.args) >= 2:
                cases = node.args[1]
                if isinstance(cases, (ast.List, ast.Tuple)):
                    parameter_cases += len(cases.elts)
            if isinstance(function, ast.Attribute) and function.attr.startswith("assert"):
                assertions += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("test"):
                test_names.add(node.name)
                test_returns += sum(
                    1 for child in ast.walk(node) if isinstance(child, ast.Return)
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                function = decorator.func
                if (
                    isinstance(function, ast.Attribute)
                    and function.attr == "parametrize"
                    and len(decorator.args) >= 2
                    and isinstance(decorator.args[1], (ast.List, ast.Tuple))
                ):
                    parameter_cases += len(decorator.args[1].elts)
    return {
        "test_names": test_names,
        "test_returns": test_returns,
        "skip_calls": skip_calls,
        "xfail_calls": xfail_calls,
        "parameter_cases": parameter_cases,
        "assertions": assertions,
    }


def _review_blob(root: Path, sha: str, path: str | None) -> str | None:
    if path is None:
        return None
    blob = run_git(root, "show", f"{sha}:{path}", check=False)
    return blob.stdout if blob.returncode == 0 else None


def _review_test_changes(
    root: Path, base: str, subject: str
) -> list[dict[str, str | None]]:
    output = run_git(root, "diff", "--name-status", "-M", base, subject).stdout
    changes: list[dict[str, str | None]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            old_path, new_path = parts[1], parts[2]
        elif status == "A":
            old_path, new_path = None, parts[1]
        elif status == "D":
            old_path, new_path = parts[1], None
        else:
            old_path = new_path = parts[1]
        if not any(
            path is not None and _review_test_path(path)
            for path in (old_path, new_path)
        ):
            continue
        changes.append(
            {"status": status, "old_path": old_path, "new_path": new_path}
        )
    return changes


def command_review_audit(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    base = exact_commit(root, args.base, label="base")
    subject = exact_commit(root, args.subject, label="subject")
    if not is_ancestor(root, base, subject):
        raise OrchestrateError("base must be an ancestor of subject")
    changes = _review_test_changes(root, base, subject)
    signals: list[dict[str, Any]] = []
    for change in changes:
        old_path = change["old_path"]
        new_path = change["new_path"]
        path = str(new_path or old_path)
        old_source = _review_blob(root, base, old_path)
        new_source = _review_blob(root, subject, new_path)
        old_tree: ast.AST | None = None
        new_tree: ast.AST | None = None
        parse_failed = False
        for label, source in (("base", old_source), ("subject", new_source)):
            if source is None:
                continue
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError as exc:
                signals.append(
                    {
                        "path": path,
                        "kind": "unparseable-test-source",
                        "detail": f"{label}: {exc.msg}",
                    }
                )
                parse_failed = True
                continue
            if label == "base":
                old_tree = tree
            else:
                new_tree = tree
        if parse_failed:
            continue
        old = _review_test_metrics(old_tree) if old_tree is not None else {
            "test_names": set(), "test_returns": 0, "skip_calls": 0,
            "xfail_calls": 0, "parameter_cases": 0, "assertions": 0,
        }
        new = _review_test_metrics(new_tree) if new_tree is not None else {
            "test_names": set(), "test_returns": 0, "skip_calls": 0,
            "xfail_calls": 0, "parameter_cases": 0, "assertions": 0,
        }
        for test_name in sorted(old["test_names"] - new["test_names"]):
            signals.append(
                {"path": path, "kind": "deleted-test", "detail": test_name}
            )
        if new["test_returns"] > old["test_returns"]:
            signals.append(
                {
                    "path": path,
                    "kind": "added-early-return",
                    "detail": f"{old['test_returns']} -> {new['test_returns']}",
                }
            )
        if new["skip_calls"] > old["skip_calls"]:
            signals.append(
                {
                    "path": path,
                    "kind": "added-skip",
                    "detail": f"{old['skip_calls']} -> {new['skip_calls']}",
                }
            )
        if new["xfail_calls"] > old["xfail_calls"]:
            signals.append(
                {
                    "path": path,
                    "kind": "added-xfail",
                    "detail": f"{old['xfail_calls']} -> {new['xfail_calls']}",
                }
            )
        if new["parameter_cases"] < old["parameter_cases"]:
            signals.append(
                {
                    "path": path,
                    "kind": "removed-parameter-cases",
                    "detail": f"{old['parameter_cases']} -> {new['parameter_cases']}",
                }
            )
        if new["assertions"] < old["assertions"]:
            signals.append(
                {
                    "path": path,
                    "kind": "assertion-count-decrease",
                    "detail": f"{old['assertions']} -> {new['assertions']}",
                }
            )
    return {
        "ok": True,
        "operation": "review-audit",
        "read_only": True,
        "base_sha": base,
        "subject_sha": subject,
        "changed_paths": [str(change["new_path"] or change["old_path"]) for change in changes],
        "changes": changes,
        "signals": signals,
        "signal_count": len(signals),
        "manual_review_required": bool(signals),
    }


def review_jobs_path(root: Path, task_id: str) -> Path:
    """Durable root-owned identity ledger for immutable review jobs.

    The file is intentionally an append-only publication record, not runtime state:
    pipeline/fleet facts are supplied by the operator at cleanup time and Git remains
    the authority for checkout identity.
    """
    return (
        common_repo_root(root)
        / ".agent_state"
        / "orchestrate"
        / "reviews"
        / f"{require_identifier(task_id, label='task-id')}.jsonl"
    )


@contextmanager
def _review_lifecycle_lock(root: Path) -> Iterator[None]:
    lock_path = common_repo_root(root) / ".git" / "orchestrate-review.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def _read_review_jobs(root: Path, task_id: str) -> list[dict[str, Any]]:
    path = review_jobs_path(root, task_id)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OrchestrateError("review job ledger is malformed") from exc
            if not isinstance(row, dict):
                raise OrchestrateError("review job ledger contains a non-object row")
            rows.append(row)
    return rows


def _latest_review_jobs(root: Path) -> list[dict[str, Any]]:
    """Reduce every task ledger to the latest row for each job identity."""
    directory = common_repo_root(root) / ".agent_state" / "orchestrate" / "reviews"
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    if not directory.exists():
        return []
    for path in sorted(directory.glob("*.jsonl")):
        task_id = path.stem
        for row in _read_review_jobs(root, task_id):
            job_id = row.get("job_id")
            if not isinstance(job_id, str):
                raise OrchestrateError("review job ledger row is missing job-id")
            latest[(task_id, job_id)] = row
    return list(latest.values())


def _latest_task_job(root: Path, task_id: str, job_id: str) -> dict[str, Any] | None:
    return next((row for row in _latest_review_jobs(root)
                 if row.get("task_id") == task_id and row.get("job_id") == job_id), None)


def _append_review_job(root: Path, task_id: str, record: dict[str, Any]) -> None:
    path = review_jobs_path(root, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def open_review_job_for_worktree(root: Path, target: Path) -> dict[str, Any] | None:
    """Return the authoritative open immutable job owning ``target``, if any."""
    target_path = str(target.resolve())
    return next(
        (
            row for row in _latest_review_jobs(root)
            if row.get("state") != "cleaned" and row.get("worktree") == target_path
        ),
        None,
    )


def _review_job_identity(args: argparse.Namespace, target_sha: str) -> tuple[str, str]:
    del target_sha  # identity is explicit; the subject is never used as a slot name
    task = require_identifier(str(getattr(args, "task_id", "")), label="task-id")
    job = require_identifier(str(getattr(args, "job_id", "")), label="job-id")
    return task, job


def _compensate_created_review_worktree(root: Path, target: Path) -> dict[str, Any]:
    try:
        removal = run_git(root, "worktree", "remove", "--force", str(target), check=False)
        remove_ok = removal.returncode == 0
        remove_error = removal.stderr.strip()
    except OSError as exc:
        remove_ok = False
        remove_error = str(exc)
    try:
        prune = run_git(root, "worktree", "prune", check=False)
        prune_ok = prune.returncode == 0
        prune_error = prune.stderr.strip()
    except OSError as exc:
        prune_ok = False
        prune_error = str(exc)
    return {"remove_ok": remove_ok, "remove_error": remove_error,
            "prune_ok": prune_ok, "prune_error": prune_error}


def command_review_checkout(args: argparse.Namespace) -> dict[str, Any]:
    """Create one clean detached checkout for one immutable review job.

    A job is never retargeted. Repeating the exact identity is an idempotent
    recovery; a subject or path mismatch fails closed and requires a new job.
    """
    started = time.monotonic()
    root = Path(args.root).resolve()
    target_sha = exact_commit(root, args.sha, label="review SHA")
    task_id, job_id = _review_job_identity(args, target_sha)
    label = require_identifier(job_id, label="job-id")
    target = require_managed_worktree(
        root,
        Path(args.worktree).resolve()
        if getattr(args, "worktree", None)
        else managed_worktree_root(root) / f"review-{task_id}-{label}",
        kind="review",
    )
    if not target.name.startswith("review-"):
        raise OrchestrateError("review worktree name must start with 'review-'")
    with _review_lifecycle_lock(root):
        prior = _latest_task_job(root, task_id, job_id)
        if prior is not None:
            if prior.get("state") == "cleaned":
                raise OrchestrateError("retired review job cannot be resurrected; use a new job-id")
            if prior.get("subject_sha") != target_sha or prior.get("worktree") != str(target):
                raise OrchestrateError("review job identity is immutable; use a new job-id")
        same_path = next((row for row in _latest_review_jobs(root)
                          if row.get("worktree") == str(target)
                          and not (row.get("task_id") == task_id and row.get("job_id") == job_id)), None)
        if same_path is not None:
            raise OrchestrateError("review worktree is already owned by another task/job")
        recovered = None
        created = False
        if target.exists():
            record = next((record for record in worktree_records(root)
                           if record.get("worktree") == str(target)), None)
            if record is None:
                raise OrchestrateError(f"review worktree path already exists but is not a registered worktree: {target}")
            # A prior publication/compensation double fault leaves a clean exact
            # checkout with no ledger row. Under the lifecycle lock, explicit
            # task/job/path identity may safely adopt that orphan.
            recovered = "adopted-orphan" if prior is None else "already-created"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            run_git(root, "worktree", "add", "--detach", str(target), target_sha)
            created = True
        try:
            evidence = worktree_evidence(target, started=started)
            if evidence["branch"] is not None or evidence["head"] != target_sha:
                raise OrchestrateError("review checkout is not detached at the requested SHA")
            if not evidence["clean"]:
                raise OrchestrateError("review worktree is dirty; evidence would be void")
            if prior is None:
                _append_review_job(root, task_id, {
                    "task_id": task_id, "job_id": job_id, "subject_sha": target_sha,
                    "worktree": str(target), "state": "open",
                    "created_at": datetime.now(UTC).isoformat(),
                })
        except Exception as publication_error:
            if created and target.exists():
                compensation = _compensate_created_review_worktree(root, target)
                if not compensation["remove_ok"] or not compensation["prune_ok"]:
                    return {
                        "ok": False, "operation": "review-job-create",
                        "reconcile_required": True, "publication": "incomplete",
                        "task_id": task_id, "job_id": job_id,
                        "subject_sha": target_sha, "worktree": str(target),
                        "compensation": compensation,
                        "error": str(publication_error),
                    }
            raise
    result = {
        "ok": True, "operation": "review-job-create", "task_id": task_id,
        "job_id": job_id, "subject_sha": target_sha, "immutable": True,
        "worktree": str(target), **evidence,
    }
    if recovered:
        result["recovered"] = recovered
    return result


def _receipt_subject(root: Path, receipt: str, expected: str, worktree: Path) -> dict[str, Any]:
    if not receipt or receipt == "-":
        raise OrchestrateError("review cleanup requires an external canonical receipt path")
    receipt_path = Path(receipt).resolve()
    try:
        receipt_path.relative_to(worktree.resolve())
    except ValueError:
        pass
    else:
        raise OrchestrateError("canonical receipt must be retained outside the removed worktree")
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OrchestrateError(f"cannot harvest review receipt: {exc}") from exc
    if not isinstance(payload, dict):
        raise OrchestrateError("review receipt must be a JSON object")
    try:
        subject, canonical, _ = normalize_finding_receipt(root, payload)
    except OrchestrateError as exc:
        raise OrchestrateError(f"invalid canonical review receipt: {exc}") from exc
    if subject != expected:
        raise OrchestrateError("review receipt subject does not match immutable job")
    return {"payload": canonical, "path": str(receipt_path)}


def _fact_paths(value: Any, *, label: str) -> set[str]:
    if isinstance(value, str):
        return {str(Path(value).resolve())}
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result |= _fact_paths(item, label=label)
        return result
    if isinstance(value, dict):
        paths = set()
        for key in ("worktree", "cwd", "path"):
            if key in value:
                paths |= _fact_paths(value[key], label=label)
        if not paths:
            raise OrchestrateError(f"pipeline facts {label} entry has no public worktree path")
        return paths
    raise OrchestrateError(f"pipeline facts {label} must contain paths")


PUBLIC_FACTS_SCHEMA_VERSION = 1
PUBLIC_FACTS_SOURCE = "pi-subagents.pipeline.status"
PUBLIC_FACTS_MAX_AGE_SECONDS = 30


def _public_pipeline_facts(root: Path, path: str, owner_session: str) -> tuple[set[str], dict[str, str]]:
    try:
        facts = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OrchestrateError(f"cannot read public pipeline facts: {exc}") from exc
    if not isinstance(facts, dict) or facts.get("schema_version") != PUBLIC_FACTS_SCHEMA_VERSION:
        raise OrchestrateError("unsupported public pipeline facts schema")
    if facts.get("source") != PUBLIC_FACTS_SOURCE:
        raise OrchestrateError("public pipeline facts source is not the runtime projection")
    expected_root = str(root.resolve())
    if facts.get("repo_root") != expected_root:
        raise OrchestrateError("public pipeline facts repo_root does not match")
    if facts.get("owner_session") != owner_session or not isinstance(owner_session, str) or not owner_session.strip():
        raise OrchestrateError("public pipeline facts owner_session does not match")
    revision = facts.get("snapshot_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise OrchestrateError("public pipeline facts require a positive snapshot_revision")
    observed = facts.get("observed_at")
    if not isinstance(observed, str):
        raise OrchestrateError("public pipeline facts require observed_at")
    try:
        observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrchestrateError("public pipeline facts observed_at is invalid") from exc
    if observed_at.tzinfo is None or abs((datetime.now(UTC) - observed_at).total_seconds()) > PUBLIC_FACTS_MAX_AGE_SECONDS:
        raise OrchestrateError("public pipeline facts are stale or lack timezone")
    revision_path = common_repo_root(root) / ".agent_state" / "orchestrate" / "review-facts-revision.json"
    previous_revision = 0
    if revision_path.exists():
        try:
            previous = json.loads(revision_path.read_text(encoding="utf-8"))
            previous_revision = int(previous.get("snapshot_revision", 0))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise OrchestrateError("stored public pipeline revision is malformed") from exc
    if revision < previous_revision:
        raise OrchestrateError("public pipeline facts snapshot_revision regressed")
    pipelines = facts.get("pipelines")
    if not isinstance(pipelines, list):
        raise OrchestrateError("public pipeline facts require complete pipelines")
    refs: set[str] = set()
    for pipeline in pipelines:
        if not isinstance(pipeline, dict) or not isinstance(pipeline.get("name"), str) or pipeline.get("state") not in {"active", "held", "blocked", "idle"} or not isinstance(pipeline.get("active"), bool) or "current" not in pipeline or not isinstance(pipeline.get("pending"), list):
            raise OrchestrateError("public pipeline facts contain an incomplete pipeline status")
        current = pipeline["current"]
        if current is not None:
            refs |= _fact_paths(current, label="current")
        refs |= _fact_paths(pipeline["pending"], label="pending") if pipeline["pending"] else set()
    receipts = facts.get("receipts")
    if receipts is None:
        receipts = {}
    if not isinstance(receipts, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in receipts.items()):
        raise OrchestrateError("public pipeline facts receipts must map job ids to paths")
    revision_path.parent.mkdir(parents=True, exist_ok=True)
    revision_path.write_text(json.dumps({"snapshot_revision": revision}, sort_keys=True) + "\n", encoding="utf-8")
    return refs, receipts


def command_review_cleanup(args: argparse.Namespace) -> dict[str, Any]:
    """Harvest a canonical receipt and complete public liveness check before removal."""
    started = time.monotonic(); root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id"); job_id = require_identifier(args.job_id, label="job-id")
    with _review_lifecycle_lock(root):
        job = _latest_task_job(root, task_id, job_id)
        if job is None or job.get("state") == "cleaned":
            raise OrchestrateError("unknown or retired review job; cleanup cannot guess its identity")
        if not isinstance(job.get("worktree"), str) or not isinstance(job.get("subject_sha"), str):
            raise OrchestrateError("review job ledger row is missing immutable identity")
        target = require_managed_worktree(root, Path(job["worktree"]).resolve(), kind="review")
        refs, _ = _public_pipeline_facts(root, args.pipeline_facts, args.owner_session)
        if str(target) in refs:
            raise OrchestrateError("review cleanup refused: worktree is referenced by active/current/pending facts")
        harvested = _receipt_subject(root, args.receipt, str(job["subject_sha"]), target)
        if target.exists():
            if run_git(target, "status", "--porcelain").stdout.strip():
                raise OrchestrateError("review worktree is dirty; receipt cannot authorize cleanup")
            evidence = worktree_evidence(target, started=started)
            if evidence["branch"] is not None or evidence["head"] != job["subject_sha"]:
                raise OrchestrateError("review job worktree drifted; cleanup refused")
            run_git(root, "worktree", "remove", str(target))
        else:
            run_git(root, "worktree", "prune")
        _append_review_job(root, task_id, {**job, "state": "cleaned", "receipt": harvested["path"], "cleaned_at": datetime.now(UTC).isoformat()})
    return {"ok": True, "operation": "review-job-cleanup", "task_id": task_id, "job_id": job_id, "subject_sha": job["subject_sha"], "worktree": str(target), "receipt_harvested": True, "receipt_path": harvested["path"], "observed_at": datetime.now(UTC).isoformat(), "duration_ms": round((time.monotonic() - started) * 1000)}


def command_review_cleanup_all(args: argparse.Namespace) -> dict[str, Any]:
    """Sweep only this task's unreferenced jobs after complete public facts and receipt validation."""
    root = Path(args.root).resolve(); task_id = require_identifier(args.task_id, label="task-id")
    with _review_lifecycle_lock(root):
        refs, receipts = _public_pipeline_facts(root, args.pipeline_facts, args.owner_session)
        jobs = [job for job in _latest_review_jobs(root) if job.get("task_id") == task_id and job.get("state") != "cleaned"]
        entries: list[dict[str, Any]] = []; plan: list[tuple[dict[str, Any], Path, dict[str, Any], dict[str, Any]]] = []
        for job in jobs:
            if not isinstance(job.get("job_id"), str) or not isinstance(job.get("worktree"), str) or not isinstance(job.get("subject_sha"), str):
                raise OrchestrateError("review job ledger row is missing immutable identity")
            target = require_managed_worktree(root, Path(job["worktree"]).resolve(), kind="review"); path = str(target)
            entry = {"job_id": job["job_id"], "worktree": path}
            receipt = receipts.get(job["job_id"])
            if path in refs:
                entry.update(action="refused", reason="referenced by active/current/pending pipeline facts"); entries.append(entry); continue
            if not isinstance(receipt, str):
                entry.update(action="refused", reason="canonical receipt missing from public facts"); entries.append(entry); continue
            harvested = _receipt_subject(root, receipt, job["subject_sha"], target)
            if target.exists() and run_git(target, "status", "--porcelain").stdout.strip():
                entry.update(action="refused", reason="review worktree is dirty"); entries.append(entry); continue
            entry["action"] = "planned"; entries.append(entry); plan.append((job, target, entry, harvested))
        refused = [entry for entry in entries if entry["action"] == "refused"]
        if refused:
            raise OrchestrateError("cleanup-all refused referenced, dirty, or unauthorised review worktrees: " + json.dumps(refused, sort_keys=True))
        for job, target, entry, harvested in plan:
            if target.exists(): run_git(root, "worktree", "remove", str(target))
            else: run_git(root, "worktree", "prune")
            _append_review_job(root, task_id, {**job, "state": "cleaned", "receipt": harvested["path"], "cleaned_at": datetime.now(UTC).isoformat()}); entry["action"] = "removed"
    return {"ok": True, "operation": "review-job-cleanup-all", "task_id": task_id, "entries": entries, "removed": sum(e["action"] == "removed" for e in entries)}
