#!/usr/bin/env node
import fs from "node:fs/promises";

const [capturePath, stepsJson] = process.argv.slice(2);
if (!capturePath || !stepsJson) throw new Error("usage: harness CAPTURE_PATH STEPS_JSON");
const lines = (await fs.readFile(capturePath, "utf8")).trim().split("\n");
const request = JSON.parse(lines.at(-1));
const script = request.params.workflowScript;
const steps = JSON.parse(stepsJson);
const calls = [];
const successfulWriterRuns = new Set();
let index = 0;

function envelopeFromStep(step, key, options) {
  // If step explicitly defines envelope shape (has ok, interrupted, stopped, error, etc.)
  const hasEnvelopeShape = step && typeof step === "object" && !Array.isArray(step) && ("ok" in step || "interrupted" in step || "stopped" in step || "detached" in step);
  if (hasEnvelopeShape) {
    const ok = typeof step.ok === "boolean" ? step.ok : !(step.interrupted || step.stopped);
    const runId = typeof step.runId === "string" ? step.runId : `run-${index}`;
    const structuredOutput = step.structuredOutput !== undefined ? step.structuredOutput : (ok ? step : undefined);
    // If step has thrown but we are in all, treat as envelope failure
    const error = typeof step.error === "string" ? step.error : (typeof step.throwMessage === "string" ? step.throwMessage : undefined);
    const output = typeof step.output === "string" ? step.output : error || "output";
    const envelope = {
      key,
      ok,
      ...(typeof step.agent === "string" ? {agent: step.agent} : (options.agent ? {agent: options.agent} : {})),
      ...(runId ? {runId} : {}),
      output: output || "",
      ...(error ? {error} : {}),
      ...(step.interrupted ? {interrupted: true} : {}),
      ...(step.stopped ? {stopped: true} : {}),
      ...(step.detached ? {detached: true} : {}),
      ...(ok && structuredOutput !== undefined ? {structuredOutput} : {}),
      ...(!ok && step.structuredOutput !== undefined ? {structuredOutput: step.structuredOutput} : {}),
      artifactPaths: Array.isArray(step.artifactPaths) ? step.artifactPaths : [],
      results: step.results || [],
    };
    // Ensure structuredOutput for ok true is correct
    if (ok && !envelope.structuredOutput && step && typeof step === "object" && !("structuredOutput" in step) && !("ok" in step)) {
      envelope.structuredOutput = step;
    }
    return envelope;
  }
  const wrapped = step && typeof step === "object" && !Array.isArray(step)
    && Object.prototype.hasOwnProperty.call(step, "structuredOutput");
  if (wrapped && typeof step.throwMessage === "string") {
    // For runs.run this was throw, for runs.all this becomes envelope failure
    // But we need to know caller context: if called via run, throw; if via all, envelope
    // This helper is for all, so return envelope
    return {
      key,
      ok: false,
      error: step.throwMessage,
      output: step.throwMessage,
      artifactPaths: [],
      results: [],
    };
  }
  if (wrapped) {
    const structuredOutput = step.structuredOutput;
    const runId = typeof step.runId === "string" ? step.runId : `run-${index}`;
    const mutationStatus = typeof step.mutationStatus === "string" ? step.mutationStatus : "not-applicable";
    const resumesWriter = Object.prototype.hasOwnProperty.call(options, "resume");
    if (resumesWriter && !successfulWriterRuns.has(options.resume)) {
      throw new Error(`resume target was not a successful earlier writer: ${String(options.resume)}`);
    }
    if (structuredOutput?.outcome === "COMPLETED"
      && (resumesWriter || options.agent === "collab-implementer")) {
      successfulWriterRuns.add(runId);
    }
    // For successful via all, still need envelope
    return {
      key,
      ok: true,
      runId,
      structuredOutput,
      output: "ignored free-form output",
      artifactPaths: [],
      results: [{ effects: { fileMutation: { status: mutationStatus } } }],
    };
  }
  // Direct structuredOutput case (reviewer success)
  if (step && typeof step === "object" && !Array.isArray(step) && ("verdict" in step || "outcome" in step)) {
    const runId = `run-${index}`;
    return {
      key,
      ok: true,
      runId,
      structuredOutput: step,
      output: "ignored free-form output",
      artifactPaths: [],
      results: [],
    };
  }
  // Fallback: treat step as envelope failure if it looks like error
  if (step && typeof step === "object" && step !== null && typeof step.error === "string") {
    return {
      key,
      ok: false,
      error: step.error,
      output: step.error,
      artifactPaths: [],
      results: [],
    };
  }
  // Default: if step is null/undefined, treat as failure
  if (step === null || step === undefined) {
    return {
      key,
      ok: false,
      error: "null child result",
      output: "null child result",
      artifactPaths: [],
      results: [],
    };
  }
  // Default envelope for other shapes
  return {
    key,
    ok: true,
    runId: `run-${index}`,
    structuredOutput: step,
    output: "ignored free-form output",
    artifactPaths: [],
    results: [],
  };
}

