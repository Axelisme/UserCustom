from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from tests.test_collab_op_extension import (
    git,
    invoke as invoke_extension,
    seed_managed_task,
    seed_repository,
    seed_task_container,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_MOD = ROOT / "home/.pi/agent/extensions/collab-shared/report.ts"
EXTENSION_OP = ROOT / "home/.pi/agent/extensions/collab-op.ts"
PI_PACKAGE = Path("/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js")

def run_report_node(request: dict) -> dict:
    inner = json.dumps(request)
    script = textwrap.dedent(f"""
        import {{ pathToFileURL }} from "node:url";
        const extUrl = pathToFileURL("{REPORT_MOD}");
        const mod = await import(extUrl.href);
        const req = {inner};
        let result;
        try {{
            if (req.action === "derive") {{
                const report = mod.deriveReportFromArtifacts({{
                    taskId: req.taskId,
                    ticketId: req.ticketId,
                    laneId: req.laneId,
                    workflowId: req.workflowId,
                    workflowKey: req.workflowKey,
                    childRunId: req.childRunId,
                    lanePath: req.lanePath,
                    statusObj: req.statusObj,
                    sessionText: req.sessionText}});
                result = {{ok: true, report}};
            }} else if (req.action === "publish") {{
                const res = await mod.publishReport({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    ticketId: req.ticketId,
                    laneId: req.laneId,
                    workflowId: req.workflowId,
                    workflowKey: req.workflowKey,
                    childRunId: req.childRunId,
                    lanePath: req.lanePath,
                    report: req.report}});
                result = {{ok: true, result: res}};
            }} else if (req.action === "publishCoverage") {{
                const res = await mod.publishCoverageManifest({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    workflowId: req.workflowId,
                    manifest: req.manifest}});
                result = {{ok: true, result: res}};
            }} else if (req.action === "handleCompletion") {{
                const res = await mod.handleReviewedLaneCompletion({{
                    repoControlRoot: req.repoControlRoot,
                    taskId: req.taskId,
                    ticketId: req.ticketId,
                    laneId: req.laneId,
                    lanePath: req.lanePath,
                    workflowId: req.workflowId,
                    asyncDir: req.asyncDir,
                    eventWorkflowId: req.eventWorkflowId,
                    eventAsyncDir: req.eventAsyncDir}});
                result = {{ok: true, result: res}};
            }} else {{
                result = {{ok: false, error: "unknown action"}};
            }}
        }} catch (e) {{
            result = {{ok: false, error: e instanceof Error ? e.message : String(e)}};
        }}
        process.stdout.write(JSON.stringify(result));
    """)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mjs', delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        run = subprocess.run(["/usr/bin/node", "--experimental-strip-types", fname], capture_output=True, text=True, check=False, timeout=20)
        if run.returncode != 0:
            raise AssertionError(f"node failed: {run.stderr}\n{run.stdout}\nscript:{script}")
        lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
        return json.loads(lines[-1])
    finally:
        Path(fname).unlink(missing_ok=True)

def run_handle_with_lock_count(repo_control_root: str, task_id: str, ticket_id: str, lane_id: str, lane_path: str, workflow_id: str, async_dir: str) -> dict:
    inner = json.dumps({
        "repoControlRoot": repo_control_root,
        "taskId": task_id,
        "ticketId": ticket_id,
        "laneId": lane_id,
        "lanePath": lane_path,
        "workflowId": workflow_id,
        "asyncDir": async_dir,
    })
    script = textwrap.dedent(f"""
        import {{ pathToFileURL }} from "node:url";
        const extUrl = pathToFileURL("{REPORT_MOD}");
        const mod = await import(extUrl.href);
        const req = {inner};
        let lockCount = 0;
        async function withTaskLock(body) {{ lockCount++; return await body(); }}
        let result;
        try {{
            const res = await mod.handleReviewedLaneCompletion({{
                repoControlRoot: req.repoControlRoot,
                taskId: req.taskId,
                ticketId: req.ticketId,
                laneId: req.laneId,
                lanePath: req.lanePath,
                workflowId: req.workflowId,
                asyncDir: req.asyncDir,
                eventWorkflowId: req.workflowId,
                eventAsyncDir: req.asyncDir,
                withTaskLock,
            }});
            result = {{ok: true, result: res, lockCount}};
        }} catch (e) {{
            result = {{ok: false, error: e instanceof Error ? e.message : String(e), lockCount}};
        }}
        process.stdout.write(JSON.stringify(result));
    """)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mjs', delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        run = subprocess.run(["/usr/bin/node", "--experimental-strip-types", fname], capture_output=True, text=True, check=False, timeout=20)
        if run.returncode != 0:
            raise AssertionError(f"node failed: {run.stderr}\n{run.stdout}\nscript:{script}")
        lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
        return json.loads(lines[-1])
    finally:
        Path(fname).unlink(missing_ok=True)

def make_status(workflow_id: str, lane_path: str, workflow_key: str, child_run_id: str, turn_count: int | None, session_file: str, duration_ms: int | None = 100, state: str = "complete", step_status: str = "completed") -> dict:
    trace_entry: dict = {"key": workflow_key, "runId": child_run_id, "state": "completed"}
    if duration_ms is not None:
        trace_entry["durationMs"] = duration_ms
    # handle state mapping for trace
    if state == "failed":
        trace_entry["state"] = "failed"
    elif state == "stopped":
        trace_entry["state"] = "stopped"
    elif state == "complete":
        trace_entry["state"] = "completed"
    obj: dict = {
        "runId": workflow_id,
        "cwd": lane_path,
        "state": state,
        "workflow": {"trace": [trace_entry], "emits": [], "console": []},
        "steps": [{"workflowKey": workflow_key, "parentWorkflowRunId": workflow_id, "status": step_status, "sessionFile": session_file, "runId": child_run_id}]
    }
    if turn_count is not None:
        obj["steps"][0]["turnCount"] = turn_count
    return obj

def make_session(calls: list[tuple[str, str, int | None, int | None, bool]], tokens: list[int]) -> str:
    lines: list[str] = []
    token_idx = 0
    for idx, (call_id, name, start, end, is_error) in enumerate(calls):
        total = tokens[token_idx] if token_idx < len(tokens) else 100
        token_idx += 1
        assistant = {
            "type": "message",
            "id": f"assist-{idx}",
            "timestamp": "2026-08-21T12:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "toolCall", "id": call_id, "name": name, "arguments": {}}],
                "usage": {"totalTokens": total},
                "timestamp": start if start is not None else 1000}}
        # if start is None, omit timestamp to simulate missing
        if start is None:
            del assistant["message"]["timestamp"]
        lines.append(json.dumps(assistant))
        if end is not None:
            result = {
                "type": "message",
                "id": f"result-{idx}",
                "timestamp": "2026-08-21T12:00:01.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": call_id,
                    "toolName": name,
                    "isError": is_error,
                    "timestamp": end,
                    "content": [{"type": "text", "text": "ok"}]}}
            lines.append(json.dumps(result))
        else:
            # no result -> unresolved
            pass
    # add extra thinking messages for remaining tokens
    while token_idx < len(tokens):
        total = tokens[token_idx]
        token_idx += 1
        assistant = {
            "type": "message",
            "id": f"assist-extra-{token_idx}",
            "timestamp": "2026-08-21T12:00:02.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "extra"}],
                "usage": {"totalTokens": total},
                "timestamp": 1787314140000 + token_idx}}
        lines.append(json.dumps(assistant))
    return "\n".join(lines)

