# Orchestrate — Pi runtime binding

## Dispatch

See [dispatch.md](references/dispatch.md) for the runtime-neutral dispatch contract, exact Git
binding, evidence, acceptance, and authority rules shared by every runtime. This file states only
Pi's own delta.

Pi Root dispatches an admitted ticket Contract through Pi Subagents' native `subagent` tool.
Orchestrate ships no Pi-specific adapter: transport, control, and evidence are the runtime's own,
and Root reads them directly. The lane is persistent during the task; Pi supplies the same canonical
cwd and exact identity on every worker call. The neutral ticket, Contract, and context-routing rules
are defined by [dispatch.md](references/dispatch.md); this file states only Pi's transport delta.

## Writer execution

Normal writer launch and resume omit `turnBudget`; no hard `toolBudget` is supplied. An exceptional
budget choice retains one caution: Pi gives the child no approaching-limit warning, so a budget can
hard-cut the child before it can commit and report cleanly. The worker's per-cycle commit discipline remains
the controllable protection against an interrupted turn.

Writer launch and resume never use `subagent_wait`. In ordinary interactive mode, Root reports the
run id, completed evidence, and next action, then ends the turn. In goal-active mode, if the only
blocker is the background writer, Root reports the same concise progress and calls one `yield_goal`.
Neither mode polls or forms a repeated wait loop.

## Root context epochs

A Context Epoch renews Pi Root's context; it does not continue a writer session or change admission,
Contract, lane, persistence, or cleanup authority. At each ticket boundary:

1. **Reconcile.** Bring the durable task record to the exact boundary required by the admission
   standard, including its required refresh. Done when `Current`, `Next`, and the ticket frontier
   agree.
2. **Decide.** An epoch is expected to span roughly one to three tickets, not as a limit. Keep
   related work in the current epoch while its context remains useful.

When Root chooses to transition:

3. **Preflight.** Call `handoff_context_status`. Unless it reports an available grant for the exact
   session, leave the current task's `HANDOFF.md` unchanged and remain in the current epoch.
4. **Seed.** Overwrite that `HANDOFF.md` with exactly this, and nothing else:

   ```
   task: <task-id>
   run:
     plan.py locate <task-id>
     orchestrate.py status --task-id <task-id>
     backlog.py list --status inbox
   why:  <one line: why the handoff>
   open: <one line: the unresolved question left to the next reader>
   ```

   List all three commands; "run the locating commands" is not a substitute. A SHA, a tree, a ref
   name or a user quote must not appear — this file is overwritten between epochs, and a reader
   arriving mid-window must find missing information rather than confident stale instructions.
   Quotes live in the record's `Standing orders`, the one place with a retirement mechanism.
5. **Transition.** Call `handoff_context` with that file as the old epoch's final tool action. Its
   authorization revalidation is authoritative. On `scheduled`, end old-context work.

After transition, run `plan.py locate` and read what it names, then reread the active skill, frozen
spec and admission standard before repeating the required Git and runtime checks.

## Recovery

Before every writer resume Root reruns `lane check` and `status`, then rebinds the exact lane SHA,
cwd, Git root/common-dir, branch, and lane identity. Resume preserves the session and launch
contract but returns a fresh run id; the prior run id no longer identifies the live run. An
`interrupt` leaves a run paused and resumable. A `stop` is terminal. `steer` is advisory and never
proves compliance, readiness, collection, or completion.

After the runtime accepts a resume, use a five-minute minimum quiet window: do not call `status`,
resume again, or poll during that window. Process completion, process-terminal, or needs-attention
events are handled immediately. If no such event arrives, make one status confirmation no earlier
than five minutes after acceptance while leaving the parent turn unblocked. A resume that overlaps
child compaction may otherwise take unusually long.

Use this writer recovery matrix:

| context state | Root action |
| --- | --- |
| context is an asset / trusted | Resume the same session. |
| context is debt / untrusted | Start a fresh run in the same lane. |
| lane is unnecessary | `lane drop`. |

Provider and liveness recovery stays with the same role, profile, and persistent lane. A semantic
Contract change still requires admission; recovery remains in the same lane. Before every resume
Root rebinds the exact cwd, Git root/common-dir, branch, HEAD, base, lane identity, and write scope;
any mismatch fast-fails. Session context never crosses lane identity, cwd, branch, or write scope.

Acceptance re-review is different: `acceptance start` removes and recreates the checkout at the
same canonical lexical cwd. After the prior reviewer process is terminal and the replacement
checkout is complete, Root rebinds its detached, tracked-clean exact SHA and resumes the same
Standards or Spec reviewer session with the prior subject, new subject, and correction range. Each
axis resumes its own session. If that reviewer context is not trusted, Root starts a fresh reviewer
with the prior terminal report supplied explicitly; reviewers use their external `Report path` only.

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
