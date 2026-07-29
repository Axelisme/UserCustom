const state = globalThis.__ORCHESTRATE_PI_PROFILE_STATE__;
state.secondImports += 1;

export async function resolveSubagentLaunchContract(input) {
  state.secondCalls += 1;
  return {
    ok: true,
    contract: {
      version: 2,
      agent: { name: "lane-worker", shadowedCandidates: [] },
      context: "fresh",
      skills: {
        requested: ["tdd"],
        resolved: [{ name: "tdd" }],
        missing: [],
      },
      roots: { cwd: input.cwd },
      diagnostics: [],
    },
  };
}
