# Orchestrate — Pi runtime binding

## Dispatch

See [dispatch.md](references/dispatch.md) for the runtime-neutral dispatch contract, exact Git
binding, evidence, acceptance, and authority rules shared by every runtime. This file states only
Pi's own delta.

Pi Root dispatches an admitted implementation lane through Pi Subagents' native `subagent` tool.
Orchestrate ships no Pi-specific adapter: transport, control, and evidence are the runtime's own,
and Root reads them directly. Root launches `lane-worker` with fresh context in async mode.

## Writer execution

Normal writer launch and resume omit `turnBudget`; no hard `toolBudget` is supplied. An exceptional
budget choice retains one caution: Pi gives the child no approaching-limit warning, so a budget can
hard-cut the child before it can hand off cleanly. The worker's per-cycle commit discipline remains
the controllable protection against an interrupted turn.

Writer launch and resume never use `subagent_wait`. In ordinary interactive mode, Root reports the
run id, completed evidence, and next action, then ends the turn. In goal-active mode, if the only
blocker is the background writer, Root reports the same concise progress and calls one `yield_goal`.
Neither mode polls or forms a repeated wait loop.

## Recovery

Before every resume Root reruns `lane check` and `status`, then rebinds the exact lane SHA, cwd,
Git root/common-dir, branch, and lane identity. Resume preserves the session and launch contract
but returns a fresh run id; the prior run id no longer identifies the live run. An `interrupt`
leaves a run paused and resumable. A `stop` is terminal. `steer` is advisory and never proves
compliance, readiness, collection, or completion.

After the runtime accepts a resume, use a five-minute minimum quiet window: do not call `status`,
resume again, or poll during that window. Process completion, process-terminal, or needs-attention
events are handled immediately. If no such event arrives, make one status confirmation no earlier
than five minutes after acceptance while leaving the parent turn unblocked. A resume that overlaps
child compaction may otherwise take unusually long.

Use this four-row recovery matrix:

| trusted state | Root action |
| --- | --- |
| Contract and session context are trusted | Resume the same session. |
| Contract is unchanged but old context is not trusted | Start a fresh run in the same lane. |
| Contract or observable behavior changed | Re-admit and recut. |
| The lane is no longer needed | `lane drop`. |

A provider, cwd, lane identity, public Interface, or observable Contract change also requires fresh
admission. A new lane always receives a fresh child session, even when its ticket and profile are
shared; session context never crosses lane identity, cwd, branch, or write scope.

## Evidence

Writer terminal/readiness evidence requires public Pi `process-terminal.json` proof whose state is
`observed`, together with exact Git checks. `lane check` and the exact identity checks must agree on
the expected branch, HEAD/base, first-parent topology, clean tree, cwd, Git root/common-dir, and
lane binding. Async `complete`, timestamps such as `endedAt`, result/output files, PID disappearance,
private candidate proof, and public `unknown` are diagnostic only; none substitutes for the public
`observed` proof.

## Runtime dependency

Bind this runtime to capabilities rather than a version string. Pi Subagents must provide:

- async writer dispatch;
- `resume`, `interrupt`, `steer`, and terminal `stop`;
- persisted sessions and a fresh run id after resume;
- lifecycle/status projection; and
- public process-terminal proof with the `observed` state.

At task start Root runs one read-only `subagent doctor` to confirm runtime paths, agent and skill
discovery, sessions, and intercom. Stop when a required capability is missing or its behavior does
not match this binding; a different version string alone is not a rejection. Pi Subagents `0.40.0`
is the last verified version, not a version pin or a standalone refusal condition.

## Authority

Beyond the shared authority in [dispatch.md](references/dispatch.md), Root owns Slice admission,
Contract semantics and amendments, validation-mode choice, the S2.4 pre-collect review, primary
checkout dirt, `lane check`, `lane sync`, recovery, collection, acceptance, landing, reporting,
removal, setup, and pin decisions. This runtime binding grants no implicit admission, collection,
acceptance, persistence, setup, pin, cleanup, or task-narrative authority.
