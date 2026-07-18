#!/usr/bin/env python3
"""Inspect orchestrate releases and guard explicit Git lane/landing actions."""

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
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EXACT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
VERSION_PATTERN = re.compile(r"^skill_version:\s*(\d+)\s*$", re.MULTILINE)
COLLECT_REVIEW_KINDS = (
    "different-identity",
    "focused",
    "root-spot",
    "mechanical",
)
LANDING_VERSION = 1
LANDING_POLICIES = (
    "validate-only",
    "land-with-confirmation",
    "commit-authorized",
    "publish-authorized",
)
LANDING_REQUIRED = ("landing_version", "task_id", "policy", "target_ref")
LANDING_FIELDS = set(LANDING_REQUIRED) | {"details"}


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


def write_release_manifest(
    skill_dir: Path, version: int, previous_version: int | None, output: Path
) -> dict[str, Any]:
    payload = build_manifest(skill_dir, version)
    if previous_version is not None:
        previous = load_manifest(skill_dir, previous_version)
        comparison = compare_manifests(previous, payload)
        payload["release_delta"] = {
            "from_version": previous_version,
            "changed_sections": {
                item["path"]: item["changed_sections"]
                for item in comparison["changed_documents"]
            },
            "changed_profiles": comparison["changed_profiles"],
            "must_reread": comparison["must_reread"],
            "acknowledge_removed": comparison["acknowledge_removed"],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def command_release_manifest(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    write_release_manifest(
        skill_dir, args.version, args.previous_version, Path(args.output).resolve()
    )
    return {"ok": True, "output": str(args.output), "skill_version": args.version}


def command_release(args: argparse.Namespace) -> dict[str, Any]:
    skill_dir = Path(args.skill_dir).resolve()
    skill_md = skill_dir / "SKILL.md"
    original = skill_md.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(original)
    if match is None:
        raise OrchestrateError("SKILL.md has no skill_version")
    current = int(match.group(1))
    target = args.version if args.version is not None else current + 1
    if target == current:
        # Rerun after an aborted release: the bump landed but the manifest or
        # doctor pass may be missing — finish or confirm, never double-bump.
        if manifest_path(skill_dir, target).is_file():
            result = verify_release(skill_dir)
            if not result["ok"]:
                raise OrchestrateError(
                    f"v{target} manifest exists but the release is not clean:"
                    f" {'; '.join(result['errors'])}"
                )
            result["recovered"] = "already-released"
            return result
        previous = target - 1
    elif target == current + 1:
        previous = current
    else:
        raise OrchestrateError(
            f"release target must be v{current} (finish an aborted release) or"
            f" v{current + 1}, got v{target}"
        )
    if target != current:
        # write_text truncates in place, so the installed hard link keeps its inode
        skill_md.write_text(
            VERSION_PATTERN.sub(f"skill_version: {target}", original, count=1),
            encoding="utf-8",
        )
    output = manifest_path(skill_dir, target)
    try:
        write_release_manifest(
            skill_dir,
            target,
            previous if manifest_path(skill_dir, previous).is_file() else None,
            output,
        )
        result = verify_release(skill_dir)
        if not result["ok"]:
            raise OrchestrateError(
                "post-release doctor failed: " + "; ".join(result["errors"])
            )
    except BaseException:
        # Roll the half-release back so the installed skill never sits mid-window.
        skill_md.write_text(original, encoding="utf-8")
        output.unlink(missing_ok=True)
        raise
    result["released_version"] = target
    result["from_version"] = current
    result["manifest"] = str(output)
    return result


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
    acknowledge_removed: list[str] = []
    old_docs = old["documents"]
    new_docs = new["documents"]
    for name in sorted(set(old_docs) | set(new_docs)):
        before = old_docs.get(name)
        after = new_docs.get(name)
        if before == after:
            continue
        change = (
            "added" if before is None else "removed" if after is None else "modified"
        )
        before_sections = before.get("sections", {}) if before else {}
        after_sections = after.get("sections", {}) if after else {}
        changed_sections = [
            section
            for section in sorted(set(before_sections) | set(after_sections))
            if before_sections.get(section) != after_sections.get(section)
        ]
        semantic = bool(changed_sections)
        reread = change != "removed" and semantic and name.endswith(".md")
        if reread:
            must_reread.append(name)
        elif change == "removed" and name.endswith(".md"):
            acknowledge_removed.append(name)
        documents.append(
            {
                "path": name,
                "change": change,
                "changed_sections": changed_sections,
                "must_reread": reread,
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
        "acknowledge_removed": acknowledge_removed,
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
        comparison["acknowledge_removed"] = [
            path
            for path in comparison["acknowledge_removed"]
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


SEAM_READY_PATTERN = re.compile(r"^Seam-Ready:\s*true\s*$", re.IGNORECASE | re.MULTILINE)
SPECULATIVE_BASE_PATTERN = re.compile(
    r"^Speculative-Base:\s*true\s*$", re.IGNORECASE | re.MULTILINE
)
DEPENDS_LANE_PATTERN = re.compile(
    r"^Depends-Lane:\s*([0-9a-fA-F]{40,64})\s*$", re.MULTILINE
)
ITEM_TRAILER_PATTERN = re.compile(r"^Item:\s*(\S+)\s*$", re.MULTILINE)
CLOSES_FINDING_PATTERN = re.compile(r"^Closes-Finding:\s*(\S+)\s*$", re.MULTILINE)


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


def command_compose_base(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    name = require_identifier(args.name, label="name")
    base = exact_commit(root, args.base, label="base")
    lanes = [
        exact_commit(root, value, label=f"lane[{index}]")
        for index, value in enumerate(args.lane)
    ]
    if len(set(lanes)) != len(lanes):
        raise OrchestrateError("duplicate lane SHAs in compose-base")
    branch = f"spec/{task_id}/{name}"
    ref = f"refs/heads/{branch}"
    if run_git(root, "show-ref", "--verify", "--quiet", ref, check=False).returncode == 0:
        # A prior run completed; verify the same inputs and report instead of failing.
        head = run_git(root, "rev-parse", ref).stdout.strip()
        for required in (base, *lanes):
            if (
                run_git(
                    root, "merge-base", "--is-ancestor", required, head, check=False
                ).returncode
                != 0
            ):
                raise OrchestrateError(
                    f"spec branch {branch} exists but does not contain {required};"
                    " pick a new --name for different inputs"
                )
        return {
            "ok": True,
            "operation": "compose-base",
            "recovered": "already-composed",
            "spec_ref": branch,
            "composite_sha": head,
            "base": base,
            "lanes": lanes,
            "observed_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    current = base
    for lane_sha in lanes:
        if (
            run_git(
                root, "merge-base", "--is-ancestor", lane_sha, current, check=False
            ).returncode
            == 0
        ):
            continue
        merged = run_git(
            root, "merge-tree", "--write-tree", current, lane_sha, check=False
        )
        if merged.returncode != 0:
            raise OrchestrateError(
                f"lanes textually collide at {lane_sha}: structural hazard —"
                " recut the seam or serialize; compose-base never resolves conflicts"
            )
        tree = merged.stdout.splitlines()[0].strip()
        message = (
            f"compose speculative base {task_id}/{name}\n\n"
            "Speculative-Base: true\n"
            f"Depends-Lane: {lane_sha}\n"
        )
        current = run_git(
            root,
            "commit-tree",
            tree,
            "-p",
            current,
            "-p",
            lane_sha,
            "-m",
            message,
        ).stdout.strip()
    if current == base:
        raise OrchestrateError("all lanes are already contained in the base")
    run_git(root, "branch", branch, current)
    return {
        "ok": True,
        "operation": "compose-base",
        "spec_ref": branch,
        "composite_sha": current,
        "base": base,
        "lanes": lanes,
        "speculative": True,
        "note": "not integrable until every Depends-Lane SHA is on the task branch",
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
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


def command_slice_milestone(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    item_id = require_identifier(args.item, label="item")
    head = run_git(root, "rev-parse", "HEAD").stdout.strip()
    parents = run_git(
        root, "rev-list", "--parents", "-1", head
    ).stdout.strip().split()[1:]
    body = run_git(root, "log", "-1", "--format=%B", head).stdout
    item_match = ITEM_TRAILER_PATTERN.search(body)
    if item_match is not None and item_match.group(1) != item_id:
        raise OrchestrateError(
            f"HEAD carries Item: {item_match.group(1)}, not {item_id};"
            " commit the item's work first or fix the --item"
        )
    evidence = worktree_evidence(root, started=started)
    payload = {
        "ok": True,
        "operation": "slice-milestone",
        "read_only": True,
        "item_id": item_id,
        "subject_sha": head,
        "parents": parents,
        "item_trailer_present": item_match is not None,
        "seam_ready": bool(SEAM_READY_PATTERN.search(body)),
        "closes_findings": CLOSES_FINDING_PATTERN.findall(body),
        "outcome": args.outcome,
        "evidence": None,
        **evidence,
    }
    if not evidence["clean"]:
        payload["warning"] = (
            "worktree is dirty: subject_sha does not carry the uncommitted work"
        )
    return payload


def command_collect(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    require_task_lane_refs(args.task_ref, args.lane_ref)
    if not (args.authorized_sha and args.review_kind):
        raise OrchestrateError(
            "collect requires both --authorized-sha and --review-kind"
        )
    authorized_value, review_kind = args.authorized_sha, args.review_kind
    authorization = {"authorization_source": "declared"}
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
    speculative_log = run_git(
        root, "log", "--format=%H%x1f%B%x1e", f"{task_head}..{expected}"
    ).stdout
    for chunk in speculative_log.split("\x1e"):
        sha, _, body = chunk.strip().partition("\x1f")
        if not sha or not SPECULATIVE_BASE_PATTERN.search(body):
            continue
        for dependency in DEPENDS_LANE_PATTERN.findall(body):
            if (
                run_git(
                    root,
                    "merge-base",
                    "--is-ancestor",
                    dependency,
                    task_head,
                    check=False,
                ).returncode
                != 0
            ):
                raise OrchestrateError(
                    f"lane stacks on speculative composite base {sha[:12]} whose"
                    f" dependency {dependency[:12]} is not on {args.task_ref};"
                    " collect that lane first"
                )
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
        "landing_authority": {"policy": policy, "state": authority_state},
        "landing_lock": {
            "state": "built-in",
            "hint": "land finish takes the landing lock itself",
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
    evidence = {
        "operation": "land-finish",
        "task_ref": args.task_ref,
        "target_ref": target_ref,
        "policy": policy,
        "task_sha": expected,
        "declaration_sha256": sha256_bytes(decl_data),
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
            "task head is not based on the current target tip: rebase off-lock,"
            " then rerun land finish"
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


def command_slice_status(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(args.root).resolve()
    task_ref = args.task_ref
    if not task_ref.startswith("task/") or task_ref.count("/") != 1:
        raise OrchestrateError(f"task ref must use task/<task>: {task_ref!r}")
    task_id = require_identifier(task_ref.split("/", 1)[1], label="task ref id")
    task_sha = run_git(root, "rev-parse", f"{task_ref}^{{commit}}").stdout.strip()
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
        if absorption is not None:
            entry["state"] = "absorbed"
            entry["absorption"] = absorption
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
        "write_set_overlaps": overlaps,
        "lanes": lanes,
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

    compose = commands.add_parser(
        "compose-base",
        help="merge seam-ready lanes into a marked speculative base (spec/<task>/<name>)",
    )
    add_root(compose)
    compose.add_argument("--task-id", required=True)
    compose.add_argument("--name", required=True)
    compose.add_argument("--base", required=True)
    compose.add_argument(
        "--lane",
        action="append",
        required=True,
        help="seam-ready lane SHA (repeatable)",
    )
    compose.set_defaults(handler=command_compose_base, requires_release_preflight=True)

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
    advance = review_commands.add_parser("advance")
    add_root(advance)
    advance.add_argument("--worktree", required=True)
    advance.add_argument("--from", dest="from_sha", required=True)
    advance.add_argument("--to", dest="to_sha", required=True)
    advance.set_defaults(
        handler=command_review_advance, requires_release_preflight=True
    )

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
    land_status.set_defaults(handler=command_land_status)
    land_finish = land_commands.add_parser("finish")
    add_root(land_finish)
    land_finish.add_argument("--task-ref", required=True)
    land_finish.add_argument("--task-sha", required=True)
    land_finish.add_argument(
        "--declaration", required=True, help="landing declaration JSON path"
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
    collect.add_argument("--authorized-sha", required=True)
    collect.add_argument(
        "--review-kind", choices=COLLECT_REVIEW_KINDS, required=True
    )
    collect.set_defaults(handler=command_collect, requires_release_preflight=True)

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
        "slice", help="derive read-only slice states from Git alone"
    )
    slice_commands = slice_parser.add_subparsers(dest="slice_command", required=True)
    slice_status = slice_commands.add_parser("status")
    add_root(slice_status)
    slice_status.add_argument("--task-ref", required=True)
    slice_status.set_defaults(handler=command_slice_status)
    slice_milestone = slice_commands.add_parser("milestone")
    add_root(slice_milestone)
    slice_milestone.add_argument("--item", required=True)
    slice_milestone.add_argument("--outcome")
    slice_milestone.set_defaults(handler=command_slice_milestone)

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

    release = commands.add_parser(
        "release",
        help="atomic release: bump skill_version, write the manifest, run doctor",
    )
    release.add_argument(
        "--version",
        type=int,
        help="target version (default: current+1; pass the current version to"
        " finish an aborted release)",
    )
    release.set_defaults(handler=command_release)

    release_manifest = commands.add_parser("release-manifest", help=argparse.SUPPRESS)
    release_manifest.add_argument("--version", required=True, type=int)
    release_manifest.add_argument("--previous-version", type=int)
    release_manifest.add_argument("--output", required=True)
    release_manifest.set_defaults(handler=command_release_manifest)
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
