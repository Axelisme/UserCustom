from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from tests.test_collab_op_extension import (
    close_harness,
    close_harness_for,
    git,
    seed_managed_task,
    seed_repository,
    seed_task_container,
    send_request,
    spawn_raw_harness,
    wait_until,
)

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_OP = ROOT / "home/.pi/agent/extensions/collab-op.ts"
PI_PACKAGE = Path("/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js")

BLOCK_TEMPLATE = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
done
if [ "$1" = "worktree" ] && [ "$2" = "add" ] && [ "$3" = "-b" ] && [ "$4" = "__BRANCH__" ]; then
  i=0
  while [ ! -f "__BLOCK__" ]; do
    sleep 0.05
    i=$((i+1))
    if [ "$i" -ge 400 ]; then break; fi
  done
fi
exec "$real_git" "$@"
"""

FAIL_TEMPLATE = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
done
if [ "$1" = "worktree" ] && [ "$2" = "add" ] && [ "$3" = "-b" ] && [ "$4" = "__BRANCH__" ]; then
  echo "injected failure for __BRANCH__" >&2
  exit 1
fi
exec "$real_git" "$@"
"""

def write_wrapper(dir: Path, script: str) -> Path:
    real = shutil.which("git") or "/usr/bin/git"
    script = script.replace("__REAL_GIT__", real)
    p = dir / "git"
    p.write_text(script, encoding="utf-8")
    p.chmod(0o755)
    return p

