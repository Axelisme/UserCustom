#!/usr/bin/env python3
"""Inspect orchestrate releases and guard explicit Git and delivery-spool actions."""

from __future__ import annotations

import argparse
import fcntl
import fnmatch
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
VERSION_PATTERN = re.compile(r"^skill_version:\s*(\d+)\s*$", re.MULTILINE)
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
QUEUE_REQUIRED = {
    "queue_version",
    "item_id",
    "order",
    "role",
    "lease_id",
    "lease_generation",
    "basis_sha",
}
QUEUE_FIELDS = QUEUE_REQUIRED | {"hard_critical_axes"}
DISPATCH_ROLES = ("planner", "writer", "reviewer")
HARD_CRITICAL_AXES = ("hardware", "persistence", "security", "atomic-cutover")
DISPATCH_FIELDS = {
    "dispatch_packet_version",
    "packet_id",
    "role",
    "basis_sha",
    "hard_critical_axes",
}
RECEIPT_VERSION = 1
RECEIPT_KINDS = ("review", "gate")
GATE_STATUSES = (
    "passed",
    "failed_current",
    "failed_baseline",
    "environment_blocked",
    "unverified",
)
GATE_RECEIPT_REQUIRED = (
    "receipt_version",
    "kind",
    "item_id",
    "subject_sha",
    "command",
    "status",
    "exclusions",
)
GATE_RECEIPT_FIELDS = set(GATE_RECEIPT_REQUIRED) | {"subject_tree", "details"}
GATE_EXCLUSION_REQUIRED = (
    "test_id",
    "reason",
    "baseline_evidence",
    "affects_acceptance",
    "follow_up",
)
REVIEW_RECEIPT_REQUIRED = (
    "receipt_version",
    "kind",
    "item_id",
    "subject_sha",
    "verdict",
    "findings",
    "evidence",
)
# The authorization block: required only on verdict=pass, the receipt that
# authorizes collect. Findings-carrier receipts stay small.
REVIEW_RECEIPT_PASS_REQUIRED = (
    "reviewer_agent_id",
    "profile_requested",
    "profile_effective",
    "review_kind",
    "checkout_detached",
    "checkout_clean",
    "checkout_head",
)
REVIEW_RECEIPT_FIELDS = (
    set(REVIEW_RECEIPT_REQUIRED)
    | set(REVIEW_RECEIPT_PASS_REQUIRED)
    | {"subject_tree", "details"}
)
SCOPE_MANIFEST_VERSION = 1
SCOPE_REQUIRED = ("scope_version", "item_id", "owned_paths")
SCOPE_FIELDS = set(SCOPE_REQUIRED) | {
    "excluded_paths",
    "shared_read_only_paths",
    "details",
}
GATE_RUN_VERSION = 1
GATE_RUN_TEST_STATUSES = ("passed", "failed", "error", "skipped", "blocked")
GATE_RUN_REQUIRED = ("run_version", "subject_sha", "command", "results")
GATE_RUN_FIELDS = set(GATE_RUN_REQUIRED) | {"details"}
LANDING_VERSION = 1
LANDING_POLICIES = (
    "validate-only",
    "land-with-confirmation",
    "commit-authorized",
    "publish-authorized",
)
LANDING_REQUIRED = ("landing_version", "task_id", "policy", "target_ref")
LANDING_FIELDS = set(LANDING_REQUIRED) | {"details"}
DISPATCH_SECTIONS = (
    "Authority",
    "Acceptance",
    "Non-goals",
    "Write scope",
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


def version_pin_path(root: Path) -> Path:
    return common_repo_root(root) / ".agent_state" / "orchestrate" / "version-pin.json"


def read_version_pin(root: Path) -> dict[str, Any] | None:
    path = version_pin_path(root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise OrchestrateError(f"cannot read version pin: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(
        payload.get("skill_version"), int
    ):
        raise OrchestrateError(f"invalid version pin: {path}")
    return payload


def check_version_pin(root: Path, current_version: int) -> dict[str, Any] | None:
    """Fail fast when the installed skill moved past the task's pinned release."""
    pin = read_version_pin(root)
    if pin is None:
        return None
    pinned = pin["skill_version"]
    if pinned != current_version:
        raise OrchestrateError(
            f"task is pinned to orchestrate v{pinned} but the installed skill is"
            f" v{current_version}: adopt the release at a safe boundary with"
            " `orchestrate pin migrate --root <repo>`, then rerun"
        )
    return {"pinned_version": pinned}


def write_version_pin(root: Path, version: int, compat: Any) -> Path:
    path = version_pin_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pin_version": 1,
        "skill_version": version,
        "orchestrate_compat": compat,
        "pinned_at": datetime.now(UTC).isoformat(),
    }
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        temp_name = handle.name
    os.replace(temp_name, path)
    return path


def require_verified_release(skill_dir: Path) -> dict[str, Any]:
    result = verify_release(skill_dir)
    if not result["ok"]:
        raise OrchestrateError(
            "release preflight failed: " + "; ".join(result["errors"])
        )
    return result


def command_pin_status(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    current = skill_version(Path(args.skill_dir))
    pin = read_version_pin(root)
    return {
        "ok": True,
        "operation": "pin-status",
        "read_only": True,
        "current_version": current,
        "pinned_version": pin["skill_version"] if pin else None,
        "aligned": bool(pin) and pin["skill_version"] == current,
        "pin_path": str(version_pin_path(root)),
    }


def command_pin_set(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    result = require_verified_release(Path(args.skill_dir))
    pin = read_version_pin(root)
    if pin is not None:
        if pin["skill_version"] == result["skill_version"]:
            return {
                "ok": True,
                "operation": "pin-set",
                "recovered": "already-pinned",
                "pinned_version": pin["skill_version"],
            }
        raise OrchestrateError(
            f"task is already pinned to v{pin['skill_version']}; adopt"
            f" v{result['skill_version']} with `pin migrate` instead"
        )
    path = write_version_pin(
        root, result["skill_version"], result["orchestrate_compat"]
    )
    return {
        "ok": True,
        "operation": "pin-set",
        "pinned_version": result["skill_version"],
        "pin_path": str(path),
    }


def command_pin_migrate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    skill_dir = Path(args.skill_dir)
    result = require_verified_release(skill_dir)
    pin = read_version_pin(root)
    if pin is None:
        raise OrchestrateError("no version pin to migrate; use `pin set` first")
    old_version = pin["skill_version"]
    new_version = result["skill_version"]
    if old_version == new_version:
        return {
            "ok": True,
            "operation": "pin-migrate",
            "recovered": "already-current",
            "pinned_version": old_version,
        }
    delta: dict[str, Any] | None
    try:
        delta = compare_manifests(
            load_manifest(skill_dir, old_version),
            load_manifest(skill_dir, new_version),
        )
    except OrchestrateError:
        delta = None
    write_version_pin(root, new_version, result["orchestrate_compat"])
    return {
        "ok": True,
        "operation": "pin-migrate",
        "from_version": old_version,
        "to_version": new_version,
        "delta": delta,
        "delta_note": (
            None
            if delta is not None
            else f"manifest for v{old_version} unavailable; reread all documents"
        ),
    }


def require_release_preflight(
    skill_dir: Path, root: str | None = None
) -> dict[str, Any]:
    result = require_verified_release(skill_dir)
    payload = {
        "skill_version": result["skill_version"],
        "orchestrate_compat": result["orchestrate_compat"],
    }
    if root is not None:
        pin_info = check_version_pin(Path(root).resolve(), result["skill_version"])
        if pin_info is not None:
            payload.update(pin_info)
    return payload


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
    """Core is three fields; state derives from outcome, the rest is optional."""
    errors: list[str] = []
    require_json_fields(payload, ("item_id", "outcome", "evidence"), errors)
    unexpected = sorted(payload.keys() - MILESTONE_FIELDS)
    if unexpected:
        errors.append(f"unexpected fields: {', '.join(unexpected)}")
    if "event" in payload and payload.get("event") != "milestone":
        errors.append("event, when supplied, must be milestone")
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

    outcome = payload.get("outcome")
    if outcome is None:
        return errors
    derived_state = "progress" if outcome == "working" else "terminal"
    if "state" in payload and payload.get("state") != derived_state:
        errors.append(f"outcome={outcome} implies state={derived_state}")
    if derived_state == "terminal":
        if outcome not in MILESTONE_OUTCOMES[role]:
            errors.append(
                f"terminal {role} outcome must be working or one of: "
                + ", ".join(MILESTONE_OUTCOMES[role])
            )
        sha_required = (role == "writer" and outcome in ("validated", "review")) or (
            role == "reviewer" and outcome in ("pass", "needs_fix")
        )
        if sha_required and "subject_sha" not in payload:
            errors.append(f"{role} outcome={outcome} requires subject_sha")
        if outcome == "needs_fix" and not payload.get("findings"):
            errors.append("outcome=needs_fix requires at least one finding id")
    return errors


def require_nonempty_string_fields(
    payload: dict[str, Any], fields: Sequence[str], errors: list[str]
) -> None:
    for field in fields:
        value = payload.get(field)
        if field in payload and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{field} must be a non-empty string")


def validate_review_receipt(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require_json_fields(payload, REVIEW_RECEIPT_REQUIRED, errors)
    unexpected = sorted(payload.keys() - REVIEW_RECEIPT_FIELDS)
    if unexpected:
        errors.append(f"unexpected fields: {', '.join(unexpected)}")
    if payload.get("receipt_version") != RECEIPT_VERSION:
        errors.append(f"receipt_version must be {RECEIPT_VERSION}")
    if payload.get("kind") != "review":
        errors.append("kind must be review")
    item_id = payload.get("item_id")
    if item_id is not None and (
        not isinstance(item_id, str) or not ID_PATTERN.fullmatch(item_id)
    ):
        errors.append("item_id must be a stable identifier")
    validate_exact_sha_field(payload, "subject_sha", errors)
    validate_exact_sha_field(payload, "subject_tree", errors)
    validate_exact_sha_field(payload, "checkout_head", errors)
    require_nonempty_string_fields(
        payload,
        ("reviewer_agent_id", "profile_requested", "profile_effective", "evidence"),
        errors,
    )
    validate_json_enum(payload, "review_kind", COLLECT_REVIEW_KINDS, errors)
    validate_json_enum(payload, "verdict", MILESTONE_OUTCOMES["reviewer"], errors)
    findings = payload.get("findings")
    if findings is not None and (
        not isinstance(findings, list)
        or any(not isinstance(item, str) or not item.strip() for item in findings)
    ):
        errors.append("findings must be a list of non-empty ids")
    for field in ("checkout_detached", "checkout_clean"):
        if field in payload and not isinstance(payload[field], bool):
            errors.append(f"{field} must be a boolean")
    details = payload.get("details")
    if details is not None and not isinstance(details, dict):
        errors.append("details must be an object when supplied")
    verdict = payload.get("verdict")
    if verdict == "pass":
        require_json_fields(payload, REVIEW_RECEIPT_PASS_REQUIRED, errors)
        if not (
            payload.get("checkout_detached") is True
            and payload.get("checkout_clean") is True
        ):
            errors.append(
                "verdict=pass requires checkout_detached and checkout_clean"
            )
    if verdict == "needs_fix" and not payload.get("findings"):
        errors.append("verdict=needs_fix requires at least one finding id")
    head = payload.get("checkout_head")
    subject = payload.get("subject_sha")
    if (
        isinstance(head, str)
        and isinstance(subject, str)
        and head.lower() != subject.lower()
    ):
        errors.append("checkout_head must equal subject_sha")
    return errors


def validate_gate_receipt(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require_json_fields(payload, GATE_RECEIPT_REQUIRED, errors)
    unexpected = sorted(payload.keys() - GATE_RECEIPT_FIELDS)
    if unexpected:
        errors.append(f"unexpected fields: {', '.join(unexpected)}")
    if payload.get("receipt_version") != RECEIPT_VERSION:
        errors.append(f"receipt_version must be {RECEIPT_VERSION}")
    if payload.get("kind") != "gate":
        errors.append("kind must be gate")
    item_id = payload.get("item_id")
    if item_id is not None and (
        not isinstance(item_id, str) or not ID_PATTERN.fullmatch(item_id)
    ):
        errors.append("item_id must be a stable identifier")
    validate_exact_sha_field(payload, "subject_sha", errors)
    validate_exact_sha_field(payload, "subject_tree", errors)
    require_nonempty_string_fields(payload, ("command",), errors)
    validate_json_enum(payload, "status", GATE_STATUSES, errors)
    exclusions = payload.get("exclusions")
    if exclusions is not None and not isinstance(exclusions, list):
        errors.append("exclusions must be a list")
        exclusions = []
    affects_acceptance = False
    for index, exclusion in enumerate(exclusions or []):
        if not isinstance(exclusion, dict):
            errors.append(f"exclusions[{index}] must be an object")
            continue
        missing = sorted(set(GATE_EXCLUSION_REQUIRED) - exclusion.keys())
        extra = sorted(exclusion.keys() - set(GATE_EXCLUSION_REQUIRED))
        if missing:
            errors.append(f"exclusions[{index}] missing: {', '.join(missing)}")
        if extra:
            errors.append(f"exclusions[{index}] unexpected: {', '.join(extra)}")
        for field in ("test_id", "reason", "baseline_evidence", "follow_up"):
            value = exclusion.get(field)
            if field in exclusion and (
                not isinstance(value, str) or not value.strip()
            ):
                errors.append(f"exclusions[{index}].{field} must be a non-empty string")
        flag = exclusion.get("affects_acceptance")
        if "affects_acceptance" in exclusion and not isinstance(flag, bool):
            errors.append(f"exclusions[{index}].affects_acceptance must be a boolean")
        if flag is True:
            affects_acceptance = True
    if payload.get("status") == "passed" and affects_acceptance:
        errors.append(
            "an exclusion with affects_acceptance=true cannot report status=passed"
        )
    details = payload.get("details")
    if details is not None and not isinstance(details, dict):
        errors.append("details must be an object when supplied")
    return errors


def validate_scope_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require_json_fields(payload, SCOPE_REQUIRED, errors)
    unexpected = sorted(payload.keys() - SCOPE_FIELDS)
    if unexpected:
        errors.append(f"unexpected fields: {', '.join(unexpected)}")
    if payload.get("scope_version") != SCOPE_MANIFEST_VERSION:
        errors.append(f"scope_version must be {SCOPE_MANIFEST_VERSION}")
    item_id = payload.get("item_id")
    if item_id is not None and (
        not isinstance(item_id, str) or not ID_PATTERN.fullmatch(item_id)
    ):
        errors.append("item_id must be a stable identifier")
    for field in ("owned_paths", "excluded_paths", "shared_read_only_paths"):
        value = payload.get(field)
        if field not in payload:
            continue
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            errors.append(f"{field} must be a list of non-empty path patterns")
    owned = payload.get("owned_paths")
    if isinstance(owned, list) and not owned:
        errors.append("owned_paths must name at least one pattern")
    details = payload.get("details")
    if details is not None and not isinstance(details, dict):
        errors.append("details must be an object when supplied")
    return errors


def scope_pattern_match(path: str, pattern: str) -> bool:
    pattern = pattern.rstrip("/")
    if fnmatch.fnmatch(path, pattern):
        return True
    return path.startswith(pattern + "/")


def scope_violations(
    paths: Sequence[str], manifest: dict[str, Any]
) -> list[dict[str, str]]:
    owned = manifest["owned_paths"]
    excluded = manifest.get("excluded_paths") or []
    shared = manifest.get("shared_read_only_paths") or []
    violations: list[dict[str, str]] = []
    for path in paths:
        if any(scope_pattern_match(path, pattern) for pattern in excluded):
            violations.append({"path": path, "reason": "excluded"})
        elif any(scope_pattern_match(path, pattern) for pattern in shared):
            violations.append({"path": path, "reason": "shared-read-only"})
        elif not any(scope_pattern_match(path, pattern) for pattern in owned):
            violations.append({"path": path, "reason": "outside-owned"})
    return violations


def read_scope_manifest(path: str) -> tuple[dict[str, Any], bytes]:
    payload, data = read_json_object(path, label="scope manifest")
    errors = validate_scope_manifest(payload)
    if errors:
        raise OrchestrateError("invalid scope manifest: " + "; ".join(errors))
    return payload, data


def validate_gate_run(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require_json_fields(payload, GATE_RUN_REQUIRED, errors)
    unexpected = sorted(payload.keys() - GATE_RUN_FIELDS)
    if unexpected:
        errors.append(f"unexpected fields: {', '.join(unexpected)}")
    if payload.get("run_version") != GATE_RUN_VERSION:
        errors.append(f"run_version must be {GATE_RUN_VERSION}")
    validate_exact_sha_field(payload, "subject_sha", errors)
    require_nonempty_string_fields(payload, ("command",), errors)
    results = payload.get("results")
    if results is not None:
        if not isinstance(results, dict) or not results:
            errors.append("results must be a non-empty object of test_id -> status")
        else:
            if any(
                not isinstance(test_id, str) or not test_id.strip()
                for test_id in results
            ):
                errors.append("results keys must be non-empty test ids")
            invalid = sorted(
                {
                    str(status)
                    for status in results.values()
                    if status not in GATE_RUN_TEST_STATUSES
                }
            )
            if invalid:
                errors.append(
                    "results statuses must be one of "
                    + "|".join(GATE_RUN_TEST_STATUSES)
                    + f"; got: {', '.join(invalid[:5])}"
                )
    details = payload.get("details")
    if details is not None and not isinstance(details, dict):
        errors.append("details must be an object when supplied")
    return errors


def read_gate_run(path: str, *, label: str) -> tuple[dict[str, Any], bytes]:
    payload, data = read_json_object(path, label=label)
    errors = validate_gate_run(payload)
    if errors:
        raise OrchestrateError(f"invalid {label}: " + "; ".join(errors))
    return payload, data


def command_gate_compare(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    item_id = require_identifier(args.item_id, label="item-id")
    baseline, baseline_data = read_gate_run(args.baseline, label="baseline run")
    current, current_data = read_gate_run(args.current, label="current run")
    if baseline["command"] != current["command"]:
        raise OrchestrateError(
            "baseline and current runs used different commands, so the comparison"
            f" is not like-for-like: {baseline['command']!r} vs"
            f" {current['command']!r}"
        )
    failing = {"failed", "error"}
    base_results = baseline["results"]
    cur_results = current["results"]
    regressions: list[str] = []
    baseline_equal: list[str] = []
    blocked: list[str] = []
    skipped: list[str] = []
    fixed: list[str] = []
    for test_id in sorted(cur_results):
        status = cur_results[test_id]
        base_status = base_results.get(test_id)
        if status == "passed":
            if base_status in failing:
                fixed.append(test_id)
        elif status in failing:
            if base_status in failing:
                baseline_equal.append(test_id)
            else:
                regressions.append(test_id)
        elif status == "blocked":
            blocked.append(test_id)
        else:
            skipped.append(test_id)
    missing = sorted(set(base_results) - set(cur_results))
    baseline_sha = baseline["subject_sha"]

    def draft_exclusion(test_id: str, reason: str) -> dict[str, Any]:
        return {
            "test_id": test_id,
            "reason": reason,
            "baseline_evidence": (
                f"baseline {baseline_sha}: {base_results.get(test_id, 'absent')}"
            ),
            "affects_acceptance": True,
            "follow_up": (
                "root: classify this exclusion and set affects_acceptance"
            ),
        }

    exclusions = (
        [
            draft_exclusion(
                test_id,
                f"{cur_results[test_id]} in current run and already failing at"
                " the baseline",
            )
            for test_id in baseline_equal
        ]
        + [
            draft_exclusion(test_id, "environment blocked in current run")
            for test_id in blocked
        ]
        + [
            draft_exclusion(test_id, "skipped in current run")
            for test_id in skipped
        ]
        + [
            draft_exclusion(
                test_id,
                "present at baseline but missing from current run"
                " (silent deselection)",
            )
            for test_id in missing
        ]
    )
    if regressions:
        status = "failed_current"
    elif blocked:
        status = "environment_blocked"
    elif baseline_equal:
        status = "failed_baseline"
    elif exclusions:
        status = "unverified"
    else:
        status = "passed"
    draft = {
        "receipt_version": RECEIPT_VERSION,
        "kind": "gate",
        "item_id": item_id,
        "subject_sha": current["subject_sha"],
        "command": current["command"],
        "status": status,
        "exclusions": exclusions,
        "details": {
            "baseline_sha": baseline_sha,
            "baseline_run_sha256": sha256_bytes(baseline_data),
            "current_run_sha256": sha256_bytes(current_data),
            "regressions": regressions,
            "fixed": fixed,
        },
    }
    draft_errors = validate_gate_receipt(draft)
    result: dict[str, Any] = {
        "ok": not draft_errors,
        "operation": "gate-compare",
        "read_only": not args.output,
        "item_id": item_id,
        "baseline_sha": baseline_sha,
        "current_sha": current["subject_sha"],
        "command": current["command"],
        "status": status,
        "counts": {
            "current_total": len(cur_results),
            "regressions": len(regressions),
            "baseline_equal_failures": len(baseline_equal),
            "environment_blocked": len(blocked),
            "skipped": len(skipped),
            "missing_in_current": len(missing),
            "fixed": len(fixed),
        },
        "regressions": regressions,
        "baseline_equal_failures": baseline_equal,
        "environment_blocked": blocked,
        "skipped": skipped,
        "missing_in_current": missing,
        "fixed": fixed,
        "receipt_draft": draft,
        "draft_errors": draft_errors,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    if args.output:
        output = Path(args.output).resolve()
        if output.exists():
            raise OrchestrateError(
                f"output already exists: {output}; a possibly edited receipt is"
                " never overwritten — remove it explicitly first"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result["draft_written"] = str(output)
    return result


def validate_landing_declaration(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require_json_fields(payload, LANDING_REQUIRED, errors)
    unexpected = sorted(payload.keys() - LANDING_FIELDS)
    if unexpected:
        errors.append(f"unexpected fields: {', '.join(unexpected)}")
    if payload.get("landing_version") != LANDING_VERSION:
        errors.append(f"landing_version must be {LANDING_VERSION}")
    task_id = payload.get("task_id")
    if task_id is not None and (
        not isinstance(task_id, str) or not ID_PATTERN.fullmatch(task_id)
    ):
        errors.append("task_id must be a stable identifier")
    validate_json_enum(payload, "policy", LANDING_POLICIES, errors)
    target = payload.get("target_ref")
    if target is not None and (
        not isinstance(target, str)
        or not target.strip()
        or target.startswith(("task/", "agent/"))
    ):
        errors.append(
            "target_ref must name a persistence branch, never task/ or agent/"
        )
    details = payload.get("details")
    if details is not None and not isinstance(details, dict):
        errors.append("details must be an object when supplied")
    return errors


def read_landing_declaration(path: str) -> tuple[dict[str, Any], bytes]:
    payload, data = read_json_object(path, label="landing declaration")
    errors = validate_landing_declaration(payload)
    if errors:
        raise OrchestrateError("invalid landing declaration: " + "; ".join(errors))
    return payload, data


def changed_paths_since_fork(root: Path, base: str, head: str) -> list[str]:
    fork = run_git(root, "merge-base", base, head).stdout.strip()
    output = run_git(root, "diff", "--name-only", fork, head).stdout
    return [line.strip() for line in output.splitlines() if line.strip()]


def command_scope_amend(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    manifest, data = read_scope_manifest(args.manifest)
    if not args.reason.strip():
        raise OrchestrateError("--reason must be a non-empty explanation")
    added_owned = list(dict.fromkeys(args.add_owned or []))
    added_shared = list(dict.fromkeys(args.add_shared_read_only or []))
    if not added_owned and not added_shared:
        raise OrchestrateError(
            "pass --add-owned and/or --add-shared-read-only; an amendment must"
            " change something"
        )
    excluded = manifest.get("excluded_paths") or []
    for pattern in added_owned:
        if any(scope_pattern_match(pattern, rule) for rule in excluded) or (
            pattern in excluded
        ):
            raise OrchestrateError(
                f"pattern is excluded by the current manifest: {pattern!r};"
                " overriding an exclusion needs a fresh root-written manifest,"
                " not an amendment"
            )
    amended = dict(manifest)
    amended["owned_paths"] = list(
        dict.fromkeys([*manifest["owned_paths"], *added_owned])
    )
    if added_shared:
        amended["shared_read_only_paths"] = list(
            dict.fromkeys(
                [*(manifest.get("shared_read_only_paths") or []), *added_shared]
            )
        )
    details = dict(amended.get("details") or {})
    amendments = list(details.get("amendments") or [])
    amendments.append(
        {
            "previous_manifest_sha256": sha256_bytes(data),
            "added_owned": added_owned,
            "added_shared_read_only": added_shared,
            "reason": args.reason,
        }
    )
    details["amendments"] = amendments
    amended["details"] = details
    errors = validate_scope_manifest(amended)
    if errors:
        raise OrchestrateError("amended manifest is invalid: " + "; ".join(errors))
    output = Path(args.output).resolve()
    if output.exists():
        raise OrchestrateError(
            f"output already exists: {output}; amendments never overwrite —"
            " each proposal is its own file"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(amended, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    output.write_text(serialized, encoding="utf-8")
    return {
        "ok": True,
        "operation": "scope-amend",
        "item_id": manifest["item_id"],
        "previous_manifest_sha256": sha256_bytes(data),
        "amended_manifest": str(output),
        "amended_manifest_sha256": sha256_bytes(serialized.encode()),
        "added_owned": added_owned,
        "added_shared_read_only": added_shared,
        "reason": args.reason,
        "amendment_count": len(amendments),
        "approval": (
            "proposal only: root approves by passing the amended manifest to"
            " scope check / collect --scope"
        ),
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_scope_lint(args: argparse.Namespace) -> dict[str, Any]:
    payload, data = read_json_object(args.input, label="scope manifest")
    errors = validate_scope_manifest(payload)
    return {
        "ok": not errors,
        "operation": "scope-lint",
        "input_sha256": sha256_bytes(data),
        "errors": errors,
    }


def command_scope_check(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    manifest, data = read_scope_manifest(args.manifest)
    base = exact_commit(root, args.base, label="base")
    head = exact_commit(root, args.head, label="head")
    changed = changed_paths_since_fork(root, base, head)
    violations = scope_violations(changed, manifest)
    return {
        "ok": not violations,
        "operation": "scope-check",
        "read_only": True,
        "item_id": manifest["item_id"],
        "manifest_sha256": sha256_bytes(data),
        "base": base,
        "head": head,
        "changed_paths": changed,
        "violations": violations,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_receipt_lint(args: argparse.Namespace) -> dict[str, Any]:
    payload, data = read_json_object(args.input, label="receipt")
    kind = args.kind or payload.get("kind")
    if kind not in RECEIPT_KINDS:
        raise OrchestrateError(
            f"receipt kind must be one of {'|'.join(RECEIPT_KINDS)};"
            f" the file declares {payload.get('kind')!r}"
        )
    if kind == "review":
        errors = validate_review_receipt(payload)
    else:
        errors = validate_gate_receipt(payload)
    return {
        "ok": not errors,
        "operation": "receipt-lint",
        "kind": kind,
        "input_sha256": sha256_bytes(data),
        "errors": errors,
    }


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
    missing = sorted(QUEUE_REQUIRED - fields.keys())
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
    if fields.get("hard_critical_axes", "none") != "none":
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


SEAM_READY_PATTERN = re.compile(r"^Seam-Ready:\s*true\s*$", re.IGNORECASE | re.MULTILINE)


def lane_absorption(root: Path, lane_sha: str, task_sha: str) -> str | None:
    if (
        run_git(
            root, "merge-base", "--is-ancestor", lane_sha, task_sha, check=False
        ).returncode
        == 0
    ):
        return "ancestor"
    if run_git(root, "diff", "--quiet", lane_sha, task_sha, check=False).returncode == 0:
        return "tree-identity"
    return None


def worktree_metadata_writability_preflight(root: Path) -> None:
    # A sandbox that can delete the directory but not .git/worktrees leaves
    # half-removed state; refuse before any mutation.
    metadata_dir = (
        root / run_git(root, "rev-parse", "--git-common-dir").stdout.strip()
    ).resolve() / "worktrees"
    if metadata_dir.exists() and not os.access(metadata_dir, os.W_OK):
        raise OrchestrateError(
            f"worktree metadata is not writable: {metadata_dir}; grant write"
            " access before cleanup — nothing was removed"
        )


def command_lane_create(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    lane = require_identifier(args.lane, label="lane")
    base = exact_commit(root, args.base, label="base")
    branch = f"agent/{task_id}/{lane}"
    target = require_managed_worktree(
        root,
        (
            Path(args.worktree).resolve()
            if args.worktree
            else managed_worktree_root(root) / f"{task_id}-{lane}"
        ),
        kind="lane",
    )
    branch_exists = (
        run_git(
            root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False
        ).returncode
        == 0
    )
    record = next(
        (
            record
            for record in worktree_records(root)
            if record.get("branch") == f"refs/heads/{branch}"
        ),
        None,
    )
    if record is not None:
        # A prior run completed; rerunning after an abort reports instead of failing.
        existing = Path(str(record.get("worktree"))).resolve()
        if existing != target:
            raise OrchestrateError(
                f"lane branch is already checked out elsewhere: {existing}"
            )
        return {
            "ok": True,
            "operation": "lane-create",
            "base": base,
            "recovered": "already-created",
            **worktree_evidence(target, started=started),
        }
    if target.exists():
        raise OrchestrateError(f"worktree path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists:
        # Branch landed but the worktree add aborted: reuse it only at the exact base.
        head = run_git(root, "rev-parse", f"refs/heads/{branch}").stdout.strip()
        if head != base:
            raise OrchestrateError(
                f"lane branch already exists at {head}, not the requested base"
            )
        run_git(root, "worktree", "add", str(target), branch)
        return {
            "ok": True,
            "operation": "lane-create",
            "base": base,
            "recovered": "reused-existing-branch",
            **worktree_evidence(target, started=started),
        }
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
    expected_receipt = (
        common_repo_root(root)
        / ".agent_state"
        / "orchestrate"
        / "receipts"
        / f"review-{label}.json"
    )
    return {
        "ok": True,
        "operation": "review-checkout",
        "subject_sha": target_sha,
        "expected_receipt": str(expected_receipt),
        **evidence,
    }


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


def command_review_verdict(args: argparse.Namespace) -> dict[str, Any]:
    payload, data = read_json_object(args.receipt, label="review receipt")
    errors = validate_review_receipt(payload)
    if not errors and args.subject_sha:
        if not EXACT_SHA_PATTERN.fullmatch(args.subject_sha):
            raise OrchestrateError(
                "subject-sha must be an exact hexadecimal commit SHA"
            )
        if payload["subject_sha"].lower() != args.subject_sha.lower():
            errors.append(
                f"receipt binds {payload['subject_sha']}, not the expected subject"
                f" {args.subject_sha}"
            )
    receipt_path = str(Path(args.receipt).resolve()) if args.receipt != "-" else "-"
    result: dict[str, Any] = {
        "ok": not errors,
        "operation": "review-verdict",
        "read_only": True,
        "receipt": receipt_path,
        "receipt_sha256": sha256_bytes(data),
        "errors": errors,
    }
    if errors:
        result["next_action"] = "unusable-evidence"
        return result
    verdict = payload["verdict"]
    result.update(
        item_id=payload["item_id"],
        subject_sha=payload["subject_sha"],
        review_kind=payload.get("review_kind"),
        verdict=verdict,
        findings=payload["findings"],
        authorizes_collect=verdict == "pass",
    )
    if verdict == "pass":
        result["next_action"] = "collect"
        result["collect_hint"] = (
            "collect --integration-worktree <task checkout> --task-ref task/<task>"
            f" --lane-ref <lane> --expected-lane-sha {payload['subject_sha']}"
            f" --receipt {receipt_path}"
        )
    elif verdict == "needs_fix":
        result["next_action"] = "return-findings-to-original-writer"
    else:
        result["next_action"] = "root-adjudication"
    return result


def collect_authorization(args: argparse.Namespace) -> tuple[str, str, dict[str, Any]]:
    """Resolve collect authority from a review receipt or an explicit declaration."""
    if args.receipt:
        if args.authorized_sha or args.review_kind:
            raise OrchestrateError(
                "--receipt replaces --authorized-sha/--review-kind; pass exactly one"
                " authorization source"
            )
        payload, data = read_json_object(args.receipt, label="review receipt")
        errors = validate_review_receipt(payload)
        if errors:
            raise OrchestrateError("invalid review receipt: " + "; ".join(errors))
        if payload["verdict"] != "pass":
            raise OrchestrateError(
                f"review receipt verdict is {payload['verdict']};"
                " only pass authorizes collection"
            )
        return (
            payload["subject_sha"],
            payload["review_kind"],
            {
                "authorization_source": "receipt",
                "receipt_sha256": sha256_bytes(data),
                "receipt_item_id": payload["item_id"],
                "reviewer_agent_id": payload["reviewer_agent_id"],
                "profile_requested": payload["profile_requested"],
                "profile_effective": payload["profile_effective"],
            },
        )
    if not (args.authorized_sha and args.review_kind):
        raise OrchestrateError(
            "collect requires either --receipt or both --authorized-sha and"
            " --review-kind"
        )
    return args.authorized_sha, args.review_kind, {"authorization_source": "declared"}


def command_collect(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    require_task_lane_refs(args.task_ref, args.lane_ref)
    authorized_value, review_kind, authorization = collect_authorization(args)
    expected = exact_commit(root, args.expected_lane_sha, label="expected lane SHA")
    authorized = exact_commit(root, authorized_value, label="authorized SHA")
    if expected != authorized:
        raise OrchestrateError("authorized SHA differs from expected lane SHA")
    task_head = run_git(root, "rev-parse", f"{args.task_ref}^{{commit}}").stdout.strip()
    if (
        run_git(
            root, "merge-base", "--is-ancestor", expected, task_head, check=False
        ).returncode
        == 0
    ):
        # A prior run merged this exact SHA; rerunning after an abort reports it.
        return {
            "ok": True,
            "operation": "collect",
            "recovered": "already-collected",
            "task_ref": args.task_ref,
            "lane_ref": args.lane_ref,
            "authorized_sha": authorized,
            "declared_review_kind": review_kind,
            "verdict_inferred": False,
            **authorization,
            "task_sha": task_head,
            "observed_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    git_dir = Path(run_git(root, "rev-parse", "--absolute-git-dir").stdout.strip())
    if (git_dir / "MERGE_HEAD").exists():
        raise OrchestrateError(
            "unfinished merge in progress: resolve it or run `git merge --abort`,"
            " then rerun collect"
        )
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
    scope_evidence: dict[str, Any] = {}
    if args.scope:
        manifest, manifest_data = read_scope_manifest(args.scope)
        changed = changed_paths_since_fork(root, task_head, expected)
        violations = scope_violations(changed, manifest)
        if violations:
            raise OrchestrateError(
                "lane writes leave the declared scope: "
                + ", ".join(
                    f"{item['path']} ({item['reason']})" for item in violations[:20]
                )
            )
        scope_evidence = {
            "scope_item_id": manifest["item_id"],
            "scope_manifest_sha256": sha256_bytes(manifest_data),
            "scope_changed_paths": len(changed),
        }
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
        "declared_review_kind": review_kind,
        "verdict_inferred": False,
        **authorization,
        **scope_evidence,
        "before": before,
        "preflight_tree": merge_tree,
        **evidence,
    }


def landing_task_id(task_ref: str, declaration: dict[str, Any]) -> str:
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    task_id = task_ref.split("/", 1)[1]
    if task_id != declaration["task_id"]:
        raise OrchestrateError(
            f"declaration task_id is {declaration['task_id']!r},"
            f" but --task-ref names {task_id!r}"
        )
    return task_id


def landing_checkout_dirt(root: Path) -> tuple[list[str], list[str]]:
    """Split porcelain status into staged paths and user-owned dirty paths."""
    staged: list[str] = []
    dirty: list[str] = []
    for line in run_git(root, "status", "--porcelain").stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(" -> ")[-1].strip()
        if line[0] not in " ?":
            staged.append(path)
        else:
            dirty.append(path)
    return staged, dirty


def landing_gate_state(
    gate_receipt: str | None, task_sha: str
) -> dict[str, Any]:
    if not gate_receipt:
        return {
            "state": "missing",
            "hint": "write a gate receipt for the final gate bound to the task head",
        }
    payload, data = read_json_object(gate_receipt, label="gate receipt")
    errors = validate_gate_receipt(payload)
    if errors:
        return {"state": "invalid", "errors": errors}
    bound = payload["subject_sha"].lower() == task_sha.lower()
    if not bound:
        state = "stale-subject"
    elif payload["status"] == "passed":
        state = "passed"
    else:
        state = payload["status"]
    return {
        "state": state,
        "status": payload["status"],
        "subject_sha": payload["subject_sha"],
        "receipt_sha256": sha256_bytes(data),
    }


_HELD_LOCKS: list[Any] = []


def acquire_landing_lock(root: Path) -> None:
    """Serialize the landing critical section within this repo, non-blocking.

    The handle is held until process exit so the flock outlives this frame.
    """
    lock_path = common_repo_root(root) / ".agent_state" / "orchestrate" / "land.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise OrchestrateError(
            f"another landing holds the lock: {lock_path}; wait for it to finish"
        ) from exc
    _HELD_LOCKS.append(handle)


def command_land_status(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    declaration, decl_data = read_landing_declaration(args.declaration)
    task_id = landing_task_id(args.task_ref, declaration)
    policy = declaration["policy"]
    target_ref = declaration["target_ref"]
    task_sha = run_git(root, "rev-parse", f"{args.task_ref}^{{commit}}").stdout.strip()
    target_sha = run_git(root, "rev-parse", f"{target_ref}^{{commit}}").stdout.strip()
    gate = landing_gate_state(args.gate_receipt, task_sha)
    branch = run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    on_target = branch.returncode == 0 and branch.stdout.strip() == target_ref
    staged, dirty = landing_checkout_dirt(root)
    changed = [
        line.strip()
        for line in run_git(
            root, "diff", "--name-only", target_sha, task_sha
        ).stdout.splitlines()
        if line.strip()
    ]
    dirty_overlap = sorted(set(dirty) & set(changed))
    landed = (
        run_git(root, "diff", "--quiet", task_sha, target_sha, check=False).returncode
        == 0
    )
    based = (
        run_git(
            root, "merge-base", "--is-ancestor", target_sha, task_sha, check=False
        ).returncode
        == 0
    )
    lanes = [
        line.strip()
        for line in run_git(
            root,
            "for-each-ref",
            "--format=%(refname:short)",
            f"refs/heads/agent/{task_id}/",
        ).stdout.splitlines()
        if line.strip()
    ]
    authority_state = (
        "forbidden"
        if policy == "validate-only"
        else "requires-user-confirmation"
        if policy == "land-with-confirmation"
        else "authorized"
    )
    steps = {
        "final_gate": gate,
        "landing_authority": {"policy": policy, "state": authority_state},
        "landing_lock": {
            "state": "built-in",
            "hint": (
                "land finish takes the landing lock itself; the merge-slot"
                " protocol (scripts/merge_slot.py) is only for concurrent roots"
            ),
        },
        "squash_landing": {
            "state": "done" if landed else "pending",
            "based_on_target": based,
            "on_target_checkout": on_target,
            "staged_paths": staged,
            "dirty_overlap": dirty_overlap,
        },
        "tree_identity": {"state": "proved" if landed else "pending"},
        "lane_cleanup": {
            "state": "done" if not lanes else "pending",
            "remaining_lanes": lanes,
        },
    }
    if policy == "validate-only":
        next_step = (
            "policy is validate-only: report the validated task branch; landing"
            " needs a new user-authorized declaration"
        )
    elif landed and lanes:
        next_step = "cleanup --absorbed, then delete the task branch"
    elif landed:
        next_step = "delete the task branch (tree identity already holds)"
    elif gate["state"] != "passed":
        next_step = "final gate: produce a passed gate receipt bound to the task head"
    elif not based:
        next_step = "rebase the task onto the target tip, rerun the gate"
    else:
        next_step = "land finish"
    return {
        "ok": True,
        "operation": "land-status",
        "read_only": True,
        "task_ref": args.task_ref,
        "target_ref": target_ref,
        "policy": policy,
        "task_sha": task_sha,
        "target_sha": target_sha,
        "declaration_sha256": sha256_bytes(decl_data),
        "steps": steps,
        "next": next_step,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_land_finish(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    declaration, decl_data = read_landing_declaration(args.declaration)
    task_id = landing_task_id(args.task_ref, declaration)
    policy = declaration["policy"]
    if policy == "validate-only":
        raise OrchestrateError(
            "declared landing policy is validate-only: landing is out of contract;"
            " get user authority and write a new declaration first"
        )
    if policy == "land-with-confirmation" and not args.confirmed:
        raise OrchestrateError(
            "policy land-with-confirmation requires --confirmed after an explicit"
            " user confirmation for this landing"
        )
    target_ref = declaration["target_ref"]
    expected = exact_commit(root, args.task_sha, label="task SHA")
    task_head = run_git(root, "rev-parse", f"{args.task_ref}^{{commit}}").stdout.strip()
    if task_head != expected:
        raise OrchestrateError(f"task head drifted: {task_head} != {expected}")
    gate = landing_gate_state(args.gate_receipt, expected)
    if gate["state"] != "passed":
        raise OrchestrateError(
            f"gate receipt state is {gate['state']}"
            + ("; " + "; ".join(gate["errors"]) if "errors" in gate else "")
            + " — only a passed receipt bound to the task head authorizes landing"
        )
    evidence = {
        "operation": "land-finish",
        "task_ref": args.task_ref,
        "target_ref": target_ref,
        "policy": policy,
        "task_sha": expected,
        "declaration_sha256": sha256_bytes(decl_data),
        "gate_receipt_sha256": gate["receipt_sha256"],
        "merge_slot_held": "declared" if args.merge_slot_held else "not-declared",
    }
    target_sha = run_git(root, "rev-parse", f"{target_ref}^{{commit}}").stdout.strip()
    if (
        run_git(root, "diff", "--quiet", expected, target_sha, check=False).returncode
        == 0
    ):
        return {
            "ok": True,
            "recovered": "already-landed",
            "landed_sha": target_sha,
            "tree_identity": True,
            **evidence,
            "observed_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    git_dir = Path(run_git(root, "rev-parse", "--absolute-git-dir").stdout.strip())
    if (git_dir / "MERGE_HEAD").exists():
        raise OrchestrateError(
            "unfinished merge in progress: resolve it or run `git merge --abort`,"
            " then rerun land finish"
        )
    current_branch = run_git(root, "symbolic-ref", "--short", "HEAD").stdout.strip()
    if current_branch != target_ref:
        raise OrchestrateError(
            f"landing checkout is {current_branch}, expected {target_ref}"
        )
    staged, dirty = landing_checkout_dirt(root)
    if staged:
        raise OrchestrateError(
            "staged changes present in the landing checkout would leak into the"
            " squash commit: " + ", ".join(staged[:20])
        )
    changed = [
        line.strip()
        for line in run_git(
            root, "diff", "--name-only", target_sha, expected
        ).stdout.splitlines()
        if line.strip()
    ]
    dirty_overlap = sorted(set(dirty) & set(changed))
    if dirty_overlap:
        raise OrchestrateError(
            "user-owned dirty paths overlap the landing diff: "
            + ", ".join(dirty_overlap[:20])
        )
    acquire_landing_lock(root)
    target_sha = run_git(root, "rev-parse", f"{target_ref}^{{commit}}").stdout.strip()
    if (
        run_git(
            root, "merge-base", "--is-ancestor", target_sha, expected, check=False
        ).returncode
        != 0
    ):
        raise OrchestrateError(
            "task head is not based on the current target tip: rebase off-slot,"
            " rerun the final gate on the new tree, then rerun land finish"
        )
    message = args.message or f"land {task_id}: squash of {expected[:12]}"
    run_git(root, "merge", "--squash", args.task_ref)
    run_git(root, "commit", "-m", message)
    landed = run_git(root, "rev-parse", "HEAD").stdout.strip()
    if (
        run_git(root, "diff", "--quiet", expected, landed, check=False).returncode
        != 0
    ):
        raise OrchestrateError(
            f"tree identity proof failed after squash: {expected} vs {landed};"
            " do not delete the task branch — investigate"
        )
    next_steps = [
        "cleanup --absorbed to sweep lanes and review checkouts",
        f"git branch -D {args.task_ref} (authorized by this tree identity proof)",
    ]
    if args.merge_slot_held:
        next_steps.insert(0, "release the merge slot with the owner token")
    if policy == "publish-authorized":
        next_steps.append(f"git push <remote> {target_ref}")
    return {
        "ok": True,
        "landed_sha": landed,
        "tree_identity": True,
        "message": message,
        "next": next_steps,
        **evidence,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def cleanup_single_worktree(
    args: argparse.Namespace, root: Path, started: float
) -> dict[str, Any]:
    target = require_managed_worktree(root, Path(args.worktree).resolve(), kind="any")
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
        "operation": "cleanup",
        "path": str(target),
    }
    if record is None:
        if target.exists():
            raise OrchestrateError(f"not a registered worktree: {target}")
        result["recovered"] = "already-removed"
    else:
        worktree_metadata_writability_preflight(root)
        if not target.exists():
            run_git(root, "worktree", "prune")
            result["recovered"] = "pruned-stale-metadata"
        elif "detached" in record:
            result["kind"] = "review"
            if run_git(target, "status", "--porcelain").stdout.strip():
                raise OrchestrateError("review worktree is dirty")
            head = run_git(target, "rev-parse", "HEAD").stdout.strip()
            if args.subject_sha:
                subject = exact_commit(root, args.subject_sha, label="subject SHA")
                if head != subject:
                    raise OrchestrateError(
                        f"review checkout HEAD drifted: {head} != {subject};"
                        " evidence bound to that SHA is void — investigate before"
                        " removing manually"
                    )
            result["head"] = head
            run_git(root, "worktree", "remove", str(target))
        else:
            result["kind"] = "lane"
            branch = str(record.get("branch", "")).removeprefix("refs/heads/")
            match = re.fullmatch(r"agent/([^/]+)/[^/]+", branch)
            if match is None:
                raise OrchestrateError(f"not an agent lane branch: {branch!r}")
            task_ref = f"task/{match.group(1)}"
            if run_git(target, "status", "--porcelain").stdout.strip():
                raise OrchestrateError("lane worktree is dirty")
            lane_sha = run_git(root, "rev-parse", f"{branch}^{{commit}}").stdout.strip()
            task_sha = run_git(
                root, "rev-parse", f"{task_ref}^{{commit}}"
            ).stdout.strip()
            absorption = lane_absorption(root, lane_sha, task_sha)
            if absorption is None:
                raise OrchestrateError(
                    f"lane is not absorbed by {task_ref} (ancestry or tree identity)"
                )
            run_git(root, "worktree", "remove", str(target))
            run_git(root, "branch", "-D", branch)
            result.update(
                branch=branch,
                lane_sha=lane_sha,
                task_ref=task_ref,
                absorption=absorption,
            )
    return {
        **result,
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def command_cleanup_absorbed(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    if args.worktree:
        return cleanup_single_worktree(args, root, started)
    if not args.absorbed:
        raise OrchestrateError(
            "pass --worktree for one target or --absorbed to authorize the sweep"
        )
    if not args.dry_run:
        worktree_metadata_writability_preflight(root)
    managed = managed_worktree_root(root).resolve()
    entries: list[dict[str, Any]] = []
    for record in worktree_records(root):
        raw = record.get("worktree")
        if not isinstance(raw, str):
            continue
        path = Path(raw)
        try:
            relative = path.resolve().relative_to(managed)
        except ValueError:
            continue
        if len(relative.parts) != 1:
            continue
        entry: dict[str, Any] = {"path": str(path)}
        entries.append(entry)
        if "detached" in record:
            entry["kind"] = "review"
            if not path.exists():
                entry.update(
                    action="rejected",
                    reason="directory missing; run cleanup --worktree to prune metadata",
                )
            elif run_git(path, "status", "--porcelain").stdout.strip():
                entry.update(action="rejected", reason="worktree is dirty")
            else:
                entry["head"] = run_git(path, "rev-parse", "HEAD").stdout.strip()
                if args.dry_run:
                    entry["action"] = "eligible"
                else:
                    run_git(root, "worktree", "remove", str(path))
                    entry["action"] = "removed"
            continue
        branch = str(record.get("branch", "")).removeprefix("refs/heads/")
        entry["kind"] = "lane"
        entry["branch"] = branch
        match = re.fullmatch(r"agent/([^/]+)/[^/]+", branch)
        if match is None:
            entry.update(action="rejected", reason="not an agent lane branch")
            continue
        task_ref = f"task/{match.group(1)}"
        if (
            run_git(
                root,
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{task_ref}",
                check=False,
            ).returncode
            != 0
        ):
            entry.update(
                action="rejected", reason=f"missing integration branch {task_ref}"
            )
            continue
        if not path.exists():
            entry.update(
                action="rejected",
                reason="directory missing; run cleanup --worktree to recover",
            )
            continue
        if run_git(path, "status", "--porcelain").stdout.strip():
            entry.update(action="rejected", reason="worktree is dirty")
            continue
        lane_sha = run_git(root, "rev-parse", f"{branch}^{{commit}}").stdout.strip()
        task_sha = run_git(root, "rev-parse", f"{task_ref}^{{commit}}").stdout.strip()
        absorption = lane_absorption(root, lane_sha, task_sha)
        if absorption is None:
            entry.update(action="rejected", reason=f"not absorbed by {task_ref}")
            continue
        entry.update(lane_sha=lane_sha, task_ref=task_ref, absorption=absorption)
        if args.dry_run:
            entry["action"] = "eligible"
        else:
            run_git(root, "worktree", "remove", str(path))
            run_git(root, "branch", "-D", branch)
            entry["action"] = "removed"
    return {
        "ok": True,
        "operation": "cleanup-absorbed",
        "dry_run": bool(args.dry_run),
        "entries": entries,
        "removed": sum(1 for entry in entries if entry.get("action") == "removed"),
        "rejected": sum(1 for entry in entries if entry.get("action") == "rejected"),
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def load_review_receipts(
    directory: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    by_sha: dict[str, dict[str, Any]] = {}
    invalid: list[str] = []
    if not directory.is_dir():
        return by_sha, invalid
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError):
            invalid.append(str(path))
            continue
        if not isinstance(payload, dict) or payload.get("kind") != "review":
            continue
        if validate_review_receipt(payload):
            invalid.append(str(path))
            continue
        by_sha[payload["subject_sha"].lower()] = {
            "path": str(path),
            "item_id": payload["item_id"],
            "review_kind": payload.get("review_kind"),
            "verdict": payload["verdict"],
        }
    return by_sha, invalid


def command_slice_status(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_ref = args.task_ref
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    task_id = require_identifier(task_ref.split("/", 1)[1], label="task ref id")
    task_sha = run_git(root, "rev-parse", f"{task_ref}^{{commit}}").stdout.strip()
    receipts_dir = (
        Path(args.receipts_dir).resolve()
        if args.receipts_dir
        else common_repo_root(root) / ".agent_state" / "orchestrate" / "receipts"
    )
    receipts, invalid = load_review_receipts(receipts_dir)
    worktrees = {
        str(record.get("branch", "")).removeprefix("refs/heads/"): record
        for record in worktree_records(root)
        if isinstance(record.get("branch"), str)
    }
    lanes: list[dict[str, Any]] = []
    lane_changed: dict[str, set[str]] = {}
    refs = run_git(
        root,
        "for-each-ref",
        "--format=%(refname:short) %(objectname)",
        f"refs/heads/agent/{task_id}/",
    ).stdout
    for line in refs.splitlines():
        branch, _, head = line.strip().partition(" ")
        entry: dict[str, Any] = {"lane_ref": branch, "head": head}
        record = worktrees.get(branch)
        if record is not None:
            worktree_path = Path(str(record.get("worktree")))
            entry["worktree"] = str(worktree_path)
            entry["dirty"] = (
                bool(run_git(worktree_path, "status", "--porcelain").stdout.strip())
                if worktree_path.exists()
                else None
            )
        body = run_git(root, "log", "-1", "--format=%B", head).stdout
        entry["seam_ready"] = bool(SEAM_READY_PATTERN.search(body))
        changed = changed_paths_since_fork(root, task_sha, head)
        entry["changed_path_count"] = len(changed)
        lane_changed[branch] = set(changed)
        absorption = lane_absorption(root, head, task_sha)
        receipt = receipts.get(head.lower())
        if receipt is not None:
            entry["receipt"] = receipt
        if absorption is not None:
            entry["state"] = "absorbed"
            entry["absorption"] = absorption
        elif receipt is not None and receipt["verdict"] == "pass":
            entry["state"] = "authorized_to_collect"
        elif receipt is not None and receipt["verdict"] == "needs_fix":
            entry["state"] = "needs_fix"
        else:
            entry["state"] = "writing"
        lanes.append(entry)
    overlaps: list[dict[str, Any]] = []
    names = sorted(lane_changed)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            shared_paths = sorted(lane_changed[first] & lane_changed[second])
            if shared_paths:
                overlaps.append({"lanes": [first, second], "paths": shared_paths})
    return {
        "ok": True,
        "operation": "slice-status",
        "read_only": True,
        "task_ref": task_ref,
        "task_sha": task_sha,
        "receipts_dir": str(receipts_dir),
        "invalid_receipts": invalid,
        "write_set_overlaps": overlaps,
        "lanes": lanes,
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

    gate = commands.add_parser(
        "gate", help="baseline-relative comparison of two gate run summaries"
    )
    gate_commands = gate.add_subparsers(dest="gate_command", required=True)
    gate_compare = gate_commands.add_parser("compare")
    gate_compare.add_argument(
        "--baseline", required=True, help="baseline gate run summary JSON path"
    )
    gate_compare.add_argument(
        "--current", required=True, help="current gate run summary JSON path"
    )
    gate_compare.add_argument("--item-id", required=True)
    gate_compare.add_argument(
        "--output", help="write the receipt draft here (never overwrites)"
    )
    gate_compare.set_defaults(handler=command_gate_compare)

    receipt = commands.add_parser(
        "receipt", help="lint one hand-written verdict or contract receipt"
    )
    receipt_commands = receipt.add_subparsers(dest="receipt_command", required=True)
    receipt_lint = receipt_commands.add_parser("lint")
    receipt_lint.add_argument(
        "--kind",
        choices=RECEIPT_KINDS,
        help="override; defaults to the receipt's own kind field",
    )
    receipt_lint.add_argument(
        "--input", required=True, help="receipt JSON path, or '-' for stdin"
    )
    receipt_lint.set_defaults(handler=command_receipt_lint)

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
    review_verdict = review_commands.add_parser("verdict")
    review_verdict.add_argument(
        "--receipt", required=True, help="review receipt JSON path, or '-' for stdin"
    )
    review_verdict.add_argument(
        "--subject-sha",
        help="fail when the receipt binds a different subject SHA",
    )
    review_verdict.set_defaults(handler=command_review_verdict)

    land = commands.add_parser(
        "land", help="declared-policy squash landing with tree-identity proof"
    )
    land_commands = land.add_subparsers(dest="land_command", required=True)
    land_status = land_commands.add_parser("status")
    add_root(land_status)
    land_status.add_argument("--task-ref", required=True)
    land_status.add_argument(
        "--declaration", required=True, help="landing declaration JSON path"
    )
    land_status.add_argument("--gate-receipt")
    land_status.set_defaults(handler=command_land_status)
    land_finish = land_commands.add_parser("finish")
    add_root(land_finish)
    land_finish.add_argument("--task-ref", required=True)
    land_finish.add_argument("--task-sha", required=True)
    land_finish.add_argument(
        "--declaration", required=True, help="landing declaration JSON path"
    )
    land_finish.add_argument("--gate-receipt", required=True)
    land_finish.add_argument(
        "--merge-slot-held",
        action="store_true",
        help="declare an external merge-slot claim (concurrent-roots protocol);"
        " the built-in landing lock is always taken",
    )
    land_finish.add_argument(
        "--confirmed",
        action="store_true",
        help="record the explicit user confirmation land-with-confirmation requires",
    )
    land_finish.add_argument("--message")
    land_finish.set_defaults(
        handler=command_land_finish, requires_release_preflight=True
    )

    collect = commands.add_parser(
        "collect", help="preflight and merge one explicitly authorized exact lane SHA"
    )
    collect.add_argument(
        "--integration-worktree",
        "--root",
        dest="root",
        required=True,
        help="integration checkout on the task ref (--root is a deprecated alias)",
    )
    collect.add_argument("--task-ref", required=True)
    collect.add_argument("--lane-ref", required=True)
    collect.add_argument("--expected-lane-sha", required=True)
    collect.add_argument("--authorized-sha")
    collect.add_argument("--review-kind", choices=COLLECT_REVIEW_KINDS)
    collect.add_argument(
        "--receipt", help="review receipt JSON path replacing the two flags above"
    )
    collect.add_argument(
        "--scope",
        help="lane scope manifest JSON; writes outside the declared scope fail collect",
    )
    collect.set_defaults(handler=command_collect, requires_release_preflight=True)

    scope = commands.add_parser(
        "scope", help="validate a declared write scope against the actual diff"
    )
    scope_commands = scope.add_subparsers(dest="scope_command", required=True)
    scope_lint = scope_commands.add_parser("lint")
    scope_lint.add_argument(
        "--input", required=True, help="scope manifest JSON path, or '-' for stdin"
    )
    scope_lint.set_defaults(handler=command_scope_lint)
    scope_check = scope_commands.add_parser("check")
    add_root(scope_check)
    scope_check.add_argument("--base", required=True)
    scope_check.add_argument("--head", required=True)
    scope_check.add_argument("--manifest", required=True)
    scope_check.set_defaults(handler=command_scope_check)
    scope_amend = scope_commands.add_parser("amend")
    scope_amend.add_argument(
        "--manifest", required=True, help="current scope manifest JSON path"
    )
    scope_amend.add_argument(
        "--add-owned", action="append", help="owned path pattern to add (repeatable)"
    )
    scope_amend.add_argument(
        "--add-shared-read-only",
        action="append",
        help="shared read-only path pattern to add (repeatable)",
    )
    scope_amend.add_argument(
        "--reason", required=True, help="why the declared scope must grow"
    )
    scope_amend.add_argument(
        "--output", required=True, help="amended manifest path (never overwrites)"
    )
    scope_amend.set_defaults(handler=command_scope_amend)

    sweep = commands.add_parser(
        "cleanup",
        help="remove one worktree, or sweep absorbed lanes and clean review checkouts",
    )
    add_root(sweep)
    sweep.add_argument(
        "--absorbed", action="store_true", help="authorize the full sweep"
    )
    sweep.add_argument("--dry-run", action="store_true")
    sweep.add_argument(
        "--worktree", help="remove exactly this managed worktree with full proofs"
    )
    sweep.add_argument(
        "--subject-sha",
        help="review targets only: fail fast when the checkout HEAD drifted",
    )
    sweep.set_defaults(handler=command_cleanup_absorbed)

    slice_parser = commands.add_parser(
        "slice", help="derive read-only slice states from Git plus receipts"
    )
    slice_commands = slice_parser.add_subparsers(dest="slice_command", required=True)
    slice_status = slice_commands.add_parser("status")
    add_root(slice_status)
    slice_status.add_argument("--task-ref", required=True)
    slice_status.add_argument(
        "--receipts-dir",
        help="review receipt directory (default .agent_state/orchestrate/receipts)",
    )
    slice_status.set_defaults(handler=command_slice_status)

    pin = commands.add_parser(
        "pin", help="pin a task to the installed orchestrate release"
    )
    pin_commands = pin.add_subparsers(dest="pin_command", required=True)
    pin_status_cmd = pin_commands.add_parser("status")
    add_root(pin_status_cmd)
    pin_status_cmd.set_defaults(handler=command_pin_status)
    pin_set = pin_commands.add_parser("set")
    add_root(pin_set)
    pin_set.set_defaults(handler=command_pin_set)
    pin_migrate = pin_commands.add_parser("migrate")
    add_root(pin_migrate)
    pin_migrate.set_defaults(handler=command_pin_migrate)

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
            release_preflight = require_release_preflight(
                Path(args.skill_dir), root=getattr(args, "root", None)
            )
        payload = args.handler(args)
        if release_preflight is not None:
            payload["release_preflight"] = release_preflight
    except (OSError, UnicodeError, OrchestrateError) as exc:
        parser.exit(2, f"orchestrate error: {exc}\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
