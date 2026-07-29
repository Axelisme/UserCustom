const state = globalThis.__ORCHESTRATE_PI_PROFILE_STATE__;
state.imports += 1;

function contract(input) {
  return {
    version: 2,
    agent: {
      name: "lane-worker",
      source: "user",
      filePath: "/fixture/agents/lane-worker.md",
      shadowedCandidates: [],
    },
    context: "fresh",
    skills: {
      requested: ["tdd"],
      resolved: [{ name: "tdd", path: "/fixture/skills/tdd/SKILL.md", source: "user" }],
      missing: [],
    },
    roots: { cwd: input.cwd },
    diagnostics: [],
  };
}

export async function resolveSubagentLaunchContract(input) {
  state.calls.push(structuredClone(input));
  state.trace.push("profile");
  const resolved = contract(input);
  switch (state.mode) {
    case "missing-contract-version":
      delete resolved.version;
      return { ok: true, contract: resolved };
    case "wrong-contract-version":
      resolved.version = 1;
      return { ok: true, contract: resolved };
    case "future-contract-version":
      resolved.version = 3;
      return { ok: true, contract: resolved };
    case "missing-agent":
      return { ok: false, code: "missing_agent", message: "Unknown agent: lane-worker", diagnostics: [] };
    case "ambiguous-agent":
      return { ok: false, code: "ambiguous_agent", message: "Ambiguous agent: lane-worker", diagnostics: [] };
    case "shadowed-agent":
      resolved.agent.shadowedCandidates.push({ name: "lane-worker", selected: false });
      return { ok: true, contract: resolved };
    case "missing-tdd":
      return {
        ok: false,
        code: "missing_skill",
        message: "Missing skills: tdd",
        diagnostics: [{ code: "missing_skill", severity: "error", message: "Missing skills: tdd" }],
      };
    case "duplicate-requested-tdd":
      resolved.skills.requested.push("tdd");
      return { ok: true, contract: resolved };
    case "duplicate-resolved-tdd":
      resolved.skills.resolved.push({ name: "tdd", path: "/fixture/skills/other-tdd/SKILL.md", source: "project" });
      return { ok: true, contract: resolved };
    case "unresolved-tdd":
      resolved.skills.resolved = [];
      return { ok: true, contract: resolved };
    case "error-diagnostic":
      resolved.diagnostics.push({ code: "missing_skill", severity: "error", message: "Missing skills: other" });
      return { ok: true, contract: resolved };
    case "malformed-result":
      return { ok: true, contract: null };
    case "throw":
      throw new Error("fixture preflight failure");
    case "never-settles":
      return new Promise((_resolve, reject) => {
        state.rejectStalledResolver = reject;
      });
    default:
      return { ok: true, contract: resolved };
  }
}
