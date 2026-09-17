#!/usr/bin/env node
import { pathToFileURL } from "node:url";

const [packageEntry, extensionPath, cwd, widthArg, expandedArg] = process.argv.slice(2);
if (!packageEntry || !extensionPath || !cwd || !widthArg || !expandedArg) {
  throw new Error("usage: harness <pi-package-entry> <extension-path> <cwd> <width> <expanded>");
}

const { DefaultResourceLoader, SettingsManager } = await import(pathToFileURL(packageEntry));
const loader = new DefaultResourceLoader({
  cwd,
  agentDir: `${cwd}/.empty-pi-agent`,
  additionalExtensionPaths: [extensionPath],
  settingsManager: SettingsManager.inMemory({}),
});
await loader.reload();
const loaded = loader.getExtensions();
if (loaded.errors.length > 0) {
  throw new Error(JSON.stringify(loaded.errors));
}
const registration = loaded.extensions
  .flatMap((extension) => [...extension.tools.entries()])
  .find(([name]) => name === "parallel")?.[1];
if (!registration) throw new Error("parallel tool was not registered");

const args = {
  tool_uses: [
    { recipient_name: "read", parameters: { path: "docs/unique-read-input.md" } },
    {
      recipient_name: "bash",
      parameters: {
        command:
          "printf unique-shell-input-with-a-command-that-must-not-wrap-across-visual-rows",
      },
    },
    { recipient_name: "grep", parameters: { pattern: "unique-failed-input", path: "." } },
    { recipient_name: "ls", parameters: { path: "unique-empty-input" } },
  ],
};
const text = (value) => ({ type: "text", text: value });
const content = [
  text(["READ-L1", "READ-L2", "READ-L3", "READ-L4", "READ-L5", "READ-L6", "READ-L7"].join("\n")),
  text(["BASH-L1", "BASH-L2", "BASH-L3", "BASH-L4", "BASH-L5", "BASH-L6", "BASH-L7"].join("\n")),
  text("BROKEN-L1\nBROKEN-L2"),
  text(""),
];
const details = {
  mode: "sequential",
  calls: [
    {
      index: 0,
      name: "read",
      label: "read(docs/unique-read-input.md)",
      args: args.tool_uses[0].parameters,
      ok: true,
      durationMs: 4,
      details: undefined,
      blockStart: 0,
      blockCount: 1,
    },
    {
      index: 1,
      name: "bash",
      label: "bash(printf unique-shell-input-with-a-command-that-must-not-wrap-across-visual-rows)",
      args: args.tool_uses[1].parameters,
      ok: true,
      durationMs: 8,
      details: undefined,
      blockStart: 1,
      blockCount: 1,
    },
    {
      index: 2,
      name: "grep",
      label: "grep(unique-failed-input)",
      args: args.tool_uses[2].parameters,
      ok: false,
      durationMs: 2,
      details: undefined,
      blockStart: 2,
      blockCount: 1,
    },
    {
      index: 3,
      name: "ls",
      label: "ls(unique-empty-input)",
      args: args.tool_uses[3].parameters,
      ok: true,
      durationMs: 1,
      details: undefined,
      blockStart: 3,
      blockCount: 1,
    },
  ],
};
const expanded = expandedArg === "true";
const width = Number(widthArg);
const identityTheme = {
  fg: (_name, value) => value,
  bg: (_name, value) => value,
  bold: (value) => value,
  italic: (value) => value,
  underline: (value) => value,
  strikethrough: (value) => value,
};
const state = {};
const baseContext = {
  args,
  toolCallId: "render-contract",
  invalidate() {},
  lastComponent: undefined,
  state,
  cwd,
  executionStarted: true,
  argsComplete: true,
  isPartial: false,
  expanded,
  showImages: false,
  isError: false,
};
const call = registration.definition.renderCall(args, identityTheme, baseContext);
const result = registration.definition.renderResult(
  { content, details },
  { expanded, isPartial: false },
  identityTheme,
  baseContext,
);
const ansi = /\x1B(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*?(?:\x07|\x1B\\))/g;
const lines = [...call.render(width), ...result.render(width)].map((line) =>
  line.replace(ansi, "").trimEnd(),
);
process.stdout.write(`${JSON.stringify({ width, expanded, lines })}\n`);
