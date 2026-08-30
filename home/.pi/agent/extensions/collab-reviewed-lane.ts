import { randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import path from "node:path";
import { getAgentDir, type ExtensionAPI, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import type {
  GitRunner,
  LaneInventory,
  Repository,
  TaskLayout,
  WorktreeRecord,
} from "./collab-op.ts";
import { handleReviewedLaneCompletion } from "./collab-shared/report.ts";
import {
  reviewedLaneWorkerSchema,
  reviewedLaneReviewerSchema,
} from "./collab-shared/result-schema.ts";

/**
 * Reviewed lane lifecycle Module
 *
 * Ownership: this Module owns lifecycle admission, process-local active task/lane
 * registration, correlated terminal completion and registration release.
 *
 * Key identity: canonical repository control root (path.resolve), task_id, lane_id.
 * Equal IDs in different repositories do not block each other.
 *
 * Reservation timing: synchronously after managed-lane identity validation
 * (discoverRepository, requireManagedIntegration, laneInventory + laneIsComplete)
 * and before the first spawn-related await (profile preflight, RPC ping/spawn).
 *
 * Duplicate admission: while launching or active, a same-key launch returns
 * reviewed_lane_active before child spawn, without a second RPC spawn. Different
 * lane keys remain independent.
 *
 * Release rules: validation failure, cancellation before spawn emission, or an
 * explicit spawn rejection releases the launching reservation immediately;
 * cancellation or timeout after spawn emission is ambiguous and retains the
 * reservation because a child may exist; a correlated receipt moves it to active
 * until exact workflowId plus asyncDir terminal settlement releases it, and a
 * later same-key launch then succeeds. Partial or unrelated completion events
 * retain the active reservation. Release uses finally so telemetry or lock
 * failure cannot strand the process-local reservation except for the admitted
 * ambiguous post-emission case where no receipt arrives. If no receipt ever
 * arrives, process restart is the admitted recovery boundary. Restart recovery
 * is absent by contract.
 *
 * Telemetry relationship: settlement and publication in collab-shared/report.ts
 * are best-effort side effects; they never delay, replace, or rewrite the public
 * reviewed-workflow receipt or terminal result.
 *
 * Exact correlation: workflowId plus asyncDir.
 */

const DEV_FLOW_TICKET_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const REVIEWED_LANE_IDENTIFIER = /^[a-z0-9][a-z0-9._-]*$/;

const reviewedLaneTaskId = {
  type: "string",
  pattern: REVIEWED_LANE_IDENTIFIER.source,
  description: "Lowercase task identifier for the Git-managed task.",
} as const;

const reviewedLaneId = {
  type: "string",
  pattern: REVIEWED_LANE_IDENTIFIER.source,
  not: { const: "integration" },
  description: "Lowercase lane identifier for the Git-managed task; integration is reserved.",
} as const;

export const registeredReviewedLaneParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    task_id: reviewedLaneTaskId,
    ticket_id: {
      type: "string",
      pattern: DEV_FLOW_TICKET_IDENTIFIER.source,
      description: "ASCII Dev-flow ticket identifier for the delegated contract.",
    },
    lane_id: reviewedLaneId,
    worker_brief: {
      type: "string",
      minLength: 1,
      maxLength: 32768,
      description: "Non-empty bounded implementation brief.",
    },
    review_brief: {
      type: "string",
      minLength: 1,
      maxLength: 32768,
      description: "Non-empty bounded read-only acceptance brief.",
    },
    correction_budget: {
      type: "integer",
      minimum: 0,
      maximum: Number.MAX_SAFE_INTEGER,
      description: "Non-negative safe integer count of fresh correction and rereview rounds; the initial implementation is free.",
    },
  },
  required: [
    "task_id",
    "ticket_id",
    "lane_id",
    "worker_brief",
    "review_brief",
    "correction_budget",
  ],
} as const;

export { reviewedLaneWorkerSchema, reviewedLaneReviewerSchema };

type ReviewedLaneErrorFactory = (
  code: string,
  message: string,
  repair?: string,
  details?: Record<string, unknown>,
) => Error;

type ManagedIntegration = {
  tip: string;
  base: string;
  records: WorktreeRecord[];
};

export type ReviewedLaneDependencies = {
  discoverRepository: (
    run: GitRunner,
    cwd: string,
    signal?: AbortSignal,
  ) => Promise<Repository>;
  createTask: (repo: Repository, taskId: string) => TaskLayout;
  requireTaskId: (value: unknown) => string;
  requireLaneId: (value: unknown) => string;
  requireManagedIntegration: (
    repo: Repository,
    task: TaskLayout,
    signal?: AbortSignal,
  ) => Promise<ManagedIntegration>;
  laneInventory: (
    repo: Repository,
    task: TaskLayout,
    laneId: string,
    signal?: AbortSignal,
    records?: readonly WorktreeRecord[],
  ) => Promise<LaneInventory>;
  laneIsComplete: (inventory: LaneInventory) => boolean;
  withTaskLock: <T>(repo: Repository, taskId: string, body: () => Promise<T>) => Promise<T>;
  error: ReviewedLaneErrorFactory;
};

