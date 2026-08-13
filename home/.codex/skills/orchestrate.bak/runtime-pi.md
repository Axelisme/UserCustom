# Orchestrate — Pi runtime binding

## Dispatch

See [dispatch.md](references/dispatch.md) for the runtime-neutral dispatch contract, exact Git
binding, evidence, acceptance, and authority rules shared by every runtime. This file states only
Pi's own delta.

Pi Root dispatches an admitted ticket Contract through Pi Subagents' native `subagent` tool.
Orchestrate ships no Pi-specific adapter; transport, control, and evidence are the runtime's own.

The profile roster is the runtime's own too. What only this binding can say is where each profile
belongs in the admission sequence — a profile's frontmatter is what Pi actually enforces, and a copy
of it in prose would be the second copy that drifts.

| stage | profile |
| --- | --- |
| S2 execution in a lane | `lane-worker`, or `mechanical-implementer` when the change is explicit and repetitive inside a closed write scope |
| S2.8 Contract review | `contract-reviewer` |
| S4 Standards and Spec axes | `acceptance-reviewer`, one session per axis |

`mechanical-implementer` declares no `async`, so it returns inside the dispatching turn and the
silence rules below never apply to it.

## Writer execution

Writer launch and resume never use `subagent_wait`. In ordinary interactive mode, Root reports the
run id, completed evidence, and next action, then ends the turn. In goal-active mode, if the only
blocker is the background writer, Root reports the same concise progress and calls one `yield_goal`.
Neither mode polls or forms a repeated wait loop.

## Context management

ACP owns session-context management for Pi Root and child sessions. Every shipped profile exposes
`compress`, `decompress`, `search_context`, and `acp_status`; these tools change session context
only. Pi Subagents remains the only delegation control plane, and ACP does not grant delegation,
admission, readiness, evidence, or checkout authority.

## Recovery

Resume preserves the session and launch contract but returns a fresh run id; the prior run id no
longer identifies the live run. An `interrupt` leaves a run paused and resumable. A `stop` is
terminal. `steer` is advisory and never proves compliance, readiness, collection, or completion. The
identity binding is rebound on a resume exactly as [dispatch.md](references/dispatch.md) binds it on
a dispatch.

Use the worker context routing in [dispatch.md](references/dispatch.md).

For acceptance re-review, after the prior reviewer process is terminal and `acceptance start`
recreates the checkout, one `subagent` fleet query settles each axis. A session the fleet still
lists resumes with the prior subject, new subject, and correction range. Every other answer —
an empty fleet included — starts a fresh reviewer carrying the prior axis report from disk,
supplied explicitly; that report is the durable form of the prior verdict, and the fleet query is
the whole of the search this rule asks for.

Never reconstruct a reviewer's context from the session store. One measured re-review read
`No active subagent fleet`, then spent 156KB parsing the previous day's session JSONL to recover
conclusions that were already on disk in the axis report whose filename it was grepping for. The
prior reviewer's context is not a thing to recover; its report is, and it is one read away.

The shared checkout binding and report rules remain in [admission.md](references/admission.md).

## Reading silence

A resumed child that says nothing is the ambiguous case this runtime is shaped around. Three states
produce the same silence:

| the child is | wake fires on completion | correct action |
| --- | --- | --- |
| still working | yes | wait |
| compacting | yes | wait |
| hard-cut by an exhausted turn budget | **no** — wake excludes `turn-budget-exceeded` | the run is over |

Nothing separates them from outside. Pi exposes no compaction state and no child heartbeat, so
elapsed time is the only instrument available, and that is why a timer stands where a check belongs.

**Assume the child is alive.** The two errors do not cost the same: killing a compacting child
discards the whole worker context and buys a fresh run in the same lane, while waiting on a child
that is already gone costs the wait. Hold that assumption for five minutes after the runtime accepts
a resume, then make one status confirmation, leaving the parent turn unblocked. Process completion,
process-terminal, and needs-attention events are handled the moment they arrive.

Five minutes is a felt bound, not a measurement. It was chosen to sit above an observed child
compaction rather than to match one, after a run was interrupted as dead while it was only
compacting and its context was spent re-establishing what it already knew. The way to shorten it is
to measure a compaction, or to find a signal that separates the first two rows from the third; the
timer retires the moment either exists.

Normal writer launch and resume therefore omit `turnBudget`, and no hard `toolBudget` is supplied.
That is what keeps the third row empty, leaving silence with only its two harmless explanations. An
exceptional budget choice re-opens it: Pi gives the child no approaching-limit warning, so a budget
can hard-cut the child before it commits and reports cleanly. The worker's per-cycle commit
discipline is the controllable protection against an interrupted turn.

## Evidence

Terminal/readiness evidence is mode-aware. Detached async runs require public Pi
`process-terminal.json` proof whose state is `observed`. Workflow runs require public workflow
`complete`, target child `completed`, and target child `exitCode` zero. Both modes also require
Git identity, clean-state, and gate evidence; timestamps, result files, and PID disappearance
alone are not proof; private candidate proof and public `unknown` are diagnostic only.

## Runtime dependency

Bind this runtime to capabilities rather than a version string. The agent profile declares what the
runtime enforces — `async`, `defaultContext`, `tools`, `inheritSkills`, `systemPromptMode` — and a
missing declaration fails at dispatch, so it is not restated here. Beyond them this binding depends
on:

- `resume`, `interrupt`, `steer`, and terminal `stop`, with the semantics above;
- persisted sessions and a fresh run id after resume;
- lifecycle/status projection; and
- the mode-aware public terminal projection described in Evidence.

At task start Root runs one read-only `subagent doctor` to confirm runtime paths, agent and skill
discovery, sessions, and intercom. Stop when a required capability is missing or its behavior does
not match this binding.

## Authority

Shared authority remains defined by [this skill](SKILL.md) and
[dispatch.md](references/dispatch.md); Pi runtime capabilities grant no additional lifecycle or
persistence authority.
