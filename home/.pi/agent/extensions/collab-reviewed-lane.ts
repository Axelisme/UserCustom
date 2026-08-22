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
import { handleReviewedLaneCompletion } from "./collab-report.ts";
import {
  reviewedLaneWorkerSchema,
  reviewedLaneReviewerSchema,
} from "./collab-result-schema.ts";

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
  description: "Launch one implement-and-review workflow with bounded fresh correction rounds in an existing managed lane.",
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

type ResolveSubagentLaunchContract = (input: {
  agent: string;
  cwd: string;
  task: string;
  context: "fresh";
  outputSchema: Record<string, unknown>;
  agentContract?: { version: 1 };
  availableModels?: readonly unknown[];
}) => Promise<{ ok: true } | { ok: false; message: string }>;

type ReviewedLaneRoleSpec = {
  agent: "collab-implementer" | "collab-acceptor";
  task: string;
  outputSchema: Record<string, unknown>;
  agentContract?: { version: 1 };
};

let resolveSubagentLaunchContract: ResolveSubagentLaunchContract | undefined;

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
    const cleanup = () => {
      if (typeof unsubscribe === "function") unsubscribe();
      clearTimeout(timer);
      signal?.removeEventListener("abort", aborted);
    };
    const fail = (failure: Error) => {
      cleanup();
      reject(failure);
    };
    const aborted = () => fail(error(
      "request_aborted",
      "reviewed-lane launch was aborted before RPC completion",
      "Retry the launch after the caller is ready to keep the request active.",
    ));
    const timer = setTimeout(() => fail(error(
      "rpc_unavailable",
      `pi-subagents did not answer the ${method} RPC request`,
      "Enable pi-subagents with Extension RPC v1 support, then retry.",
    )), method === "ping" ? 2000 : 15000);
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

