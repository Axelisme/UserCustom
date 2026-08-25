import { constants as fsConstants } from "node:fs";
import { lstat, mkdir, open, readFile, readdir, unlink, link } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { isValidStructuredOutput } from "./result-schema.ts";

/**
 * Lane-loop report Module — settlement, version 2 terminal reporting, and coverage ownership (S1-S5 + S4 call relationship)
 *
 * Ownership: this Module owns completion-input settlement, artifact correlation,
 * mechanical child-session derivation, exactly-once publication for version 2
 * terminal reports and per-workflow coverage manifests, warning-only outcomes,
 * coverage reconciliation, and snapshot call relationship for S4. The lifecycle
 * owner in collab-reviewed-lane.ts calls this module for terminal settlement;
 * collab-op.ts calls its snapshot primitives for S4 reconciliation.
 *
 * S1 — Version 2 terminal report: one explicit version 2 report represents
 * completed, failed, or stopped children (terminalState: completed | failed | stopped
 * derived from the terminal step status) and omits unavailable duration, turn,
 * token, or tool facts rather than substituting zero. Version 1 files remain
 * readable legacy inputs and are never rewritten. The report never adds
 * structured worker Validation or other semantic result fields.
 *
 * S2 — Mechanical tool observations: recorded assistant toolCall events define
 * calls (including a visible wrapper counted once; hidden work is not inferred);
 * matching results split into succeeded and failed, unmatched calls remain
 * unresolved, intervals align one-for-one with calls using null when unavailable,
 * and summed observed duration includes only non-null runtime intervals.
 * An observed interval runs from the runtime-recorded call timestamp to its matching result timestamp and may include provider, scheduler, and extension overhead; it is not pure command execution time.
 *
 * S3 — Workflow coverage owner: each readable terminal trace produces one
 * idempotent workflow manifest whose unique known impl-* and review-* steps are
 * classified exactly once as published, warning-only, or unavailable.
 * known_steps = published_reports + warning_only_steps + unavailable_steps.
 * Identical existing manifest content is idempotent; different-content collisions
 * warn without overwrite.
 *
 * S4 — Snapshot reconciliation: the existing collab_report snapshot (in
 * collab-op.ts, via this Module's snapshot primitives) reads manifests and
 * copied report files, reconciles the three classifications against known steps,
 * identifies legacy version 1 inputs, and warns on malformed, duplicate,
 * missing, or mismatched facts without inventing a denominator.
 *
 * S5 — Best-effort boundary: report and coverage publication remain task-owned
 * telemetry that cannot change public workflow results; qualitative feedback
 * stays separate and cannot alter numeric counts; telemetry failure never
 * rewrites the public workflow outcome.
 *
 * Settlement states: permanent structural vs retryable incomplete.
 * Permanent structural correlation failures are fixed value contradictions that cannot become valid through session-file readiness waiting:
 *   - lane/workflow identity contradictions (runId mismatch, lane identity mismatch, missing cwd, duplicate/missing trace/step entries, non-terminal trace state, missing sessionFile field)
 *   - structurally invalid session identity/path (relative sessionFile, path lacking correlated childRunId segment, unsafe ancestry, symlink)
 * These route immediately through permanent settlement with complete seen, identifying affected step as unavailable, others warning-only, publishing exact manifest with durable warning in one task-lock phase.
 * Retryable is genuinely missing/incomplete material that may appear within deadline: missing status file, temporarily unreadable/partial JSON, nonterminal state, incomplete trace extraction (no readable unique trace), missing or unreadable session file content.
 * Retryable waits with 50 ms polling up to 1 s deadline, then settles warning-only with manifest per lastSeen; early no-readable-trace remains warning-only without denominator. Permanent stops waiting immediately.
 *
 * Readiness loop: an exact completion event starts an immediate readiness check
 * and then at 50 ms intervals with a fixed one-second deadline outside the task
 * mutation lock. No lock is held during waiting.
 *
 * Publication: only captured ready inputs (terminal status + readable session
 * contents) or one terminal warning proceed to short locked publication. The
 * module captures inputs, then takes the existing fail-fast task lock only while
 * publishing idempotent report/feedback/coverage or warning files. At the
 * deadline, it takes one short lock phase to append exactly one bounded
 * settlement warning and, when already correlated from terminal status/trace,
 * separately publish qualitative feedback through its own owner; feedback does
 * not affect readiness, report classification, lifecycle release, or public
 * workflow results. It performs no leaked retries and returns a terminal
 * warning-only report result. Coverage manifests are published idempotently
 * alongside reports in the same lock phase.
 *
 * Idempotency and best-effort: report/feedback/coverage publication is idempotent and
 * best-effort; telemetry failure never rewrites the public workflow result; feedback
 * publication cannot change tool observations or coverage totals.
 *
 * Observed intervals: recorded assistant toolCall events define calls; matched
 * results split succeeded/failed, unmatched remain unresolved; intervals align
 * one-for-one with calls using null when unavailable; summed duration includes
 * only non-null runtime intervals and is described as runtime observation
 * including provider/scheduler/extension overhead, not pure command time.
 */