const SUBAGENT_RPC_REQUEST_EVENT = "subagents:rpc:v1:request";
const SUBAGENT_RPC_REPLY_PREFIX = "subagents:rpc:v1:reply:";
const SUBAGENT_RPC_VERSION = 1;

type SubagentRpcReply = {
  version?: unknown;
  requestId?: unknown;
  success?: unknown;
  data?: unknown;
  error?: unknown;
};

type SubagentLaunchContractResult =
  | {
    ok: true;
    contract?: {
      inheritProjectContext?: unknown;
      roots?: { cwd?: unknown };
    };
  }
  | { ok: false; message?: unknown };

type ResolveSubagentLaunchContract = (input: {
  agent: string;
  cwd: string;
  task: string;
  context: "fresh";
  outputSchema: Record<string, unknown>;
  agentContract?: { version: 1 };
  availableModels?: readonly unknown[];
}) => Promise<SubagentLaunchContractResult>;

type ReviewedLaneRoleSpec = {
  agent: "collab-implementer" | "collab-acceptor";
  task: string;
  outputSchema: Record<string, unknown>;
  agentContract?: { version: 1 };
};

let resolveSubagentLaunchContract: ResolveSubagentLaunchContract | undefined;

let __testSpawnTimeoutMs: number | undefined;
export function __setTestSpawnTimeoutForTest(ms: number | undefined): void {
  __testSpawnTimeoutMs = ms;
  (globalThis as unknown as Record<string, unknown>).__collabTestSpawnTimeoutMs = ms;
}

function boundedMessage(value: unknown): string {
  const message =
    value instanceof Error ? value.message : typeof value === "string" ? value : "unknown error";
  return message.replace(/[\r\n]+/g, " ").slice(0, 300);
}

async function callSubagentRpc(
  pi: ExtensionAPI,
  method: "ping" | "spawn",
  params: Record<string, unknown>,
  error: ReviewedLaneErrorFactory,
  signal?: AbortSignal,
): Promise<SubagentRpcReply> {
  const requestId = randomUUID();
  const replyEvent = `${SUBAGENT_RPC_REPLY_PREFIX}${requestId}`;
  return new Promise<SubagentRpcReply>((resolve, reject) => {
    let unsubscribe: (() => void) | void;
    let emitted = false;
    const cleanup = () => {
      if (typeof unsubscribe === "function") unsubscribe();
      clearTimeout(timer);
      signal?.removeEventListener("abort", aborted);
    };
    const fail = (failure: Error) => {
      cleanup();
      reject(failure);
    };
    const aborted = () => {
      if (method === "spawn" && emitted) return;
      const err = error(
        "request_aborted",
        "reviewed-lane launch was aborted before RPC completion",
        "Retry the launch after the caller is ready to keep the request active.",
      );
      (err as unknown as Record<string, unknown>).__emitted = emitted;
      (err as unknown as Record<string, unknown>).__method = method;
      fail(err);
    };
    const globalTimeout = (globalThis as unknown as Record<string, unknown>).__collabTestSpawnTimeoutMs as number | undefined;
    const timeoutMs = method === "ping" ? 2000 : (globalTimeout ?? __testSpawnTimeoutMs ?? 15000);
    const timer = setTimeout(() => {
      const err = error(
        "rpc_unavailable",
        `pi-subagents did not answer the ${method} RPC request`,
        "Enable pi-subagents with Extension RPC v1 support, then retry.",
      );
      (err as unknown as Record<string, unknown>).__emitted = emitted;
      (err as unknown as Record<string, unknown>).__method = method;
      fail(err);
    }, timeoutMs);
    unsubscribe = pi.events.on(replyEvent, (raw: unknown) => {
      const reply = raw && typeof raw === "object" && !Array.isArray(raw)
        ? raw as SubagentRpcReply
        : {};
      if (reply.requestId !== requestId) return;
      cleanup();
      resolve(reply);
    });
    if (signal?.aborted) {
      aborted();
      return;
    }
    signal?.addEventListener("abort", aborted, { once: true });
    pi.events.emit(SUBAGENT_RPC_REQUEST_EVENT, {
      version: SUBAGENT_RPC_VERSION,
      requestId,
      method,
      params,
      source: { extension: "collab-op" },
    });
    emitted = true;
  });
}

