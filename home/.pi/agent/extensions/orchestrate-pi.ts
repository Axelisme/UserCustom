import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import { createRequire } from "node:module";
import * as path from "node:path";
import { pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { StringEnum } from "@earendil-works/pi-ai";
import { DefaultPackageManager, SettingsManager, getAgentDir } from "@earendil-works/pi-coding-agent";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const execFileAsync = promisify(execFile);
const RPC_REQUEST = "subagents:rpc:v1:request";
const RPC_REPLY = "subagents:rpc:v1:reply:";
const PROCESS_TERMINAL_EVENT = "subagent:process-terminal";
const RPC_REPLY_TIMEOUT_MS = 10_000;
const GIT_PREFLIGHT_TIMEOUT_MS = 10_000;
const PROFILE_PREFLIGHT_TIMEOUT_MS = 10_000;
const MAX_RUN_TIMEOUT_MS = 604_800_000;
const MAX_ATTEST_WAIT_MS = 120_000;
const MAX_BUFFERED_PROCESS_EVENTS = 64;
const MAX_EARLY_EVENT_WAKES = 64;
const MAX_EVENT_RUN_ID_LENGTH = 512;

type JsonRecord = Record<string, unknown>;
type EventBus = ExtensionAPI["events"];

class AdapterError extends Error {
  constructor(readonly code: string, message: string, readonly extra: JsonRecord = {}) {
    super(message);
  }
}

function record(value: unknown): value is JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value: JsonRecord, allowed: readonly string[], label: string): void {
  const unknown = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unknown.length) throw new AdapterError("invalid_request", `${label} has unknown field(s): ${unknown.join(", ")}.`);
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) throw new AdapterError("invalid_request", `${label} must be a non-empty string.`);
  return value;
}

function stringList(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string" || !entry.trim())) {
    throw new AdapterError("invalid_request", `${label} must be an array of non-empty strings.`);
  }
  return value as string[];
}

function runTimeout(value: unknown): number {
  if (!Number.isInteger(value) || (value as number) < 1 || (value as number) > MAX_RUN_TIMEOUT_MS) {
    throw new AdapterError("invalid_request", `timeoutMs must be an integer from 1 through ${MAX_RUN_TIMEOUT_MS}.`);
  }
  return value as number;
}

function attestWait(value: unknown): number {
  if (!Number.isInteger(value) || (value as number) < 1 || (value as number) > MAX_ATTEST_WAIT_MS) {
    throw new AdapterError("invalid_request", `waitMs must be an integer from 1 through ${MAX_ATTEST_WAIT_MS}.`);
  }
  return value as number;
}

function isRunComponent(runId: string): boolean {
  return runId !== "." && runId !== ".." && !runId.includes("/") && !runId.includes("\\")
    && !runId.includes("\0") && !path.isAbsolute(runId) && path.normalize(runId) === runId;
}

interface ExpectedLane {
  cwd: string;
  gitRoot: string;
  gitCommonDir: string;
  branch: string;
  head: string;
  clean: true;
  primaryDirt: string[];
}

interface FrozenContract {
  objective: string;
  writeScope: string[];
  immutablePaths: string[];
  focusedCommands: string[];
  evidence: string[];
  stopConditions: string[];
}

interface DispatchRequest {
  version: 1;
  action: "dispatch-lane";
  taskId: string;
  laneId: string;
  subjectSha: string;
  expected: ExpectedLane;
  contract: FrozenContract;
  timeoutMs?: number;
}

interface DispatchReceipt {
  version: 1;
  requestId: string;
  runId: string;
  asyncDir: string;
  statusPath: string;
  processTerminalPath: string;
  expected: {
    cwd: string;
    gitRoot: string;
    gitCommonDir: string;
    branch: string;
    initialHead: string;
  };
  runtime: {
    rpcVersion: 1;
    processTerminalVersion: 1;
    lifecycleArtifactVersion: 3;
    launchContractDigest: string;
    hostSessionId?: string;
  };
}

interface AttestRequest {
  version: 1;
  action: "attest-run";
  receipt: DispatchReceipt;
  waitMs?: number;
}

type AdapterRequest = DispatchRequest | AttestRequest;

