#!/usr/bin/env node
// Observable dispatch contract for tools other extensions publish into the
// shared bridged registry. Loads the real extension through Pi's loader, the
// same way parallel_tools_render_harness.mjs does, and calls the tool.
import { pathToFileURL } from "node:url";

const [packageEntry, extensionPath, cwd, scenario = "sequential"] = process.argv.slice(2);
if (!packageEntry || !extensionPath || !cwd) {
  throw new Error("usage: harness <pi-package-entry> <extension-path> <cwd> [scenario]");
}

const order = [];
const bridgedTool = (name) => ({
  name,
  label: name,
  description: name,
  parameters: { type: "object", properties: {}, additionalProperties: true },
  async execute(_toolCallId, params) {
    order.push(name);
    // A pause long enough that concurrent and sequential runs are telling apart
    // by wall clock, not just by the reported mode.
    await new Promise((resolve) => setTimeout(resolve, 60));
    return { content: [{ type: "text", text: `${name} ran with ${JSON.stringify(params ?? {})}` }] };
  },
});

// Published before the tool is called, which is all the consumer requires.
globalThis.__piBridgedTools = new Map([
  ["fake_mutator", { definition: bridgedTool("fake_mutator"), sequential: true }],
  ["fake_reader", { definition: bridgedTool("fake_reader") }],
  ["fake_reader_two", { definition: bridgedTool("fake_reader_two") }],
  // A publisher trying to take over a built-in name must not win.
  ["read", { definition: bridgedTool("read") }],
]);

const { DefaultResourceLoader, SettingsManager } = await import(pathToFileURL(packageEntry));
const loader = new DefaultResourceLoader({
  cwd,
  agentDir: `${cwd}/.empty-pi-agent`,
  additionalExtensionPaths: [extensionPath],
  settingsManager: SettingsManager.inMemory({}),
});
await loader.reload();
const loaded = loader.getExtensions();
if (loaded.errors.length > 0) throw new Error(JSON.stringify(loaded.errors));
const registration = loaded.extensions
  .flatMap((extension) => [...extension.tools.entries()])
  .find(([name]) => name === "parallel")?.[1];
if (!registration) throw new Error("parallel tool was not registered");

const batches = {
  sequential: [
    { recipient_name: "fake_reader", parameters: { i: 1 } },
    { recipient_name: "fake_mutator", parameters: { i: 2 } },
  ],
  concurrent: [
    { recipient_name: "fake_reader", parameters: { i: 1 } },
    { recipient_name: "fake_reader_two", parameters: { i: 2 } },
  ],
  unknown: [{ recipient_name: "not_published", parameters: {} }],
  "no-shadow": [{ recipient_name: "read", parameters: { path: "README.md" } }],
};
const tool_uses = batches[scenario];
if (!tool_uses) throw new Error(`unknown scenario ${scenario}`);

const ctx = { cwd, sessionManager: { getSessionId: () => "harness-session", getSessionFile: () => undefined } };
const definition = registration.definition;
const prepared = definition.prepareArguments ? definition.prepareArguments({ tool_uses }) : { tool_uses };
const started = Date.now();
const result = await definition.execute("tc-bridge", prepared, undefined, undefined, ctx);
const elapsedMs = Date.now() - started;

process.stdout.write(
  JSON.stringify({
    mode: result?.details?.mode ?? null,
    names: (result?.details?.calls ?? []).map((call) => call.name),
    ok: (result?.details?.calls ?? []).map((call) => call.ok),
    order,
    elapsedMs,
    text: (result?.content ?? []).map((block) => block.text ?? `[${block.type}]`).join("\n"),
  }),
);
