import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

function resolvePiSdkPath() {
  if (process.env.PI_CODING_AGENT_SDK_PATH) return path.resolve(process.env.PI_CODING_AGENT_SDK_PATH);
  const activePi = process.env.PI_BIN || execFileSync("which", ["pi"], { encoding: "utf8" }).trim();
  const cliPath = fs.realpathSync(activePi);
  return path.join(path.dirname(cliPath), "index.js");
}

const {
  createEventBus,
  DefaultResourceLoader,
  SettingsManager,
} = await import(pathToFileURL(resolvePiSdkPath()).href);

const ROOT = path.resolve(import.meta.dirname, "../../..");
const EXTENSION = path.join(ROOT, "home/.pi/agent/extensions/orchestrate-pi.ts");
const PROFILE_FIXTURE = path.join(import.meta.dirname, "fake-pi-subagents");
const SECOND_PROFILE_FIXTURE = path.join(import.meta.dirname, "fake-second-pi-subagents");
const RPC_REQUEST = "subagents:rpc:v1:request";
const RPC_REPLY = "subagents:rpc:v1:reply:";
const PROCESS_TERMINAL_EVENT = "subagent:process-terminal";
const DIGEST = "a".repeat(64);

function git(cwd, ...args) {
  return execFileSync("git", args, { cwd, encoding: "utf8" }).trim();
}

function makeRepo() {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), "orchestrate-pi-git-"));
  git(cwd, "init", "-q", "-b", "adapter");
  git(cwd, "config", "user.name", "Adapter Test");
  git(cwd, "config", "user.email", "adapter@example.invalid");
  fs.writeFileSync(path.join(cwd, "subject.txt"), "subject\n");
  git(cwd, "add", "subject.txt");
  git(cwd, "commit", "-q", "-m", "subject");
  return cwd;
}

function expectedFor(cwd) {
  return {
    cwd: fs.realpathSync(cwd),
    gitRoot: fs.realpathSync(git(cwd, "rev-parse", "--show-toplevel")),
    gitCommonDir: fs.realpathSync(path.resolve(cwd, git(cwd, "rev-parse", "--git-common-dir"))),
    branch: git(cwd, "symbolic-ref", "--short", "HEAD"),
    head: git(cwd, "rev-parse", "HEAD"),
    clean: true,
    primaryDirt: [],
  };
}

function dispatchRequest(cwd) {
  const expected = expectedFor(cwd);
  return {
    version: 1,
    action: "dispatch-lane",
    taskId: "v133-pi-runtime-adapter",
    laneId: "adapter",
    subjectSha: expected.head,
    expected,
    contract: {
      objective: "Implement the admitted adapter lane.",
      writeScope: ["home/.pi/agent/extensions/orchestrate-pi*"],
      immutablePaths: ["home/.pi/agent/settings.json"],
      focusedCommands: ["PYTHONPATH=tests python -m unittest -v test_orchestrate_pi_adapter"],
      evidence: ["focused red and green"],
      stopConditions: ["semantic contract change"],
    },
    timeoutMs: 1000,
  };
}

function pingData(overrides = {}) {
  return {
    version: 1,
    methods: ["ping", "status", "spawn", "steer", "stop"],
    capabilities: {
      status: true,
      asyncSpawn: true,
      steer: true,
      nonRecoveringSteer: true,
      stop: true,
      processTerminalProof: { version: 1, lifecycleArtifactVersion: 3 },
    },
    events: {
      request: RPC_REQUEST,
      replyPrefix: RPC_REPLY,
      processTerminal: PROCESS_TERMINAL_EVENT,
    },
    ...overrides,
  };
}

function successReply(bus, request, data, synchronous = false) {
  const emit = () => bus.emit(`${RPC_REPLY}${request.requestId}`, {
    version: 1,
    requestId: request.requestId,
    method: request.method,
    success: true,
    data,
  });
  if (synchronous) emit();
  else queueMicrotask(emit);
}

