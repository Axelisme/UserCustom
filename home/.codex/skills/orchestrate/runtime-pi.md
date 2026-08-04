# Orchestrate — Pi runtime binding

## Dispatch

See [dispatch.md](references/dispatch.md) for the runtime-neutral dispatch contract, exact Git
binding, evidence, acceptance, and authority rules shared by every runtime. This file states only
Pi's own delta.

Pi Root dispatches an admitted ticket Contract through Pi Subagents' native `subagent` tool.
Orchestrate ships no Pi-specific adapter; transport, control, and evidence are the runtime's own.

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

A Context Epoch changes Pi Root's model-context projection; it does not continue a writer session
or change admission, Contract, lane, persistence, or cleanup authority. At each ticket boundary:

1. **Reconcile.** Bring the durable task record to the exact boundary required by the admission
   standard, including its required refresh. Done when `Current`, `Next`, and the ticket frontier
   agree.
2. **Decide.** Keep related work in the current epoch while its context remains useful; this usually
   spans one to three tickets, not as a limit.

When Root chooses to transition:

3. **Preflight.** Call `handoff_context_status`. Unless it reports an available grant for the exact
   session, remain in the current epoch.
4. **Seed.** Prepare exactly this inline handoff, and nothing else:

   ```
   task: <task-id>
   run:
     plan.py locate <task-id>
     orchestrate.py status --task-id <task-id>
     backlog.py list --status inbox
   why:  <one line: why the handoff>
   open: <one line: the unresolved question left to the next reader>
   ```

   Do not replace the three commands with prose. A SHA, tree, ref name or user quote must not
   appear; the seed is a locator, and those values can become stale. Quotes live in the record's
   `Standing orders`, the one place with a retirement mechanism.
5. **Transition.** Call `handoff_context` with the complete inline seed as the old epoch's final tool
   action. Its authorization revalidation is authoritative. On `scheduled`, end old-context work.

After transition, run `plan.py locate` and read what it names, then reread the active skill, frozen
spec and admission before repeating the required Git and runtime checks.

## Recovery

Before every writer resume Root reruns `lane check`, which reports the exact lane SHA and base it
just measured, and rebinds that SHA. A resume into a session that already attested its cwd, Git
root/common-dir and branch rebinds only that SHA and the scope of the call; a fresh run in the lane
rebinds the full identity. Resume preserves the session and launch
contract but returns a fresh run id; the prior run id no longer identifies the live run. An
`interrupt` leaves a run paused and resumable. A `stop` is terminal. `steer` is advisory and never
proves compliance, readiness, collection, or completion.

After the runtime accepts a resume, use a five-minute minimum quiet window: do not call `status`,
resume again, or poll during that window. Process completion, process-terminal, or needs-attention
events are handled immediately. If no such event arrives, make one status confirmation no earlier
than five minutes after acceptance while leaving the parent turn unblocked. A resume that overlaps
child compaction may otherwise take unusually long.

Use the worker context routing in [dispatch.md](references/dispatch.md).

For acceptance re-review, after the prior reviewer process is terminal and `acceptance start`
recreates the checkout, resume each trusted axis reviewer session with the prior subject, new
subject, and correction range. If its context is untrusted, start a fresh reviewer with the prior
terminal report supplied explicitly. The shared checkout binding and report rules remain in
[admission.md](references/admission.md).

## Evidence

Writer terminal/readiness evidence requires public Pi `process-terminal.json` proof whose state is
`observed`, together with the identity checks required by [dispatch.md](references/dispatch.md).
Async `complete`, timestamps such as `endedAt`, result/output files, PID disappearance, private
candidate proof, and public `unknown` are diagnostic only; none substitutes for the public
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
not match this binding.

## Authority

Shared authority remains defined by [this skill](SKILL.md) and
[dispatch.md](references/dispatch.md); Pi runtime capabilities grant no additional lifecycle or
persistence authority.