function requireDevFlowTicketIdentifier(
  value: unknown,
  error: ReviewedLaneErrorFactory,
): string {
  if (typeof value !== "string" || !DEV_FLOW_TICKET_IDENTIFIER.test(value)) {
    throw error(
      "invalid_identifier",
      "ticket id must be an ASCII Dev-flow identifier of at most 64 characters",
      `Use a ticket id matching ${DEV_FLOW_TICKET_IDENTIFIER.source}.`,
    );
  }
  return value;
}

function requireReviewedLaneBrief(
  value: unknown,
  label: string,
  error: ReviewedLaneErrorFactory,
): string {
  if (typeof value !== "string" || !value.trim() || value.length > 32768) {
    throw error(
      "invalid_parameters",
      `${label} must be non-empty and no longer than 32768 characters`,
      `Provide one bounded, non-empty ${label}.`,
    );
  }
  return value.trim();
}

function requireCorrectionBudget(value: unknown, error: ReviewedLaneErrorFactory): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw error(
      "invalid_parameters",
      "correction budget must be a non-negative safe integer",
      "Provide a finite non-negative integer no greater than Number.MAX_SAFE_INTEGER.",
    );
  }
  return value;
}

/**
 * Pi reviewed result projection — S1/S3 aligned
 *
 * This projection keeps typed routing in REVIEWED/CORRECTION_BUDGET_EXHAUSTED/BLOCKED/NEEDS_DECISION/REVIEWER_RUNTIME_RECOVERY_EXHAUSTED,
 * merges latest worker residualRisks then final reviewer residualRisks (every branch preserves available risks, REVIEWED merges both),
 * carries no free-text validation, no outOfEnvelopeFindings and no evidence body or pointer; correctionBase is internal
 * to the reviewed loop (initial BLOCKED carries exact lane HEAD SHA, rereview receives original brief, prior blockers and that base,
 * reviewer obtains delta via Git) and never appears in public terminal results. Commands remain with run artifacts; durable
 * observations for difficult claims belong to the workflow-scoped Acceptance appendix at the
 * exact dispatched target. The runtime adds no evidence parameter, does not validate assignment, and carries only original
 * review brief, prior typed blockers and correctionBase for rereview with no ancestry, reconciliation, scope or
 * incremental-eligibility policy.
 * Initial review exhausts every non-mechanical Acceptance claim and directly reachable siblings in the same failure class
 * before returning BLOCKED; rereview verifies every prior blocker and correction-reachable semantic effect without rerunning
 * mechanical gates or restarting the whole review.
 */