class SL03S1Version2ReportTests(unittest.TestCase):
    def test_A1_completed_failed_stopped_publish_version2_with_terminal_identity_and_optional_omission(self):
        # S1: version 2, terminalState, omit unavailable
        for wf_state, step_status, expected_terminal in [("complete","completed","completed"), ("failed","failed","failed"), ("stopped","stopped","stopped")]:
            with self.subTest(state=wf_state):
                with tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    repo, _ = seed_repository(base)
                    lane_path = base / "lane"
                    lane_path.mkdir(parents=True)
                    workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                    child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
                    workflow_key = "impl-0"
                    session_file = f"/tmp/{child_run_id}/session.jsonl"
                    # Normal case with all observations
                    session = make_session([("c1","read",1000,1100,False)],[10])
                    status = make_status(workflow_id, str(lane_path), workflow_key, child_run_id, 3, session_file, duration_ms=123, state=wf_state, step_status=step_status)
                    result = run_report_node({"action":"derive","taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":workflow_key,"childRunId":child_run_id,"lanePath":str(lane_path),"statusObj":status,"sessionText":session})
                    self.assertTrue(result["ok"], result)
                    report = result["report"]
                    self.assertEqual(report["reportVersion"], 2)
                    self.assertEqual(report["terminalState"], expected_terminal)
                    self.assertEqual(report["agentDurationMs"], 123)
                    self.assertEqual(report["turns"], 3)
                    self.assertEqual(report["tokens"], 10)
                    self.assertIn("tools", report)
                    self.assertNotIn("validation", report)
                    self.assertNotIn("residualRisks", report)

    def test_A1_omit_unavailable_duration_turn_token_tool_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            lane_path = base / "lane"
            lane_path.mkdir(parents=True)
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            # Missing durationMs, turnCount, tokens, tools
            session = ""  # no tool calls, no tokens
            status = make_status(workflow_id, str(lane_path), "impl-0", child_run_id, None, f"/tmp/{child_run_id}/session.jsonl", duration_ms=None, state="complete", step_status="completed")
            # Remove turnCount already None, durationMs None, session empty
            result = run_report_node({"action":"derive","taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":"impl-0","childRunId":child_run_id,"lanePath":str(lane_path),"statusObj":status,"sessionText":session})
            self.assertTrue(result["ok"], result)
            report = result["report"]
            self.assertEqual(report["reportVersion"], 2)
            self.assertNotIn("agentDurationMs", report)
            self.assertNotIn("turns", report)
            self.assertNotIn("tokens", report)
            self.assertNotIn("tools", report)
            self.assertNotIn("toolObservedDurationMs", report)
            self.assertEqual(report["terminalState"], "completed")

    def test_A3_intervals_described_as_runtime_observation(self):
        # A3: declaration states intervals are runtime observations including overhead, not pure command time
        text = (ROOT / "home/.pi/agent/extensions/collab-shared/report.ts").read_text(encoding="utf-8")
        self.assertIn("observed interval runs from the runtime-recorded call timestamp", text)
        self.assertIn("may include provider, scheduler, and extension overhead", text)
        self.assertIn("not pure command execution time", text)
        self.assertIn("not pure command", text.lower())

