import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { findPackageJSON } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const entry = process.env.PI_TEST_PACKAGE_ENTRY
  ?? "/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js";
const aiRoot = dirname(findPackageJSON("@earendil-works/pi-ai", pathToFileURL(entry)));
const { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } = await import(pathToFileURL(entry));
const { registerFauxProvider } = await import(pathToFileURL(join(aiRoot, "dist/compat.js")));
const { fauxAssistantMessage, fauxToolCall, getCurrentSystemPrompt, getCurrentTools, InMemoryCredentialStore } = await import(pathToFileURL(join(aiRoot, "dist/index.js")));
const plugin = resolve(dirname(fileURLToPath(import.meta.url)), "../home/.pi/agent/workarounds/herdr-first-prompt/index.ts");
const prompt = "<subagent_role_guidance>Read-only reviewer</subagent_role_guidance>\n<subagent_dispatch>Review SENTINEL-123</subagent_dispatch>";
const kickoff = "Start working on the supplied subagent task now.";

// All requests run in-process against the real SDK, never a child process or network model.
async function run({ enabled = true, child = true, source = prompt, priorPrompt, user = false } = {}) {
  const root = mkdtempSync(join(tmpdir(), "herdr-prompt-test-"));
  const envKeys = ["PI_HERDR_SUBAGENT_ID", "PI_HERDR_SUBAGENT_ATTEMPT_ID"];
  const previousEnv = envKeys.map((key) => process.env[key]);
  for (const key of envKeys) {
    if (child) process.env[key] = `test-${key}`;
    else delete process.env[key];
  }
  const faux = registerFauxProvider();
  let session;
  try {
    const model = faux.getModel();
    const runtime = await ModelRuntime.create({
      credentials: new InMemoryCredentialStore(), modelsPath: join(root, "models.json"),
      modelsStorePath: join(root, "models-store.json"), allowModelNetwork: false,
    });
    runtime.registerProvider(model.provider, { baseUrl: model.baseUrl, apiKey: "faux-key", api: faux.api, models: faux.models });
    const settingsManager = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
    const loader = new DefaultResourceLoader({
      cwd: root, agentDir: root, settingsManager,
      noExtensions: true, noSkills: true, noContextFiles: true, noPromptTemplates: true, noThemes: true,
      additionalExtensionPaths: enabled ? [plugin] : [],
      systemPromptOverride: () => source, appendSystemPromptOverride: () => [],
    });
    await loader.reload();
    assert.deepEqual(loader.getExtensions().errors, []);
    const manager = SessionManager.inMemory(root);
    if (priorPrompt !== undefined) {
      // A restored history whose prompt can live in a later system patch.
      manager.appendMessage({ role: "system", content: "", timestamp: 1 });
      manager.appendCustomMessageEntry("pi-herdr-subagents", "Earlier kickoff", true, {});
      manager.appendMessage(fauxAssistantMessage("Earlier response"));
      if (priorPrompt) manager.appendMessage({ role: "system", content: "", sections: { preamble: priorPrompt }, timestamp: 2 });
    }
    const history = structuredClone(manager.getEntries());
    let executions = 0;
    ({ session } = await createAgentSession({
      cwd: root, agentDir: root, resourceLoader: loader, modelRuntime: runtime, model,
      settingsManager, sessionManager: manager, tools: ["check_task"],
      customTools: [{
        name: "check_task", label: "check_task", description: "Record one execution",
        parameters: { type: "object", properties: {} },
        execute: async () => { executions++; return { content: [{ type: "text", text: "continue" }], details: {} }; },
      }],
    }));
    const extensionErrors = [];
    await session.bindExtensions({ onError: (error) => extensionErrors.push(error) });
    const requests = [];
    let recordedFirstPrompt;
    faux.setResponses([
      (context) => {
        requests.push(structuredClone(context));
        recordedFirstPrompt = getCurrentSystemPrompt(manager.buildSessionContext().messages);
        return fauxAssistantMessage([fauxToolCall("check_task", {})]);
      },
      (context) => { requests.push(structuredClone(context)); return fauxAssistantMessage("done"); },
    ]);
    if (user) await session.prompt(kickoff);
    else await session.sendCustomMessage({ customType: "pi-herdr-subagents", content: kickoff, display: true }, { triggerTurn: true, deliverAs: "followUp" });
    assert.deepEqual(extensionErrors, []);
    assert.equal(requests.length, 2, "no retry or duplicate provider request");
    assert.equal(executions, 1, "no tool replay");
    assert.deepEqual(manager.getEntries().slice(0, history.length), history, "restored history is unchanged");
    assert.equal(manager.getEntries().filter((e) => e.type === "custom_message" && e.content === kickoff).length, user ? 0 : 1);
    assert.equal(session.messages.filter((m) => m.role === "user").length, user ? 1 : 0, "custom kickoff must not impersonate the user");
    for (const request of requests) assert.deepEqual(getCurrentTools(request.messages).map((tool) => tool.name), ["check_task"]);
    const normalizeRoot = (text) => text.replaceAll(root, "<test-cwd>");
    return { prompts: requests.map((r) => normalizeRoot(getCurrentSystemPrompt(r.messages))), recordedFirstPrompt: normalizeRoot(recordedFirstPrompt) };
  } finally {
    session?.dispose();
    faux.unregister();
    envKeys.forEach((key, i) => { if (previousEnv[i] === undefined) delete process.env[key]; else process.env[key] = previousEnv[i]; });
    rmSync(root, { recursive: true, force: true });
  }
}

// Sequential subtests because the managed-child environment is process-global.
test("removable herdr first-prompt repair", async (t) => {
  await t.test("fresh custom kickoff is repaired before its first provider request", async () => {
    const result = await run();
    assert.ok(result.prompts[0].includes(prompt));
    assert.ok(result.prompts[1].includes(prompt));
    // On affected Pi this remains empty; fixed Pi may already persist the prompt itself.
    const disabled = await run({ enabled: false });
    assert.equal(result.recordedFirstPrompt, disabled.recordedFirstPrompt, "plugin never persists its repair");
    t.diagnostic(`upstream first prompt present: ${disabled.prompts[0].includes(prompt)}`);
  });
  await t.test("restored missing prompt is repaired", async () => {
    assert.ok((await run({ priorPrompt: "" })).prompts[0].includes(prompt));
  });
  await t.test("restored complete prompt is untouched", async () => {
    const options = { priorPrompt: prompt };
    assert.deepEqual((await run(options)).prompts, (await run({ ...options, enabled: false })).prompts);
  });
  await t.test("nonempty different prompt in a later system patch is not overwritten", async () => {
    const options = { priorPrompt: "Different existing instructions" };
    assert.deepEqual((await run(options)).prompts, (await run({ ...options, enabled: false })).prompts);
  });
  await t.test("ordinary user-prompt startup is untouched", async () => {
    assert.deepEqual((await run({ user: true })).prompts, (await run({ user: true, enabled: false })).prompts);
  });
  await t.test("parent session is untouched", async () => {
    assert.deepEqual((await run({ child: false })).prompts, (await run({ child: false, enabled: false })).prompts);
  });
  await t.test("unrecognized or empty role/dispatch source is untouched", async () => {
    for (const source of ["Normal assistant", "<subagent_role_guidance> </subagent_role_guidance>\n<subagent_dispatch>task</subagent_dispatch>", "<subagent_role_guidance>role</subagent_role_guidance>\n<subagent_dispatch> </subagent_dispatch>"]) {
      assert.deepEqual((await run({ source })).prompts, (await run({ source, enabled: false })).prompts);
    }
  });
});
