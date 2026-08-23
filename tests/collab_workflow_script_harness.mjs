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
const runs = {
  async run(key, options) {
    calls.push({ key, options });
    const step = steps[index++];
    const wrapped = step && typeof step === "object" && !Array.isArray(step)
      && Object.prototype.hasOwnProperty.call(step, "structuredOutput");
    if (wrapped && typeof step.throwMessage === "string") {
      throw new Error(step.throwMessage);
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
    return {
      runId,
      structuredOutput,
      output: "ignored free-form output",
      results: [{ effects: { fileMutation: { status: mutationStatus } } }],
    };
  },
};
const execute = Function("runs", `return (async () => {\n${script}\n})()`);
try {
  const result = await execute(runs);
  process.stdout.write(JSON.stringify({ result, calls }));
} catch (error) {
  process.stdout.write(JSON.stringify({ error: String(error?.message ?? error), calls }));
  console.error(error);
  process.exitCode = 1;
}
