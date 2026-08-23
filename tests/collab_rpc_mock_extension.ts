import { appendFile } from "node:fs/promises";

const RPC_REQUEST = "subagents:rpc:v1:request";
const RPC_REPLY_PREFIX = "subagents:rpc:v1:reply:";

type Config = {
  mode?: "available" | "unsupported-version" | "missing-spawn" | "spawn-error";
  capture?: string;
  runId?: string;
  omitRunId?: boolean;
  foregroundStructuredResume?: unknown;
};

export default function collabRpcMock(pi: any): void {
  let config: Config = {};

  pi.registerTool({
    name: "_collab_test_rpc_config",
    label: "Configure Collab test RPC",
    description: "Test-only RPC configuration.",
    parameters: { type: "object", additionalProperties: true },
    async execute(_id: string, request: Config) {
      config = request;
      return { content: [{ type: "text", text: "{}" }], details: {} };
    },
  });

  pi.events.on(RPC_REQUEST, async (raw: any) => {
    const replyEvent = `${RPC_REPLY_PREFIX}${String(raw?.requestId ?? "")}`;
    if (raw?.method === "ping") {
      if (config.mode === "unsupported-version") {
        pi.events.emit(replyEvent, {
          version: 2,
          requestId: raw.requestId,
          success: true,
          data: { version: 2, methods: ["ping", "spawn"], capabilities: { asyncSpawn: true } },
        });
        return;
      }
      const methods = config.mode === "missing-spawn" ? ["ping"] : ["ping", "spawn"];
      pi.events.emit(replyEvent, {
        version: 1,
        requestId: raw.requestId,
        success: true,
        data: {
          version: 1,
          methods,
          capabilities: {
            asyncSpawn: methods.includes("spawn"),
            ...(config.foregroundStructuredResume === undefined
              ? {}
              : { foregroundStructuredResume: config.foregroundStructuredResume }),
          },
        },
      });
      return;
    }
    if (raw?.method !== "spawn") return;
    if (config.capture) await appendFile(config.capture, `${JSON.stringify(raw)}\n`, "utf8");
    if (config.mode === "spawn-error") {
      pi.events.emit(replyEvent, {
        version: 1,
        requestId: raw.requestId,
        success: false,
        error: { code: "execution_failed", message: "controlled spawn failure" },
      });
      return;
    }
    pi.events.emit(replyEvent, {
      version: 1,
      requestId: raw.requestId,
      success: true,
      data: {
        text: "started",
        details: {
          mode: "workflow",
          ...(config.omitRunId ? {} : { runId: config.runId ?? "async-test-id" }),
          asyncId: "async-test-id",
          asyncDir: "/tmp/pi-subagents/async-test-id",
          results: [],
        },
      },
    });
  });
}