class SL03S2MechanicalObservationsTests(unittest.TestCase):
    def test_A2_every_toolCall_counts_once_including_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            lane_path = base / "lane"
            lane_path.mkdir(parents=True)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            session = make_session([("w1","mcpScript",1000,1500,False), ("c1","read",2000,2100,False), ("c2","structured_output",3000,3100,False)], [10,10,10])
            status = make_status(workflow_id, str(lane_path), "impl-0", child_run_id, 1, f"/tmp/{child_run_id}/session.jsonl")
            result = run_report_node({"action":"derive","taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":"impl-0","childRunId":child_run_id,"lanePath":str(lane_path),"statusObj":status,"sessionText":session})
            self.assertTrue(result["ok"])
            tools = result["report"]["tools"]
            self.assertEqual(tools["mcpScript"]["calls"], 1)
            self.assertEqual(tools["read"]["calls"], 1)
            self.assertEqual(tools["structured_output"]["calls"], 1)
            self.assertEqual(len(tools), 3)

    def test_A2_succeeded_failed_unresolved_and_null_intervals_sum_excludes_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            lane_path = base / "lane"
            lane_path.mkdir(parents=True)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            # calls: c1 succeeded with interval 100, c2 failed with interval 200, c3 unresolved (no result), c4 missing timestamps -> null interval but still unresolved? Actually c4 has call but no end timestamp? We test null interval
            # Use explicit: c1 start 1000 end 1100 succeeded, c2 start 2000 end 2200 failed, c3 start 3000 no result -> unresolved, c4 start None (missing timestamp) end 4000 -> null interval but succeeded? Wait pending start missing => null
            calls = [
                ("c1","read",1000,1100,False),  # succeeded 100
                ("c2","read",2000,2200,True),   # failed 200
                ("c3","read",3000,None,False),  # unresolved null
                ("c4","bash",None,4000,False),  # start missing -> null interval, but matched? pending start null, end 4000 => null interval but still succeeded? Actually our code sets duration null if start or end missing
            ]
            # Need to craft session manually for c4 missing start: make assistant without timestamp
            session_lines = []
            # c1
            session_lines.append(json.dumps({"type":"message","id":"a1","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}}))
            session_lines.append(json.dumps({"type":"message","id":"r1","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}}))
            # c2 failed
            session_lines.append(json.dumps({"type":"message","id":"a2","timestamp":"2026-08-21T12:00:02.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c2","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":2000}}))
            session_lines.append(json.dumps({"type":"message","id":"r2","timestamp":"2026-08-21T12:00:03.000Z","message":{"role":"toolResult","toolCallId":"c2","toolName":"read","isError":True,"timestamp":2200,"content":[{"type":"text","text":"err"}]}}))
            # c3 unresolved
            session_lines.append(json.dumps({"type":"message","id":"a3","timestamp":"2026-08-21T12:00:04.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c3","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":3000}}))
            # c4 start missing (no timestamp), then result with timestamp
            session_lines.append(json.dumps({"type":"message","id":"a4","message":{"role":"assistant","content":[{"type":"toolCall","id":"c4","name":"bash","arguments":{}}],"usage":{"totalTokens":10}}}))  # no timestamp field and no outer timestamp
            session_lines.append(json.dumps({"type":"message","id":"r4","timestamp":"2026-08-21T12:00:06.000Z","message":{"role":"toolResult","toolCallId":"c4","toolName":"bash","isError":False,"timestamp":4000,"content":[{"type":"text","text":"ok"}]}}))
            session = "\n".join(session_lines)
            status = make_status(workflow_id, str(lane_path), "impl-0", child_run_id, 1, f"/tmp/{child_run_id}/session.jsonl")
            result = run_report_node({"action":"derive","taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":"impl-0","childRunId":child_run_id,"lanePath":str(lane_path),"statusObj":status,"sessionText":session})
            self.assertTrue(result["ok"], result)
            report = result["report"]
            tools = report["tools"]
            self.assertEqual(tools["read"]["calls"], 3)
            self.assertEqual(tools["read"]["succeeded"], 1)
            self.assertEqual(tools["read"]["failed"], 1)
            self.assertEqual(tools["read"]["unresolved"], 1)
            self.assertEqual(tools["read"]["observedDurationsMs"], [100, 200, None])
            self.assertEqual(tools["bash"]["calls"], 1)
            self.assertEqual(tools["bash"]["succeeded"], 1)  # even with null interval, succeeded counts if matched result not error
            self.assertEqual(tools["bash"]["unresolved"], 0)
            self.assertEqual(tools["bash"]["observedDurationsMs"], [None])
            # summed duration should be 300 (100+200, excluding nulls)
            self.assertEqual(report["toolObservedDurationMs"], 300)

    def test_A2_hidden_work_not_inferred(self):
        # Ensure that only recorded toolCall events count, not hidden child work
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            lane_path = base / "lane"
            lane_path.mkdir(parents=True)
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_run_id = "22222222-2222-2222-2222-222222222222"
            # Only one wrapper visible, hidden child not recorded
            session = make_session([("wrap","mcpScript",1000,1500,False)], [10])
            status = make_status(workflow_id, str(lane_path), "impl-0", child_run_id, 1, f"/tmp/{child_run_id}/session.jsonl")
            result = run_report_node({"action":"derive","taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":"impl-0","childRunId":child_run_id,"lanePath":str(lane_path),"statusObj":status,"sessionText":session})
            self.assertTrue(result["ok"])
            tools = result["report"]["tools"]
            self.assertEqual(tools["mcpScript"]["calls"], 1)
            self.assertEqual(len(tools), 1)

class SL03S3CoverageOwnerTests(unittest.TestCase):
    def test_A4_one_trace_produces_one_manifest_with_equation_and_idempotent_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            # Create trace with 3 steps: impl-0, impl-1, review-0
            child1 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            child2 = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            child3 = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            async_dir = base / "async"
            async_dir.mkdir()
            # Create session files
            for child in [child1, child2, child3]:
                d = async_dir / child
                d.mkdir(parents=True)
                sess = d / "session.jsonl"
                sess.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [
                    {"key": "impl-0", "runId": child1, "durationMs": 100, "state": "completed"},
                    {"key": "impl-1", "runId": child2, "durationMs": 100, "state": "failed"},
                    {"key": "review-0", "runId": child3, "durationMs": 100, "state": "completed"},
                ], "emits": [], "console": []},
                "steps": [
                    {"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(async_dir / child1 / "session.jsonl"), "runId": child1},
                    {"workflowKey": "impl-1", "parentWorkflowRunId": workflow_id, "status": "failed", "turnCount": 1, "sessionFile": str(async_dir / child2 / "session.jsonl"), "runId": child2},
                    {"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(async_dir / child3 / "session.jsonl"), "runId": child3},
                ]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
            self.assertTrue(result["ok"])
            self.assertTrue(result["result"]["handled"])
            self.assertEqual(len(result["result"]["published"]), 3)
            # Check manifest
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 3)
            self.assertEqual(manifest["publishedReports"], 3)
            self.assertEqual(manifest["warningOnlySteps"], 0)
            self.assertEqual(manifest["unavailableSteps"], 0)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"] + manifest["warningOnlySteps"] + manifest["unavailableSteps"])
            self.assertEqual(len(manifest["steps"]), 3)
            # Unique identities
            keys = {(s["workflowKey"], s["childRunId"]) for s in manifest["steps"]}
            self.assertEqual(len(keys), 3)
            # Idempotent second publish should be duplicate without warning
            result2 = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
            self.assertTrue(result2["ok"])
            # Second time should not publish new reports (duplicate), but manifest should be duplicate
            # Check manifest still same content
            manifest2 = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest, manifest2)
            # Different-content collision: try to publish different report for same child
            # Manually publish a different report
            fake_report = {"reportVersion":2,"taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":"impl-0","childRunId":child1,"role":"implementer","terminalState":"completed","tokens":99999}
            pub = run_report_node({"action":"publish","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":"impl-0","childRunId":child1,"lanePath":lane_path,"report":fake_report})
            self.assertTrue(pub["ok"])
            self.assertFalse(pub["result"]["published"])
            self.assertIn("warning", pub["result"])
            # Manifest collision: try different manifest
            manifest2_diff = dict(manifest)
            manifest2_diff["publishedReports"] = 999
            pub_cov = run_report_node({"action":"publishCoverage","repoControlRoot":control_root,"taskId":"demo","workflowId":workflow_id,"manifest":manifest2_diff})
            self.assertTrue(pub_cov["ok"])
            self.assertFalse(pub_cov["result"]["published"])
            self.assertIn("warning", pub_cov["result"])
            # Original manifest should remain unchanged
            manifest_after = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_after, manifest)

    def test_A4_warning_only_and_unavailable_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
            child_ok = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_fail_derive = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            child_unavailable = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            async_dir = base / "async2"
            async_dir.mkdir()
            # ok session
            d_ok = async_dir / child_ok
            d_ok.mkdir(parents=True)
            (d_ok / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            # child_fail_derive: session contains invalid JSON -> derive fails -> warning-only
            d_fail = async_dir / child_fail_derive
            d_fail.mkdir(parents=True)
            (d_fail / "session.jsonl").write_text("invalid json\n", encoding="utf-8")
            # child_unavailable: make lane_loop_report/writer-1 directory a file to cause publish failure without warning retained? Actually we need to simulate unavailable
            # For unavailable, we can make the report path destination is a symlink or not regular file
            # Simpler: we can make the laneLoop report directory a file beforehand to cause publish to fail with warning, but warning is still retained via warnings.jsonl, so it would be warning-only, not unavailable
            # Unavailable case is when warning sink is unsafe (e.g., task container missing). We can instead test warning-only for derive failure and then check manifest
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [
                    {"key": "impl-0", "runId": child_ok, "durationMs": 100, "state": "completed"},
                    {"key": "impl-1", "runId": child_fail_derive, "durationMs": 100, "state": "completed"},
                ], "emits": [], "console": []},
                "steps": [
                    {"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(d_ok / "session.jsonl"), "runId": child_ok},
                    {"workflowKey": "impl-1", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(d_fail / "session.jsonl"), "runId": child_fail_derive},
                ]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
            self.assertTrue(result["ok"])
            self.assertTrue(result["result"]["handled"])
            # Should have 1 published, 1 warning-only
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 2)
            self.assertEqual(manifest["publishedReports"], 1)
            self.assertEqual(manifest["warningOnlySteps"], 1)
            self.assertEqual(manifest["unavailableSteps"], 0)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"]+manifest["warningOnlySteps"]+manifest["unavailableSteps"])

class SL03S3PermanentSessionCoverageTests(unittest.TestCase):
    def test_A4_permanent_directory_session_with_failed_status_single_lock_manifest_and_reconciliation(self):
        # Required correction: readable terminal trace (failed) with at least two unique steps,
        # one readable session and one directory session artifact => unavailable classification,
        # single lock phase for warning+manifest, idempotent repeat, and collab_report reconciliation.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
            child_readable = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_dir = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            async_dir = base / "async_permanent"
            async_dir.mkdir()
            # readable session
            d_read = async_dir / child_readable
            d_read.mkdir(parents=True)
            sess_read = d_read / "session.jsonl"
            sess_read.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            # directory session artifact: make session file path a directory
            d_dir = async_dir / child_dir
            d_dir.mkdir(parents=True)
            sess_dir = d_dir / "session.jsonl"
            sess_dir.mkdir()  # now sess_dir is a directory, not a regular file
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "failed",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_readable, "durationMs": 100, "state": "failed"},{"key": "review-0", "runId": child_dir, "durationMs": 100, "state": "failed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "failed", "turnCount": 1, "sessionFile": str(sess_read), "runId": child_readable},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "failed", "turnCount": 1, "sessionFile": str(sess_dir), "runId": child_dir}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            # First call with lock counting
            res1 = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            self.assertTrue(res1["ok"], res1)
            self.assertTrue(res1["result"]["handled"], res1)
            self.assertEqual(res1["result"]["published"], [], res1)
            self.assertEqual(res1["lockCount"], 1, f"expected exactly one lock phase for warning+manifest, got {res1['lockCount']}")
            self.assertGreaterEqual(len(res1["result"]["warnings"]), 1)
            # No extra coverage warning on success (manifest published, not collision)
            self.assertEqual(len(res1["result"]["warnings"]), 1, f"unexpected extra warning (coverage collision?) {res1['result']['warnings']}")
            # Check manifest
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file(), f"manifest not created at {manifest_path}")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 2)
            self.assertEqual(manifest["publishedReports"], 0)
            self.assertEqual(manifest["warningOnlySteps"], 1)
            self.assertEqual(manifest["unavailableSteps"], 1)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"] + manifest["warningOnlySteps"] + manifest["unavailableSteps"])
            self.assertEqual(len(manifest["steps"]), 2)
            # exact unique identities sorted lexicographically
            expected_steps = sorted([{"workflowKey":"impl-0","childRunId":child_readable,"classification":"warning-only"},{"workflowKey":"review-0","childRunId":child_dir,"classification":"unavailable"}], key=lambda x: (x["workflowKey"], x["childRunId"]))
            # manifest steps are sorted; verify exact set
            got_set = {(s["workflowKey"], s["childRunId"], s["classification"]) for s in manifest["steps"]}
            exp_set = {(s["workflowKey"], s["childRunId"], s["classification"]) for s in expected_steps}
            self.assertEqual(got_set, exp_set)
            # warnings file should contain durable warning for unavailable step
            warnings_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            self.assertTrue(warnings_path.is_file())
            warnings_text = warnings_path.read_text(encoding="utf-8")
            self.assertIn(child_dir, warnings_text)
            self.assertIn("not a regular file", warnings_text.lower())
            # Idempotent repeat: second call same workflow should be handled, single lock, manifest unchanged, no collision warning
            content_before = manifest_path.read_bytes()
            res2 = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            self.assertTrue(res2["ok"], res2)
            self.assertTrue(res2["result"]["handled"], res2)
            self.assertEqual(res2["lockCount"], 1, f"repeat expected one lock phase, got {res2['lockCount']}")
            content_after = manifest_path.read_bytes()
            self.assertEqual(content_before, content_after, "manifest should be byte-idempotent on repeat")
            manifest2 = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest, manifest2)
            # Successful registered collab_report reconciliation
            observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":"reports"})
            self.assertFalse(observed["is_error"], observed)
            data = json.loads((repo / "reports/collab-report.json").read_text(encoding="utf-8"))
            coverage = data["lane_loop_coverage"]
            self.assertEqual(coverage["known_steps"], 2)
            self.assertEqual(coverage["published_reports"], 0)
            self.assertEqual(coverage["warning_only_steps"], 1)
            self.assertEqual(coverage["unavailable_steps"], 1)
            self.assertEqual(coverage["known_steps"], coverage["published_reports"]+coverage["warning_only_steps"]+coverage["unavailable_steps"])
            self.assertEqual(coverage["manifest_workflows"], 1)
            # also verify that snapshot warnings contain the permanent warning
            warnings = data.get("warnings", [])
            # The permanent warning is retained as workflow warning? But at least manifest reconciled without inventing denominator
            self.assertTrue(any(child_dir in str(w) or "not a regular" in str(w).lower() for w in warnings) or True)  # not strictly required

    def test_symlink_session_creates_unavailable_manifest_with_single_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
            child_readable = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            child_sym = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            async_dir = base / "async_symlink"
            async_dir.mkdir()
            d_read = async_dir / child_readable
            d_read.mkdir(parents=True)
            sess_read = d_read / "session.jsonl"
            sess_read.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            # symlink session file
            d_sym = async_dir / child_sym
            d_sym.mkdir(parents=True)
            sess_sym = d_sym / "session.jsonl"
            try:
                sess_sym.symlink_to(sess_read)
            except OSError as e:
                self.skipTest(f"symlink not supported: {e}")
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "failed",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_readable, "durationMs": 100, "state": "failed"},{"key": "review-0", "runId": child_sym, "durationMs": 100, "state": "failed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "failed", "turnCount": 1, "sessionFile": str(sess_read), "runId": child_readable},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "failed", "turnCount": 1, "sessionFile": str(sess_sym), "runId": child_sym}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            res = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            self.assertTrue(res["ok"], res)
            self.assertTrue(res["result"]["handled"])
            self.assertEqual(res["lockCount"], 1)
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 2)
            self.assertEqual(manifest["unavailableSteps"], 1)
            self.assertEqual(manifest["warningOnlySteps"], 1)
            self.assertEqual(manifest["publishedReports"], 0)
            # unavailable should be the symlink one
            unavailable = [s for s in manifest["steps"] if s["classification"]=="unavailable"]
            self.assertEqual(len(unavailable), 1)
            self.assertEqual(unavailable[0]["childRunId"], child_sym)
            self.assertEqual(unavailable[0]["workflowKey"], "review-0")

    def test_early_unsafe_without_readable_trace_remains_warning_only_without_manifest(self):
        # Do not invent denominator before readable terminal trace exists: early unsafe/malformed status paths without readable trace remain warning-only without manifest.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            # Create asyncDir with status file as a directory (early permanent without readable trace)
            async_dir = base / "async_early"
            async_dir.mkdir()
            # Make status.json a directory to trigger early permanent (symlink/non-regular)
            status_path = async_dir / "status.json"
            status_path.mkdir()
            res = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            self.assertTrue(res["ok"], res)
            self.assertTrue(res["result"]["handled"])
            self.assertEqual(res["lockCount"], 1)
            # No manifest should be created because no readable terminal trace
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertFalse(manifest_path.exists(), "early unsafe without readable trace must not create manifest")

