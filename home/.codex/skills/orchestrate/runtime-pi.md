# Orchestrate — Pi runtime binding

Pi Root dispatches an admitted implementation lane through the native `subagent` tool. Orchestrate ships
no Pi-specific adapter: transport, control, and evidence are the runtime's own, and Root reads them
directly.

Before dispatch Root runs `lane check --task-id <task> --lane-id <lane>`, which must exit 0, and reads
`status --task-id <task>` to record the exact lane tip SHA. The launch carries that SHA together with the
frozen objective, canonical lane cwd, expected Git root/common-dir, branch, write scope, immutable paths,
primary-checkout dirt snapshot, focused commands, evidence, and stop conditions. Root launches
`lane-worker` with fresh context in async mode. Working inside the canonical lane cwd is the only hard
contract; the agent name, its skills, and the context mode are recommendations. The worker reports the
cwd, Git root/common-dir, branch, HEAD, and clean state it observes, and Root judges whether they match
the admitted lane; the worker runs no mechanical self-check and does not block itself. Root records the
returned run id, which is the handle for every later status, evidence, and continuation call.

Root normally passes `turnBudget` for an async writer lane with `maxTurns` no lower than 80 and
`graceTurns` at least 1; a lower ceiling requires a stated reason. At `maxTurns` the child is asked to wrap up, and after
`graceTurns` further assistant turns it is aborted with partial output returned, so a budget bounds a
lane without cutting a write in half.

## Continuation

A `paused`, `completed`, or `failed` run may be resumed with `action: "resume"` while the frozen
Contract, provider, cwd, and lane identity are all unchanged; a change in any of them requires Root
re-admission and a fresh dispatch instead. Resume keeps the run id, session, and launch contract, so
continuation preserves the worker's context. Before every resume Root reruns `lane check` and `status`
and rebinds the exact SHA.

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

Root owns Slice admission, Contract semantics and amendments, the S2.4 pre-collect test review,
primary-checkout dirt, `lane check`, `lane sync`, collection, acceptance, landing, reporting, removal,
and recovery. After every lane is collected and the shared gates pass, Root uses `acceptance start` and
`acceptance result` for the exact integration subject; only the accepted subject may become landed.
Persistence drift routes through a new admitted writer lane and `integration reconcile`, followed by
normal collection and renewed acceptance. `timing pause` and `timing resume` bracket external waits and
grant no lifecycle authority.