export const REPORT_VERSION = 2;

export const FEEDBACK_VERSION = 1;

export const COVERAGE_VERSION = 1;

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

function correlateArtifacts(input: { statusObj: Record<string, unknown>; workflowId: string; workflowKey: string; childRunId: string; lanePath: string; }): { agentDurationMs: number | null; turnCount: number | null; sessionFile: string; terminalState: string } {
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
  if (traceState !== undefined && traceState !== "completed" && traceState !== "complete" && traceState !== "failed" && traceState !== "stopped" && traceState !== "paused") throw new Error(`trace entry state is not terminal: ${String(traceState)}`);
  let agentDurationMs: number | null = null;
  const dm = traceEntry["durationMs"];
  if (typeof dm === "number" && Number.isFinite(dm)) agentDurationMs = dm;
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
  let turnCount: number | null = null;
  const tc = step["turnCount"];
  if (typeof tc === "number" && Number.isFinite(tc)) turnCount = tc;
  const statusStr = step["status"] as string;
  let terminalState: string;
  if (statusStr === "failed") terminalState = "failed";
  else if (statusStr === "stopped" || statusStr === "paused") terminalState = "stopped";
  else terminalState = "completed";
  return { agentDurationMs, turnCount, sessionFile: sessionFile as string, terminalState };
}

export function deriveReportFromArtifacts(input: { taskId: string; ticketId: string; laneId: string; workflowId: string; workflowKey: string; childRunId: string; lanePath: string; statusObj: Record<string, unknown>; sessionText: string; }): Record<string, unknown> {
  const { taskId, ticketId, laneId, workflowId, workflowKey, childRunId, lanePath, statusObj, sessionText } = input;
  if (!taskId || !ticketId || !laneId || !workflowId || !workflowKey || !childRunId) throw new Error("missing attribution identity");
  if (!isSafeIdentifier(taskId) || !isSafeTicket(ticketId) || !isSafeIdentifier(laneId)) throw new Error("unsafe attribution identifier");
  const isWorkflowIdSafe = isUuid(workflowId) || isSafeIdentifier(workflowId) || isSafeTicket(workflowId);
  const isChildRunIdSafe = isUuid(childRunId) || isSafeIdentifier(childRunId) || isSafeTicket(childRunId);
  if (!isWorkflowIdSafe || !isWorkflowKey(workflowKey) || !isChildRunIdSafe) throw new Error("unsafe workflow identifier");
  const { agentDurationMs, turnCount, terminalState } = correlateArtifacts({ statusObj, workflowId, workflowKey, childRunId, lanePath });
  let tokensSum = 0;
  let tokensFound = false;
  const tools: Record<string, { calls: number; succeeded: number; failed: number; unresolved: number; observedDurationsMs: (number | null)[] }> = {};
  const pendingCalls = new Map<string, Array<{ name: string; startMs: number | null; index: number }>>();
  let toolObservedDurationMsSum = 0;
  let hasNonNullDuration = false;
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
      if (usage && typeof usage["totalTokens"] === "number" && Number.isFinite(usage["totalTokens"] as number)) {
        tokensFound = true;
        tokensSum += usage["totalTokens"] as number;
      }
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
            if (!tools[name]) tools[name] = { calls: 0, succeeded: 0, failed: 0, unresolved: 0, observedDurationsMs: [] };
            const idx = tools[name].observedDurationsMs.length;
            tools[name].calls += 1;
            tools[name].observedDurationsMs.push(null);
            if (!pendingCalls.has(id)) pendingCalls.set(id, []);
            pendingCalls.get(id)!.push({ name, startMs, index: idx });
          }
        }
      }
    } else if (role === "toolResult") {
      const toolCallId = message["toolCallId"];
      if (typeof toolCallId !== "string") continue;
      const queue = pendingCalls.get(toolCallId);
      if (!queue || queue.length === 0) continue;
      const pending = queue.shift()!;
      if (queue.length === 0) pendingCalls.delete(toolCallId);
      let endMs: number | null = null;
      const innerTs = message["timestamp"];
      if (typeof innerTs === "number" && Number.isFinite(innerTs)) endMs = innerTs;
      else if (typeof obj["timestamp"] === "string") { const p = Date.parse(obj["timestamp"] as string); if (Number.isFinite(p)) endMs = p; }
      let duration: number | null = null;
      if (pending.startMs !== null && endMs !== null) {
        const raw = endMs - pending.startMs;
        if (Number.isFinite(raw) && raw >= 0) {
          duration = raw;
          toolObservedDurationMsSum += duration;
          hasNonNullDuration = true;
        } else {
          duration = null;
        }
      } else {
        duration = null;
      }
      const entry = tools[pending.name];
      if (entry) {
        entry.observedDurationsMs[pending.index] = duration;
        if (message["isError"] !== true) entry.succeeded += 1;
        else entry.failed += 1;
      }
    }
  }
  for (const queue of pendingCalls.values()) {
    for (const pend of queue) {
      const e = tools[pend.name];
      if (e) e.unresolved += 1;
    }
  }
  const role = roleForWorkflowKey(workflowKey);
  const report: Record<string, unknown> = { reportVersion: REPORT_VERSION, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, role, terminalState };
  if (agentDurationMs !== null) (report as Record<string, unknown>)["agentDurationMs"] = agentDurationMs;
  if (turnCount !== null) (report as Record<string, unknown>)["turns"] = turnCount;
  if (tokensFound) (report as Record<string, unknown>)["tokens"] = tokensSum;
  if (hasNonNullDuration) (report as Record<string, unknown>)["toolObservedDurationMs"] = toolObservedDurationMsSum;
  if (Object.keys(tools).length > 0) (report as Record<string, unknown>)["tools"] = tools;
  return report;
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

