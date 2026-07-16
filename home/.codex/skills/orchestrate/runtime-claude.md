---
orchestrate_compat: 64
---

# Orchestrate — Claude Code runtime binding

Current tool availability is authoritative. Claude subagents start fresh; their prompt must
carry the objective, workdir/scope, basis, acceptance, authority, stop conditions, checkpoint
budget, and artifact pointers.

## Tool and profile binding

| capability | Claude tool |
|---|---|
| spawn | `Agent` with the requested `subagent_type`; fall back explicitly to `general-purpose` |
| milestone / follow-up | `SendMessage`, only when currently exposed |
| interrupt | `TaskStop` |
| wait/status | background completion plus `Monitor`, `TaskList`, `TaskGet`, `TaskOutput` |
| ephemeral isolation | `Agent(isolation="worktree")` |

Profile names map to registered user/repo agents. A selected profile/model/worktree is an
observed capability, not something config alone proves. For a long direct contract, send an
immutable dispatch-packet absolute path and SHA-256; for a spool consumer, send queue path,
role, lease, generation, and adapter command.

## One milestone

When `SendMessage` exists, every item sends one envelope before continuing or ending:

```text
event=milestone
item_id=<stable id>
state=progress|terminal
outcome=<role-specific outcome>
subject_sha=<exact SHA when applicable>
evidence=<compact result or artifact pointer>
findings=<ids or []>
next=continue|idle|stop
```

The final response does not duplicate it; runtime completion means only that the turn ended.
If `SendMessage` is absent, root must predeclare a one-item final-response fallback. When
same-identity continuation is required and `SendMessage` is absent, return `needs_decision`;
never respawn and call it continuity.

## Flow control

- Spawn independent background agents together, then advance on completion events—not polls.
- Ready direct work wakes an idle identity. Running spool consumers discover routine additions
  at item boundaries; root also inspects once on their completion event to avoid lost wakeup.
- Major finding, retract, correction, and stop remain direct. Use `TaskStop` for urgent
  invalidation, then continue the same identity when possible.
- Pass may continue to a complete pre-authorized review target; other outcomes stop unless
  independent continuation was frozen. Hard-critical dependent work waits.

## Stalled work

Liveness recovery has exactly three triggers: the runtime reports the task errored or a
model/capacity failure; the runtime declares its lease/continuation lost; or the
dispatch-declared checkpoint budget passes with no milestone. Everything else is healthy: a
running task with no tool activity is model reasoning, a `Monitor`/wait timeout is normal
silence to wait on again, and fixed-interval status polling of a sub-agent is forbidden.
There is no universal timer. Updating the user never requires touching the assignee — report
from the last milestone, read-only Git, and the frozen dispatch.

When a trigger fires:

1. inspect runtime activity/waiting metadata when available, without Git/process polling;
2. send one liveness ping asking for progress, blocker, or a coherent checkpoint;
3. without a response, interrupt and resume the same identity with a recovery delta. Use a
   replacement only for unavailable continuity, a changed domain, or required independence.

## Capability boundaries

Official Claude `SendMessage` may require an experimental flag; check the live tool list.
Parking, retirement, slot accounting, and role switching are runtime capabilities, not skill
assumptions. A role switch reloads the profile and never makes an implementer an independent
reviewer. Workers do not spawn sub-agents. Read-only roles remain behaviorally read-only even
when the runtime cannot enforce a separate sandbox.

Experimental agent teams remain outside this binding because their autonomous task/mailbox
state bypasses root authority. Reconsider only if they gain root-mediated, recoverable state.
