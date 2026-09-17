import { readFileSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import {
	createBashToolDefinition,
	createEditToolDefinition,
	createFindToolDefinition,
	createGrepToolDefinition,
	createLsToolDefinition,
	createReadToolDefinition,
	createWriteToolDefinition,
	type ExtensionAPI,
	type ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { Container, Text, truncateToWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";

/** Sub-tools the batch tool is allowed to dispatch to. */
const READ_ONLY = ["read", "grep", "find", "ls"] as const;
const MUTATING = ["bash", "edit", "write"] as const;
type SubToolName = (typeof READ_ONLY)[number] | (typeof MUTATING)[number];

const MUTATING_SET = new Set<string>(MUTATING);
const MAX_CALLS = 16;
/** Head kept inline when a sub-result is spilled to a file. */
const SPILL_EXCERPT_BYTES = 2_000;
/** billion-context-pi guardrail defaults, used when acp.json says nothing. */
const DEFAULT_TOOL_OUTPUT_MAX_BYTES = 200_000;
const DEFAULT_BASH_TIMEOUT = 60;

type AcpConfig = { toolOutputMaxBytes?: number; toolBashDefaultTimeout?: number };

/**
 * Read the same global-then-project acp.json the guardrails read, so the batch
 * budget and the bash timeout track whatever the user configured there.
 */
function readAcpConfig(cwd: string): AcpConfig {
	const merged: AcpConfig = {};
	for (const base of [join(homedir(), ".pi"), join(cwd, ".pi")]) {
		try {
			const parsed = JSON.parse(readFileSync(join(base, "acp.json"), "utf8")) as AcpConfig;
			if (typeof parsed.toolOutputMaxBytes === "number") merged.toolOutputMaxBytes = parsed.toolOutputMaxBytes;
			if (typeof parsed.toolBashDefaultTimeout === "number") {
				merged.toolBashDefaultTimeout = parsed.toolBashDefaultTimeout;
			}
		} catch {
			/* absent or malformed config leaves the defaults in place */
		}
	}
	return merged;
}

/**
 * Inline ceiling for one batch. Sub-tools already truncate themselves at 50KB,
 * so this only stops a large batch from being head-truncated downstream, where
 * trailing calls would vanish outright.
 */
function inlineBudget(config: AcpConfig): number {
	const cap = config.toolOutputMaxBytes ?? DEFAULT_TOOL_OUTPUT_MAX_BYTES;
	return Math.max(SPILL_EXCERPT_BYTES, Math.floor(cap * 0.75));
}

type AnyToolDef = {
	name: string;
	prepareArguments?: (args: unknown) => unknown;
	execute: (
		toolCallId: string,
		params: any,
		signal: AbortSignal | undefined,
		onUpdate: undefined,
		ctx: ExtensionContext,
	) => Promise<{ content: Array<{ type: string; [k: string]: unknown }>; details?: unknown }>;
};

/** Built-in tool definitions are cwd-bound, so cache one set per cwd. */
const definitionsByCwd = new Map<string, Record<SubToolName, AnyToolDef>>();

/**
 * pi-claude-code-ui replaces the built-in tools with its own wrappers, and its renderers
 * read result details only those wrappers produce. ExtensionAPI exposes no way to ask
 * another extension for a registered tool, so it publishes them on this global. Internal
 * handshake, not a stable interface: when it is absent we simply use the raw factories.
 */
function sharedToolDefinitions(): Map<string, AnyToolDef> | undefined {
	const published = (globalThis as { __piClaudeCodeUiTools?: unknown }).__piClaudeCodeUiTools;
	return published instanceof Map ? (published as Map<string, AnyToolDef>) : undefined;
}

function definitionsFor(cwd: string): Record<SubToolName, AnyToolDef> {
	const shared = sharedToolDefinitions();
	// Key on availability too, so a set built before the other extension registered its
	// tools is not cached forever.
	const cacheKey = `${shared ? "shared" : "raw"}:${cwd}`;
	const cached = definitionsByCwd.get(cacheKey);
	if (cached) return cached;
	const created = {
		read: createReadToolDefinition(cwd),
		grep: createGrepToolDefinition(cwd),
		find: createFindToolDefinition(cwd),
		ls: createLsToolDefinition(cwd),
		bash: createBashToolDefinition(cwd),
		edit: createEditToolDefinition(cwd),
		write: createWriteToolDefinition(cwd),
	} as unknown as Record<SubToolName, AnyToolDef>;
	if (shared) {
		for (const name of Object.keys(created) as SubToolName[]) {
			const definition = shared.get(name);
			if (!definition || typeof definition.execute !== "function") continue;
			// The published wrappers do not carry prepareArguments — pi applies the
			// built-in one for them. We call execute directly, so keep the factory's.
			created[name] = definition.prepareArguments
				? definition
				: { ...definition, prepareArguments: created[name].prepareArguments };
		}
	}
	definitionsByCwd.set(cacheKey, created);
	return created;
}

export type SubCall = { recipient_name: string; parameters: Record<string, unknown> };
export type ParallelInput = { tool_uses: SubCall[] };

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Strip the `functions.` namespace the OpenAI wrapper shape carries. */
export function normalizeRecipient(raw: unknown): string {
	const text = typeof raw === "string" ? raw.trim() : "";
	const withoutNamespace = text.includes(".") ? text.slice(text.lastIndexOf(".") + 1) : text;
	return withoutNamespace;
}

/**
 * Accept the shapes models actually emit: the OpenAI wrapper's
 * `{tool_uses:[{recipient_name,parameters}]}` plus the common aliases.
 */
export function prepareParallelArguments(args: unknown): ParallelInput {
	if (!isRecord(args)) return { tool_uses: [] };
	const listKey = ["tool_uses", "invocations", "calls", "tool_calls", "tools"].find((key) =>
		Array.isArray(args[key]),
	);
	const rawList = listKey ? (args[listKey] as unknown[]) : [];
	const tool_uses: SubCall[] = [];
	for (const entry of rawList) {
		if (!isRecord(entry)) continue;
		const recipient = normalizeRecipient(
			entry.recipient_name ?? entry.name ?? entry.tool ?? entry.tool_name,
		);
		const parametersKey = ["parameters", "arguments", "args", "input", "params"].find((key) =>
			isRecord(entry[key]),
		);
		let parameters = parametersKey ? (entry[parametersKey] as Record<string, unknown>) : {};
		if (typeof entry.arguments === "string") {
			try {
				const parsed: unknown = JSON.parse(entry.arguments);
				if (isRecord(parsed)) parameters = parsed;
			} catch {
				/* leave parameters empty; the sub-tool reports the failure */
			}
		}
		tool_uses.push({ recipient_name: recipient, parameters });
	}
	return { tool_uses };
}

function summarize(call: SubCall): string {
	const parameters = call.parameters;
	const hint =
		(typeof parameters.path === "string" && parameters.path) ||
		(typeof parameters.pattern === "string" && parameters.pattern) ||
		(typeof parameters.command === "string" && parameters.command) ||
		"";
	const trimmed = hint.length > 80 ? `${hint.slice(0, 80)}…` : hint;
	return trimmed ? `${call.recipient_name}(${trimmed})` : call.recipient_name;
}

function headBytes(text: string, limitBytes: number): string {
	if (Buffer.byteLength(text, "utf8") <= limitBytes) return text;
	return Buffer.from(text, "utf8").subarray(0, Math.max(0, limitBytes)).toString("utf8");
}

/** Move an oversized sub-result to a file so later calls still reach the model. */
function spill(text: string, toolCallId: string, index: number): string {
	const path = join(tmpdir(), `pi-parallel-${toolCallId.replace(/[^\w.-]/g, "_")}-${index}.txt`);
	try {
		writeFileSync(path, text, "utf8");
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		return `${headBytes(text, SPILL_EXCERPT_BYTES)}\n… [batch budget exhausted; spill failed: ${message}]`;
	}
	const total = Buffer.byteLength(text, "utf8");
	return `${headBytes(text, SPILL_EXCERPT_BYTES)}\n… [batch budget exhausted; full output (${total} bytes) written to ${path} — read it for the rest]`;
}

type CallOutcome = {
	index: number;
	label: string;
	name: string;
	args: Record<string, unknown>;
	ok: boolean;
	blocks: Array<{ type: string; [k: string]: unknown }>;
	details: unknown;
	durationMs: number;
};

/**
 * Per-sub-call record kept in `details` so the renderers can hand each built-in
 * tool its own result. `blockStart`/`blockCount` index into `result.content`
 * rather than copying it, so the session file carries the output once.
 */
type CallRecord = {
	index: number;
	name: string;
	label: string;
	args: Record<string, unknown>;
	ok: boolean;
	durationMs: number;
	details: unknown;
	blockStart: number;
	blockCount: number;
};

type ParallelDetails = { mode: "sequential" | "concurrent"; calls: CallRecord[] };

async function runOne(
	call: SubCall,
	index: number,
	toolCallId: string,
	signal: AbortSignal | undefined,
	ctx: ExtensionContext,
	bashTimeout: number | undefined,
): Promise<CallOutcome> {
	const label = summarize(call);
	const started = Date.now();
	const name = call.recipient_name as SubToolName;
	const definition = definitionsFor(ctx.cwd)[name];
	if (!definition) {
		return {
			index,
			label,
			name,
			args: call.parameters,
			ok: false,
			durationMs: 0,
			details: undefined,
			blocks: [
				{
					type: "text",
					text: `unknown tool ${JSON.stringify(call.recipient_name)}; allowed: ${[...READ_ONLY, ...MUTATING].join(", ")}`,
				},
			],
		};
	}
	try {
		let args = call.parameters;
		if (name === "bash" && args.timeout === undefined && bashTimeout !== undefined) {
			args = { ...args, timeout: bashTimeout };
		}
		const prepared = definition.prepareArguments ? definition.prepareArguments(args) : args;
		const result = await definition.execute(`${toolCallId}:${index}`, prepared, signal, undefined, ctx);
		const blocks = [...result.content];
		// bash writes its untruncated output to a file; surface the path the batch would otherwise hide.
		const fullOutputPath = (result.details as { fullOutputPath?: unknown } | undefined)?.fullOutputPath;
		if (typeof fullOutputPath === "string" && fullOutputPath.length > 0) {
			blocks.push({ type: "text", text: `[full output: ${fullOutputPath}]` });
		}
		return {
			index,
			label,
			name,
			args: prepared as Record<string, unknown>,
			ok: true,
			durationMs: Date.now() - started,
			details: result.details,
			blocks,
		};
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		return {
			index,
			label,
			name,
			args: call.parameters,
			ok: false,
			durationMs: Date.now() - started,
			details: undefined,
			blocks: [{ type: "text", text: message }],
		};
	}
}


function plural(count: number, word: string): string {
	return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function textOf(block: { type: string; [k: string]: unknown }): string {
	return block.type === "text" && typeof block.text === "string" ? block.text : `[${block.type}]`;
}

function formatExpandedChildInput(record: CallRecord): string {
	const serializedArgs = JSON.stringify(record.args ?? {});
	return serializedArgs === undefined ? record.name : `${record.name} ${serializedArgs}`;
}

export default function parallelToolsExtension(pi: ExtensionAPI): void {
	pi.registerTool({
		name: "parallel",
		label: "Parallel",
		description:
			"Run several independent tool calls in one request. Each entry of tool_uses names a tool in recipient_name (read, grep, find, ls, bash, edit, write) and passes that tool's own arguments in parameters. Read-only batches run concurrently; a batch containing bash, edit, or write runs in listed order. This is the route for every batch: prefer one parallel call over emitting the same calls separately in one response. Never batch a call whose arguments depend on another call's result.",
		promptSnippet: "Run several independent tool calls in one request",
		promptGuidelines: [
			"Use parallel when the next step needs several independent reads, searches, or commands that are known in advance.",
			"Only batch calls that are independent of each other; a call that needs another's result must wait for the next turn.",
			"Route every batch through parallel rather than emitting the same calls as separate tool calls in one response.",
		],
		parameters: {
			type: "object",
			properties: {
				tool_uses: {
					type: "array",
					description: "The independent tool calls to run.",
					maxItems: MAX_CALLS,
					items: {
						type: "object",
						properties: {
							recipient_name: {
								type: "string",
								description:
									"Name of the tool to call: read, grep, find, ls, bash, edit, or write.",
							},
							parameters: {
								type: "object",
								description: "Arguments for that tool, exactly as the tool itself defines them.",
								additionalProperties: true,
							},
						},
						required: ["recipient_name", "parameters"],
						additionalProperties: false,
					},
				},
			},
			required: ["tool_uses"],
			additionalProperties: false,
		} as any,
		executionMode: "parallel",
		renderCall(args: ParallelInput, theme: any, context: any) {
			const calls = Array.isArray(args?.tool_uses) ? args.tool_uses : [];
			const header = `${theme.fg("toolTitle", theme.bold("parallel"))} ${theme.fg("muted", `(${plural(calls.length, "call")})`)}`;
			const state = context ? (context.state ??= {}) : {};
			return {
				render(_width: number) {
					if (state.hasResult) return [];
					return [header];
				},
				invalidate() {},
			};
		},
		renderResult(result: any, options: any, theme: any, context: any) {
			const details = result?.details as ParallelDetails | undefined;
			const records = Array.isArray(details?.calls) ? details.calls : [];
			const blocks = (result?.content ?? []) as Array<{ type: string; [k: string]: unknown }>;
			const box = context?.lastComponent instanceof Container ? context.lastComponent : new Container();
			box.clear();

			if (records.length === 0) {
				if (blocks.length > 0) {
					box.addChild(new Text(blocks.map(textOf).join("\n"), 0, 0));
				}
				return box as never;
			}

			const state = context ? (context.state ??= {}) : {};
			state.hasResult = true;

			const failed = records.filter((record) => !record.ok).length;
			const wall =
				details?.mode === "sequential"
					? records.reduce((sum, record) => sum + record.durationMs, 0)
					: records.reduce((max, record) => Math.max(max, record.durationMs), 0);
			const status =
				failed === 0 ? theme.fg("success", "all ok") : theme.fg("error", `${failed} failed`);
			const headerText = `${theme.fg("toolTitle", theme.bold("parallel"))} ${theme.fg(
				"muted",
				`(${plural(records.length, "call")} · ${details?.mode ?? "concurrent"} · ${wall}ms · `,
			)}${status}${theme.fg("muted", ")")}`;
			box.addChild(new Text(headerText, 0, 0));

			const expanded = Boolean(options?.expanded ?? context?.expanded);

			for (const record of records) {
				const mark = record.ok ? theme.fg("success", "✓") : theme.fg("error", "✗");
				const durationStr = `${record.durationMs}ms`;
				const durationText = theme.fg("muted", durationStr);

				if (expanded) {
					const label = formatExpandedChildInput(record);
					const inputLine = `  ${mark} ${label} ${durationText}`;
					box.addChild(new Text(inputLine, 0, 0));
				} else {
					const label =
						record.label ||
						summarize({ recipient_name: record.name, parameters: record.args });
					const inputLine = `  ${mark} ${label}`;
					box.addChild({
						render: (width: number) => {
							const reserved = durationStr.length + 1;
							const avail = Math.max(0, width - reserved);
							const truncated = truncateToWidth(inputLine, avail, "…");
							return [`${truncated} ${durationText}`];
						},
						invalidate: () => {},
					});
				}

				const slice = blocks.slice(record.blockStart, record.blockStart + record.blockCount);
				const rawText = slice
					.filter((block) => block.type === "text" && typeof block.text === "string")
					.map((block) => block.text as string)
					.join("\n")
					.replace(/\r\n/g, "\n");

				if (rawText.trim() === "") {
					box.addChild({
						render: () => [`      ${theme.fg("muted", "(no output)")}`],
						invalidate: () => {},
					});
				} else if (expanded) {
					box.addChild({
						render: (width: number) => {
							const contentWidth = Math.max(1, width - 6);
							const visualLines = wrapTextWithAnsi(rawText.trimEnd(), contentWidth);
							while (visualLines.length > 0 && visualLines[visualLines.length - 1].trim() === "") {
								visualLines.pop();
							}
							if (visualLines.length === 0) {
								return [`      ${theme.fg("muted", "(no output)")}`];
							}
							return visualLines.map((line) => `      ${theme.fg("toolOutput", line)}`);
						},
						invalidate: () => {},
					});
				} else {
					const isTail = record.name === "bash" || record.name === "powershell";
					box.addChild({
						render: (width: number) => {
							const contentWidth = Math.max(1, width - 6);
							const visualLines = wrapTextWithAnsi(rawText.trimEnd(), contentWidth);
							while (visualLines.length > 0 && visualLines[visualLines.length - 1].trim() === "") {
								visualLines.pop();
							}
							if (visualLines.length === 0) {
								return [`      ${theme.fg("muted", "(no output)")}`];
							}
							const displayLines =
								visualLines.length > 5
									? isTail
										? visualLines.slice(-5)
										: visualLines.slice(0, 5)
									: visualLines;
							return displayLines.map((line) => `      ${theme.fg("toolOutput", line)}`);
						},
						invalidate: () => {},
					});
				}
			}
			return box as never;
		},

		prepareArguments: prepareParallelArguments as any,
		async execute(toolCallId, params: ParallelInput, signal, _onUpdate, ctx) {
			const calls = Array.isArray(params?.tool_uses) ? params.tool_uses : [];
			if (calls.length === 0) {
				return {
					content: [{ type: "text", text: "parallel: tool_uses was empty; nothing ran." }],
					details: { calls: [] },
				};
			}
			if (calls.length > MAX_CALLS) {
				return {
					content: [
						{
							type: "text",
							text: `parallel: ${calls.length} calls exceeds the limit of ${MAX_CALLS}; split the batch.`,
						},
					],
					details: { calls: [] },
				};
			}

			const config = readAcpConfig(ctx.cwd);
			const bashTimeout = config.toolBashDefaultTimeout ?? DEFAULT_BASH_TIMEOUT;
			const sequential = calls.some((call) => MUTATING_SET.has(call.recipient_name));
			let outcomes: CallOutcome[];
			if (sequential) {
				outcomes = [];
				for (const [index, call] of calls.entries()) {
					if (signal?.aborted) break;
					outcomes.push(await runOne(call, index, toolCallId, signal, ctx, bashTimeout));
				}
			} else {
				outcomes = await Promise.all(
					calls.map((call, index) => runOne(call, index, toolCallId, signal, ctx, bashTimeout)),
				);
			}

			const content: Array<{ type: string; [k: string]: unknown }> = [];
			// Each sub-call keeps the budget its tool would get on its own; only a
			// batch large enough to be head-truncated downstream spills to files.
			let budget = inlineBudget(config);
			const records: CallRecord[] = [];
			for (const outcome of outcomes) {
				const status = outcome.ok ? "ok" : "failed";
				content.push({
					type: "text",
					text: `--- [${outcome.index + 1}/${calls.length}] ${outcome.label} — ${status} ---`,
				});
				const blockStart = content.length;
				for (const block of outcome.blocks) {
					if (block.type !== "text") {
						content.push(block);
						continue;
					}
					const raw = typeof block.text === "string" ? block.text : "";
					const size = Buffer.byteLength(raw, "utf8");
					const text = size <= budget ? raw : spill(raw, toolCallId, outcome.index);
					budget = Math.max(0, budget - Buffer.byteLength(text, "utf8"));
					content.push({ type: "text", text });
				}
				records.push({
					index: outcome.index,
					name: outcome.name,
					label: outcome.label,
					args: outcome.args,
					ok: outcome.ok,
					durationMs: outcome.durationMs,
					details: outcome.details,
					blockStart,
					blockCount: content.length - blockStart,
				});
			}
			if (outcomes.length < calls.length) {
				content.push({
					type: "text",
					text: `parallel: aborted after ${outcomes.length} of ${calls.length} calls.`,
				});
			}

			const details: ParallelDetails = {
				mode: sequential ? "sequential" : "concurrent",
				calls: records,
			};
			return { content, details };
		},
	});
}
