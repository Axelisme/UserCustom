import { constants as fsConstants } from "node:fs";
import { lstat, mkdir, open, readFile, readdir, unlink, link } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { isValidStructuredOutput } from "./result-schema.ts";

export const REPORT_VERSION = 1;

export const FEEDBACK_VERSION = 1;

const SAFE_IDENTIFIER = /^[a-z0-9][a-z0-9._-]*$/;
const DEV_FLOW_TICKET = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const WORKFLOW_KEY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

function isSafeIdentifier(v: string): boolean { return SAFE_IDENTIFIER.test(v); }
function isSafeTicket(v: string): boolean { return DEV_FLOW_TICKET.test(v); }
function isUuid(v: string): boolean { return UUID_PATTERN.test(v); }
function isWorkflowKey(v: string): boolean { return WORKFLOW_KEY_PATTERN.test(v); }

export function roleForWorkflowKey(key: string): string {
  if (key === "impl-0") return "implementer";
  if (key.startsWith("impl-")) return "correction";
  if (key === "review-0") return "acceptor";
  if (key.startsWith("review-")) return "rereview";
  return "unknown";
}

async function pathMetadata(p: string) {
  try { return await lstat(p); } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "ENOENT" || err.code === "ENOTDIR") return null;
    throw e;
  }
}

function boundedMessage(value: unknown): string {
  const m = value instanceof Error ? value.message : typeof value === "string" ? value : "unknown error";
  return m.replace(/[\r\n]+/g, " ").slice(0, 300);
}

function unicodeLength(value: string): number {
  return [...value].length;
}

async function isAncestrySafe(repoControlRoot: string, targetPath: string): Promise<boolean> {
  const trusted = (() => {
    const r = path.resolve(repoControlRoot);
    const t = path.resolve(targetPath);
    if (t === r || t.startsWith(r + path.sep)) return r;
    return path.parse(t).root;
  })();
  const rel = path.relative(trusted, path.resolve(targetPath));
  if (rel.startsWith("..") || path.isAbsolute(rel)) return false;
  const parts = rel.split(path.sep).filter(Boolean);
  let cur = trusted;
  for (const part of parts) {
    cur = path.join(cur, part);
    const meta = await pathMetadata(cur);
    if (meta?.isSymbolicLink()) return false;
  }
  return true;
}

async function ensureSafeDir(repoControlRoot: string, dirPath: string): Promise<boolean> {
  const trusted = (() => {
    const r = path.resolve(repoControlRoot);
    const t = path.resolve(dirPath);
    if (t === r || t.startsWith(r + path.sep)) return r;
    return path.parse(t).root;
  })();
  const rel = path.relative(trusted, path.resolve(dirPath));
  if (rel.startsWith("..") || path.isAbsolute(rel)) return false;
  const parts = rel.split(path.sep).filter(Boolean);
  let cur = trusted;
  for (const part of parts) {
    cur = path.join(cur, part);
    const meta = await pathMetadata(cur);
    if (meta === null) {
      try {
        await mkdir(cur, { mode: 0o700 });
      } catch (e) {
        const err = e as NodeJS.ErrnoException;
        if (err.code === "EEXIST") {
          const after = await pathMetadata(cur);
          if (!after?.isDirectory() || after.isSymbolicLink()) return false;
          continue;
        }
        return false;
      }
      const after = await pathMetadata(cur);
      if (!after?.isDirectory() || after.isSymbolicLink()) return false;
    } else {
      if (meta.isSymbolicLink()) return false;
      if (!meta.isDirectory()) return false;
    }
  }
  return true;
}

async function resolveTaskContainer(repoControlRoot: string, taskId: string): Promise<{ container: string | null; warning: string | null }> {
  const plans = path.join(repoControlRoot, ".agent_state", "plans", taskId);
  const archives = path.join(repoControlRoot, ".agent_state", "archives", taskId);
  const plansSafe = await isAncestrySafe(repoControlRoot, plans);
  const archivesSafe = await isAncestrySafe(repoControlRoot, archives);
  const plansMeta = plansSafe ? await pathMetadata(plans) : null;
  const archivesMeta = archivesSafe ? await pathMetadata(archives) : null;
  const plansIsDir = plansMeta?.isDirectory() === true && !plansMeta.isSymbolicLink();
  const archivesIsDir = archivesMeta?.isDirectory() === true && !archivesMeta.isSymbolicLink();
  if (plansIsDir && !archivesIsDir) return { container: plans, warning: null };
  if (!plansIsDir && archivesIsDir) return { container: archives, warning: null };
  if (plansIsDir && archivesIsDir) return { container: null, warning: `ambiguous task container for ${taskId}` };
  return { container: null, warning: `missing task container for ${taskId}` };
}

async function emitOperationWarning(_repoControlRoot: string, message: string): Promise<void> {
  const bounded = boundedMessage(message).slice(0, 500);
  try { console.warn(`[collab-report] ${bounded}`); } catch {}
}

