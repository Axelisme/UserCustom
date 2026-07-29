# Orchestrate — Pi runtime binding

Pi Root dispatches an admitted implementation lane only through the versioned
`orchestrate_pi` tool. The executable Adapter has exactly two actions:
`dispatch-lane` and `attest-run`. There is no raw `subagent` fallback. An unknown
version, action, or field; a canonical cwd/Git mismatch; an incompatible RPC
capability response; or an invalid receipt fails closed.

For `dispatch-lane`, Root supplies the frozen objective, canonical lane cwd,
expected Git root/common-dir, branch, full subject SHA, clean-state expectation,
write scope, immutable paths, primary-checkout dirt snapshot, focused commands,
evidence, and stop conditions. The Adapter verifies canonical Git identity before
RPC, probes RPC v1 plus async spawn, status, stop, process-terminal proof v1, and
lifecycle artifact v3, then fixes the upstream launch to `lane-worker`, fresh
context, async mode, and no clarification. The Adapter subscribes to the exact
reply channel before emitting. It returns only a structured exact-run receipt.
If spawn may have started but that receipt is invalid, it reports orphan risk and
best-effort stops that exact `runId`; it never redispatches automatically.

Root retains the opaque receipt and calls `attest-run` for the same run.
`process-terminal.json` is the primary durable proof, the exact status overlay is
fallback evidence, and the process event is wake-up only. Execution state and
process-terminal/canonical-session-lease evidence remain independent. Missing,
pending, not-started, malformed, mismatched, or otherwise unknown proof stays
unknown. Result-file presence, `endedAt`, PID disappearance, lease-directory
absence, and human-readable RPC text are never terminal evidence.

The Adapter is transport and exact-run evidence projection only. It does not
create or discover lanes, mutate Git, maintain a run registry, enumerate matching
runs, decide lane readiness, grant collect or acceptance, or wrap upstream steer,
interrupt, stop, or resume operations. Root still owns Slice admission, Contract
semantics and amendments, S2.4 pre-collect test review, primary-checkout dirt,
collect, candidate, landing, and recovery. Native lifecycle continuation is valid
only while the frozen Contract, provider, cwd, and lane identity remain unchanged;
a change requires Root re-admission and a fresh authorized dispatch.