export function reviewedLaneWorkflowScript(input: {
  lane: string;
  workerBrief: string;
  reviewBrief: string;
  correctionBudget: number;
  retainedCorrection: boolean;
  /** Runtime-owned immutable comparison baseline for initial review. */
  integrationTip: string;
}): string {
  const workerSchema = JSON.stringify(reviewedLaneWorkerSchema);
  const reviewerSchema = JSON.stringify(reviewedLaneReviewerSchema);
  return `
const budget = ${input.correctionBudget};
const lane = ${JSON.stringify(input.lane)};
const integrationTip = ${JSON.stringify(input.integrationTip)};
const initialReviewerBaseline = "Initial review — runtime-owned integration tip " + integrationTip + ". Exhaust every non-mechanical Acceptance claim and directly reachable siblings before returning BLOCKED. Use this read-only canonical command for the complete candidate lane diff: git diff --find-renames " + integrationTip + "...HEAD --";
const rereviewBaselineFor = (base) => "Rereview — fresh reviewer receives original brief, prior typed blockers and internal correctionBase " + base + ". Verify every prior blocker and correction-reachable semantic effect without rerunning mechanical gates or restarting the whole review. Obtain delta from Git with this read-only canonical command: git diff --find-renames " + base + "...HEAD --";
const workerSchema = ${workerSchema};
const reviewerSchema = ${reviewerSchema};
const retainedCorrection = ${input.retainedCorrection};
const efficiencyFeedbackRequest = "You may return optional native efficiencyFeedback when you observed a concrete avoidable cost.";
const runFreshChild = (key, agent, task, outputSchema) => runs.run(key, {
  agent,
  cwd: lane,
  worktree: false,
  context: "fresh",
  task,
  outputSchema,
  ...(agent === "collab-implementer" ? { agentContract: { version: 1 } } : {})
});
const successfulRunId = (child) => typeof child.runId === "string" && child.runId.length > 0
  ? child.runId
  : undefined;
const retainedCorrectionTask = (blockers) =>
  "Continue the original bounded correction contract with these latest typed blockers only: "
    + JSON.stringify(blockers) + "\\n\\n" + efficiencyFeedbackRequest;
const freshCorrectionTask = (blockers) => [
  "Fresh compatible correction writer selected before launch.",
  "Original ticket contract and exact execution parameters:",
  ${JSON.stringify(input.workerBrief)},
  "Latest typed blockers:",
  JSON.stringify(blockers),
  "Current lane placement:",
  lane
].join("\\n\\n");
const runCorrection = (key, resumeTarget, blockers) =>
  retainedCorrection && resumeTarget !== undefined
    ? runs.run(key, { resume: resumeTarget, task: retainedCorrectionTask(blockers) })
    : runFreshChild(key, "collab-implementer", freshCorrectionTask(blockers), workerSchema);
const projectNeedsDecision = (child) => {
  const base = {
    outcome: "NEEDS_DECISION",
    why: child.structuredOutput.decision.why,
    question: child.structuredOutput.decision.question
  };
  if (Array.isArray(child.structuredOutput.residualRisks) && child.structuredOutput.residualRisks.length > 0) base.residualRisks = child.structuredOutput.residualRisks;
  else if (Array.isArray(child.structuredOutput.residualRisks)) base.residualRisks = [];
  return base;
};
const projectWorkerStop = (child) => {
  if (child.structuredOutput.outcome === "BLOCKED") {
    const out = { outcome: "BLOCKED", blocker: child.structuredOutput.blocker };
    if (Array.isArray(child.structuredOutput.residualRisks)) out.residualRisks = child.structuredOutput.residualRisks;
    return out;
  }
  return projectNeedsDecision(child);
};
const boundedMessage = (value) => {
  const m = value instanceof Error ? value.message : typeof value === "string" ? value : "unknown error";
  return m.replace(/[\\r\\n]+/g, " ").slice(0, 300);
};
const isInterruptionError = (err) => err && (err.name === "AbortError" || err.code === "ABORT_ERR" || err.code === "INTERRUPTED" || err.interrupted === true || err.stopped === true);
const MAX_REVIEWER_RECOVERY_ATTEMPTS = 2;
const hasRunsAll = typeof runs.all === "function";
const runReviewerWithRecovery = (baseKey, task, phase) => {
  let lastError = null;
  const attemptReviewer = (attempt) => {
    const attemptKey = attempt === 0 ? baseKey : baseKey + "-retry-" + attempt;
    if (hasRunsAll) {
      return runs.all([{key: attemptKey, agent: "collab-acceptor", cwd: lane, worktree: false, context: "fresh", task, outputSchema: reviewerSchema}]).then((results) => {
        const child = results[0];
        if (child.interrupted === true || child.stopped === true) {
          const err = new Error(child.error || child.output || (child.interrupted ? "reviewer interrupted" : "reviewer stopped"));
          err.name = "AbortError";
          err.code = child.interrupted ? "INTERRUPTED" : "STOPPED";
          if (child.interrupted) err.interrupted = true;
          if (child.stopped) err.stopped = true;
          throw err;
        }
        if (child.ok === true) {
          if (child.structuredOutput && (child.structuredOutput.verdict === "PASS" || child.structuredOutput.verdict === "BLOCKED" || child.structuredOutput.verdict === "NEEDS_DECISION")) {
            return child;
          }
          const msg = boundedMessage(child.error || "reviewer returned invalid structured output");
          const invErr = new Error(msg);
          invErr.code = "INVALID_CHILD_RESULT";
          throw invErr;
        }
        lastError = child.error || child.output || "reviewer runtime failure";
        if (attempt === MAX_REVIEWER_RECOVERY_ATTEMPTS) {
          const bounded = boundedMessage(lastError);
          throw { __reviewerRecoveryExhausted: true, phase, error: bounded, attempts: MAX_REVIEWER_RECOVERY_ATTEMPTS + 1 };
        }
        return attemptReviewer(attempt + 1);
      }).catch((e) => {
        if (e && e.__reviewerRecoveryExhausted) throw e;
        if (isInterruptionError(e)) throw e;
        throw e;
      });
    }
    return runFreshChild(attemptKey, "collab-acceptor", task, reviewerSchema).catch((e) => {
      if (isInterruptionError(e)) throw e;
      lastError = e;
      if (attempt === MAX_REVIEWER_RECOVERY_ATTEMPTS) {
        const bounded = boundedMessage(lastError);
        throw { __reviewerRecoveryExhausted: true, phase, error: bounded, attempts: MAX_REVIEWER_RECOVERY_ATTEMPTS + 1 };
      }
      return attemptReviewer(attempt + 1);
    });
  };
  return attemptReviewer(0);
};
let writer = await runFreshChild("impl-0", "collab-implementer", ${JSON.stringify(input.workerBrief)}, workerSchema);
if (writer.structuredOutput.outcome !== "COMPLETED") {
  const ws = projectWorkerStop(writer);
  return ws;
}
let resumeTarget = successfulRunId(writer);
const mergeResidualRisks = (a, b) => {
  const aw = Array.isArray(a) ? a : [];
  const bw = Array.isArray(b) ? b : [];
  const merged = [...aw, ...bw];
  return merged;
};
const correctionBaseOf = (rev) => {
  const cb = rev.structuredOutput.correctionBase;
  if (typeof cb !== "string" || cb.trim().length === 0) {
    const msg = "reviewer BLOCKED missing required correctionBase";
    const err = new Error(msg);
    err.code = "INVALID_CHILD_RESULT";
    throw err;
  }
  return cb;
};
let reviewer;
try {
  reviewer = await runReviewerWithRecovery("review-0", ${JSON.stringify(input.reviewBrief)} + "\\n\\n" + initialReviewerBaseline, "REVIEW");
} catch (e) {
  if (e && e.__reviewerRecoveryExhausted) {
    const out = { outcome: "REVIEWER_RUNTIME_RECOVERY_EXHAUSTED", phase: e.phase, error: e.error };
    if (writer && Array.isArray(writer.structuredOutput.residualRisks)) out.residualRisks = writer.structuredOutput.residualRisks;
    return out;
  }
  throw e;
}
if (reviewer.structuredOutput.verdict === "NEEDS_DECISION") {
  const nd = projectNeedsDecision(reviewer);
  if (writer && Array.isArray(writer.structuredOutput.residualRisks) && writer.structuredOutput.residualRisks.length > 0 && (!nd.residualRisks || nd.residualRisks.length === 0)) {
    // preserve available risks: latest worker then final reviewer already handled in projectNeedsDecision, but also ensure worker risks are preserved on reviewer decision branch
    const merged = mergeResidualRisks(writer.structuredOutput.residualRisks, reviewer.structuredOutput.residualRisks);
    if (merged.length > 0) nd.residualRisks = merged;
  } else if (writer && Array.isArray(writer.structuredOutput.residualRisks)) {
    const merged = mergeResidualRisks(writer.structuredOutput.residualRisks, reviewer.structuredOutput.residualRisks);
    if (merged.length > 0) nd.residualRisks = merged;
  }
  return nd;
}
let round = 1;
let currentCorrectionBase = null;
if (reviewer.structuredOutput.verdict === "BLOCKED") {
  currentCorrectionBase = correctionBaseOf(reviewer);
}
while (reviewer.structuredOutput.verdict === "BLOCKED" && round <= budget) {
  writer = await runCorrection(
    "impl-" + round,
    resumeTarget,
    reviewer.structuredOutput.blockers
  );
  if (writer.structuredOutput.outcome !== "COMPLETED") {
    const ws = projectWorkerStop(writer);
    // preserve latest reviewer risks on worker-stop branches
    if (reviewer && Array.isArray(reviewer.structuredOutput.residualRisks) && reviewer.structuredOutput.residualRisks.length > 0) {
      const merged = mergeResidualRisks(writer.structuredOutput.residualRisks, reviewer.structuredOutput.residualRisks);
      if (merged.length > 0) ws.residualRisks = merged;
      else if (Array.isArray(ws.residualRisks) && ws.residualRisks.length === 0) ws.residualRisks = [];
    }
    return ws;
  }
  resumeTarget = successfulRunId(writer);
  if (currentCorrectionBase === null) {
    const err = new Error("reviewer BLOCKED missing required correctionBase for rereview");
    err.code = "INVALID_CHILD_RESULT";
    throw err;
  }
  const rereviewBaseline = rereviewBaselineFor(currentCorrectionBase);
  try {
    reviewer = await runReviewerWithRecovery("review-" + round, ${JSON.stringify(input.reviewBrief)} + " — rereview the complete current lane diff against retained correctionBase.\\n\\n" + rereviewBaseline + "\\n\\nPrior blockers: " + JSON.stringify(reviewer.structuredOutput.blockers) + "\\n\\nOriginal brief: " + ${JSON.stringify(input.reviewBrief)}, "REREVIEW");
  } catch (e) {
    if (e && e.__reviewerRecoveryExhausted) {
      const out = { outcome: "REVIEWER_RUNTIME_RECOVERY_EXHAUSTED", phase: e.phase, error: e.error };
      const merged = mergeResidualRisks(writer && writer.structuredOutput.residualRisks, reviewer && reviewer.structuredOutput.residualRisks);
      if (merged.length > 0 || (writer && Array.isArray(writer.structuredOutput.residualRisks)) || (reviewer && Array.isArray(reviewer.structuredOutput.residualRisks))) out.residualRisks = merged;
      return out;
    }
    throw e;
  }
  if (reviewer.structuredOutput.verdict === "NEEDS_DECISION") {
    const nd = projectNeedsDecision(reviewer);
    const merged = mergeResidualRisks(writer.structuredOutput.residualRisks, reviewer.structuredOutput.residualRisks);
    if (merged.length > 0) nd.residualRisks = merged;
    return nd;
  }
  if (reviewer.structuredOutput.verdict === "BLOCKED") currentCorrectionBase = correctionBaseOf(reviewer);
  round += 1;
}
if (reviewer.structuredOutput.verdict === "BLOCKED") {
  return { outcome: "CORRECTION_BUDGET_EXHAUSTED", blockers: reviewer.structuredOutput.blockers, residualRisks: mergeResidualRisks(writer.structuredOutput.residualRisks, reviewer.structuredOutput.residualRisks) };
}
return {
  outcome: "REVIEWED",
  residualRisks: mergeResidualRisks(writer.structuredOutput.residualRisks, reviewer.structuredOutput.residualRisks)
};`;
}