async function loadAdapter(cwd, configureRpc, profileOptions = {}) {
  const bus = createEventBus();
  const calls = [];
  const profileState = {
    mode: profileOptions.mode ?? "success",
    calls: [],
    imports: 0,
    rootLoads: 0,
    secondImports: 0,
    secondRootLoads: 0,
    secondCalls: 0,
    rejectStalledResolver: undefined,
    trace: [],
  };
  globalThis.__ORCHESTRATE_PI_PROFILE_STATE__ = profileState;
  let activeSubscriptions = 0;
  const subscriptionsByEvent = new Map();
  const originalOn = bus.on.bind(bus);
  bus.on = (event, handler) => {
    activeSubscriptions += 1;
    subscriptionsByEvent.set(event, (subscriptionsByEvent.get(event) ?? 0) + 1);
    const off = originalOn(event, handler);
    return () => {
      activeSubscriptions -= 1;
      subscriptionsByEvent.set(event, subscriptionsByEvent.get(event) - 1);
      off();
    };
  };
  if (configureRpc) {
    originalOn(RPC_REQUEST, (request) => {
      calls.push(request);
      profileState.trace.push(`rpc:${request.method}`);
      configureRpc({ bus, request, calls, successReply });
    });
  }
  const agentDir = fs.mkdtempSync(path.join(os.tmpdir(), "orchestrate-pi-agent-"));
  const packageRoots = [];
  for (let index = 0; index < (profileOptions.packageCount ?? 1); index += 1) {
    const packageRoot = path.join(agentDir, "fixture-packages", `pi-subagents-${index}`);
    fs.cpSync(PROFILE_FIXTURE, packageRoot, { recursive: true });
    const packageJsonPath = path.join(packageRoot, "package.json");
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
    packageJson.name = profileOptions.packageName ?? "pi-subagents";
    if (profileOptions.module === "malformed") {
      packageJson.exports["./preflight"] = "./malformed-preflight.mjs";
    }
    if (profileOptions.exportMode === "absent") {
      delete packageJson.exports["./preflight"];
    } else if (profileOptions.exportMode === "nested-fallback") {
      delete packageJson.exports;
    } else if (profileOptions.exportMode === "malformed") {
      packageJson.exports["./preflight"] = 42;
    } else if (profileOptions.exportMode === "escape") {
      const secondRoot = path.join(agentDir, "fixture-packages", `escape-target-${index}`);
      fs.cpSync(SECOND_PROFILE_FIXTURE, secondRoot, { recursive: true });
      fs.symlinkSync(path.join(secondRoot, "preflight.mjs"), path.join(packageRoot, "escaped-preflight.mjs"));
      packageJson.exports["./preflight"] = "./escaped-preflight.mjs";
    }
    fs.writeFileSync(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`);
    if (profileOptions.exportMode === "nested-fallback") {
      fs.cpSync(SECOND_PROFILE_FIXTURE, path.join(packageRoot, "node_modules", "pi-subagents"), { recursive: true });
    }
    packageRoots.push(packageRoot);
  }
  fs.writeFileSync(path.join(agentDir, "settings.json"), `${JSON.stringify({ packages: packageRoots }, null, 2)}\n`);
  process.env.PI_CODING_AGENT_DIR = agentDir;
  const settingsManager = SettingsManager.create(cwd, agentDir, { projectTrusted: true });
  const loader = new DefaultResourceLoader({
    cwd,
    agentDir,
    settingsManager,
    eventBus: bus,
    additionalExtensionPaths: [EXTENSION],
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
  });
  await loader.reload();
  const loaded = loader.getExtensions();
  assert.deepEqual(loaded.errors, []);
  const registered = loaded.extensions.flatMap((extension) => [...extension.tools.entries()]);
  const adapterEntries = registered.filter(([name]) => name === "orchestrate_pi");
  assert.equal(adapterEntries.length, 1, "orchestrate_pi must be registered exactly once");
  const tool = adapterEntries[0][1].definition;
  const execute = (request, signal = new AbortController().signal) => {
    process.env.PI_CODING_AGENT_DIR = agentDir;
    globalThis.__ORCHESTRATE_PI_PROFILE_STATE__ = profileState;
    return tool.execute(
      "adapter-test-call",
      request,
      signal,
      undefined,
      {
        cwd,
        isProjectTrusted: () => profileOptions.projectTrusted ?? true,
        sessionManager: {
          getSessionId: () => typeof profileOptions.sessionId === "function"
            ? profileOptions.sessionId()
            : profileOptions.sessionId ?? "host-session",
        },
      },
    );
  };
  return {
    agentDir,
    bus,
    calls,
    execute,
    loaded,
    profileState,
    tool,
    activeSubscriptions: () => activeSubscriptions,
    activeSubscriptionsFor: (event) => subscriptionsByEvent.get(event) ?? 0,
  };
}

function resultDetails(result) {
  assert.equal(typeof result, "object");
  assert.equal(typeof result.details, "object");
  return result.details;
}

function receiptFor(cwd, runId) {
  const expected = expectedFor(cwd);
  const asyncDir = path.join(cwd, ".runtime", runId);
  fs.mkdirSync(asyncDir, { recursive: true });
  return {
    version: 1,
    requestId: "00000000-0000-4000-8000-000000000001",
    runId,
    asyncDir,
    statusPath: path.join(asyncDir, "status.json"),
    processTerminalPath: path.join(asyncDir, "process-terminal.json"),
    expected: {
      cwd: expected.cwd,
      gitRoot: expected.gitRoot,
      gitCommonDir: expected.gitCommonDir,
      branch: expected.branch,
      initialHead: expected.head,
    },
    runtime: {
      rpcVersion: 1,
      processTerminalVersion: 1,
      lifecycleArtifactVersion: 3,
      launchContractDigest: DIGEST,
      hostSessionId: "host-session",
    },
  };
}

function observedProof(runId) {
  const fixturePath = path.join(import.meta.dirname, "process-terminal-observed.json");
  return JSON.parse(fs.readFileSync(fixturePath, "utf8").replaceAll("RUN_ID", runId));
}

function exactStatus(receipt, state, extra = {}) {
  return {
    lifecycleArtifactVersion: 3,
    runId: receipt.runId,
    cwd: receipt.expected.cwd,
    launchContractDigest: receipt.runtime.launchContractDigest,
    state,
    ...extra,
  };
}

async function scenarioLoad() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd);
  const tools = adapter.loaded.extensions.flatMap((extension) => [...extension.tools.keys()]);
  assert.deepEqual(tools, ["orchestrate_pi"]);
  assert.equal(adapter.calls.length, 0);
}

async function scenarioStrict() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd);
  for (const request of [
    { version: 2, action: "dispatch-lane" },
    { version: 1, action: "raw-dispatch" },
    { ...dispatchRequest(cwd), model: "forbidden" },
    { version: 1, action: "attest-run", receipt: receiptFor(cwd, "cross-action"), taskId: "forbidden" },
  ]) {
    const result = await adapter.execute(request);
    assert.equal(result.isError, true);
    assert.equal(resultDetails(result).version, 1);
    assert.equal(typeof resultDetails(result).error.code, "string");
  }
  assert.equal(adapter.calls.length, 0);
}

async function scenarioGitMismatch() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd);
  const request = dispatchRequest(cwd);
  request.expected.head = "0".repeat(40);
  request.subjectSha = request.expected.head;
  const result = await adapter.execute(request);
  assert.equal(result.isError, true);
  assert.equal(resultDetails(result).error.code, "git_identity_mismatch");
  assert.equal(adapter.calls.length, 0);
}

async function scenarioCapability() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") {
      successReply(bus, request, pingData({ capabilities: { asyncSpawn: false } }));
    } else {
      assert.fail(`unexpected RPC method ${request.method}`);
    }
  });
  const result = await adapter.execute(dispatchRequest(cwd));
  assert.equal(result.isError, true);
  assert.equal(resultDetails(result).error.code, "rpc_capability_mismatch");
  assert.deepEqual(adapter.calls.map((call) => call.method), ["ping"]);
  assert.equal(adapter.profileState.imports, 0);
  assert.deepEqual(adapter.profileState.calls, []);
  assert.deepEqual(adapter.profileState.trace, ["rpc:ping"]);
}

async function scenarioProfileSuccess() {
  const cwd = makeRepo();
  const runId = "profile-success-run";
  const asyncDir = path.join(cwd, ".runtime", runId);
  fs.mkdirSync(asyncDir, { recursive: true });
  let spawnedTask;
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else if (request.method === "spawn") {
      spawnedTask = request.params.task;
      successReply(bus, request, {
        details: { mode: "single", runId, asyncId: runId, asyncDir, launchContractDigest: DIGEST },
      });
    } else assert.fail(`unexpected RPC method ${request.method}`);
  });
  const request = dispatchRequest(cwd);
  const result = await adapter.execute(request);
  assert.notEqual(result.isError, true);
  assert.equal(resultDetails(result).runId, runId);
  assert.equal(adapter.profileState.imports, 1);
  assert.equal(adapter.profileState.rootLoads, 0, "package root/index must never be loaded");
  assert.equal(adapter.profileState.calls.length, 1);
  const preflight = adapter.profileState.calls[0];
  assert.deepEqual(Object.keys(preflight).sort(), ["agent", "artifacts", "context", "cwd", "task"]);
  assert.equal(preflight.agent, "lane-worker");
  assert.equal(preflight.cwd, fs.realpathSync(cwd));
  assert.equal(preflight.context, "fresh");
  assert.equal(preflight.task, spawnedTask, "public preflight and spawn must receive the exact same derived task");
  assert.equal(preflight.artifacts, false);
  assert.deepEqual(adapter.profileState.trace, ["rpc:ping", "profile", "rpc:spawn"]);
  assert.deepEqual(adapter.calls.map((call) => call.method), ["ping", "spawn"]);
  assert.match(adapter.agentDir, /orchestrate-pi-agent-/);
}

async function scenarioUntrustedProject() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else assert.fail(`untrusted project must not emit ${request.method}`);
  }, { projectTrusted: false });
  const result = await adapter.execute(dispatchRequest(cwd));
  assert.equal(result.isError, true);
  assert.equal(resultDetails(result).error.code, "profile_capability_mismatch");
  assert.deepEqual(adapter.calls.map((call) => call.method), ["ping"]);
  assert.deepEqual(adapter.profileState.trace, ["rpc:ping"]);
  assert.equal(adapter.profileState.imports, 0, "untrusted context must not import project package code");
  assert.deepEqual(adapter.profileState.calls, []);
  assert.equal(adapter.profileState.rootLoads, 0);
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioProfileFailures() {
  const cases = [
    ["missing-package", { packageCount: 0 }],
    ["wrong-package-name", { packageName: "not-pi-subagents" }],
    ["duplicate-package-roots", { packageCount: 2 }],
    ["missing-contract-version", { mode: "missing-contract-version" }],
    ["wrong-contract-version", { mode: "wrong-contract-version" }],
    ["future-contract-version", { mode: "future-contract-version" }],
    ["missing-agent", { mode: "missing-agent" }],
    ["ambiguous-agent", { mode: "ambiguous-agent" }],
    ["shadowed-agent", { mode: "shadowed-agent" }],
    ["missing-tdd", { mode: "missing-tdd" }],
    ["duplicate-requested-tdd", { mode: "duplicate-requested-tdd" }],
    ["duplicate-resolved-tdd", { mode: "duplicate-resolved-tdd" }],
    ["unresolved-tdd", { mode: "unresolved-tdd" }],
    ["error-diagnostic", { mode: "error-diagnostic" }],
    ["malformed-module", { module: "malformed" }],
    ["malformed-result", { mode: "malformed-result" }],
    ["preflight-throw", { mode: "throw" }],
  ];
  for (const [label, options] of cases) {
    const cwd = makeRepo();
    const adapter = await loadAdapter(cwd, ({ bus, request }) => {
      if (request.method === "ping") {
        successReply(bus, request, pingData());
      } else {
        bus.emit(`${RPC_REPLY}${request.requestId}`, {
          version: 1,
          requestId: request.requestId,
          method: request.method,
          success: false,
          error: { code: `${label}-unexpected-${request.method}` },
        });
      }
    }, options);
    const result = await adapter.execute(dispatchRequest(cwd));
    assert.equal(result.isError, true, label);
    assert.equal(resultDetails(result).error.code, "profile_capability_mismatch", label);
    assert.deepEqual(adapter.calls.map((call) => call.method), ["ping"], label);
    assert.equal(adapter.profileState.rootLoads, 0, `${label}: package root/index must never load`);
    assert.equal(adapter.activeSubscriptions(), 0, label);
  }
}

async function scenarioProfilePackageScope() {
  const cases = [
    ["nested-fallback", { exportMode: "nested-fallback" }],
    ["escaped-resolution", { exportMode: "escape" }],
    ["absent-export", { exportMode: "absent" }],
    ["malformed-export", { exportMode: "malformed" }],
  ];
  for (const [label, options] of cases) {
    const cwd = makeRepo();
    const adapter = await loadAdapter(cwd, ({ bus, request }) => {
      if (request.method === "ping") {
        successReply(bus, request, pingData());
      } else {
        bus.emit(`${RPC_REPLY}${request.requestId}`, {
          version: 1,
          requestId: request.requestId,
          method: request.method,
          success: false,
          error: { code: `${label}-unexpected-${request.method}` },
        });
      }
    }, options);
    const result = await adapter.execute(dispatchRequest(cwd));
    assert.equal(result.isError, true, label);
    assert.equal(resultDetails(result).error.code, "profile_capability_mismatch", label);
    assert.deepEqual(adapter.calls.map((call) => call.method), ["ping"], label);
    assert.equal(adapter.profileState.imports, 0, `${label}: selected preflight must not import`);
    assert.equal(adapter.profileState.rootLoads, 0, `${label}: selected root/index must not execute`);
    assert.equal(adapter.profileState.secondImports, 0, `${label}: second preflight must not import`);
    assert.equal(adapter.profileState.secondCalls, 0, `${label}: second resolver must not execute`);
    assert.equal(adapter.profileState.secondRootLoads, 0, `${label}: second root/index must not execute`);
    assert.equal(adapter.activeSubscriptions(), 0, label);
  }
}

async function scenarioProfileCancellation() {
  const nativeSetTimeout = globalThis.setTimeout;

  const abortCwd = makeRepo();
  const abortAdapter = await loadAdapter(abortCwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else assert.fail(`aborted profile preflight must not emit ${request.method}`);
  }, { mode: "never-settles" });
  const controller = new AbortController();
  const aborting = abortAdapter.execute(dispatchRequest(abortCwd), controller.signal);
  const resolverDeadline = Date.now() + 500;
  while (abortAdapter.profileState.calls.length === 0 && Date.now() < resolverDeadline) {
    await new Promise((resolve) => nativeSetTimeout(resolve, 5));
  }
  assert.equal(abortAdapter.profileState.calls.length, 1, "stalled resolver was not invoked");
  const abortedAt = Date.now();
  controller.abort();
  const aborted = await Promise.race([
    aborting,
    new Promise((_, reject) => nativeSetTimeout(
      () => reject(new Error("profile resolver abort did not settle promptly")),
      500,
    )),
  ]);
  assert.equal(aborted.isError, true);
  assert.equal(resultDetails(aborted).error.code, "aborted");
  assert.ok(Date.now() - abortedAt < 500, "profile resolver abort did not return promptly");
  assert.deepEqual(abortAdapter.calls.map((call) => call.method), ["ping"]);
  assert.equal(abortAdapter.activeSubscriptions(), 0);
  abortAdapter.profileState.rejectStalledResolver(new Error("late resolver rejection after abort"));
  await Promise.resolve();

  const deadlineCwd = makeRepo();
  const deadlineAdapter = await loadAdapter(deadlineCwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else assert.fail(`timed profile preflight must not emit ${request.method}`);
  }, { mode: "never-settles" });
  let exactTimeouts = 0;
  let profileDeadlineInstrumented = false;
  globalThis.setTimeout = (handler, delay, ...args) => {
    if (delay === 10_000) {
      exactTimeouts += 1;
      if (exactTimeouts === 2) {
        profileDeadlineInstrumented = true;
        return nativeSetTimeout(handler, 25, ...args);
      }
    }
    return nativeSetTimeout(handler, delay, ...args);
  };
  let timed;
  try {
    timed = await Promise.race([
      deadlineAdapter.execute(dispatchRequest(deadlineCwd)),
      new Promise((_, reject) => nativeSetTimeout(
        () => reject(new Error("profile resolver deadline was not installed")),
        500,
      )),
    ]);
  } finally {
    globalThis.setTimeout = nativeSetTimeout;
  }
  assert.equal(profileDeadlineInstrumented, true, "second exact timeout after ping must bound profile preflight");
  assert.equal(timed.isError, true);
  assert.equal(resultDetails(timed).error.code, "profile_capability_mismatch");
  assert.deepEqual(deadlineAdapter.calls.map((call) => call.method), ["ping"]);
  assert.equal(deadlineAdapter.profileState.calls.length, 1);
  assert.equal(deadlineAdapter.activeSubscriptions(), 0);
  deadlineAdapter.profileState.rejectStalledResolver(new Error("late resolver rejection after deadline"));
  await Promise.resolve();
}

async function scenarioDispatch() {
  const cwd = makeRepo();
  const asyncDir = path.join(cwd, ".runtime", "run-1");
  fs.mkdirSync(asyncDir, { recursive: true });
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else if (request.method === "spawn") {
      assert.deepEqual(Object.keys(request.params).sort(), ["agent", "async", "clarify", "context", "cwd", "task", "timeoutMs"]);
      assert.equal(request.params.agent, "lane-worker");
      assert.equal(request.params.context, "fresh");
      assert.equal(request.params.async, true);
      assert.equal(request.params.clarify, false);
      assert.equal(request.params.cwd, fs.realpathSync(cwd));
      assert.match(request.params.task, /v133-pi-runtime-adapter/);
      successReply(bus, request, {
        text: "human text must not be parsed",
        details: { mode: "single", runId: "run-1", asyncId: "run-1", asyncDir, launchContractDigest: DIGEST },
      });
    } else assert.fail(`unexpected RPC method ${request.method}`);
  });
  const request = dispatchRequest(cwd);
  const result = await adapter.execute(request);
  assert.notEqual(result.isError, true);
  const receipt = resultDetails(result);
  assert.deepEqual(receipt, {
    version: 1,
    requestId: receipt.requestId,
    runId: "run-1",
    asyncDir,
    statusPath: path.join(asyncDir, "status.json"),
    processTerminalPath: path.join(asyncDir, "process-terminal.json"),
    expected: {
      cwd: request.expected.cwd,
      gitRoot: request.expected.gitRoot,
      gitCommonDir: request.expected.gitCommonDir,
      branch: request.expected.branch,
      initialHead: request.expected.head,
    },
    runtime: {
      rpcVersion: 1,
      processTerminalVersion: 1,
      lifecycleArtifactVersion: 3,
      launchContractDigest: DIGEST,
      hostSessionId: "host-session",
    },
  });
  assert.match(receipt.requestId, /^[0-9a-f-]{36}$/);
  assert.deepEqual(adapter.calls.map((call) => call.method), ["ping", "spawn"]);
}

async function scenarioDispatchProcessSubscription() {
  const cwd = makeRepo();
  let spawnIndex = 0;
  let adapter;
  adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") {
      successReply(bus, request, pingData(), true);
      return;
    }
    if (request.method === "spawn") {
      assert.equal(
        adapter.activeSubscriptionsFor(PROCESS_TERMINAL_EVENT),
        1,
        "process-terminal listener must be active before synchronous spawn handling",
      );
      const runId = `process-subscription-${spawnIndex++}`;
      const asyncDir = path.join(cwd, ".runtime", runId);
      fs.mkdirSync(asyncDir, { recursive: true });
      bus.emit(PROCESS_TERMINAL_EVENT, observedProof(runId));
      if (spawnIndex === 1) {
        bus.emit(`${RPC_REPLY}${request.requestId}`, {
          version: 1,
          requestId: request.requestId,
          method: request.method,
          success: false,
          error: { code: "spawn-refused" },
        });
      } else {
        successReply(bus, request, {
          details: { mode: "single", runId, asyncId: runId, asyncDir },
        }, true);
      }
      return;
    }
    if (request.method === "stop") {
      successReply(bus, request, { runId: request.params.runId, state: "stopping" }, true);
      return;
    }
    assert.fail(`unexpected RPC method ${request.method}`);
  });

  const dispatchFailure = await adapter.execute(dispatchRequest(cwd));
  assert.equal(dispatchFailure.isError, true);
  assert.equal(resultDetails(dispatchFailure).error.code, "rpc_failure");
  assert.equal(adapter.activeSubscriptionsFor(PROCESS_TERMINAL_EVENT), 0);

  const receiptFailure = await adapter.execute(dispatchRequest(cwd));
  assert.equal(receiptFailure.isError, true);
  assert.equal(resultDetails(receiptFailure).error.code, "orphan_risk");
  assert.equal(resultDetails(receiptFailure).error.stopAttempted, true);
  assert.equal(adapter.activeSubscriptionsFor(PROCESS_TERMINAL_EVENT), 0);
  assert.equal(adapter.activeSubscriptions(), 0);

  const wrongChannel = await loadAdapter(cwd, ({ bus, request }) => {
    assert.equal(request.method, "ping");
    successReply(bus, request, pingData({
      events: {
        request: RPC_REQUEST,
        replyPrefix: RPC_REPLY,
        processTerminal: "subagent:undocumented-terminal",
      },
    }), true);
  });
  const incompatible = await wrongChannel.execute(dispatchRequest(cwd));
  assert.equal(incompatible.isError, true);
  assert.equal(resultDetails(incompatible).error.code, "rpc_capability_mismatch");
  assert.equal(wrongChannel.activeSubscriptionsFor(PROCESS_TERMINAL_EVENT), 0);
}

async function scenarioDispatchEarlyWake() {
  const cwd = makeRepo();
  const plans = [
    {
      runId: "early-matching-run",
      eventRunIds: ["different-run", "early-matching-run"],
    },
    {
      runId: "early-mismatched-run",
      eventRunIds: ["not-early-mismatched-run"],
    },
    {
      runId: "early-evicted-run",
      eventRunIds: ["early-evicted-run", ...Array.from({ length: 256 }, (_, index) => `noise-${index}`)],
    },
  ];
  let spawnIndex = 0;
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") {
      successReply(bus, request, pingData(), true);
      return;
    }
    if (request.method === "spawn") {
      const plan = plans[spawnIndex++];
      const asyncDir = path.join(cwd, ".runtime", plan.runId);
      fs.mkdirSync(asyncDir, { recursive: true });
      for (const runId of plan.eventRunIds) bus.emit(PROCESS_TERMINAL_EVENT, { runId });
      successReply(bus, request, {
        details: {
          mode: "single",
          runId: plan.runId,
          asyncId: plan.runId,
          asyncDir,
          launchContractDigest: DIGEST,
        },
      }, true);
      return;
    }
    assert.fail(`unexpected RPC method ${request.method}`);
  });

  const matchingReceipt = resultDetails(await adapter.execute(dispatchRequest(cwd)));
  assert.equal(adapter.activeSubscriptions(), 0);

  const nativeSetTimeout = globalThis.setTimeout;
  const waitTimers = [];
  globalThis.setTimeout = (handler, delay, ...args) => {
    if (delay >= 431 && delay <= 434) {
      waitTimers.push(delay);
      return nativeSetTimeout(handler, 0, ...args);
    }
    return nativeSetTimeout(handler, delay, ...args);
  };
  try {
    const matchingResult = resultDetails(await adapter.execute({
      version: 1,
      action: "attest-run",
      receipt: matchingReceipt,
      waitMs: 431,
    }));
    assert.deepEqual(matchingResult, {
      version: 1,
      runId: matchingReceipt.runId,
      execution: "unknown",
      processTerminal: "unknown",
      canonicalSessionLease: "unknown",
      evidenceSource: "event",
      reason: "process-terminal-proof-unavailable",
    });
    assert.deepEqual(waitTimers, [], "matching early event must bypass timer installation");

    const consumedResult = resultDetails(await adapter.execute({
      version: 1,
      action: "attest-run",
      receipt: matchingReceipt,
      waitMs: 432,
    }));
    assert.equal(consumedResult.evidenceSource, "none", "early wake marker must be one shot");
    assert.deepEqual(waitTimers, [432]);

    const mismatchedReceipt = resultDetails(await adapter.execute(dispatchRequest(cwd)));
    const mismatchedResult = resultDetails(await adapter.execute({
      version: 1,
      action: "attest-run",
      receipt: mismatchedReceipt,
      waitMs: 433,
    }));
    assert.equal(mismatchedResult.processTerminal, "unknown");
    assert.equal(mismatchedResult.canonicalSessionLease, "unknown");
    assert.equal(mismatchedResult.evidenceSource, "none", "mismatched event must not wake exact run");
    assert.deepEqual(waitTimers, [432, 433]);

    const evictedReceipt = resultDetails(await adapter.execute(dispatchRequest(cwd)));
    const evictedResult = resultDetails(await adapter.execute({
      version: 1,
      action: "attest-run",
      receipt: evictedReceipt,
      waitMs: 434,
    }));
    assert.equal(evictedResult.processTerminal, "unknown");
    assert.equal(evictedResult.canonicalSessionLease, "unknown");
    assert.equal(evictedResult.evidenceSource, "none", "bounded noise must evict rather than retain an unbounded exact marker");
    assert.deepEqual(waitTimers, [432, 433, 434]);
  } finally {
    globalThis.setTimeout = nativeSetTimeout;
  }
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioRpcCorrelation() {
  const cwd = makeRepo();
  const pendingSpawns = [];
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") {
      bus.emit(`${RPC_REPLY}${request.requestId}`, { version: 1, requestId: "wrong-id", method: "ping", success: true, data: pingData() });
      successReply(bus, request, pingData(), true);
    } else if (request.method === "spawn") {
      pendingSpawns.push(request);
      if (pendingSpawns.length === 2) {
        for (const spawn of [...pendingSpawns].reverse()) {
          const runId = spawn.params.task.includes('"laneId":"adapter-b"') ? "run-b" : "run-a";
          const asyncDir = path.join(cwd, ".runtime", runId);
          fs.mkdirSync(asyncDir, { recursive: true });
          successReply(bus, spawn, { details: { mode: "single", runId, asyncId: runId, asyncDir, launchContractDigest: DIGEST } }, true);
        }
      }
    }
  });
  const first = dispatchRequest(cwd);
  first.laneId = "adapter-a";
  const second = dispatchRequest(cwd);
  second.laneId = "adapter-b";
  const [a, b] = await Promise.all([adapter.execute(first), adapter.execute(second)]);
  assert.equal(resultDetails(a).runId, "run-a");
  assert.equal(resultDetails(b).runId, "run-b");
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioRpcCancel() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd, () => {});
  const nativeSetTimeout = globalThis.setTimeout;

  const observedDeadlines = [];
  globalThis.setTimeout = (handler, delay, ...args) => {
    observedDeadlines.push(delay);
    return nativeSetTimeout(handler, delay, ...args);
  };
  const controller = new AbortController();
  const longRun = dispatchRequest(cwd);
  longRun.timeoutMs = 7_200_000;
  let completed = false;
  const aborting = adapter.execute(longRun, controller.signal).then((result) => {
    completed = true;
    return result;
  });
  while (adapter.calls.length === 0 && !completed) await new Promise((resolve) => nativeSetTimeout(resolve, 5));
  if (adapter.calls.length > 0) controller.abort();
  const abortedResult = await aborting;
  globalThis.setTimeout = nativeSetTimeout;
  assert.equal(resultDetails(abortedResult).error.code, "aborted");
  assert.equal(observedDeadlines.includes(7_200_000), false, "run timeout must not become the RPC reply deadline");
  assert.equal(observedDeadlines.some((delay) => delay > 0 && delay <= 120_000), true);
  assert.equal(adapter.activeSubscriptions(), 0);

  globalThis.setTimeout = (handler, delay, ...args) => nativeSetTimeout(handler, delay === 10_000 ? 25 : delay, ...args);
  const timed = dispatchRequest(cwd);
  delete timed.timeoutMs;
  const timedResult = await adapter.execute(timed);
  globalThis.setTimeout = nativeSetTimeout;
  assert.equal(resultDetails(timedResult).error.code, "rpc_timeout");
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioGitPreflightCancel() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd, () => assert.fail("Git cancellation must emit no RPC"));
  const fakeBin = fs.mkdtempSync(path.join(os.tmpdir(), "orchestrate-pi-fake-git-"));
  const marker = path.join(fakeBin, "started");
  const fakeGit = path.join(fakeBin, "git");
  fs.writeFileSync(fakeGit, `#!/usr/bin/env node\nimport fs from "node:fs";\nfs.writeFileSync(process.env.ORCHESTRATE_FAKE_GIT_MARKER, "started\\n");\nAtomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 1500);\nprocess.exit(3);\n`);
  fs.chmodSync(fakeGit, 0o755);
  const request = dispatchRequest(cwd);
  const originalPath = process.env.PATH;
  process.env.PATH = `${fakeBin}${path.delimiter}${originalPath}`;
  process.env.ORCHESTRATE_FAKE_GIT_MARKER = marker;
  const controller = new AbortController();
  try {
    const dispatching = adapter.execute(request, controller.signal);
    const markerDeadline = Date.now() + 500;
    while (!fs.existsSync(marker) && Date.now() < markerDeadline) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    assert.equal(fs.existsSync(marker), true, "fake Git preflight did not start");
    const abortedAt = Date.now();
    controller.abort();
    const result = await dispatching;
    assert.equal(result.isError, true);
    assert.equal(resultDetails(result).error.code, "aborted");
    assert.ok(Date.now() - abortedAt < 500, "stalled Git preflight did not abort promptly");
  } finally {
    process.env.PATH = originalPath;
    delete process.env.ORCHESTRATE_FAKE_GIT_MARKER;
  }
  assert.equal(adapter.calls.length, 0);
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioOrphanRisk() {
  const cwd = makeRepo();
  const asyncDir = path.join(cwd, ".runtime", "orphan-run");
  fs.mkdirSync(asyncDir, { recursive: true });
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else if (request.method === "spawn") successReply(bus, request, {
      text: JSON.stringify({ runId: "forged-from-human-text", asyncDir, launchContractDigest: DIGEST }),
      details: { mode: "single", runId: "orphan-run", asyncId: "orphan-run", asyncDir },
    });
    else if (request.method === "stop") {
      assert.deepEqual(request.params, { runId: "orphan-run" });
      successReply(bus, request, { runId: "orphan-run", state: "stopping" });
    } else assert.fail(`unexpected RPC method ${request.method}`);
  });
  const result = await adapter.execute(dispatchRequest(cwd));
  const details = resultDetails(result);
  assert.equal(result.isError, true);
  assert.equal(details.error.code, "orphan_risk");
  assert.equal(details.error.runId, "orphan-run");
  assert.equal(details.error.stopAttempted, true);
  assert.equal(details.error.stopAcknowledged, true);
  assert.deepEqual(adapter.calls.map((call) => call.method), ["ping", "spawn", "stop"]);
}

async function scenarioDispatchRejectsUnattestableRunId() {
  const cwd = makeRepo();
  const runId = "nested\\run";
  const asyncDir = path.join(cwd, ".runtime", runId);
  fs.mkdirSync(asyncDir, { recursive: true });
  assert.equal(path.basename(asyncDir), runId, "fixture requires POSIX backslash component semantics");
  const stopped = [];
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else if (request.method === "spawn") successReply(bus, request, {
      details: { mode: "single", runId, asyncId: runId, asyncDir, launchContractDigest: DIGEST },
    });
    else if (request.method === "stop") {
      stopped.push(request.params.runId);
      successReply(bus, request, { runId: request.params.runId, state: "stopping" });
    } else assert.fail(`unexpected RPC method ${request.method}`);
  });

  const result = await adapter.execute(dispatchRequest(cwd));
  const details = resultDetails(result);
  assert.equal(result.isError, true);
  assert.equal(details.error.code, "orphan_risk");
  assert.equal(details.error.runId, runId);
  assert.equal(details.error.stopAttempted, true);
  assert.deepEqual(stopped, [runId], "dispatch must stop the exact possible run once");
  assert.equal(adapter.calls.filter((call) => call.method === "spawn").length, 1, "dispatch must not retry spawn");
  assert.deepEqual(adapter.calls.map((call) => call.method), ["ping", "spawn", "stop"]);
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioRunTimeout() {
  const cwd = makeRepo();
  let spawnIndex = 0;
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else if (request.method === "spawn") {
      const runId = `timeout-run-${spawnIndex++}`;
      const asyncDir = path.join(cwd, ".runtime", runId);
      fs.mkdirSync(asyncDir, { recursive: true });
      if (runId === "timeout-run-0") assert.equal(Object.hasOwn(request.params, "timeoutMs"), false);
      else assert.equal(request.params.timeoutMs, 7_200_000);
      successReply(bus, request, {
        details: { mode: "single", runId, asyncId: runId, asyncDir, launchContractDigest: DIGEST },
      });
    } else assert.fail(`unexpected RPC method ${request.method}`);
  });
  const omitted = dispatchRequest(cwd);
  delete omitted.timeoutMs;
  assert.equal((await adapter.execute(omitted)).isError, undefined);
  const bounded = dispatchRequest(cwd);
  bounded.timeoutMs = 7_200_000;
  assert.equal((await adapter.execute(bounded)).isError, undefined);
  assert.ok(adapter.tool.parameters.properties.timeoutMs.maximum >= 7_200_000);
}

