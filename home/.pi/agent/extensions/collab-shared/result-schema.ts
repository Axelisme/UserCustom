/**
 * Pi reviewed result contract Module
 *
 * Ownership: this Module owns worker structured outcomes and the public reviewed terminal projection.
 * It keeps typed routing, residualRisks and reviewer findings but excludes free-text validation and
 * evidence bodies. Worker COMPLETED carries outcome and optional residualRisks/efficiencyFeedback
 * with additionalProperties false rejecting any validation field; BLOCKED and NEEDS_DECISION keep their
 * typed branches. Public REVIEWED merges latest worker residualRisks then final reviewer residualRisks
 * and carries no validation, no outOfEnvelopeFindings and no evidence pointer; correctionBase is
 * internal to the reviewed loop and never projected to public terminal results. Commands remain with
 * run artifacts and durable observations remain with the assigned workflow-scoped Acceptance appendix
 * when dispatched; runtime does not add an evidence parameter or enforce assignment; runtime carries
 * only original review brief, prior typed blockers and correctionBase for rereview with no ancestry,
 * reconciliation, scope or incremental-eligibility policy.
 */

const reviewedLaneDecisionSchema = {
  type: "object",
  additionalProperties: false,
  required: ["why", "question"],
  properties: {
    why: { type: "string" },
    question: { type: "string" },
  },
} as const;



export const reviewedLaneWorkerSchema = {
  type: "object",
  oneOf: [
    {
      type: "object",
      properties: {
        outcome: { const: "COMPLETED" },
        residualRisks: { type: "array", items: { type: "string" } },
        efficiencyFeedback: {
          type: "string",
          maxLength: 10000,
          description: "Optional qualitative efficiency feedback for a requested investigation. Plain text, at most 10000 characters, no minimum; an explicitly present empty string is valid. Not a substitute for runtime mechanical counts or timing.",
        },
      },
      additionalProperties: false,
      required: ["outcome"],
    },
    {
      type: "object",
      properties: {
        outcome: { const: "BLOCKED" },
        blocker: { type: "string" },
        efficiencyFeedback: {
          type: "string",
          maxLength: 10000,
          description: "Optional qualitative efficiency feedback for a requested investigation. Plain text, at most 10000 characters, no minimum; an explicitly present empty string is valid. Not a substitute for runtime mechanical counts or timing.",
        },
      },
      additionalProperties: false,
      required: ["outcome", "blocker"],
    },
    {
      type: "object",
      properties: {
        outcome: { const: "NEEDS_DECISION" },
        decision: reviewedLaneDecisionSchema,
        efficiencyFeedback: {
          type: "string",
          maxLength: 10000,
          description: "Optional qualitative efficiency feedback for a requested investigation. Plain text, at most 10000 characters, no minimum; an explicitly present empty string is valid. Not a substitute for runtime mechanical counts or timing.",
        },
      },
      additionalProperties: false,
      required: ["outcome", "decision"],
    },
  ],
} as const;

export const reviewedLaneReviewerSchema = {
  type: "object",
  oneOf: [
    {
      type: "object",
      properties: {
        verdict: { const: "PASS" },
        residualRisks: { type: "array", items: { type: "string" } },
        efficiencyFeedback: {
          type: "string",
          maxLength: 10000,
          description: "Optional qualitative efficiency feedback for a requested investigation. Plain text, at most 10000 characters, no minimum; an explicitly present empty string is valid. Not a substitute for runtime mechanical counts or timing.",
        },
      },
      additionalProperties: false,
      required: ["verdict"],
    },
    {
      type: "object",
      properties: {
        verdict: { const: "BLOCKED" },
        blockers: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["where", "why", "howToFix", "trigger"],
            properties: {
              where: { type: "string" },
              why: { type: "string" },
              howToFix: { type: "string" },
              trigger: {
                type: "string",
                description: "The concrete input or call sequence that produces the defect, and the existing entry point it reaches from.",
              },
            },
          },
        },
        residualRisks: { type: "array", items: { type: "string" } },
        correctionBase: {
          type: "string",
          description: "Internal correction base SHA of the reviewed lane HEAD at initial BLOCKED; runtime-owned delta authority, never projected to public terminal.",
        },
        efficiencyFeedback: {
          type: "string",
          maxLength: 10000,
          description: "Optional qualitative efficiency feedback for a requested investigation. Plain text, at most 10000 characters, no minimum; an explicitly present empty string is valid. Not a substitute for runtime mechanical counts or timing.",
        },
      },
      additionalProperties: false,
      required: ["verdict", "blockers"],
    },
    {
      type: "object",
      properties: {
        verdict: { const: "NEEDS_DECISION" },
        decision: reviewedLaneDecisionSchema,
        residualRisks: { type: "array", items: { type: "string" } },
        efficiencyFeedback: {
          type: "string",
          maxLength: 10000,
          description: "Optional qualitative efficiency feedback for a requested investigation. Plain text, at most 10000 characters, no minimum; an explicitly present empty string is valid. Not a substitute for runtime mechanical counts or timing.",
        },
      },
      additionalProperties: false,
      required: ["verdict", "decision"],
    },
  ],
} as const;