function subagentPreflight(error: ReviewedLaneErrorFactory): ResolveSubagentLaunchContract {
  if (resolveSubagentLaunchContract) return resolveSubagentLaunchContract;
  try {
    const agentPackage = path.join(getAgentDir(), "npm", "package.json");
    const requireFromAgentPackages = createRequire(agentPackage);
    const createJiti = requireFromAgentPackages("jiti") as (
      filename: string,
    ) => (id: string) => Record<string, unknown>;
    const api = createJiti(agentPackage)("pi-subagents/preflight");
    if (typeof api.resolveSubagentLaunchContract !== "function") throw new Error("preflight export is missing");
    resolveSubagentLaunchContract = api.resolveSubagentLaunchContract as ResolveSubagentLaunchContract;
    return resolveSubagentLaunchContract;
  } catch (cause) {
    throw error(
      "profile_unavailable",
      `pi-subagents profile preflight is unavailable: ${boundedMessage(cause)}`,
      "Install and enable pi-subagents with its public preflight API, then retry.",
    );
  }
}

function requireRpcObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function requiredReceiptString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

export async function runReviewedLane(
  pi: ExtensionAPI,
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  ctx: ExtensionContext,
  dependencies: ReviewedLaneDependencies,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const taskId = dependencies.requireTaskId(request.task_id);
  const ticketId = requireDevFlowTicketIdentifier(request.ticket_id, dependencies.error);
  const laneId = dependencies.requireLaneId(request.lane_id);
  const workerBrief = requireReviewedLaneBrief(request.worker_brief, "worker brief", dependencies.error);
  const reviewBrief = requireReviewedLaneBrief(request.review_brief, "review brief", dependencies.error);
  const correctionBudget = requireCorrectionBudget(request.correction_budget, dependencies.error);

  const repo = await dependencies.discoverRepository(run, cwd, signal);
  const task = dependencies.createTask(repo, taskId);
  const integration = await dependencies.requireManagedIntegration(repo, task, signal);
  const inventory = await dependencies.laneInventory(repo, task, laneId, signal, integration.records);
  if (!dependencies.laneIsComplete(inventory)) {
    throw dependencies.error(
      "worktree_identity_mismatch",
      `managed lane ${taskId}/${laneId} does not match its canonical branch and worktree`,
      "Restore or recreate the exact managed lane at its canonical path before launching review work.",
    );
  }
  const lane = inventory.lanePath;
  const canonicalKey = canonicalLaneKey(repo.controlRoot, taskId, laneId);
  if (activeLaneReservations.has(canonicalKey)) {
    throw dependencies.error(
      "reviewed_lane_active",
      `reviewed lane ${taskId}/${laneId} is already active for this repository`,
      "Wait for the correlated terminal settlement to release the lane before relaunching.",
      { task_id: taskId, lane_id: laneId, repo_control_root: repo.controlRoot },
    );
  }
  activeLaneReservations.set(canonicalKey, {
    pi,
    repo,
    taskId,
    ticketId,
    laneId,
    lanePath: lane,
    workflowId: "",
    asyncDir: "",
    deps: dependencies,
    canonicalKey,
  });
  const workerTask = `Task ${taskId}; ticket ${ticketId}; managed lane ${lane}.\n\n${workerBrief}`;
  const reviewerTask = `Task ${taskId}; ticket ${ticketId}; protected managed lane ${lane}.\n\n${reviewBrief}`;

  let _spawnedWorkflowId: string | undefined;
  let _spawnedAsyncDir: string | undefined;
  let _spawnedAsyncId: string | undefined;
  try {
  const preflight = subagentPreflight(dependencies.error);
  const availableModels = ctx.modelRegistry?.getAvailable?.();
  const roleSpecs: ReviewedLaneRoleSpec[] = [
    {
      agent: "collab-implementer",
      task: workerTask,
      outputSchema: reviewedLaneWorkerSchema,
      agentContract: { version: 1 },
    },
    {
      agent: "collab-acceptor",
      task: reviewerTask,
      outputSchema: reviewedLaneReviewerSchema,
    },
  ];
  const preflightResults = await Promise.all(
    roleSpecs.map(async (spec) => {
      try {
        return {
          spec,
          result: await preflight({
            agent: spec.agent,
            cwd: lane,
            task: spec.task,
            context: "fresh",
            outputSchema: spec.outputSchema,
            ...(spec.agentContract ? { agentContract: spec.agentContract } : {}),
            ...(availableModels ? { availableModels } : {}),
          }),
        };
      } catch (cause) {
        throw dependencies.error(
          "profile_unavailable",
          `${spec.agent} profile preflight could not resolve its launch contract: ${boundedMessage(cause)}`,
          `Correct the ${spec.agent} profile so pi-subagents public preflight can resolve it, then retry.`,
        );
      }
    }),
  );
  const expectedLaneCwd = path.resolve(lane);
  for (const { spec, result } of preflightResults) {
    if (result.ok !== true) {
      const message = "message" in result ? result.message : "unknown preflight error";
      throw dependencies.error(
        "profile_unavailable",
        `${spec.agent} profile is unavailable: ${boundedMessage(message)}`,
        `Enable an executable ${spec.agent} profile and its required capabilities, then retry.`,
      );
    }
    if (result.contract?.inheritProjectContext !== true) {
      throw dependencies.error(
        "project_context_unavailable",
        `${spec.agent} profile does not deterministically inherit project context for the managed lane`,
        `Set inheritProjectContext: true on the resolved ${spec.agent} profile, then retry.`,
      );
    }
    if (result.contract.roots?.cwd !== expectedLaneCwd) {
      throw dependencies.error(
        "project_context_unavailable",
        `${spec.agent} profile preflight did not bind project context to the exact managed lane cwd`,
        `Resolve the ${spec.agent} profile against the canonical managed lane cwd, then retry.`,
      );
    }
  }

  const ping = await callSubagentRpc(pi, "ping", {}, dependencies.error, signal);
  const pingData = requireRpcObject(ping.data);
  const methods = Array.isArray(pingData.methods) ? pingData.methods : [];
  const capabilities = requireRpcObject(pingData.capabilities);
  if (
    ping.version !== SUBAGENT_RPC_VERSION ||
    ping.success !== true ||
    pingData.version !== SUBAGENT_RPC_VERSION ||
    !methods.includes("spawn") ||
    capabilities.asyncSpawn !== true
  ) {
    throw dependencies.error(
      "unsupported_rpc",
      "pi-subagents Extension RPC v1 async spawn capability is unavailable",
      "Enable a pi-subagents version that advertises RPC v1 spawn and asyncSpawn, then retry.",
    );
  }
  const foregroundStructuredResume = requireRpcObject(
    capabilities.foregroundStructuredResume,
  );
  const retainedCorrection =
    foregroundStructuredResume.version === 1
    && foregroundStructuredResume.recoveryDescriptorVersion === 1;

  const spawned = await callSubagentRpc(pi, "spawn", {
    cwd: lane,
    workflowScript: reviewedLaneWorkflowScript({
      lane,
      workerBrief: workerTask,
      reviewBrief: reviewerTask,
      correctionBudget,
      retainedCorrection,
      integrationTip: integration.tip,
    }),
    async: true,
  }, dependencies.error, signal);
  if (spawned.version !== SUBAGENT_RPC_VERSION || spawned.success !== true) {
    const rpcError = spawned.error && typeof spawned.error === "object"
      ? boundedMessage((spawned.error as Record<string, unknown>).message)
      : "spawn failed";
    throw dependencies.error(
      "rpc_spawn_failed",
      `pi-subagents could not launch the reviewed-lane workflow: ${rpcError}`,
      "Correct the reported pi-subagents launch condition and retry; no fallback launcher is used.",
    );
  }
  const spawnData = requireRpcObject(spawned.data);
  const details = requireRpcObject(spawnData.details);
  const runId = requiredReceiptString(details.runId)
    ?? requiredReceiptString(details.asyncId);
  const asyncId = requiredReceiptString(details.asyncId);
  const asyncDir = requiredReceiptString(details.asyncDir);
  if (!runId || !asyncId || !asyncDir) {
    throw dependencies.error(
      "rpc_spawn_failed",
      "pi-subagents spawn returned no correlated asynchronous workflow receipt",
      "Use a pi-subagents RPC implementation that returns runId (or correlated asyncId) and asyncDir for spawn.",
    );
  }
  _spawnedWorkflowId = runId;
  _spawnedAsyncDir = asyncDir;
  _spawnedAsyncId = asyncId;
  const active = activeLaneReservations.get(canonicalKey);
  if (active) {
    active.workflowId = runId;
    active.asyncDir = asyncDir;
  }
  registerPendingReviewedLane({
    pi,
    repo,
    taskId,
    ticketId,
    laneId,
    lanePath: lane,
    workflowId: runId,
    asyncDir,
    deps: dependencies,
    canonicalKey,
  });
  return { workflow_id: runId, async_id: asyncId, async_dir: asyncDir };
  } catch (e) {
    const method = (e as unknown as Record<string, unknown>)?.__method as string | undefined;
    const emitted = (e as unknown as Record<string, unknown>)?.__emitted as boolean | undefined;
    const code = (e as unknown as { code?: unknown })?.code as string | undefined;
    const isAmbiguousPostEmission = method === "spawn" && emitted === true && (code === "rpc_unavailable" || code === "request_aborted");
    if (!isAmbiguousPostEmission) {
      activeLaneReservations.delete(canonicalKey);
    }
    throw e;
  }
}

