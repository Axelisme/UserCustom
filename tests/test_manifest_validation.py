from __future__ import annotations
import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_collab_op_extension import (
    invoke as invoke_extension,
    seed_managed_task,
    seed_repository,
    seed_task_container,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_MOD = ROOT / "home/.pi/agent/extensions/collab-shared/report.ts"

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

class ManifestValidationTests(unittest.TestCase):
    def _setup_valid_baseline(self, base: Path, repo: Path, lane_path: str, control_root: str):
        workflow_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        child = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        async_dir = base / "async_valid"
        async_dir.mkdir(parents=True, exist_ok=True)
        d = async_dir / child
        d.mkdir(parents=True, exist_ok=True)
        (d / "session.jsonl").write_text(json.dumps({"type":"message","id":"a","timestamp":"2026-08-21T12:00:00.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"c1","name":"read","arguments":{}}],"usage":{"totalTokens":10},"timestamp":1000}})+"\n"+json.dumps({"type":"message","id":"r","timestamp":"2026-08-21T12:00:01.000Z","message":{"role":"toolResult","toolCallId":"c1","toolName":"read","isError":False,"timestamp":1100,"content":[{"type":"text","text":"ok"}]}})+"\n", encoding="utf-8")
        status = {
            "runId": workflow_id,
            "cwd": lane_path,
            "state": "complete",
            "workflow": {"trace": [{"key": "impl-0", "runId": child, "durationMs": 100, "state": "completed"}], "emits": [], "console": []},
            "steps": [{"workflowKey": "impl-0", "parentWorkflowRunId": workflow_id, "status": "completed", "turnCount": 1, "sessionFile": str(d / "session.jsonl"), "runId": child}]
        }
        (async_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        result = run_report_node({"action":"handleCompletion","repoControlRoot":control_root,"taskId":"demo","ticketId":"T001","laneId":"writer-1","lanePath":lane_path,"workflowId":workflow_id,"asyncDir":str(async_dir),"eventWorkflowId":workflow_id,"eventAsyncDir":str(async_dir)})
        assert result["ok"] and result["result"]["handled"], result
        manifest_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage" / f"{workflow_id}.json"
        assert manifest_path.is_file(), "valid baseline manifest not created"
        return workflow_id, 1

    def _run_collab_report_and_get_coverage(self, repo: Path):
        import uuid
        out = f"reports-{uuid.uuid4().hex[:8]}"
        observed = invoke_extension(repo, {"tool":"collab_report","task_id":"demo","output_dir":out})
        assert not observed["is_error"], observed
        data = json.loads((repo / f"{out}/collab-report.json").read_text(encoding="utf-8"))
        return data["lane_loop_coverage"], data.get("warnings", [])

    def test_unsupported_coverageVersion_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_wid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            invalid_file = cov_dir / f"{invalid_wid}.json"
            manifest = {
                "coverageVersion": 2,
                "taskId": "demo",
                "workflowId": invalid_wid,
                "knownSteps": 1,
                "publishedReports": 1,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [{"workflowKey":"impl-0","childRunId":"dddddddd-dddd-dddd-dddd-dddddddddddd","classification":"published"}],
                "generatedAt": "2026-08-21T00:00:00.000Z"
            }
            invalid_file.write_text(json.dumps(manifest)+"\n", encoding="utf-8")
            invalid_wid2 = "dddddddd-dddd-dddd-dddd-ddddddddddde"
            invalid_file2 = cov_dir / f"{invalid_wid2}.json"
            manifest2 = dict(manifest)
            manifest2["workflowId"] = invalid_wid2
            manifest2["coverageVersion"] = 0
            invalid_file2.write_text(json.dumps(manifest2)+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w) for w in warnings).lower()
            self.assertIn("unsupported coverageversion", combined)
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_missing_taskId_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_wid = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
            invalid_file = cov_dir / f"{invalid_wid}.json"
            manifest = {
                "coverageVersion": 1,
                "workflowId": invalid_wid,
                "knownSteps": 1,
                "publishedReports": 1,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [{"workflowKey":"impl-0","childRunId":"ffffffff-ffff-ffff-ffff-ffffffffffff","classification":"published"}]
            }
            invalid_file.write_text(json.dumps(manifest)+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w) for w in warnings)
            self.assertIn("taskId", combined)
            self.assertTrue("missing" in combined.lower() or "mismatched" in combined.lower())
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_mismatched_taskId_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_wid = "ffffffff-ffff-ffff-ffff-fffffffffff0"
            invalid_file = cov_dir / f"{invalid_wid}.json"
            manifest = {
                "coverageVersion": 1,
                "taskId": "other-task",
                "workflowId": invalid_wid,
                "knownSteps": 1,
                "publishedReports": 1,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [{"workflowKey":"impl-0","childRunId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab","classification":"published"}]
            }
            invalid_file.write_text(json.dumps(manifest)+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w) for w in warnings)
            self.assertIn("taskId", combined)
            self.assertIn("mismatched", combined.lower())
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_filename_workflowId_mismatch_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_file = cov_dir / "mismatch.json"
            manifest = {
                "coverageVersion": 1,
                "taskId": "demo",
                "workflowId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "knownSteps": 1,
                "publishedReports": 1,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [{"workflowKey":"impl-0","childRunId":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbc","classification":"published"}]
            }
            invalid_file.write_text(json.dumps(manifest)+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w) for w in warnings)
            self.assertIn("filename", combined.lower())
            self.assertIn("workflowId", combined)
            self.assertTrue("mismatch" in combined.lower())
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_non_finite_totals_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_wid = "11111111-1111-1111-1111-111111111111"
            invalid_file = cov_dir / f"{invalid_wid}.json"
            raw = json.dumps({
                "coverageVersion": 1,
                "taskId": "demo",
                "workflowId": invalid_wid,
                "knownSteps": 1,
                "publishedReports": 1,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [{"workflowKey":"impl-0","childRunId":"22222222-2222-2222-2222-222222222222","classification":"published"}]
            })
            raw = raw.replace('"knownSteps": 1,', '"knownSteps": 1e999,')
            invalid_file.write_text(raw+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w) for w in warnings)
            self.assertIn("non-finite", combined.lower())
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_non_integer_totals_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_wid = "33333333-3333-3333-3333-333333333333"
            invalid_file = cov_dir / f"{invalid_wid}.json"
            manifest = {
                "coverageVersion": 1,
                "taskId": "demo",
                "workflowId": invalid_wid,
                "knownSteps": 1.5,
                "publishedReports": 1.5,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [{"workflowKey":"impl-0","childRunId":"44444444-4444-4444-4444-444444444444","classification":"published"}]
            }
            invalid_file.write_text(json.dumps(manifest)+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w) for w in warnings)
            self.assertIn("non-integer", combined.lower())
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_negative_totals_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_wid = "55555555-5555-5555-5555-555555555555"
            invalid_file = cov_dir / f"{invalid_wid}.json"
            manifest = {
                "coverageVersion": 1,
                "taskId": "demo",
                "workflowId": invalid_wid,
                "knownSteps": -1,
                "publishedReports": -1,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [{"workflowKey":"impl-0","childRunId":"66666666-6666-6666-6666-666666666666","classification":"published"}]
            }
            invalid_file.write_text(json.dumps(manifest)+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w) for w in warnings)
            self.assertIn("negative", combined.lower())
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_valid_contradictory_integer_totals_included_with_derived_and_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            contradictory_wid = "77777777-7777-7777-7777-777777777777"
            contradictory_file = cov_dir / f"{contradictory_wid}.json"
            manifest = {
                "coverageVersion": 1,
                "taskId": "demo",
                "workflowId": contradictory_wid,
                "knownSteps": 5,
                "publishedReports": 5,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [
                    {"workflowKey":"impl-0","childRunId":"88888888-8888-8888-8888-888888888888","classification":"published"},
                    {"workflowKey":"impl-1","childRunId":"99999999-9999-9999-9999-999999999999","classification":"warning-only"}
                ]
            }
            contradictory_file.write_text(json.dumps(manifest)+"\n", encoding="utf-8")
            report_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1"
            report_dir.mkdir(parents=True, exist_ok=True)
            report = {"reportVersion":2,"taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":contradictory_wid,"workflowKey":"impl-0","childRunId":"88888888-8888-8888-8888-888888888888","role":"implementer","terminalState":"completed"}
            (report_dir / "88888888-8888-8888-8888-888888888888.json").write_text(json.dumps(report)+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 2)
            self.assertEqual(coverage["known_steps"], 3)
            self.assertEqual(coverage["published_reports"], 2)
            self.assertEqual(coverage["warning_only_steps"], 1)
            self.assertEqual(coverage["unavailable_steps"], 0)
            combined = " ".join(str(w) for w in warnings)
            self.assertIn("declared totals contradict classifications", combined.lower())
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)
            self.assertEqual(coverage["known_steps"], coverage["published_reports"]+coverage["warning_only_steps"]+coverage["unavailable_steps"])

    def test_invalid_does_not_contribute_denominator_and_valid_contradictory_uses_classifications(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            inv1_wid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab"
            (cov_dir / f"{inv1_wid}.json").write_text(json.dumps({"coverageVersion":2,"taskId":"demo","workflowId":inv1_wid,"knownSteps":10,"publishedReports":10,"warningOnlySteps":0,"unavailableSteps":0,"steps":[{"workflowKey":"impl-0","childRunId":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbc","classification":"published"}]})+"\n", encoding="utf-8")
            inv2_wid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbd"
            (cov_dir / f"{inv2_wid}.json").write_text(json.dumps({"coverageVersion":1,"taskId":"wrong","workflowId":inv2_wid,"knownSteps":10,"publishedReports":10,"warningOnlySteps":0,"unavailableSteps":0,"steps":[{"workflowKey":"impl-0","childRunId":"cccccccc-cccc-cccc-cccc-ccccccccccce","classification":"published"}]})+"\n", encoding="utf-8")
            (cov_dir / "mismatch2.json").write_text(json.dumps({"coverageVersion":1,"taskId":"demo","workflowId":"different-wid-1234","knownSteps":10,"publishedReports":10,"warningOnlySteps":0,"unavailableSteps":0,"steps":[{"workflowKey":"impl-0","childRunId":"dddddddd-dddd-dddd-dddd-dddddddddddf","classification":"published"}]})+"\n", encoding="utf-8")
            inv3_wid = "cccccccc-cccc-cccc-cccc-ccccccccccc0"
            (cov_dir / f"{inv3_wid}.json").write_text(json.dumps({"coverageVersion":1,"taskId":"demo","workflowId":inv3_wid,"knownSteps":1.5,"publishedReports":1.5,"warningOnlySteps":0,"unavailableSteps":0,"steps":[{"workflowKey":"impl-0","childRunId":"eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee0","classification":"published"}]})+"\n", encoding="utf-8")
            contra_wid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            (cov_dir / f"{contra_wid}.json").write_text(json.dumps({"coverageVersion":1,"taskId":"demo","workflowId":contra_wid,"knownSteps":99,"publishedReports":99,"warningOnlySteps":0,"unavailableSteps":0,"steps":[{"workflowKey":"impl-0","childRunId":"ffffffff-ffff-ffff-ffff-fffffffffff1","classification":"published"},{"workflowKey":"review-0","childRunId":"ffffffff-ffff-ffff-ffff-fffffffffff2","classification":"unavailable"}]})+"\n", encoding="utf-8")
            report_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "ffffffff-ffff-ffff-ffff-fffffffffff1.json").write_text(json.dumps({"reportVersion":2,"taskId":"demo","ticketId":"T001","laneId":"writer-1","workflowId":contra_wid,"workflowKey":"impl-0","childRunId":"ffffffff-ffff-ffff-ffff-fffffffffff1","role":"implementer","terminalState":"completed"})+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 2)
            self.assertEqual(coverage["known_steps"], 3)
            self.assertEqual(coverage["published_reports"], 2)
            self.assertEqual(coverage["warning_only_steps"], 0)
            self.assertEqual(coverage["unavailable_steps"], 1)
            combined = " ".join(str(w).lower() for w in warnings)
            self.assertIn("unsupported coverageversion", combined)
            self.assertIn("taskid", combined)
            self.assertIn("filename", combined)
            self.assertIn("non-integer", combined)
            self.assertIn("declared totals contradict", combined)
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_root_null_excluded_with_warning_and_unchanged_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_wid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab"
            (cov_dir / f"{invalid_wid}.json").write_text("null\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w) for w in warnings)
            self.assertIn("malformed manifest", combined.lower())
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)
            self.assertIn(invalid_wid, " ".join(str(w) for w in warnings) if invalid_wid in combined else combined)

    def test_root_array_and_primitive_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            # root array
            arr_wid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab"
            (cov_dir / f"{arr_wid}.json").write_text("[]\n", encoding="utf-8")
            # root primitive number
            prim_wid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbc"
            (cov_dir / f"{prim_wid}.json").write_text("42\n", encoding="utf-8")
            # root primitive string
            str_wid = "cccccccc-cccc-cccc-cccc-cccccccccccd"
            (cov_dir / f"{str_wid}.json").write_text('"hello"\n', encoding="utf-8")
            # root primitive boolean
            bool_wid = "dddddddd-dddd-dddd-dddd-ddddddddddde"
            (cov_dir / f"{bool_wid}.json").write_text("true\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w).lower() for w in warnings)
            self.assertIn("malformed manifest", combined)
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_null_step_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            invalid_wid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab"
            manifest = {
                "coverageVersion": 1,
                "taskId": "demo",
                "workflowId": invalid_wid,
                "knownSteps": 1,
                "publishedReports": 1,
                "warningOnlySteps": 0,
                "unavailableSteps": 0,
                "steps": [None]
            }
            (cov_dir / f"{invalid_wid}.json").write_text(json.dumps(manifest)+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w).lower() for w in warnings)
            self.assertIn("malformed manifest", combined)
            self.assertIn("invalid step", combined)
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_non_object_step_values_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            # steps with number
            wid1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab"
            (cov_dir / f"{wid1}.json").write_text(json.dumps({"coverageVersion":1,"taskId":"demo","workflowId":wid1,"knownSteps":1,"publishedReports":1,"warningOnlySteps":0,"unavailableSteps":0,"steps":[42]})+"\n", encoding="utf-8")
            # steps with string
            wid2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbc"
            (cov_dir / f"{wid2}.json").write_text(json.dumps({"coverageVersion":1,"taskId":"demo","workflowId":wid2,"knownSteps":1,"publishedReports":1,"warningOnlySteps":0,"unavailableSteps":0,"steps":["hello"]})+"\n", encoding="utf-8")
            # steps with boolean
            wid3 = "cccccccc-cccc-cccc-cccc-cccccccccccd"
            (cov_dir / f"{wid3}.json").write_text(json.dumps({"coverageVersion":1,"taskId":"demo","workflowId":wid3,"knownSteps":1,"publishedReports":1,"warningOnlySteps":0,"unavailableSteps":0,"steps":[True]})+"\n", encoding="utf-8")
            # steps with array
            wid4 = "dddddddd-dddd-dddd-dddd-ddddddddddde"
            (cov_dir / f"{wid4}.json").write_text(json.dumps({"coverageVersion":1,"taskId":"demo","workflowId":wid4,"knownSteps":1,"publishedReports":1,"warningOnlySteps":0,"unavailableSteps":0,"steps":[[]]})+"\n", encoding="utf-8")
            # steps with bare number primitive inside valid-shaped array but mixed with null already covered
            wid5 = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeef"
            (cov_dir / f"{wid5}.json").write_text(json.dumps({"coverageVersion":1,"taskId":"demo","workflowId":wid5,"knownSteps":2,"publishedReports":1,"warningOnlySteps":0,"unavailableSteps":1,"steps":[{"workflowKey":"impl-0","childRunId":"ffffffff-ffff-ffff-ffff-fffffffffff0","classification":"published"}, 123]})+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w).lower() for w in warnings)
            self.assertIn("malformed manifest", combined)
            self.assertIn("invalid step", combined)
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_report_root_null_array_primitive_excluded_with_bounded_warning_table_driven(self):
        shapes = [
            ("null", "null\n"),
            ("array", "[]\n"),
            ("number", "42\n"),
            ("string", '"hello"\n'),
            ("boolean", "true\n"),
        ]
        for label, content in shapes:
            with self.subTest(shape=label):
                with tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    repo, _ = seed_repository(base)
                    seed_task_container(repo)
                    managed = seed_managed_task(repo, "demo")
                    lane_path = managed["lane"]
                    control_root = str(repo.resolve())
                    valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
                    report_root = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1"
                    report_root.mkdir(parents=True, exist_ok=True)
                    malformed_report = report_root / f"malformed-{label}.json"
                    malformed_report.write_text(content, encoding="utf-8")
                    coverage, warnings = self._run_collab_report_and_get_coverage(repo)
                    self.assertEqual(coverage["manifest_workflows"], 1)
                    self.assertEqual(coverage["known_steps"], valid_known)
                    combined = " ".join(str(w).lower() for w in warnings)
                    self.assertIn("malformed report", combined)
                    for w in warnings:
                        self.assertLessEqual(len(str(w)), 300)
                    self.assertLessEqual(len(warnings), 32)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            report_root = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1"
            report_root.mkdir(parents=True, exist_ok=True)
            for label, content in shapes:
                (report_root / f"malformed-{label}.json").write_text(content, encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            combined = " ".join(str(w).lower() for w in warnings)
            self.assertIn("malformed report", combined)
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_warning_record_null_array_primitive_counted_conservatively_table_driven(self):
        shapes = [
            ("null", "null"),
            ("array", "[]"),
            ("number", "42"),
            ("string", '"hello"'),
            ("boolean", "true"),
        ]
        for label, content in shapes:
            with self.subTest(shape=label):
                with tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    repo, _ = seed_repository(base)
                    seed_task_container(repo)
                    managed = seed_managed_task(repo, "demo")
                    lane_path = managed["lane"]
                    control_root = str(repo.resolve())
                    valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
                    report_root = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report"
                    warnings_path = report_root / "warnings.jsonl"
                    valid_warning = json.dumps({"at":"2026-08-21T00:00:00.000Z","taskId":"demo","workflowId":"orphan-wf-1","workflowKey":"impl-0","childRunId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","message":"orphan"})
                    warnings_path.write_text(valid_warning + "\n" + content + "\n", encoding="utf-8")
                    coverage, warnings = self._run_collab_report_and_get_coverage(repo)
                    self.assertEqual(coverage["workflow_warnings"], 2)
                    self.assertEqual(coverage["manifest_workflows"], 1)
                    combined = " ".join(str(w).lower() for w in warnings)
                    self.assertIn("malformed warning", combined)
                    for w in warnings:
                        self.assertLessEqual(len(str(w)), 300)
                    self.assertLessEqual(len(warnings), 32)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            report_root = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report"
            warnings_path = report_root / "warnings.jsonl"
            lines = []
            for label, content in shapes:
                lines.append(content)
            lines.append(json.dumps({"at":"2026-08-21T00:00:00.000Z","taskId":"demo","workflowId":"orphan-wf-2","workflowKey":"impl-0","childRunId":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","message":"orphan2"}))
            lines.append(json.dumps({"at":"2026-08-21T00:00:00.000Z","taskId":"demo","workflowId":"orphan-wf-3","workflowKey":"impl-0","childRunId":"cccccccc-cccc-cccc-cccc-cccccccccccc","message":"orphan3"}))
            warnings_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["workflow_warnings"], 7)
            self.assertEqual(coverage["manifest_workflows"], 1)
            combined = " ".join(str(w).lower() for w in warnings)
            self.assertIn("malformed warning", combined)
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)

    def test_report_and_warning_malformed_combined_denominator_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, _ = seed_repository(base)
            seed_task_container(repo)
            managed = seed_managed_task(repo, "demo")
            lane_path = managed["lane"]
            control_root = str(repo.resolve())
            valid_wid, valid_known = self._setup_valid_baseline(base, repo, lane_path, control_root)
            report_root = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/writer-1"
            report_root.mkdir(parents=True, exist_ok=True)
            (report_root / "report-null.json").write_text("null\n", encoding="utf-8")
            (report_root / "report-array.json").write_text("[]\n", encoding="utf-8")
            warnings_path = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/warnings.jsonl"
            warnings_path.write_text("null\n[]\n42\n\"hello\"\ntrue\n", encoding="utf-8")
            cov_dir = repo / ".agent_state/plans/demo/.collab_op/lane_loop_report/coverage"
            (cov_dir / "bad-version.json").write_text(json.dumps({"coverageVersion":2,"taskId":"demo","workflowId":"bad-version","knownSteps":1,"publishedReports":1,"warningOnlySteps":0,"unavailableSteps":0,"steps":[{"workflowKey":"impl-0","childRunId":"dddddddd-dddd-dddd-dddd-dddddddddddd","classification":"published"}]})+"\n", encoding="utf-8")
            (cov_dir / "bad-task.json").write_text(json.dumps({"coverageVersion":1,"taskId":"other","workflowId":"bad-task","knownSteps":1,"publishedReports":1,"warningOnlySteps":0,"unavailableSteps":0,"steps":[{"workflowKey":"impl-0","childRunId":"eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee","classification":"published"}]})+"\n", encoding="utf-8")
            coverage, warnings = self._run_collab_report_and_get_coverage(repo)
            self.assertEqual(coverage["manifest_workflows"], 1)
            self.assertEqual(coverage["known_steps"], valid_known)
            self.assertEqual(coverage["workflow_warnings"], 5)
            combined = " ".join(str(w).lower() for w in warnings)
            self.assertIn("malformed report", combined)
            self.assertIn("malformed warning", combined)
            self.assertIn("unsupported coverageversion", combined)
            self.assertIn("taskid", combined)
            for w in warnings:
                self.assertLessEqual(len(str(w)), 300)
            self.assertLessEqual(len(warnings), 32)