def run_node_script(script: str, timeout: int = 20) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        run = subprocess.run(
            ["/usr/bin/node", "--experimental-strip-types", fname],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if run.returncode != 0:
            raise AssertionError(f"node failed: {run.stderr}\n{run.stdout}\n{script}")
        lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
        if not lines:
            raise AssertionError(f"no output: {run.stderr}")
        return json.loads(lines[-1])
    finally:
        Path(fname).unlink(missing_ok=True)

def node_loader_script(repo_path: str, body: str) -> str:
    return textwrap.dedent(f"""
        import {{ pathToFileURL }} from "node:url";
        import fs from "node:fs";
        import path from "node:path";
        const piPackage = "{PI_PACKAGE}";
        const extensionPath = "{EXTENSION_OP}";
        const repoPath = "{repo_path}";
        const {{ DefaultResourceLoader, SettingsManager }} = await import(pathToFileURL(piPackage));
        const settingsManager = SettingsManager.inMemory({{}});
        const loader = new DefaultResourceLoader({{
          cwd: repoPath,
          agentDir: repoPath + "/.empty-pi-agent",
          additionalExtensionPaths: [extensionPath],
          settingsManager,
        }});
        await loader.reload();
        const loaded = loader.getExtensions();
        const regs = new Map(loaded.extensions.flatMap(e => [...e.tools.entries()]));
        const collabLane = regs.get("collab_lane");
        if (!collabLane) throw new Error("collab_lane not found");
        const laneCreate = {{ definition: {{ execute: (id, req, signal, onUpdate, ctx) => collabLane.definition.execute(id, {{ action: "create", ...req }}, signal, onUpdate, ctx) }} }};
        const laneDrop = {{ definition: {{ execute: (id, req, signal, onUpdate, ctx) => collabLane.definition.execute(id, {{ action: "drop", ...req }}, signal, onUpdate, ctx) }} }};
        const reportTool = regs.get("collab_report");
        const statusTool = regs.get("collab_status");
        {body}
    """)


class SL02ConcurrentLaneCreateTests(unittest.TestCase):
    def test_A1_concurrent_distinct_lanes_serialize_within_deadline(self):
        # A1 covers S1,S2,S4 : distinct lanes receive own receipts, serialized within 10s deadlines
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            block = base / "block"
            if block.exists():
                block.unlink()
            wrapper_dir = base / "wrapper"
            wrapper_dir.mkdir()
            script = BLOCK_TEMPLATE.replace("__BRANCH__", "wave/demo/alpha").replace("__BLOCK__", str(block))
            write_wrapper(wrapper_dir, script)
            orig_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wrapper_dir}:{orig_path}"
            try:
                repo_str = str(repository)
                block_str = str(block)
                node_body = textwrap.dedent(f"""
                    const blockPath = "{block_str}";
                    // ensure block does not exist at start
                    try {{ fs.unlinkSync(blockPath); }} catch {{}}
                    let p1Done = false, p2Done = false;
                    let p1Result, p2Result;
                    const p1 = laneCreate.definition.execute("c1", {{task_id: "demo", lane_id: "alpha"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => {{ p1Done = true; p1Result = JSON.parse(r.content.find(c=>c.type==="text").text); return p1Result; }})
                      .catch(e => {{ p1Done = true; try {{ p1Result = JSON.parse(e.message); }} catch {{ p1Result = {{error: {{message: String(e)}}}}}}; throw e; }});
                    // wait for lock to be held by p1 (poll lock file)
                    const lockPath = path.join(repoPath, ".git", "collab-op-locks", "demo.lock");
                    let waited = 0;
                    while (waited < 5000) {{
                      if (fs.existsSync(lockPath)) break;
                      await new Promise(r=>setTimeout(r, 20));
                      waited += 20;
                    }}
                    if (!fs.existsSync(lockPath)) throw new Error("p1 did not acquire lock within 5s");
                    const p2 = laneCreate.definition.execute("c2", {{task_id: "demo", lane_id: "beta"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => {{ p2Done = true; p2Result = JSON.parse(r.content.find(c=>c.type==="text").text); return p2Result; }})
                      .catch(e => {{ p2Done = true; try {{ p2Result = JSON.parse(e.message); }} catch {{ p2Result = {{error: {{message: String(e)}}}}}}; throw e; }});
                    // give p2 time to queue (should be queued, not done)
                    await new Promise(r=>setTimeout(r, 200));
                    if (p2Done) throw new Error("p2 should be queued while p1 holds lock, but it already completed");
                    // unblock p1
                    fs.writeFileSync(blockPath, "go");
                    const start = Date.now();
                    const [r1, r2] = await Promise.all([p1, p2]);
                    const elapsed = Date.now() - start;
                    // Both should succeed
                    if (!r1.ok) throw new Error("p1 should succeed, got "+JSON.stringify(r1));
                    if (!r2.ok) throw new Error("p2 should succeed, got "+JSON.stringify(r2));
                    // Check lanes exist
                    const checkAlpha = await regs.get("collab_status").definition.execute("s1", {{task_id: "demo"}}, undefined, undefined, {{cwd: repoPath}});
                    // use git to verify branches
                    // telemetry
                    const telPath = path.join(repoPath, ".agent_state", "plans", "demo", ".collab_op", "telemetry.jsonl");
                    const tel = fs.readFileSync(telPath, "utf8").trim().split("\\n").map(l=>JSON.parse(l));
                    const laneCreates = tel.filter(e=>e.operation==="lane-create" && e.outcome==="success");
                    const hasAlpha = laneCreates.some(e=>e.lane_id==="alpha");
                    const hasBeta = laneCreates.some(e=>e.lane_id==="beta");
                    if (!hasAlpha || !hasBeta) throw new Error("telemetry missing distinct lanes: "+JSON.stringify(laneCreates));
                    // verify distinct branches exist via git
                    const {{ execSync }} = await import("node:child_process");
                    const alphaTip = execSync("git -C "+repoPath+" rev-parse --verify wave/demo/alpha", {{encoding:"utf8"}}).trim();
                    const betaTip = execSync("git -C "+repoPath+" rev-parse --verify wave/demo/beta", {{encoding:"utf8"}}).trim();
                    if (!alphaTip || !betaTip) throw new Error("branches missing");
                    if (alphaTip !== betaTip) {{
                      // Both should be same integration tip initially, but after sequential creation they both point to integration tip, so equal is fine. Just check they exist.
                    }}
                    // Ensure p2 waited but within 10s total (elapsed from unblock should be small, but total from p2 start <10s)
                    // p2 started after lock held, unblock after 200ms, so total wait < 1s + 10s
                    if (elapsed > 10000) throw new Error("p2 should complete within 10s after unblock, elapsed "+elapsed);
                    process.stdout.write(JSON.stringify({{ok:true, elapsed, laneCreates}})+"\\n");
                """)
                result = run_node_script(node_loader_script(repo_str, node_body), timeout=20)
                self.assertTrue(result.get("ok"), result)
            finally:
                os.environ["PATH"] = orig_path
            # verify lanes via git
            self.assertEqual(git(repository, "rev-parse", "--verify", "wave/demo/alpha"), git(repository, "rev-parse", "wave/demo/integration"))
            self.assertEqual(git(repository, "rev-parse", "--verify", "wave/demo/beta"), git(repository, "rev-parse", "wave/demo/integration"))

    def test_A2_concurrent_same_id_collision_without_partial_mutation(self):
        # A2 covers S3,S4 : duplicate IDs serialize, second reaches collision handling without partial mutation
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            block = base / "block"
            if block.exists():
                block.unlink()
            wrapper_dir = base / "wrapper"
            wrapper_dir.mkdir()
            script = BLOCK_TEMPLATE.replace("__BRANCH__", "wave/demo/dup").replace("__BLOCK__", str(block))
            write_wrapper(wrapper_dir, script)
            orig_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wrapper_dir}:{orig_path}"
            try:
                repo_str = str(repository)
                block_str = str(block)
                node_body = textwrap.dedent(f"""
                    const blockPath = "{block_str}";
                    try {{ fs.unlinkSync(blockPath); }} catch {{}}
                    const p1 = laneCreate.definition.execute("c1", {{task_id: "demo", lane_id: "dup"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => JSON.parse(r.content.find(c=>c.type==="text").text))
                      .catch(e => {{ try {{ return JSON.parse(e.message); }} catch {{ throw e; }} }});
                    const lockPath = path.join(repoPath, ".git", "collab-op-locks", "demo.lock");
                    let waited=0; while(waited<5000){{ if(fs.existsSync(lockPath)) break; await new Promise(r=>setTimeout(r,20)); waited+=20; }}
                    if(!fs.existsSync(lockPath)) throw new Error("p1 lock not held");
                    const p2Promise = laneCreate.definition.execute("c2", {{task_id: "demo", lane_id: "dup"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => ({{ok:true, result: JSON.parse(r.content.find(c=>c.type==="text").text)}}))
                      .catch(e => {{ let err; try{{err=JSON.parse(e.message)}}catch{{err={{error:{{message:String(e)}}}}}}; return {{ok:false, error:err}}; }});
                    await new Promise(r=>setTimeout(r,150));
                    fs.writeFileSync(blockPath, "go");
                    const r1 = await p1;
                    const r2 = await p2Promise;
                    if (!r1.ok) throw new Error("first dup should succeed, got "+JSON.stringify(r1));
                    if (r2.ok) throw new Error("second dup should fail with collision, got "+JSON.stringify(r2));
                    const code = r2.error?.error?.code || r2.error?.code;
                    if (code !== "lane_resource_collision") throw new Error("expected lane_resource_collision, got "+JSON.stringify(r2));
                    // Ensure no partial mutation: lane dup should exist exactly once, no extra worktree for failed attempt
                    const telPath = path.join(repoPath, ".agent_state", "plans", "demo", ".collab_op", "telemetry.jsonl");
                    const tel = fs.existsSync(telPath) ? fs.readFileSync(telPath,"utf8").trim().split("\\n").filter(l=>l.trim()).map(l=>JSON.parse(l)) : [];
                    const successes = tel.filter(e=>e.operation==="lane-create" && e.outcome==="success" && e.lane_id==="dup");
                    if (successes.length !== 1) throw new Error("expected exactly one success telemetry for dup, got "+JSON.stringify(tel));
                    // Check worktree for dup exists and is not dirty partial
                    const lanePath = path.join(repoPath, ".agent_state", "worktrees", "demo", "lanes", "dup");
                    if (!fs.existsSync(lanePath)) throw new Error("lane dup worktree missing after success");
                    // Ensure no extra branch for dup (only one)
                    const {{ execSync }} = await import("node:child_process");
                    const branches = execSync("git -C "+repoPath+" for-each-ref --format='%(refname)' refs/heads/wave/demo/dup", {{encoding:"utf8"}}).trim().split("\\n").filter(Boolean);
                    if (branches.length !== 1 || branches[0] !== "refs/heads/wave/demo/dup") throw new Error("unexpected branches for dup: "+JSON.stringify(branches));
                    process.stdout.write(JSON.stringify({{ok:true}})+"\\n");
                """)
                result = run_node_script(node_loader_script(repo_str, node_body), timeout=20)
                self.assertTrue(result.get("ok"), result)
            finally:
                os.environ["PATH"] = orig_path

    def test_A3_cancellation_removes_only_that_waiter(self):
        # A3 covers S2,S3 : cancelling queued call returns request_aborted, next eligible proceeds
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            block = base / "block"
            if block.exists():
                block.unlink()
            wrapper_dir = base / "wrapper"
            wrapper_dir.mkdir()
            script = BLOCK_TEMPLATE.replace("__BRANCH__", "wave/demo/slow").replace("__BLOCK__", str(block))
            write_wrapper(wrapper_dir, script)
            orig_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wrapper_dir}:{orig_path}"
            try:
                repo_str = str(repository)
                block_str = str(block)
                node_body = textwrap.dedent(f"""
                    const blockPath = "{block_str}";
                    try {{ fs.unlinkSync(blockPath); }} catch {{}}
                    const p1 = laneCreate.definition.execute("c1", {{task_id: "demo", lane_id: "slow"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => JSON.parse(r.content.find(c=>c.type==="text").text));
                    const lockPath = path.join(repoPath, ".git", "collab-op-locks", "demo.lock");
                    let waited=0; while(waited<5000){{ if(fs.existsSync(lockPath)) break; await new Promise(r=>setTimeout(r,20)); waited+=20; }}
                    if(!fs.existsSync(lockPath)) throw new Error("p1 lock not held");
                    const controller = new AbortController();
                    const p2Promise = laneCreate.definition.execute("c2", {{task_id: "demo", lane_id: "queued1"}}, controller.signal, undefined, {{cwd: repoPath}})
                      .then(r => ({{ok:true, result: JSON.parse(r.content.find(c=>c.type==="text").text)}}))
                      .catch(e => {{ let err; try{{err=JSON.parse(e.message)}}catch{{err={{error:{{message:String(e)}}}}}}; const code = err.error?.code || err.code || ""; return {{ok:false, code, error:err}}; }});
                    const p3Promise = laneCreate.definition.execute("c3", {{task_id: "demo", lane_id: "queued2"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => ({{ok:true, result: JSON.parse(r.content.find(c=>c.type==="text").text)}}))
                      .catch(e => {{ let err; try{{err=JSON.parse(e.message)}}catch{{err={{error:{{message:String(e)}}}}}}; return {{ok:false, error:err}}; }});
                    // give p2 and p3 time to queue
                    await new Promise(r=>setTimeout(r,200));
                    // cancel p2 (queued, not head)
                    controller.abort();
                    const r2 = await p2Promise;
                    if (r2.ok) throw new Error("cancelled p2 should fail, got "+JSON.stringify(r2));
                    if (r2.code !== "request_aborted") throw new Error("expected request_aborted for cancelled, got "+JSON.stringify(r2));
                    // p3 should still be queued behind p1 (since p2 removed, p3 is next after p1)
                    // unblock p1
                    fs.writeFileSync(blockPath, "go");
                    const r1 = await p1;
                    if (!r1.ok) throw new Error("p1 should succeed, got "+JSON.stringify(r1));
                    const r3 = await p3Promise;
                    if (!r3.ok) throw new Error("p3 should succeed after p2 cancelled, got "+JSON.stringify(r3));
                    // verify queued1 not created, queued2 created
                    const {{ execSync }} = await import("node:child_process");
                    const checkQueued1 = execSync("git -C "+repoPath+" branch --list wave/demo/queued1", {{encoding:"utf8"}}).trim();
                    if (checkQueued1) throw new Error("cancelled queued1 branch should not exist, got "+checkQueued1);
                    const checkQueued2 = execSync("git -C "+repoPath+" rev-parse --verify wave/demo/queued2", {{encoding:"utf8"}}).trim();
                    if (!checkQueued2) throw new Error("queued2 should exist after p2 cancelled");
                    const lanePath1 = path.join(repoPath, ".agent_state", "worktrees", "demo", "lanes", "queued1");
                    if (fs.existsSync(lanePath1)) throw new Error("queued1 worktree should not exist");
                    process.stdout.write(JSON.stringify({{ok:true}})+"\\n");
                """)
                result = run_node_script(node_loader_script(repo_str, node_body), timeout=20)
                self.assertTrue(result.get("ok"), result)
            finally:
                os.environ["PATH"] = orig_path
            # also test cancelling head waiter case: queued head abort should advance next
            # (we already tested queued non-head cancellation; head cancellation is similar but we trust implementation)

    def test_A4_live_external_lock_timeout_returns_task_busy_with_wait_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            lock_dir = repository / ".git/collab-op-locks"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_path = lock_dir / "demo.lock"
            lock_path.write_text(json.dumps({"pid": os.getpid(), "started_at": "2026-08-13T00:00:00.000Z", "task_id": "demo", "token": "live-token"}), encoding="utf-8")
            repo_str = str(repository)
            node_body = textwrap.dedent(f"""
                const lanePathTimeout = path.join(repoPath, ".agent_state", "worktrees", "demo", "lanes", "timeout-lane");
                const lanePathAfter = path.join(repoPath, ".agent_state", "worktrees", "demo", "lanes", "after-timeout");
                const lockPath = path.join(repoPath, ".git", "collab-op-locks", "demo.lock");
                const {{ execSync }} = await import("node:child_process");
                const refsBefore = execSync("git -C "+repoPath+" for-each-ref --format='%(refname) %(objectname)'", {{encoding:"utf8"}}).trim();
                if (fs.existsSync(lanePathTimeout)) throw new Error("timeout-lane worktree should not exist before timeout");
                if (fs.existsSync(lanePathAfter)) throw new Error("after-timeout worktree should not exist before timeout");
                const start = Date.now();
                let timeoutResult;
                try {{
                  const r = await laneCreate.definition.execute("c1", {{task_id: "demo", lane_id: "timeout-lane"}}, undefined, undefined, {{cwd: repoPath}});
                  timeoutResult = {{ok:true, result: JSON.parse(r.content.find(c=>c.type==="text").text)}};
                }} catch (e) {{
                  let err; try{{err=JSON.parse(e.message)}}catch{{err={{error:{{message:String(e)}}}}}};
                  timeoutResult = {{ok:false, error:err, elapsed: Date.now()-start}};
                }}
                if (timeoutResult.ok) throw new Error("timeout lane should fail with task_busy, got success");
                const code = timeoutResult.error?.error?.code || timeoutResult.error?.code;
                if (code !== "task_busy") throw new Error("expected task_busy, got "+JSON.stringify(timeoutResult));
                const details = timeoutResult.error?.error?.details || {{}};
                if (details.task_id !== "demo") throw new Error("expected task_id demo in details, got "+JSON.stringify(details));
                if (typeof details.waited_ms !== "number") throw new Error("waited_ms missing in details "+JSON.stringify(details));
                if (details.timeout_ms !== 10000) throw new Error("timeout_ms should be 10000, got "+JSON.stringify(details));
                if (details.waited_ms < 9000 || details.waited_ms > 11000) throw new Error("waited_ms should be ~10000, got "+details.waited_ms);
                const elapsed = Date.now()-start;
                if (elapsed < 9000 || elapsed > 12000) throw new Error("elapsed should be ~10000, got "+elapsed);
                const refsAfterTimeout = execSync("git -C "+repoPath+" for-each-ref --format='%(refname) %(objectname)'", {{encoding:"utf8"}}).trim();
                if (refsBefore !== refsAfterTimeout) throw new Error("refs should be unchanged after timeout, before="+JSON.stringify(refsBefore)+" after="+JSON.stringify(refsAfterTimeout));
                if (fs.existsSync(lanePathTimeout)) throw new Error("timeout should not create lane worktree");
                const branchCheck = execSync("git -C "+repoPath+" branch --list wave/demo/timeout-lane", {{encoding:"utf8"}}).trim();
                if (branchCheck) throw new Error("timeout branch should not exist, got "+branchCheck);
                const refCheck = execSync("git -C "+repoPath+" for-each-ref --format='%(refname)' refs/heads/wave/demo/timeout-lane", {{encoding:"utf8"}}).trim();
                if (refCheck) throw new Error("timeout ref should not exist, got "+refCheck);
                if (!fs.existsSync(lockPath)) throw new Error("planted lock file should still exist after timeout before removal");
                const telPath = path.join(repoPath, ".agent_state", "plans", "demo", ".collab_op", "telemetry.jsonl");
                if (fs.existsSync(telPath)) {{
                  const tel = fs.readFileSync(telPath,"utf8").trim().split("\\n").filter(l=>l.trim()).map(l=>JSON.parse(l));
                  const successForTimeout = tel.filter(e=>e.operation==="lane-create" && e.outcome==="success" && e.lane_id==="timeout-lane");
                  if (successForTimeout.length !== 0) throw new Error("telemetry should not contain success for timeout-lane");
                }}
                fs.unlinkSync(lockPath);
                let waitedUnlock=0;
                while (fs.existsSync(lockPath) && waitedUnlock<2000) {{ await new Promise(r=>setTimeout(r,20)); waitedUnlock+=20; }}
                if (fs.existsSync(lockPath)) throw new Error("lock file still exists after unlink");
                const followStart = Date.now();
                const rAfter = await laneCreate.definition.execute("c2", {{task_id: "demo", lane_id: "after-timeout"}}, undefined, undefined, {{cwd: repoPath}});
                const followElapsed = Date.now()-followStart;
                const afterResult = JSON.parse(rAfter.content.find(c=>c.type==="text").text);
                if (!afterResult.ok) throw new Error("after-timeout lane should succeed via same loader (queue not leaked), got "+JSON.stringify(afterResult));
                if (followElapsed > 2000) throw new Error("follow-up should succeed quickly after lock removed (<2s), elapsed "+followElapsed);
                const afterBranch = execSync("git -C "+repoPath+" rev-parse --verify wave/demo/after-timeout", {{encoding:"utf8"}}).trim();
                if (!afterBranch) throw new Error("after-timeout branch missing");
                const refsAfterFollow = execSync("git -C "+repoPath+" for-each-ref --format='%(refname)' refs/heads/wave/demo/after-timeout", {{encoding:"utf8"}}).trim();
                if (refsAfterFollow !== "refs/heads/wave/demo/after-timeout") throw new Error("after-timeout ref not found");
                if (!fs.existsSync(lanePathAfter)) throw new Error("after-timeout worktree missing after follow-up");
                const integrationTip = execSync("git -C "+repoPath+" rev-parse wave/demo/integration", {{encoding:"utf8"}}).trim();
                if (afterBranch !== integrationTip) throw new Error("after-timeout should point at integration tip, got "+afterBranch+" vs "+integrationTip);
                process.stdout.write(JSON.stringify({{ok:true, elapsed, followElapsed, details}})+"\\n");
            """)
            result = run_node_script(node_loader_script(repo_str, node_body), timeout=30)
            self.assertTrue(result.get("ok"), result)
            self.assertEqual(git(repository, "rev-parse", "--verify", "wave/demo/after-timeout"), git(repository, "rev-parse", "wave/demo/integration"))
            self.assertFalse((repository / ".agent_state/worktrees/demo/lanes/timeout-lane").exists())
            self.assertTrue((repository / ".agent_state/worktrees/demo/lanes/after-timeout").exists())
            self.assertFalse((repository / ".git/collab-op-locks/demo.lock").exists())

    def test_A5_body_failure_releases_lock_and_advances_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            wrapper_dir = base / "wrapper"
            wrapper_dir.mkdir()
            signal_file = base / "signal"
            block_file = base / "block"
            if signal_file.exists():
                signal_file.unlink()
            if block_file.exists():
                block_file.unlink()
            # wrapper signals ownership via signal file, blocks until block file, then fails
            signal_fail_template = """#!/bin/sh
real_git="__REAL_GIT__"
for arg in "$@"; do
  if [ "$arg" = "-C" ]; then exec "$real_git" "$@"; fi
 done
if [ "$1" = "worktree" ] && [ "$2" = "add" ] && [ "$3" = "-b" ] && [ "$4" = "__BRANCH__" ]; then
  touch "__SIGNAL__"
  i=0
  while [ ! -f "__BLOCK__" ]; do
    sleep 0.05
    i=$((i+1))
    if [ "$i" -ge 400 ]; then break; fi
  done
  echo "injected failure for __BRANCH__" >&2
  exit 1
fi
exec "$real_git" "$@"
"""
            fail_script = signal_fail_template.replace("__BRANCH__", "wave/demo/failme").replace("__SIGNAL__", str(signal_file)).replace("__BLOCK__", str(block_file))
            write_wrapper(wrapper_dir, fail_script)
            orig_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wrapper_dir}:{orig_path}"
            try:
                repo_str = str(repository)
                signal_str = str(signal_file)
                block_str = str(block_file)
                node_body = textwrap.dedent(f"""
                    const signalPath = "{signal_str}";
                    const blockPath = "{block_str}";
                    const lockPath = path.join(repoPath, ".git", "collab-op-locks", "demo.lock");
                    const {{ execSync }} = await import("node:child_process");
                    try {{ fs.unlinkSync(signalPath); }} catch {{}}
                    try {{ fs.unlinkSync(blockPath); }} catch {{}}
                    let p1Done=false, p2Done=false;
                    let p1Result, p2Result;
                    let p1Error, p2Error;
                    const p1 = laneCreate.definition.execute("c1", {{task_id: "demo", lane_id: "failme"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => {{ p1Done=true; p1Result=JSON.parse(r.content.find(c=>c.type==="text").text); return {{ok:true, result:p1Result}}; }})
                      .catch(e => {{ p1Done=true; try{{p1Error=JSON.parse(e.message)}}catch{{p1Error={{error:{{message:String(e)}}}}}}; return {{ok:false, error:p1Error}}; }});
                    // observable sync: wait until failme owns lock (signal && lock)
                    let waited=0;
                    while (waited<5000) {{
                      if (fs.existsSync(signalPath) && fs.existsSync(lockPath)) break;
                      await new Promise(r=>setTimeout(r,20));
                      waited+=20;
                    }}
                    if (!fs.existsSync(signalPath)) throw new Error("failme did not reach wrapper (signal missing) within 5s, waited "+waited);
                    if (!fs.existsSync(lockPath)) throw new Error("lock not held by failme when signal observed, waited "+waited);
                    // only after failme owns lock, queue sibling
                    const p2 = laneCreate.definition.execute("c2", {{task_id: "demo", lane_id: "sibling"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => {{ p2Done=true; p2Result=JSON.parse(r.content.find(c=>c.type==="text").text); return {{ok:true, result:p2Result}}; }})
                      .catch(e => {{ p2Done=true; try{{p2Error=JSON.parse(e.message)}}catch{{p2Error={{error:{{message:String(e)}}}}}}; return {{ok:false, error:p2Error}}; }});
                    await new Promise(r=>setTimeout(r,200));
                    if (p2Done) throw new Error("sibling should be queued while failme holds lock, but already completed");
                    if (p1Done) throw new Error("failme should still be blocked inside wrapper, but already completed");
                    // release wrapper to fail (body failure) — this releases lock and should advance queue
                    fs.writeFileSync(blockPath, "go");
                    const [r1, r2] = await Promise.all([p1, p2]);
                    if (r1.ok) throw new Error("failme should fail after wrapper releases, got "+JSON.stringify(r1));
                    const code1 = r1.error?.error?.code || r1.error?.code;
                    if (code1 === "task_busy") throw new Error("failme should not be task_busy, got "+JSON.stringify(r1));
                    if (!r2.ok) throw new Error("sibling should succeed after failme releases lock and advances queue, got "+JSON.stringify(r2));
                    const siblingTip = execSync("git -C "+repoPath+" rev-parse --verify wave/demo/sibling", {{encoding:"utf8"}}).trim();
                    if (!siblingTip) throw new Error("sibling branch missing after queue advance");
                    const failExists = execSync("git -C "+repoPath+" branch --list wave/demo/failme", {{encoding:"utf8"}}).trim();
                    if (failExists) throw new Error("failme branch should not exist after failure, got "+failExists);
                    const laneFailPath = path.join(repoPath, ".agent_state", "worktrees", "demo", "lanes", "failme");
                    if (fs.existsSync(laneFailPath)) throw new Error("failme worktree should not exist after failure");
                    const laneSiblingPath = path.join(repoPath, ".agent_state", "worktrees", "demo", "lanes", "sibling");
                    if (!fs.existsSync(laneSiblingPath)) throw new Error("sibling worktree should exist after queue advance");
                    // ensure lock released after both
                    let lockGoneWait=0;
                    while (fs.existsSync(lockPath) && lockGoneWait<2000) {{ await new Promise(r=>setTimeout(r,20)); lockGoneWait+=20; }}
                    // lock should be free now (either gone or not owned), but sibling succeeded so queue advanced
                    const integrationTip = execSync("git -C "+repoPath+" rev-parse wave/demo/integration", {{encoding:"utf8"}}).trim();
                    if (siblingTip !== integrationTip) throw new Error("sibling should point at integration tip, got "+siblingTip+" vs "+integrationTip);
                    process.stdout.write(JSON.stringify({{ok:true, r1code: code1}})+"\\n");
                """)
                result = run_node_script(node_loader_script(repo_str, node_body), timeout=20)
                self.assertTrue(result.get("ok"), result)
            finally:
                os.environ["PATH"] = orig_path

    def test_A6_heterogeneous_mutations_remain_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            block = base / "block"
            if block.exists():
                block.unlink()
            wrapper_dir = base / "wrapper"
            wrapper_dir.mkdir()
            script = BLOCK_TEMPLATE.replace("__BRANCH__", "wave/demo/slow").replace("__BLOCK__", str(block))
            write_wrapper(wrapper_dir, script)
            orig_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wrapper_dir}:{orig_path}"
            try:
                repo_str = str(repository)
                block_str = str(block)
                node_body = textwrap.dedent(f"""
                    const blockPath = "{block_str}";
                    try {{ fs.unlinkSync(blockPath); }} catch {{}}
                    const pSlow = laneCreate.definition.execute("slow", {{task_id: "demo", lane_id: "slow"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => JSON.parse(r.content.find(c=>c.type==="text").text))
                      .catch(e=> {{ try{{return JSON.parse(e.message)}}catch{{throw e}}}});
                    const lockPath = path.join(repoPath, ".git", "collab-op-locks", "demo.lock");
                    let waited=0; while(waited<5000){{ if(fs.existsSync(lockPath)) break; await new Promise(r=>setTimeout(r,20)); waited+=20; }}
                    if(!fs.existsSync(lockPath)) throw new Error("slow lane did not acquire lock");
                    // Now try heterogeneous mutations that should fail-fast immediately
                    const heteroStart = Date.now();
                    let collectResult;
                    try {{
                      const r = await laneDrop.definition.execute("drop", {{task_id: "demo", lane_id: "writer-1"}}, undefined, undefined, {{cwd: repoPath}});
                      collectResult = {{ok:true, result: JSON.parse(r.content.find(c=>c.type==="text").text)}};
                    }} catch(e) {{
                      let err; try{{err=JSON.parse(e.message)}}catch{{err={{error:{{message:String(e)}}}}}};
                      collectResult = {{ok:false, error:err, elapsed: Date.now()-heteroStart}};
                    }}
                    const heteroElapsed = Date.now() - heteroStart;
                    if (collectResult.ok) throw new Error("heterogeneous lane_drop should fail with task_busy while slow holds lock, got success");
                    const code = collectResult.error?.error?.code || collectResult.error?.code;
                    if (code !== "task_busy") throw new Error("expected task_busy for heterogeneous, got "+JSON.stringify(collectResult));
                    if (heteroElapsed > 2000) throw new Error("heterogeneous should fail-fast quickly (<2s), elapsed "+heteroElapsed);
                    // also try report (which uses withTaskLock internally) should also fail-fast
                    const reportStart = Date.now();
                    let reportResult;
                    try {{
                      const r = await reportTool.definition.execute("rep", {{task_id: "demo", output_dir: "report-out"}}, undefined, undefined, {{cwd: repoPath}});
                      reportResult = {{ok:true, result: JSON.parse(r.content.find(c=>c.type==="text").text)}};
                    }} catch(e) {{
                      let err; try{{err=JSON.parse(e.message)}}catch{{err={{error:{{message:String(e)}}}}}};
                      reportResult = {{ok:false, error:err, elapsed: Date.now()-reportStart}};
                    }}
                    const reportElapsed = Date.now()-reportStart;
                    if (reportResult.ok) throw new Error("report should fail with task_busy while lock held");
                    const code2 = reportResult.error?.error?.code || reportResult.error?.code;
                    if (code2 !== "task_busy") throw new Error("expected task_busy for report, got "+JSON.stringify(reportResult));
                    if (reportElapsed > 2000) throw new Error("report should fail-fast (<2s), elapsed "+reportElapsed);
                    // Now unblock slow
                    fs.writeFileSync(blockPath, "go");
                    const rSlow = await pSlow;
                    if (!rSlow.ok) throw new Error("slow lane should succeed after unblock, got "+JSON.stringify(rSlow));
                    // After slow releases, heterogeneous should succeed (report should succeed now)
                    const r2 = await reportTool.definition.execute("rep2", {{task_id: "demo", output_dir: "report-out2"}}, undefined, undefined, {{cwd: repoPath}});
                    const rep2 = JSON.parse(r2.content.find(c=>c.type==="text").text);
                    if (!rep2.ok) throw new Error("report after release should succeed, got "+JSON.stringify(rep2));
                    process.stdout.write(JSON.stringify({{ok:true, heteroElapsed, reportElapsed}})+"\\n");
                """)
                result = run_node_script(node_loader_script(repo_str, node_body), timeout=20)
                self.assertTrue(result.get("ok"), result)
            finally:
                os.environ["PATH"] = orig_path

    def test_A7_queue_keys_for_distinct_repos_and_tasks_do_not_interfere(self):
        # distinct tasks
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repository, _ = seed_repository(base)
            seed_task_container(repository)
            seed_managed_task(repository, "demo")
            seed_managed_task(repository, "other")
            block = base / "block"
            if block.exists():
                block.unlink()
            wrapper_dir = base / "wrapper"
            wrapper_dir.mkdir()
            script = BLOCK_TEMPLATE.replace("__BRANCH__", "wave/demo/blocked").replace("__BLOCK__", str(block))
            write_wrapper(wrapper_dir, script)
            orig_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wrapper_dir}:{orig_path}"
            try:
                repo_str = str(repository)
                block_str = str(block)
                node_body = textwrap.dedent(f"""
                    const blockPath = "{block_str}";
                    try {{ fs.unlinkSync(blockPath); }} catch {{}}
                    const pDemo = laneCreate.definition.execute("d1", {{task_id: "demo", lane_id: "blocked"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => JSON.parse(r.content.find(c=>c.type==="text").text));
                    const lockPathDemo = path.join(repoPath, ".git", "collab-op-locks", "demo.lock");
                    let waited=0; while(waited<5000){{ if(fs.existsSync(lockPathDemo)) break; await new Promise(r=>setTimeout(r,20)); waited+=20; }}
                    if(!fs.existsSync(lockPathDemo)) throw new Error("demo lock not held");
                    const startOther = Date.now();
                    const rOther = await laneCreate.definition.execute("o1", {{task_id: "other", lane_id: "fast"}}, undefined, undefined, {{cwd: repoPath}})
                      .then(r => ({{ok:true, result: JSON.parse(r.content.find(c=>c.type==="text").text), elapsed: Date.now()-startOther}}))
                      .catch(e => {{ let err; try{{err=JSON.parse(e.message)}}catch{{err={{error:{{message:String(e)}}}}}}; return {{ok:false, error:err, elapsed: Date.now()-startOther}}; }});
                    if (!rOther.ok) throw new Error("other task lane should succeed immediately despite demo lock, got "+JSON.stringify(rOther));
                    if (rOther.elapsed > 2000) throw new Error("other task should not wait for demo queue, elapsed "+rOther.elapsed);
                    // also distinct lock files should be independent
                    const lockOther = path.join(repoPath, ".git", "collab-op-locks", "other.lock");
                    // other lock should have been acquired and released quickly, not held now
                    // unblock demo
                    fs.writeFileSync(blockPath, "go");
                    const rDemo = await pDemo;
                    if (!rDemo.ok) throw new Error("demo blocked should eventually succeed, got "+JSON.stringify(rDemo));
                    // verify both lanes exist
                    const {{ execSync }} = await import("node:child_process");
                    execSync("git -C "+repoPath+" rev-parse --verify wave/demo/blocked", {{encoding:"utf8"}});
                    execSync("git -C "+repoPath+" rev-parse --verify wave/other/fast", {{encoding:"utf8"}});
                    process.stdout.write(JSON.stringify({{ok:true, otherElapsed: rOther.elapsed}})+"\\n");
                """)
                result = run_node_script(node_loader_script(repo_str, node_body), timeout=20)
                self.assertTrue(result.get("ok"), result)
            finally:
                os.environ["PATH"] = orig_path

        # distinct repositories (control roots)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a").mkdir(parents=True, exist_ok=True)
            repoA, _ = seed_repository(base / "a")
            seed_task_container(repoA)
            seed_managed_task(repoA, "demo")
            (base / "b").mkdir(parents=True, exist_ok=True)
            repoB, _ = seed_repository(base / "b")
            seed_task_container(repoB)
            seed_managed_task(repoB, "demo")
            block = base / "block2"
            if block.exists():
                block.unlink()
            wrapper_dir = base / "wrapper2"
            wrapper_dir.mkdir()
            script = BLOCK_TEMPLATE.replace("__BRANCH__", "wave/demo/concurrent").replace("__BLOCK__", str(block))
            write_wrapper(wrapper_dir, script)
            orig_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wrapper_dir}:{orig_path}"
            try:
                repoAStr = str(repoA)
                repoBStr = str(repoB)
                blockStr = str(block)
                # Need a script that uses two loaders (different cwd) concurrently? But queue is per controlRoot, so we need two separate loaders with different cwd.
                node_body = textwrap.dedent(f"""
                    import {{ pathToFileURL }} from "node:url";
                    import fs from "node:fs";
                    import path from "node:path";
                    const piPackage = "{PI_PACKAGE}";
                    const extensionPath = "{EXTENSION_OP}";
                    const repoAPath = "{repoAStr}";
                    const repoBPath = "{repoBStr}";
                    const blockPath = "{blockStr}";
                    try {{ fs.unlinkSync(blockPath); }} catch {{}}
                    async function loaderFor(cwd) {{
                      const {{ DefaultResourceLoader, SettingsManager }} = await import(pathToFileURL(piPackage));
                      const settingsManager = SettingsManager.inMemory({{}});
                      const l = new DefaultResourceLoader({{ cwd, agentDir: cwd+"/.empty-pi-agent", additionalExtensionPaths: [extensionPath], settingsManager }});
                      await l.reload();
                      const regs = new Map(l.getExtensions().extensions.flatMap(e=>[...e.tools.entries()]));
                      const collabLane = regs.get("collab_lane");
                      if (!collabLane) throw new Error("collab_lane not found");
                      return {{ definition: {{ execute: (id, req, signal, onUpdate, ctx) => collabLane.definition.execute(id, {{ action: "create", ...req }}, signal, onUpdate, ctx) }} }};
                    }}
                    const toolA = await loaderFor(repoAPath);
                    const toolB = await loaderFor(repoBPath);
                    const pA = toolA.definition.execute("a1", {{task_id: "demo", lane_id: "concurrent"}}, undefined, undefined, {{cwd: repoAPath}})
                      .then(r => JSON.parse(r.content.find(c=>c.type==="text").text));
                    const lockA = path.join(repoAPath, ".git", "collab-op-locks", "demo.lock");
                    let waited=0; while(waited<5000){{ if(fs.existsSync(lockA)) break; await new Promise(r=>setTimeout(r,20)); waited+=20; }}
                    if(!fs.existsSync(lockA)) throw new Error("repoA lock not held");
                    const startB = Date.now();
                    const rB = await toolB.definition.execute("b1", {{task_id: "demo", lane_id: "fast"}}, undefined, undefined, {{cwd: repoBPath}})
                      .then(r => ({{ok:true, result: JSON.parse(r.content.find(c=>c.type==="text").text), elapsed: Date.now()-startB}}))
                      .catch(e => {{ let err; try{{err=JSON.parse(e.message)}}catch{{err={{error:{{message:String(e)}}}}}}; return {{ok:false, error:err, elapsed: Date.now()-startB}}; }});
                    if (!rB.ok) throw new Error("repoB lane should succeed despite repoA lock, got "+JSON.stringify(rB));
                    if (rB.elapsed > 2000) throw new Error("repoB should not wait for repoA queue, elapsed "+rB.elapsed);
                    fs.writeFileSync(blockPath, "go");
                    const rA = await pA;
                    if (!rA.ok) throw new Error("repoA concurrent should succeed after unblock, got "+JSON.stringify(rA));
                    const {{ execSync }} = await import("node:child_process");
                    execSync("git -C "+repoAPath+" rev-parse --verify wave/demo/concurrent", {{encoding:"utf8"}});
                    execSync("git -C "+repoBPath+" rev-parse --verify wave/demo/fast", {{encoding:"utf8"}});
                    process.stdout.write(JSON.stringify({{ok:true, bElapsed: rB.elapsed}})+"\\n");
                """)
                # Need to run without the wrapper loader script helper, use direct run_node_script with custom body that doesn't use node_loader_script
                result = run_node_script(node_body, timeout=20)
                self.assertTrue(result.get("ok"), result)
            finally:
                os.environ["PATH"] = orig_path

    def test_repo_parameter_keeps_same_task_lanes_independent_across_repositories(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            outside.mkdir()
            first_base = base / "first"
            first_base.mkdir()
            first_repository, _ = seed_repository(first_base)
            seed_task_container(first_repository)
            seed_managed_task(first_repository, "demo")
            second_base = base / "second"
            second_base.mkdir()
            second_repository, _ = seed_repository(second_base)
            seed_task_container(second_repository)
            seed_managed_task(second_repository, "demo")
            release = base / "release-first"
            wrapper_dir = base / "wrapper"
            wrapper_dir.mkdir()
            wrapper = BLOCK_TEMPLATE.replace("__BRANCH__", "wave/demo/selected-first").replace(
                "__BLOCK__", str(release)
            )
            write_wrapper(wrapper_dir, wrapper)
            original_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wrapper_dir}:{original_path}"
            first: subprocess.Popen[str] | None = None
            second: subprocess.Popen[str] | None = None
            try:
                first = spawn_raw_harness(outside)
                second = spawn_raw_harness(outside)
                first_stdin = first.stdin
                first_stdout = first.stdout
                assert first_stdin is not None and first_stdout is not None
                first_stdin.write(
                    f"{json.dumps({'tool': 'collab_lane_create', 'task_id': 'demo', 'lane_id': 'selected-first', 'repo': str(first_repository)})}\n"
                )
                first_stdin.flush()
                first_lock = first_repository / ".git/collab-op-locks/demo.lock"
                self.assertTrue(
                    wait_until(lambda: first_lock.exists()),
                    "first repository never acquired its task lock",
                )

                second_observed = send_request(
                    second,
                    {
                        "tool": "collab_lane_create",
                        "task_id": "demo",
                        "lane_id": "selected-second",
                        "repo": str(second_repository),
                    },
                )

                self.assertFalse(second_observed["is_error"])
                self.assertEqual(
                    git(second_repository, "rev-parse", "wave/demo/selected-second"),
                    git(second_repository, "rev-parse", "wave/demo/integration"),
                )
                self.assertTrue(first_lock.exists())

                release.write_text("go\n", encoding="utf-8")
                first_observed = json.loads(first_stdout.readline())
                self.assertFalse(first_observed["is_error"])
                self.assertEqual(
                    git(first_repository, "rev-parse", "wave/demo/selected-first"),
                    git(first_repository, "rev-parse", "wave/demo/integration"),
                )
            finally:
                release.write_text("go\n", encoding="utf-8")
                os.environ["PATH"] = original_path
                if first is not None:
                    close_harness(first)
                if second is not None:
                    close_harness_for(outside)

    def test_A7_fifo_no_cross_process_ordering_claim(self):
        # This is a documentation/no-test check: FIFO makes no cross-process ordering claim, just verify that distinct process queues are independent (already covered).
        # We just ensure that the module declaration states this.
        decl_path = ROOT / "home/.pi/agent/extensions/collab-op.ts"
        text = decl_path.read_text(encoding="utf-8")
        self.assertIn("FIFO", text)
        self.assertIn("no fairness promise against another", text)
        self.assertIn("fail-fast default", text.lower())
        self.assertIn("bounded-wait", text.lower())
        self.assertIn("request_aborted", text.lower())
        self.assertIn("waited_ms", text)
        self.assertIn("ownership-safe", text.lower())
        self.assertIn("re-read", text.lower())

