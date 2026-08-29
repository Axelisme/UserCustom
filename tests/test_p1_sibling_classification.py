import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_MOD = ROOT / "home/.pi/agent/extensions/collab-shared/report.ts"
from tests.test_collab_op_extension import seed_repository, seed_task_container, seed_managed_task, invoke as invoke_extension

def run_report_node(request: dict) -> dict:
    inner = json.dumps(request)
    script = textwrap.dedent(f"""
        import {{ pathToFileURL }} from "node:url";
        const extUrl = pathToFileURL("{REPORT_MOD}");
        const mod = await import(extUrl.href);
        const req = {inner};
        let result;
        try {{
            if (req.action === "handleCompletion") {{
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


class P1SiblingClassificationTests(unittest.TestCase):
    def test_A1_single_permanent_still_publishes_sibling_and_A2_equation_and_A3_and_A5(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_ok = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            child_bad = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            async_dir = base / "async_probe"
            async_dir.mkdir()
            d_ok = async_dir / child_ok
            d_ok.mkdir(parents=True)
            sess_ok = d_ok / "session.jsonl"
            sess_ok.write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            relative_session = "relative/path/session.jsonl"
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_ok, "durationMs": 100, "state": "completed"},{"key": "review-0", "runId": child_bad, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(sess_ok), "runId": child_ok},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": relative_session, "runId": child_bad}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            res = run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            self.assertTrue(res["ok"], res)
            self.assertTrue(res["result"]["handled"])
            self.assertEqual(res["lockCount"], 1)
            published = res["result"]["published"]
            self.assertIn(f"impl-0/{child_ok}", published)
            self.assertNotIn(f"review-0/{child_bad}", published)
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 2)
            self.assertEqual(manifest["publishedReports"], 1)
            self.assertEqual(manifest["unavailableSteps"], 1)
            self.assertEqual(manifest["warningOnlySteps"], 0)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"] + manifest["warningOnlySteps"] + manifest["unavailableSteps"])
            steps = {(s["workflowKey"], s["childRunId"], s["classification"]) for s in manifest["steps"]}
            self.assertIn(("impl-0", child_ok, "published"), steps)
            self.assertIn(("review-0", child_bad, "unavailable"), steps)
            report_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1" / f"{child_ok}.json"
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["workflowKey"], "impl-0")
            self.assertEqual(report["childRunId"], child_ok)
            warnings_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            self.assertTrue(warnings_path.is_file())
            text = warnings_path.read_text(encoding="utf-8")
            self.assertIn(child_bad, text)
            self.assertIn("is not absolute", text.lower())
            for k in ["knownSteps","publishedReports","warningOnlySteps","unavailableSteps","steps","coverageVersion","taskId","workflowId"]:
                self.assertIn(k, manifest)
            extra = set(manifest.keys()) - {"coverageVersion","taskId","workflowId","knownSteps","publishedReports","warningOnlySteps","unavailableSteps","steps","generatedAt"}
            self.assertEqual(extra, set(), f"new field added {extra}")
            observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":"reports_probe"})
            self.assertFalse(observed["is_error"], observed)
            data = json.loads((repo / "reports_probe/collab-report.json").read_text(encoding="utf-8"))
            cov = data["lane_loop_coverage"]
            self.assertEqual(cov["known_steps"], 2)
            self.assertEqual(cov["published_reports"], 1)
            self.assertEqual(cov["unavailable_steps"], 1)
            self.assertEqual(cov["warning_only_steps"], 0)

    def test_three_steps_one_perm_publishes_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            child1 = "11111111-1111-1111-1111-111111111111"
            child2 = "22222222-2222-2222-2222-222222222222"
            child3 = "33333333-3333-3333-3333-333333333333"
            async_dir = base / "async3"
            async_dir.mkdir()
            for child in [child1, child2]:
                d = async_dir / child
                d.mkdir(parents=True)
                (d / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":5},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            bad_path = f"/tmp/other-{child3}/session.jsonl"
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child1, "durationMs": 100, "state": "completed"},{"key": "impl-1", "runId": child2, "durationMs": 100, "state": "completed"},{"key": "review-0", "runId": child3, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(async_dir / child1 / "session.jsonl"), "runId": child1},{"workflowKey": "impl-1", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(async_dir / child2 / "session.jsonl"), "runId": child2},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": bad_path, "runId": child3}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            res = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
            self.assertTrue(res["ok"])
            self.assertTrue(res["result"]["handled"])
            manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], 3)
            self.assertEqual(manifest["publishedReports"], 2)
            self.assertEqual(manifest["unavailableSteps"], 1)
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"]+manifest["warningOnlySteps"]+manifest["unavailableSteps"])
            self.assertEqual(len([s for s in manifest["steps"] if s["classification"]=="published"]), 2)

    def test_A4_module_comment_updated(self):
        text = (ROOT / "home/.pi/agent/extensions/collab-shared/report.ts").read_text(encoding="utf-8")
        self.assertIn("each step is classified on its own derivation outcome", text)
        self.assertIn("does not determine siblings", text.lower())
        self.assertIn("siblings that derive are published", text.lower())
        self.assertNotIn("identifying affected step as unavailable, others warning-only", text)

    def test_A5_no_new_manifest_field_and_equation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            workflow_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            child_ok = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            child_bad = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
            async_dir = base / "async_a5"
            async_dir.mkdir()
            d_ok = async_dir / child_ok
            d_ok.mkdir(parents=True)
            (d_ok / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":5},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
            bad = "relative/path2/session.jsonl"
            status = {
                "runId": workflow_id,
                "cwd": lane_path,
                "state": "complete",
                "workflow": {"trace": [{"key": "impl-0", "runId": child_ok, "durationMs": 100, "state": "completed"},{"key": "review-0", "runId": child_bad, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
                "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(d_ok / "session.jsonl"), "runId": child_ok},{"workflowKey": "review-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": bad, "runId": child_bad}]
            }
            (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            run_handle_with_lock_count(control_root, "demo", "T001", "writer-1", lane_path, workflow_id, str(async_dir))
            manifest = json.loads((repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["knownSteps"], manifest["publishedReports"]+manifest["warningOnlySteps"]+manifest["unavailableSteps"])
            allowed = {"coverageVersion","taskId","workflowId","knownSteps","publishedReports","warningOnlySteps","unavailableSteps","steps","generatedAt"}
            self.assertTrue(set(manifest.keys()).issubset(allowed), f"new field {set(manifest.keys())-allowed}")
