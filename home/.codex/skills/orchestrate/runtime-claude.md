# Orchestrate — Claude Code runtime binding

Current tool availability is authoritative. Claude subagents start fresh; their prompt must
carry the objective, workdir/scope, basis, acceptance, authority, stop conditions,
checkpoint budget, and artifact pointers.

## Tool and profile binding

| capability | Claude tool |
|---|---|
| spawn | `Agent` with the requested `subagent_type`; fall back explicitly to `general-purpose` |
| milestone / follow-up | `SendMessage`, only when currently exposed |
| interrupt | `TaskStop` |
| wait/status | background completion plus `Monitor`, `TaskList`, `TaskGet`, `TaskOutput` |
| ephemeral isolation | `Agent(isolation="worktree")` |

Profile names map to registered user/repo agents. A selected profile/model/worktree is an
observed capability, not something config alone proves. A long direct contract travels as a
plain file whose absolute path the dispatch names.

## Milestones and flow control

The envelope schema, delivery rule, and liveness triggers live in
[coordination](references/coordination.md). When `SendMessage` exists, send each envelope
through it at the boundary; root measures its own wall-clock bound while waiting. If
`SendMessage` is absent, root must predeclare a one-item final-response fallback; when
same-identity continuation is required and `SendMessage` is absent, return
`needs_decision` — never respawn and call it continuity.

- Spawn independent background agents together, then advance on completion events — not
  polls.
- The runtime task list may carry a **projection** of wave state for the user's benefit —
  it is the only surface they see without asking. Write it one-directionally from a derived
  read (`wave status`) at a serial turn, and never read it back to decide anything: the
  moment it informs a decision it has become hand-kept state that drifts from Git.
- Use `TaskStop` for urgent invalidation, then continue the same identity when possible.

## Capability boundaries

Parking, retirement, slot accounting, and role switching are runtime capabilities, not
skill assumptions. A role switch reloads the profile and never makes an implementer an
independent reviewer. Workers do not spawn sub-agents. Read-only roles remain behaviorally
read-only even when the runtime cannot enforce a separate sandbox. Experimental agent
teams remain outside this binding because their autonomous task/mailbox state bypasses
root authority.
