#!/usr/bin/env node
import { pathToFileURL } from "node:url";
import { createInterface } from "node:readline";

const [packageEntry, extensionPath, cwd] = process.argv.slice(2);
if (!packageEntry || !extensionPath || !cwd) {
  throw new Error("usage: harness <pi-package-entry> <extension-path> <cwd>");
}

const { DefaultResourceLoader, SettingsManager } = await import(pathToFileURL(packageEntry));
const settingsManager = SettingsManager.inMemory({});
const loader = new DefaultResourceLoader({
  cwd,
  agentDir: `${cwd}/.empty-pi-agent`,
  additionalExtensionPaths: [extensionPath],
  settingsManager,
});
await loader.reload();
const loaded = loader.getExtensions();
if (loaded.errors.length > 0) {
  process.stderr.write(`${JSON.stringify({ loader_errors: loaded.errors })}\n`);
  process.exit(2);
}

const tools = loaded.extensions.flatMap((extension) => [...extension.tools.keys()]).sort();
const registrations = new Map(
  loaded.extensions.flatMap((extension) => [...extension.tools.entries()]),
);
const schemas = Object.fromEntries(
  [...registrations.entries()]
    .filter(([name]) => name.startsWith("collab_"))
    .map(([name, tool]) => [
      name,
      {
        label: tool.definition.label,
        description: tool.definition.description,
        parameters: tool.definition.parameters,
      },
    ]),
);

async function execute(envelope) {
  const toolName = typeof envelope.tool === "string" ? envelope.tool : "collab_op";
  const registration = registrations.get(toolName);
  if (!registration) {
    return {
      tools,
      schemas,
      tool: toolName,
      is_error: true,
      error: {
        ok: false,
        tool_version: 1,
        error: {
          code: "unknown_tool",
          message: `${toolName} is not registered`,
          repair: "Choose one of the registered Collab tools.",
        },
      },
    };
  }
  const request = envelope.tool === undefined
    ? envelope
    : Object.fromEntries(Object.entries(envelope).filter(([key]) => key !== "tool"));
  try {
    const result = await registration.definition.execute(
      "test-call",
      request,
      undefined,
      undefined,
      { cwd },
    );
    const text = result.content.find((part) => part.type === "text")?.text;
    return { tools, schemas, tool: toolName, is_error: false, result: JSON.parse(text) };
  } catch (error) {
    let errorEnvelope;
    try {
      errorEnvelope = JSON.parse(error instanceof Error ? error.message : String(error));
    } catch {
      errorEnvelope = { raw: error instanceof Error ? error.message : String(error) };
    }
    return { tools, schemas, tool: toolName, is_error: true, error: errorEnvelope };
  }
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  if (!line) continue;
  const response = await execute(JSON.parse(line));
  process.stdout.write(`${JSON.stringify(response)}\n`);
}