function parseDispatch(raw: JsonRecord): DispatchRequest {
  exactKeys(raw, ["version", "action", "taskId", "laneId", "subjectSha", "expected", "contract", "timeoutMs"], "request");
  if (raw.version !== 1) throw new AdapterError("unsupported_version", `Unsupported orchestrate_pi version: ${String(raw.version)}.`);
  if (raw.action !== "dispatch-lane") throw new AdapterError("unsupported_action", `Unsupported orchestrate_pi action: ${String(raw.action)}.`);
  if (!record(raw.expected)) throw new AdapterError("invalid_request", "expected must be an object.");
  exactKeys(raw.expected, ["cwd", "gitRoot", "gitCommonDir", "branch", "head", "clean", "primaryDirt"], "expected");
  if (raw.expected.clean !== true) throw new AdapterError("invalid_request", "expected.clean must be true.");
  if (!record(raw.contract)) throw new AdapterError("invalid_request", "contract must be an object.");
  exactKeys(raw.contract, ["objective", "writeScope", "immutablePaths", "focusedCommands", "evidence", "stopConditions"], "contract");
  const expected: ExpectedLane = {
    cwd: text(raw.expected.cwd, "expected.cwd"),
    gitRoot: text(raw.expected.gitRoot, "expected.gitRoot"),
    gitCommonDir: text(raw.expected.gitCommonDir, "expected.gitCommonDir"),
    branch: text(raw.expected.branch, "expected.branch"),
    head: text(raw.expected.head, "expected.head"),
    clean: true,
    primaryDirt: stringList(raw.expected.primaryDirt, "expected.primaryDirt"),
  };
  const subjectSha = text(raw.subjectSha, "subjectSha");
  if (!/^[0-9a-f]{40,64}$/.test(subjectSha) || subjectSha !== expected.head) {
    throw new AdapterError("invalid_request", "subjectSha must be the full expected HEAD SHA.");
  }
  return {
    version: 1,
    action: "dispatch-lane",
    taskId: text(raw.taskId, "taskId"),
    laneId: text(raw.laneId, "laneId"),
    subjectSha,
    expected,
    contract: {
      objective: text(raw.contract.objective, "contract.objective"),
      writeScope: stringList(raw.contract.writeScope, "contract.writeScope"),
      immutablePaths: stringList(raw.contract.immutablePaths, "contract.immutablePaths"),
      focusedCommands: stringList(raw.contract.focusedCommands, "contract.focusedCommands"),
      evidence: stringList(raw.contract.evidence, "contract.evidence"),
      stopConditions: stringList(raw.contract.stopConditions, "contract.stopConditions"),
    },
    ...(raw.timeoutMs === undefined ? {} : { timeoutMs: runTimeout(raw.timeoutMs) }),
  };
}

function parsePathBoundReceipt(raw: unknown): DispatchReceipt {
  if (!record(raw)) throw new AdapterError("invalid_receipt", "receipt must be an object.");
  exactKeys(raw, ["version", "requestId", "runId", "asyncDir", "statusPath", "processTerminalPath", "expected", "runtime"], "receipt");
  if (raw.version !== 1) throw new AdapterError("invalid_receipt", "receipt version must be 1.");
  if (!record(raw.expected) || !record(raw.runtime)) throw new AdapterError("invalid_receipt", "receipt expected and runtime must be objects.");
  exactKeys(raw.expected, ["cwd", "gitRoot", "gitCommonDir", "branch", "initialHead"], "receipt.expected");
  exactKeys(raw.runtime, ["rpcVersion", "processTerminalVersion", "lifecycleArtifactVersion", "launchContractDigest", "hostSessionId"], "receipt.runtime");
  const requestId = text(raw.requestId, "receipt.requestId");
  const runId = text(raw.runId, "receipt.runId");
  const asyncDir = text(raw.asyncDir, "receipt.asyncDir");
  const statusPath = text(raw.statusPath, "receipt.statusPath");
  const processTerminalPath = text(raw.processTerminalPath, "receipt.processTerminalPath");
  const initialHead = text(raw.expected.initialHead, "receipt.expected.initialHead");
  const launchContractDigest = text(raw.runtime.launchContractDigest, "receipt.runtime.launchContractDigest");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId)
    || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i.test(initialHead)
    || !/^[0-9a-f]{64}$/i.test(launchContractDigest)) {
    throw new AdapterError("invalid_receipt", "receipt requestId, initialHead, or launchContractDigest format is invalid.");
  }
  const invalidRunId = !isRunComponent(runId);
  const invalidAsyncDir = asyncDir.includes("\0") || !path.isAbsolute(asyncDir)
    || path.normalize(asyncDir) !== asyncDir || asyncDir.endsWith(path.sep) || path.basename(asyncDir) !== runId;
  const invalidStatusPath = statusPath.includes("\0") || !path.isAbsolute(statusPath)
    || path.normalize(statusPath) !== statusPath || statusPath !== `${asyncDir}${path.sep}status.json`;
  const invalidProcessTerminalPath = processTerminalPath.includes("\0") || !path.isAbsolute(processTerminalPath)
    || path.normalize(processTerminalPath) !== processTerminalPath
    || processTerminalPath !== `${asyncDir}${path.sep}process-terminal.json`;
  if (invalidRunId || invalidAsyncDir || invalidStatusPath || invalidProcessTerminalPath) {
    throw new AdapterError("invalid_request", "receipt lifecycle paths must be normalized exact children of the exact run directory.");
  }
  if (raw.runtime.rpcVersion !== 1 || raw.runtime.processTerminalVersion !== 1 || raw.runtime.lifecycleArtifactVersion !== 3) {
    throw new AdapterError("invalid_receipt", "receipt protocol versions are incompatible.");
  }
  return {
    version: 1,
    requestId,
    runId,
    asyncDir,
    statusPath,
    processTerminalPath,
    expected: {
      cwd: text(raw.expected.cwd, "receipt.expected.cwd"),
      gitRoot: text(raw.expected.gitRoot, "receipt.expected.gitRoot"),
      gitCommonDir: text(raw.expected.gitCommonDir, "receipt.expected.gitCommonDir"),
      branch: text(raw.expected.branch, "receipt.expected.branch"),
      initialHead,
    },
    runtime: {
      rpcVersion: 1,
      processTerminalVersion: 1,
      lifecycleArtifactVersion: 3,
      launchContractDigest,
      ...(raw.runtime.hostSessionId === undefined ? {} : { hostSessionId: text(raw.runtime.hostSessionId, "receipt.runtime.hostSessionId") }),
    },
  };
}

