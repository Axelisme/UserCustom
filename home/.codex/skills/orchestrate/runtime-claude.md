---
orchestrate_compat: 80
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

## Milestones

The envelope schema, delivery rule, review-continuation rule, and liveness triggers live in
[Delegation and review](references/delegation-and-review.md). When `SendMessage` exists,
send each envelope through it at the boundary; root measures its own wall-clock bound while
waiting, and the worker's cadence stays in discrete units. Cross-identity pipelining bases
only on a seam-ready SHA ([Git coordination](references/git-coordination.md)).
If `SendMessage` is absent, root must predeclare a one-item final-response fallback. When
same-identity continuation is required and `SendMessage` is absent, return `needs_decision`;
never respawn and call it continuity.

## Flow control

- Spawn independent background agents together, then advance on completion events—not polls.
- Ready direct work wakes an idle identity. Running spool consumers discover routine additions
  at item boundaries; root also inspects once on their completion event to avoid lost wakeup.
- Use `TaskStop` for urgent invalidation, then continue the same identity when possible.

## Capability boundaries

Official Claude `SendMessage` may require an experimental flag; check the live tool list.
Parking, retirement, slot accounting, and role switching are runtime capabilities, not skill
assumptions. A role switch reloads the profile and never makes an implementer an independent
reviewer. Workers do not spawn sub-agents. Read-only roles remain behaviorally read-only even
when the runtime cannot enforce a separate sandbox.

Experimental agent teams remain outside this binding because their autonomous task/mailbox
state bypasses root authority. Reconsider only if they gain root-mediated, recoverable state.