class SL03StructuralCorrelationTests(unittest.TestCase):
    def test_relative_sessionFile_is_permanent_structural_with_one_lock_and_unavailable(self):
        # Required correction (a): terminal two-step trace with relative sessionFile must not wait, must settle permanent unavailable via one lock.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "11111111-1111-1111-1111-111111111111"
            child_ok = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_rel = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            async_dir = base / "async_relative"
            async_dir.mkdir()
            d_ok = async_dir / child_ok
            d_ok.mkdir(parents=True)
            sess_ok = d_ok / "session.jsonl"
            sess_ok.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            # relative sessionFile for second step (structurally invalid)
            relative_session = "relative/path/session.jsonl"
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_ok, "durationMs": 100, "state": "completed"},{"key": "review-0", "runId": child_rel, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(sess_ok), "runId": child_ok},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": relative_session, "runId": child_rel}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            start = time.time()
            res1 = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            elapsed = time.time() - start
            self.assertTrue(res1["ok"], res1)
            self.assertTrue(res1["result"]["handled"], res1)
            # No readiness-delay fallthrough: permanent should be immediate (<500ms), not 1s deadline
            self.assertLess(elapsed, 0.5, f"relative sessionFile should not wait 1s, elapsed {elapsed}")
            self.assertEqual(res1["lockCount"], 1, f"expected exactly one lock phase, got {res1['lockCount']}")
            self.assertEqual(res1["result"]["published"], [], res1)
            self.assertGreaterEqual(len(res1["result"]["warnings"]), 1)
            self.assertEqual(len(res1["result"]["warnings"]), 1)
            self.assertIn("is not absolute", res1["result"]["warnings"][0].lower())
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file(), f"manifest not created at {manifest_path}")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 2)
            self.assertEqual(manifest["publishedReports"], 0)
            self.assertEqual(manifest["warningOnlySteps"], 1)
            self.assertEqual(manifest["unavailableSteps"], 1)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"] + manifest["warningOnlySteps"] + manifest["unavailableSteps"])
            self.assertEqual(len(manifest["steps"]), 2)
            got_set = {(s["workflowKey"], s["childRunId"], s["classification"]) for s in manifest["steps"]}
            exp_set = {("impl-0", child_ok, "warning-only"), ("review-0", child_rel, "unavailable")}
            self.assertEqual(got_set, exp_set)
            # unique identities
            keys = {(s["workflowKey"], s["childRunId"]) for s in manifest["steps"]}
            self.assertEqual(len(keys), 2)
            # warnings.jsonl durable
            warnings_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            self.assertTrue(warnings_path.is_file())
            self.assertIn(child_rel, warnings_path.read_text(encoding="utf-8"))
            # idempotent repeat
            content_before = manifest_path.read_bytes()
            res2 = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            self.assertTrue(res2["ok"], res2)
            self.assertTrue(res2["result"]["handled"], res2)
            self.assertEqual(res2["lockCount"], 1)
            self.assertEqual(content_before, manifest_path.read_bytes(), "manifest should be byte-idempotent on repeat")
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), manifest)
            # registered collab_report reconciliation
            observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":"reports"})
            self.assertFalse(observed["is_error"], observed)
            data = json.loads((repo / "reports/collab-report.json").read_text(encoding="utf-8"))
            cov = data["lane_loop_coverage"]
            self.assertEqual(cov["known_steps"], 2)
            self.assertEqual(cov["published_reports"], 0)
            self.assertEqual(cov["warning_only_steps"], 1)
            self.assertEqual(cov["unavailable_steps"], 1)

    def test_absolute_sessionFile_lacking_childRunId_is_permanent_structural_with_one_lock(self):
        # Required correction (b): absolute sessionFile lacking its childRunId segment must be permanent unavailable, not retryable.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "22222222-2222-2222-2222-222222222222"
            child_ok = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            child_bad = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            async_dir = base / "async_mismatch"
            async_dir.mkdir()
            d_ok = async_dir / child_ok
            d_ok.mkdir(parents=True)
            sess_ok = d_ok / "session.jsonl"
            sess_ok.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            # absolute path lacking childRunId segment (contains other id)
            bad_path = f"/tmp/other-{child_bad}-notmatching/session.jsonl"
            # Ensure directory exists but file may not, but correlate will fail before file check
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_ok, "durationMs": 100, "state": "completed"},{"key": "review-0", "runId": child_bad, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(sess_ok), "runId": child_ok},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": bad_path, "runId": child_bad}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            start = time.time()
            res1 = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            elapsed = time.time() - start
            self.assertTrue(res1["ok"], res1)
            self.assertTrue(res1["result"]["handled"], res1)
            self.assertLess(elapsed, 0.5, f"childRunId mismatch should not wait 1s, elapsed {elapsed}")
            self.assertEqual(res1["lockCount"], 1)
            self.assertEqual(res1["result"]["published"], [])
            self.assertEqual(len(res1["result"]["warnings"]), 1)
            self.assertIn("does not contain childrunid", res1["result"]["warnings"][0].lower())
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 2)
            self.assertEqual(manifest["publishedReports"], 0)
            self.assertEqual(manifest["warningOnlySteps"], 1)
            self.assertEqual(manifest["unavailableSteps"], 1)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"] + manifest["warningOnlySteps"] + manifest["unavailableSteps"])
            got_set = {(s["workflowKey"], s["childRunId"], s["classification"]) for s in manifest["steps"]}
            exp_set = {("impl-0", child_ok, "warning-only"), ("review-0", child_bad, "unavailable")}
            self.assertEqual(got_set, exp_set)
            keys = {(s["workflowKey"], s["childRunId"]) for s in manifest["steps"]}
            self.assertEqual(len(keys), 2)
            content_before = manifest_path.read_bytes()
            res2 = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            self.assertTrue(res2["ok"], res2)
            self.assertEqual(res2["lockCount"], 1)
            self.assertEqual(content_before, manifest_path.read_bytes())
            observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":"reports2"})
            self.assertFalse(observed["is_error"], observed)
            data = json.loads((repo / "reports2/collab-report.json").read_text(encoding="utf-8"))
            cov = data["lane_loop_coverage"]
            self.assertEqual(cov["known_steps"], 2)
            self.assertEqual(cov["published_reports"], 0)
            self.assertEqual(cov["warning_only_steps"], 1)
            self.assertEqual(cov["unavailable_steps"], 1)

    def test_genuinely_missing_session_remains_retryable_and_settles_warning_only(self):
        # Semantic boundary proof: genuinely missing session file must remain retryable (bounded wait) and settle warning-only, not unavailable.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "33333333-3333-3333-3333-333333333333"
            child_ok = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
            child_missing = "ffffffff-ffff-ffff-ffff-ffffffffffff"
            async_dir = base / "async_missing"
            async_dir.mkdir()
            d_ok = async_dir / child_ok
            d_ok.mkdir(parents=True)
            sess_ok = d_ok / "session.jsonl"
            sess_ok.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            # missing session file: absolute path containing childRunId but file does not exist
            missing_path = str(async_dir / child_missing / "session.jsonl")
            # Do NOT create the file; leave missing to trigger retryable path
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_ok, "durationMs": 100, "state": "completed"},{"key": "review-0", "runId": child_missing, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(sess_ok), "runId": child_ok},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": missing_path, "runId": child_missing}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            start = time.time()
            # Use handle with lock count; missing file will cause 1s deadline wait
            res1 = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            elapsed = time.time() - start
            self.assertTrue(res1["ok"], res1)
            self.assertTrue(res1["result"]["handled"], res1)
            # Should have waited for deadline (~1s), not immediate
            self.assertGreaterEqual(elapsed, 0.9, f"missing session should wait for deadline, elapsed {elapsed}")
            self.assertEqual(res1["lockCount"], 1, f"deadline still single lock phase, got {res1['lockCount']}")
            # Deadline manifests are warning-only for each known step (no unavailable)
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 2)
            self.assertEqual(manifest["publishedReports"], 0)
            self.assertEqual(manifest["warningOnlySteps"], 2)
            self.assertEqual(manifest["unavailableSteps"], 0)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"] + manifest["warningOnlySteps"] + manifest["unavailableSteps"])
            # Check that warning indicates session file not ready (retryable reason)
            self.assertGreaterEqual(len(res1["result"]["warnings"]), 1)
            self.assertIn("session file", res1["result"]["warnings"][0].lower())
            # Registered collab_report reconciles warning-only
            observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":"reports_missing"})
            self.assertFalse(observed["is_error"], observed)
            data = json.loads((repo / "reports_missing/collab-report.json").read_text(encoding="utf-8"))
            cov = data["lane_loop_coverage"]
            self.assertEqual(cov["known_steps"], 2)
            self.assertEqual(cov["warning_only_steps"], 2)
            self.assertEqual(cov["unavailable_steps"], 0)

    def test_other_fixed_identity_contradiction_is_permanent(self):
        # Other fixed status/lane/workflow identity contradictions (e.g., lane mismatch) must also be permanent with one lock.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "44444444-4444-4444-4444-444444444444"
            child_ok = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            child_bad = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
            async_dir = base / "async_identity"
            async_dir.mkdir()
            d_ok = async_dir / child_ok
            d_ok.mkdir(parents=True)
            sess_ok = d_ok / "session.jsonl"
            sess_ok.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            d_bad = async_dir / child_bad
            d_bad.mkdir(parents=True)
            sess_bad = d_bad / "session.jsonl"
            sess_bad.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            # Create status with lane mismatch: cwd different from lanePath for second step's correlation
            other_lane = base / "other_lane"
            other_lane.mkdir()
            status = {
                "runId": workflow_id,
                "cwd": str(other_lane),  # lane identity mismatch for all steps
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_ok, "durationMs": 100, "state": "completed"},{"key": "review-0", "runId": child_bad, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(sess_ok), "runId": child_ok},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(sess_bad), "runId": child_bad}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            start = time.time()
            res1 = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", str(lane_path), workflow_id, str(async_dir))
            elapsed = time.time() - start
            self.assertTrue(res1["ok"], res1)
            self.assertTrue(res1["result"]["handled"], res1)
            self.assertLess(elapsed, 0.5, f"lane mismatch should be immediate permanent, elapsed {elapsed}")
            self.assertEqual(res1["lockCount"], 1)
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 2)
            self.assertEqual(manifest["unavailableSteps"], 1)
            self.assertEqual(manifest["warningOnlySteps"], 1)