export async function publishCoverageManifest(params: { repoControlRoot: string; taskId: string; workflowId: string; manifest: Record<string, unknown>; }): Promise<{ published: boolean; warning?: string; isDuplicate?: boolean }> {
  const { repoControlRoot, taskId, workflowId, manifest } = params;
  const isWorkflowIdSafe = isUuid(workflowId) || isSafeIdentifier(workflowId) || isSafeTicket(workflowId);
  if (!isSafeIdentifier(taskId) || !isWorkflowIdSafe) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `unsafe identities for coverage ${taskId}/${workflowId}` });
    return { published: false, warning };
  }
  const resolved = await resolveTaskContainer(repoControlRoot, taskId);
  if (!resolved.container) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: resolved.warning! });
    return { published: false, warning };
  }
  const container = resolved.container;
  const coverageDir = path.join(container, ".collab_op", "lane_loop_report", "coverage");
  const manifestPath = path.join(coverageDir, `${workflowId}.json`);
  if (path.resolve(manifestPath) !== path.resolve(container) && !path.resolve(manifestPath).startsWith(path.resolve(container) + path.sep)) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `coverage path escapes container` });
    return { published: false, warning };
  }
  if (!(await isAncestrySafe(repoControlRoot, coverageDir)) || !(await isAncestrySafe(repoControlRoot, manifestPath))) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `coverage path ancestry is unsafe: ${manifestPath}` });
    return { published: false, warning };
  }
  const existingMeta = await pathMetadata(manifestPath);
  if (existingMeta !== null && (!existingMeta.isFile() || existingMeta.isSymbolicLink())) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `coverage destination is not a regular file: ${manifestPath}` });
    return { published: false, warning };
  }
  // Ensure byte-idempotency: omit volatile generatedAt from file bytes and from comparison
  const normalizedManifest: Record<string, unknown> = { ...manifest };
  if ("generatedAt" in normalizedManifest) delete (normalizedManifest as Record<string, unknown>)["generatedAt"];
  const content = `${JSON.stringify(normalizedManifest)}\n`;
  if (!(await ensureSafeDir(repoControlRoot, coverageDir))) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `could not create coverage directory: ancestry unsafe ${coverageDir}` });
    return { published: false, warning };
  }
  const dirMeta = await pathMetadata(coverageDir);
  if (!dirMeta?.isDirectory() || dirMeta.isSymbolicLink()) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `coverage directory is not a directory` });
    return { published: false, warning };
  }
  const tmpName = `${workflowId}.tmp.${process.pid}.${randomUUID()}`;
  const tmpPath = path.join(coverageDir, tmpName);
  try {
    const handle = await open(tmpPath, fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW, 0o600);
    try { await handle.writeFile(content, { encoding: "utf8" }); } finally { await handle.close(); }
  } catch (e) {
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `could not write temporary coverage: ${boundedMessage(e)}` });
    return { published: false, warning };
  }
  try {
    await link(tmpPath, manifestPath);
    try { await unlink(tmpPath); } catch {}
    return { published: true };
  } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "EEXIST") {
      try {
        const existingContent = await readFile(manifestPath, "utf8");
        if (existingContent === content) { try { await unlink(tmpPath); } catch {} return { published: false, isDuplicate: true }; }
        // For byte-idempotency, compare normalized logical content ignoring volatile generatedAt
        try {
          const existingObj = JSON.parse(existingContent) as Record<string, unknown>;
          const existingNorm: Record<string, unknown> = { ...existingObj };
          if ("generatedAt" in existingNorm) delete existingNorm["generatedAt"];
          const existingNormalizedContent = `${JSON.stringify(existingNorm)}\n`;
          if (existingNormalizedContent === content) { try { await unlink(tmpPath); } catch {} return { published: false, isDuplicate: true }; }
        } catch {}
        try { await unlink(tmpPath); } catch {}
        const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `coverage collision for ${workflowId}: different content exists` });
        return { published: false, warning };
      } catch (readErr) {
        try { await unlink(tmpPath); } catch {}
        const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `could not compare existing coverage: ${boundedMessage(readErr)}` });
        return { published: false, warning };
      }
    }
    try { await unlink(tmpPath); } catch {}
    const warning = await appendWarning(repoControlRoot, { taskId, laneId: "unknown", workflowId, workflowKey: "unknown", childRunId: "unknown", message: `could not install coverage: ${boundedMessage(e)}` });
    return { published: false, warning };
  }
}