async function scenarioTurnBudget() {
  const cwd = makeRepo();
  let spawnIndex = 0;
  let pingIndex = 0;
  const spawnParams = [];
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") {
      const data = pingData();
      if (pingIndex++ === 1) {
        data.methods = data.methods.filter((method) => method !== "steer");
        delete data.capabilities.steer;
        delete data.capabilities.nonRecoveringSteer;
      }
      successReply(bus, request, data);
    }
    else if (request.method === "spawn") {
      spawnParams.push(structuredClone(request.params));
      const runId = `turn-budget-${spawnIndex++}`;
      const asyncDir = path.join(cwd, ".runtime", runId);
      fs.mkdirSync(asyncDir, { recursive: true });
      successReply(bus, request, {
        details: { mode: "single", runId, asyncId: runId, asyncDir, launchContractDigest: DIGEST },
      });
    } else assert.fail(`unexpected RPC method ${request.method}`);
  });

  const omitted = dispatchRequest(cwd);
  delete omitted.turnBudget;
  assert.equal((await adapter.execute(omitted)).isError, undefined);

  const budgets = [
    { maxTurns: 1 },
    { maxTurns: 11, graceTurns: 0 },
    { maxTurns: 200, graceTurns: 7 },
  ];
  for (const [index, budget] of budgets.entries()) {
    const request = dispatchRequest(cwd);
    request.turnBudget = budget;
    const result = await adapter.execute(request);
    assert.equal(result.isError, undefined);
    assert.equal(
      adapter.calls.some((call) => call.method === "steer"),
      false,
      "dispatch must not attempt notice steering without an exact threshold event",
    );
    if (index === 0) {
      assert.deepEqual(
        adapter.calls.map((call) => call.method),
        ["ping", "spawn", "ping", "spawn"],
        "missing optional steer capability must still pass the explicit budget to spawn",
      );
      assert.equal(adapter.activeSubscriptions(), 0, "missing steer capability must not retain a turn observer");
    } else {
      adapter.bus.emit(PROCESS_TERMINAL_EVENT, { runId: resultDetails(result).runId });
      assert.equal(adapter.activeSubscriptions(), 0);
    }
  }

  assert.equal(Object.hasOwn(spawnParams[0], "turnBudget"), false, "omission must preserve upstream inheritance");
  assert.equal(Object.hasOwn(spawnParams[0], "control"), false, "omission must create no Adapter notice control");
  assert.deepEqual(spawnParams.slice(1).map((params) => params.turnBudget), [
    { maxTurns: 1, graceTurns: 1 },
    { maxTurns: 11, graceTurns: 0 },
    { maxTurns: 200, graceTurns: 7 },
  ]);
  assert.deepEqual(spawnParams.slice(1).map((params) => params.control), [
    { enabled: true, activeNoticeAfterTurns: 1, activeNoticeAfterMs: Number.MAX_SAFE_INTEGER, activeNoticeAfterTokens: Number.MAX_SAFE_INTEGER, notifyOn: ["active_long_running"], notifyChannels: ["event"] },
    { enabled: true, activeNoticeAfterTurns: 9, activeNoticeAfterMs: Number.MAX_SAFE_INTEGER, activeNoticeAfterTokens: Number.MAX_SAFE_INTEGER, notifyOn: ["active_long_running"], notifyChannels: ["event"] },
    { enabled: true, activeNoticeAfterTurns: 190, activeNoticeAfterMs: Number.MAX_SAFE_INTEGER, activeNoticeAfterTokens: Number.MAX_SAFE_INTEGER, notifyOn: ["active_long_running"], notifyChannels: ["event"] },
  ]);

  const invalidAdapter = await loadAdapter(cwd, () => assert.fail("invalid turn budget must fail before Git/RPC"));
  const unsafe = Number.MAX_SAFE_INTEGER + 1;
  const invalidBudgets = [
    null,
    false,
    "10",
    {},
    { maxTurns: 0 },
    { maxTurns: 1.5 },
    { maxTurns: unsafe },
    { maxTurns: 10, graceTurns: null },
    { maxTurns: 10, graceTurns: -1 },
    { maxTurns: 10, graceTurns: 1.5 },
    { maxTurns: Number.MAX_SAFE_INTEGER, graceTurns: 1 },
    { maxTurns: 10, surprise: true },
  ];
  for (const turnBudget of invalidBudgets) {
    const request = dispatchRequest(cwd);
    request.turnBudget = turnBudget;
    const result = await invalidAdapter.execute(request);
    assert.equal(result.isError, true, JSON.stringify(turnBudget));
    assert.equal(resultDetails(result).error.code, "invalid_request", JSON.stringify(turnBudget));
  }
  assert.deepEqual(invalidAdapter.calls, []);
  assert.equal(adapter.tool.parameters.properties.turnBudget.type, "object");
  assert.equal(adapter.tool.parameters.properties.turnBudget.additionalProperties, false);
}