type PendingReviewedLane = {
  pi: ExtensionAPI;
  repo: Repository;
  taskId: string;
  ticketId: string;
  laneId: string;
  lanePath: string;
  workflowId: string;
  asyncDir: string;
  deps: ReviewedLaneDependencies;
  canonicalKey: string;
};

function canonicalLaneKey(repoControlRoot: string, taskId: string, laneId: string): string {
  return `${path.resolve(repoControlRoot)}\0${taskId}\0${laneId}`;
}

const activeLaneReservations = new Map<string, PendingReviewedLane>();
const pendingReviewedLanes = new Map<string, PendingReviewedLane>();
let reviewedLaneListenerInstalled = false;

export function getActiveReservationCount(): number {
  return activeLaneReservations.size;
}
export function clearActiveReservationsForTest(): void {
  activeLaneReservations.clear();
}
export function clearPendingForTest(): void {
  pendingReviewedLanes.clear();
}

function registerPendingReviewedLane(pending: PendingReviewedLane): void {
  pendingReviewedLanes.set(pending.workflowId, pending);
  if (reviewedLaneListenerInstalled) return;
  reviewedLaneListenerInstalled = true;
  pending.pi.events.on("subagent:async-complete", (raw: unknown) => {
    void handleAsyncCompleteEvent(raw);
  });
}

