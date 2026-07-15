#!/usr/bin/env python3
"""Inspect orchestrate releases and apply explicit stateless Git safety guards."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

MANIFEST_SCHEMA = 1
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EXACT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
COMPAT_PATTERN = re.compile(r"^orchestrate_compat:\s*(\d+)\s*$", re.MULTILINE)
VERSION_PATTERN = re.compile(r"^skill_version:\s*(\d+)\s*$", re.MULTILINE)
PHASE_ROW_PATTERN = re.compile(
    r"^\|\s*(?P<phase>[^|]+?)\s*\|\s*"
    r"(?P<status>pending|in_progress|blocked|completed)\s*\|"
)


class OrchestrateError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_sha256(text: str) -> str:
    return sha256_bytes(" ".join(text.split()).encode())


def run_git(
    root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise OrchestrateError(f"git {' '.join(args)} failed: {detail}")
    return completed


def exact_commit(root: Path, value: str, *, label: str) -> str:
    if not EXACT_SHA_PATTERN.fullmatch(value):
        raise OrchestrateError(f"{label} must be an exact hexadecimal commit SHA")
    resolved = run_git(
        root, "rev-parse", "--verify", f"{value}^{{commit}}"
    ).stdout.strip()
    if not resolved.lower().startswith(value.lower()):
        raise OrchestrateError(f"{label} does not identify one exact commit: {value}")
    return resolved


def require_identifier(value: str, *, label: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise OrchestrateError(f"{label} must match {ID_PATTERN.pattern}: {value!r}")
    return value


def skill_version(skill_dir: Path) -> int:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(text)
    if match is None:
        raise OrchestrateError("SKILL.md has no skill_version")
    return int(match.group(1))


def source_home(skill_dir: Path) -> Path:
    try:
        return skill_dir.resolve().parents[2]
    except IndexError as exc:
        raise OrchestrateError(f"cannot locate home root from {skill_dir}") from exc


def markdown_sections(text: str) -> dict[str, str]:
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
        except ValueError:
            end = -1
        if end >= 0:
            start = end + 1
    headings: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines[start:], start=start):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if not in_fence and re.match(r"^#{1,6}\s+\S", line):
            headings.append((index, line.lstrip("#").strip()))
    if not headings:
        return {"__file__": normalized_sha256("\n".join(lines[start:]))}
    sections: dict[str, str] = {}
    for position, (index, heading) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        key = heading
        suffix = 2
        while key in sections:
            key = f"{heading} [{suffix}]"
            suffix += 1
        sections[key] = normalized_sha256("\n".join(lines[index:end]))
    return sections


def profile_standing_orders(text: str, suffix: str) -> str:
    if suffix == ".toml":
        match = re.search(
            r"developer_instructions\s*=\s*'''\s*(.*?)\s*'''",
            text,
            flags=re.DOTALL,
        )
        return match.group(1) if match else text
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            return "\n".join(lines[lines.index("---", 1) + 1 :])
        except ValueError:
            pass
    return text


def document_paths(skill_dir: Path) -> list[Path]:
    paths = [
        skill_dir / "SKILL.md",
        skill_dir / "runtime-codex.md",
        skill_dir / "runtime-claude.md",
    ]
    paths.extend(sorted((skill_dir / "references").glob("*.md")))
    paths.extend(sorted((skill_dir / "scripts").glob("*.py")))
    return [path for path in paths if path.is_file()]


def profile_paths(home: Path) -> list[Path]:
    names = ("contract-planner", "implementer", "reviewer")
    return [
        *[home / ".codex" / "agents" / f"{name}.toml" for name in names],
        *[home / ".claude" / "agents" / f"{name}.md" for name in names],
    ]


def build_manifest(skill_dir: Path, version: int) -> dict[str, Any]:
    home = source_home(skill_dir)
    documents: dict[str, Any] = {}
    for path in document_paths(skill_dir):
        data = path.read_bytes()
        relative = path.relative_to(skill_dir).as_posix()
        entry: dict[str, Any] = {
            "bytes": len(data),
            "sha256": sha256_bytes(data),
            "sections": markdown_sections(data.decode("utf-8"))
            if path.suffix == ".md"
            else {"__file__": sha256_bytes(data)},
        }
        match = COMPAT_PATTERN.search(data.decode("utf-8"))
        if match:
            entry["orchestrate_compat"] = int(match.group(1))
        documents[relative] = entry
    profiles: dict[str, Any] = {}
    for path in profile_paths(home):
        if not path.is_file():
            continue
        data = path.read_bytes()
        text = data.decode("utf-8")
        profiles[path.relative_to(home).as_posix()] = {
            "bytes": len(data),
            "sha256": sha256_bytes(data),
            "standing_orders_sha256": normalized_sha256(
                profile_standing_orders(text, path.suffix)
            ),
        }
    return {
        "schema_version": MANIFEST_SCHEMA,
        "skill_version": version,
        "orchestrate_compat": version,
        "documents": documents,
        "profiles": profiles,
    }


def manifest_path(skill_dir: Path, version: int) -> Path:
    return skill_dir / "manifests" / f"{version}.json"


def load_manifest(skill_dir: Path, version: int) -> dict[str, Any]:
    path = manifest_path(skill_dir, version)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OrchestrateError(f"release manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OrchestrateError(f"invalid release manifest {path}: {exc}") from exc
    if payload.get("schema_version") != MANIFEST_SCHEMA:
        raise OrchestrateError(f"unsupported manifest schema: {path}")
    if payload.get("skill_version") != version:
        raise OrchestrateError(f"manifest version mismatch: {path}")
    return payload


def command_release_manifest(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    payload = build_manifest(skill_dir, args.version)
    if args.previous_version is not None:
        previous = load_manifest(skill_dir, args.previous_version)
        comparison = compare_manifests(previous, payload)
        payload["release_delta"] = {
            "from_version": args.previous_version,
            "changed_sections": {
                item["path"]: item["changed_sections"]
                for item in comparison["changed_documents"]
            },
            "changed_profiles": comparison["changed_profiles"],
            "must_reread": comparison["must_reread"],
        }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"ok": True, "output": str(output), "skill_version": args.version}


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    version = skill_version(skill_dir)
    manifest = load_manifest(skill_dir, version)
    observed = build_manifest(skill_dir, version)
    errors: list[str] = []
    for category in ("documents", "profiles"):
        expected_items = manifest[category]
        observed_items = observed[category]
        for name in sorted(set(expected_items) | set(observed_items)):
            if name not in expected_items:
                errors.append(f"unexpected {category[:-1]}: {name}")
            elif name not in observed_items:
                errors.append(f"missing {category[:-1]}: {name}")
            elif expected_items[name]["sha256"] != observed_items[name]["sha256"]:
                errors.append(f"hash mismatch: {name}")
    for name, entry in observed["documents"].items():
        if name.endswith(".md") and entry["bytes"] > 16_384:
            errors.append(
                f"single-read budget exceeded: {name} ({entry['bytes']} bytes)"
            )
        compat = entry.get("orchestrate_compat")
        if compat is not None and compat != version:
            errors.append(f"compat mismatch: {name}={compat}, expected {version}")
    if manifest.get("orchestrate_compat") != version:
        errors.append("manifest orchestrate_compat does not match SKILL.md")
    return {
        "ok": not errors,
        "skill_dir": str(skill_dir),
        "skill_version": version,
        "orchestrate_compat": manifest.get("orchestrate_compat"),
        "documents": len(observed["documents"]),
        "profiles": len(observed["profiles"]),
        "errors": errors,
    }


def compare_manifests(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    must_reread: list[str] = []
    old_docs = old["documents"]
    new_docs = new["documents"]
    for name in sorted(set(old_docs) | set(new_docs)):
        before = old_docs.get(name)
        after = new_docs.get(name)
        if before == after:
            continue
        before_sections = before.get("sections", {}) if before else {}
        after_sections = after.get("sections", {}) if after else {}
        changed_sections = [
            section
            for section in sorted(set(before_sections) | set(after_sections))
            if before_sections.get(section) != after_sections.get(section)
        ]
        semantic = bool(changed_sections)
        if semantic and name.endswith(".md"):
            must_reread.append(name)
        documents.append(
            {
                "path": name,
                "change": "added"
                if before is None
                else "removed"
                if after is None
                else "modified",
                "changed_sections": changed_sections,
                "must_reread": semantic and name.endswith(".md"),
            }
        )
    changed_profiles = [
        name
        for name in sorted(set(old["profiles"]) | set(new["profiles"]))
        if old["profiles"].get(name) != new["profiles"].get(name)
    ]
    return {
        "from": old["skill_version"],
        "to": new["skill_version"],
        "compat": [old["orchestrate_compat"], new["orchestrate_compat"]],
        "changed_documents": documents,
        "changed_profiles": changed_profiles,
        "must_reread": must_reread,
    }


def command_diff(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    old = load_manifest(skill_dir, args.old_version)
    new = load_manifest(skill_dir, args.new_version)
    return {"ok": True, **compare_manifests(old, new)}


def command_identity(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    profile = Path(args.profile).resolve()
    try:
        data = profile.read_bytes()
    except OSError as exc:
        raise OrchestrateError(f"cannot read profile {profile}: {exc}") from exc
    text = data.decode("utf-8")
    same_identity: bool | None = None
    if args.writer_agent_id is not None:
        same_identity = args.agent_id == args.writer_agent_id
    profile_manifest_version: int | None = None
    try:
        relative_profile = profile.relative_to(source_home(skill_dir)).as_posix()
        current_version = skill_version(skill_dir)
        expected_profile = load_manifest(skill_dir, current_version)["profiles"].get(
            relative_profile
        )
        if expected_profile and expected_profile["sha256"] == sha256_bytes(data):
            profile_manifest_version = current_version
    except ValueError:
        pass
    different_identity = None if same_identity is None else not same_identity
    requirement_checks: dict[str, bool] = {}
    if args.require_different_identity:
        requirement_checks["different_identity"] = different_identity is True
    return {
        "ok": True,
        "requested_identity": args.requested,
        "effective_identity": args.effective,
        "agent_id": args.agent_id,
        "profile": str(profile),
        "profile_sha256": sha256_bytes(data),
        "profile_manifest_version": profile_manifest_version,
        "standing_orders_sha256": normalized_sha256(
            profile_standing_orders(text, profile.suffix)
        ),
        "writer_agent_id": args.writer_agent_id,
        "different_identity": different_identity,
        "park_capability": args.park_capability,
        "requirement_checks": requirement_checks,
        "requirements_satisfied": (
            all(requirement_checks.values()) if requirement_checks else None
        ),
    }


def common_repo_root(root: Path) -> Path:
    common = Path(
        run_git(
            root, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).stdout.strip()
    )
    return common.parent if common.name == ".git" else common


def managed_worktree_root(root: Path) -> Path:
    return common_repo_root(root) / ".agent_state" / "worktrees"


def require_managed_worktree(root: Path, target: Path, *, kind: str) -> Path:
    managed = managed_worktree_root(root).resolve()
    resolved = target.resolve()
    try:
        relative = resolved.relative_to(managed)
    except ValueError as exc:
        raise OrchestrateError(f"{kind} worktree must be below {managed}") from exc
    if len(relative.parts) != 1:
        raise OrchestrateError(f"{kind} worktree must be a direct child of {managed}")
    return resolved


def require_task_lane_refs(task_ref: str, lane_ref: str) -> None:
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    if not lane_ref.startswith("agent/") or lane_ref.count("/") != 2:
        raise OrchestrateError(f"lane ref must use agent/<task>/<lane>: {lane_ref!r}")
    task_id = task_ref.split("/", 1)[1]
    _, lane_task, lane_name = lane_ref.split("/", 2)
    require_identifier(task_id, label="task ref id")
    require_identifier(lane_task, label="lane task id")
    require_identifier(lane_name, label="lane name")
    if task_id != lane_task:
        raise OrchestrateError("task and lane refs name different tasks")


def worktree_records(root: Path) -> list[dict[str, Any]]:
    output = run_git(root, "worktree", "list", "--porcelain").stdout
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value if value else True
    return records


def worktree_evidence(path: Path, *, started: float) -> dict[str, Any]:
    head = run_git(path, "rev-parse", "HEAD").stdout.strip()
    tree = run_git(path, "rev-parse", "HEAD^{tree}").stdout.strip()
    branch = run_git(path, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    status = run_git(path, "status", "--porcelain").stdout
    return {
        "path": str(path.resolve()),
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "head": head,
        "tree": tree,
        "clean": not bool(status.strip()),
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_lane_create(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    lane = require_identifier(args.lane, label="lane")
    base = exact_commit(root, args.base, label="base")
    branch = f"agent/{task_id}/{lane}"
    if (
        run_git(
            root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False
        ).returncode
        == 0
    ):
        raise OrchestrateError(f"lane branch already exists: {branch}")
    target = require_managed_worktree(
        root,
        (
            Path(args.worktree).resolve()
            if args.worktree
            else managed_worktree_root(root) / f"{task_id}-{lane}"
        ),
        kind="lane",
    )
    if target.exists():
        raise OrchestrateError(f"worktree path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "worktree", "add", "-b", branch, str(target), base)
    return {
        "ok": True,
        "operation": "lane-create",
        "base": base,
        **worktree_evidence(target, started=started),
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
    if target.exists():
        raise OrchestrateError(f"review worktree path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "worktree", "add", "--detach", str(target), target_sha)
    evidence = worktree_evidence(target, started=started)
    if evidence["branch"] is not None or evidence["head"] != target_sha:
        raise OrchestrateError("review checkout is not detached at the requested SHA")
    return {"ok": True, "operation": "review-checkout", **evidence}


def require_registered_worktree(root: Path, target: Path) -> dict[str, Any]:
    resolved = str(target.resolve())
    record = next(
        (
            record
            for record in worktree_records(root)
            if record.get("worktree") == resolved
        ),
        None,
    )
    if record is None:
        raise OrchestrateError(f"not a registered worktree: {target}")
    return record


def command_review_cleanup(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    target = require_managed_worktree(
        root, Path(args.worktree).resolve(), kind="review"
    )
    if not target.name.startswith("review-"):
        raise OrchestrateError("review worktree name must start with 'review-'")
    record = require_registered_worktree(root, target)
    if "detached" not in record:
        raise OrchestrateError("review cleanup only removes detached worktrees")
    if run_git(target, "status", "--porcelain").stdout.strip():
        raise OrchestrateError("review worktree is dirty")
    head = run_git(target, "rev-parse", "HEAD").stdout.strip()
    run_git(root, "worktree", "remove", str(target))
    return {
        "ok": True,
        "operation": "review-cleanup",
        "path": str(target),
        "head": head,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_collect(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    require_task_lane_refs(args.task_ref, args.lane_ref)
    expected = exact_commit(root, args.expected_lane_sha, label="expected lane SHA")
    reviewed = exact_commit(root, args.reviewed_sha, label="reviewed SHA")
    if expected != reviewed:
        raise OrchestrateError("reviewed SHA differs from expected lane SHA")
    current_branch = run_git(root, "symbolic-ref", "--short", "HEAD").stdout.strip()
    if current_branch != args.task_ref:
        raise OrchestrateError(
            f"integration checkout is {current_branch}, expected {args.task_ref}"
        )
    if run_git(root, "status", "--porcelain").stdout.strip():
        raise OrchestrateError("integration worktree is dirty")
    lane_head = run_git(root, "rev-parse", f"{args.lane_ref}^{{commit}}").stdout.strip()
    if lane_head != expected:
        raise OrchestrateError(f"lane target drifted: {lane_head} != {expected}")
    before = run_git(root, "rev-parse", "HEAD").stdout.strip()
    preflight = run_git(root, "merge-tree", "--write-tree", before, expected)
    merge_tree = preflight.stdout.splitlines()[0].strip()
    lane_head_again = run_git(
        root, "rev-parse", f"{args.lane_ref}^{{commit}}"
    ).stdout.strip()
    if lane_head_again != expected:
        raise OrchestrateError("lane target drifted after merge preflight")
    run_git(root, "merge", "--no-ff", "--no-edit", args.lane_ref)
    evidence = worktree_evidence(root, started=started)
    if not evidence["clean"]:
        raise OrchestrateError("collection left the integration worktree dirty")
    return {
        "ok": True,
        "operation": "collect",
        "task_ref": args.task_ref,
        "lane_ref": args.lane_ref,
        "reviewed_sha": reviewed,
        "before": before,
        "preflight_tree": merge_tree,
        **evidence,
    }


def command_lane_cleanup(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    require_task_lane_refs(args.task_ref, args.lane_ref)
    target = require_managed_worktree(root, Path(args.worktree).resolve(), kind="lane")
    record = require_registered_worktree(root, target)
    branch = str(record.get("branch", "")).removeprefix("refs/heads/")
    if branch != args.lane_ref:
        raise OrchestrateError(
            f"worktree branch is {branch!r}, expected {args.lane_ref!r}"
        )
    if run_git(target, "status", "--porcelain").stdout.strip():
        raise OrchestrateError("lane worktree is dirty")
    lane_sha = run_git(root, "rev-parse", f"{args.lane_ref}^{{commit}}").stdout.strip()
    task_sha = run_git(root, "rev-parse", f"{args.task_ref}^{{commit}}").stdout.strip()
    ancestor = (
        run_git(
            root,
            "merge-base",
            "--is-ancestor",
            lane_sha,
            task_sha,
            check=False,
        ).returncode
        == 0
    )
    tree_equal = (
        run_git(root, "diff", "--quiet", lane_sha, task_sha, check=False).returncode
        == 0
    )
    if not (ancestor or tree_equal):
        raise OrchestrateError(
            "lane is not absorbed by task ref (ancestry or tree identity)"
        )
    run_git(root, "worktree", "remove", str(target))
    run_git(root, "branch", "-D", args.lane_ref)
    return {
        "ok": True,
        "operation": "lane-cleanup",
        "lane_ref": args.lane_ref,
        "lane_sha": lane_sha,
        "task_ref": args.task_ref,
        "task_sha": task_sha,
        "absorption": "ancestor" if ancestor else "tree-identity",
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def section_text(text: str, heading: str) -> str:
    lines = text.splitlines()
    try:
        start = (
            next(index for index, line in enumerate(lines) if line.strip() == heading)
            + 1
        )
    except StopIteration:
        return ""
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


def table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else []


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    plan = root / ".agent_state" / "plans" / task_id / "task_plan.md"
    if not plan.is_file():
        raise OrchestrateError(f"task plan not found: {plan}")
    text = plan.read_text(encoding="utf-8")
    phases = []
    for line in section_text(text, "## Phase Status").splitlines():
        match = PHASE_ROW_PATTERN.match(line)
        if match:
            phases.append(match.groupdict())
    current = [
        item["phase"] for item in phases if item["status"] in {"in_progress", "blocked"}
    ]
    remaining = [item["phase"] for item in phases if item["status"] == "pending"]
    completed = [item["phase"] for item in phases if item["status"] == "completed"]
    current_state = section_text(text, "## Current State")
    packets = section_text(text, "## Active Domain Packets")
    review_debt = [
        line.split("Review debt:", 1)[1].strip()
        for line in packets.splitlines()
        if "Review debt:" in line and not line.rstrip().endswith(("none", "無"))
    ]
    next_gates = [
        line.split("Next acceptance gate:", 1)[1].strip()
        for line in packets.splitlines()
        if "Next acceptance gate:" in line
    ]
    progress_path = plan.parent / "progress.md"
    verification = []
    if progress_path.is_file():
        progress = progress_path.read_text(encoding="utf-8")
        verification = table_rows(section_text(progress, "## Verification Log"))[-5:]
    worktrees = []
    for record in worktree_records(root):
        path = Path(record["worktree"])
        status = run_git(path, "status", "--porcelain", check=False)
        worktrees.append(
            {
                "path": str(path),
                "branch": str(record.get("branch", "")).removeprefix("refs/heads/")
                or None,
                "head": record.get("HEAD"),
                "detached": "detached" in record,
                "clean": status.returncode == 0 and not bool(status.stdout.strip()),
            }
        )
    return {
        "ok": True,
        "task_id": task_id,
        "current_phase": current,
        "completed_phases": completed,
        "remaining_phases": remaining,
        "current_state": current_state,
        "review_debt": review_debt,
        "recent_verification": verification,
        "next_safe_pause": next_gates,
        "worktrees": worktrees,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def add_root(command: argparse.ArgumentParser) -> None:
    command.add_argument("--root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-dir",
        default=str(Path(__file__).resolve().parent.parent),
        help="orchestrate skill directory (defaults to this script's parent skill)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser(
        "doctor", help="verify manifest, compat, hashes, and read budgets"
    )
    doctor.set_defaults(handler=command_doctor)

    diff = commands.add_parser("diff", help="compare two bundled release manifests")
    diff.add_argument("old_version", type=int)
    diff.add_argument("new_version", type=int)
    diff.set_defaults(handler=command_diff)

    identity = commands.add_parser(
        "identity", help="report explicit runtime/profile identity evidence"
    )
    identity.add_argument("--requested", required=True)
    identity.add_argument("--effective", required=True)
    identity.add_argument("--profile", required=True)
    identity.add_argument("--agent-id", required=True)
    identity.add_argument("--writer-agent-id")
    identity.add_argument("--require-different-identity", action="store_true")
    identity.add_argument(
        "--park-capability",
        choices=("slot-free", "slot-held", "unknown"),
        default="unknown",
    )
    identity.set_defaults(handler=command_identity)

    status = commands.add_parser(
        "status", help="summarize plan plus observed Git topology"
    )
    add_root(status)
    status.add_argument("--task-id", required=True)
    status.set_defaults(handler=command_status)

    lane = commands.add_parser("lane", help="explicit lane lifecycle guards")
    lane_commands = lane.add_subparsers(dest="lane_command", required=True)
    lane_create = lane_commands.add_parser("create")
    add_root(lane_create)
    lane_create.add_argument("--task-id", required=True)
    lane_create.add_argument("--lane", required=True)
    lane_create.add_argument("--base", required=True)
    lane_create.add_argument("--worktree")
    lane_create.set_defaults(handler=command_lane_create)
    lane_cleanup = lane_commands.add_parser("cleanup")
    add_root(lane_cleanup)
    lane_cleanup.add_argument("--task-ref", required=True)
    lane_cleanup.add_argument("--lane-ref", required=True)
    lane_cleanup.add_argument("--worktree", required=True)
    lane_cleanup.set_defaults(handler=command_lane_cleanup)

    review = commands.add_parser("review", help="detached exact-SHA review worktrees")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    checkout = review_commands.add_parser("checkout")
    add_root(checkout)
    checkout.add_argument("sha")
    checkout.add_argument("--label")
    checkout.add_argument("--worktree")
    checkout.set_defaults(handler=command_review_checkout)
    cleanup = review_commands.add_parser("cleanup")
    add_root(cleanup)
    cleanup.add_argument("--worktree", required=True)
    cleanup.set_defaults(handler=command_review_cleanup)

    collect = commands.add_parser(
        "collect", help="preflight and merge one reviewed exact lane SHA"
    )
    add_root(collect)
    collect.add_argument("--task-ref", required=True)
    collect.add_argument("--lane-ref", required=True)
    collect.add_argument("--expected-lane-sha", required=True)
    collect.add_argument("--reviewed-sha", required=True)
    collect.set_defaults(handler=command_collect)

    release = commands.add_parser("release-manifest", help=argparse.SUPPRESS)
    release.add_argument("--version", required=True, type=int)
    release.add_argument("--previous-version", type=int)
    release.add_argument("--output", required=True)
    release.set_defaults(handler=command_release_manifest)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.handler(args)
    except (OSError, UnicodeError, OrchestrateError) as exc:
        parser.exit(2, f"orchestrate error: {exc}\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
