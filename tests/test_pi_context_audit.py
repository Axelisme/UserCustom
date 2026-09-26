from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home" / ".local" / "bin" / "pi-context-audit"
CWD = "/work/demo"
SINCE = "2026-01-01T00:00:00Z"
UNTIL = "2026-01-02T00:00:00Z"


class Session:
    """Builds one Pi session file entry by entry, one second apart inside the audit window."""

    def __init__(self, cwd: str = CWD, start: str = "2026-01-01T10:00:00") -> None:
        self.cwd = cwd
        self.clock = int(start[-8:-6]) * 3600
        self.day = start[:10]
        self.lines: list[dict] = [{"type": "session", "cwd": cwd, "timestamp": self.stamp()}]
        self.calls = 0

    def stamp(self) -> str:
        self.clock += 1
        h, rest = divmod(self.clock, 3600)
        return f"{self.day}T{h:02d}:{rest // 60:02d}:{rest % 60:02d}Z"

    def add(self, entry: dict) -> None:
        self.lines.append({**entry, "timestamp": self.stamp()})

    def assistant(self, *calls: tuple[str, dict], usage: dict | None = None) -> list[str]:
        ids = []
        content = []
        for name, arguments in calls:
            self.calls += 1
            ids.append(f"c{self.calls}")
            content.append({"type": "toolCall", "id": ids[-1], "name": name, "arguments": arguments})
        self.add({"type": "message", "message": {"role": "assistant", "content": content,
                                                  "usage": usage or {"input": 10, "cacheRead": 0}}})
        return ids

    def result(self, call_id: str, name: str, text: str, details: dict | None = None) -> None:
        message = {"role": "toolResult", "toolCallId": call_id, "toolName": name,
                   "content": [{"type": "text", "text": text}], "isError": False}
        if details is not None:
            message["details"] = details
        self.add({"type": "message", "message": message})

    def tool(self, name: str, arguments: dict, text: str, details: dict | None = None) -> None:
        (call_id,) = self.assistant((name, arguments))
        self.result(call_id, name, text, details)

    def compaction(self, details: dict | None = None) -> None:
        self.add({"type": "compaction", "summary": "", "tokensBefore": 1, "details": details or {}})

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(line) + "\n" for line in self.lines), encoding="utf-8")


def audit(agent_dir: Path, *extra: str) -> dict:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--agent-dir", str(agent_dir), "--since", SINCE, "--until", UNTIL,
         "--json", *extra],
        capture_output=True, text=True, check=True,
    )
    return json.loads(done.stdout)


class PiContextAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def main_session(self, session: Session, name: str = "a.jsonl") -> None:
        session.write(self.agent / "sessions" / "--work-demo--" / name)

    def test_a_policy_document_read_again_after_compaction_is_a_reread(self) -> None:
        session = Session()
        skill = "/home/u/.pi/agent/skills/dev-flow/SKILL.md"
        session.tool("read", {"path": skill}, "x" * 400)
        session.compaction({"remoteCompaction": {}})
        session.tool("read", {"path": skill}, "x" * 400)
        self.main_session(session)

        report = audit(self.agent)

        self.assertEqual(report["policy_rereads"]["by_cause"], {"first": 100, "after_compaction": 100})
        self.assertEqual(report["context"]["categories"]["skill"]["added"], 200)
        self.assertEqual(report["compaction"]["by_kind"], {"remote": 1})
        self.assertEqual(report["compaction"]["reorientation_wave_avg"], 100)
        self.assertEqual(report["policy_rereads"]["top_sources"],
                         [{"category": "skill", "source": "skills/dev-flow/SKILL.md", "tokens": 200, "reads": 2}])

    def test_worktree_copies_of_one_document_share_a_source(self) -> None:
        session = Session()
        session.tool("read", {"path": f"{CWD}/tests/README.md"}, "y" * 40)
        session.tool("read", {"path": f"{CWD}/.agent_state/worktrees/t/lanes/a/tests/README.md"}, "y" * 40)
        self.main_session(session)

        report = audit(self.agent)

        self.assertEqual(report["policy_rereads"]["by_cause"], {"first": 10, "same_window": 10})
        self.assertEqual(report["policy_rereads"]["top_sources"][0]["source"], "tests/README.md")

    def test_shell_output_counts_as_documentation_only_when_every_named_file_is_markdown(self) -> None:
        session = Session()
        session.tool("bash", {"command": "sed -n 1,20p docs/guide.md"}, "d" * 40)
        session.tool("bash", {"command": "git diff -- lib/a.py docs/guide.md"}, "b" * 80)
        session.tool("bash", {"command": "sed -n 1,9p .agent_state/plans/t/INDEX.md"}, "t" * 120)
        self.main_session(session)

        categories = audit(self.agent)["context"]["categories"]

        self.assertEqual(categories["repo_docs"]["added"], 10)
        self.assertEqual(categories["task"]["added"], 30)
        self.assertEqual(categories["business"]["added"], 20)

    def test_compaction_failures_and_absorb_outcomes_are_reported(self) -> None:
        session = Session()
        session.add({"type": "custom", "customType": "pi-absorb.offer.v1", "data": {"ids": ["1", "2", "3", "4"]}})
        session.tool("absorb", {"entries": []}, "[]", {"version": 3, "accepted": [], "outcomes": [
            {"ids": ["1", "2"], "status": "accepted", "toolNames": ["bash"], "beforeTokens": 900, "afterTokens": 100},
            {"ids": ["3"], "status": "failed", "reason": "already_claimed"},
        ]})
        session.compaction({"remoteCompactionFailure": {"category": "service", "message": "boom"}})
        self.main_session(session)

        report = audit(self.agent)

        absorb = report["absorb"]
        self.assertEqual((absorb["offered_ids"], absorb["absorbed_ids"], absorb["failed_entries"]), (4, 2, 1))
        self.assertEqual(absorb["adoption"], 0.5)
        self.assertEqual(absorb["saved_tokens"], 800)
        self.assertEqual(report["compaction"]["by_kind"], {"remote_failed": 1})
        self.assertEqual(report["compaction"]["failures"], {"service": 1})

    def test_compaction_interval_counts_requests_between_compactions(self) -> None:
        session = Session()
        session.assistant()
        session.compaction()
        session.assistant()
        session.assistant()
        session.compaction()
        self.main_session(session)

        compaction = audit(self.agent)["compaction"]

        self.assertEqual(compaction["by_kind"], {"local": 2})
        self.assertEqual(compaction["interval_requests_median"], 2)

    def test_record_upkeep_counts_record_edits_per_commit_and_repeated_commit_ids(self) -> None:
        session = Session()
        sha = "a" * 40
        plans = f"{CWD}/.agent_state/plans/t"
        session.tool("bash", {"command": "git -C lane commit -m done"}, "ok")
        session.assistant(("edit", {"path": f"{plans}/INDEX.md", "edits": [{"oldText": "b" * 40, "newText": sha}]}),
                          ("edit", {"path": f"{plans}/tickets/01/ticket.md",
                                    "edits": [{"oldText": "x", "newText": f"at {sha}"}]}))
        session.assistant()
        session.assistant(("write", {"path": f"{plans}/reviews/01.history.md", "content": "ended round"}))
        session.assistant(("edit", {"path": f"{plans}/reviews/01.md", "edits": [{"oldText": sha, "newText": "y"}]}))
        session.tool("write", {"path": f"{CWD}/lib/a.py", "content": sha}, "ok")
        self.main_session(session)

        upkeep = audit(self.agent)["record_upkeep"]

        self.assertEqual((upkeep["edits"], upkeep["responses"], upkeep["commits"]), (4, 3, 1))
        self.assertEqual(upkeep["by_record"], {"index": 1, "ticket": 1, "history": 1, "review": 1})
        self.assertEqual(upkeep["edits_per_commit"], 4)
        self.assertEqual(upkeep["gap_requests_median"], 1.5)
        self.assertEqual(upkeep["sha_writes_max"], 2)

    def test_usage_totals_cost_and_cache_hit_rate(self) -> None:
        session = Session()
        session.assistant(usage={"input": 100, "cacheRead": 300, "output": 5,
                                 "cost": {"input": 0.2, "cacheRead": 0.06, "output": 0.1, "total": 0.36}})
        session.assistant(usage={"input": 100, "cacheRead": 500, "output": 5,
                                 "cost": {"input": 0.2, "cacheRead": 0.1, "output": 0.1, "total": 0.4}})
        self.main_session(session)

        usage = audit(self.agent)["usage"]

        self.assertEqual((usage["requests"], usage["uncached_input"], usage["cache_read"]), (2, 200, 800))
        self.assertAlmostEqual(usage["cache_hit_rate"], 0.8)
        self.assertAlmostEqual(usage["cost_usd"], 0.76)
        self.assertAlmostEqual(usage["cost_split_usd"]["cache_read"], 0.16)

    def test_window_project_and_subagent_selection(self) -> None:
        inside = Session()
        inside.assistant()
        self.main_session(inside, "inside.jsonl")
        before = Session(start="2025-12-31T10:00:00")
        before.assistant()
        self.main_session(before, "before.jsonl")
        other = Session(cwd="/work/other")
        other.assistant()
        other.write(self.agent / "sessions" / "--work-other--" / "o.jsonl")
        child = self.agent / "herdr-subagents" / "sessions" / "session-x" / "child"
        child.mkdir(parents=True)
        (child / "record.json").write_text(json.dumps({"role": "collab-acceptor", "cwd": f"{CWD}/lane"}))
        sub = Session(cwd=f"{CWD}/lane")
        sub.assistant()
        sub.write(child / "sessions" / "attempt.jsonl")

        everything = audit(self.agent)
        demo = audit(self.agent, "--project", "/work/demo")

        self.assertEqual(everything["sessions"], {"main": 2, "sub": 1})
        self.assertEqual(demo["sessions"], {"main": 1, "sub": 1})
        self.assertEqual(demo["subagent_roles"], {"collab-acceptor": 1})


if __name__ == "__main__":
    unittest.main()