function parseRequest(raw: unknown): AdapterRequest {
  if (!record(raw)) throw new AdapterError("invalid_request", "request must be an object.");
  if (raw.version !== 1) throw new AdapterError("unsupported_version", `Unsupported orchestrate_pi version: ${String(raw.version)}.`);
  if (raw.action === "dispatch-lane") return parseDispatch(raw);
  if (raw.action === "attest-run") {
    exactKeys(raw, ["version", "action", "receipt", "waitMs"], "request");
    return {
      version: 1,
      action: "attest-run",
      receipt: parsePathBoundReceipt(raw.receipt),
      ...(raw.waitMs === undefined ? {} : { waitMs: attestWait(raw.waitMs) }),
    };
  }
  throw new AdapterError("unsupported_action", `Unsupported orchestrate_pi action: ${String(raw.action)}.`);
}

async function git(cwd: string, signal: AbortSignal | undefined, ...args: string[]): Promise<string> {
  try {
    const { stdout } = await execFileAsync("git", args, {
      cwd,
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
      signal,
      timeout: GIT_PREFLIGHT_TIMEOUT_MS,
    });
    return stdout.trim();
  } catch (error) {
    if (signal?.aborted || (record(error) && (error.name === "AbortError" || error.code === "ABORT_ERR"))) {
      throw new AdapterError("aborted", "Dispatch was aborted during Git preflight.");
    }
    throw new AdapterError("git_preflight_failed", error instanceof Error ? error.message : String(error));
  }
}

async function canonical(value: string, base?: string): Promise<string> {
  try {
    return await realpath(base && !path.isAbsolute(value) ? path.resolve(base, value) : value);
  } catch (error) {
    throw new AdapterError("git_preflight_failed", error instanceof Error ? error.message : String(error));
  }
}

async function verifyLane(expected: ExpectedLane, signal?: AbortSignal): Promise<ExpectedLane> {
  const cwd = await canonical(expected.cwd);
  const [rootText, commonText, branch, head, dirt] = await Promise.all([
    git(cwd, signal, "rev-parse", "--show-toplevel"),
    git(cwd, signal, "rev-parse", "--git-common-dir"),
    git(cwd, signal, "symbolic-ref", "--short", "HEAD"),
    git(cwd, signal, "rev-parse", "HEAD"),
    git(cwd, signal, "status", "--porcelain"),
  ]);
  const gitRoot = await canonical(rootText, cwd);
  const gitCommonDir = await canonical(commonText, cwd);
  const wanted = {
    cwd: await canonical(expected.cwd),
    gitRoot: await canonical(expected.gitRoot),
    gitCommonDir: await canonical(expected.gitCommonDir),
    branch: expected.branch,
    head: expected.head,
    clean: true as const,
    primaryDirt: expected.primaryDirt,
  };
  const mismatch = cwd !== wanted.cwd || gitRoot !== wanted.gitRoot || gitCommonDir !== wanted.gitCommonDir
    || branch !== wanted.branch || head !== wanted.head || dirt !== "";
  if (mismatch) {
    throw new AdapterError("git_identity_mismatch", "Canonical cwd or Git identity does not match the admitted lane.", {
      observed: { cwd, gitRoot, gitCommonDir, branch, head, clean: dirt === "" },
    });
  }
  return wanted;
}

interface RpcReply {
  version: 1;
  requestId: string;
  method?: string;
  success: boolean;
  data?: unknown;
  error?: unknown;
}

