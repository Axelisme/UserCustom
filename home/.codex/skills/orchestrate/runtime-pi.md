# Orchestrate — Pi runtime binding

Pi Root dispatches an admitted implementation lane only through the versioned
`orchestrate_pi` tool. The executable Adapter has exactly two actions:
`dispatch-lane` and `attest-run`. There is no raw `subagent` fallback. An unknown
version, action, or field; a canonical cwd/Git mismatch; an incompatible RPC
capability response; or an invalid receipt fails closed.

For `dispatch-lane`, Root supplies the frozen objective, canonical lane cwd,
expected Git root/common-dir, branch, full subject SHA, clean-state expectation,
write scope, immutable paths, primary-checkout dirt snapshot, focused commands,
evidence, and stop conditions. Root may also supply an explicit `turnBudget`
with safe-integer `maxTurns >= 1` and optional `graceTurns >= 0` (default 1).
The Adapter verifies canonical Git identity before RPC, probes RPC v1 plus async
spawn, status, non-recovering steer, stop, process-terminal proof v1, and
lifecycle artifact v3, then fixes the upstream launch to `lane-worker`, fresh
context, async mode, and no clarification. An explicit budget is the upstream
run override; omission passes no budget or notice control and preserves upstream
inheritance. The Adapter subscribes to the exact reply channel before emitting.
It returns only the unchanged structured exact-run receipt. If spawn may have
started but that receipt is invalid, it reports orphan risk and best-effort stops
that exact `runId`; it never redispatches automatically.

For an explicit budget, the Adapter derives the notice turn as
`max(1, maxTurns - min(ceil(maxTurns * 0.10), 10))`. It raises time/token active
notice thresholds to the safe-integer ceiling so the turn threshold owns the one
notice. One same-parent-session async lane-worker turn event may cause one exact
run/index-0 handoff steer after canonical async-directory and running
status/cwd/digest/session correlation. The steer disables recovery, is never
retried, and only asks the worker to make state safe and return the existing
lane-ready or blocked evidence; it is not readiness or compliance evidence.
Wrong, forged, early, duplicate, post-terminal, and cross-run events do nothing.
The bounded observer is ephemeral: reload can lose the best-effort notice while
the upstream budget and hard abort remain active. The private control-event
coupling was tested with pi-subagents 0.37.2; package drift is not refused and may
also lose this notice without weakening the upstream hard budget.

Root retains the opaque receipt and calls `attest-run` for the same run.
`process-terminal.json` is the primary durable proof, the exact status overlay is
fallback evidence, and the process event is wake-up only. Execution state and
process-terminal/canonical-session-lease evidence remain independent. Missing,
pending, not-started, malformed, mismatched, or otherwise unknown proof stays
unknown. Result-file presence, `endedAt`, PID disappearance, lease-directory
absence, human-readable RPC text, and turn/steering state are never terminal or
readiness evidence.

The Adapter is transport and exact-run evidence projection only. It does not
create or discover lanes, mutate Git, maintain a run registry, enumerate matching
runs, decide lane readiness, grant collect or acceptance, or wrap upstream steer,
interrupt, stop, or resume operations. Root still owns Slice admission, Contract
semantics and amendments, S2.4 pre-collect test review, primary-checkout dirt,
collect, candidate, landing, and recovery. Native lifecycle continuation is valid
only while the frozen Contract, provider, cwd, and lane identity remain unchanged;
a change requires Root re-admission and a fresh authorized dispatch.
