# Orchestrate — Pi runtime binding

See [dispatch.md](references/dispatch.md) for the runtime-neutral dispatch contract, evidence, acceptance, and
authority rules shared by every runtime. This file states only Pi's own delta.

Pi Root dispatches an admitted implementation lane through the native `subagent` tool. Orchestrate ships
no Pi-specific adapter: transport, control, and evidence are the runtime's own, and Root reads them
directly. Root launches `lane-worker` with fresh context in async mode.

## Budgets

Pass `turnBudget` on every async writer lane and on every resume — the recovery descriptor restores
`toolBudget` but not the turn budget, so a resume that omits it runs unbounded. Any sufficient ceiling
will do (80, 160, 300); the number is not a safety property, because safety comes from the worker's
per-cycle commit discipline. Set no hard `toolBudget`.

This deliberately overrides upstream `pi-subagents/skills/pi-subagents/SKILL.md:93`, which advises
against passing `turnBudget` *or* a hard `toolBudget` to an implementation worker. The two are not the
same kind of limit and upstream's single warning conflates them:

- **`toolBudget` degrades.** Exhausting it blocks read and search tools but leaves mutation tools
  available, producing a worker that can write but cannot see. Upstream's warning holds here.
- **`turnBudget` stops.** It is a soft ceiling — `maxTurns` plus `graceTurns` (default 1) — after
  which the supervisor aborts the process and returns partial output. The worker is told its budget
  **once, at launch**, in its system prompt; process-mode execution has no live steering, so nothing
  warns it as the ceiling approaches and it must track its own turns to wrap up in time. Expect a stop
  it failed to prepare for, and a lane left dirty.

The override is a question of who pays. An unprepared stop costs Root one `resume`. Upstream's
alternative — a narrow task scope, an elapsed deadline, and requested checkpoints instead of a ceiling
— costs Root continuous coordination: 84 `status` and 155 `yield_goal` calls in one observed session.

`status` reports `turnBudgetExceeded`, which is how Root tells a budget stop from any other stop.

### When a budget stops a lane

Root chooses; these are the available moves, not a decision procedure.

| | worker context | lane and its commits | Contract | re-admission |
|---|---|---|---|---|
| `resume` the same run with a larger `turnBudget` | kept | kept | unchanged | no |
| `resume` the same run unchanged (after an `interrupt`) | kept | kept | unchanged | no |
| dispatch a new run into the **same lane** | lost | kept | unchanged | no |
| recut the Slice into a new lane | lost | lost | changed | yes |
| `lane drop` | lost | lost | — | — |

Changing the run is not changing the lane: a lane is a branch and a worktree, a run is the agent
working in it. Reusing the worker's context is the cheapest of these moves — prefer a resume while the
worker's understanding of the Contract is still sound, and take a fresh run once it has drifted.

## Continuation

A `paused`, `completed`, or `failed` run may be resumed with `action: "resume"` under the conditions
`dispatch.md` states; a change in any of them requires Root re-admission and a fresh dispatch instead.

Resume keeps the session and launch contract but **not the run id**: `resumeAsyncRun` mints a fresh one
on every revival (`randomUUID().slice(0, 8)`). Root uses the id `resume` returns for the next status,
evidence, or continuation call — the old id inspects a dead run. Before every resume Root reruns
`lane check` and `status` and rebinds the exact SHA.

`action: "interrupt"` softly interrupts the current child turn and leaves the run `paused`; it is the
resumable pause. `action: "stop"` is terminal and a stopped run can never be resumed, so it is reserved
for abandoning a run. `action: "steer"` only delivers guidance: its reply reports that Pi accepted the
input, never that the model complied, so steering is never readiness, compliance, collect, or terminal
evidence.

Root may use a Contract checkpoint on a risky Slice: the worker reports and ends its run after
committing the Contract tests, Root reviews the Contract diff and the exact red evidence, and the same
run is resumed for implementation. The admission standard alone decides when Root must personally rerun
a focused red command.

## Evidence

Only the run's `process-terminal` artifact and exact Git checks constitute readiness or terminal
evidence; everything else the runtime exposes is diagnostic.

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
