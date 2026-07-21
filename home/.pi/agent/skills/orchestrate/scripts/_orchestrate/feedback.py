from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .primitives import OrchestrateError, require_identifier
from .git_ops import common_repo_root

_WHITESPACE = re.compile(r"\s+")


# Feedback is subagent-authored signal about the *process itself*: any reaction to or
# suggestion about orchestrate and about working under root. The scope is deliberately
# open — enumerating what qualifies would filter out exactly the unforeseen signal this
# exists to catch — and it is by-exception: an agent with nothing to say records nothing.
# v103 preserved a subagent's judgment about the code (finding evidence); this preserves
# its judgment about the workflow, which otherwise vanishes when the agent terminates.
#
# It is a plain append-only file and nothing more. There is no machine dedup or
# aggregation: natural-language notes differing by a word would defeat a hash, so merging
# near-duplicates is left to root's judgment when it reads the file — on demand, when the
# human asks or at task close, not carried in context every wave. The file, not root's
# memory, is what must not forget across the several waves before the human asks. It gates
# nothing: it never blocks collect, review, or landing, and it is not folded into
# `wave status`, which root reads every boundary — keeping it out is what makes it
# on-demand rather than a standing context cost.
def feedback_ledger_path(root: Path, task_id: str) -> Path:
    return (
        common_repo_root(root)
        / ".agent_state"
        / "orchestrate"
        / "feedback"
        / f"{task_id}.jsonl"
    )


def command_feedback_record(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    task_id = require_identifier(args.task_id, label="task-id")
    note = _WHITESPACE.sub(" ", args.note or "").strip()
    if not note:
        raise OrchestrateError("feedback note must be non-empty")
    source = args.source.strip() if args.source else None
    subject = args.subject.strip() if args.subject else None
    record = {
        "source": source,
        "subject": subject,
        "note": note,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    path = feedback_ledger_path(root, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return {
        "ok": True,
        "operation": "feedback-record",
        "task_id": task_id,
        "path": str(path),
        "recorded": note,
    }
