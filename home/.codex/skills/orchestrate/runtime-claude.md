---
orchestrate_compat: 54
---

# Orchestrate — Claude Code runtime binding

This file is the hand-written **Claude Code** companion for the `orchestrate` skill. It maps
the skill's abstract capabilities (spawn / follow-up / interrupt / wait / status) to the tools
actually exposed in this runtime. It is hand-maintained and lives inside the skill directory
as `runtime-claude.md`; the Codex counterpart is `runtime-codex.md`.

## Tool binding

| skill capability | Claude Code tool |
|---|---|
| spawn | `Agent` (`prompt` carries the full context; `subagent_type` selects the profile; `model`, `isolation:"worktree"`, `run_in_background`) |
| message (add context) | `SendMessage` (by agent id/name) — **see capability flag below** |
| follow-up (same identity, next slice) | `SendMessage` (same agent id/name; context preserved) — **see capability flag below** |
| interrupt | `TaskStop` |
| wait / event | subagents run in the background by default and notify the lead on completion; use `Monitor` for active waiting |
| status | `TaskList` / `TaskGet` / `TaskOutput` |
| ephemeral worktree isolation | `Agent` with `isolation:"worktree"` (single-agent, auto-cleanup). Durable / cross-terminal worktrees use plain `git worktree` per `references/git-coordination.md` |

Profiles map to `Agent`'s `subagent_type`: `contract-planner`, `repo-investigator`,
`web-researcher`, `implementer`, `mechanical-implementer`, `reviewer`, `integration-reviewer`,
`mcp-skill-tester` (registered as user-level Claude Code agent types in `~/.claude/agents/`;
a repo may override or extend them with its own `.claude/agents/`). If a profile is not
registered in the current session, fall back to `general-purpose` and say so.

For a pipelined slice queue, this compact prompt shape is a useful Claude-oriented starting
point. Omit fields that add no value for a small or exploratory task:

```text
profile_requested=<subagent_type>
profile_effective=<selected subagent_type/model/isolation>
lease + write scope: <domain ownership and the only files this writer may change>
ordered slices:
  1. <slice; acceptance; targeted tests>
  2. <slice; acceptance; targeted tests>
stop conditions: <when to checkpoint and return needs_decision>
milestone delivery: SendMessage(slice, checkpoint_kind, kind-specific evidence, next)
  when available
```

`finding_class` is `none`, `mechanically-propagatable`, `design-invalidating`,
`dangerous-intermediate`, or `scope-collision`; the final three are retract classes.
`checkpoint_kind` is `progress`, `validated`, or `review`. Progress carries `completion`,
`stop_reason`, `finding_class`, and `next`, plus optional provisional `diagnostics`, while
omitting SHA/validation. Diagnostics are non-gating, non-review evidence and never authorize
run-ahead. Validated/review carry exact `sha`, `finding_class`,
`validation=tdd-green(...)|targeted-acceptance(...)`, and
`remaining_uncertainty=behavior-only|structural|hard-critical|anomaly`.
`checkpoint_kind=review` freezes its SHA and creates review debt. Validated (or normal review)
with behavior-only uncertainty may run ahead; progress never authorizes the next slice.

The labels make runtime adaptation visible; they are not a mandatory report schema.

## Capability flag: same-identity continuation

`SendMessage` is the only implementation of follow-up / domain-lease continuation.

- **Official `claude` CLI**: `SendMessage` is gated behind `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`,
  and the gate is deliberate. With the flag off (default) the tool does not exist and no
  subagent can be continued.
- **This build** may expose `SendMessage` directly. **Do not assume** — check whether
  `SendMessage` is in the currently available tool list.

**When absent (hard rule, overrides any auto-degradation):** if same-identity continuation is
needed and `SendMessage` is unavailable → stop and report `needs_decision` to the user. Do
**not** silently respawn a fresh identity and rebuild context from reports, and do not guess
tool names. (One-shot fan-out — spawn → background → completion notification → collect —
needs no `SendMessage` and is unaffected.)

## Flow control

- Subagents run in the background by default and notify the lead on completion — never build
  polling loops. Spawn independent agents in a single message so they actually run in
  parallel.
- **Warm-up = early background spawn of read-only roles.** While the contract is still being
  discussed, an investigator can already build its source map in the background — speculative
  read-only work costs nothing to discard. Writers are never spawned speculatively; they
  start only after the contract is frozen.
- **Slice long work vertically.** Deliver in reviewable slices with an event per finished
  slice, so root integrates early and steers — never wait for one giant black-box delivery.
- **Stalls: interrupt, then correct — don't respawn.** Inspect with `TaskOutput`/`Monitor`,
  stop with `TaskStop`, then continue the *same* agent via a `SendMessage` follow-up carrying
  the corrective delta. Its loaded context is an asset; respawning a fresh identity throws it
  away (and, per the skill, needs an articulable reason).
- **Pipelined slices** — a recommended option for frozen contracts; the pattern and its
  guardrails (run-ahead, append-only commits, retract-class protocol) live in
  `references/slice-queues.md`. When available, the implementer pushes the useful subset of
  `slice / checkpoint_kind / next` plus the fields required by that kind via `SendMessage`
  and normally continues without an ack. When
  `SendMessage` is unavailable,
  root may instead let a fully pre-authorized queue
  finish in one turn or dispatch a single slice and stop at completion, depending on steering
  risk. If the next step requires same-identity continuation, follow the capability rule above
  and return `needs_decision`; do not claim that a fresh spawn is a continuation.

## Fork context policy

Claude Code subagents are **always fresh** — they inherit none of the lead's conversation
history. The spawn `prompt` must therefore carry everything: objective, workdir, file scope,
frozen decisions, acceptance commands, stop conditions, and artifact pointers.

## Model and sandbox mapping

- **Model tier**: use `Agent`'s `model` — high → `opus`, mid → `sonnet`, low → `haiku`
  (omit to inherit the session model).
- **Sandbox**: Claude Code does not enforce per-agent read-only. Read-only roles are
  approximated by the agent definition's tools allowlist (no `Edit`/`Write`/`NotebookEdit`);
  regardless of enforcement, a read-only role writing files is a behavioral violation.
- **Nesting**: workers must not spawn sub-agents (skill policy, stricter than the runtime).

## Agent teams: evaluated and not adopted

Claude Code's experimental agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) were
evaluated and rejected for this skill; the binding stays on native subagents. Reasons:

- Teams coordinate through state files (`~/.claude/tasks/{team}/`, mailbox JSONs under
  `~/.claude/teams/`) — exactly the workflow-state machinery the skill forbids; that state
  also lives outside Git, so `/resume` cannot restore it (crash recovery breaks).
- Teammates self-claim tasks and message each other without the lead, bypassing root's
  steering points: write-scope declaration, run-ahead retraction, severity-routed
  preemption.
- Experimental reliability (task-status lag, unmarked completions) and ~3–4× token cost.

Native `Agent` + `SendMessage` already covers the load-bearing needs: same-identity
follow-up (domain lease), background execution with completion events, parallel read-only
fan-out. Revisit only if teams gain a root-mediated mode and Git-recoverable state.