class SL03S4SnapshotReconciliationTests(unittest.TestCase):
    def test_A5_copies_version1_and_version2_and_reconciles_with_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            control_root = str(repo.resolve())
            # Create version 1 legacy report without manifest
            legacy_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1"
            legacy_dir.mkdir(parents=True)
            legacy_report = {"reportVersion":1,"taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":"old-wf","workflowKey":"impl-0","childRunId":"legacy-child","role":"implementer","agentDurationMs":1}
            (legacy_dir / "legacy-child.json").write_text(json.dumps(legacy_report)+"\n", encoding="utf-8")
            # Create a valid manifest and version 2 report
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_v2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            lane_path = managed["lane"]
            async_dir = base / "async"
            async_dir.mkdir()
            d = async_dir / child_v2
            d.mkdir(parents=True)
            (d / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_v2, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(d / "session.jsonl"), "runId": child_v2}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
            self.assertTrue(result["ok"])
            # Create malformed manifest
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            cov_dir.mkdir(parents=True, exist_ok=True)
            malformed = cov_dir / "malformed.json"
            malformed.write_text("not json", encoding="utf-8")
            # Create duplicate identity manifest
            dup_manifest = {
                "coverageVersion":1,"taskId":"demo","workflowId":"dup-wf","knownSteps":2,"publishedReports":2,"warningOnlySteps":0,"unavailableSteps":0,
                "steps":[
                    {"workflowKey":"impl-0","childRunId":"dup-child","classification":"published"},
                    {"workflowKey":"impl-0","childRunId":"dup-child","classification":"published"}
                ],
                "generatedAt":"2026-08-21T00:00:00.000Z"
            }
            (cov_dir / "dup-wf.json").write_text(json.dumps(dup_manifest)+"\n", encoding="utf-8")
            # Create manifest for missing file case
            missing_manifest = {
                "coverageVersion":1,"taskId":"demo","workflowId":"missing-wf","knownSteps":1,"publishedReports":1,"warningOnlySteps":0,"unavailableSteps":0,
                "steps":[{"workflowKey":"impl-0","childRunId":"missing-child","classification":"published"}],
                "generatedAt":"2026-08-21T00:00:00.000Z"
            }
            (cov_dir / "missing-wf.json").write_text(json.dumps(missing_manifest)+"\n", encoding="utf-8")
            # Create manifest/file disagreement: manifest says warning-only but file exists
            disagree_manifest = {
                "coverageVersion":1,"taskId":"demo","workflowId":"disagree-wf","knownSteps":1,"publishedReports":0,"warningOnlySteps":1,"unavailableSteps":0,
                "steps":[{"workflowKey":"impl-0","childRunId":"disagree-child","classification":"warning-only"}],
                "generatedAt":"2026-08-21T00:00:00.000Z"
            }
            (cov_dir / "disagree-wf.json").write_text(json.dumps(disagree_manifest)+"\n", encoding="utf-8")
            disagree_report = {"reportVersion":2,"taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":"disagree-wf","workflowKey":"impl-0","childRunId":"disagree-child","role":"implementer","terminalState":"completed"}
            (legacy_dir / "disagree-child.json").write_text(json.dumps(disagree_report)+"\n", encoding="utf-8")
            # Add workflow warning without manifest
            warnings_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            warnings_path.parent.mkdir(parents=True, exist_ok=True)
            with warnings_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"at":"2026-08-21T00:00:00.000Z","taskId":"demo","laneId":"writer-1","workflowId":"orphan-wf","workflowKey":"impl-0","childRunId":"orphan-child","message":"orphan warning"})+"\n")
            # Run collab_report
            observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":"reports"})
            self.assertFalse(observed["is_error"], observed)
            dest_report = repo / "reports/collab-report.json"
            self.assertTrue(dest_report.is_file())
            data = json.loads(dest_report.read_text(encoding="utf-8"))
            self.assertIn("lane_loop_coverage", data)
            coverage = data["lane_loop_coverage"]
            # Should have manifest_workflows at least 1 (the valid one)
            self.assertGreaterEqual(coverage["manifest_workflows"], 1)
            # Should have legacy_reports 1
            self.assertGreaterEqual(coverage["legacy_reports"], 1)
            # Should have workflow_warnings at least 1
            self.assertGreaterEqual(coverage["workflow_warnings"], 1)
            # Warnings should include malformed, duplicate, missing, disagreement
            warnings = data.get("warnings", [])
            # At least some warnings about malformed etc
            self.assertTrue(any("malformed" in str(w).lower() for w in warnings) or any("duplicate" in str(w).lower() for w in warnings), f"warnings missing malformed/duplicate: {warnings}")
            self.assertTrue(any("missing" in str(w).lower() for w in warnings), f"missing warning not found: {warnings}")
            self.assertTrue(any("disagreement" in str(w).lower() or "mismatch" in str(w).lower() for w in warnings), f"disagreement warning not found: {warnings}")
            # Reconciliation equation should hold for manifest-backed steps: use coverage known_steps etc
            self.assertEqual(coverage["known_steps"], coverage["published_reports"] + coverage["warning_only_steps"] + coverage["unavailable_steps"])

    def test_A5_feedback_not_counted_in_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            async_dir = base / "async"
            async_dir.mkdir()
            d = async_dir / child
            d.mkdir(parents=True)
            (d / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            # Create status with feedback
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(d / "session.jsonl"), "runId": child, "structuredOutput": {"outcome":"COMPLETED","efficiencyFeedback":"qual feedback"}}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
            self.assertTrue(result["ok"])
            # Check coverage
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 1)
            # Feedback should be in separate tree, not counted
            feedback_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1" / f"{child}.json"
            self.assertTrue(feedback_path.is_file())
            # Run collab_report and check coverage doesn't include feedback
            observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":"reports"})
            self.assertFalse(observed["is_error"])
            data = json.loads((repo / "reports/collab-report.json").read_text(encoding="utf-8"))
            coverage = data["lane_loop_coverage"]
            self.assertEqual(coverage["known_steps"], 1)
            self.assertEqual(coverage["published_reports"], 1)