const runs = {
  async run(key, options) {
    calls.push({ key, options });
    const step = steps[index++];
    const wrapped = step && typeof step === "object" && !Array.isArray(step)
      && Object.prototype.hasOwnProperty.call(step, "structuredOutput");
    if (wrapped && typeof step.throwMessage === "string") {
      throw new Error(step.throwMessage);
    }
    // Handle explicit envelope for run (interrupted etc.) - if step has ok/interrupted/stopped, we should return envelope but run should throw for ok false?
    // For run, host would throw for ok false (except stopped). But our harness for run should mimic that: if envelope indicates failure, throw.
    const hasEnvelopeShape = step && typeof step === "object" && !Array.isArray(step) && ("ok" in step || "interrupted" in step || "stopped" in step);
    if (hasEnvelopeShape) {
      const envelope = envelopeFromStep(step, key, options);
      if (envelope.ok === false && envelope.stopped !== true) {
        const err = new Error(envelope.error || envelope.output || "child failed");
        if (envelope.interrupted) { err.name = "AbortError"; err.code = "INTERRUPTED"; err.interrupted = true; }
        else if (envelope.stopped) { err.name = "AbortError"; err.code = "STOPPED"; err.stopped = true; }
        throw err;
      }
      // For stopped, return envelope (not throw) - matches host behavior for run with stopped
      if (envelope.stopped === true) {
        return envelope;
      }
      // For ok true, return envelope shape but with runId etc.
      return envelope;
    }
    const structuredOutput = wrapped ? step.structuredOutput : step;
    if (wrapped && step.noMutationStop === true && options.agentContract?.version !== 1) {
      throw new Error("Subagent completed without making edits for an implementation task.");
    }
    const mutationStatus = wrapped && typeof step.mutationStatus === "string"
      ? step.mutationStatus
      : "not-applicable";
    const runId = wrapped && typeof step.runId === "string" ? step.runId : `run-${index}`;
    const resumesWriter = Object.prototype.hasOwnProperty.call(options, "resume");
    if (resumesWriter && !successfulWriterRuns.has(options.resume)) {
      throw new Error(`resume target was not a successful earlier writer: ${String(options.resume)}`);
    }
    if (structuredOutput?.outcome === "COMPLETED"
      && (resumesWriter || options.agent === "collab-implementer")) {
      successfulWriterRuns.add(runId);
    }
    // Handle throwMessage for wrapped case already above, but also for direct step with throwMessage
    if (step && typeof step === "object" && typeof step.throwMessage === "string" && !wrapped) {
      throw new Error(step.throwMessage);
    }
    return {
      runId,
      structuredOutput,
      output: "ignored free-form output",
      results: [{ effects: { fileMutation: { status: mutationStatus } } }],
    };
  },
  async all(items) {
    if (!Array.isArray(items)) throw new Error("runs.all requires array");
    const results = [];
    for (const item of items) {
      const {key, ...options} = item;
      calls.push({ key, options });
      const step = steps[index++];
      // Detect if step is envelope with throwMessage: treat as failure envelope for all
      if (step && typeof step === "object" && typeof step.throwMessage === "string" && !("ok" in step) && !("interrupted" in step) && !("stopped" in step)) {
        results.push({
          key,
          ok: false,
          error: step.throwMessage,
          output: step.throwMessage,
          artifactPaths: [],
          results: [],
          ...(step.structuredOutput !== undefined ? {structuredOutput: step.structuredOutput} : {}),
        });
        continue;
      }
      const envelope = envelopeFromStep(step, key, options);
      // For all, we return envelope directly (including ok false) without throwing, matching host collectFailure true
      // But need to handle successfulWriterRuns for writer via all? Not needed, but preserve
      if (envelope.structuredOutput?.outcome === "COMPLETED" && options.agent === "collab-implementer") {
        if (envelope.runId) successfulWriterRuns.add(envelope.runId);
      }
      // Check for validation that would throw before launch? Not simulated
      results.push(envelope);
    }
    // Wrap to prevent keyed access errors like host does
    // But for test, just return results array
    return results;
  },
  async status(keyOrRunId) {
    // Not used in harness
    throw new Error("runs.status not implemented in harness");
  },
  async steer(key, message, options) {
    throw new Error("runs.steer not implemented");
  }
};
const execute = Function("runs", `return (async () => {\n${script}\n})()`);
try {
  const result = await execute(runs);
  process.stdout.write(JSON.stringify({ result, calls }));
} catch (error) {
  // Preserve error details for interruption markers
  const errObj = error && typeof error === "object" ? {...error, message: String(error.message ?? error), name: error.name, code: error.code, interrupted: error.interrupted, stopped: error.stopped, __reviewerRecoveryExhausted: error.__reviewerRecoveryExhausted, phase: error.phase, error: error.error} : {message: String(error)};
  process.stdout.write(JSON.stringify({ error: String(error?.message ?? error), errorDetails: errObj, calls }));
  console.error(error);
  process.exitCode = 1;
}