function turnThresholdEvent(runId, asyncDir, turns, overrides = {}) {
  const base = {
    source: "async",
    asyncDir,
    event: {
      type: "active_long_running",
      to: "active_long_running",
      ts: Date.now(),
      agent: "lane-worker",
      index: 0,
      runId,
      message: "lane-worker is still active but long-running",
      reason: "turn_threshold",
      turns,
    },
  };
  return {
    ...base,
    ...overrides,
    event: { ...base.event, ...(overrides.event ?? {}) },
  };
}

async function waitUntil(predicate, label) {
  const deadline = Date.now() + 750;
  while (!predicate() && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(predicate(), true, label);
}

async function scenarioTurnHandoff() {
  const cwd = makeRepo();
  const runtimeRoot = fs.mkdtempSync(path.join(os.tmpdir(), "orchestrate-pi-turn-runtime-"));
  let hostSessionId = "host-session";
  const plans = [
    { runId: "pre-receipt-match", status: "exact", preEvents: "matching" },
    { runId: "forged-digest", status: "forged", preEvents: "matching" },
    { runId: "mismatch-matrix", status: "exact", preEvents: "mismatches" },
    { runId: "steer-terminal-race", status: "exact", preEvents: "none" },
    { runId: "parent-session-switched", status: "exact", preEvents: "none" },
  ];
  let spawnIndex = 0;
  const steerCalls = [];
  let adapter;
  adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") {
      successReply(bus, request, pingData(), true);
      return;
    }
    if (request.method === "spawn") {
      const plan = plans[spawnIndex++];
      const asyncDir = path.join(runtimeRoot, plan.runId);
      fs.mkdirSync(asyncDir, { recursive: true });
      const receipt = receiptFor(cwd, plan.runId);
      receipt.asyncDir = asyncDir;
      receipt.statusPath = path.join(asyncDir, "status.json");
      receipt.processTerminalPath = path.join(asyncDir, "process-terminal.json");
      const status = exactStatus(receipt, "running", {
        sessionId: "upstream-run-session",
        ...(plan.status === "forged" ? { launchContractDigest: "b".repeat(64) } : {}),
      });
      fs.writeFileSync(path.join(asyncDir, "status.json"), JSON.stringify(status));
      if (plan.preEvents === "matching") {
        bus.emit("subagent:control-event", turnThresholdEvent(plan.runId, asyncDir, 18));
        bus.emit("subagent:control-event", turnThresholdEvent(plan.runId, asyncDir, 19));
      } else if (plan.preEvents === "mismatches") {
        const mismatches = [
          turnThresholdEvent(plan.runId, asyncDir, 17),
          turnThresholdEvent("other-run", asyncDir, 18),
          turnThresholdEvent(plan.runId, `${asyncDir}-forged`, 18),
          turnThresholdEvent(plan.runId, asyncDir, 18, { source: "foreground" }),
          turnThresholdEvent(plan.runId, asyncDir, 18, { event: { type: "needs_attention" } }),
          turnThresholdEvent(plan.runId, asyncDir, 18, { event: { reason: "time_threshold" } }),
          turnThresholdEvent(plan.runId, asyncDir, 18, { event: { agent: "reviewer" } }),
          turnThresholdEvent(plan.runId, asyncDir, 18, { event: { index: 1 } }),
        ];
        for (const event of mismatches) bus.emit("subagent:control-event", event);
      }
      successReply(bus, request, {
        details: { mode: "single", runId: plan.runId, asyncId: plan.runId, asyncDir, launchContractDigest: DIGEST },
      }, true);
      return;
    }
    if (request.method === "steer") {
      steerCalls.push(structuredClone(request));
      if (request.params.runId === "steer-terminal-race") {
        const asyncDir = path.join(runtimeRoot, request.params.runId);
        const statusPath = path.join(asyncDir, "status.json");
        const receipt = receiptFor(cwd, request.params.runId);
        receipt.asyncDir = asyncDir;
        receipt.statusPath = statusPath;
        receipt.processTerminalPath = path.join(asyncDir, "process-terminal.json");
        fs.writeFileSync(statusPath, JSON.stringify(exactStatus(receipt, "complete", { sessionId: "upstream-run-session" })));
        bus.emit(PROCESS_TERMINAL_EVENT, { runId: request.params.runId });
        bus.emit("subagent:control-event", turnThresholdEvent(request.params.runId, receipt.asyncDir, 20));
        bus.emit(`${RPC_REPLY}${request.requestId}`, {
          version: 1,
          requestId: request.requestId,
          method: request.method,
          success: false,
          error: { code: "terminal-race" },
        });
      } else {
        successReply(bus, request, { steering: { state: "delivered" } }, true);
      }
      return;
    }
    assert.fail(`unexpected RPC method ${request.method}`);
  }, { sessionId: () => hostSessionId });

  const dispatchBudgeted = async () => {
    const request = dispatchRequest(cwd);
    request.turnBudget = { maxTurns: 20 };
    return resultDetails(await adapter.execute(request));
  };

  const matched = await dispatchBudgeted();
  await waitUntil(() => steerCalls.length === 1, "pre-receipt exact threshold event must steer");
  assert.deepEqual(steerCalls[0].params, {
    runId: matched.runId,
    index: 0,
    message: "Turn-budget handoff notice: finish the current tool call and start no new exploration. Make the lane state safe, then return the required lane-ready report now; if that is not defensible, return blocked evidence. Include exact HEAD SHA, clean status, focused test evidence, and residual risks. Do not collect or land.",
    steeringRecovery: false,
  });
  assert.equal(adapter.activeSubscriptions(), 0, "accepted one-shot observer must clean up");

  for (const label of ["forged digest", "mismatched event matrix"]) {
    const receipt = await dispatchBudgeted();
    await new Promise((resolve) => setTimeout(resolve, 25));
    assert.equal(steerCalls.length, 1, `${label} must not steer`);
    adapter.bus.emit(PROCESS_TERMINAL_EVENT, { runId: receipt.runId });
    assert.equal(adapter.activeSubscriptions(), 0, `${label} observer must clean up at terminal event`);
  }

  const racing = await dispatchBudgeted();
  adapter.bus.emit("subagent:control-event", turnThresholdEvent(racing.runId, racing.asyncDir, 18));
  await waitUntil(() => steerCalls.length === 2, "running exact event must attempt steer");
  await new Promise((resolve) => setTimeout(resolve, 25));
  assert.equal(steerCalls.filter((call) => call.params.runId === racing.runId).length, 1, "terminal/failed-steer race must not retry");
  assert.equal(adapter.activeSubscriptions(), 0);

  const switched = await dispatchBudgeted();
  hostSessionId = "replacement-host-session";
  adapter.bus.emit("subagent:control-event", turnThresholdEvent(switched.runId, switched.asyncDir, 18));
  await new Promise((resolve) => setTimeout(resolve, 25));
  assert.equal(steerCalls.length, 2, "event after parent-session switch must not steer the old run");
  adapter.bus.emit(PROCESS_TERMINAL_EVENT, { runId: switched.runId });
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioSpawnCorrelation() {
  const cwd = makeRepo();
  const invalidDetails = [
    { mode: "parallel", runId: "bad-mode", asyncId: "bad-mode", launchContractDigest: DIGEST },
    { mode: "single", runId: "missing-async", launchContractDigest: DIGEST },
    { mode: "single", runId: "mismatch-async", asyncId: "different-run", launchContractDigest: DIGEST },
    { mode: "single", runId: "bad-digest", asyncId: "bad-digest", launchContractDigest: "not-a-digest" },
  ];
  let spawnIndex = 0;
  const stopped = [];
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else if (request.method === "spawn") {
      const details = invalidDetails[spawnIndex++];
      const asyncDir = path.join(cwd, ".runtime", details.runId);
      fs.mkdirSync(asyncDir, { recursive: true });
      successReply(bus, request, { text: JSON.stringify({ runId: "human-forgery" }), details: { ...details, asyncDir } });
    } else if (request.method === "stop") {
      stopped.push(request.params.runId);
      successReply(bus, request, { runId: request.params.runId, state: "stopping" });
    } else assert.fail(`unexpected RPC method ${request.method}`);
  });
  for (const details of invalidDetails) {
    const result = await adapter.execute(dispatchRequest(cwd));
    assert.equal(result.isError, true);
    assert.equal(resultDetails(result).error.code, "orphan_risk");
    assert.equal(resultDetails(result).error.runId, details.runId);
  }
  assert.deepEqual(stopped, invalidDetails.map((details) => details.runId));
  assert.equal(adapter.calls.filter((call) => call.method === "spawn").length, invalidDetails.length);
}

