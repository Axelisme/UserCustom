from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class OrchestrateError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_sha256(text: str) -> str:
    return sha256_bytes(" ".join(text.split()).encode())


def require_identifier(value: str, *, label: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise OrchestrateError(f"{label} must match {ID_PATTERN.pattern}: {value!r}")
    return value


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
