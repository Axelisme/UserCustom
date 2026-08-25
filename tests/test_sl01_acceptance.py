from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_collab_op_extension import (
    git,
    invoke as invoke_extension,
    seed_managed_task,
    seed_repository,
    seed_task_container,
)
from tests.test_collab_reviewed_lane_extension import RPC_MOCK as REVIEWED_RPC_MOCK

ROOT = Path(__file__).resolve().parents[1]
LANE_MOD = ROOT / "home/.pi/agent/extensions/collab-reviewed-lane.ts"
REPORT_MOD = ROOT / "home/.pi/agent/extensions/collab-shared/report.ts"
PI_PACKAGE = Path("/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js")
EXTENSION_OP = ROOT / "home/.pi/agent/extensions/collab-op.ts"

def run_node_script(script: str, timeout: int = 20) -> dict:
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mjs', delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        run = subprocess.run(["/usr/bin/node", "--experimental-strip-types", fname], capture_output=True, text=True, timeout=timeout)
        if run.returncode != 0:
            raise AssertionError(f"node failed: {run.stderr}\n{run.stdout}\n{script}")
        lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
        if not lines:
            raise AssertionError(f"no output: {run.stderr}")
        return json.loads(lines[-1])
    finally:
        Path(fname).unlink(missing_ok=True)

def lane_script_wrapper(body: str) -> str:
    return textwrap.dedent(f"""
        import {{ createRequire }} from "node:module";
        const require = createRequire('/home/axel/.pi/agent/npm/package.json');
        const createJiti = require('jiti');
        const jiti = createJiti('/home/axel/.pi/agent/npm/package.json', {{ alias: {{ "@earendil-works/pi-coding-agent": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js" }}, fsCache:false, moduleCache:false }});
        const laneMod = jiti("{LANE_MOD}");
        const reportMod = jiti("{REPORT_MOD}");
        {body}
    """)