async function scenarioAttestObserved() {
  const cwd = makeRepo();
  const receipt = receiptFor(cwd, "observed-run");
  fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "running")));
  fs.writeFileSync(receipt.processTerminalPath, JSON.stringify(observedProof(receipt.runId)));
  const adapter = await loadAdapter(cwd);
  const result = await adapter.execute({ version: 1, action: "attest-run", receipt });
  assert.notEqual(result.isError, true);
  assert.deepEqual(resultDetails(result), {
    version: 1,
    runId: receipt.runId,
    execution: "running",
    processTerminal: "observed",
    canonicalSessionLease: "released",
    evidenceSource: "sidecar",
  });
  assert.equal(adapter.calls.length, 0);
}

async function scenarioAttestReceiptPaths() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd);

  const aliasedSentinelReceipt = (runId, label) => {
    const receipt = receiptFor(cwd, `sentinel-${label}`);
    const sentinelRoot = fs.mkdtempSync(path.join(os.tmpdir(), "orchestrate-pi-external-"));
    const apparentRun = path.join(sentinelRoot, "apparent-run");
    fs.mkdirSync(apparentRun);
    receipt.runId = runId;
    receipt.asyncDir = `${apparentRun}${path.sep}${runId}`;
    receipt.statusPath = path.join(receipt.asyncDir, "status.json");
    receipt.processTerminalPath = path.join(receipt.asyncDir, "process-terminal.json");
    fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "complete")));
    fs.writeFileSync(receipt.processTerminalPath, JSON.stringify(observedProof(receipt.runId)));
    return receipt;
  };

  const traversal = aliasedSentinelReceipt("..", "parent");
  const dotAlias = aliasedSentinelReceipt(".", "dot");
  const externalStatus = receiptFor(cwd, "external-status-run");
  const externalStatusDir = fs.mkdtempSync(path.join(os.tmpdir(), "orchestrate-pi-external-status-"));
  externalStatus.statusPath = path.join(externalStatusDir, "status.json");
  fs.writeFileSync(externalStatus.statusPath, JSON.stringify(exactStatus(externalStatus, "complete")));
  fs.writeFileSync(externalStatus.processTerminalPath, JSON.stringify(observedProof(externalStatus.runId)));

  const backslashRun = receiptFor(cwd, "nested\\run");
  fs.writeFileSync(backslashRun.statusPath, JSON.stringify(exactStatus(backslashRun, "complete")));
  fs.writeFileSync(backslashRun.processTerminalPath, JSON.stringify(observedProof(backslashRun.runId)));

  const malformed = (label, mutate) => {
    const receipt = receiptFor(cwd, `malformed-${label}`);
    mutate(receipt);
    return [label, receipt];
  };
  const cases = [
    ["parent traversal with external lifecycle sentinels", traversal],
    ["dot run alias with external lifecycle sentinels", dotAlias],
    ["external status path", externalStatus],
    ["backslash separator in runId", backslashRun],
    malformed("slash-run", (receipt) => { receipt.runId = "nested/run"; }),
    malformed("absolute-run", (receipt) => { receipt.runId = path.join(cwd, "absolute-run"); }),
    malformed("nul-run", (receipt) => {
      receipt.runId = "run\u0000id";
      receipt.asyncDir = `${path.dirname(receipt.asyncDir)}${path.sep}${receipt.runId}`;
      receipt.statusPath = `${receipt.asyncDir}${path.sep}status.json`;
      receipt.processTerminalPath = `${receipt.asyncDir}${path.sep}process-terminal.json`;
    }),
    malformed("relative-async", (receipt) => { receipt.asyncDir = path.join("relative", receipt.runId); }),
    malformed("dot-segment-async", (receipt) => { receipt.asyncDir = `${path.dirname(receipt.asyncDir)}${path.sep}.${path.sep}${receipt.runId}`; }),
    malformed("parent-segment-async", (receipt) => { receipt.asyncDir = `${path.dirname(receipt.asyncDir)}${path.sep}child${path.sep}..${path.sep}${receipt.runId}`; }),
    malformed("trailing-async", (receipt) => { receipt.asyncDir = `${receipt.asyncDir}${path.sep}`; }),
    malformed("relative-status", (receipt) => { receipt.statusPath = "status.json"; }),
    malformed("dot-segment-status", (receipt) => { receipt.statusPath = `${receipt.asyncDir}${path.sep}.${path.sep}status.json`; }),
    malformed("sibling-status", (receipt) => { receipt.statusPath = path.join(receipt.asyncDir, "..", "status.json"); }),
    malformed("nested-status", (receipt) => { receipt.statusPath = path.join(receipt.asyncDir, "nested", "status.json"); }),
    malformed("relative-proof", (receipt) => { receipt.processTerminalPath = "process-terminal.json"; }),
    malformed("dot-segment-proof", (receipt) => { receipt.processTerminalPath = `${receipt.asyncDir}${path.sep}.${path.sep}process-terminal.json`; }),
    malformed("sibling-proof", (receipt) => { receipt.processTerminalPath = path.join(receipt.asyncDir, "..", "process-terminal.json"); }),
    malformed("nested-proof", (receipt) => { receipt.processTerminalPath = path.join(receipt.asyncDir, "nested", "process-terminal.json"); }),
  ];

  for (const [label, receipt] of cases) {
    const result = await adapter.execute({ version: 1, action: "attest-run", receipt, waitMs: 50 });
    assert.equal(result.isError, true, `${label} must fail before sentinel evidence can project safe`);
    assert.equal(resultDetails(result).error.code, "invalid_request", label);
    assert.equal(adapter.activeSubscriptionsFor(PROCESS_TERMINAL_EVENT), 0, `${label} must not subscribe`);
    assert.equal(adapter.calls.length, 0, `${label} must not invoke lifecycle RPC`);
  }

  const exact = receiptFor(cwd, "exact-receipt-run");
  fs.writeFileSync(exact.statusPath, JSON.stringify(exactStatus(exact, "complete")));
  fs.writeFileSync(exact.processTerminalPath, JSON.stringify(observedProof(exact.runId)));
  assert.deepEqual(resultDetails(await adapter.execute({ version: 1, action: "attest-run", receipt: exact })), {
    version: 1,
    runId: exact.runId,
    execution: "complete",
    processTerminal: "observed",
    canonicalSessionLease: "released",
    evidenceSource: "sidecar",
  });
}

