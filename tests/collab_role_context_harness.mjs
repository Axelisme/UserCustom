#!/usr/bin/env node
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const [capturePath, piPackagePath, agentPackagePath, agentDir, marker] = process.argv.slice(2);
if (!capturePath || !piPackagePath || !agentPackagePath || !agentDir || !marker) {
  throw new Error("usage: harness CAPTURE PI_PACKAGE AGENT_PACKAGE AGENT_DIR MARKER");
}

const lines = (await fs.readFile(capturePath, "utf8")).trim().split("\n");
const request = JSON.parse(lines.at(-1));
const script = request.params.workflowScript;
const piSdk = await import(pathToFileURL(piPackagePath).href);
const requireFromAgentPackages = createRequire(agentPackagePath);
const createJiti = requireFromAgentPackages("jiti");
const { resolveSubagentLaunchContract } = createJiti(agentPackagePath)("pi-subagents/preflight");
const observations = [];

function executionParameters(task) {
  const prefix = "Execution parameters JSON: ";
  const line = task.split("\n").find((candidate) => candidate.startsWith(prefix));
  if (!line) throw new Error("role task omitted exact execution parameters");
  const parsed = JSON.parse(line.slice(prefix.length));
  if (typeof parsed.runtime !== "string" || !Array.isArray(parsed.args)) {
    throw new Error("role task supplied malformed execution parameters");
  }
  if (!parsed.environment || typeof parsed.environment !== "object" || Array.isArray(parsed.environment)) {
    throw new Error("role task supplied malformed environment parameters");
  }
  return parsed;
}

const runs = {
  async run(key, options) {
    const resolved = await resolveSubagentLaunchContract({
      agent: options.agent,
      cwd: options.cwd,
      task: options.task,
      context: options.context,
      outputSchema: options.outputSchema,
      ...(options.agentContract ? { agentContract: options.agentContract } : {}),
    });
    if (!resolved.ok) throw new Error(resolved.message);
    if (resolved.contract.inheritProjectContext !== true) {
      throw new Error(`${options.agent} did not inherit project context`);
    }
    if (resolved.contract.roots.cwd !== options.cwd) {
      throw new Error(`${options.agent} resolved the wrong cwd`);
    }

    const loader = new piSdk.DefaultResourceLoader({
      cwd: resolved.contract.roots.cwd,
      agentDir,
      noExtensions: true,
      noSkills: true,
      noPromptTemplates: true,
      noThemes: true,
      noContextFiles: !resolved.contract.inheritProjectContext,
    });
    await loader.reload();
    const { session } = await piSdk.createAgentSession({
      cwd: resolved.contract.roots.cwd,
      resourceLoader: loader,
      sessionManager: piSdk.SessionManager.inMemory(),
      tools: [],
    });
    const effectiveSystemPrompt = session.systemPrompt;
    session.dispose();
    if (!effectiveSystemPrompt.includes(marker)) {
      throw new Error(`${options.agent} effective context omitted the lane marker`);
    }

    const execution = executionParameters(options.task);
    const command = spawnSync(execution.runtime, execution.args, {
      cwd: resolved.contract.roots.cwd,
      env: execution.environment,
      encoding: "utf8",
    });
    if (command.status !== 0) {
      throw new Error(`${options.agent} execution failed: ${command.stderr || command.error || command.status}`);
    }
    const commandObservation = JSON.parse(command.stdout);
    observations.push({
      key,
      agent: options.agent,
      context: resolved.contract.context,
      cwd: resolved.contract.roots.cwd,
      markerObserved: true,
      execution,
      commandObservation,
    });

    if (options.agent === "collab-implementer") {
      return {
        structuredOutput: {
          outcome: "COMPLETED",
          validation: [{ check: "fixture command", result: "PASSED", summary: "exact execution parameters consumed" }],
          efficiencyFeedback: "Public preflight and inherited effective context were sufficient; no repository-instruction reread was needed.",
        },
        results: [{ effects: { fileMutation: { status: "observed" } } }],
      };
    }
    return {
      structuredOutput: {
        verdict: "PASS",
        efficiencyFeedback: "Fresh context exposed the lane marker and cwd directly without environment discovery.",
      },
      results: [{ effects: { fileMutation: { status: "not-applicable" } } }],
    };
  },
};

const execute = Function("runs", `return (async () => {\n${script}\n})()`);
const result = await execute(runs);
process.stdout.write(JSON.stringify({ result, observations }));
