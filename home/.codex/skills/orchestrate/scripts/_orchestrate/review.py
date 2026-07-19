from __future__ import annotations

import argparse
import ast
import time
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError, require_identifier
from .git_ops import exact_commit, is_ancestor, managed_worktree_root, require_managed_worktree, run_git, worktree_evidence, worktree_records

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


def _review_blob(root: Path, sha: str, path: str) -> str | None:
    blob = run_git(root, "show", f"{sha}:{path}", check=False)
    return blob.stdout if blob.returncode == 0 else None


def command_review_audit(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    base = exact_commit(root, args.base, label="base")
    subject = exact_commit(root, args.subject, label="subject")
    if not is_ancestor(root, base, subject):
        raise OrchestrateError("base must be an ancestor of subject")
    changed = [
        path.strip()
        for path in run_git(root, "diff", "--name-only", base, subject).stdout.splitlines()
        if path.strip() and _review_test_path(path.strip())
    ]
    signals: list[dict[str, Any]] = []
    for path in changed:
        old_source = _review_blob(root, base, path)
        new_source = _review_blob(root, subject, path)
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
        "changed_paths": changed,
        "signals": signals,
        "signal_count": len(signals),
        "manual_review_required": bool(signals),
    }


def command_review_checkout(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    target_sha = exact_commit(root, args.sha, label="review SHA")
    label = (
        require_identifier(args.label, label="label") if args.label else target_sha[:12]
    )
    target = require_managed_worktree(
        root,
        (
            Path(args.worktree).resolve()
            if args.worktree
            else managed_worktree_root(root) / f"review-{label}"
        ),
        kind="review",
    )
    if not target.name.startswith("review-"):
        raise OrchestrateError("review worktree name must start with 'review-'")
    recovered = None
    if target.exists():
        # A prior run completed; rerunning after an abort reports instead of failing.
        record = next(
            (
                record
                for record in worktree_records(root)
                if record.get("worktree") == str(target)
            ),
            None,
        )
        if record is None:
            raise OrchestrateError(
                f"review worktree path already exists but is not a registered"
                f" worktree: {target}"
            )
        recovered = "already-created"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        run_git(root, "worktree", "add", "--detach", str(target), target_sha)
    evidence = worktree_evidence(target, started=started)
    if evidence["branch"] is not None or evidence["head"] != target_sha:
        raise OrchestrateError("review checkout is not detached at the requested SHA")
    result = {
        "ok": True,
        "operation": "review-checkout",
        "subject_sha": target_sha,
        **evidence,
    }
    if recovered:
        result["recovered"] = recovered
    return result


def command_review_advance(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    from_sha = exact_commit(root, args.from_sha, label="--from SHA")
    to_sha = exact_commit(root, args.to_sha, label="--to SHA")
    target = require_managed_worktree(
        root, Path(args.worktree).resolve(), kind="review"
    )
    if not target.name.startswith("review-"):
        raise OrchestrateError("review worktree name must start with 'review-'")
    if not any(
        record.get("worktree") == str(target) for record in worktree_records(root)
    ):
        raise OrchestrateError(f"not a registered worktree: {target}")
    evidence = worktree_evidence(target, started=started)
    if evidence["branch"] is not None:
        raise OrchestrateError("review worktree is not detached")
    if not evidence["clean"]:
        raise OrchestrateError("review worktree is dirty; evidence would be void")
    if evidence["head"] == to_sha:
        # A prior run completed; rerunning after an abort reports instead of failing.
        return {
            "ok": True,
            "operation": "review-advance",
            "recovered": "already-advanced",
            "subject_sha": to_sha,
            "previous_subject_sha": from_sha,
            **evidence,
        }
    if evidence["head"] != from_sha:
        raise OrchestrateError(
            f"review worktree HEAD is {evidence['head']}, not the declared --from;"
            " the subject history would break"
        )
    run_git(target, "checkout", "--detach", to_sha)
    evidence = worktree_evidence(target, started=started)
    if evidence["head"] != to_sha or not evidence["clean"]:
        raise OrchestrateError("review advance did not reach a clean detached --to")
    return {
        "ok": True,
        "operation": "review-advance",
        "subject_sha": to_sha,
        "previous_subject_sha": from_sha,
        **evidence,
    }