function unicodeLength(value: string): number {
  return [...value].length;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isValidDecision(value: unknown): boolean {
  if (!isPlainObject(value)) return false;
  const keys = Object.keys(value);
  if (keys.length !== 2) return false;
  if (!keys.includes("why") || !keys.includes("question")) return false;
  return isString(value["why"]) && isString(value["question"]);
}

function isValidBlockerItem(value: unknown): boolean {
  if (!isPlainObject(value)) return false;
  const keys = Object.keys(value);
  if (keys.length !== 4) return false;
  if (!keys.includes("where") || !keys.includes("why") || !keys.includes("howToFix") || !keys.includes("trigger")) return false;
  return isString(value["where"]) && isString(value["why"]) && isString(value["howToFix"]) && isString(value["trigger"]);
}

export function isValidWorkerOutput(value: unknown): boolean {
  if (!isPlainObject(value)) return false;
  const outcome = value["outcome"];
  if (outcome === "COMPLETED") {
    const allowed = new Set(["outcome", "residualRisks", "efficiencyFeedback"]);
    for (const k of Object.keys(value)) if (!allowed.has(k)) return false;
    if (!("outcome" in value)) return false;
    if ("residualRisks" in value) {
      if (!Array.isArray(value["residualRisks"])) return false;
      for (const r of value["residualRisks"] as unknown[]) if (!isString(r)) return false;
    }
    if ("efficiencyFeedback" in value) {
      const fb = value["efficiencyFeedback"];
      if (!isString(fb)) return false;
      if (unicodeLength(fb) > 10000) return false;
    }
    return true;
  }
  if (outcome === "BLOCKED") {
    const allowed = new Set(["outcome", "blocker", "efficiencyFeedback"]);
    for (const k of Object.keys(value)) if (!allowed.has(k)) return false;
    if (!("outcome" in value) || !("blocker" in value)) return false;
    if (!isString(value["blocker"])) return false;
    if ("efficiencyFeedback" in value) {
      const fb = value["efficiencyFeedback"];
      if (!isString(fb)) return false;
      if (unicodeLength(fb) > 10000) return false;
    }
    return true;
  }
  if (outcome === "NEEDS_DECISION") {
    const allowed = new Set(["outcome", "decision", "efficiencyFeedback"]);
    for (const k of Object.keys(value)) if (!allowed.has(k)) return false;
    if (!("outcome" in value) || !("decision" in value)) return false;
    if (!isValidDecision(value["decision"])) return false;
    if ("efficiencyFeedback" in value) {
      const fb = value["efficiencyFeedback"];
      if (!isString(fb)) return false;
      if (unicodeLength(fb) > 10000) return false;
    }
    return true;
  }
  return false;
}

export function isValidReviewerOutput(value: unknown): boolean {
  if (!isPlainObject(value)) return false;
  const verdict = value["verdict"];
  if (verdict === "PASS") {
    const allowed = new Set(["verdict", "residualRisks", "efficiencyFeedback"]);
    for (const k of Object.keys(value)) if (!allowed.has(k)) return false;
    if (!("verdict" in value)) return false;
    if ("residualRisks" in value) {
      if (!Array.isArray(value["residualRisks"])) return false;
      for (const r of value["residualRisks"] as unknown[]) if (!isString(r)) return false;
    }
    if ("efficiencyFeedback" in value) {
      const fb = value["efficiencyFeedback"];
      if (!isString(fb)) return false;
      if (unicodeLength(fb) > 10000) return false;
    }
    return true;
  }
  if (verdict === "BLOCKED") {
    const allowed = new Set(["verdict", "blockers", "residualRisks", "correctionBase", "efficiencyFeedback"]);
    for (const k of Object.keys(value)) if (!allowed.has(k)) return false;
    if (!("verdict" in value) || !("blockers" in value)) return false;
    if (!Array.isArray(value["blockers"])) return false;
    for (const b of value["blockers"] as unknown[]) if (!isValidBlockerItem(b)) return false;
    if ("residualRisks" in value) {
      if (!Array.isArray(value["residualRisks"])) return false;
      for (const r of value["residualRisks"] as unknown[]) if (!isString(r)) return false;
    }
    if ("correctionBase" in value) {
      if (!isString(value["correctionBase"])) return false;
    }
    if ("efficiencyFeedback" in value) {
      const fb = value["efficiencyFeedback"];
      if (!isString(fb)) return false;
      if (unicodeLength(fb) > 10000) return false;
    }
    return true;
  }
  if (verdict === "NEEDS_DECISION") {
    const allowed = new Set(["verdict", "decision", "residualRisks", "efficiencyFeedback"]);
    for (const k of Object.keys(value)) if (!allowed.has(k)) return false;
    if (!("verdict" in value) || !("decision" in value)) return false;
    if (!isValidDecision(value["decision"])) return false;
    if ("residualRisks" in value) {
      if (!Array.isArray(value["residualRisks"])) return false;
      for (const r of value["residualRisks"] as unknown[]) if (!isString(r)) return false;
    }
    if ("efficiencyFeedback" in value) {
      const fb = value["efficiencyFeedback"];
      if (!isString(fb)) return false;
      if (unicodeLength(fb) > 10000) return false;
    }
    return true;
  }
  return false;
}

export function isValidStructuredOutput(workflowKey: string, value: unknown): boolean {
  if (workflowKey.startsWith("impl-")) return isValidWorkerOutput(value);
  if (workflowKey.startsWith("review-")) return isValidReviewerOutput(value);
  return false;
}
