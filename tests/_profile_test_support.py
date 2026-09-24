from __future__ import annotations

import tomllib
import unittest
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeProfile:
    pi_path: Path
    claude_path: Path
    codex_path: Path
    prompt: str


def markdown_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2].strip()


def codex_prompt(path: Path) -> str:
    return tomllib.loads(path.read_text(encoding="utf-8"))["developer_instructions"].strip()


def load_runtime_profile(home: Path, name: str) -> RuntimeProfile:
    pi_path = home / ".pi/agent/herdr-subagents/profiles" / f"{name}.md"
    return RuntimeProfile(
        pi_path=pi_path,
        claude_path=home / ".claude/agents" / f"{name}.md",
        codex_path=home / ".codex/agents" / f"{name}.toml",
        prompt=markdown_prompt(pi_path),
    )


def assert_prompt_parity(case: unittest.TestCase, profile: RuntimeProfile) -> None:
    case.assertEqual(profile.prompt, markdown_prompt(profile.claude_path))
    case.assertEqual(profile.prompt, codex_prompt(profile.codex_path))