function rpcCall(
  bus: EventBus,
  method: string,
  params: unknown,
  timeoutMs: number,
  signal?: AbortSignal,
): Promise<{ requestId: string; data: unknown }> {
  const requestId = randomUUID();
  if (signal?.aborted) return Promise.reject(new AdapterError("aborted", `Subagent RPC ${method} was aborted.`));
  return new Promise((resolve, reject) => {
    let settled = false;
    let off: (() => void) | void;
    let timer: ReturnType<typeof setTimeout>;
    const finish = (error?: AdapterError, data?: unknown) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (typeof off === "function") off();
      signal?.removeEventListener("abort", onAbort);
      if (error) reject(error);
      else resolve({ requestId, data });
    };
    const onAbort = () => finish(new AdapterError("aborted", `Subagent RPC ${method} was aborted.`));
    off = bus.on(`${RPC_REPLY}${requestId}`, (raw: unknown) => {
      if (!record(raw) || raw.version !== 1 || raw.requestId !== requestId) return;
      if (raw.method !== undefined && raw.method !== method) return;
      if (raw.success !== true) {
        finish(new AdapterError("rpc_failure", `Subagent RPC ${method} failed closed.`));
        return;
      }
      finish(undefined, (raw as RpcReply).data);
    });
    timer = setTimeout(() => finish(new AdapterError("rpc_timeout", `Subagent RPC ${method} timed out.`)), timeoutMs);
    signal?.addEventListener("abort", onAbort, { once: true });
    bus.emit(RPC_REQUEST, { version: 1, requestId, method, ...(params === undefined ? {} : { params }), source: { extension: "orchestrate-pi" } });
  });
}

function requireCapabilities(raw: unknown): string {
  if (!record(raw) || raw.version !== 1 || !Array.isArray(raw.methods) || !record(raw.capabilities) || !record(raw.events)) {
    throw new AdapterError("rpc_capability_mismatch", "Malformed subagent RPC ping response.");
  }
  const methods = raw.methods as unknown[];
  const proof = raw.capabilities.processTerminalProof;
  const compatible = ["spawn", "status", "stop"].every((method) => methods.includes(method))
    && raw.capabilities.status === true && raw.capabilities.asyncSpawn === true && raw.capabilities.stop === true
    && record(proof) && proof.version === 1 && proof.lifecycleArtifactVersion === 3
    && raw.events.request === RPC_REQUEST && raw.events.replyPrefix === RPC_REPLY
    && raw.events.processTerminal === PROCESS_TERMINAL_EVENT;
  if (!compatible) throw new AdapterError("rpc_capability_mismatch", "Required RPC, async spawn, or lifecycle proof capability is unavailable.");
  return raw.events.processTerminal as string;
}

function profileMismatch(): AdapterError {
  return new AdapterError(
    "profile_capability_mismatch",
    "The configured Pi lane-worker profile and its required tdd capability could not be proven exactly.",
  );
}

function requireProfileResult(raw: unknown, cwd: string): void {
  if (!record(raw) || raw.ok !== true || !record(raw.contract)) throw profileMismatch();
  const contract = raw.contract;
  if (contract.version !== 2 || !record(contract.agent) || contract.agent.name !== "lane-worker"
    || !Array.isArray(contract.agent.shadowedCandidates) || contract.agent.shadowedCandidates.length !== 0
    || contract.context !== "fresh" || !record(contract.roots) || contract.roots.cwd !== cwd
    || !record(contract.skills) || !Array.isArray(contract.skills.requested)
    || contract.skills.requested.length !== 1 || contract.skills.requested[0] !== "tdd"
    || !Array.isArray(contract.skills.resolved) || contract.skills.resolved.length !== 1
    || !record(contract.skills.resolved[0]) || contract.skills.resolved[0].name !== "tdd"
    || !Array.isArray(contract.skills.missing) || contract.skills.missing.length !== 0
    || !Array.isArray(contract.diagnostics)
    || contract.diagnostics.some((diagnostic) => !record(diagnostic)
      || typeof diagnostic.severity !== "string" || diagnostic.severity === "error")) {
    throw profileMismatch();
  }
}

function validPackageExport(value: unknown): boolean {
  if (typeof value === "string") return value.startsWith("./") && value.length > 2;
  if (Array.isArray(value)) return value.length > 0 && value.every(validPackageExport);
  return record(value) && Object.keys(value).length > 0 && Object.values(value).every(validPackageExport);
}

function isWithinPackageRoot(root: string, entry: string): boolean {
  const relative = path.relative(root, entry);
  return relative !== "" && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

function boundedProfilePreflight(operation: () => Promise<void>, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return Promise.reject(new AdapterError("aborted", "Dispatch was aborted during profile preflight."));
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error?: AdapterError) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      if (error) reject(error);
      else resolve();
    };
    const onAbort = () => finish(new AdapterError("aborted", "Dispatch was aborted during profile preflight."));
    const timer = setTimeout(() => finish(profileMismatch()), PROFILE_PREFLIGHT_TIMEOUT_MS);
    signal?.addEventListener("abort", onAbort, { once: true });
    const pending = Promise.resolve().then(operation);
    void pending.then(
      () => finish(),
      (error) => finish(error instanceof AdapterError && error.code === "aborted" ? error : profileMismatch()),
    );
  });
}

