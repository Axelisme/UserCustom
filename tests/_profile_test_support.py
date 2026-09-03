from __future__ import annotations

import difflib
import re
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


def load_runtime_profile(home: Path, name: str) -> RuntimeProfile:
    pi_path = home / ".pi/agent/agents" / f"{name}.md"
    claude_path = home / ".claude/agents" / f"{name}.md"
    codex_path = home / ".codex/agents" / f"{name}.toml"
    return RuntimeProfile(
        pi_path=pi_path,
        claude_path=claude_path,
        codex_path=codex_path,
        prompt=markdown_prompt(pi_path),
    )


def codex_prompt(path: Path) -> str:
    return tomllib.loads(path.read_text(encoding="utf-8"))["developer_instructions"].strip()


def runtime_prompts(profile: RuntimeProfile) -> dict[str, str]:
    """Every runtime's copy of one profile body, keyed by runtime."""
    return {
        "pi": markdown_prompt(profile.pi_path),
        "claude": markdown_prompt(profile.claude_path),
        "codex": codex_prompt(profile.codex_path),
    }


def section_headings(prompt: str) -> list[str]:
    return [line.strip() for line in prompt.splitlines() if line.startswith("## ")]


def normalize_whitespace(text: str) -> str:
    """Collapse every run of whitespace into one space.

    This absorbs formatting-only differences (including line wrapping and blank lines) between
    otherwise identical copies. It does not judge semantic equivalence: wording differences still
    change the result.
    """
    return re.sub(r"\s+", " ", text).strip()


def prompt_sections(prompt: str) -> dict[str | None, str]:
    """Split one runtime prompt into `## `-heading sections, each whitespace-normalized.

    The `None` key holds the text preceding the first `## ` heading.
    """
    lines_by_heading: dict[str | None, list[str]] = {}
    heading: str | None = None
    for line in prompt.splitlines():
        if line.startswith("## "):
            heading = line.strip()
            lines_by_heading.setdefault(heading, [])
        else:
            lines_by_heading.setdefault(heading, []).append(line)
    return {key: normalize_whitespace("\n".join(lines)) for key, lines in lines_by_heading.items()}


@dataclass(frozen=True)
class DeclaredDelta:
    """One explicitly allowed divergence between a profile's three runtime copies.

    The record names the profile, the runtime carrying the delta, its exact section location, and
    the reason it is allowed. It deliberately contains no profile wording, so the declaration
    cannot become a second copy of the content it guards.
    """

    profile: str
    runtime: str
    location: str
    reason: str


def _normalized_without_sections(prompt: str, ignored: set[str]) -> str:
    """Return one copy's normalized body after removing declared section-level deltas."""
    retained: list[str] = []
    section: str | None = None
    for line in prompt.splitlines():
        if line.startswith("## "):
            section = line.strip()
        if section not in ignored:
            retained.append(line)
    return normalize_whitespace("\n".join(retained))


def _diff(expected: str, actual: str, expected_label: str, actual_label: str) -> str:
    """Render a compact word-level unified diff for a parity failure."""
    expected_lines = [f"{word}\n" for word in normalize_whitespace(expected).split()]
    actual_lines = [f"{word}\n" for word in normalize_whitespace(actual).split()]
    return "".join(
        difflib.unified_diff(
            expected_lines,
            actual_lines,
            fromfile=expected_label,
            tofile=actual_label,
            n=3,
        )
    ).rstrip()


def _assert_equal_with_diff(
    case: unittest.TestCase,
    expected: str,
    actual: str,
    expected_label: str,
    actual_label: str,
    message: str,
) -> None:
    """Fail with the two normalized values' useful diff instead of only their reprs."""
    if expected == actual:
        return
    case.fail(f"{message}\n{_diff(expected, actual, expected_label, actual_label)}")


def assert_prompt_parity(
    case: unittest.TestCase,
    profile: RuntimeProfile,
    *,
    profile_name: str | None = None,
    deltas: tuple[DeclaredDelta, ...] = (),
) -> None:
    """Assert three runtime copies are normalized-identical except for declared section deltas.

    The original byte-identity check remains the no-delta case used by the other profiles. For a
    Collab role, every declared location is removed from the common comparison, then the copies not
    named by that location's delta are compared with each other. Thus an undeclared change outside a
    delta, or an unexplained change in the other copies of a delta section, fails with a diff.
    """
    name = profile_name or profile.pi_path.stem
    if not deltas:
        case.assertEqual(profile.prompt, markdown_prompt(profile.claude_path))
        case.assertEqual(profile.prompt, codex_prompt(profile.codex_path))
        return

    prompts = runtime_prompts(profile)
    runtimes = set(prompts)

    for delta in deltas:
        case.assertEqual(
            name,
            delta.profile,
            f"declared delta profile {delta.profile!r} does not match {name!r}",
        )
        case.assertIn(delta.runtime, runtimes, f"unknown runtime in declared delta: {delta.runtime!r}")
        case.assertTrue(delta.location, "a declared delta must identify its location")
        case.assertTrue(delta.reason.strip(), "a declared delta must state why it is allowed")

    locations = {delta.location for delta in deltas}
    normalized = {
        runtime: _normalized_without_sections(prompt, locations)
        for runtime, prompt in prompts.items()
    }
    reference_runtime = next(iter(prompts))
    for runtime, body in normalized.items():
        if runtime == reference_runtime:
            continue
        _assert_equal_with_diff(
            case,
            normalized[reference_runtime],
            body,
            f"{name}/{reference_runtime}",
            f"{name}/{runtime}",
            f"{name}: normalized runtime copies differ outside declared deltas",
        )

    sections = {runtime: prompt_sections(text) for runtime, text in prompts.items()}
    for location in locations:
        exempt = {delta.runtime for delta in deltas if delta.location == location}
        checked = {
            runtime: bodies.get(location)
            for runtime, bodies in sections.items()
            if runtime not in exempt
        }
        if len(checked) < 2:
            continue
        reference_runtime = next(iter(checked))
        reference_body = checked[reference_runtime]
        for runtime, body in checked.items():
            if runtime == reference_runtime:
                continue
            _assert_equal_with_diff(
                case,
                reference_body or "<missing section>",
                body or "<missing section>",
                f"{name}/{reference_runtime}/{location}",
                f"{name}/{runtime}/{location}",
                f"{name}: {location!r} differs outside its declared runtime deltas",
            )