async function processPendingEvent(map: Map<string, PendingReviewedLane>, raw: unknown, reservationMap?: Map<string, PendingReviewedLane>): Promise<void> {
  const data = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const eventWorkflowId = typeof data["runId"] === "string" ? (data["runId"] as string) : typeof data["id"] === "string" ? (data["id"] as string) : undefined;
  const eventAsyncDir = typeof data["asyncDir"] === "string" ? (data["asyncDir"] as string) : undefined;
  if (!eventWorkflowId || !eventAsyncDir) return;
  const pending = map.get(eventWorkflowId);
  if (!pending) return;
  if (pending.asyncDir !== eventAsyncDir) return;
  const reservations = reservationMap ?? activeLaneReservations;
  try {
    const result = await handleReviewedLaneCompletion({
      repoControlRoot: pending.repo.controlRoot,
      taskId: pending.taskId,
      ticketId: pending.ticketId,
      laneId: pending.laneId,
      lanePath: pending.lanePath,
      workflowId: pending.workflowId,
      asyncDir: pending.asyncDir,
      eventWorkflowId,
      eventAsyncDir,
      withTaskLock: <T>(body: () => Promise<T>) => pending.deps.withTaskLock(pending.repo, pending.taskId, body),
    } as any);
    if (result.handled) {
      map.delete(eventWorkflowId);
      reservations.delete(pending.canonicalKey);
    }
  } catch (e) {
    try { console.warn(`[collab-reviewed-lane] ${boundedMessage(e).slice(0, 500)}`); } catch {}
    map.delete(eventWorkflowId);
    reservations.delete(pending.canonicalKey);
  }
}

