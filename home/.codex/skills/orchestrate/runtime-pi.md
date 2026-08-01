# Orchestrate — Pi runtime binding

See [dispatch.md](references/dispatch.md) for the runtime-neutral dispatch contract, evidence, acceptance, and
authority rules shared by every runtime. This file states only Pi's own delta.

Pi Root dispatches an admitted implementation lane through the native `subagent` tool. Orchestrate ships
no Pi-specific adapter: transport, control, and evidence are the runtime's own, and Root reads them
directly.

Root launches `lane-worker` with fresh context in async mode. Root records the returned run id, which is
the handle for every later status, evidence, and continuation call.

Root normally passes `turnBudget` for an async writer lane with `maxTurns` no lower than 80 and
`graceTurns` at least 1; a lower ceiling requires a stated reason. At `maxTurns` the child is asked to wrap up, and after
`graceTurns` further assistant turns it is aborted with partial output returned, so a budget bounds a
lane without cutting a write in half. **A budget is not inherited by a continuation:** the recovery
descriptor restores `toolBudget` but not the initial turn budget, so a `resume` that omits
`turnBudget` runs unbounded. Pass it on every resume.

`status` reports `turnBudgetExceeded`, which is how Root tells a budget stop from any other stop.

### When a budget stops a lane

Root chooses; these are the available moves, not a decision procedure. Only the last two lose the
lane's committed work, and only a recut changes the Contract.

| | worker context | lane and its commits | Contract | re-admission |
|---|---|---|---|---|
| `resume` the same run with a larger `turnBudget` | kept | kept | unchanged | no |
| `resume` the same run unchanged (after an `interrupt`) | kept | kept | unchanged | no |
| dispatch a new run into the **same lane** | lost | kept | unchanged | no |
| recut the Slice into a new lane | lost | lost | changed | yes |
| `lane drop` | lost | lost | — | — |

Changing the run is not changing the lane: a lane is a branch and a worktree, a run is the agent
working in it. Raising a budget needs a new run, never a new lane, so it costs neither the Contract
tests already committed nor a fresh admission. Reuse of the worker's context is the cheapest of these
moves — prefer a resume while the worker's understanding of the Contract is still sound, and take a
fresh run when it has drifted.

## Continuation

A `paused`, `completed`, or `failed` run may be resumed with `action: "resume"` under the conditions
`dispatch.md` states; a change in any of them requires Root re-admission and a fresh dispatch instead.
Resume keeps the run id, session, and launch contract, so continuation preserves the worker's context.
Before every resume Root reruns `lane check` and `status` and rebinds the exact SHA.

`action: "interrupt"` softly interrupts the current child turn and leaves the run `paused`; it is the
resumable pause. `action: "stop"` is terminal and a stopped run can never be resumed, so it is reserved
for abandoning a run. `action: "steer"` only delivers guidance: its reply reports that Pi accepted the
input, never that the model complied, so steering is never readiness, compliance, collect, or terminal
evidence.

Root may optionally use a Contract checkpoint on a risky Slice: the worker reports and ends its run after
committing the Contract tests, Root reviews the Contract diff and the exact red evidence, and the same
run is resumed for implementation. This is a tool, not a required step; the admission standard alone
decides when Root must personally rerun a focused red command.

## Evidence

Only the run's `process-terminal` artifact and exact Git checks constitute readiness or terminal
evidence; everything else the runtime exposes is diagnostic, and unknown proof stays unknown.

## Turn boundaries

Long interactive background work returns control after dispatch rather than defaulting to
`subagent_wait`; holding the parent turn delays a compactable boundary and raises context-exhaustion
risk. Before ending an interactive turn or calling `yield_goal`, Root reports concise progress naming
completed evidence, the active run or prerequisite, and the next action or blocker. In goal mode Root
calls `yield_goal` only when work is blocked solely on an external or background prerequisite; outside
goal mode Root ends the turn and Pi wakes the session when background work completes. A bounded
same-turn `subagent_wait` is reasonable only when the current turn must receive the result before it can
finish, the run is expected to finish shortly, and the wait stays within a small explicit bound. Do not
sleep, poll, or repeatedly wait to manufacture same-turn completion.

## Runtime dependency

This binding depends on upstream pi-subagents providing `resume`, `interrupt`, `steer`, `turnBudget`, the
`process-terminal` artifact, and the async status fields named above. It was verified against upstream
0.38.0. Root runs a read-only `subagent action: "doctor"` once at the start of a task to confirm runtime
paths, agent and skill discovery, sessions, and intercom. No further capability probe exists: an
interface change outside that report surfaces at the first failing dispatch, and Root then judges against
this dependency list rather than retrying.

## Authority

Beyond the shared authority in [dispatch.md](references/dispatch.md), Root also owns Slice admission, Contract
semantics and amendments, the S2.4 pre-collect test review, primary-checkout dirt, `lane check`, and
`lane sync`.
