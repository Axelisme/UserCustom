from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tomllib

from .primitives import CommandResult, OrchestrateError, normalized_sha256, sha256_bytes

MANIFEST_SCHEMA = 1


VERSION_PATTERN = re.compile(r"^skill_version:\s*(\d+)\s*$", re.MULTILINE)
CLI_VERSION_PATTERN = re.compile(r"^ORCHESTRATE_VERSION = (\d+)$", re.MULTILINE)


def skill_version(skill_dir: Path) -> int:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(text)
    if match is None:
        raise OrchestrateError("SKILL.md has no skill_version")
    return int(match.group(1))


def source_home(skill_dir: Path) -> Path:
    resolved = skill_dir.resolve()
    for parent in resolved.parents:
        relative = resolved.relative_to(parent)
        if parent.name in {".codex", ".claude"} and relative.parts[:1] == ("skills",):
            return parent.parent
        if parent.name == ".pi" and relative.parts[:2] == ("agent", "skills"):
            return parent.parent
    raise OrchestrateError(f"cannot locate home root from {skill_dir}")


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


def _profile_text(value: object, field: str, path: Path) -> str:
    if not isinstance(value, str):
        raise OrchestrateError(
            f"profile {path} requires string {field}"
        )
    if not value.strip():
        raise OrchestrateError(
            f"profile {path} requires non-blank {field}"
        )
    return value


def _frontmatter_text(frontmatter: str, field: str, path: Path) -> str:
    match = re.search(
        rf"(?m)^\s*{re.escape(field)}\s*:\s*(.*?)\s*$", frontmatter
    )
    if match is None:
        raise OrchestrateError(f"profile {path} is missing {field}")
    raw = match.group(1)
    if not raw:
        return _profile_text(raw, field, path)
    if raw[0] in {'"', "'"}:
        if len(raw) < 2 or raw[-1] != raw[0]:
            raise OrchestrateError(f"profile {path} requires string {field}")
        if raw[0] == '"':
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise OrchestrateError(
                    f"profile {path} requires string {field}"
                ) from exc
        else:
            value = raw[1:-1]
    elif (
        raw.lower() in {"null", "true", "false", "~"}
        or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", raw) is not None
        or raw.startswith(("[", "{"))
    ):
        raise OrchestrateError(f"profile {path} requires string {field}")
    else:
        value = raw
    return _profile_text(value, field, path)


def _markdown_profile_parts(text: str, path: Path) -> tuple[str, str]:
    opening = re.match(r"\A---[ \t]*(?:\r?\n|\Z)", text)
    if opening is None:
        raise OrchestrateError(f"profile {path} is missing frontmatter")
    closing = re.compile(r"(?m)^---[ \t]*(?:\r?\n|\Z)").search(
        text, opening.end()
    )
    if closing is None:
        raise OrchestrateError(f"profile {path} is missing closing frontmatter")
    frontmatter = text[opening.end() : closing.start()]
    return _frontmatter_text(frontmatter, "name", path), text[closing.end() :]


