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
    const structuredOutput = steps[index++];
    return { structuredOutput, output: "ignored free-form output" };
  },
};
const execute = Function("runs", `return (async () => {\n${script}\n})()`);
const result = await execute(runs);
process.stdout.write(JSON.stringify({ result, calls }));
