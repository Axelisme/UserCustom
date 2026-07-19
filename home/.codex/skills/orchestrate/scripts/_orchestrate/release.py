from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError, normalized_sha256, sha256_bytes
from .git_ops import common_repo_root

MANIFEST_SCHEMA = 1


VERSION_PATTERN = re.compile(r"^skill_version:\s*(\d+)\s*$", re.MULTILINE)


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
    paths.extend(sorted((skill_dir / "scripts").rglob("*.py")))
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