def profile_identity_prompt(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    if path.name == "APPEND_SYSTEM.md":
        return "APPEND_SYSTEM", _profile_text(text, "prompt", path)
    if path.suffix == ".toml":
        try:
            profile = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise OrchestrateError(f"invalid TOML profile: {exc}") from exc
        return (
            _profile_text(profile.get("name"), "name", path),
            _profile_text(profile.get("developer_instructions"), "developer_instructions", path),
        )
    if path.suffix == ".md":
        name, prompt = _markdown_profile_parts(text, path)
        return name, _profile_text(prompt, "prompt", path)
    raise OrchestrateError(f"unsupported profile format: {path}")


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


def profile_contract(text: str, suffix: str) -> str:
    """Return behavior/tooling contract while excluding runtime tuning knobs."""
    ignored = {"model", "model_reasoning_effort", "thinking", "fallbackModels"}
    lines = text.splitlines()
    if suffix == ".toml":
        try:
            contract = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise OrchestrateError(f"invalid TOML profile: {exc}") from exc
        for key in ignored:
            contract.pop(key, None)
        return json.dumps(
            contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
        except ValueError:
            return text
        frontmatter: list[str] = []
        skip_value = False
        for line in lines[1:end]:
            match = re.match(r"^([A-Za-z_][\w-]*):", line)
            if match:
                skip_value = match.group(1) in ignored
            if not skip_value:
                frontmatter.append(line)
        return "\n".join(["---", *frontmatter, "---", *lines[end + 1 :]])
    return text


def document_paths(skill_dir: Path) -> list[Path]:
    paths = [skill_dir / "SKILL.md", *sorted(skill_dir.glob("runtime-*.md"))]
    paths.extend(sorted((skill_dir / "references").glob("*.md")))
    paths.extend(sorted((skill_dir / "migrations").glob("*.md")))
    paths.extend(sorted((skill_dir / "scripts").rglob("*.py")))
    return [path for path in paths if path.is_file()]


PROFILE_NAMES = (
    "acceptance-reviewer",
    "contract-reviewer",
    "lane-worker",
)


def profile_paths(home: Path) -> list[Path]:
    # Bind only the profiles orchestrate itself dispatches, so editing an
    # unrelated shipped profile is not a package change requiring a release.
    names = PROFILE_NAMES
    return [
        *[home / ".codex" / "agents" / f"{name}.toml" for name in names],
        *[home / ".claude" / "agents" / f"{name}.md" for name in names],
        home / ".pi" / "agent" / "APPEND_SYSTEM.md",
        *[home / ".pi" / "agent" / "agents" / f"{name}.md" for name in names],
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
        relative = path.relative_to(home).as_posix()
        if version >= 137:
            agent_name, prompt = profile_identity_prompt(path)
            entry = {
                "agent_name": agent_name,
                "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
            }
        else:
            data = path.read_bytes()
            text = data.decode("utf-8")
            entry = {
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "standing_orders_sha256": normalized_sha256(
                    profile_standing_orders(text, path.suffix)
                ),
                "profile_contract_sha256": normalized_sha256(
                    profile_contract(text, path.suffix)
                ),
            }
        profiles[relative] = entry
    return {
        "schema_version": MANIFEST_SCHEMA,
        "skill_version": version,
        "orchestrate_compat": version,
        "documents": documents,
        "profiles": profiles,
    }


def manifest_path(skill_dir: Path, version: int) -> Path:
    return skill_dir / "manifests" / f"{version}.json"


def _validate_profile_entry(
    entry: dict[str, Any], name: str, version: int, path: Path
) -> None:
    if version >= 137:
        expected = {"agent_name", "prompt_sha256"}
        if set(entry) != expected:
            raise OrchestrateError(
                f"invalid release manifest structure {path}: profile entry {name!r} "
                f"must contain exactly {sorted(expected)}"
            )
        agent_name = entry["agent_name"]
        prompt_sha256 = entry["prompt_sha256"]
        if not isinstance(agent_name, str) or not agent_name.strip():
            raise OrchestrateError(
                f"invalid release manifest structure {path}: profile entry {name!r} "
                "requires non-blank string agent_name"
            )
        if not isinstance(prompt_sha256, str) or re.fullmatch(
            r"[0-9a-f]{64}", prompt_sha256
        ) is None:
            raise OrchestrateError(
                f"invalid release manifest structure {path}: profile entry {name!r} "
                "requires a SHA-256 prompt_sha256"
            )
        return
    expected = {
        "bytes",
        "sha256",
        "standing_orders_sha256",
        "profile_contract_sha256",
    }
    if set(entry) != expected:
        raise OrchestrateError(
            f"invalid release manifest structure {path}: legacy profile entry "
            f"{name!r} must contain exactly {sorted(expected)}"
        )
    if type(entry["bytes"]) is not int:
        raise OrchestrateError(
            f"invalid release manifest structure {path}: legacy profile entry "
            f"{name!r} requires integer bytes"
        )
    for field in ("sha256", "standing_orders_sha256", "profile_contract_sha256"):
        if not isinstance(entry[field], str):
            raise OrchestrateError(
                f"invalid release manifest structure {path}: legacy profile entry "
                f"{name!r} requires string {field}"
            )


def validate_manifest_structure(
    payload: Any, path: Path, version: int | None = None
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OrchestrateError(
            f"invalid release manifest structure {path}: root must be an object"
        )
    manifest_version = payload.get("skill_version")
    if type(manifest_version) is not int:
        raise OrchestrateError(
            f"invalid release manifest structure {path}: "
            "skill_version must be an integer"
        )
    shape_version = manifest_version if version is None else version
    if type(payload.get("orchestrate_compat")) is not int:
        raise OrchestrateError(
            f"invalid release manifest structure {path}: "
            "orchestrate_compat must be an integer"
        )
    if shape_version <= 137:
        runtime_assets = payload.get("runtime_assets")
        if not isinstance(runtime_assets, dict):
            raise OrchestrateError(
                f"invalid release manifest structure {path}: "
                "runtime_assets must be an object for v137 and earlier"
            )
    elif "runtime_assets" in payload:
        raise OrchestrateError(
            f"invalid release manifest structure {path}: "
            "runtime_assets is not allowed for v138 and later"
        )
    categories = [
        ("documents", "sha256"),
        ("profiles", None),
    ]
    if shape_version <= 137:
        categories.append(("runtime_assets", "sha256"))
    for category, hash_field in categories:
        entries = payload.get(category)
        if not isinstance(entries, dict):
            raise OrchestrateError(
                f"invalid release manifest structure {path}: "
                f"{category} must be an object"
            )
        for name, entry in entries.items():
            if not isinstance(name, str):
                raise OrchestrateError(
                    f"invalid release manifest structure {path}: "
                    f"{category} names must be strings"
                )
            if not isinstance(entry, dict):
                raise OrchestrateError(
                    f"invalid release manifest structure {path}: "
                    f"{category} entry {name!r} must be an object"
                )
            if category == "profiles":
                _validate_profile_entry(entry, name, shape_version, path)
            else:
                assert hash_field is not None
                if not isinstance(entry.get(hash_field), str):
                    raise OrchestrateError(
                        f"invalid release manifest structure {path}: "
                        f"{category} entry {name!r} requires string {hash_field}"
                    )
            if category == "documents":
                sections = entry.get("sections")
                if not isinstance(sections, dict) or not all(
                    isinstance(section, str) and isinstance(digest, str)
                    for section, digest in sections.items()
                ):
                    raise OrchestrateError(
                        f"invalid release manifest structure {path}: "
                        f"documents entry {name!r} requires string-hash sections"
                    )
    return payload


def load_manifest(skill_dir: Path, version: int) -> dict[str, Any]:
    path = manifest_path(skill_dir, version)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OrchestrateError(
            f"release manifest not found: {path}", "manifest_invalid"
        ) from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OrchestrateError(
            f"invalid release manifest {path}: {exc}", "manifest_invalid"
        ) from exc
    try:
        payload = validate_manifest_structure(loaded, path, version)
        if payload.get("schema_version") != MANIFEST_SCHEMA:
            raise OrchestrateError(f"unsupported manifest schema: {path}")
        if payload.get("skill_version") != version:
            raise OrchestrateError(f"manifest version mismatch: {path}")
    except OrchestrateError as exc:
        raise OrchestrateError(str(exc), "manifest_invalid") from exc
    return payload


def write_release_manifest(
    skill_dir: Path, version: int, previous_version: int | None, output: Path
) -> dict[str, Any]:
    guide = skill_dir / "migrations" / f"{version}.md"
    if not guide.is_file():
        raise OrchestrateError(
            f"cannot publish release; migration guide missing: {guide}"
        )
    payload = build_manifest(skill_dir, version)
    if f"migrations/{version}.md" not in payload["documents"]:
        raise OrchestrateError(
            f"cannot publish release; migration guide is not manifest-hashed: {guide}"
        )
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
            "changed_runtime_assets": comparison["changed_runtime_assets"],
            "must_reread": comparison["must_reread"],
            "acknowledge_removed": comparison["acknowledge_removed"],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _replace_version_once(
    original: bytes,
    pattern: re.Pattern[str],
    current: int,
    replacement: str,
    source: Path,
) -> bytes:
    text = original.decode("utf-8")
    matches = pattern.findall(text)
    if matches != [str(current)]:
        raise OrchestrateError(
            f"release version source must contain exactly one current version: {source}"
        )
    updated, substitutions = pattern.subn(replacement, text)
    if substitutions != 1:
        raise OrchestrateError(
            f"release version substitution count was {substitutions}, expected 1: {source}"
        )
    return updated.encode("utf-8")


def release_package(skill_dir: Path, target: int) -> CommandResult:
    """Publish exactly the next package version as one restorable transaction."""
    skill_dir = skill_dir.resolve()
    skill_md = skill_dir / "SKILL.md"
    cli_source = skill_dir / "scripts" / "_orchestrate" / "cli.py"
    originals = {
        skill_md: skill_md.read_bytes(),
        cli_source: cli_source.read_bytes(),
    }
    current = skill_version(skill_dir)
    if target != current + 1:
        raise OrchestrateError(
            f"release target must be exactly v{current + 1}, got v{target}",
            "invalid_release_target",
        )
    replacements = {
        skill_md: _replace_version_once(
            originals[skill_md],
            VERSION_PATTERN,
            current,
            f"skill_version: {target}",
            skill_md,
        ),
        cli_source: _replace_version_once(
            originals[cli_source],
            CLI_VERSION_PATTERN,
            current,
            f"ORCHESTRATE_VERSION = {target}",
            cli_source,
        ),
    }
    output = manifest_path(skill_dir, target)
    try:
        output_stat = output.lstat()
    except FileNotFoundError:
        output_stat = None
    if output_stat is not None and (
        stat.S_ISLNK(output_stat.st_mode)
        or stat.S_ISREG(output_stat.st_mode) and output_stat.st_nlink > 1
    ):
        raise OrchestrateError(
            f"release manifest target is not safely restorable: {output}",
            "release_failed",
        )
    output_existed = output_stat is not None
    output_original: bytes | None = None
    try:
        if output_existed:
            output_original = output.read_bytes()
        for source, replacement in replacements.items():
            source.write_bytes(replacement)
        write_release_manifest(skill_dir, target, current, output)
        verified = verify_release(skill_dir)
        if not verified["ok"]:
            raise OrchestrateError(
                "post-release doctor failed: " + "; ".join(verified["errors"])
            )
    except BaseException as exc:
        for source, original in originals.items():
            source.write_bytes(original)
        if output_existed:
            if output_original is not None:
                output.write_bytes(output_original)
        else:
            output.unlink(missing_ok=True)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise OrchestrateError(str(exc), "release_failed") from exc
    return CommandResult(True, {})


def verify_release(skill_dir: Path) -> dict[str, Any]:
    skill_dir = skill_dir.resolve()
    version = skill_version(skill_dir)
    manifest = load_manifest(skill_dir, version)
    observed = build_manifest(skill_dir, version)
    errors: list[str] = []
    for category in ("documents", "profiles"):
        expected_items = manifest.get(category, {})
        observed_items = observed.get(category, {})
        for name in sorted(set(expected_items) | set(observed_items)):
            if name not in expected_items:
                errors.append(f"unexpected {category[:-1]}: {name}")
            elif name not in observed_items:
                errors.append(f"missing {category[:-1]}: {name}")
            else:
                expected = expected_items[name]
                observed_entry = observed_items[name]
                if category == "documents":
                    matches = expected["sha256"] == observed_entry["sha256"]
                elif version >= 137:
                    matches = (
                        expected["agent_name"] == observed_entry["agent_name"]
                        and expected["prompt_sha256"]
                        == observed_entry["prompt_sha256"]
                    )
                else:
                    matches = (
                        expected["profile_contract_sha256"]
                        == observed_entry["profile_contract_sha256"]
                    )
                if not matches:
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
        "runtime_assets": 0,
        "errors": errors,
    }


def version_pin_path(root: Path) -> Path:
    return root.resolve() / ".agent_state" / "orchestrate" / "version-pin.json"


def read_version_pin(root: Path) -> dict[str, Any] | None:
    path = version_pin_path(root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OrchestrateError(
            f"cannot read version pin: {exc}", "pin_invalid"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(
        payload.get("skill_version"), int
    ):
        raise OrchestrateError(f"invalid version pin: {path}", "pin_invalid")
    return payload


def write_version_pin(root: Path, version: int, compat: Any) -> Path:
    path = version_pin_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pin_version": 1,
        "skill_version": version,
        "orchestrate_compat": compat,
        "pinned_at": datetime.now(UTC).isoformat(),
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8"
        ) as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return path


def require_verified_release(skill_dir: Path) -> dict[str, Any]:
    result = verify_release(skill_dir)
    if not result["ok"]:
        raise OrchestrateError(
            "release preflight failed: " + "; ".join(result["errors"])
        )
    return result


def require_intact_package(skill_dir: Path) -> dict[str, Any]:
    """Publication preflight: the current package must be whole, not unchanged.

    Publishing a release necessarily edits documents the current manifest still
    hashes, so hash equality cannot be a precondition for it. Require instead
    that the current manifest loads and that no document it lists has gone
    missing; `release_package` verifies the published result against the target
    manifest and restores prior bytes when that fails.
    """
    skill_dir = skill_dir.resolve()
    version = skill_version(skill_dir)
    manifest = load_manifest(skill_dir, version)
    missing = sorted(
        name
        for name in manifest.get("documents", {})
        if not (skill_dir / name).is_file()
    )
    if missing:
        raise OrchestrateError(
            "release preflight failed: " + "; ".join(f"missing document: {name}" for name in missing)
        )
    return manifest


def pin_status(root: Path, skill_dir: Path) -> CommandResult:
    current = skill_version(skill_dir)
    pin = read_version_pin(root)
    data: dict[str, object] = {"current": current, "aligned": False}
    if pin is not None:
        pinned = pin["skill_version"]
        data.update({"pinned": pinned, "aligned": pinned == current})
    return CommandResult(True, data)


def pin_set(root: Path, skill_dir: Path) -> CommandResult:
    verified = require_verified_release(skill_dir)
    current = verified["skill_version"]
    pin = read_version_pin(root)
    if pin is not None and pin["skill_version"] == current:
        return CommandResult(True, {}, ("repository is already pinned",))
    write_version_pin(root, current, verified["orchestrate_compat"])
    return CommandResult(True, {})


def _package_projection(skill_dir: Path) -> dict[str, int]:
    current = skill_version(skill_dir)
    observed = build_manifest(skill_dir, current)
    return {
        "current": current,
        "documents": len(observed["documents"]),
        "profiles": len(observed["profiles"]),
        "runtime_assets": 0,
    }


def doctor_package(skill_dir: Path, repo: Any | None) -> CommandResult:
    """Report package predicate truth separately from repository pin projection."""
    warnings: list[str] = []
    data: dict[str, object] = {}
    diagnostics: list[dict[str, str]] = []
    current: int | None = None
    try:
        package = _package_projection(skill_dir)
        data["package"] = package
        current = package["current"]
        verified = verify_release(skill_dir)
        errors = verified["errors"]
    except (OSError, UnicodeError, OrchestrateError) as exc:
        errors = [str(exc)]
    seen: set[str] = set()
    for message in errors:
        if message not in seen and len(diagnostics) < 20:
            diagnostics.append({"code": "manifest_invalid", "message": message})
            seen.add(message)

    if repo is None:
        warnings.append("repository projection unavailable")
    else:
        try:
            pin = read_version_pin(repo.worktree_root)
        except (OSError, UnicodeError, OrchestrateError) as exc:
            pin = None
            warnings.append(f"repository pin unavailable: {exc}")
        if pin is None:
            warnings.append("repository has no version pin")
        else:
            pinned = pin["skill_version"]
            aligned = current is not None and pinned == current
            data["repository"] = {"pinned": pinned, "aligned": aligned}
            if not aligned:
                warnings.append("repository pin is not aligned")
    return CommandResult(
        not diagnostics,
        data,
        tuple(warnings),
        tuple(diagnostics),
    )


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
    profile_names = sorted(set(old["profiles"]) | set(new["profiles"]))
    if old["skill_version"] == 136 and new["skill_version"] == 137:
        # v137 changes the projection schema once, so every shipped profile is
        # explicitly acknowledged even when its identity and prompt are stable.
        changed_profiles = profile_names
    else:
        changed_profiles = []
        for name in profile_names:
            before = old["profiles"].get(name)
            after = new["profiles"].get(name)
            if before is None or after is None:
                changed_profiles.append(name)
                continue
            if old["skill_version"] >= 137 and new["skill_version"] >= 137:
                changed = (
                    before["agent_name"] != after["agent_name"]
                    or before["prompt_sha256"] != after["prompt_sha256"]
                )
            elif old["skill_version"] < 137 and new["skill_version"] < 137:
                changed = (
                    before["profile_contract_sha256"]
                    != after["profile_contract_sha256"]
                )
            else:
                changed = True
            if changed:
                changed_profiles.append(name)
    old_runtime_assets = old.get("runtime_assets", {})
    new_runtime_assets = new.get("runtime_assets", {})
    changed_runtime_assets = [
        name
        for name in sorted(set(old_runtime_assets) | set(new_runtime_assets))
        if old_runtime_assets.get(name) != new_runtime_assets.get(name)
    ]
    return {
        "from": old["skill_version"],
        "to": new["skill_version"],
        "compat": [old["orchestrate_compat"], new["orchestrate_compat"]],
        "changed_documents": documents,
        "changed_profiles": changed_profiles,
        "changed_runtime_assets": changed_runtime_assets,
        "must_reread": must_reread,
        "acknowledge_removed": acknowledge_removed,
    }


def doctor_diff(
    skill_dir: Path,
    old_version: int,
    new_version: int,
    runtime: str | None,
) -> CommandResult:
    old = load_manifest(skill_dir.resolve(), old_version)
    new = load_manifest(skill_dir.resolve(), new_version)
    comparison = compare_manifests(old, new)
    if runtime is not None:
        runtime_document = f"runtime-{runtime}.md"
        profile_prefix = {
            "codex": ".codex/",
            "claude": ".claude/",
            "pi": ".pi/",
        }[runtime]
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
        comparison["changed_runtime_assets"] = [
            path
            for path in comparison["changed_runtime_assets"]
            if path.startswith(profile_prefix)
        ]
        comparison["runtime"] = runtime
    return CommandResult(True, comparison)