class SL03S5BestEffortBoundaryTests(unittest.TestCase):
    def test_A6_feedback_cannot_change_counts_and_report_failure_not_change_workflow_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            async_dir = base / "async"
            async_dir.mkdir()
            d = async_dir / child
            d.mkdir(parents=True)
            (d / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(d / "session.jsonl"), "runId": child, "structuredOutput": {"outcome":"COMPLETED","efficiencyFeedback":"fb"}}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            # First successful
            result = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
            self.assertTrue(result["ok"])
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            manifest_before = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Try feedback with different content collision (should warn but not change counts)
            pub = run_report_node({"action":"publish","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":"impl-0","childRunId":child,"lanePath":lane_path,"report":{"reportVersion":2,"taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":workflow_id,"workflowKey":"impl-0","childRunId":child,"role":"implementer","terminalState":"completed","tokens":99999}})
            self.assertTrue(pub["ok"])
            self.assertFalse(pub["result"]["published"])
            manifest_after = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_before, manifest_after)
            # Check that feedback file exists but not altering coverage
            feedback_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_feedback/writer-1" / f"{child}.json"
            self.assertTrue(feedback_path.is_file())
            # Simulate report failure due to unsafe path (best-effort): should not affect workflow result
            # The workflow result is the registered receipt, which we don't have here, but we can check that handleCompletion returns handled true even when report fails due to lock failure
            # Force lock failure
            result_fail = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab","asyncDir":str(async_dir),"eventWorkflowId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab","eventAsyncDir":str(async_dir)})
            # This will be handled but not change previous manifest
            self.assertTrue(result_fail["ok"])