async function scenarioAttestIndependent() {
  const cwd = makeRepo();
  const receipt = receiptFor(cwd, "pending-run");
  fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "complete", {
    endedAt: 1730000000000,
    pid: 999999,
    resultFile: path.join(receipt.asyncDir, "result.json"),
  })));
  fs.writeFileSync(path.join(receipt.asyncDir, "result.json"), "{}");
  fs.writeFileSync(receipt.processTerminalPath, JSON.stringify({
    version: 1,
    state: "pending",
    runId: receipt.runId,
    runnerProcessInstanceId: "runner-pending",
  }));
  const adapter = await loadAdapter(cwd);
  const result = await adapter.execute({ version: 1, action: "attest-run", receipt });
  assert.deepEqual(resultDetails(result), {
    version: 1,
    runId: receipt.runId,
    execution: "complete",
    processTerminal: "unknown",
    canonicalSessionLease: "unknown",
    evidenceSource: "sidecar",
    reason: "process-terminal-pending",
  });
}

async function scenarioAttestInvalidProof() {
  const cwd = makeRepo();
  for (const [runId, sidecar] of [
    ["malformed-run", "{not-json"],
    ["mismatch-run", JSON.stringify(observedProof("different-run"))],
  ]) {
    const receipt = receiptFor(cwd, runId);
    fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "complete", {
      processTerminal: observedProof(runId),
    })));
    fs.writeFileSync(receipt.processTerminalPath, sidecar);
    const adapter = await loadAdapter(cwd);
    const result = await adapter.execute({ version: 1, action: "attest-run", receipt });
    const details = resultDetails(result);
    assert.equal(details.execution, "complete");
    assert.equal(details.processTerminal, "unknown");
    assert.equal(details.canonicalSessionLease, "unknown");
    assert.equal(details.evidenceSource, "sidecar");
    assert.match(details.reason, /malformed|mismatch/);
  }
}

