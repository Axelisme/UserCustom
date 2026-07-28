"""Four zero-parameter Git checks over one task's collected lanes.

Deletion, loop, mass, and focus ask nothing of the caller: each is a pure
function of a Git commit range and the lane collect records ``report`` has
already discovered. They only report; ``report`` never refuses on their
account.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .git_ops import run_git

DEFAULT_LANE_FAMILY_TOKENS = 1
DEFAULT_MAX_LANE_REPEATS = 2
DEFAULT_MAX_FILE_ADDED = 2000
DEFAULT_FOCUS_DAYS = 3

PASS = "pass"
REFUSE = "refuse"


def is_test_path(path: str) -> bool:
    tail = path.rsplit("/", 1)[-1]
    return (
        "tests/" in path
        or path.startswith("test/")
        or tail.startswith("test_")
        or tail.endswith("_test.py")
        or tail == "conftest.py"
    )


def numstat(root: Path, *args: str) -> list[tuple[int, int, str]]:
    output = run_git(root, "diff", "--numstat", *args).stdout
    rows: list[tuple[int, int, str]] = []
    for line in output.splitlines():
        added, _, rest = line.partition("\t")
        deleted, _, path = rest.partition("\t")
        if added == "-" or deleted == "-" or not path:
            continue  # binary
        rows.append((int(added), int(deleted), path))
    return rows


def _family(lane_id: str, tokens: int) -> str:
    # A repair lane is routinely given a fresh, unrelated-looking id, so
    # counting exact lane ids would report one loop iteration per lane and
    # never see a repeated-rework pattern. Group by the leading tokens.
    return "-".join(lane_id.split("-")[:tokens]) or lane_id


def deletion_check(root: Path, base: str, tip: str) -> dict[str, Any]:
    """PASS only once the range deletes at least one production line.

    Pure addition accumulates unreachable code; a milestone that never
    deletes anything in production is the check this flags.
    """
    rows = numstat(root, f"{base}..{tip}")
    production = [row for row in rows if not is_test_path(row[2])]
    deletions = sum(deleted for _, deleted, _ in production)
    return {
        "status": PASS if deletions else REFUSE,
        "value": deletions,
        "threshold": 1,
    }


def mass_check(
    root: Path, base: str, tip: str, *, max_file_added: int = DEFAULT_MAX_FILE_ADDED
) -> dict[str, Any]:
    """REFUSE when one production file's added lines cross the threshold."""
    rows = numstat(root, f"{base}..{tip}")
    production = [row for row in rows if not is_test_path(row[2])]
    worst = max(production, key=lambda row: row[0], default=(0, 0, ""))
    return {
        "status": REFUSE if worst[0] > max_file_added else PASS,
        "value": worst[0],
        "threshold": max_file_added,
        "detail": {"largest": worst[2] or None},
    }


def loop_check(
    collected: list[dict[str, Any]],
    *,
    tokens: int = DEFAULT_LANE_FAMILY_TOKENS,
    max_repeats: int = DEFAULT_MAX_LANE_REPEATS,
) -> dict[str, Any]:
    """REFUSE when one lane family was collected more than ``max_repeats`` times.

    A family past its repeat cap is a scope event, not routine iteration.
    """
    counts: dict[str, int] = {}
    for record in collected:
        family = _family(record["lane"], tokens)
        counts[family] = counts.get(family, 0) + 1
    worst = max(counts.values(), default=0)
    return {
        "status": REFUSE if worst > max_repeats else PASS,
        "value": worst,
        "threshold": max_repeats,
        "detail": dict(sorted(counts.items(), key=lambda item: -item[1])[:5]),
    }


def focus_check(
    collected: list[dict[str, Any]],
    *,
    tokens: int = DEFAULT_LANE_FAMILY_TOKENS,
    focus_days: int = DEFAULT_FOCUS_DAYS,
) -> dict[str, Any]:
    """REFUSE when every lane collected in the recent window is the same family.

    Every recent collect landing on one family is what a correction loop
    looks like from the outside; with no recent collects at all, there is
    nothing to flag.
    """
    horizon = datetime.now(UTC) - timedelta(days=focus_days)
    horizon_ts = int(horizon.timestamp())
    recent = [record for record in collected if record["timestamp"] >= horizon_ts]
    families = {_family(record["lane"], tokens) for record in recent}
    refuses = bool(recent) and len(families) == 1
    return {
        "status": REFUSE if refuses else PASS,
        "value": sorted(families) or None,
        "threshold": f">1 lane family across {len(recent)} collected lanes in {focus_days}d",
    }


def compute_checks(
    root: Path, base: str, tip: str, collected: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    return {
        "deletion": deletion_check(root, base, tip),
        "loop": loop_check(collected),
        "mass": mass_check(root, base, tip),
        "focus": focus_check(collected),
    }