async function requireProfileCapability(
  cwd: string,
  task: string,
  ctx: ExtensionContext,
  signal?: AbortSignal,
): Promise<void> {
  await boundedProfilePreflight(async () => {
    if (ctx.isProjectTrusted() !== true) throw profileMismatch();
    const agentDir = getAgentDir();
    const settingsManager = SettingsManager.create(cwd, agentDir, { projectTrusted: true });
    if (settingsManager.drainErrors().length !== 0) throw profileMismatch();
    const packageManager = new DefaultPackageManager({ cwd, agentDir, settingsManager });
    const matchingPackages: { root: string; manifestPath: string; manifest: JsonRecord }[] = [];
    for (const configured of packageManager.listConfiguredPackages()) {
      if (configured.installedPath === undefined) continue;
      const root = await realpath(configured.installedPath);
      const manifestPath = path.join(root, "package.json");
      const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as unknown;
      if (!record(manifest) || typeof manifest.name !== "string") throw profileMismatch();
      if (manifest.name === "pi-subagents") matchingPackages.push({ root, manifestPath, manifest });
    }
    if (matchingPackages.length !== 1) throw profileMismatch();
    const selected = matchingPackages[0];
    if (!record(selected.manifest.exports)
      || !Object.prototype.hasOwnProperty.call(selected.manifest.exports, "./preflight")
      || !validPackageExport(selected.manifest.exports["./preflight"])) throw profileMismatch();
    const packageRequire = createRequire(selected.manifestPath);
    const publicEntry = await realpath(packageRequire.resolve("pi-subagents/preflight"));
    if (!isWithinPackageRoot(selected.root, publicEntry)) throw profileMismatch();
    const imported = await import(pathToFileURL(publicEntry).href) as JsonRecord;
    if (typeof imported.resolveSubagentLaunchContract !== "function") throw profileMismatch();
    const result = await imported.resolveSubagentLaunchContract({
      agent: "lane-worker",
      cwd,
      context: "fresh",
      task,
      artifacts: false,
    });
    requireProfileResult(result, cwd);
  }, signal);
}

class BoundedRunIds {
  private readonly runIds = new Set<string>();

  constructor(private readonly capacity: number) {}

  add(runId: string): void {
    this.runIds.delete(runId);
    this.runIds.add(runId);
    while (this.runIds.size > this.capacity) {
      const oldest = this.runIds.values().next().value as string | undefined;
      if (oldest === undefined) break;
      this.runIds.delete(oldest);
    }
  }

  consume(runId: string): boolean {
    return this.runIds.delete(runId);
  }

  clear(): void {
    this.runIds.clear();
  }
}

interface ProcessEventObserver {
  correlate(runId: string): boolean;
  cancel(): void;
}

function observeProcessEvents(bus: EventBus, event: string): ProcessEventObserver {
  const observedRunIds = new BoundedRunIds(MAX_BUFFERED_PROCESS_EVENTS);
  let cancelled = false;
  const off = bus.on(event, (payload: unknown) => {
    if (record(payload) && typeof payload.runId === "string"
      && payload.runId.trim() && payload.runId.length <= MAX_EVENT_RUN_ID_LENGTH) {
      observedRunIds.add(payload.runId);
    }
  });
  return {
    correlate(runId: string) {
      return observedRunIds.consume(runId);
    },
    cancel() {
      if (cancelled) return;
      cancelled = true;
      observedRunIds.clear();
      if (typeof off === "function") off();
    },
  };
}

