#!/usr/bin/env python3
"""Inspect orchestrate releases and guard explicit Git and delivery-spool actions."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

MANIFEST_SCHEMA = 1
QUEUE_VERSION = 1
DISPATCH_PACKET_VERSION = 1
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EXACT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMPAT_PATTERN = re.compile(r"^orchestrate_compat:\s*(\d+)\s*$", re.MULTILINE)
PROFILE_COMPAT_PATTERN = re.compile(
    r"^\s*(?:#\s*|<!--\s*)?orchestrate_compat\s*(?:=|:)\s*(\d+)\s*(?:-->)?\s*$",
    re.MULTILINE,
)
VERSION_PATTERN = re.compile(r"^skill_version:\s*(\d+)\s*$", re.MULTILINE)
PHASE_ROW_PATTERN = re.compile(
    r"^\|\s*(?P<phase>[^|]+?)\s*\|\s*"
    r"(?P<status>pending|in_progress|blocked|completed)\s*\|"
)
MILESTONE_STATES = ("progress", "terminal")
MILESTONE_NEXT = ("continue", "idle", "stop")
MILESTONE_OUTCOMES = {
    "planner": ("proposal", "needs_decision"),
    "writer": ("validated", "review", "blocked", "needs_decision"),
    "reviewer": ("pass", "needs_fix", "blocked", "needs_decision"),
}
MILESTONE_FIELDS = {
    "event",
    "item_id",
    "state",
    "outcome",
    "subject_sha",
    "evidence",
    "findings",
    "next",
    "details",
}
COLLECT_REVIEW_KINDS = (
    "different-identity",
    "focused",
    "root-spot",
    "mechanical",
)
QUEUE_ROLES = ("writer", "reviewer")
QUEUE_FIELDS = {
    "queue_version",
    "item_id",
    "order",
    "role",
    "lease_id",
    "lease_generation",
    "basis_sha",
    "hard_critical_axes",
}
DISPATCH_ROLES = ("planner", "writer", "reviewer")
HARD_CRITICAL_AXES = ("hardware", "persistence", "security", "atomic-cutover")
DISPATCH_FIELDS = {
    "dispatch_packet_version",
    "packet_id",
    "role",
    "basis_sha",
    "hard_critical_axes",
}
DISPATCH_SECTIONS = (
    "Authority",
    "Acceptance",
    "Non-goals",
    "Exact literals",
    "Oracles",
    "Review policy",
    "Stop conditions",
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
        probe = run_git(
            root, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}", check=False
        )
        resolved = probe.stdout.strip()
        hint = (
            f"; resolved full SHA: {resolved} — retry with this value"
            if probe.returncode == 0 and resolved
            else ""
        )
        raise OrchestrateError(
            f"{label} must be an exact hexadecimal commit SHA{hint}"
        )
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


def profile_compat(text: str) -> int | None:
    match = PROFILE_COMPAT_PATTERN.search(text)
    return int(match.group(1)) if match else None


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
        entry = {
            "bytes": len(data),
            "sha256": sha256_bytes(data),
            "standing_orders_sha256": normalized_sha256(
                profile_standing_orders(text, path.suffix)
            ),
        }
        compat = profile_compat(text)
        if compat is not None:
            entry["orchestrate_compat"] = compat
        profiles[path.relative_to(home).as_posix()] = entry
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


def verify_release(skill_dir: Path) -> dict[str, Any]:
    skill_dir = skill_dir.resolve()
    version = skill_version(skill_dir)
    manifest = load_manifest(skill_dir, version)
    observed = build_manifest(skill_dir, version)
    errors: list[str] = []
    for category in ("documents", "profiles"):
        expected_items = manifest[category]
        observed_items = observed[category]
        # Profile identity is the standing orders, not the file: model/effort
        # tuning outside developer_instructions must not fail a release check.
        digest = "sha256" if category == "documents" else "standing_orders_sha256"
        for name in sorted(set(expected_items) | set(observed_items)):
            if name not in expected_items:
                errors.append(f"unexpected {category[:-1]}: {name}")
            elif name not in observed_items:
                errors.append(f"missing {category[:-1]}: {name}")
            elif expected_items[name][digest] != observed_items[name][digest]:
                errors.append(f"hash mismatch: {name}")
    for name, entry in observed["documents"].items():
        if name.endswith(".md") and entry["bytes"] > 16_384:
            errors.append(
                f"single-read budget exceeded: {name} ({entry['bytes']} bytes)"
            )
        compat = entry.get("orchestrate_compat")
        if compat is not None and compat != version:
            errors.append(f"compat mismatch: {name}={compat}, expected {version}")
    for name, entry in observed["profiles"].items():
        compat = entry.get("orchestrate_compat")
        if compat != version:
            errors.append(
                f"profile compat mismatch: {name}={compat}, expected {version}"
            )
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


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    return verify_release(Path(args.skill_dir))


def require_release_preflight(skill_dir: Path) -> dict[str, Any]:
    result = verify_release(skill_dir)
    if not result["ok"]:
        raise OrchestrateError(
            "release preflight failed: " + "; ".join(result["errors"])
        )
    return {
        "skill_version": result["skill_version"],
        "orchestrate_compat": result["orchestrate_compat"],
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
    comparison = compare_manifests(old, new)
    if args.runtime is not None:
        runtime_document = f"runtime-{args.runtime}.md"
        profile_prefix = ".codex/" if args.runtime == "codex" else ".claude/"
        comparison["changed_documents"] = [
            document
            for document in comparison["changed_documents"]
            if not document["path"].startswith("runtime-")
            or document["path"] == runtime_document
        ]
        comparison["must_reread"] = [
            path
            for path in comparison["must_reread"]
            if not path.startswith("runtime-") or path == runtime_document
        ]
        comparison["changed_profiles"] = [
            path
            for path in comparison["changed_profiles"]
            if path.startswith(profile_prefix)
        ]
        comparison["runtime"] = args.runtime
    return {"ok": True, **comparison}


def command_identity(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    profile = Path(args.profile).resolve()
    try:
        data = profile.read_bytes()
    except OSError as exc:
        raise OrchestrateError(f"cannot read profile {profile}: {exc}") from exc
    text = data.decode("utf-8")
    profile_hash = sha256_bytes(data)
    same_identity: bool | None = None
    if args.writer_agent_id is not None:
        same_identity = args.agent_id == args.writer_agent_id
    current_version = skill_version(skill_dir)
    observed_compat = profile_compat(text)
    profile_manifest_version: int | None = None
    manifest_profiles = load_manifest(skill_dir, current_version)["profiles"]
    try:
        relative_profile = profile.relative_to(source_home(skill_dir)).as_posix()
        expected_profile = manifest_profiles.get(relative_profile)
        if expected_profile and expected_profile["sha256"] == profile_hash:
            profile_manifest_version = current_version
    except ValueError:
        pass
    if profile_manifest_version is None and any(
        entry["sha256"] == profile_hash for entry in manifest_profiles.values()
    ):
        profile_manifest_version = current_version
    different_identity = None if same_identity is None else not same_identity
    requirement_checks: dict[str, bool] = {}
    requirement_checks["profile_compat"] = observed_compat == current_version
    requirement_checks["profile_release_match"] = (
        profile_manifest_version == current_version
    )
    if args.require_different_identity:
        requirement_checks["different_identity"] = different_identity is True
    return {
        "ok": True,
        "requested_identity": args.requested,
        "effective_identity": args.effective,
        "agent_id": args.agent_id,
        "profile": str(profile),
        "profile_sha256": profile_hash,
        "profile_manifest_version": profile_manifest_version,
        "profile_compat": observed_compat,
        "profile_compat_matches_current": observed_compat == current_version,
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


def read_json_object(path: str, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        data = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
        payload = json.loads(data)
    except (OSError, json.JSONDecodeError) as exc:
        raise OrchestrateError(f"cannot read {label} JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise OrchestrateError(f"{label} JSON must be an object")
    return payload, data


def require_json_fields(
    payload: dict[str, Any], fields: Sequence[str], errors: list[str]
) -> None:
    for field in fields:
        if field not in payload:
            errors.append(f"missing required field: {field}")


def validate_json_enum(
    payload: dict[str, Any],
    field: str,
    choices: Sequence[str],
    errors: list[str],
) -> None:
    if field in payload and payload[field] not in choices:
        errors.append(f"{field} must be one of: {', '.join(choices)}")


def validate_exact_sha_field(
    payload: dict[str, Any], field: str, errors: list[str]
) -> None:
    value = payload.get(field)
    if value is not None and (
        not isinstance(value, str) or not EXACT_SHA_PATTERN.fullmatch(value)
    ):
        errors.append(f"{field} must be an exact 40-64 character hexadecimal SHA")


def validate_milestone(payload: dict[str, Any], *, role: str) -> list[str]:
    errors: list[str] = []
    required = ("event", "item_id", "state", "outcome", "evidence", "findings", "next")
    require_json_fields(
        payload,
        required,
        errors,
    )
    unexpected = sorted(payload.keys() - MILESTONE_FIELDS)
    if unexpected:
        errors.append(f"unexpected fields: {', '.join(unexpected)}")
    if payload.get("event") != "milestone":
        errors.append("event must be milestone")
    item_id = payload.get("item_id")
    if item_id is not None and (
        not isinstance(item_id, str) or not ID_PATTERN.fullmatch(item_id)
    ):
        errors.append("item_id must be a stable identifier")
    validate_json_enum(payload, "state", MILESTONE_STATES, errors)
    validate_json_enum(payload, "next", MILESTONE_NEXT, errors)
    evidence = payload.get("evidence")
    if evidence is not None and (not isinstance(evidence, str) or not evidence.strip()):
        errors.append("evidence must be a non-empty string")
    findings = payload.get("findings")
    if findings is not None and (
        not isinstance(findings, list)
        or any(not isinstance(item, str) or not item.strip() for item in findings)
    ):
        errors.append("findings must be a list of non-empty ids")
    details = payload.get("details")
    if details is not None and not isinstance(details, dict):
        errors.append("details must be an object when supplied")
    validate_exact_sha_field(payload, "subject_sha", errors)

    state = payload.get("state")
    outcome = payload.get("outcome")
    if state == "progress":
        if outcome != "working":
            errors.append("progress requires outcome=working")
        if "subject_sha" in payload:
            errors.append("progress must omit subject_sha")
    elif state == "terminal":
        if outcome not in MILESTONE_OUTCOMES[role]:
            errors.append(
                f"terminal {role} outcome must be one of: "
                + ", ".join(MILESTONE_OUTCOMES[role])
            )
        sha_required = (role == "writer" and outcome in ("validated", "review")) or (
            role == "reviewer" and outcome in ("pass", "needs_fix")
        )
        if sha_required and "subject_sha" not in payload:
            errors.append(f"{role} outcome={outcome} requires subject_sha")
    return errors


def command_milestone_lint(args: argparse.Namespace) -> dict[str, Any]:
    payload, data = read_json_object(args.input, label="milestone")
    errors = validate_milestone(payload, role=args.role)
    return {
        "ok": not errors,
        "operation": "milestone-lint",
        "role": args.role,
        "input_sha256": sha256_bytes(data),
        "delivery_inferred": False,
        "errors": errors,
    }


def common_repo_root(root: Path) -> Path:
    common = Path(
        run_git(
            root, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).stdout.strip()
    )
    return common.parent if common.name == ".git" else common


def require_gitignored_agent_state(root: Path) -> None:
    ignored = run_git(
        root,
        "check-ignore",
        "--no-index",
        "--quiet",
        "--",
        ".agent_state/orchestrate/.probe",
        check=False,
    )
    if ignored.returncode != 0:
        raise OrchestrateError(
            ".agent_state/orchestrate must be gitignored before transport use"
        )


def read_regular_input(path_value: str, *, label: str) -> tuple[bytes, Path]:
    supplied = Path(path_value)
    if supplied.is_symlink():
        raise OrchestrateError(f"{label} input must not be a symlink: {supplied}")
    path = supplied.resolve()
    if not path.is_file():
        raise OrchestrateError(f"{label} input must be a regular file: {path}")
    return path.read_bytes(), path


def dispatch_packet_directory(root: Path, *, task_id: str) -> tuple[Path, Path]:
    common = common_repo_root(root).resolve()
    task_id = require_identifier(task_id, label="task-id")
    state = common / ".agent_state"
    paths = (
        state,
        state / "orchestrate",
        state / "orchestrate" / task_id,
        state / "orchestrate" / task_id / "packets",
    )
    for path in paths:
        if path.is_symlink():
            raise OrchestrateError(
                f"dispatch packet path component must not be a symlink: {path}"
            )
    require_gitignored_agent_state(common)
    return common, paths[-1]


def parse_dispatch_packet(data: bytes, *, root: Path, source: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OrchestrateError(f"dispatch packet is not UTF-8: {source}") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise OrchestrateError(
            f"dispatch packet requires YAML-style front matter: {source}"
        )
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise OrchestrateError(
            f"dispatch packet front matter is not closed: {source}"
        ) from exc
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not separator or not key or not value:
            raise OrchestrateError(
                f"malformed dispatch packet front matter line: {line!r}"
            )
        if key in fields:
            raise OrchestrateError(
                f"duplicate dispatch packet front matter field: {key}"
            )
        fields[key] = value
    missing = sorted(DISPATCH_FIELDS - fields.keys())
    unexpected = sorted(fields.keys() - DISPATCH_FIELDS)
    if missing or unexpected:
        detail = []
        if missing:
            detail.append(f"missing={','.join(missing)}")
        if unexpected:
            detail.append(f"unexpected={','.join(unexpected)}")
        raise OrchestrateError(
            f"invalid dispatch packet front matter ({'; '.join(detail)})"
        )
    try:
        version = int(fields["dispatch_packet_version"])
    except ValueError as exc:
        raise OrchestrateError("dispatch_packet_version must be an integer") from exc
    if version != DISPATCH_PACKET_VERSION:
        raise OrchestrateError(
            f"unsupported dispatch_packet_version={version}; "
            f"expected {DISPATCH_PACKET_VERSION}"
        )
    packet_id = require_identifier(fields["packet_id"], label="packet-id")
    role = fields["role"]
    if role not in DISPATCH_ROLES:
        raise OrchestrateError(
            f"dispatch packet role must be one of: {', '.join(DISPATCH_ROLES)}"
        )
    raw_axes = fields["hard_critical_axes"]
    axes = [] if raw_axes == "none" else [axis.strip() for axis in raw_axes.split(",")]
    if (
        any(axis not in HARD_CRITICAL_AXES for axis in axes)
        or len(axes) != len(set(axes))
        or any(not axis for axis in axes)
    ):
        raise OrchestrateError(
            "hard_critical_axes must be none or a unique comma-separated subset of: "
            + ", ".join(HARD_CRITICAL_AXES)
        )
    basis_sha = exact_commit(root, fields["basis_sha"], label="basis_sha")
    for heading in DISPATCH_SECTIONS:
        if not section_text(text, f"## {heading}"):
            raise OrchestrateError(
                f"dispatch packet missing or empty required section: {heading}"
            )
    return {
        "dispatch_packet_version": version,
        "packet_id": packet_id,
        "role": role,
        "basis_sha": basis_sha,
        "hard_critical_axes": axes,
    }


def dispatch_packet_evidence(
    *,
    root: Path,
    directory: Path,
    path: Path,
    data: bytes,
    envelope: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": "packet-inspect",
        "root": str(root),
        "packet_directory": str(directory),
        "path": str(path),
        "sha256": sha256_bytes(data),
        "envelope": envelope,
        "authority_inferred": False,
        "dispatch_inferred": False,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_packet_publish(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    requested_root = Path(args.root).resolve()
    root, directory = dispatch_packet_directory(requested_root, task_id=args.task_id)
    data, source = read_regular_input(args.input, label="dispatch packet")
    envelope = parse_dispatch_packet(data, root=root, source=str(source))
    digest = sha256_bytes(data)
    destination = directory / f"{digest}.md"
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise OrchestrateError(
            f"dispatch packet directory must not be a symlink: {directory}"
        )
    descriptor = lock_queue_directory(directory, exclusive=True)
    try:
        if destination.exists():
            if destination.is_symlink() or not destination.is_file():
                raise OrchestrateError(
                    f"dispatch packet destination is not a regular file: {destination}"
                )
            if destination.read_bytes() != data:
                raise OrchestrateError(
                    f"content-address collision or tampered packet: {destination}"
                )
            created = False
        else:
            handle, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.pending-", dir=directory
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if destination.exists():
                    raise OrchestrateError(
                        f"dispatch packet destination appeared: {destination}"
                    )
                os.replace(temporary, destination)
                os.fsync(descriptor)
            finally:
                temporary.unlink(missing_ok=True)
            created = True
    finally:
        unlock_queue_directory(descriptor)
    return {
        **dispatch_packet_evidence(
            root=root,
            directory=directory,
            path=destination,
            data=data,
            envelope=envelope,
            started=started,
        ),
        "operation": "packet-publish",
        "created": created,
    }


def command_packet_inspect(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    if not SHA256_PATTERN.fullmatch(args.sha256):
        raise OrchestrateError("sha256 must be 64 lowercase hexadecimal digits")
    requested_root = Path(args.root).resolve()
    root, directory = dispatch_packet_directory(requested_root, task_id=args.task_id)
    path = directory / f"{args.sha256}.md"
    if path.is_symlink() or not path.is_file():
        raise OrchestrateError(f"dispatch packet not found: {path}")
    data = path.read_bytes()
    if sha256_bytes(data) != args.sha256:
        raise OrchestrateError(f"dispatch packet hash mismatch: {path}")
    envelope = parse_dispatch_packet(data, root=root, source=str(path))
    return dispatch_packet_evidence(
        root=root,
        directory=directory,
        path=path,
        data=data,
        envelope=envelope,
        started=started,
    )


def queue_directory(
    root: Path,
    *,
    task_id: str,
    lease_id: str,
    generation: int,
) -> tuple[Path, Path]:
    common = common_repo_root(root).resolve()
    task_id = require_identifier(task_id, label="task-id")
    lease_id = require_identifier(lease_id, label="lease-id")
    if generation < 1 or generation > 9999:
        raise OrchestrateError("generation must be between 1 and 9999")
    state = common / ".agent_state"
    paths = (
        state,
        state / "orchestrate",
        state / "orchestrate" / task_id,
        state / "orchestrate" / task_id / "queues",
        state / "orchestrate" / task_id / "queues" / lease_id,
    )
    for path in paths:
        if path.is_symlink():
            raise OrchestrateError(
                f"queue path component must not be a symlink: {path}"
            )
    queue = paths[-1] / f"g{generation:04d}"
    if queue.is_symlink():
        raise OrchestrateError(f"queue directory must not be a symlink: {queue}")
    require_gitignored_agent_state(common)
    return common, queue


def read_queue_input(path_value: str) -> tuple[bytes, Path]:
    return read_regular_input(path_value, label="queue")


def parse_queue_item(data: bytes, *, root: Path, source: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OrchestrateError(f"queue item is not UTF-8: {source}") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise OrchestrateError(f"queue item requires YAML-style front matter: {source}")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise OrchestrateError(
            f"queue item front matter is not closed: {source}"
        ) from exc
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not separator or not key or not value:
            raise OrchestrateError(f"malformed queue front matter line: {line!r}")
        if key in fields:
            raise OrchestrateError(f"duplicate queue front matter field: {key}")
        fields[key] = value
    missing = sorted(QUEUE_FIELDS - fields.keys())
    unexpected = sorted(fields.keys() - QUEUE_FIELDS)
    if missing or unexpected:
        detail = []
        if missing:
            detail.append(f"missing={','.join(missing)}")
        if unexpected:
            detail.append(f"unexpected={','.join(unexpected)}")
        raise OrchestrateError(f"invalid queue front matter ({'; '.join(detail)})")
    try:
        queue_version = int(fields["queue_version"])
        order = int(fields["order"])
        generation = int(fields["lease_generation"])
    except ValueError as exc:
        raise OrchestrateError(
            "queue_version, order, and lease_generation must be integers"
        ) from exc
    if queue_version != QUEUE_VERSION:
        raise OrchestrateError(
            f"unsupported queue_version={queue_version}; expected {QUEUE_VERSION}"
        )
    if order < 0 or order > 999999:
        raise OrchestrateError("queue order must be between 0 and 999999")
    if generation < 1 or generation > 9999:
        raise OrchestrateError("lease_generation must be between 1 and 9999")
    item_id = require_identifier(fields["item_id"], label="item-id")
    lease_id = require_identifier(fields["lease_id"], label="lease-id")
    role = fields["role"]
    if role not in QUEUE_ROLES:
        raise OrchestrateError(
            f"queue role must be a normal writer/reviewer role: {role!r}"
        )
    if fields["hard_critical_axes"] != "none":
        raise OrchestrateError(
            "durable queues accept normal writer/reviewer work only; "
            "hard_critical_axes must be none"
        )
    basis_sha = exact_commit(root, fields["basis_sha"], label="basis_sha")
    if not "\n".join(lines[end + 1 :]).strip():
        raise OrchestrateError(f"queue item body is empty: {source}")
    return {
        "queue_version": queue_version,
        "item_id": item_id,
        "order": order,
        "role": role,
        "lease_id": lease_id,
        "lease_generation": generation,
        "basis_sha": basis_sha,
        "hard_critical_axes": "none",
    }


def validate_queue_binding(
    item: dict[str, Any],
    *,
    role: str,
    lease_id: str,
    generation: int,
) -> None:
    expected = {
        "role": role,
        "lease_id": lease_id,
        "lease_generation": generation,
    }
    for field, value in expected.items():
        if item[field] != value:
            raise OrchestrateError(
                f"queue item {field}={item[field]!r}, expected {value!r}"
            )


def queue_filename(item: dict[str, Any]) -> str:
    return f"{item['order']:06d}-{item['item_id']}.md"


def queue_item_evidence(
    item: dict[str, Any], *, path: Path, data: bytes
) -> dict[str, Any]:
    return {
        **item,
        "path": str(path),
        "sha256": sha256_bytes(data),
    }


def scan_queue(
    root: Path,
    directory: Path,
    *,
    role: str,
    lease_id: str,
    generation: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    if not directory.exists():
        return [], [], []
    if directory.is_symlink() or not directory.is_dir():
        raise OrchestrateError(f"queue path must be a directory: {directory}")
    items: list[dict[str, Any]] = []
    pending: list[str] = []
    unexpected: list[str] = []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.name.startswith(".") and ".pending-" in path.name:
            pending.append(path.name)
            continue
        if path.suffix != ".md" or path.is_symlink() or not path.is_file():
            unexpected.append(path.name)
            continue
        data = path.read_bytes()
        item = parse_queue_item(data, root=root, source=str(path))
        validate_queue_binding(
            item, role=role, lease_id=lease_id, generation=generation
        )
        expected_name = queue_filename(item)
        if path.name != expected_name:
            raise OrchestrateError(
                f"queue filename {path.name!r}, expected {expected_name!r}"
            )
        if item["item_id"] in seen_ids:
            raise OrchestrateError(f"duplicate queue item_id: {item['item_id']}")
        if item["order"] in seen_orders:
            raise OrchestrateError(f"duplicate queue order: {item['order']}")
        seen_ids.add(item["item_id"])
        seen_orders.add(item["order"])
        items.append(queue_item_evidence(item, path=path, data=data))
    items.sort(key=lambda item: (item["order"], item["item_id"]))
    return items, pending, unexpected


def lock_queue_directory(directory: Path, *, exclusive: bool) -> int:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(
            descriptor,
            fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH,
        )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def unlock_queue_directory(descriptor: int) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def queue_operation_base(
    *,
    operation: str,
    root: Path,
    directory: Path,
    task_id: str,
    role: str,
    lease_id: str,
    generation: int,
    started: float,
) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": operation,
        "root": str(root),
        "task_id": task_id,
        "role": role,
        "lease_id": lease_id,
        "lease_generation": generation,
        "queue_path": str(directory),
        "queue_version": QUEUE_VERSION,
        "completion_inferred": False,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_queue_inspect(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    requested_root = Path(args.root).resolve()
    root, directory = queue_directory(
        requested_root,
        task_id=args.task_id,
        lease_id=args.lease_id,
        generation=args.generation,
    )
    if directory.exists():
        descriptor = lock_queue_directory(directory, exclusive=False)
        try:
            items, pending, unexpected = scan_queue(
                root,
                directory,
                role=args.role,
                lease_id=args.lease_id,
                generation=args.generation,
            )
        finally:
            unlock_queue_directory(descriptor)
    else:
        items, pending, unexpected = [], [], []
    return {
        **queue_operation_base(
            operation="queue-inspect",
            root=root,
            directory=directory,
            task_id=args.task_id,
            role=args.role,
            lease_id=args.lease_id,
            generation=args.generation,
            started=started,
        ),
        "items": items,
        "pending_artifacts": pending,
        "unexpected_artifacts": unexpected,
    }


def command_queue_publish(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    requested_root = Path(args.root).resolve()
    root, directory = queue_directory(
        requested_root,
        task_id=args.task_id,
        lease_id=args.lease_id,
        generation=args.generation,
    )
    candidates: list[tuple[dict[str, Any], bytes]] = []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for input_path in args.input:
        data, source = read_queue_input(input_path)
        item = parse_queue_item(data, root=root, source=str(source))
        validate_queue_binding(
            item,
            role=args.role,
            lease_id=args.lease_id,
            generation=args.generation,
        )
        if item["item_id"] in seen_ids:
            raise OrchestrateError(f"duplicate input item_id: {item['item_id']}")
        if item["order"] in seen_orders:
            raise OrchestrateError(f"duplicate input order: {item['order']}")
        seen_ids.add(item["item_id"])
        seen_orders.add(item["order"])
        candidates.append((item, data))
    candidates.sort(
        key=lambda candidate: (candidate[0]["order"], candidate[0]["item_id"])
    )
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise OrchestrateError(f"queue directory must not be a symlink: {directory}")
    descriptor = lock_queue_directory(directory, exclusive=True)
    try:
        existing, pending, unexpected = scan_queue(
            root,
            directory,
            role=args.role,
            lease_id=args.lease_id,
            generation=args.generation,
        )
        if pending or unexpected:
            raise OrchestrateError(
                "queue contains unreconciled artifacts; inspect before publishing"
            )
        existing_ids = {item["item_id"] for item in existing}
        existing_orders = {item["order"] for item in existing}
        for item, _ in candidates:
            destination = directory / queue_filename(item)
            if (
                destination.exists()
                or item["item_id"] in existing_ids
                or item["order"] in existing_orders
            ):
                raise OrchestrateError(
                    f"queue item already exists: {item['item_id']} order={item['order']}"
                )
        published: list[dict[str, Any]] = []
        for item, data in candidates:
            destination = directory / queue_filename(item)
            handle, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.pending-",
                dir=directory,
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if destination.exists():
                    raise OrchestrateError(f"queue destination appeared: {destination}")
                os.replace(temporary, destination)
                os.fsync(descriptor)
            finally:
                if temporary.exists():
                    temporary.unlink()
            published.append(queue_item_evidence(item, path=destination, data=data))
    finally:
        unlock_queue_directory(descriptor)
    return {
        **queue_operation_base(
            operation="queue-publish",
            root=root,
            directory=directory,
            task_id=args.task_id,
            role=args.role,
            lease_id=args.lease_id,
            generation=args.generation,
            started=started,
        ),
        "items": published,
        "producer_authority_inferred": False,
        "readiness_inferred": False,
    }


def command_queue_remove(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    requested_root = Path(args.root).resolve()
    root, directory = queue_directory(
        requested_root,
        task_id=args.task_id,
        lease_id=args.lease_id,
        generation=args.generation,
    )
    item_id = require_identifier(args.item_id, label="item-id")
    if args.order < 0 or args.order > 999999:
        raise OrchestrateError("queue order must be between 0 and 999999")
    if not SHA256_PATTERN.fullmatch(args.expected_sha256):
        raise OrchestrateError(
            "expected-sha256 must be 64 lowercase hexadecimal digits"
        )
    stale_reconciliation = bool(args.stale_reconciliation_confirmed)
    retraction_reason = (args.reason or "").strip()
    if stale_reconciliation and (
        not args.consumer_ended_confirmed or not retraction_reason
    ):
        raise OrchestrateError(
            "stale reconciliation requires --consumer-ended-confirmed and --reason"
        )
    if not directory.is_dir() or directory.is_symlink():
        raise OrchestrateError(f"queue directory not found: {directory}")
    descriptor = lock_queue_directory(directory, exclusive=True)
    try:
        destination = directory / f"{args.order:06d}-{item_id}.md"
        if destination.is_symlink() or not destination.is_file():
            raise OrchestrateError(f"queue item not found: {destination}")
        data = destination.read_bytes()
        observed_sha256 = sha256_bytes(data)
        if observed_sha256 != args.expected_sha256:
            raise OrchestrateError(
                "queue item hash mismatch; retain the item and reconcile before retrying"
            )
        item = parse_queue_item(data, root=root, source=str(destination))
        validate_queue_binding(
            item,
            role=args.role,
            lease_id=args.lease_id,
            generation=args.generation,
        )
        if item["item_id"] != item_id or item["order"] != args.order:
            raise OrchestrateError("queue item envelope does not match removal request")
        destination.unlink()
        os.fsync(descriptor)
    finally:
        unlock_queue_directory(descriptor)
    return {
        **queue_operation_base(
            operation="queue-remove",
            root=root,
            directory=directory,
            task_id=args.task_id,
            role=args.role,
            lease_id=args.lease_id,
            generation=args.generation,
            started=started,
        ),
        "item_id": item_id,
        "order": args.order,
        "removed_sha256": observed_sha256,
        "terminal_delivery_declared": bool(args.terminal_delivery_confirmed),
        "terminal_delivery_inferred": False,
        "removal_authorization": (
            "stale-reconciliation" if stale_reconciliation else "terminal-delivery"
        ),
        "consumer_ended_declared": bool(args.consumer_ended_confirmed),
        "retraction_reason": retraction_reason if stale_reconciliation else None,
    }


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
    record = next(
        (
            record
            for record in worktree_records(root)
            if record.get("worktree") == str(target)
        ),
        None,
    )
    result: dict[str, Any] = {
        "ok": True,
        "operation": "review-cleanup",
        "path": str(target),
    }
    if record is None:
        if target.exists():
            raise OrchestrateError(f"not a registered worktree: {target}")
        result["recovered"] = "already-removed"
    else:
        # Preflight metadata writability before any mutation: a sandbox that can
        # delete the directory but not .git/worktrees leaves half-removed state.
        metadata_dir = (
            root / run_git(root, "rev-parse", "--git-common-dir").stdout.strip()
        ).resolve() / "worktrees"
        if metadata_dir.exists() and not os.access(metadata_dir, os.W_OK):
            raise OrchestrateError(
                f"worktree metadata is not writable: {metadata_dir}; grant write"
                " access before cleanup — nothing was removed"
            )
        if not target.exists():
            run_git(root, "worktree", "prune")
            result["recovered"] = "pruned-stale-metadata"
        else:
            if "detached" not in record:
                raise OrchestrateError(
                    "review cleanup only removes detached worktrees"
                )
            if run_git(target, "status", "--porcelain").stdout.strip():
                raise OrchestrateError("review worktree is dirty")
            result["head"] = run_git(target, "rev-parse", "HEAD").stdout.strip()
            run_git(root, "worktree", "remove", str(target))
    return {
        **result,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_collect(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    require_task_lane_refs(args.task_ref, args.lane_ref)
    expected = exact_commit(root, args.expected_lane_sha, label="expected lane SHA")
    authorized = exact_commit(root, args.authorized_sha, label="authorized SHA")
    if expected != authorized:
        raise OrchestrateError("authorized SHA differs from expected lane SHA")
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
        "authorized_sha": authorized,
        "declared_review_kind": args.review_kind,
        "verdict_inferred": False,
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
    diff.add_argument("--runtime", choices=("codex", "claude"))
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

    packet = commands.add_parser(
        "packet", help="publish or inspect immutable direct-dispatch packets"
    )
    packet_commands = packet.add_subparsers(dest="packet_command", required=True)
    packet_publish = packet_commands.add_parser(
        "publish", help="validate and atomically publish content-addressed work"
    )
    add_root(packet_publish)
    packet_publish.add_argument("--task-id", required=True)
    packet_publish.add_argument("--input", required=True)
    packet_publish.set_defaults(
        handler=command_packet_publish, requires_release_preflight=True
    )
    packet_inspect = packet_commands.add_parser(
        "inspect", help="read and verify one exact content-addressed packet"
    )
    add_root(packet_inspect)
    packet_inspect.add_argument("--task-id", required=True)
    packet_inspect.add_argument("--sha256", required=True)
    packet_inspect.set_defaults(handler=command_packet_inspect)

    milestone = commands.add_parser("milestone", help="lint one semantic role event")
    milestone_commands = milestone.add_subparsers(
        dest="milestone_command", required=True
    )
    milestone_lint = milestone_commands.add_parser("lint")
    milestone_lint.add_argument("--role", choices=DISPATCH_ROLES, required=True)
    milestone_lint.add_argument(
        "--input", required=True, help="milestone JSON path, or '-' for stdin"
    )
    milestone_lint.set_defaults(handler=command_milestone_lint)

    queue = commands.add_parser(
        "queue", help="guard the bounded per-agent durable delivery spool"
    )
    queue_commands = queue.add_subparsers(dest="queue_command", required=True)

    def add_queue_binding(command: argparse.ArgumentParser) -> None:
        add_root(command)
        command.add_argument("--task-id", required=True)
        command.add_argument("--role", choices=QUEUE_ROLES, required=True)
        command.add_argument("--lease-id", required=True)
        command.add_argument("--generation", type=int, required=True)

    queue_publish = queue_commands.add_parser(
        "publish", help="atomically publish immutable ready item files"
    )
    add_queue_binding(queue_publish)
    queue_publish.add_argument("--input", action="append", required=True)
    queue_publish.set_defaults(
        handler=command_queue_publish, requires_release_preflight=True
    )

    queue_inspect = queue_commands.add_parser(
        "inspect", help="read and validate one lease generation without mutation"
    )
    add_queue_binding(queue_inspect)
    queue_inspect.set_defaults(handler=command_queue_inspect)

    queue_remove = queue_commands.add_parser(
        "remove", help="remove one exact terminal or root-reconciled stale item"
    )
    add_queue_binding(queue_remove)
    queue_remove.add_argument("--item-id", required=True)
    queue_remove.add_argument("--order", type=int, required=True)
    queue_remove.add_argument("--expected-sha256", required=True)
    removal_authorization = queue_remove.add_mutually_exclusive_group(required=True)
    removal_authorization.add_argument(
        "--terminal-delivery-confirmed", action="store_true"
    )
    removal_authorization.add_argument(
        "--stale-reconciliation-confirmed", action="store_true"
    )
    queue_remove.add_argument("--consumer-ended-confirmed", action="store_true")
    queue_remove.add_argument("--reason")
    queue_remove.set_defaults(handler=command_queue_remove)

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
    lane_create.set_defaults(
        handler=command_lane_create, requires_release_preflight=True
    )
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
    checkout.set_defaults(
        handler=command_review_checkout, requires_release_preflight=True
    )
    cleanup = review_commands.add_parser("cleanup")
    add_root(cleanup)
    cleanup.add_argument("--worktree", required=True)
    cleanup.set_defaults(handler=command_review_cleanup)

    collect = commands.add_parser(
        "collect", help="preflight and merge one explicitly authorized exact lane SHA"
    )
    add_root(collect)
    collect.add_argument("--task-ref", required=True)
    collect.add_argument("--lane-ref", required=True)
    collect.add_argument("--expected-lane-sha", required=True)
    collect.add_argument("--authorized-sha", required=True)
    collect.add_argument("--review-kind", choices=COLLECT_REVIEW_KINDS, required=True)
    collect.set_defaults(handler=command_collect, requires_release_preflight=True)

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
        release_preflight = None
        if getattr(args, "requires_release_preflight", False):
            release_preflight = require_release_preflight(Path(args.skill_dir))
        payload = args.handler(args)
        if release_preflight is not None:
            payload["release_preflight"] = release_preflight
    except (OSError, UnicodeError, OrchestrateError) as exc:
        parser.exit(2, f"orchestrate error: {exc}\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
