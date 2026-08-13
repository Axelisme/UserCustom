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
const registrations = loaded.extensions
  .map((extension) => extension.tools.get("collab_op"))
  .filter(Boolean);
if (registrations.length !== 1) {
  throw new Error(`expected one collab_op registration, found ${registrations.length}`);
}

async function execute(request) {
  try {
    const result = await registrations[0].definition.execute(
      "test-call",
      request,
      undefined,
      undefined,
      { cwd },
    );
    const text = result.content.find((part) => part.type === "text")?.text;
    return { tools, is_error: false, result: JSON.parse(text) };
  } catch (error) {
    let envelope;
    try {
      envelope = JSON.parse(error instanceof Error ? error.message : String(error));
    } catch {
      envelope = { raw: error instanceof Error ? error.message : String(error) };
    }
    return { tools, is_error: true, error: envelope };
  }
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  if (!line) continue;
  const response = await execute(JSON.parse(line));
  process.stdout.write(`${JSON.stringify(response)}\n`);
}