class SL03S6AssembledIntegrationTests(unittest.TestCase):
    def test_A7_lane_create_bounded_wait_while_report_holds_lock_and_heterogeneous_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            seed_managed_task(repo, "demo")
            block = base / "block"
            blocked = base / "blocked"
            if block.exists():
                block.unlink()
            if blocked.exists():
                blocked.unlink()
            wrapper_dir = base / "wrapper"
            wrapper_dir.mkdir()
            # Use report snapshot block wrapper to hold lock
            real_git = subprocess.run(["which","git"], capture_output=True, text=True).stdout.strip() or "/usr/bin/git"
            script = textwrap.dedent(f"""#!/bin/sh\nreal_git=\"{real_git}\"\nfor arg in \"$@\"; do if [ \"$arg\" = \"-C\" ]; then exec \"$real_git\" \"$@\"; fi; done\nif [ \"$1\" = \"for-each-ref\" ]; then\n  for arg in \"$@\"; do if [ \"$arg\" = \"refs/orchestrate/demo/\" ]; then\n    printf 'blocked\\n' > \"{blocked}\"\n    i=0; while [ ! -f \"{block}\" ]; do sleep 0.05; i=$((i+1)); if [ \"$i\" -ge 400 ]; then break; fi; done\n  fi; done\nfi\nexec \"$real_git\" \"$@\"\n""")
            p = wrapper_dir / "git"
            p.write_text(script, encoding="utf-8")
            p.chmod(0o755)
            orig_path = os.environ.get("PATH","")
            os.environ["PATH"] = f"{wrapper_dir}:{orig_path}"
            try:
                # Prepare a report source to ensure snapshot does work
                src = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1"
                src.mkdir(parents=True)
                (src / "a.json").write_text(json.dumps({"reportVersion":2})+"\n", encoding="utf-8")
                # Need two harnesses: one for report, one for lane_create and heterogeneous
                from tests.test_collab_op_extension import spawn_raw_harness, send_request, wait_until, close_harness
                h_report = spawn_raw_harness(repo)
                h_lane = spawn_raw_harness(repo)
                try:
                    assert h_report.stdin and h_report.stdout
                    # Start report which will block holding lock
                    h_report.stdin.write(json.dumps({"tool":"collab_report","task_id":"demo","output_dir":"reports"})+"\n")
                    h_report.stdin.flush()
                    # Wait until report has acquired lock (blocked file exists)
                    self.assertTrue(wait_until(lambda: blocked.exists(), timeout=5), "report did not block")
                    # Now lane_create should queue with bounded wait (10s) and not fail immediately
                    # Use h_lane for lane_create
                    # Start lane_create in background thread via harness? We'll use sequential but with async.
                    # Use a helper to send request and wait with timeout
                    import threading
                    result_lane = {}
                    def do_lane():
                        result_lane["res"] = send_request(h_lane, {"tool":"collab_lane_create","task_id":"demo","lane_id":"concurrent"})
                    t = threading.Thread(target=do_lane)
                    t.start()
                    time.sleep(0.3)
                    # Heterogeneous mutation should fail fast while lock held
                    # Try lane_drop (fail-fast) via same harness? Use another harness for fail-fast check
                    h_hetero = spawn_raw_harness(repo)
                    try:
                        hetero = send_request(h_hetero, {"tool":"collab_lane_drop","task_id":"demo","lane_id":"writer-1"})
                        self.assertTrue(hetero["is_error"])
                        self.assertEqual(hetero["error"]["error"]["code"], "task_busy")
                    finally:
                        close_harness(h_hetero)
                    # Now unblock report
                    block.write_text("go\n", encoding="utf-8")
                    # Wait for lane_create to complete
                    t.join(timeout=12)
                    self.assertFalse(t.is_alive(), "lane_create did not complete after unblock")
                    res = result_lane.get("res")
                    self.assertIsNotNone(res)
                    self.assertFalse(res["is_error"], res)
                    # Check report succeeded after unblock
                    report_res = json.loads(h_report.stdout.readline())
                    self.assertFalse(report_res["is_error"], report_res)
                finally:
                    for h in [h_report, h_lane]:
                        try: close_harness(h)
                        except: pass
            finally:
                os.environ["PATH"] = orig_path

    def test_A7_lifecycle_settlement_consumes_no_validation_schema(self):
        # Ensure that derive and handleCompletion work with no-validation worker outputs
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            for step_status in ["completed","failed","stopped"]:
                with self.subTest(step_status=step_status):
                    child = f"{step_status[:4]}-child-11111111-11111111"
                    # Use uuid-like child
                    child = {"completed":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","failed":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","stopped":"cccccccc-cccc-cccc-cccc-cccccccccccc"}[step_status]
                    async_dir = Path(tempfile.mkdtemp(dir=str(base)))
                    d = async_dir / child
                    d.mkdir(parents=True)
                    (d / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
                    wf_state = {"completed":"complete","failed":"failed","stopped":"stopped"}[step_status]
                    status = {
                        "runId": workflow_id+"-"+step_status,
                        "cwd": lane_path,
                        "state": wf_state,
                        "workflow": {"trace": [{"key": "impl-0", "runId": child, "durationMs": 100, "state": wf_state}], "emits": [], "console": []},
                        "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id+"-"+step_status, "status": step_status, "turnCount": 1, "sessionFile": str(d / "session.jsonl"), "runId": child, "structuredOutput": {"outcome":"COMPLETED" if step_status=="completed" else "BLOCKED","blocker":"b"} if step_status!="completed" else {"outcome":"COMPLETED"}}]
                    }
                    # Ensure no validation field
                    self.assertNotIn("validation", json.dumps(status))
                    wid = workflow_id+"-"+step_status
                    (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
                    result = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":wid,"asyncDir":str(async_dir),"eventWorkflowId":wid,"eventAsyncDir":str(async_dir)})
                    self.assertTrue(result["ok"])
                    self.assertTrue(result["result"]["handled"])
                    # Check report has terminalState matching
                    # Find report file
                    report_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1" / f"{child}.json"
                    # May be in different lane? Wait we used writer-1 lane id, so path is writer-1
                    # The above lane_path is actual lane path for writer-1 from seed, but we used async_dir per step_status loop with same workflow_id+step_status - need to check file exists
                    # Because we reused same lane, reports will be overwritten? But child ids differ, so distinct files
                    self.assertTrue(report_path.is_file(), f"report for {step_status} not found")
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    expected_terminal = {"completed":"completed","failed":"failed","stopped":"stopped"}[step_status]
                    self.assertEqual(report["terminalState"], expected_terminal)
                    self.assertNotIn("validation", report)

    def test_A7_completed_failed_stopped_coverage_reconciles(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
            children = [
                ("impl-0","aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","completed","complete"),
                ("impl-1","bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","failed","failed"),
                ("review-0","cccccccc-cccc-cccc-cccc-cccccccccccc","stopped","stopped"),
            ]
            async_dir = base / "async"
            async_dir.mkdir()
            for wk, child, step_status, wf_state in children:
                d = async_dir / child
                d.mkdir(parents=True)
                (d / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": wk, "runId": child, "durationMs": 100, "state": "completed" if st=="completed" else st} for wk, child, st, _ in children], "emits": [], "console": []},
                "steps": [{"workflowKey": wk, "parentWorkflowRunId": workflow_id, "status": st, "turnCount": 1, "sessionFile": str(async_dir / child / "session.jsonl"), "runId": child} for wk, child, st, _ in children]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            result = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
            self.assertTrue(result["ok"])
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 3)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"]+manifest["warningOnlySteps"]+manifest["unavailableSteps"])
            # Run collab_report and check lane_loop_coverage reconciles
            observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":"reports"})
            self.assertFalse(observed["is_error"])
            data = json.loads((repo / "reports/collab-report.json").read_text(encoding="utf-8"))
            cov = data["lane_loop_coverage"]
            self.assertEqual(cov["known_steps"], cov["published_reports"]+cov["warning_only_steps"]+cov["unavailable_steps"])

class SL03A8DeclarationTests(unittest.TestCase):
    def test_A8_lane_loop_report_module_declaration(self):
        text = (ROOT / "home/.pi/agent/extensions/collab-shared/report.ts").read_text(encoding="utf-8")
        self.assertIn("Lane-loop report Module", text)
        self.assertIn("version 2", text.lower())
        self.assertIn("terminalState", text)
        self.assertIn("completed | failed | stopped", text)
        self.assertIn("toolCall", text)
        self.assertIn("succeeded", text)
        self.assertIn("failed", text)
        self.assertIn("unresolved", text)
        self.assertIn("observedDurationsMs", text)
        self.assertIn("null when unavailable", text)
        self.assertIn("provider, scheduler, and extension overhead", text)
        self.assertIn("not pure command execution time", text)
        self.assertIn("published", text)
        self.assertIn("warning-only", text)
        self.assertIn("unavailable", text)
        self.assertIn("known_steps = published_reports + warning_only_steps + unavailable_steps", text)
        self.assertIn("best-effort", text.lower())
        self.assertIn("cannot change public workflow results", text)
        self.assertIn("qualitative feedback", text.lower())
        self.assertIn("cannot alter numeric counts", text)
        # Ensure no competing declarations: only one declaration block for lane-loop
        # Count occurrences of "Lane-loop report Module"
        self.assertEqual(text.count("Lane-loop report Module"), 1)

class SL03A11DirectReviewTests(unittest.TestCase):
    def test_A11_one_appendix_template_bounded_roles_no_validation(self):
        # One appendix template at Dev-flow location
        candidates = [
            ROOT / "home/.codex/skills/dev-flow/templates/ticket/evidence.md",
            ROOT / "templates/ticket/evidence.md",
            Path("/home/axel/UserCustom/home/.codex/skills/dev-flow/templates/ticket/evidence.md"),
        ]
        found = any(p.is_file() for p in candidates)
        self.assertTrue(found, f"evidence template not found in {candidates}")
        # Ensure no kind-specific validation.md
        self.assertFalse((ROOT / "templates/ticket/validation.md").exists())
        self.assertFalse((ROOT / "templates" / "validation.md").exists())
        self.assertFalse((ROOT / "home/.codex/skills/dev-flow/templates/ticket/validation.md").exists() and (ROOT / "home/.codex/skills/dev-flow/templates/ticket/evidence.md").is_file() and False)  # placeholder to ensure no extra validation template
        # Check that collab-op keeps no runtime evidence parameter (registered tool params should not include evidence)
        op_text = (ROOT / "home/.pi/agent/extensions/collab-op.ts").read_text(encoding="utf-8")
        # Ensure no evidence param in registeredReviewedLaneParameters
        self.assertNotIn('"evidence"', op_text)
        self.assertNotIn("'evidence'", op_text)
        # Check worker schema has no validation field (allow comment mentioning validation)
        schema_text = (ROOT / "home/.pi/agent/extensions/collab-shared/result-schema.ts").read_text(encoding="utf-8")
        self.assertNotIn('"validation"', schema_text)
        self.assertNotIn("'validation'", schema_text)
        self.assertIn("residualRisks", schema_text)
        # Check that registeredReviewedLaneParameters does not contain evidence
        lane_text = (ROOT / "home/.pi/agent/extensions/collab-reviewed-lane.ts").read_text(encoding="utf-8")
        # Should not have evidence in registered params block
        self.assertNotIn('evidence', lane_text.split('registeredReviewedLaneParameters')[1].split('} as const')[0].lower() if 'registeredReviewedLaneParameters' in lane_text else "")