async function dispatch(
  bus: EventBus,
  earlyEventWakes: BoundedRunIds,
  request: DispatchRequest,
  ctx: ExtensionContext,
  signal?: AbortSignal,
): Promise<JsonRecord> {
  if (signal?.aborted) throw new AdapterError("aborted", "Dispatch was aborted before preflight.");
  const expected = await verifyLane(request.expected, signal);
  const ping = await rpcCall(bus, "ping", undefined, RPC_REPLY_TIMEOUT_MS, signal);
  const processTerminalEvent = requireCapabilities(ping.data);
  const task = `Execute the admitted lane Contract exactly:\n${JSON.stringify({
    taskId: request.taskId,
    laneId: request.laneId,
    subjectSha: request.subjectSha,
    expected: request.expected,
    contract: request.contract,
  })}`;
  await requireProfileCapability(expected.cwd, task, ctx, signal);
  if (signal?.aborted) throw new AdapterError("aborted", "Dispatch was aborted during profile preflight.");
  const processObserver = observeProcessEvents(bus, processTerminalEvent);
  try {
    const spawned = await rpcCall(bus, "spawn", {
      agent: "lane-worker",
      task,
      context: "fresh",
      async: true,
      clarify: false,
      cwd: expected.cwd,
      ...(request.timeoutMs === undefined ? {} : { timeoutMs: request.timeoutMs }),
    }, RPC_REPLY_TIMEOUT_MS, signal);
    const details = record(spawned.data) && record(spawned.data.details) ? spawned.data.details : undefined;
    const possibleRunId = details && typeof details.runId === "string" && details.runId.trim() ? details.runId : undefined;
    let runId: string;
    let asyncDir: string;
    let launchContractDigest: string;
    try {
      if (!details) throw new AdapterError("invalid_spawn_receipt", "RPC spawn did not return structured details.");
      if (details.mode !== "single") throw new AdapterError("invalid_spawn_receipt", "Spawn details mode must be single.");
      runId = text(details.runId, "spawn.details.runId");
      if (!isRunComponent(runId)) throw new AdapterError("invalid_spawn_receipt", "Spawn runId must be one valid path component.");
      const asyncId = text(details.asyncId, "spawn.details.asyncId");
      if (asyncId !== runId) throw new AdapterError("invalid_spawn_receipt", "Spawn runId and asyncId must match exactly.");
      asyncDir = await canonical(text(details.asyncDir, "spawn.details.asyncDir"));
      launchContractDigest = text(details.launchContractDigest, "spawn.details.launchContractDigest");
      if (!/^[0-9a-f]{64}$/i.test(launchContractDigest)) {
        throw new AdapterError("invalid_spawn_receipt", "Spawn launchContractDigest must be 64 hexadecimal characters.");
      }
      if (path.basename(asyncDir) !== runId) throw new AdapterError("invalid_spawn_receipt", "Spawn asyncDir is not owned by the exact runId.");
      if (processObserver.correlate(runId)) earlyEventWakes.add(runId);
    } catch (receiptError) {
      let stopAttempted = false;
      let stopAcknowledged = false;
      if (possibleRunId) {
        stopAttempted = true;
        try {
          await rpcCall(bus, "stop", { runId: possibleRunId }, Math.min(RPC_REPLY_TIMEOUT_MS, 2_000));
          stopAcknowledged = true;
        } catch {
          // The orphan-risk error remains authoritative; stopping is best effort.
        }
      }
      throw new AdapterError("orphan_risk", "Spawn may have started but its structured receipt was invalid.", {
        ...(possibleRunId ? { runId: possibleRunId } : {}),
        stopAttempted,
        stopAcknowledged,
        receiptError: receiptError instanceof AdapterError ? receiptError.code : "invalid_spawn_receipt",
      });
    }
    return {
      version: 1,
      requestId: spawned.requestId,
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
        launchContractDigest,
        ...(ctx.sessionManager.getSessionId() ? { hostSessionId: ctx.sessionManager.getSessionId() } : {}),
      },
    };
  } finally {
    processObserver.cancel();
  }
}

type JsonRead = { kind: "missing" } | { kind: "malformed" } | { kind: "value"; value: JsonRecord };

type EvidenceProjection = {
  processTerminal: "observed" | "active" | "unknown";
  canonicalSessionLease: "released" | "active" | "unknown";
  reason?: string;
};

async function readJson(file: string): Promise<JsonRead> {
  try {
    const parsed = JSON.parse(await readFile(file, "utf8")) as unknown;
    return record(parsed) ? { kind: "value", value: parsed } : { kind: "malformed" };
  } catch (error) {
    if (record(error) && error.code === "ENOENT") return { kind: "missing" };
    return { kind: "malformed" };
  }
}

function statusMatchesReceipt(status: JsonRecord | undefined, receipt: DispatchReceipt): status is JsonRecord {
  return Boolean(status)
    && status?.lifecycleArtifactVersion === 3
    && status.runId === receipt.runId
    && status.cwd === receipt.expected.cwd
    && status.launchContractDigest === receipt.runtime.launchContractDigest;
}

function executionFrom(status: JsonRecord | undefined, receipt: DispatchReceipt): "running" | "complete" | "failed" | "stopped" | "unknown" {
  if (!statusMatchesReceipt(status, receipt)) return "unknown";
  if (status.state === "queued" || status.state === "running") return "running";
  if (status.state === "complete" || status.state === "completed") return "complete";
  if (status.state === "failed") return "failed";
  if (status.state === "stopped") return "stopped";
  return "unknown";
}

function validInstance(value: unknown): boolean {
  if (!record(value) || (value.kind !== "runner" && value.kind !== "pi-writer")
    || typeof value.processInstanceId !== "string" || !value.processInstanceId
    || typeof value.closeObservedAt !== "number" || !Number.isFinite(value.closeObservedAt)
    || (typeof value.exitCode !== "number" && value.exitCode !== null)
    || (typeof value.signal !== "string" && value.signal !== null)) return false;
  return value.kind === "runner"
    ? value.attempt === undefined
    : Number.isInteger(value.attempt) && (value.attempt as number) >= 0;
}

