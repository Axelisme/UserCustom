from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class OrchestrateError(RuntimeError):
    def __init__(
        self,
        message: str,
        code: str = "git_error",
        repair: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.repair = repair


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    data: Mapping[str, object]
    warnings: tuple[str, ...] = ()
    diagnostics: tuple[Mapping[str, object], ...] = ()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_sha256(text: str) -> str:
    return sha256_bytes(" ".join(text.split()).encode())


def require_identifier(value: str, *, label: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        lowered = value.casefold()
        repair = (
            f"Use {lowered!r}."
            if ID_PATTERN.fullmatch(lowered)
            else f"Use a {label} matching {ID_PATTERN.pattern}."
        )
        raise OrchestrateError(
            f"{label} must match {ID_PATTERN.pattern}: {value!r}",
            "invalid_identifier",
            repair,
        )
    return value


def read_json_object(path: str, *, label: str) -> tuple[dict[str, Any], bytes]:
    import json
    from pathlib import Path
    try:
        data = __import__("sys").stdin.buffer.read() if path == "-" else Path(path).read_bytes()
        payload = json.loads(data)
    except (OSError, json.JSONDecodeError) as exc:
        raise OrchestrateError(f"cannot read {label} JSON: {exc}", "filesystem_error") from exc
    if not isinstance(payload, dict):
        raise OrchestrateError(f"{label} JSON must be an object", "filesystem_error")
    return payload, data


def require_json_fields(payload: dict[str, Any], fields: Sequence[str], errors: list[str]) -> None:
    for field in fields:
        if field not in payload:
            errors.append(f"missing required field: {field}")


def validate_json_enum(payload: dict[str, Any], field: str, choices: Sequence[str], errors: list[str]) -> None:
    if field in payload and payload[field] not in choices:
        errors.append(f"{field} must be one of: {', '.join(choices)}")
