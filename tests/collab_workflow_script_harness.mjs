#!/usr/bin/env node
import fs from "node:fs/promises";

const [capturePath, stepsJson] = process.argv.slice(2);
if (!capturePath || !stepsJson) throw new Error("usage: harness CAPTURE_PATH STEPS_JSON");
const lines = (await fs.readFile(capturePath, "utf8")).trim().split("\n");
const request = JSON.parse(lines.at(-1));
const script = request.params.workflowScript;
const steps = JSON.parse(stepsJson);
const calls = [];
let index = 0;
const runs = {
  async run(key, options) {
    calls.push({ key, options });
    const step = steps[index++];
    const wrapped = step && typeof step === "object" && !Array.isArray(step)
      && Object.prototype.hasOwnProperty.call(step, "structuredOutput");
    const structuredOutput = wrapped ? step.structuredOutput : step;
    if (wrapped && step.noMutationStop === true && options.agentContract?.version !== 1) {
      throw new Error("Subagent completed without making edits for an implementation task.");
    }
    const mutationStatus = wrapped && typeof step.mutationStatus === "string"
      ? step.mutationStatus
      : "not-applicable";
    return {
      structuredOutput,
      output: "ignored free-form output",
      results: [{ effects: { fileMutation: { status: mutationStatus } } }],
    };
  },
};
const execute = Function("runs", `return (async () => {\n${script}\n})()`);
const result = await execute(runs);
process.stdout.write(JSON.stringify({ result, calls }));