function proofProjection(proof: unknown, runId: string): EvidenceProjection {
  if (!record(proof) || proof.version !== 1 || typeof proof.runId !== "string"
    || typeof proof.runnerProcessInstanceId !== "string" || !proof.runnerProcessInstanceId) {
    return { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "process-terminal-malformed" };
  }
  if (proof.runId !== runId) {
    return { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "process-terminal-mismatch" };
  }
  if (proof.state === "pending" || proof.state === "not-started") {
    return {
      processTerminal: "unknown",
      canonicalSessionLease: "unknown",
      reason: proof.state === "pending" ? "process-terminal-pending" : "process-terminal-not-started",
    };
  }
  if (proof.state === "unknown") {
    if (typeof proof.reason !== "string" || !proof.reason) {
      return { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "process-terminal-malformed" };
    }
    return {
      processTerminal: "unknown",
      canonicalSessionLease: proof.reason === "canonical-session-lease-active" ? "active" : "unknown",
      reason: proof.reason,
    };
  }
  if (proof.state !== "observed" || typeof proof.observedAt !== "number" || !Number.isFinite(proof.observedAt)
    || !Array.isArray(proof.instances) || !proof.instances.every(validInstance)
    || !proof.instances.some((entry) => record(entry) && entry.kind === "runner"
      && entry.processInstanceId === proof.runnerProcessInstanceId)) {
    return { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "process-terminal-malformed" };
  }
  let canonicalSessionLease: "released" | "unknown" = "unknown";
  if (proof.canonicalSession !== undefined) {
    const session = proof.canonicalSession;
    const validSession = record(session)
      && Object.keys(session).every((key) => [
        "canonicalSessionId",
        "leaseDisposition",
        "freeAtObservation",
        "canonicalSessionLeaseReleased",
      ].includes(key))
      && typeof session.canonicalSessionId === "string"
      && Boolean(session.canonicalSessionId.trim())
      && session.freeAtObservation === true
      && (session.leaseDisposition === "released" || session.leaseDisposition === "not-held")
      && (session.canonicalSessionLeaseReleased === undefined || session.canonicalSessionLeaseReleased === true);
    if (!validSession) {
      return { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "process-terminal-malformed" };
    }
    canonicalSessionLease = "released";
  }
  return { processTerminal: "observed", canonicalSessionLease };
}

async function projectEvidence(receipt: DispatchReceipt, eventWoke = false): Promise<JsonRecord> {
  const [statusRead, sidecarRead] = await Promise.all([readJson(receipt.statusPath), readJson(receipt.processTerminalPath)]);
  const status = statusRead.kind === "value" ? statusRead.value : undefined;
  let projection: EvidenceProjection;
  let evidenceSource: "sidecar" | "status" | "event" | "none";
  if (sidecarRead.kind === "malformed") {
    projection = { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "process-terminal-malformed" };
    evidenceSource = "sidecar";
  } else if (sidecarRead.kind === "value") {
    projection = proofProjection(sidecarRead.value, receipt.runId);
    evidenceSource = "sidecar";
  } else if (statusRead.kind === "malformed") {
    projection = { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "status-malformed" };
    evidenceSource = "status";
  } else if (status && !statusMatchesReceipt(status, receipt)) {
    projection = { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "status-mismatch" };
    evidenceSource = "status";
  } else if (status && status.processTerminal !== undefined) {
    projection = proofProjection(status.processTerminal, receipt.runId);
    evidenceSource = "status";
  } else {
    projection = { processTerminal: "unknown", canonicalSessionLease: "unknown", reason: "process-terminal-proof-unavailable" };
    evidenceSource = eventWoke ? "event" : "none";
  }
  return {
    version: 1,
    runId: receipt.runId,
    execution: executionFrom(status, receipt),
    processTerminal: projection.processTerminal,
    canonicalSessionLease: projection.canonicalSessionLease,
    evidenceSource,
    ...(projection.reason ? { reason: projection.reason } : {}),
  };
}

interface ProcessEventWaiter {
  result: Promise<boolean>;
  cancel(): void;
}

function waitForProcessEvent(bus: EventBus, runId: string, waitMs: number, signal?: AbortSignal): ProcessEventWaiter {
  let cancel = () => {};
  const result = new Promise<boolean>((resolve, reject) => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout>;
    let off: (() => void) | void;
    const finish = (woke: boolean, error?: AdapterError) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (typeof off === "function") off();
      signal?.removeEventListener("abort", onAbort);
      if (error) reject(error);
      else resolve(woke);
    };
    const onAbort = () => finish(false, new AdapterError("aborted", "Attestation wait was aborted."));
    off = bus.on(PROCESS_TERMINAL_EVENT, (payload: unknown) => {
      if (record(payload) && typeof payload.runId === "string" && payload.runId === runId) finish(true);
    });
    timer = setTimeout(() => finish(false), waitMs);
    signal?.addEventListener("abort", onAbort, { once: true });
    cancel = () => finish(false);
  });
  return { result, cancel };
}