async function appendWarning(repoControlRoot: string, sink: { taskId: string; laneId: string; workflowId: string; workflowKey: string; childRunId: string; message: string; }): Promise<string> {
  const { taskId, laneId } = sink;
  if (!isSafeIdentifier(taskId) || !isSafeIdentifier(laneId)) {
    const msg = `lane_loop_report warning sink is unsafe for ${taskId}/${laneId}: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const resolved = await resolveTaskContainer(repoControlRoot, taskId);
  if (!resolved.container) {
    const msg = `${resolved.warning}: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const container = resolved.container;
  const warningsDir = path.join(container, ".collab_op", "lane_loop_report");
  const warningsFile = path.join(warningsDir, "warnings.jsonl");
  if (path.resolve(warningsFile) !== path.resolve(container) && !path.resolve(warningsFile).startsWith(path.resolve(container) + path.sep)) {
    const msg = `lane_loop_report warning sink escapes container: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  if (!(await isAncestrySafe(repoControlRoot, warningsDir)) || !(await isAncestrySafe(repoControlRoot, warningsFile))) {
    const msg = `lane_loop_report warning sink ancestry is unsafe: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const dirMeta = await pathMetadata(warningsDir);
  if (dirMeta !== null && !dirMeta.isDirectory()) {
    const msg = `lane_loop_report warnings sink is not a directory: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const fileMeta = await pathMetadata(warningsFile);
  if (fileMeta !== null && (!fileMeta.isFile() || fileMeta.isSymbolicLink())) {
    const msg = `lane_loop_report warnings sink is not a regular file: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  if (!(await ensureSafeDir(repoControlRoot, warningsDir))) {
    const msg = `lane_loop_report warnings sink is not a directory after create: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const afterMeta = await pathMetadata(warningsDir);
  if (!afterMeta?.isDirectory() || afterMeta.isSymbolicLink()) {
    const msg = `lane_loop_report warnings sink is not a directory after create: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  try {
    const handle = await open(warningsFile, fsConstants.O_APPEND | fsConstants.O_CREAT | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW, 0o600);
    try {
      const record = { at: new Date().toISOString(), taskId: sink.taskId, laneId: sink.laneId, workflowId: sink.workflowId, workflowKey: sink.workflowKey, childRunId: sink.childRunId, message: boundedMessage(sink.message).slice(0, 500) };
      await handle.writeFile(`${JSON.stringify(record)}\n`, { encoding: "utf8" });
    } finally { await handle.close(); }
    return boundedMessage(sink.message).slice(0, 500);
  } catch (e) {
    const msg = `lane_loop_report warning append failed: ${boundedMessage(e)}: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
}

async function appendFeedbackWarning(repoControlRoot: string, sink: { taskId: string; laneId: string; workflowId: string; workflowKey: string; childRunId: string; message: string; }): Promise<string> {
  const { taskId, laneId } = sink;
  if (!isSafeIdentifier(taskId) || !isSafeIdentifier(laneId)) {
    const msg = `lane_loop_feedback warning sink is unsafe for ${taskId}/${laneId}: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const resolved = await resolveTaskContainer(repoControlRoot, taskId);
  if (!resolved.container) {
    const msg = `${resolved.warning}: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const container = resolved.container;
  const warningsDir = path.join(container, ".collab_op", "lane_loop_feedback");
  const warningsFile = path.join(warningsDir, "warnings.jsonl");
  if (path.resolve(warningsFile) !== path.resolve(container) && !path.resolve(warningsFile).startsWith(path.resolve(container) + path.sep)) {
    const msg = `lane_loop_feedback warning sink escapes container: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  if (!(await isAncestrySafe(repoControlRoot, warningsDir)) || !(await isAncestrySafe(repoControlRoot, warningsFile))) {
    const msg = `lane_loop_feedback warning sink ancestry is unsafe: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const dirMeta = await pathMetadata(warningsDir);
  if (dirMeta !== null && !dirMeta.isDirectory()) {
    const msg = `lane_loop_feedback warnings sink is not a directory: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const fileMeta = await pathMetadata(warningsFile);
  if (fileMeta !== null && (!fileMeta.isFile() || fileMeta.isSymbolicLink())) {
    const msg = `lane_loop_feedback warnings sink is not a regular file: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  if (!(await ensureSafeDir(repoControlRoot, warningsDir))) {
    const msg = `lane_loop_feedback warnings sink is not a directory after create: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  const afterMeta = await pathMetadata(warningsDir);
  if (!afterMeta?.isDirectory() || afterMeta.isSymbolicLink()) {
    const msg = `lane_loop_feedback warnings sink is not a directory after create: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
  // Deduplicate identical attributable feedback warnings by stable identity (task/lane/workflow/key/child/message).
  try {
    const existingMeta = await pathMetadata(warningsFile);
    if (existingMeta?.isFile() && !existingMeta.isSymbolicLink()) {
      try {
        const existingContent = await readFile(warningsFile, "utf8");
        const boundedMsg = boundedMessage(sink.message).slice(0, 500);
        for (const line of existingContent.split("\n")) {
          if (!line.trim()) continue;
          try {
            const rec = JSON.parse(line) as Record<string, unknown>;
            if (rec["taskId"] === sink.taskId && rec["laneId"] === sink.laneId && rec["workflowId"] === sink.workflowId && rec["workflowKey"] === sink.workflowKey && rec["childRunId"] === sink.childRunId && rec["message"] === boundedMsg) {
              return boundedMsg;
            }
          } catch {}
        }
      } catch {}
    }
  } catch {}
  try {
    const handle = await open(warningsFile, fsConstants.O_APPEND | fsConstants.O_CREAT | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW, 0o600);
    try {
      const record = { at: new Date().toISOString(), taskId: sink.taskId, laneId: sink.laneId, workflowId: sink.workflowId, workflowKey: sink.workflowKey, childRunId: sink.childRunId, message: boundedMessage(sink.message).slice(0, 500) };
      await handle.writeFile(`${JSON.stringify(record)}\n`, { encoding: "utf8" });
    } finally { await handle.close(); }
    return boundedMessage(sink.message).slice(0, 500);
  } catch (e) {
    const msg = `lane_loop_feedback warning append failed: ${boundedMessage(e)}: ${boundedMessage(sink.message)}`;
    await emitOperationWarning(repoControlRoot, msg);
    return msg;
  }
}

async function readEfficiencyFeedbackValue(statusObj: Record<string, unknown>, workflowId: string, workflowKey: string, childRunId: string, lanePath: string): Promise<{ found: boolean; value?: unknown; warning?: string }> {
  // Single correlated step resolution owns workflowId, workflowKey, childRunId, terminal status and lane/session identity.
  try {
    correlateArtifacts({ statusObj, workflowId, workflowKey, childRunId, lanePath });
  } catch (e) {
    return { found: false, warning: `derivation failed for ${workflowKey}/${childRunId}: ${boundedMessage(e)}` };
  }
  const steps = Array.isArray((statusObj as { steps?: unknown }).steps) ? (statusObj as { steps: Array<Record<string, unknown>> }).steps : [];
  const terminalStatuses = new Set(["complete", "completed", "failed", "stopped", "paused"]);
  const matching = steps.filter(s => {
    if (s["workflowKey"] !== workflowKey || s["parentWorkflowRunId"] !== workflowId || typeof s["status"] !== "string" || !terminalStatuses.has(s["status"] as string)) return false;
    // Correlate childRunId via sessionFile segment and optional runId field.
    const runId = s["runId"];
    if (typeof runId === "string" && runId !== childRunId) return false;
    const sessionFile = s["sessionFile"];
    if (typeof sessionFile === "string") {
      const segs = path.resolve(sessionFile as string).split(path.sep);
      if (!segs.includes(childRunId)) return false;
    }
    return true;
  });
  if (matching.length !== 1) return { found: false };
  const step = matching[0];
  if (step["structuredOutput"] !== undefined && step["structuredOutput"] !== null && typeof step["structuredOutput"] === "object" && !Array.isArray(step["structuredOutput"])) {
    const out = step["structuredOutput"] as Record<string, unknown>;
    if (!("efficiencyFeedback" in out)) return { found: false };
    if (!isValidStructuredOutput(workflowKey, out)) {
      const fbVal = out["efficiencyFeedback"];
      if (typeof fbVal !== "string") return { found: false, warning: `efficiencyFeedback is not a string for ${workflowKey}/${childRunId}` };
      if (unicodeLength(fbVal as string) > 10000) return { found: false, warning: `efficiencyFeedback exceeds maxLength 10000 for ${workflowKey}/${childRunId}` };
      return { found: false, warning: `structured output validation failed for ${workflowKey}/${childRunId}` };
    }
    return { found: true, value: out["efficiencyFeedback"] };
  }
  return { found: false };
}

function correlateArtifacts(input: { statusObj: Record<string, unknown>; workflowId: string; workflowKey: string; childRunId: string; lanePath: string; }): { agentDurationMs: number; turnCount: number; sessionFile: string } {
  const { statusObj, workflowId, workflowKey, childRunId, lanePath } = input;
  const status = statusObj as { runId?: unknown; cwd?: unknown; workflow?: unknown; steps?: unknown };
  if (status.runId !== workflowId) throw new Error(`status runId ${String(status.runId)} does not match workflowId ${workflowId}`);
  const cwdRaw = (statusObj as { cwd?: unknown }).cwd;
  if (typeof cwdRaw !== "string") throw new Error("status missing cwd");
  const normCwd = path.resolve(cwdRaw);
  const normLane = path.resolve(lanePath);
  if (normCwd !== normLane) throw new Error(`lane identity mismatch: cwd ${normCwd} != lanePath ${normLane}`);
  const workflow = status.workflow as { trace?: unknown } | undefined;
  if (!workflow || !Array.isArray(workflow.trace)) throw new Error("missing workflow trace");
  const trace = workflow.trace as Array<Record<string, unknown>>;
  const matchingTrace = trace.filter(t => t["key"] === workflowKey && t["runId"] === childRunId);
  if (matchingTrace.length === 0) throw new Error(`trace entry not found for workflowKey ${workflowKey} childRunId ${childRunId}`);
  if (matchingTrace.length > 1) throw new Error(`duplicate trace entries for workflowKey ${workflowKey} childRunId ${childRunId}`);
  const traceEntry = matchingTrace[0];
  const traceState = traceEntry["state"];
  if (traceState !== undefined && traceState !== "completed" && traceState !== "complete") throw new Error(`trace entry state is not completed: ${String(traceState)}`);
  const agentDurationMs = traceEntry["durationMs"];
  if (typeof agentDurationMs !== "number" || !Number.isFinite(agentDurationMs)) throw new Error("trace entry missing numeric durationMs");
  const steps = Array.isArray(status.steps) ? (status.steps as Array<Record<string, unknown>>) : null;
  if (!steps) throw new Error("missing steps");
  const terminalStatuses = new Set(["complete", "completed", "failed", "stopped", "paused"]);
  const matchingSteps = steps.filter(s => s["workflowKey"] === workflowKey && s["parentWorkflowRunId"] === workflowId && typeof s["status"] === "string" && terminalStatuses.has(s["status"] as string));
  if (matchingSteps.length === 0) throw new Error(`status step not found for workflowKey ${workflowKey} parent ${workflowId}`);
  if (matchingSteps.length > 1) throw new Error(`duplicate terminal steps for workflowKey ${workflowKey} parent ${workflowId}`);
  const step = matchingSteps[0];
  const sessionFile = step["sessionFile"];
  if (typeof sessionFile !== "string" || sessionFile.length === 0) throw new Error("step missing sessionFile");
  if (!path.isAbsolute(sessionFile)) throw new Error(`sessionFile is not absolute: ${sessionFile}`);
  const segs = path.resolve(sessionFile).split(path.sep);
  if (!segs.includes(childRunId)) throw new Error(`sessionFile does not contain childRunId segment ${childRunId}: ${sessionFile}`);
  const turnCount = step["turnCount"];
  if (typeof turnCount !== "number" || !Number.isFinite(turnCount)) throw new Error("step missing numeric turnCount");
  return { agentDurationMs, turnCount, sessionFile: sessionFile as string };
}

export function deriveReportFromArtifacts(input: { taskId: string; ticketId: string; laneId: string; workflowId: string; workflowKey: string; childRunId: string; lanePath: string; statusObj: Record<string, unknown>; sessionText: string; }): Record<string, unknown> {
  const { taskId, ticketId, laneId, workflowId, workflowKey, childRunId, lanePath, statusObj, sessionText } = input;
  if (!taskId || !ticketId || !laneId || !workflowId || !workflowKey || !childRunId) throw new Error("missing attribution identity");
  if (!isSafeIdentifier(taskId) || !isSafeTicket(ticketId) || !isSafeIdentifier(laneId)) throw new Error("unsafe attribution identifier");
  const isWorkflowIdSafe = isUuid(workflowId) || isSafeIdentifier(workflowId) || isSafeTicket(workflowId);
  const isChildRunIdSafe = isUuid(childRunId) || isSafeIdentifier(childRunId) || isSafeTicket(childRunId);
  if (!isWorkflowIdSafe || !isWorkflowKey(workflowKey) || !isChildRunIdSafe) throw new Error("unsafe workflow identifier");
  const { agentDurationMs, turnCount } = correlateArtifacts({ statusObj, workflowId, workflowKey, childRunId, lanePath });
  let tokens = 0;
  const tools: Record<string, { calls: number; succeeded: number; failed: number; observedDurationsMs: (number | null)[] }> = {};
  const pendingCalls = new Map<string, { name: string; startMs: number | null; index: number }>();
  let toolObservedDurationMs = 0;
  const lines = sessionText.split(/\r?\n/);
  for (const line of lines) {
    if (!line.trim()) continue;
    let obj: Record<string, unknown>;
    try { obj = JSON.parse(line); } catch { throw new Error("session contains invalid JSON"); }
    if (obj["type"] !== "message") continue;
    const message = obj["message"] as Record<string, unknown> | undefined;
    if (!message || typeof message !== "object") continue;
    const role = message["role"];
    if (role === "assistant") {
      const usage = message["usage"] as Record<string, unknown> | undefined;
      if (usage && typeof usage["totalTokens"] === "number") tokens += usage["totalTokens"] as number;
      const content = message["content"] as unknown[] | undefined;
      if (Array.isArray(content)) {
        for (const item of content) {
          if (item && typeof item === "object" && (item as Record<string, unknown>)["type"] === "toolCall") {
            const call = item as Record<string, unknown>;
            const id = call["id"];
            const name = call["name"];
            if (typeof id !== "string" || typeof name !== "string") continue;
            let startMs: number | null = null;
            const innerTs = message["timestamp"];
            if (typeof innerTs === "number" && Number.isFinite(innerTs)) startMs = innerTs;
            else if (typeof obj["timestamp"] === "string") { const p = Date.parse(obj["timestamp"] as string); if (Number.isFinite(p)) startMs = p; }
            if (!tools[name]) tools[name] = { calls: 0, succeeded: 0, failed: 0, observedDurationsMs: [] };
            const idx = tools[name].observedDurationsMs.length;
            tools[name].calls += 1;
            tools[name].observedDurationsMs.push(null);
            pendingCalls.set(id, { name, startMs, index: idx });
          }
        }
      }
    } else if (role === "toolResult") {
      const toolCallId = message["toolCallId"];
      if (typeof toolCallId !== "string") continue;
      const pending = pendingCalls.get(toolCallId);
      if (!pending) continue;
      let endMs: number | null = null;
      const innerTs = message["timestamp"];
      if (typeof innerTs === "number" && Number.isFinite(innerTs)) endMs = innerTs;
      else if (typeof obj["timestamp"] === "string") { const p = Date.parse(obj["timestamp"] as string); if (Number.isFinite(p)) endMs = p; }
      let duration: number | null = null;
      if (pending.startMs !== null && endMs !== null) {
        duration = endMs - pending.startMs;
        if (!Number.isFinite(duration) || duration < 0) duration = 0;
        toolObservedDurationMs += duration;
      }
      const entry = tools[pending.name];
      if (entry) {
        entry.observedDurationsMs[pending.index] = duration;
        if (message["isError"] !== true) entry.succeeded += 1;
        else entry.failed += 1;
      }
      pendingCalls.delete(toolCallId);
    }
  }
  for (const pend of pendingCalls.values()) {
    const e = tools[pend.name];
    if (e) e.failed += 1;
  }
  const role = roleForWorkflowKey(workflowKey);
  return { reportVersion: REPORT_VERSION, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, role, agentDurationMs, toolObservedDurationMs, turns: turnCount, tokens, tools };
}

export async function publishReport(params: { repoControlRoot: string; taskId: string; ticketId: string; laneId: string; workflowId: string; workflowKey: string; childRunId: string; lanePath: string; report: Record<string, unknown>; }): Promise<{ published: boolean; warning?: string; isDuplicate?: boolean }> {
  const { repoControlRoot, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, report } = params;
  const isWorkflowIdSafe = isUuid(workflowId) || isSafeIdentifier(workflowId) || isSafeTicket(workflowId);
  const isChildRunIdSafe = isUuid(childRunId) || isSafeIdentifier(childRunId) || isSafeTicket(childRunId);
  if (!isSafeIdentifier(taskId) || !isSafeTicket(ticketId) || !isSafeIdentifier(laneId) || !isWorkflowIdSafe || !isWorkflowKey(workflowKey) || !isChildRunIdSafe) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `unsafe identities for report ${taskId}/${laneId}/${childRunId}` });
    return { published: false, warning };
  }
  const resolved = await resolveTaskContainer(repoControlRoot, taskId);
  if (!resolved.container) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: resolved.warning! });
    return { published: false, warning };
  }
  const container = resolved.container;
  const reportDir = path.join(container, ".collab_op", "lane_loop_report", laneId);
  const reportPath = path.join(reportDir, `${childRunId}.json`);
  if (path.resolve(reportPath) !== path.resolve(container) && !path.resolve(reportPath).startsWith(path.resolve(container) + path.sep)) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `report path escapes container` });
    return { published: false, warning };
  }
  if (!(await isAncestrySafe(repoControlRoot, reportDir)) || !(await isAncestrySafe(repoControlRoot, reportPath))) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `report path ancestry is unsafe: ${reportPath}` });
    return { published: false, warning };
  }
  const existingMeta = await pathMetadata(reportPath);
  if (existingMeta !== null && (!existingMeta.isFile() || existingMeta.isSymbolicLink())) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `report destination is not a regular file: ${reportPath}` });
    return { published: false, warning };
  }
  const reportContent = `${JSON.stringify(report)}\n`;
  if (!(await ensureSafeDir(repoControlRoot, reportDir))) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `could not create report directory: ancestry unsafe ${reportDir}` });
    return { published: false, warning };
  }
  const dirMeta = await pathMetadata(reportDir);
  if (!dirMeta?.isDirectory() || dirMeta.isSymbolicLink()) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `report directory is not a directory` });
    return { published: false, warning };
  }
  const tmpName = `${childRunId}.tmp.${process.pid}.${randomUUID()}`;
  const tmpPath = path.join(reportDir, tmpName);
  try {
    const handle = await open(tmpPath, fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW, 0o600);
    try { await handle.writeFile(reportContent, { encoding: "utf8" }); } finally { await handle.close(); }
  } catch (e) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `could not write temporary report: ${boundedMessage(e)}` });
    return { published: false, warning };
  }
  try {
    await link(tmpPath, reportPath);
    try { await unlink(tmpPath); } catch {}
    return { published: true };
  } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "EEXIST") {
      try {
        const existingContent = await readFile(reportPath, "utf8");
        if (existingContent === reportContent) { try { await unlink(tmpPath); } catch {} return { published: false, isDuplicate: true }; }
        try { await unlink(tmpPath); } catch {}
        const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `report collision for ${laneId}/${childRunId}: different content exists` });
        return { published: false, warning };
      } catch (readErr) {
        try { await unlink(tmpPath); } catch {}
        const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `could not compare existing report: ${boundedMessage(readErr)}` });
        return { published: false, warning };
      }
    }
    try { await unlink(tmpPath); } catch {}
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `could not install report: ${boundedMessage(e)}` });
    return { published: false, warning };
  }
}

export async function publishFeedback(params: { repoControlRoot: string; taskId: string; ticketId: string; laneId: string; workflowId: string; workflowKey: string; childRunId: string; lanePath: string; efficiencyFeedback: string; }): Promise<{ published: boolean; warning?: string; isDuplicate?: boolean }> {
  const { repoControlRoot, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, efficiencyFeedback } = params;
  const isWorkflowIdSafe = isUuid(workflowId) || isSafeIdentifier(workflowId) || isSafeTicket(workflowId);
  const isChildRunIdSafe = isUuid(childRunId) || isSafeIdentifier(childRunId) || isSafeTicket(childRunId);
  if (!isSafeIdentifier(taskId) || !isSafeTicket(ticketId) || !isSafeIdentifier(laneId) || !isWorkflowIdSafe || !isWorkflowKey(workflowKey) || !isChildRunIdSafe) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `unsafe identities for feedback ${taskId}/${laneId}/${childRunId}` });
    return { published: false, warning };
  }
  if (typeof efficiencyFeedback !== "string" || unicodeLength(efficiencyFeedback) > 10000) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `feedback value is not a valid string of at most 10000 characters for ${taskId}/${laneId}/${childRunId}` });
    return { published: false, warning };
  }
  const resolved = await resolveTaskContainer(repoControlRoot, taskId);
  if (!resolved.container) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: resolved.warning! });
    return { published: false, warning };
  }
  const container = resolved.container;
  const feedbackDir = path.join(container, ".collab_op", "lane_loop_feedback", laneId);
  const feedbackPath = path.join(feedbackDir, `${childRunId}.json`);
  if (path.resolve(feedbackPath) !== path.resolve(container) && !path.resolve(feedbackPath).startsWith(path.resolve(container) + path.sep)) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `feedback path escapes container` });
    return { published: false, warning };
  }
  if (!(await isAncestrySafe(repoControlRoot, feedbackDir)) || !(await isAncestrySafe(repoControlRoot, feedbackPath))) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `feedback path ancestry is unsafe: ${feedbackPath}` });
    return { published: false, warning };
  }
  const existingMeta = await pathMetadata(feedbackPath);
  if (existingMeta !== null && (!existingMeta.isFile() || existingMeta.isSymbolicLink())) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `feedback destination is not a regular file: ${feedbackPath}` });
    return { published: false, warning };
  }
  const role = roleForWorkflowKey(workflowKey);
  const payload: Record<string, unknown> = { feedbackVersion: FEEDBACK_VERSION, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, role, efficiencyFeedback };
  const content = `${JSON.stringify(payload)}\n`;
  if (!(await ensureSafeDir(repoControlRoot, feedbackDir))) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `could not create feedback directory: ancestry unsafe ${feedbackDir}` });
    return { published: false, warning };
  }
  const dirMeta = await pathMetadata(feedbackDir);
  if (!dirMeta?.isDirectory() || dirMeta.isSymbolicLink()) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `feedback directory is not a directory` });
    return { published: false, warning };
  }
  const tmpName = `${childRunId}.tmp.${process.pid}.${randomUUID()}`;
  const tmpPath = path.join(feedbackDir, tmpName);
  try {
    const handle = await open(tmpPath, fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW, 0o600);
    try { await handle.writeFile(content, { encoding: "utf8" }); } finally { await handle.close(); }
  } catch (e) {
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `could not write temporary feedback: ${boundedMessage(e)}` });
    return { published: false, warning };
  }
  try {
    await link(tmpPath, feedbackPath);
    try { await unlink(tmpPath); } catch {}
    return { published: true };
  } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "EEXIST") {
      try {
        const existingContent = await readFile(feedbackPath, "utf8");
        if (existingContent === content) { try { await unlink(tmpPath); } catch {} return { published: false, isDuplicate: true }; }
        try { await unlink(tmpPath); } catch {}
        const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `feedback collision for ${laneId}/${childRunId}: different content exists` });
        return { published: false, warning };
      } catch (readErr) {
        try { await unlink(tmpPath); } catch {}
        const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `could not compare existing feedback: ${boundedMessage(readErr)}` });
        return { published: false, warning };
      }
    }
    try { await unlink(tmpPath); } catch {}
    const warning = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `could not install feedback: ${boundedMessage(e)}` });
    return { published: false, warning };
  }
}

export async function handleReviewedLaneCompletion(input: { repoControlRoot: string; taskId: string; ticketId: string; laneId: string; lanePath: string; workflowId: string; asyncDir: string; eventWorkflowId: string; eventAsyncDir: string; }): Promise<{ handled: boolean; published: string[]; warnings: string[]; ignoredReason?: string }> {
  const { repoControlRoot, taskId, ticketId, laneId, lanePath, workflowId, asyncDir, eventWorkflowId, eventAsyncDir } = input;
  if (eventWorkflowId !== workflowId || eventAsyncDir !== asyncDir) return { handled: false, published: [], warnings: [], ignoredReason: "partial or unrelated completion event" };
  const statusPath = path.join(asyncDir, "status.json");
  if (!(await isAncestrySafe(repoControlRoot, statusPath))) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message: `status path ancestry is unsafe at ${statusPath}` });
    return { handled: true, published: [], warnings: [warning], ignoredReason: "unsafe status ancestry" };
  }
  const statusMeta = await pathMetadata(statusPath);
  if (!statusMeta?.isFile() || statusMeta.isSymbolicLink()) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message: `status artifact is not a regular file at ${statusPath}` });
    return { handled: true, published: [], warnings: [warning], ignoredReason: "unsafe status artifact" };
  }
  let statusText: string;
  try { statusText = await readFile(statusPath, "utf8"); } catch (e) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message: `missing status artifact at ${statusPath}: ${boundedMessage(e)}` });
    return { handled: true, published: [], warnings: [warning], ignoredReason: "missing status" };
  }
  let statusObj: Record<string, unknown>;
  try { statusObj = JSON.parse(statusText); } catch (e) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message: `invalid status JSON: ${boundedMessage(e)}` });
    return { handled: true, published: [], warnings: [warning], ignoredReason: "invalid status json" };
  }
  const state = (statusObj as { state?: unknown }).state;
  if (state !== "complete" && state !== "failed" && state !== "stopped") {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message: `exact completion event has nonterminal status state ${String(state)}` });
    return { handled: true, published: [], warnings: [warning], ignoredReason: "nonterminal status artifact" };
  }
  const workflow = (statusObj as { workflow?: unknown }).workflow as { trace?: unknown } | undefined;
  const trace = workflow?.trace as Array<Record<string, unknown>> | undefined;
  if (!Array.isArray(trace) || trace.length === 0) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message: `missing workflow trace for ${workflowId}` });
    return { handled: true, published: [], warnings: [warning] };
  }
  const seen = new Map<string, { workflowKey: string; childRunId: string }>();
  for (const entry of trace) {
    const workflowKey = entry["key"];
    const childRunId = entry["runId"];
    if (typeof workflowKey !== "string" || typeof childRunId !== "string") continue;
    if (!/^impl-/.test(workflowKey) && !/^review-/.test(workflowKey)) continue;
    const key = `${workflowKey}\0${childRunId}`;
    if (!seen.has(key)) seen.set(key, { workflowKey, childRunId });
  }
  const published: string[] = [];
  const warnings: string[] = [];
  for (const { workflowKey, childRunId } of seen.values()) {
    let sessionFile: string;
    try {
      const corr = correlateArtifacts({ statusObj, workflowId, workflowKey, childRunId, lanePath });
      sessionFile = corr.sessionFile;
    } catch (e) {
      const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `derivation failed for ${workflowKey}/${childRunId}: ${boundedMessage(e)}` });
      warnings.push(warning);
      continue;
    }
    {
      if (!(await isAncestrySafe(repoControlRoot, sessionFile))) {
        const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `session file ancestry is unsafe for ${workflowKey} at ${sessionFile}` });
        warnings.push(warning);
      } else {
        const sessMeta = await pathMetadata(sessionFile);
        if (!sessMeta?.isFile()) {
          const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `session file is not a regular file for ${workflowKey} at ${sessionFile}` });
          warnings.push(warning);
        } else if (sessMeta.isSymbolicLink()) {
          const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `session file is a symlink for ${workflowKey} at ${sessionFile}` });
          warnings.push(warning);
        } else {
          let sessionText: string | null = null;
          try { sessionText = await readFile(sessionFile, "utf8"); } catch (e) {
            const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `missing or unreadable session for ${workflowKey} at ${String(sessionFile)}: ${boundedMessage(e)}` });
            warnings.push(warning);
          }
          if (sessionText !== null) {
            let report: Record<string, unknown> | null = null;
            try {
              report = deriveReportFromArtifacts({ taskId, ticketId, laneId, workflowId, workflowKey, childRunId, lanePath, statusObj, sessionText });
            } catch (e) {
              const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `derivation failed for ${workflowKey}/${childRunId}: ${boundedMessage(e)}` });
              warnings.push(warning);
            }
            if (report !== null) {
              const result = await publishReport({ repoControlRoot, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, lanePath, report });
              if (result.published) published.push(`${workflowKey}/${childRunId}`);
              else if (result.isDuplicate) { /* report duplicate is idempotent */ }
              else if (result.warning) warnings.push(result.warning);
            }
          }
        }
      }
    }
    try {
      const fb = await readEfficiencyFeedbackValue(statusObj, workflowId, workflowKey, childRunId, lanePath);
      if (fb.warning) {
        const w = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: fb.warning });
        warnings.push(w);
      }
      if (fb.found) {
        if (typeof fb.value !== "string") {
          const w = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `efficiencyFeedback is not a string for ${workflowKey}/${childRunId}` });
          warnings.push(w);
        } else if (unicodeLength(fb.value as string) > 10000) {
          const w = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `efficiencyFeedback exceeds maxLength 10000 for ${workflowKey}/${childRunId}` });
          warnings.push(w);
        } else {
          const fbResult = await publishFeedback({ repoControlRoot, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, lanePath, efficiencyFeedback: fb.value as string });
          if (fbResult.isDuplicate) {
          } else if (fbResult.warning) {
            warnings.push(fbResult.warning);
          }
        }
      }
    } catch (e) {
      const w = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `feedback handling failed for ${workflowKey}/${childRunId}: ${boundedMessage(e)}` });
      warnings.push(w);
    }
  }
  return { handled: true, published, warnings };
}

async function preflightSourceTreeGeneric(src: string, label: string): Promise<void> {
  const entries = await readdir(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const meta = await lstat(srcPath);
    if (meta.isSymbolicLink()) throw new Error(`${label} source contains symlink: ${srcPath}`);
    if (meta.isDirectory()) await preflightSourceTreeGeneric(srcPath, label);
    else if (!meta.isFile()) throw new Error(`${label} source contains unsupported entry: ${srcPath}`);
  }
}

async function copyRecursiveByteExactGeneric(src: string, dest: string, label: string): Promise<void> {
  const entries = await readdir(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    const meta = await lstat(srcPath);
    if (meta.isSymbolicLink()) throw new Error(`symlink encountered during copy: ${srcPath}`);
    if (meta.isDirectory()) {
      try { await mkdir(destPath, { mode: meta.mode }); } catch (e) {
        const err = e as NodeJS.ErrnoException;
        if (err.code === "EEXIST") throw new Error(`${label} destination already exists: ${destPath}`);
        throw e;
      }
      await copyRecursiveByteExactGeneric(srcPath, destPath, label);
    } else if (meta.isFile()) {
      const content = await readFile(srcPath);
      const handle = await open(destPath, fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW, 0o600);
      try { await handle.writeFile(content); } finally { await handle.close(); }
    } else throw new Error(`unsupported entry during copy: ${srcPath}`);
  }
}

// Unified snapshot primitive reused by both report and feedback trees.
async function snapshotTree(params: { repoControlRoot: string; taskId: string; outputDir: string; subtree: "lane_loop_report" | "lane_loop_feedback"; }): Promise<void> {
  const { repoControlRoot, taskId, outputDir, subtree } = params;
  if (!isSafeIdentifier(taskId)) throw new Error(`taskId must match ${SAFE_IDENTIFIER.source}`);
  if (typeof outputDir !== "string" || outputDir.length === 0) throw new Error("output_dir must be a non-empty path");
  const resolved = await resolveTaskContainer(repoControlRoot, taskId);
  if (!resolved.container) throw new Error(resolved.warning!);
  const container = resolved.container;
  const sourceRoot = path.join(container, ".collab_op", subtree);
  const destBase = path.resolve(repoControlRoot, outputDir);
  const destRoot = path.join(destBase, subtree);
  if (!(await isAncestrySafe(repoControlRoot, sourceRoot))) throw new Error(`${subtree} source ancestry is unsafe: ${sourceRoot}`);
  if (!(await isAncestrySafe(repoControlRoot, destBase)) || !(await isAncestrySafe(repoControlRoot, destRoot))) throw new Error(`${subtree} destination ancestry is unsafe: ${destRoot}`);
  const destMeta = await pathMetadata(destRoot);
  if (destMeta !== null) throw new Error(`${subtree} destination already exists: ${destRoot}`);
  const destBaseMeta = await pathMetadata(destBase);
  if (destBaseMeta !== null && !destBaseMeta.isDirectory()) throw new Error(`report destination is not a regular directory: ${destBase}`);
  const sourceMeta = await pathMetadata(sourceRoot);
  if (sourceMeta !== null) {
    if (!sourceMeta.isDirectory() || sourceMeta.isSymbolicLink()) throw new Error(`${subtree} source is not a directory: ${sourceRoot}`);
    await preflightSourceTreeGeneric(sourceRoot, subtree);
  }
  if (!(await ensureSafeDir(repoControlRoot, destBase))) throw new Error(`${subtree} destination ancestry is unsafe: ${destBase}`);
  const destMeta2 = await pathMetadata(destRoot);
  if (destMeta2 !== null) throw new Error(`${subtree} destination already exists: ${destRoot}`);
  if (sourceMeta === null) {
    try { await mkdir(destRoot, { mode: 0o700 }); } catch (e) {
      const err = e as NodeJS.ErrnoException;
      if (err.code === "EEXIST") throw new Error(`${subtree} destination already exists: ${destRoot}`);
      throw e;
    }
    return;
  }
  try { await mkdir(destRoot, { mode: 0o700 }); } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "EEXIST") throw new Error(`${subtree} destination already exists: ${destRoot}`);
    throw e;
  }
  await copyRecursiveByteExactGeneric(sourceRoot, destRoot, subtree);
}

export async function preflightSnapshot(params: { repoControlRoot: string; taskId: string; outputDir: string; subtree: "lane_loop_report" | "lane_loop_feedback"; }): Promise<void> {
  const { repoControlRoot, taskId, outputDir, subtree } = params;
  if (!isSafeIdentifier(taskId)) throw new Error(`taskId must match ${SAFE_IDENTIFIER.source}`);
  if (typeof outputDir !== "string" || outputDir.length === 0) throw new Error("output_dir must be a non-empty path");
  const resolved = await resolveTaskContainer(repoControlRoot, taskId);
  if (!resolved.container) throw new Error(resolved.warning!);
  const container = resolved.container;
  const sourceRoot = path.join(container, ".collab_op", subtree);
  const destBase = path.resolve(repoControlRoot, outputDir);
  const destRoot = path.join(destBase, subtree);
  if (!(await isAncestrySafe(repoControlRoot, sourceRoot))) throw new Error(`${subtree} source ancestry is unsafe: ${sourceRoot}`);
  if (!(await isAncestrySafe(repoControlRoot, destBase)) || !(await isAncestrySafe(repoControlRoot, destRoot))) throw new Error(`${subtree} destination ancestry is unsafe: ${destRoot}`);
  const destMeta = await pathMetadata(destRoot);
  if (destMeta !== null) throw new Error(`${subtree} destination already exists: ${destRoot}`);
  const destBaseMeta = await pathMetadata(destBase);
  if (destBaseMeta !== null && !destBaseMeta.isDirectory()) throw new Error(`report destination is not a regular directory: ${destBase}`);
  const sourceMeta = await pathMetadata(sourceRoot);
  if (sourceMeta !== null) {
    if (!sourceMeta.isDirectory() || sourceMeta.isSymbolicLink()) throw new Error(`${subtree} source is not a directory: ${sourceRoot}`);
    await preflightSourceTreeGeneric(sourceRoot, subtree);
  }
}

export async function snapshotLaneLoopReport(params: { repoControlRoot: string; taskId: string; outputDir: string; }): Promise<void> {
  return snapshotTree({ ...params, subtree: "lane_loop_report" });
}

export async function snapshotLaneLoopFeedback(params: { repoControlRoot: string; taskId: string; outputDir: string; }): Promise<void> {
  return snapshotTree({ ...params, subtree: "lane_loop_feedback" });
}