export function reviewedLaneWorkflowScript(input: {
  lane: string;
  workerBrief: string;
  reviewBrief: string;
  correctionBudget: number;
}): string {
  const workerSchema = JSON.stringify(reviewedLaneWorkerSchema);
  const reviewerSchema = JSON.stringify(reviewedLaneReviewerSchema);
  return `
const budget = ${input.correctionBudget};
const lane = ${JSON.stringify(input.lane)};
const workerSchema = ${workerSchema};
const reviewerSchema = ${reviewerSchema};
const runChild = (key, agent, task, outputSchema) => runs.run(key, {
  agent,
  cwd: lane,
  worktree: false,
  context: "fresh",
  task,
  outputSchema,
  ...(agent === "collab-implementer" ? { agentContract: { version: 1 } } : {})
});
const completedWriterHasMutation = (child) => child.results?.some(
  (result) => result.effects?.fileMutation?.status === "observed"
    || result.effects?.fileMutation?.attempted === true
    || result.observedMutationAttempt === true
) === true;
const requireCompletedWriterMutation = (child) => {
  if (child.structuredOutput.outcome === "COMPLETED" && !completedWriterHasMutation(child)) {
    throw new Error("A COMPLETED collab-implementer result requires an observed file mutation.");
  }
};
const projectNeedsDecision = (child) => ({
  outcome: "NEEDS_DECISION",
  why: child.structuredOutput.decision.why,
  question: child.structuredOutput.decision.question
});
const projectWorkerStop = (child) => child.structuredOutput.outcome === "BLOCKED"
  ? { outcome: "BLOCKED", blocker: child.structuredOutput.blocker }
  : projectNeedsDecision(child);
let writer = await runChild("impl-0", "collab-implementer", ${JSON.stringify(input.workerBrief)}, workerSchema);
if (writer.structuredOutput.outcome !== "COMPLETED") return projectWorkerStop(writer);
requireCompletedWriterMutation(writer);
let reviewer = await runChild("review-0", "collab-acceptor", ${JSON.stringify(input.reviewBrief)}, reviewerSchema);
if (reviewer.structuredOutput.verdict === "NEEDS_DECISION") return projectNeedsDecision(reviewer);
let round = 1;
while (reviewer.structuredOutput.verdict === "BLOCKED" && round <= budget) {
  writer = await runChild(
    "impl-" + round,
    "collab-implementer",
    "Round " + round + " correction within the original bounded worker contract: " + ${JSON.stringify(input.workerBrief)} + " — current typed blockers: " + JSON.stringify(reviewer.structuredOutput.blockers),
    workerSchema
  );
  if (writer.structuredOutput.outcome !== "COMPLETED") return projectWorkerStop(writer);
  requireCompletedWriterMutation(writer);
  reviewer = await runChild(
    "review-" + round,
    "collab-acceptor",
    ${JSON.stringify(input.reviewBrief)} + " — rereview the changed protected current lane",
    reviewerSchema
  );
  if (reviewer.structuredOutput.verdict === "NEEDS_DECISION") return projectNeedsDecision(reviewer);
  round += 1;
}
if (reviewer.structuredOutput.verdict === "BLOCKED") {
  return { outcome: "CORRECTION_BUDGET_EXHAUSTED", blockers: reviewer.structuredOutput.blockers };
}
return {
  outcome: "REVIEWED",
  validation: writer.structuredOutput.validation,
  residualRisks: writer.structuredOutput.residualRisks,
  outOfEnvelopeFindings: reviewer.structuredOutput.outOfEnvelopeFindings
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
  const workerTask = `Task ${taskId}; ticket ${ticketId}; managed lane ${lane}.\n\n${workerBrief}`;
  const reviewerTask = `Task ${taskId}; ticket ${ticketId}; protected managed lane ${lane}.\n\n${reviewBrief}`;

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
    roleSpecs.map(async (spec) => ({
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
    })),
  );
  const assertPreflight = (
    agent: string,
    result: Awaited<ReturnType<typeof preflight>>,
  ): void => {
    if (result.ok !== true) {
      const message = "message" in result ? result.message : "unknown preflight error";
      throw dependencies.error(
        "profile_unavailable",
        `${agent} profile is unavailable: ${boundedMessage(message)}`,
        `Enable an executable ${agent} profile and its required capabilities, then retry.`,
      );
    }
  };
  for (const { spec, result } of preflightResults) {
    assertPreflight(spec.agent, result);
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

  const spawned = await callSubagentRpc(pi, "spawn", {
    cwd: lane,
    workflowScript: reviewedLaneWorkflowScript({
      lane,
      workerBrief: workerTask,
      reviewBrief: reviewerTask,
      correctionBudget,
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
  });
  return { workflow_id: runId, async_id: asyncId, async_dir: asyncDir };
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
};

const pendingReviewedLanes = new Map<string, PendingReviewedLane>();
let reviewedLaneListenerInstalled = false;

function registerPendingReviewedLane(pending: PendingReviewedLane): void {
  pendingReviewedLanes.set(pending.workflowId, pending);
  if (reviewedLaneListenerInstalled) return;
  reviewedLaneListenerInstalled = true;
  pending.pi.events.on("subagent:async-complete", (raw: unknown) => {
    void handleAsyncCompleteEvent(raw);
  });
}

async function processPendingEvent(map: Map<string, PendingReviewedLane>, raw: unknown): Promise<void> {
  const data = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const eventWorkflowId = typeof data["runId"] === "string" ? (data["runId"] as string) : typeof data["id"] === "string" ? (data["id"] as string) : undefined;
  const eventAsyncDir = typeof data["asyncDir"] === "string" ? (data["asyncDir"] as string) : undefined;
  if (!eventWorkflowId || !eventAsyncDir) return;
  const pending = map.get(eventWorkflowId);
  if (!pending) return;
  if (pending.asyncDir !== eventAsyncDir) return;
  try {
    const result = await pending.deps.withTaskLock(pending.repo, pending.taskId, () =>
      handleReviewedLaneCompletion({
        repoControlRoot: pending.repo.controlRoot,
        taskId: pending.taskId,
        ticketId: pending.ticketId,
        laneId: pending.laneId,
        lanePath: pending.lanePath,
        workflowId: pending.workflowId,
        asyncDir: pending.asyncDir,
        eventWorkflowId,
        eventAsyncDir,
      }),
    );
    if (result.handled) map.delete(eventWorkflowId);
  } catch (e) {
    try { console.warn(`[collab-reviewed-lane] ${boundedMessage(e).slice(0, 500)}`); } catch {}
    map.delete(eventWorkflowId);
  }
}

export async function handleAsyncCompleteEvent(raw: unknown): Promise<void> {
  await processPendingEvent(pendingReviewedLanes, raw);
}

export function createIsolatedReviewedLaneHarness() {
  const isolatedPending = new Map<string, PendingReviewedLane>();
  const installed = new Set<ExtensionAPI>();
  function ensureListener(pi: ExtensionAPI) {
    if (installed.has(pi)) return;
    installed.add(pi);
    pi.events.on("subagent:async-complete", (raw: unknown) => {
      void processPendingEvent(isolatedPending, raw);
    });
  }
  return {
    registerPending(pending: PendingReviewedLane) {
      isolatedPending.set(pending.workflowId, pending);
      ensureListener(pending.pi);
    },
    handleAsyncCompleteEvent(raw: unknown) {
      return processPendingEvent(isolatedPending, raw);
    },
    getPendingCount() {
      return isolatedPending.size;
    },
    clearPending() {
      isolatedPending.clear();
    },
    emitViaPi(pi: ExtensionAPI, event: unknown) {
      pi.events.emit("subagent:async-complete", event);
    },
  };
}

export default function collabReviewedLaneCompanion(): void {}