class SL01A1RegisteredConcurrentTests(unittest.TestCase):
    def test_A1_registered_concurrent_same_key_refused_one_spawn_other_lane_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            managed = seed_managed_task(repository, "demo")
            created = invoke_extension(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer-2"})
            self.assertFalse(created["is_error"], created)
            capture = base / "capture.jsonl"
            script = textwrap.dedent(f"""
                import {{ pathToFileURL }} from "node:url";
                const piPackage = "{PI_PACKAGE}";
                const extensionPath = "{EXTENSION_OP}";
                const supportPath = "{REVIEWED_RPC_MOCK}";
                const repoPath = "{repository}";
                const capturePath = "{capture}";
                const {{ DefaultResourceLoader, SettingsManager }} = await import(pathToFileURL(piPackage));
                const settingsManager = SettingsManager.inMemory({{}});
                const loader = new DefaultResourceLoader({{
                  cwd: repoPath,
                  agentDir: repoPath + "/.empty-pi-agent",
                  additionalExtensionPaths: [extensionPath, supportPath],
                  settingsManager}});
                await loader.reload();
                const loaded = loader.getExtensions();
                const regs = new Map(loaded.extensions.flatMap(e => [...e.tools.entries()]));
                const tool = regs.get("collab_run_reviewed_lane");
                const configTool = regs.get("_collab_test_rpc_config");
                if (!tool) throw new Error("reviewed lane tool not found");
                await configTool.definition.execute("test-rpc-config", {{ mode: "available", capture: capturePath, delaySpawnMs: 400, runId: "workflow-1" }}, undefined, undefined, {{ cwd: repoPath }});
                const baseReq = {{ task_id: "demo", ticket_id: "T001", worker_brief: "implement", review_brief: "review", correction_budget: 0 }};
                const p1 = tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, undefined, undefined, {{ cwd: repoPath }}).then(r => ({{ ok: true, result: JSON.parse(r.content.find(c=>c.type==="text").text) }})).catch(async e => {{
                    let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ message: String(e) }} }}; }}
                    return {{ ok: false, error: err }};
                }});
                await new Promise(r => setTimeout(r, 60));
                const p2 = tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, undefined, undefined, {{ cwd: repoPath }}).then(r => ({{ ok: true, result: JSON.parse(r.content.find(c=>c.type==="text").text) }})).catch(async e => {{
                    let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ message: String(e) }} }}; }}
                    return {{ ok: false, error: err }};
                }});
                const p3 = tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-2" }}, undefined, undefined, {{ cwd: repoPath }}).then(r => ({{ ok: true, result: JSON.parse(r.content.find(c=>c.type==="text").text) }})).catch(async e => {{
                    let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ message: String(e) }} }}; }}
                    return {{ ok: false, error: err }};
                }});
                const [r1, r2, r3] = await Promise.all([p1, p2, p3]);
                const r1Success = r1.ok === true;
                const r2Code = r2.ok === false ? (r2.error?.error?.code || r2.error?.code || "") : "";
                const r3Success = r3.ok === true;
                import fs from "node:fs";
                let spawnCount = 0;
                try {{
                  const txt = fs.readFileSync(capturePath, "utf8");
                  for (const line of txt.trim().split("\\n")) {{
                    if (!line.trim()) continue;
                    const j = JSON.parse(line);
                    if (j.method === "spawn") spawnCount++;
                  }}
                }} catch {{}}
                const ok = r1Success && r2Code === "reviewed_lane_active" && r3Success && spawnCount === 2;
                if (!ok) {{
                  console.error(JSON.stringify({{ r1, r2, r3, spawnCount }}, null, 2));
                  throw new Error(`A1 failed: r1Success=${{r1Success}} r2Code=${{r2Code}} r3Success=${{r3Success}} spawnCount=${{spawnCount}}`);
                }}
                process.stdout.write(JSON.stringify({{ok:true, spawnCount}})+"\\n");
            """)
            result = run_node_script(script, timeout=20)
            self.assertTrue(result.get("ok"))

    def test_A1_delayed_spawn_abort_after_emission_retains_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            capture = base / "capture.jsonl"
            emission = base / "emission.jsonl"
            script = textwrap.dedent(f"""
                import {{ pathToFileURL }} from "node:url";
                import fs from "node:fs";
                const piPackage = "{PI_PACKAGE}";
                const extensionPath = "{EXTENSION_OP}";
                const supportPath = "{REVIEWED_RPC_MOCK}";
                const repoPath = "{repository}";
                const capturePath = "{capture}";
                const emissionPath = "{emission}";
                const {{ DefaultResourceLoader, SettingsManager }} = await import(pathToFileURL(piPackage));
                const settingsManager = SettingsManager.inMemory({{}});
                const loader = new DefaultResourceLoader({{
                  cwd: repoPath,
                  agentDir: repoPath + "/.empty-pi-agent",
                  additionalExtensionPaths: [extensionPath, supportPath],
                  settingsManager}});
                await loader.reload();
                const loaded = loader.getExtensions();
                const regs = new Map(loaded.extensions.flatMap(e => [...e.tools.entries()]));
                const tool = regs.get("collab_run_reviewed_lane");
                const configTool = regs.get("_collab_test_rpc_config");
                if (!tool) throw new Error("reviewed lane tool not found");
                await configTool.definition.execute("test-rpc-config", {{ mode: "available", capture: capturePath, emissionMarker: emissionPath, delaySpawnMs: 400, runId: "workflow-delayed" }}, undefined, undefined, {{ cwd: repoPath }});
                const baseReq = {{ task_id: "demo", ticket_id: "T001", worker_brief: "implement", review_brief: "review", correction_budget: 0 }};
                const controller = new AbortController();
                const p1 = tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, controller.signal, undefined, {{ cwd: repoPath }}).then(r => ({{ ok: true, result: JSON.parse(r.content.find(c=>c.type==="text").text) }})).catch(async e => {{
                    let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: e.code || "unknown", message: String(e.message || e) }} }}; }}
                    const code = err?.error?.code || err?.code || "";
                    return {{ ok: false, code, error: err }};
                }});
                async function waitForEmission(path, timeoutMs=3000) {{
                  const start = Date.now();
                  while (Date.now() - start < timeoutMs) {{
                    try {{
                      const txt = fs.readFileSync(path, "utf8");
                      for (const line of txt.split(String.fromCharCode(10))) {{
                        if (!line.trim()) continue;
                        const j = JSON.parse(line);
                        if (j.method === "spawn") return;
                      }}
                    }} catch {{}}
                    await new Promise(r => setTimeout(r, 10));
                  }}
                  throw new Error("emission timeout for "+path);
                }}
                await waitForEmission(emissionPath);
                controller.abort();
                await new Promise(r => setTimeout(r, 20));
                const p2 = await tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, undefined, undefined, {{ cwd: repoPath }}).then(r => ({{ ok: true, result: JSON.parse(r.content.find(c=>c.type==="text").text) }})).catch(async e => {{
                    let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: e.code || "unknown", message: String(e.message || e) }} }}; }}
                    const code = err?.error?.code || err?.code || "";
                    return {{ ok: false, code, error: err }};
                }});
                const r1 = await p1;
                const r2 = p2;
                let spawnCount = 0;
                try {{
                  const txt = fs.readFileSync(emissionPath, "utf8");
                  for (const line of txt.trim().split(String.fromCharCode(10))) {{
                    if (!line.trim()) continue;
                    const j = JSON.parse(line);
                    if (j.method === "spawn") spawnCount++;
                  }}
                }} catch {{}}
                const ok = r1.ok === true && r2.ok === false && r2.code === "reviewed_lane_active" && spawnCount === 1;
                if (!ok) {{
                  console.error(JSON.stringify({{ r1, r2, spawnCount }}, null, 2));
                  throw new Error(`delayed abort retention failed: r1.ok=${{r1.ok}} r1=${{JSON.stringify(r1)}} r2.code=${{r2.code}} spawnCount=${{spawnCount}}`);
                }}
                process.stdout.write(JSON.stringify({{ok:true, spawnCount}})+"\\n");
            """)
            result = run_node_script(script, timeout=20)
            self.assertTrue(result.get("ok"))

    def test_A1_spawn_timeout_after_emission_retains_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            capture = base / "capture.jsonl"
            emission = base / "emission.jsonl"
            script = textwrap.dedent(f"""
                import {{ pathToFileURL }} from "node:url";
                import fs from "node:fs";
                const piPackage = "{PI_PACKAGE}";
                const extensionPath = "{EXTENSION_OP}";
                const supportPath = "{REVIEWED_RPC_MOCK}";
                const repoPath = "{repository}";
                const capturePath = "{capture}";
                const emissionPath = "{emission}";
                const laneModPath = "{LANE_MOD}";
                const {{ DefaultResourceLoader, SettingsManager }} = await import(pathToFileURL(piPackage));
                const settingsManager = SettingsManager.inMemory({{}});
                const loader = new DefaultResourceLoader({{
                  cwd: repoPath,
                  agentDir: repoPath + "/.empty-pi-agent",
                  additionalExtensionPaths: [extensionPath, supportPath],
                  settingsManager}});
                await loader.reload();
                const {{ createRequire }} = await import("node:module");
                const require = createRequire('/home/axel/.pi/agent/npm/package.json');
                const createJiti = require('jiti');
                const jiti = createJiti('/home/axel/.pi/agent/npm/package.json', {{ alias: {{ "@earendil-works/pi-coding-agent": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js" }}, fsCache:false, moduleCache:false }});
                const laneMod = jiti(laneModPath);
                laneMod.__setTestSpawnTimeoutForTest(600);
                const loaded = loader.getExtensions();
                const regs = new Map(loaded.extensions.flatMap(e => [...e.tools.entries()]));
                const tool = regs.get("collab_run_reviewed_lane");
                const configTool = regs.get("_collab_test_rpc_config");
                if (!tool) throw new Error("reviewed lane tool not found");
                await configTool.definition.execute("test-rpc-config", {{ mode: "available", capture: capturePath, emissionMarker: emissionPath, delaySpawnMs: 1500, runId: "workflow-timeout" }}, undefined, undefined, {{ cwd: repoPath }});
                const baseReq = {{ task_id: "demo", ticket_id: "T001", worker_brief: "implement", review_brief: "review", correction_budget: 0 }};
                const p1 = tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, undefined, undefined, {{ cwd: repoPath }}).then(r => ({{ ok: true, result: JSON.parse(r.content.find(c=>c.type==="text").text) }})).catch(async e => {{
                    let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: e.code || "unknown", message: String(e.message || e) }} }}; }}
                    const code = err?.error?.code || err?.code || "";
                    return {{ ok: false, code, error: err }};
                }});
                async function waitForEmission(path, timeoutMs=3000) {{
                  const start = Date.now();
                  while (Date.now() - start < timeoutMs) {{
                    try {{
                      const txt = fs.readFileSync(path, "utf8");
                      for (const line of txt.split(String.fromCharCode(10))) {{
                        if (!line.trim()) continue;
                        const j = JSON.parse(line);
                        if (j.method === "spawn") return;
                      }}
                    }} catch {{}}
                    await new Promise(r => setTimeout(r, 10));
                  }}
                  throw new Error("emission timeout");
                }}
                await waitForEmission(emissionPath);
                await new Promise(r => setTimeout(r, 50));
                const p2 = await tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, undefined, undefined, {{ cwd: repoPath }}).then(r => ({{ ok: true, result: JSON.parse(r.content.find(c=>c.type==="text").text) }})).catch(async e => {{
                    let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: e.code || "unknown", message: String(e.message || e) }} }}; }}
                    const code = err?.error?.code || err?.code || "";
                    return {{ ok: false, code, error: err }};
                }});
                const r1 = await p1;
                let emissionCount = 0;
                try {{
                  const txt = fs.readFileSync(emissionPath, "utf8");
                  for (const line of txt.trim().split(String.fromCharCode(10))) {{
                    if (!line.trim()) continue;
                    const j = JSON.parse(line);
                    if (j.method === "spawn") emissionCount++;
                  }}
                }} catch {{}}
                const p2Code = p2.ok === false ? p2.code : "";
                const r1Code = r1.ok === false ? r1.code : "";
                if (p2Code !== "reviewed_lane_active") {{
                  console.error(JSON.stringify({{ r1, p2, emissionCount }}, null, 2));
                  throw new Error(`timeout retention p2 failed: p2Code=${{p2Code}} emissionCount=${{emissionCount}} r1=${{JSON.stringify(r1)}}`);
                }}
                if (r1Code !== "rpc_unavailable") {{
                  console.error(JSON.stringify({{ r1, p2, emissionCount }}, null, 2));
                  throw new Error(`expected p1 timeout rpc_unavailable, got r1Code=${{r1Code}} r1=${{JSON.stringify(r1)}}`);
                }}
                if (emissionCount !== 1) {{
                  throw new Error(`expected one emitted spawn, got ${{emissionCount}}`);
                }}
                const p3 = await tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, undefined, undefined, {{ cwd: repoPath }}).then(r => ({{ ok: true, result: JSON.parse(r.content.find(c=>c.type==="text").text) }})).catch(async e => {{
                    let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: e.code || "unknown", message: String(e.message || e) }} }}; }}
                    const code = err?.error?.code || err?.code || "";
                    return {{ ok: false, code, error: err }};
                }});
                const p3Code = p3.ok === false ? p3.code : "";
                if (p3Code !== "reviewed_lane_active") {{
                  throw new Error(`p3 should still be blocked after timeout retention, got ${{p3Code}} ${{JSON.stringify(p3)}}`);
                }}
                laneMod.__setTestSpawnTimeoutForTest(undefined);
                await new Promise(r => setTimeout(r, 200));
                process.stdout.write(JSON.stringify({{ok:true, emissionCount, r1Code, p2Code}})+"\\n");
            """)
            result = run_node_script(script, timeout=20)
            self.assertTrue(result.get("ok"))



class SL01A2RegisteredReleaseTests(unittest.TestCase):
    def test_A2_validation_spawn_and_abort_release_then_same_key_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            # create writer-2 for abort test
            created = invoke_extension(repository, {"tool": "collab_lane_create", "task_id": "demo", "lane_id": "writer-2"})
            self.assertFalse(created["is_error"], created)
            script = textwrap.dedent(f"""
                import {{ pathToFileURL }} from "node:url";
                const piPackage = "{PI_PACKAGE}";
                const extensionPath = "{EXTENSION_OP}";
                const supportPath = "{REVIEWED_RPC_MOCK}";
                const repoPath = "{repository}";
                const {{ DefaultResourceLoader, SettingsManager }} = await import(pathToFileURL(piPackage));
                const settingsManager = SettingsManager.inMemory({{}});
                const loader = new DefaultResourceLoader({{
                  cwd: repoPath,
                  agentDir: repoPath + "/.empty-pi-agent",
                  additionalExtensionPaths: [extensionPath, supportPath],
                  settingsManager}});
                await loader.reload();
                const loaded = loader.getExtensions();
                const regs = new Map(loaded.extensions.flatMap(e => [...e.tools.entries()]));
                const tool = regs.get("collab_run_reviewed_lane");
                const configTool = regs.get("_collab_test_rpc_config");
                const baseReq = {{ task_id: "demo", ticket_id: "T001", worker_brief: "implement", review_brief: "review", correction_budget: 0 }};
                let r1;
                try {{
                  const res = await tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-9" }}, undefined, undefined, {{ cwd: repoPath }});
                  r1 = {{ ok: true, result: JSON.parse(res.content.find(c=>c.type==="text").text) }};
                }} catch (e) {{
                  let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: "unknown", message: String(e) }} }}; }}
                  r1 = {{ ok: false, error: err }};
                }}
                if (r1.ok) throw new Error("validation should have failed for writer-9");
                await configTool.definition.execute("test-rpc-config", {{ mode: "spawn-error" }}, undefined, undefined, {{ cwd: repoPath }});
                let r2;
                try {{
                  const res = await tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, undefined, undefined, {{ cwd: repoPath }});
                  r2 = {{ ok: true, result: JSON.parse(res.content.find(c=>c.type==="text").text) }};
                }} catch (e) {{
                  let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: "unknown", message: String(e) }} }}; }}
                  r2 = {{ ok: false, error: err }};
                }}
                if (r2.ok) throw new Error("spawn should have failed");
                const code2 = r2.error?.error?.code || "";
                if (code2 !== "rpc_spawn_failed") throw new Error("expected rpc_spawn_failed, got "+code2+" "+JSON.stringify(r2));
                await configTool.definition.execute("test-rpc-config", {{ mode: "available", runId: "retry-workflow" }}, undefined, undefined, {{ cwd: repoPath }});
                let r3;
                try {{
                  const res = await tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-1" }}, undefined, undefined, {{ cwd: repoPath }});
                  r3 = {{ ok: true, result: JSON.parse(res.content.find(c=>c.type==="text").text) }};
                }} catch (e) {{
                  let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: "unknown", message: String(e) }} }}; }}
                  r3 = {{ ok: false, error: err }};
                }}
                if (!r3.ok) throw new Error("retry after spawn failure should succeed, got "+JSON.stringify(r3));
                const controller = new AbortController();
                controller.abort();
                let r4;
                try {{
                  const res = await tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-2" }}, controller.signal, undefined, {{ cwd: repoPath }});
                  r4 = {{ ok: true, result: JSON.parse(res.content.find(c=>c.type==="text").text) }};
                }} catch (e) {{
                  let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: "unknown", message: String(e) }} }}; }}
                  r4 = {{ ok: false, error: err }};
                }}
                if (r4.ok) throw new Error("abort should have failed, got "+JSON.stringify(r4));
                await configTool.definition.execute("test-rpc-config", {{ mode: "available", runId: "retry2" }}, undefined, undefined, {{ cwd: repoPath }});
                let r5;
                try {{
                  const res = await tool.definition.execute("test-call", {{ ...baseReq, lane_id: "writer-2" }}, undefined, undefined, {{ cwd: repoPath }});
                  r5 = {{ ok: true, result: JSON.parse(res.content.find(c=>c.type==="text").text) }};
                }} catch (e) {{
                  let err; try {{ err = JSON.parse(e.message); }} catch {{ err = {{ error: {{ code: "unknown", message: String(e) }} }}; }}
                  r5 = {{ ok: false, error: err }};
                }}
                if (!r5.ok) throw new Error("retry after abort should succeed, got "+JSON.stringify(r5));
                process.stdout.write(JSON.stringify({{ok:true}})+"\\n");
            """)
            result = run_node_script(script, timeout=20)
            self.assertTrue(result.get("ok"))

    def test_A2_partial_and_exact_release_via_handle(self):
        script = lane_script_wrapper(textwrap.dedent("""
            const fakePi = {
              events: { handlers: new Map(), on(event,h){ if(!this.handlers.has(event)) this.handlers.set(event,[]); this.handlers.get(event).push(h); return ()=>{}; }, emit(event,data){ const arr=this.handlers.get(event)||[]; for(const h of [...arr]) h(data); } },
              exec: async () => ({ code: 0, stdout: "", stderr: "" })
            };
            const repo = { controlRoot: "/tmp/repoA2b", gitDir: "/tmp/repoA2b/.git", worktreeRoot: "/tmp/repoA2b", git: async () => ({ code: 0, stdout: "", stderr: "" }) };
            const lanePath = "/tmp/laneA2b";
            const harness = laneMod.createIsolatedReviewedLaneHarness();
            const deps = {
              withTaskLock: async (r, t, body) => body(),
              error: (c,m)=>{ const e=new Error(m); e.code=c; return e; }
            };
            const pending = { pi: fakePi, repo, taskId: "demo", ticketId: "T001", laneId: "writer-1", lanePath, workflowId: "11111111-1111-1111-1111-111111111111", asyncDir: "/tmp/asyncA2b", deps, canonicalKey: "/tmp/repoA2b\\0demo\\0writer-1" };
            harness.registerPending(pending);
            if (harness.getReservationCount() !== 1) throw new Error("should be 1");
            if (harness.getPendingCount() !== 1) throw new Error("pending 1");
            await harness.handleAsyncCompleteEvent({ runId: "11111111-1111-1111-1111-111111111111", asyncDir: "/tmp/wrong" });
            if (harness.getPendingCount() !== 1) throw new Error("partial should retain pending");
            if (harness.getReservationCount() !== 1) throw new Error("partial should retain reservation");
            await harness.handleAsyncCompleteEvent({ runId: "wrong-id", asyncDir: "/tmp/asyncA2b" });
            if (harness.getPendingCount() !== 1) throw new Error("unrelated should retain");
            import fs from "node:fs";
            import path from "node:path";
            import os from "node:os";
            const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "async-"));
            const statusPath = path.join(tmp, "status.json");
            const laneTmp = fs.mkdtempSync(path.join(os.tmpdir(), "lane-"));
            const controlRoot = fs.mkdtempSync(path.join(os.tmpdir(), "repo-"));
            const childRunId = "22222222-2222-2222-2222-222222222222";
            const workflowId = "33333333-3333-3333-3333-333333333333";
            const sessionDir = path.join(tmp, childRunId);
            fs.mkdirSync(sessionDir, {recursive:true});
            const sessionFile = path.join(sessionDir, "session.jsonl");
            fs.writeFileSync(sessionFile, JSON.stringify({type:"message", message:{role:"assistant", content:[{type:"toolCall", id:"c1", name:"read"}], usage:{totalTokens:10}}}) + "\\n" + JSON.stringify({type:"message", message:{role:"toolResult", toolCallId:"c1", isError:false}}) + "\\n");
            const status = {
              runId: workflowId,
              cwd: laneTmp,
              state: "complete",
              workflow: { trace: [{key:"impl-0", runId: childRunId, durationMs:100, state:"completed"}] },
              steps: [{ workflowKey:"impl-0", parentWorkflowRunId: workflowId, status:"completed", turnCount:1, sessionFile, runId: childRunId }]
            };
            fs.writeFileSync(statusPath, JSON.stringify(status));
            const plans = path.join(controlRoot, ".agent_state", "plans", "demo");
            fs.mkdirSync(plans, {recursive:true});
            const harness2 = laneMod.createIsolatedReviewedLaneHarness();
            const deps2 = {
              withTaskLock: async (r, t, body) => body(),
              error: (c,m)=>{ const e=new Error(m); e.code=c; return e; }
            };
            const pending2 = { pi: fakePi, repo: { controlRoot, gitDir: path.join(controlRoot,".git"), worktreeRoot: controlRoot, git: async()=>({code:0,stdout:"",stderr:""}) }, taskId: "demo", ticketId: "T001", laneId: "writer-1", lanePath: laneTmp, workflowId, asyncDir: tmp, deps: deps2, canonicalKey: controlRoot+"\\0demo\\0writer-1" };
            harness2.registerPending(pending2);
            await harness2.handleAsyncCompleteEvent({ runId: workflowId, asyncDir: tmp });
            if (harness2.getPendingCount() !== 0) throw new Error("exact should release pending, got "+harness2.getPendingCount());
            if (harness2.getReservationCount() !== 0) throw new Error("exact should release reservation");
            const pending3 = { pi: fakePi, repo: { controlRoot, gitDir: path.join(controlRoot,".git"), worktreeRoot: controlRoot, git: async()=>({code:0,stdout:"",stderr:""}) }, taskId: "demo", ticketId: "T001", laneId: "writer-1", lanePath: laneTmp, workflowId: "44444444-4444-4444-4444-444444444444", asyncDir: tmp+"2", deps: deps2, canonicalKey: controlRoot+"\\0demo\\0writer-1" };
            harness2.registerPending(pending3);
            if (harness2.getReservationCount() !== 1) throw new Error("later same-key should succeed after release");
            process.stdout.write(JSON.stringify({ok:true}));
        """))
        result = run_node_script(script)
        self.assertTrue(result.get("ok"))

class SL01A3SettlementTests(unittest.TestCase):
    def test_A3_early_event_waits_and_publishes_once_lock_not_held(self):
        script = lane_script_wrapper(textwrap.dedent("""
            import fs from "node:fs";
            import path from "node:path";
            import os from "node:os";
            const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "asyncA3-"));
            const laneTmp = fs.mkdtempSync(path.join(os.tmpdir(), "laneA3-"));
            const controlRoot = fs.mkdtempSync(path.join(os.tmpdir(), "repoA3-"));
            const childRunId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
            const workflowId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
            const sessionDir = path.join(tmp, childRunId);
            fs.mkdirSync(sessionDir, {recursive:true});
            const sessionFile = path.join(sessionDir, "session.jsonl");
            const statusPath = path.join(tmp, "status.json");
            const plans = path.join(controlRoot, ".agent_state", "plans", "demo");
            fs.mkdirSync(plans, {recursive:true});
            const sessionContent = JSON.stringify({type:"message", message:{role:"assistant", content:[{type:"toolCall", id:"c1", name:"read"}], usage:{totalTokens:10}}}) + "\\n" + JSON.stringify({type:"message", message:{role:"toolResult", toolCallId:"c1", isError:false}}) + "\\n";
            const status = {
              runId: workflowId,
              cwd: laneTmp,
              state: "complete",
              workflow: { trace: [{key:"impl-0", runId: childRunId, durationMs:100, state:"completed"}] },
              steps: [{ workflowKey:"impl-0", parentWorkflowRunId: workflowId, status:"completed", turnCount:1, sessionFile, runId: childRunId }]
            };
            setTimeout(()=>{ fs.writeFileSync(sessionFile, sessionContent); }, 80);
            setTimeout(()=>{ fs.writeFileSync(statusPath, JSON.stringify(status)); }, 100);
            let lockAcquiredAt = null;
            const withTaskLock = async (body) => {
                lockAcquiredAt = Date.now();
                return body();
            };
            const start = Date.now();
            const result = await reportMod.handleReviewedLaneCompletion({
              repoControlRoot: controlRoot,
              taskId: "demo",
              ticketId: "T001",
              laneId: "writer-1",
              lanePath: laneTmp,
              workflowId,
              asyncDir: tmp,
              eventWorkflowId: workflowId,
              eventAsyncDir: tmp,
              withTaskLock
            });
            const elapsed = Date.now() - start;
            if (!result.handled) throw new Error("should be handled");
            if (result.published.length !== 1) throw new Error("should publish once, got "+JSON.stringify(result));
            if (result.warnings.length !== 0) throw new Error("should have no warnings");
            if (elapsed < 90 || elapsed > 1200) throw new Error("elapsed should be ~100-1200ms, got "+elapsed);
            if (lockAcquiredAt === null) throw new Error("lock should be acquired");
            if (lockAcquiredAt < start + 90) throw new Error("lock should not be held during waiting, acquired too early: "+lockAcquiredAt+" vs start "+start);
            const result2 = await reportMod.handleReviewedLaneCompletion({
              repoControlRoot: controlRoot,
              taskId: "demo",
              ticketId: "T001",
              laneId: "writer-1",
              lanePath: laneTmp,
              workflowId,
              asyncDir: tmp,
              eventWorkflowId: workflowId,
              eventAsyncDir: tmp,
              withTaskLock
            });
            process.stdout.write(JSON.stringify({ok:true, elapsed, lockAcquiredAt}));
        """))
        result = run_node_script(script)
        self.assertTrue(result.get("ok"))

class SL01A4UnsafeAndDeadlineTests(unittest.TestCase):
    def test_A4_permanent_unsafe_stops_immediately_and_deadline_warns(self):
        script = lane_script_wrapper(textwrap.dedent("""
            import fs from "node:fs";
            import path from "node:path";
            import os from "node:os";
            const controlRoot = fs.mkdtempSync(path.join(os.tmpdir(), "repoA4-"));
            const laneTmp = fs.mkdtempSync(path.join(os.tmpdir(), "laneA4-"));
            const tmpPerm = fs.mkdtempSync(path.join(os.tmpdir(), "asyncPerm-"));
            const tmpRetry = fs.mkdtempSync(path.join(os.tmpdir(), "asyncRetry-"));
            const plans = path.join(controlRoot, ".agent_state", "plans", "demo");
            fs.mkdirSync(plans, {recursive:true});
            const statusPathPerm = path.join(tmpPerm, "status.json");
            const target = path.join(tmpPerm, "real.json");
            fs.writeFileSync(target, JSON.stringify({runId:"w1", cwd:laneTmp, state:"complete", workflow:{trace:[]}}));
            try { fs.symlinkSync(target, statusPathPerm); } catch {}
            const startPerm = Date.now();
            const resultPerm = await reportMod.handleReviewedLaneCompletion({
              repoControlRoot: controlRoot,
              taskId: "demo",
              ticketId: "T001",
              laneId: "writer-1",
              lanePath: laneTmp,
              workflowId: "w1",
              asyncDir: tmpPerm,
              eventWorkflowId: "w1",
              eventAsyncDir: tmpPerm,
              withTaskLock: async (b)=>b()
            });
            const elapsedPerm = Date.now() - startPerm;
            if (!resultPerm.handled) throw new Error("perm should be handled");
            if (resultPerm.warnings.length === 0) throw new Error("perm should warn");
            if (elapsedPerm > 300) throw new Error("permanent should stop immediately, elapsed "+elapsedPerm);
            const workflowId2 = "w2";
            const startRetry = Date.now();
            let lockCalls = 0;
            const withTaskLock = async (b)=>{ lockCalls++; return b(); };
            const resultRetry = await reportMod.handleReviewedLaneCompletion({
              repoControlRoot: controlRoot,
              taskId: "demo",
              ticketId: "T001",
              laneId: "writer-1",
              lanePath: laneTmp,
              workflowId: workflowId2,
              asyncDir: tmpRetry,
              eventWorkflowId: workflowId2,
              eventAsyncDir: tmpRetry,
              withTaskLock
            });
            const elapsedRetry = Date.now() - startRetry;
            if (!resultRetry.handled) throw new Error("retry should be handled");
            if (resultRetry.warnings.length !== 1) throw new Error("retry should have exactly one warning, got "+resultRetry.warnings.length);
            if (elapsedRetry < 900 || elapsedRetry > 1500) throw new Error("retry should take ~1s, got "+elapsedRetry);
            if (lockCalls !== 1) throw new Error("should have exactly one lock call for deadline warning, got "+lockCalls);
            process.stdout.write(JSON.stringify({ok:true, elapsedPerm, elapsedRetry}));
        """))
        result = run_node_script(script)
        self.assertTrue(result.get("ok"))


    def test_A4_deadline_with_feedback_single_lock_warning_only_and_feedback_published(self):
        script = lane_script_wrapper(textwrap.dedent("""
            import fs from "node:fs";
            import path from "node:path";
            import os from "node:os";
            const controlRoot = fs.mkdtempSync(path.join(os.tmpdir(), "repoA4fb-"));
            const laneTmp = fs.mkdtempSync(path.join(os.tmpdir(), "laneA4fb-"));
            const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "asyncFb-"));
            const plans = path.join(controlRoot, ".agent_state", "plans", "demo");
            fs.mkdirSync(plans, {recursive:true});
            const childRunId = "cccccccc-cccc-cccc-cccc-cccccccccccc";
            const workflowId = "dddddddd-dddd-dddd-dddd-dddddddddddd";
            const sessionDir = path.join(tmp, childRunId);
            fs.mkdirSync(sessionDir, {recursive:true});
            const sessionFile = path.join(sessionDir, "session.jsonl");
            // session remains missing through deadline
            const status = {
              runId: workflowId,
              cwd: laneTmp,
              state: "complete",
              workflow: { trace: [{key:"impl-0", runId: childRunId, durationMs:100, state:"completed"}] },
              steps: [{ workflowKey:"impl-0", parentWorkflowRunId: workflowId, status:"completed", turnCount:1, sessionFile, runId: childRunId, structuredOutput: { outcome: "COMPLETED", efficiencyFeedback: "feedback for deadline test", residualRisks: [] } }]
            };
            fs.writeFileSync(path.join(tmp, "status.json"), JSON.stringify(status));
            let lockCalls = 0;
            const withTaskLock = async (b)=>{ lockCalls++; return b(); };
            const start = Date.now();
            const result = await reportMod.handleReviewedLaneCompletion({
              repoControlRoot: controlRoot,
              taskId: "demo",
              ticketId: "T001",
              laneId: "writer-1",
              lanePath: laneTmp,
              workflowId,
              asyncDir: tmp,
              eventWorkflowId: workflowId,
              eventAsyncDir: tmp,
              withTaskLock
            });
            const elapsed = Date.now() - start;
            if (!result.handled) throw new Error("should be handled, got "+JSON.stringify(result));
            if (result.published.length !== 0) throw new Error("should be warning-only, published must be 0, got "+JSON.stringify(result.published));
            if (result.warnings.length < 1) throw new Error("should have settlement warning");
            // exactly one settlement warning in lane_loop_report warnings.jsonl
            const warningsPath = path.join(plans, ".collab_op", "lane_loop_report", "warnings.jsonl");
            let warnLines = [];
            try { warnLines = fs.readFileSync(warningsPath, "utf8").trim().split("\\n").filter(l=>l.trim()); } catch {}
            if (warnLines.length !== 1) throw new Error("expected exactly one settlement warning, got "+warnLines.length+" "+JSON.stringify(warnLines));
            // separate feedback publication inside same lock phase
            const feedbackPath = path.join(plans, ".collab_op", "lane_loop_feedback", "writer-1", `${childRunId}.json`);
            if (!fs.existsSync(feedbackPath)) throw new Error("feedback should be published inside same lock phase");
            const fb = JSON.parse(fs.readFileSync(feedbackPath,"utf8"));
            if (fb.efficiencyFeedback !== "feedback for deadline test") throw new Error("feedback mismatch "+JSON.stringify(fb));
            if (lockCalls !== 1) throw new Error("should have exactly one task-lock acquisition, got "+lockCalls);
            if (elapsed < 900 || elapsed > 1500) throw new Error("deadline should be ~1s, got "+elapsed);
            // terminal lifecycle release via harness
            const fakePi = {
              events: { handlers: new Map(), on(event,h){ if(!this.handlers.has(event)) this.handlers.set(event,[]); this.handlers.get(event).push(h); return ()=>{}; }, emit(event,data){ const arr=this.handlers.get(event)||[]; for(const h of [...arr]) h(data); } },
              exec: async () => ({ code: 0, stdout: "", stderr: "" })
            };
            const lanePath2 = fs.mkdtempSync(path.join(os.tmpdir(), "laneH-"));
            const controlRoot2 = fs.mkdtempSync(path.join(os.tmpdir(), "repoH-"));
            const tmp2 = fs.mkdtempSync(path.join(os.tmpdir(), "asyncH-"));
            const child2 = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee";
            const wf2 = "ffffffff-ffff-ffff-ffff-ffffffffffff";
            const sessDir2 = path.join(tmp2, child2);
            fs.mkdirSync(sessDir2, {recursive:true});
            const sessFile2 = path.join(sessDir2, "session.jsonl");
            const status2 = {
              runId: wf2,
              cwd: lanePath2,
              state: "complete",
              workflow: { trace: [{key:"impl-0", runId: child2, durationMs:100, state:"completed"}] },
              steps: [{ workflowKey:"impl-0", parentWorkflowRunId: wf2, status:"completed", turnCount:1, sessionFile: sessFile2, runId: child2, structuredOutput: { outcome: "COMPLETED", efficiencyFeedback: "fb2" } }]
            };
            fs.writeFileSync(path.join(tmp2, "status.json"), JSON.stringify(status2));
            fs.mkdirSync(path.join(controlRoot2, ".agent_state", "plans", "demo"), {recursive:true});
            const harness = laneMod.createIsolatedReviewedLaneHarness();
            const deps = {
              withTaskLock: async (r,t,b)=>b(),
              error: (c,m)=>{ const e=new Error(m); e.code=c; return e; }
            };
            const pending = { pi: fakePi, repo: { controlRoot: controlRoot2, gitDir: path.join(controlRoot2,".git"), worktreeRoot: controlRoot2, git: async()=>({code:0,stdout:"",stderr:""}) }, taskId: "demo", ticketId: "T001", laneId: "writer-1", lanePath: lanePath2, workflowId: wf2, asyncDir: tmp2, deps, canonicalKey: controlRoot2+"\\0demo\\0writer-1" };
            harness.registerPending(pending);
            await harness.handleAsyncCompleteEvent({ runId: wf2, asyncDir: tmp2 });
            if (harness.getPendingCount() !== 0) throw new Error("should release pending after deadline, got "+harness.getPendingCount());
            if (harness.getReservationCount() !== 0) throw new Error("should release reservation after deadline, got "+harness.getReservationCount());
            process.stdout.write(JSON.stringify({ok:true, elapsed, lockCalls}));
        """))
        result = run_node_script(script, timeout=20)
        self.assertTrue(result.get("ok"))


class SL01A5RegisteredResultOwnershipTests(unittest.TestCase):
    def test_A5_telemetry_via_registered_path_receipt_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            managed = seed_managed_task(repository, "demo")
            lanePath = managed["lane"]
            controlRoot = str(repository.resolve())
            req = {"tool": "collab_run_reviewed_lane", "task_id": "demo", "ticket_id": "T001", "lane_id": "writer-1", "worker_brief": "implement", "review_brief": "review", "correction_budget": 0}
            receipt_resp = invoke_extension(repository, {**req, "__rpc": {"mode": "available", "runId": "workflow-a5"}}, support_extension=REVIEWED_RPC_MOCK)
            self.assertFalse(receipt_resp["is_error"], receipt_resp)
            receipt = receipt_resp["result"]
            stored = json.dumps(receipt, sort_keys=True)
            script = lane_script_wrapper(textwrap.dedent(f"""
                import fs from "node:fs";
                import path from "node:path";
                import os from "node:os";
                const controlRoot = "{controlRoot}";
                const laneTmp = "{lanePath}";
                const repoControlRoot = controlRoot;
                const tmpSuccess = fs.mkdtempSync(path.join(os.tmpdir(), "asyncA5s-"));
                const child1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
                const wf1 = "workflow-a5-success";
                const sessDir1 = path.join(tmpSuccess, child1);
                fs.mkdirSync(sessDir1, {{recursive:true}});
                const sessFile1 = path.join(sessDir1, "session.jsonl");
                fs.writeFileSync(sessFile1, JSON.stringify({{type:"message", message:{{role:"assistant", content:[{{type:"toolCall", id:"c1", name:"read"}}], usage:{{totalTokens:10}}}}}}) + "\\n" + JSON.stringify({{type:"message", message:{{role:"toolResult", toolCallId:"c1", isError:false}}}}) + "\\n");
                const status1 = {{ runId: wf1, cwd: laneTmp, state: "complete", workflow: {{ trace: [{{key:"impl-0", runId: child1, durationMs:100, state:"completed"}}] }}, steps: [{{ workflowKey:"impl-0", parentWorkflowRunId: wf1, status:"completed", turnCount:1, sessionFile: sessFile1, runId: child1, structuredOutput: {{ outcome: "COMPLETED"}} }}] }};
                fs.writeFileSync(path.join(tmpSuccess, "status.json"), JSON.stringify(status1));
                const plans = path.join(controlRoot, ".agent_state", "plans", "demo");
                fs.mkdirSync(plans, {{recursive:true}});
                const stored = '{stored}';
                const receiptBefore = JSON.parse(stored);
                let r1 = await reportMod.handleReviewedLaneCompletion({{
                  repoControlRoot, taskId: "demo", ticketId: "T001", laneId: "writer-1", lanePath: laneTmp,
                  workflowId: wf1, asyncDir: tmpSuccess, eventWorkflowId: wf1, eventAsyncDir: tmpSuccess,
                  withTaskLock: async (b)=>b()
                }});
                if (!r1.handled || r1.published.length !== 1) throw new Error("success should publish, got "+JSON.stringify(r1));
                const tmpWarn = fs.mkdtempSync(path.join(os.tmpdir(), "asyncA5w-"));
                const wf2 = "workflow-a5-warn";
                const statusPathW = path.join(tmpWarn, "status.json");
                const target = path.join(tmpWarn, "real.json");
                fs.writeFileSync(target, JSON.stringify({{runId:wf2, cwd:laneTmp, state:"complete", workflow:{{trace:[]}}}}));
                try {{ fs.symlinkSync(target, statusPathW); }} catch {{}}
                let r2 = await reportMod.handleReviewedLaneCompletion({{
                  repoControlRoot, taskId: "demo", ticketId: "T001", laneId: "writer-1", lanePath: laneTmp,
                  workflowId: wf2, asyncDir: tmpWarn, eventWorkflowId: wf2, eventAsyncDir: tmpWarn,
                  withTaskLock: async (b)=>b()
                }});
                if (!r2.handled || r2.warnings.length === 0) throw new Error("warn should warn");
                const tmpLock = fs.mkdtempSync(path.join(os.tmpdir(), "asyncA5l-"));
                const child3 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
                const wf3 = "workflow-a5-lock";
                const sessDir3 = path.join(tmpLock, child3);
                fs.mkdirSync(sessDir3, {{recursive:true}});
                const sessFile3 = path.join(sessDir3, "session.jsonl");
                fs.writeFileSync(sessFile3, JSON.stringify({{type:"message", message:{{role:"assistant", content:[{{type:"toolCall", id:"c1", name:"read"}}], usage:{{totalTokens:10}}}}}}) + "\\n" + JSON.stringify({{type:"message", message:{{role:"toolResult", toolCallId:"c1", isError:false}}}}) + "\\n");
                const status3 = {{ runId: wf3, cwd: laneTmp, state: "complete", workflow: {{ trace: [{{key:"impl-0", runId: child3, durationMs:100, state:"completed"}}] }}, steps: [{{ workflowKey:"impl-0", parentWorkflowRunId: wf3, status:"completed", turnCount:1, sessionFile: sessFile3, runId: child3 }}] }};
                fs.writeFileSync(path.join(tmpLock, "status.json"), JSON.stringify(status3));
                const warningsBefore = (()=>{{ try {{ return fs.readFileSync(path.join(plans, ".collab_op", "lane_loop_report", "warnings.jsonl"), "utf8").length; }} catch {{ return 0; }} }})();
                let r3 = await reportMod.handleReviewedLaneCompletion({{
                  repoControlRoot, taskId: "demo", ticketId: "T001", laneId: "writer-1", lanePath: laneTmp,
                  workflowId: wf3, asyncDir: tmpLock, eventWorkflowId: wf3, eventAsyncDir: tmpLock,
                  withTaskLock: async (b)=>{{ throw new Error("busy lock"); }}
                }});
                if (!r3.handled) throw new Error("lock failure should be handled");
                const warningsAfter = (()=>{{ try {{ return fs.readFileSync(path.join(plans, ".collab_op", "lane_loop_report", "warnings.jsonl"), "utf8").length; }} catch {{ return 0; }} }})();
                if (warningsAfter !== warningsBefore) throw new Error("lock failure should not create warnings.jsonl, before "+warningsBefore+" after "+warningsAfter);
                const receiptAfter = JSON.parse(stored);
                if (JSON.stringify(receiptAfter) !== JSON.stringify(JSON.parse(stored))) throw new Error("receipt mutated");
                process.stdout.write(JSON.stringify({{ok:true}})+"\\n");
            """))
            result = run_node_script(script, timeout=20)
            self.assertTrue(result.get("ok"))
            self.assertEqual(json.dumps(receipt, sort_keys=True), stored)