async function attest(
  bus: EventBus,
  earlyEventWakes: BoundedRunIds,
  request: AttestRequest,
  signal?: AbortSignal,
): Promise<JsonRecord> {
  let projected = await projectEvidence(request.receipt);
  if (projected.processTerminal === "observed" || request.waitMs === undefined) return projected;
  if (signal?.aborted) throw new AdapterError("aborted", "Attestation wait was aborted.");
  if (earlyEventWakes.consume(request.receipt.runId)) return projectEvidence(request.receipt, true);
  if (signal?.aborted) throw new AdapterError("aborted", "Attestation wait was aborted.");
  const waiting = waitForProcessEvent(bus, request.receipt.runId, request.waitMs, signal);
  void waiting.result.catch(() => {});
  // Close the subscribe/read race: durable evidence may have landed immediately
  // before the event listener was installed.
  projected = await projectEvidence(request.receipt);
  if (projected.processTerminal === "observed") {
    waiting.cancel();
    await waiting.result;
    return projected;
  }
  const eventWoke = await waiting.result;
  return projectEvidence(request.receipt, eventWoke);
}

function success(details: JsonRecord) {
  return { content: [{ type: "text" as const, text: JSON.stringify(details) }], details };
}

function failure(error: unknown) {
  const adapted = error instanceof AdapterError ? error : new AdapterError("internal_error", error instanceof Error ? error.message : String(error));
  const details = { version: 1, error: { code: adapted.code, message: adapted.message, ...adapted.extra } };
  return { content: [{ type: "text" as const, text: JSON.stringify(details) }], details, isError: true };
}

const StringArray = Type.Array(Type.String({ minLength: 1 }));
const ExpectedSchema = Type.Object({
  cwd: Type.String({ minLength: 1 }),
  gitRoot: Type.String({ minLength: 1 }),
  gitCommonDir: Type.String({ minLength: 1 }),
  branch: Type.String({ minLength: 1 }),
  head: Type.String({ minLength: 1 }),
  clean: Type.Literal(true),
  primaryDirt: StringArray,
}, { additionalProperties: false });
const ContractSchema = Type.Object({
  objective: Type.String({ minLength: 1 }),
  writeScope: StringArray,
  immutablePaths: StringArray,
  focusedCommands: StringArray,
  evidence: StringArray,
  stopConditions: StringArray,
}, { additionalProperties: false });
const ReceiptExpectedSchema = Type.Object({
  cwd: Type.String({ minLength: 1 }),
  gitRoot: Type.String({ minLength: 1 }),
  gitCommonDir: Type.String({ minLength: 1 }),
  branch: Type.String({ minLength: 1 }),
  initialHead: Type.String({ pattern: "^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$" }),
}, { additionalProperties: false });
const ReceiptRuntimeSchema = Type.Object({
  rpcVersion: Type.Literal(1),
  processTerminalVersion: Type.Literal(1),
  lifecycleArtifactVersion: Type.Literal(3),
  launchContractDigest: Type.String({ pattern: "^[0-9a-fA-F]{64}$" }),
  hostSessionId: Type.Optional(Type.String({ minLength: 1 })),
}, { additionalProperties: false });
const ReceiptSchema = Type.Object({
  version: Type.Literal(1),
  requestId: Type.String({ pattern: "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$" }),
  runId: Type.String({ minLength: 1 }),
  asyncDir: Type.String({ minLength: 1 }),
  statusPath: Type.String({ minLength: 1 }),
  processTerminalPath: Type.String({ minLength: 1 }),
  expected: ReceiptExpectedSchema,
  runtime: ReceiptRuntimeSchema,
}, { additionalProperties: false });
const ParametersSchema = Type.Object({
  version: Type.Literal(1),
  action: StringEnum(["dispatch-lane", "attest-run"] as const),
  taskId: Type.Optional(Type.String({ minLength: 1 })),
  laneId: Type.Optional(Type.String({ minLength: 1 })),
  subjectSha: Type.Optional(Type.String({ pattern: "^[0-9a-f]{40,64}$" })),
  expected: Type.Optional(ExpectedSchema),
  contract: Type.Optional(ContractSchema),
  timeoutMs: Type.Optional(Type.Integer({ minimum: 1, maximum: MAX_RUN_TIMEOUT_MS })),
  receipt: Type.Optional(ReceiptSchema),
  waitMs: Type.Optional(Type.Integer({ minimum: 1, maximum: MAX_ATTEST_WAIT_MS })),
}, { additionalProperties: false });

export default function orchestratePi(pi: ExtensionAPI) {
  const earlyEventWakes = new BoundedRunIds(MAX_EARLY_EVENT_WAKES);
  pi.registerTool({
    name: "orchestrate_pi",
    label: "Orchestrate Pi",
    description: "Dispatch one admitted Pi lane or attest its exact runtime evidence. Fails closed; never collects or mutates Git.",
    parameters: ParametersSchema,
    async execute(_toolCallId, raw, signal, _onUpdate, ctx) {
      try {
        const request = parseRequest(raw);
        return success(request.action === "dispatch-lane"
          ? await dispatch(pi.events, earlyEventWakes, request, ctx, signal)
          : await attest(pi.events, earlyEventWakes, request, signal));
      } catch (error) {
        return failure(error);
      }
    },
  });
}