async function scenarioAttestCanonicalSession() {
  const cwd = makeRepo();
  const malformedIdentities = [
    ["missing", (canonicalSession) => { delete canonicalSession.canonicalSessionId; }],
    ["empty", (canonicalSession) => { canonicalSession.canonicalSessionId = ""; }],
    ["non-string", (canonicalSession) => { canonicalSession.canonicalSessionId = 17; }],
  ];
  const adapter = await loadAdapter(cwd);
  for (const [label, mutate] of malformedIdentities) {
    const receipt = receiptFor(cwd, `canonical-session-${label}`);
    const proof = observedProof(receipt.runId);
    mutate(proof.canonicalSession);
    fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "complete")));
    fs.writeFileSync(receipt.processTerminalPath, JSON.stringify(proof));
    const projected = resultDetails(await adapter.execute({ version: 1, action: "attest-run", receipt }));
    assert.deepEqual(projected, {
      version: 1,
      runId: receipt.runId,
      execution: "complete",
      processTerminal: "unknown",
      canonicalSessionLease: "unknown",
      evidenceSource: "sidecar",
      reason: "process-terminal-malformed",
    });
  }
}

async function scenarioAttestStatus() {
  const cwd = makeRepo();
  const active = receiptFor(cwd, "active-run");
  fs.writeFileSync(active.statusPath, JSON.stringify(exactStatus(active, "complete", {
    processTerminal: {
      version: 1,
      state: "unknown",
      runId: active.runId,
      runnerProcessInstanceId: "runner-active",
      reason: "canonical-session-lease-active",
    },
  })));
  const adapter = await loadAdapter(cwd);
  const activeResult = resultDetails(await adapter.execute({ version: 1, action: "attest-run", receipt: active }));
  assert.deepEqual(activeResult, {
    version: 1,
    runId: active.runId,
    execution: "complete",
    processTerminal: "unknown",
    canonicalSessionLease: "active",
    evidenceSource: "status",
    reason: "canonical-session-lease-active",
  });

  const fallback = receiptFor(cwd, "fallback-run");
  fs.writeFileSync(fallback.statusPath, JSON.stringify(exactStatus(fallback, "failed", {
    processTerminal: observedProof(fallback.runId),
  })));
  const fallbackResult = resultDetails(await adapter.execute({ version: 1, action: "attest-run", receipt: fallback }));
  assert.equal(fallbackResult.execution, "failed");
  assert.equal(fallbackResult.processTerminal, "observed");
  assert.equal(fallbackResult.evidenceSource, "status");

  const badReceipt = structuredClone(fallback);
  badReceipt.processTerminalPath = path.join(fallback.asyncDir, "other.json");
  const invalid = await adapter.execute({ version: 1, action: "attest-run", receipt: badReceipt });
  assert.equal(invalid.isError, true);
  assert.equal(resultDetails(invalid).error.code, "invalid_request");
}

async function scenarioStatusCorrelation() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd);

  const receiptMutations = [
    (receipt) => { receipt.requestId = "not-a-request-id"; },
    (receipt) => { receipt.expected.initialHead = "not-a-sha"; },
    (receipt) => { receipt.runtime.launchContractDigest = "a".repeat(63); },
  ];
  for (const [index, mutate] of receiptMutations.entries()) {
    const receipt = receiptFor(cwd, `bad-receipt-${index}`);
    mutate(receipt);
    const result = await adapter.execute({ version: 1, action: "attest-run", receipt });
    assert.equal(result.isError, true);
    assert.equal(resultDetails(result).error.code, "invalid_receipt");
  }

  const statusMutations = [
    (status) => { delete status.cwd; },
    (status) => { status.cwd = path.join(cwd, "wrong-cwd"); },
    (status) => { delete status.launchContractDigest; },
    (status) => { status.launchContractDigest = "b".repeat(64); },
  ];
  for (const [index, mutate] of statusMutations.entries()) {
    const receipt = receiptFor(cwd, `bad-status-${index}`);
    const status = exactStatus(receipt, "complete");
    mutate(status);
    fs.writeFileSync(receipt.statusPath, JSON.stringify(status));
    fs.writeFileSync(receipt.processTerminalPath, JSON.stringify(observedProof(receipt.runId)));
    const projected = resultDetails(await adapter.execute({ version: 1, action: "attest-run", receipt }));
    assert.equal(projected.execution, "unknown");
    assert.equal(projected.processTerminal, "observed");
    assert.equal(projected.evidenceSource, "sidecar");
  }

  for (const [state, expectedExecution] of [["queued", "running"], ["running", "running"], ["paused", "unknown"]]) {
    const receipt = receiptFor(cwd, `${state}-run`);
    fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, state)));
    const projected = resultDetails(await adapter.execute({ version: 1, action: "attest-run", receipt }));
    assert.equal(projected.execution, expectedExecution);
  }
}