export async function handleAsyncCompleteEvent(raw: unknown): Promise<void> {
  await processPendingEvent(pendingReviewedLanes, raw);
}

export function createIsolatedReviewedLaneHarness() {
  const isolatedPending = new Map<string, PendingReviewedLane>();
  const isolatedReservations = new Map<string, PendingReviewedLane>();
  const installed = new Set<ExtensionAPI>();
  function ensureListener(pi: ExtensionAPI) {
    if (installed.has(pi)) return;
    installed.add(pi);
    pi.events.on("subagent:async-complete", (raw: unknown) => {
      void processPendingEvent(isolatedPending, raw, isolatedReservations);
    });
  }
  return {
    registerPending(pending: PendingReviewedLane) {
      isolatedPending.set(pending.workflowId, pending);
      isolatedReservations.set(pending.canonicalKey, pending);
      ensureListener(pending.pi);
    },
    handleAsyncCompleteEvent(raw: unknown) {
      return processPendingEvent(isolatedPending, raw, isolatedReservations);
    },
    getPendingCount() {
      return isolatedPending.size;
    },
    getReservationCount() {
      return isolatedReservations.size;
    },
    clearPending() {
      isolatedPending.clear();
    },
    clearReservations() {
      isolatedReservations.clear();
    },
    emitViaPi(pi: ExtensionAPI, event: unknown) {
      pi.events.emit("subagent:async-complete", event);
    },
  };
}

export default function collabReviewedLaneCompanion(): void {}