export async function handleReviewedLaneCompletion(input: { repoControlRoot: string; taskId: string; ticketId: string; laneId: string; lanePath: string; workflowId: string; asyncDir: string; eventWorkflowId: string; eventAsyncDir: string; withTaskLock?: <T>(body: () => Promise<T>) => Promise<T>; }): Promise<{ handled: boolean; published: string[]; warnings: string[]; ignoredReason?: string }> {
  const { repoControlRoot, taskId, ticketId, laneId, lanePath, workflowId, asyncDir, eventWorkflowId, eventAsyncDir } = input as any;
  const withTaskLock = (input as any).withTaskLock as (<T>(body: () => Promise<T>) => Promise<T>) | undefined;
  if (eventWorkflowId !== workflowId || eventAsyncDir !== asyncDir) return { handled: false, published: [], warnings: [], ignoredReason: "partial or unrelated completion event" };
  const statusPath = path.join(asyncDir, "status.json");
  // Permanent ancestry check outside readiness loop: unsafe path is immediate terminal warning (no retry)
  if (!(await isAncestrySafe(repoControlRoot, statusPath))) {
    const doWarn = () => appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message: `status path ancestry is unsafe at ${statusPath}` });
    const warning = withTaskLock ? await withTaskLock(doWarn).catch((e: unknown) => boundedMessage(e).slice(0, 500)) : await doWarn();
    return { handled: true, published: [], warnings: [warning], ignoredReason: "unsafe status ancestry" };
  }
  // Early permanent check for status file being a symlink or non-regular file that exists (missing is retryable)
  const earlyMeta = await pathMetadata(statusPath);
  if (earlyMeta !== null && (earlyMeta.isSymbolicLink() || !earlyMeta.isFile())) {
    const doWarn = () => appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message: `status artifact is not a regular file at ${statusPath}` });
    const warning = withTaskLock ? await withTaskLock(doWarn).catch((e: unknown) => boundedMessage(e).slice(0, 500)) : await doWarn();
    return { handled: true, published: [], warnings: [warning], ignoredReason: "unsafe status artifact" };
  }

  // Readiness settlement outside task lock: immediate check then 50ms interval, 1s deadline
  const deadline = Date.now() + 1000;
  let lastRetryReason: string | null = null;
  type Captured = { statusObj: Record<string, unknown>; seen: Map<string, { workflowKey: string; childRunId: string }>; sessionTexts: Map<string, string> };
  let captured: Captured | null = null;

  const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

  /**
   * Explicit semantic boundary: permanent structural vs retryable incomplete.
   * Permanent = fixed value contradictions that cannot become valid by waiting for session-file readiness.
   * Retryable = genuinely missing/incomplete material (handled elsewhere: missing status, invalid JSON, nonterminal state, missing trace when no readable unique steps, missing/unreadable session file).
   * This list covers at minimum relative sessionFile, childRunId segment mismatch, and other fixed status/lane/workflow identity contradictions emitted by correlateArtifacts.
   */
  const PERMANENT_STRUCTURAL_SUBSTRINGS: readonly string[] = [
    // lane/workflow identity contradictions (fixed)
    "does not match workflowid",
    "status missing cwd",
    "lane identity mismatch",
    "trace entry not found",
    "duplicate trace entries",
    "trace entry state is not terminal",
    "missing steps",
    "status step not found",
    "duplicate terminal steps",
    "step missing sessionfile",
    // structurally invalid session identity/path (at minimum relative + childRunId mismatch)
    "is not absolute",
    "does not contain childrunid",
    // unsafe filesystem signals (structural)
    "ancestry is unsafe",
    "symlink",
    "unsafe identities",
    "is not a regular directory",
  ];
  const isPermanentStructuralFailure = (msg: string): boolean => {
    const lower = msg.toLowerCase();
    return PERMANENT_STRUCTURAL_SUBSTRINGS.some((p) => lower.includes(p));
  };
  const isPermanentMessage = isPermanentStructuralFailure;

  async function tryCapture(): Promise<{ state: "ready"; captured: Captured } | { state: "retryable"; reason: string; statusObj?: Record<string, unknown>; seen?: Map<string, { workflowKey: string; childRunId: string }>; sessionTexts?: Map<string, string> } | { state: "permanent"; message: string; workflowKey?: string; childRunId?: string; ignoredReason?: string; seen?: Map<string, { workflowKey: string; childRunId: string }>; sessionTexts?: Map<string, string> }> {
    let statusText: string;
    try {
      statusText = await readFile(statusPath, "utf8");
    } catch (e) {
      return { state: "retryable", reason: `missing status artifact at ${statusPath}: ${boundedMessage(e)}` };
    }
    let statusObj: Record<string, unknown>;
    try {
      statusObj = JSON.parse(statusText);
    } catch (e) {
      return { state: "retryable", reason: `invalid status JSON: ${boundedMessage(e)}` };
    }
    const state = (statusObj as { state?: unknown }).state;
    if (state !== "complete" && state !== "failed" && state !== "stopped") {
      return { state: "retryable", reason: `exact completion event has nonterminal status state ${String(state)}`, statusObj };
    }
    const workflow = (statusObj as { workflow?: unknown }).workflow as { trace?: unknown } | undefined;
    const trace = workflow?.trace as Array<Record<string, unknown>> | undefined;
    if (!Array.isArray(trace) || trace.length === 0) {
      return { state: "retryable", reason: `missing workflow trace for ${workflowId}`, statusObj };
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
    if (seen.size === 0) {
      return { state: "retryable", reason: `missing workflow trace for ${workflowId}`, statusObj };
    }
    const sessionTexts = new Map<string, string>();
    for (const { workflowKey, childRunId } of seen.values()) {
      let sessionFile: string;
      try {
        const corr = correlateArtifacts({ statusObj, workflowId, workflowKey, childRunId, lanePath });
        sessionFile = corr.sessionFile;
      } catch (e) {
        const msg = `derivation failed for ${workflowKey}/${childRunId}: ${boundedMessage(e)}`;
        if (isPermanentMessage(msg)) return { state: "permanent", message: msg, workflowKey, childRunId, ignoredReason: "permanent derivation failure", seen, sessionTexts };
        return { state: "retryable", reason: msg, statusObj, seen, sessionTexts };
      }
      if (!(await isAncestrySafe(repoControlRoot, sessionFile))) {
        return { state: "permanent", message: `session file ancestry is unsafe for ${workflowKey} at ${sessionFile}`, workflowKey, childRunId, ignoredReason: "unsafe session ancestry", seen, sessionTexts };
      }
      const sessMeta = await pathMetadata(sessionFile);
      if (sessMeta !== null && (sessMeta.isSymbolicLink() || !sessMeta.isFile())) {
        const msg = sessMeta.isSymbolicLink() ? `session file is a symlink for ${workflowKey} at ${sessionFile}` : `session file is not a regular file for ${workflowKey} at ${sessionFile}`;
        return { state: "permanent", message: msg, workflowKey, childRunId, ignoredReason: "unsafe session artifact", seen, sessionTexts };
      }
      if (sessMeta === null) {
        return { state: "retryable", reason: `session file is not a regular file for ${workflowKey} at ${sessionFile}`, statusObj, seen, sessionTexts };
      }
      try {
        const txt = await readFile(sessionFile, "utf8");
        sessionTexts.set(`${workflowKey}\0${childRunId}`, txt);
      } catch (e) {
        return { state: "retryable", reason: `missing or unreadable session for ${workflowKey} at ${String(sessionFile)}: ${boundedMessage(e)}`, statusObj, seen, sessionTexts };
      }
    }
    return { state: "ready", captured: { statusObj, seen, sessionTexts } };
  }

  while (true) {
    const attempt = await tryCapture();
    if (attempt.state === "permanent") {
      const seen = (attempt as any).seen as Map<string, { workflowKey: string; childRunId: string }> | undefined;
      const hasSeen = seen instanceof Map && seen.size > 0;
      if (hasSeen) {
        const affectedKey = attempt.workflowKey ?? "unknown";
        const affectedChild = attempt.childRunId ?? "unknown";
        const doPermanentSettlement = async (): Promise<{ warnings: string[] }> => {
          const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: affectedKey, childRunId: affectedChild, message: attempt.message });
          const warnings: string[] = [warning];
          const classifications: Array<{ workflowKey: string; childRunId: string; classification: string }> = [];
          for (const { workflowKey, childRunId } of seen!.values()) {
            const isAffected = workflowKey === affectedKey && childRunId === affectedChild;
            classifications.push({ workflowKey, childRunId, classification: isAffected ? "unavailable" : "warning-only" });
          }
          classifications.sort((a, b) => a.workflowKey.localeCompare(b.workflowKey) || a.childRunId.localeCompare(b.childRunId));
          const knownSteps = classifications.length;
          const publishedReports = 0;
          const warningOnlySteps = classifications.filter(c => c.classification === "warning-only").length;
          const unavailableSteps = classifications.filter(c => c.classification === "unavailable").length;
          const manifest: Record<string, unknown> = {
            coverageVersion: COVERAGE_VERSION,
            taskId,
            workflowId,
            knownSteps,
            publishedReports,
            warningOnlySteps,
            unavailableSteps,
            steps: classifications.map(c => ({ workflowKey: c.workflowKey, childRunId: c.childRunId, classification: c.classification })),
          };
          const covResult = await publishCoverageManifest({ repoControlRoot, taskId, workflowId, manifest });
          if (covResult.warning) warnings.push(covResult.warning);
          return { warnings };
        };
        let warnings: string[];
        if (withTaskLock) {
          try {
            const res = await withTaskLock(doPermanentSettlement);
            warnings = res.warnings;
          } catch (e) {
            const w = boundedMessage(e).slice(0, 500);
            try { console.warn(`[collab-report] ${w}`); } catch {}
            await emitOperationWarning(repoControlRoot, w);
            return { handled: true, published: [], warnings: [w], ignoredReason: "lock failure" };
          }
        } else {
          const res = await doPermanentSettlement();
          warnings = res.warnings;
        }
        return { handled: true, published: [], warnings, ignoredReason: attempt.ignoredReason ?? "permanent input" };
      } else {
        const doWarn = () => appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: attempt.workflowKey ?? "unknown", childRunId: attempt.childRunId ?? "unknown", message: attempt.message });
        let warning: string;
        if (withTaskLock) {
          try { warning = await withTaskLock(doWarn); } catch (e) { warning = boundedMessage(e).slice(0, 500); try { console.warn(`[collab-report] ${warning}`);} catch {} }
        } else { warning = await doWarn(); }
        return { handled: true, published: [], warnings: [warning], ignoredReason: attempt.ignoredReason ?? "permanent input" };
      }
    }
    if (attempt.state === "ready") { captured = attempt.captured; break; }
    lastRetryReason = attempt.reason;
    // retain last statusObj if available for feedback publishing after deadline
    const lastStatusObj = (attempt as any).statusObj as Record<string, unknown> | undefined;
    const lastSeen = (attempt as any).seen as Map<string, { workflowKey: string; childRunId: string }> | undefined;
    // keep for deadline feedback
    (globalThis as any).__lastStatusObj = lastStatusObj;
    (globalThis as any).__lastSeen = lastSeen;
    const now = Date.now();
    if (now >= deadline) {
      const message = lastRetryReason ?? "settlement deadline exceeded";
      // Map retryable reason to original ignoredReason for compatibility
      let ignoredReason = "deadline exceeded";
      if (message.includes("nonterminal")) ignoredReason = "nonterminal status artifact";
      else if (message.includes("missing status artifact")) ignoredReason = "missing status";
      else if (message.includes("invalid status JSON")) ignoredReason = "invalid status json";
      else if (message.includes("missing workflow trace")) ignoredReason = "missing workflow trace";
      else if (message.toLowerCase().includes("session file")) ignoredReason = "session file not ready";
      // One short lock phase: exactly one settlement warning and already-correlated feedback separately within same lock.
      // Feedback does not affect report readiness, classification, lifecycle release, or public workflow results.
      const doDeadlineSettlement = async (): Promise<{ warning: string; fbWarnings: string[] }> => {
        const warning = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey: "unknown", childRunId: "unknown", message });
        const fbWarnings: string[] = [];
        if (lastStatusObj && lastSeen) {
          for (const { workflowKey, childRunId } of lastSeen.values()) {
            try {
              const fb = await readEfficiencyFeedbackValue(lastStatusObj, workflowId, workflowKey, childRunId, lanePath);
              if (fb.warning) {
                const w = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: fb.warning });
                fbWarnings.push(w);
              }
              if (fb.found) {
                if (typeof fb.value !== "string") {
                  const w = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `efficiencyFeedback is not a string for ${workflowKey}/${childRunId}` });
                  fbWarnings.push(w);
                } else if (unicodeLength(fb.value as string) > 10000) {
                  const w = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `efficiencyFeedback exceeds maxLength 10000 for ${workflowKey}/${childRunId}` });
                  fbWarnings.push(w);
                } else {
                  const fbResult = await publishFeedback({ repoControlRoot, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, lanePath, efficiencyFeedback: fb.value as string });
                  if (fbResult.warning) fbWarnings.push(fbResult.warning);
                }
              }
            } catch {}
          }
          // Coverage manifest for deadline: readable trace but incomplete sessions => warning-only for each known step
          try {
            const classifications: Array<{ workflowKey: string; childRunId: string; classification: string }> = [];
            for (const { workflowKey, childRunId } of lastSeen.values()) {
              classifications.push({ workflowKey, childRunId, classification: "warning-only" });
            }
            classifications.sort((a, b) => a.workflowKey.localeCompare(b.workflowKey) || a.childRunId.localeCompare(b.childRunId));
            const manifest: Record<string, unknown> = {
              coverageVersion: COVERAGE_VERSION,
              taskId,
              workflowId,
              knownSteps: classifications.length,
              publishedReports: 0,
              warningOnlySteps: classifications.length,
              unavailableSteps: 0,
              steps: classifications.map(c => ({ workflowKey: c.workflowKey, childRunId: c.childRunId, classification: c.classification })),
            };
            const covResult = await publishCoverageManifest({ repoControlRoot, taskId, workflowId, manifest });
            if (covResult.warning) fbWarnings.push(covResult.warning);
          } catch {}
        }
        return { warning, fbWarnings };
      };
      if (withTaskLock) {
        try {
          const { warning, fbWarnings } = await withTaskLock(doDeadlineSettlement);
          return { handled: true, published: [], warnings: [warning, ...fbWarnings], ignoredReason };
        } catch (e) {
          const warning = boundedMessage(e).slice(0, 500);
          try { console.warn(`[collab-report] ${warning}`); } catch {}
          await emitOperationWarning(repoControlRoot, warning);
          return { handled: true, published: [], warnings: [warning], ignoredReason: "lock failure" };
        }
      } else {
        const { warning, fbWarnings } = await doDeadlineSettlement();
        return { handled: true, published: [], warnings: [warning, ...fbWarnings], ignoredReason };
      }
    }
    const waitMs = Math.min(50, deadline - now);
    if (waitMs > 0) await sleep(waitMs);
  }

  // Captured ready inputs: publish under short lock if provided
  const { statusObj, seen, sessionTexts } = captured!;
  const doPublish = async (): Promise<{ published: string[]; warnings: string[] }> => {
    const published: string[] = [];
    const warnings: string[] = [];
    const classifications: Array<{ workflowKey: string; childRunId: string; classification: string }> = [];
    for (const { workflowKey, childRunId } of seen.values()) {
      const sessionText = sessionTexts.get(`${workflowKey}\0${childRunId}`) ?? null;
      if (sessionText === null) {
        const w = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `missing captured session for ${workflowKey}/${childRunId}` });
        warnings.push(w);
        const isUnavail = w.toLowerCase().includes("ancestry is unsafe") || w.toLowerCase().includes("is not a regular");
        classifications.push({ workflowKey, childRunId, classification: isUnavail ? "unavailable" : "warning-only" });
        continue;
      }
      let report: Record<string, unknown> | null = null;
      try {
        report = deriveReportFromArtifacts({ taskId, ticketId, laneId, workflowId, workflowKey, childRunId, lanePath, statusObj, sessionText });
      } catch (e) {
        const w = await appendWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `derivation failed for ${workflowKey}/${childRunId}: ${boundedMessage(e)}` });
        warnings.push(w);
        const isUnavail = w.toLowerCase().includes("ancestry is unsafe") || w.toLowerCase().includes("is not a regular") || w.toLowerCase().includes("unsafe");
        classifications.push({ workflowKey, childRunId, classification: isUnavail ? "unavailable" : "warning-only" });
        continue;
      }
      if (report !== null) {
        const result = await publishReport({ repoControlRoot, taskId, ticketId, laneId, workflowId, workflowKey, childRunId, lanePath, report });
        if (result.published) {
          published.push(`${workflowKey}/${childRunId}`);
          classifications.push({ workflowKey, childRunId, classification: "published" });
        } else if (result.isDuplicate) {
          classifications.push({ workflowKey, childRunId, classification: "published" });
        } else if (result.warning) {
          warnings.push(result.warning);
          const isUnavail = result.warning.toLowerCase().includes("ancestry is unsafe") || result.warning.toLowerCase().includes("is not a regular");
          classifications.push({ workflowKey, childRunId, classification: isUnavail ? "unavailable" : "warning-only" });
        } else {
          classifications.push({ workflowKey, childRunId, classification: "unavailable" });
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
            if (fbResult.isDuplicate) { } else if (fbResult.warning) warnings.push(fbResult.warning);
          }
        }
      } catch (e) {
        const w = await appendFeedbackWarning(repoControlRoot, { taskId, laneId, workflowId, workflowKey, childRunId, message: `feedback handling failed for ${workflowKey}/${childRunId}: ${boundedMessage(e)}` });
        warnings.push(w);
      }
    }
    // Coverage manifest: one idempotent manifest per readable terminal trace, with unique known steps and equation known_steps = published + warning-only + unavailable
    classifications.sort((a, b) => a.workflowKey.localeCompare(b.workflowKey) || a.childRunId.localeCompare(b.childRunId));
    const knownSteps = classifications.length;
    const publishedReports = classifications.filter(c => c.classification === "published").length;
    const warningOnlySteps = classifications.filter(c => c.classification === "warning-only").length;
    const unavailableSteps = classifications.filter(c => c.classification === "unavailable").length;
    const manifest: Record<string, unknown> = {
      coverageVersion: COVERAGE_VERSION,
      taskId,
      workflowId,
      knownSteps,
      publishedReports,
      warningOnlySteps,
      unavailableSteps,
      steps: classifications.map(c => ({ workflowKey: c.workflowKey, childRunId: c.childRunId, classification: c.classification })),
    };
    const covResult = await publishCoverageManifest({ repoControlRoot, taskId, workflowId, manifest });
    if (covResult.warning) warnings.push(covResult.warning);
    return { published, warnings };
  };

  try {
    const res = withTaskLock ? await withTaskLock(doPublish) : await doPublish();
    return { handled: true, published: res.published, warnings: res.warnings };
  } catch (e) {
    const msg = `task lock failed during publication: ${boundedMessage(e)}`;
    const bounded = boundedMessage(msg).slice(0, 500);
    try { console.warn(`[collab-report] ${bounded}`); } catch {}
    // Do not mutate task files without a successful lock — best-effort telemetry only.
    await emitOperationWarning(repoControlRoot, bounded);
    return { handled: true, published: [], warnings: [bounded], ignoredReason: "lock failure" };
  }
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