async function scenarioAttestWait() {
  const cwd = makeRepo();
  const receipt = receiptFor(cwd, "wait-run");
  fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "running")));
  const adapter = await loadAdapter(cwd);
  setTimeout(() => {
    fs.writeFileSync(receipt.processTerminalPath, JSON.stringify(observedProof(receipt.runId)));
    adapter.bus.emit("subagent:process-terminal", { runId: receipt.runId, processTerminal: observedProof(receipt.runId) });
  }, 20);
  const waited = resultDetails(await adapter.execute({ version: 1, action: "attest-run", receipt, waitMs: 500 }));
  assert.equal(waited.processTerminal, "observed");
  assert.equal(waited.evidenceSource, "sidecar");
  assert.equal(adapter.activeSubscriptions(), 0);

  fs.rmSync(receipt.processTerminalPath);
  const wakeOnly = adapter.execute({ version: 1, action: "attest-run", receipt, waitMs: 100 });
  setTimeout(() => adapter.bus.emit("subagent:process-terminal", {
    runId: receipt.runId,
    processTerminal: observedProof(receipt.runId),
  }), 10);
  const wakeOnlyResult = resultDetails(await wakeOnly);
  assert.equal(wakeOnlyResult.processTerminal, "unknown");
  assert.equal(wakeOnlyResult.evidenceSource, "event");
  assert.equal(adapter.activeSubscriptions(), 0);

  const controller = new AbortController();
  const aborting = adapter.execute({ version: 1, action: "attest-run", receipt, waitMs: 1000 }, controller.signal);
  setTimeout(() => controller.abort(), 10);
  const aborted = await aborting;
  assert.equal(aborted.isError, true);
  assert.equal(resultDetails(aborted).error.code, "aborted");
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioAttestPreaborted() {
  const cwd = makeRepo();
  const receipt = receiptFor(cwd, "preaborted-run");
  fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "running")));
  const adapter = await loadAdapter(cwd);
  const controller = new AbortController();
  controller.abort();
  const result = await adapter.execute({
    version: 1,
    action: "attest-run",
    receipt,
    waitMs: 500,
  }, controller.signal);
  assert.equal(result.isError, true);
  assert.equal(resultDetails(result).error.code, "aborted");
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioAttestInflightAbort() {
  const cwd = makeRepo();
  const receipt = receiptFor(cwd, "inflight-abort-run");
  fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "running")));
  const adapter = await loadAdapter(cwd);
  const controller = new AbortController();
  const instrumentedOn = adapter.bus.on.bind(adapter.bus);
  let abortQueued = false;
  adapter.bus.on = (event, handler) => {
    const off = instrumentedOn(event, handler);
    if (event === PROCESS_TERMINAL_EVENT && !abortQueued) {
      abortQueued = true;
      queueMicrotask(() => controller.abort());
    }
    return off;
  };

  const result = await adapter.execute({
    version: 1,
    action: "attest-run",
    receipt,
    waitMs: 500,
  }, controller.signal);
  assert.equal(abortQueued, true, "test must abort immediately after the terminal listener is installed");
  assert.equal(result.isError, true);
  assert.equal(resultDetails(result).error.code, "aborted");
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioAttestRaceNoEmit() {
  const cwd = makeRepo();
  const receipt = receiptFor(cwd, "race-proof-run");
  fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "complete")));
  const adapter = await loadAdapter(cwd);
  const externallyObserved = [];
  const stopObserving = adapter.bus.on(PROCESS_TERMINAL_EVENT, (payload) => externallyObserved.push(payload));
  const instrumentedOn = adapter.bus.on.bind(adapter.bus);
  let proofInstalled = false;
  adapter.bus.on = (event, handler) => {
    const off = instrumentedOn(event, handler);
    if (event === PROCESS_TERMINAL_EVENT && !proofInstalled) {
      proofInstalled = true;
      fs.writeFileSync(receipt.processTerminalPath, JSON.stringify(observedProof(receipt.runId)));
    }
    return off;
  };

  const projected = resultDetails(await adapter.execute({
    version: 1,
    action: "attest-run",
    receipt,
    waitMs: 500,
  }));
  assert.equal(proofInstalled, true, "test must install proof only after Adapter subscribes");
  assert.equal(projected.processTerminal, "observed");
  assert.equal(projected.evidenceSource, "sidecar");
  assert.deepEqual(externallyObserved, [], "Adapter must never emit the upstream-owned process event");
  assert.equal(adapter.activeSubscriptionsFor(PROCESS_TERMINAL_EVENT), 1, "only external observer should remain");
  stopObserving();
  assert.equal(adapter.activeSubscriptions(), 0);
}

async function scenarioSchema() {
  const cwd = makeRepo();
  const adapter = await loadAdapter(cwd);
  const schema = adapter.tool.parameters;
  assert.equal(schema.type, "object");
  assert.equal(schema.additionalProperties, false);
  assert.equal(Object.hasOwn(schema, "anyOf"), false, "Google-compatible schema must not use anyOf");
  assert.deepEqual(schema.properties.action.enum, ["dispatch-lane", "attest-run"]);
  assert.equal(schema.properties.action.type, "string");
  assert.deepEqual(Object.keys(schema.properties).sort(), [
    "action", "contract", "expected", "laneId", "receipt", "subjectSha", "taskId", "timeoutMs", "turnBudget", "version", "waitMs",
  ]);
  const harnessSource = fs.readFileSync(import.meta.filename, "utf8");
  assert.doesNotMatch(harnessSource, /\/usr\/lib\/node_modules/);
  assert.match(harnessSource, /PI_CODING_AGENT_SDK_PATH/);
}

function forbiddenAuthorityKey(value) {
  const forbidden = new Set(["laneReady", "collectAllowed", "safeToLand", "accepted", "matchingActiveRuns", "globalLeaseClear"]);
  if (Array.isArray(value)) return value.some(forbiddenAuthorityKey);
  if (!value || typeof value !== "object") return false;
  return Object.entries(value).some(([key, child]) => forbidden.has(key) || forbiddenAuthorityKey(child));
}

async function scenarioAuthorityBoundary() {
  const cwd = makeRepo();
  const runId = "authority-run";
  const asyncDir = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "orchestrate-pi-runtime-")), runId);
  fs.mkdirSync(asyncDir);
  const before = {
    head: git(cwd, "rev-parse", "HEAD"),
    status: git(cwd, "status", "--porcelain=v2", "--untracked-files=all"),
    refs: git(cwd, "show-ref"),
    worktrees: git(cwd, "worktree", "list", "--porcelain"),
  };
  const adapter = await loadAdapter(cwd, ({ bus, request }) => {
    if (request.method === "ping") successReply(bus, request, pingData());
    else if (request.method === "spawn") successReply(bus, request, { details: { mode: "single", runId, asyncId: runId, asyncDir, launchContractDigest: DIGEST } });
    else assert.fail(`unexpected RPC method ${request.method}`);
  });
  const dispatched = await adapter.execute(dispatchRequest(cwd));
  assert.equal(forbiddenAuthorityKey(resultDetails(dispatched)), false);
  const receipt = resultDetails(dispatched);
  fs.writeFileSync(receipt.statusPath, JSON.stringify(exactStatus(receipt, "complete")));
  fs.writeFileSync(receipt.processTerminalPath, JSON.stringify(observedProof(runId)));
  const attested = await adapter.execute({ version: 1, action: "attest-run", receipt });
  assert.equal(forbiddenAuthorityKey(resultDetails(attested)), false);
  const after = {
    head: git(cwd, "rev-parse", "HEAD"),
    status: git(cwd, "status", "--porcelain=v2", "--untracked-files=all"),
    refs: git(cwd, "show-ref"),
    worktrees: git(cwd, "worktree", "list", "--porcelain"),
  };
  assert.deepEqual(after, before);

  const source = fs.readFileSync(EXTENSION, "utf8");
  assert.doesNotMatch(source, /from ["']pi-subagents(?:\/|["'])/);
  assert.doesNotMatch(source, /\/home\/axel\//);
  const siblings = fs.readdirSync(path.dirname(EXTENSION)).filter((name) => name.startsWith("orchestrate-pi"));
  assert.deepEqual(siblings, ["orchestrate-pi.ts"]);
}

const scenarios = {
  load: scenarioLoad,
  strict: scenarioStrict,
  "git-mismatch": scenarioGitMismatch,
  capability: scenarioCapability,
  "profile-success": scenarioProfileSuccess,
  "profile-untrusted": scenarioUntrustedProject,
  "profile-failures": scenarioProfileFailures,
  "profile-package-scope": scenarioProfilePackageScope,
  "profile-cancellation": scenarioProfileCancellation,
  dispatch: scenarioDispatch,
  "dispatch-process-subscription": scenarioDispatchProcessSubscription,
  "dispatch-early-wake": scenarioDispatchEarlyWake,
  "rpc-correlation": scenarioRpcCorrelation,
  "rpc-cancel": scenarioRpcCancel,
  "git-preflight-cancel": scenarioGitPreflightCancel,
  "orphan-risk": scenarioOrphanRisk,
  "dispatch-unattestable-run-id": scenarioDispatchRejectsUnattestableRunId,
  "run-timeout": scenarioRunTimeout,
  "turn-budget": scenarioTurnBudget,
  "turn-handoff": scenarioTurnHandoff,
  "spawn-correlation": scenarioSpawnCorrelation,
  "attest-observed": scenarioAttestObserved,
  "attest-receipt-paths": scenarioAttestReceiptPaths,
  "attest-independent": scenarioAttestIndependent,
  "attest-invalid-proof": scenarioAttestInvalidProof,
  "attest-canonical-session": scenarioAttestCanonicalSession,
  "attest-status": scenarioAttestStatus,
  "status-correlation": scenarioStatusCorrelation,
  "attest-wait": scenarioAttestWait,
  "attest-preaborted": scenarioAttestPreaborted,
  "attest-inflight-abort": scenarioAttestInflightAbort,
  "attest-race-no-emit": scenarioAttestRaceNoEmit,
  schema: scenarioSchema,
  "authority-boundary": scenarioAuthorityBoundary,
};

const selected = scenarios[process.argv[2]];
if (!selected) throw new Error(`unknown scenario: ${process.argv[2]}`);
await selected();
console.log(JSON.stringify({ scenario: process.argv[2], passed: true }));
