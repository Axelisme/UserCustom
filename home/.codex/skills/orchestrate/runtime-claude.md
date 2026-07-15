---
orchestrate_compat: 60
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
| ephemeral worktree isolation | `Agent` with `isolation:"worktree"` (single-agent, auto-cleanup). Durable / cross-terminal worktrees use plain Git or the entrypoint's explicit guarded aliases per `references/git-coordination.md` |

Profiles map to `Agent`'s `subagent_type`: `contract-planner`, `repo-investigator`,
`web-researcher`, `implementer`, `mechanical-implementer`, `reviewer`, `integration-reviewer`,
`mcp-skill-tester` (registered as user-level Claude Code agent types in `~/.claude/agents/`;
a repo may override or extend them with its own `.claude/agents/`). If a profile is not
registered in the current session, fall back to `general-purpose` and say so.

When different identity or a warm reviewer matters, use the entrypoint's `orchestrate
identity` pseudo command with the runtime-observed agent id, selected profile, writer id, and
`park_capability=slot-free|slot-held|unknown`. The hash report proves profile content, not
that the runtime selected or parked it; capability still comes from current tools.

For any pipelined role, use the same compact contract. Omit fields that add no value for a
small or exploratory task:

```text
profile_requested=<subagent_type>
profile_effective=<selected subagent_type/model/isolation>
lease: <role/domain; writer scope or reviewer immutable scope>
wave + basis: <wave id; exact SHA/ADR/contract assumptions>
ordered items or spool binding:
  <direct items, or absolute queue path + role + lease_id + lease_generation>
continue_without_ack: <qualifying outcome and dependency rule>
stop conditions: <when to checkpoint and return needs_decision>
milestone delivery: SendMessage(<role milestone and next>) when available
```

For a v60 normal writer/reviewer spool, the spawn prompt also names the canonical agent task
name and absolute queue path. The inventory milestone echoes role, lease ID, and
`lease_generation` before consumption. It also provides the exact `orchestrate queue` adapter
command; agents never hand-edit published files. Planner and hard-critical work remain direct.

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
When `SendMessage` exists, every packet carries `delivery_phase=milestone` and is sent before
the final response; a single-item turn is not exempt. The pre-final checklist confirms the
message succeeded and enum/required fields are valid. Without `SendMessage`, root must
predeclare the one-item final-response fallback; it is capability degradation, not a normal
milestone.
For a spool item, a writer removes it only after a delivered terminal validated/review
milestone; progress retains it. A reviewer removes it only after its terminal verdict is
delivered. Both inspect after inventory, at each item boundary, and pre-final—not on a timer.
Malformed, stale, stopped, or undelivered items remain for reconciliation.
Root may lint a supplied packet, but `delivery_phase` is only a declaration; the linter does
not prove that `SendMessage` preceded the final response.

Planner reports `PLAN_MILESTONE` with `wave`,
`planning_mode=contract-resolution|wave-ahead`, basis, invalidators,
`items=<target=3-5;tail=1-2 natural slices>`, and `outcome=proposal|needs_decision`.
Wave-ahead stops after N+1 and never freezes, dispatches, or plans N+2.

Reviewer reports `REVIEW_MILESTONE` with exact target, `outcome=pass|needs_fix|blocked|
needs_decision`, findings/evidence, and next. PASS plus a complete queued readiness packet may
continue without acknowledgment. Other outcomes stop by default; continuation after a
non-retract finding requires a pre-authorized independent/surface-disjoint next target. No
ready packet means idle, never Git polling. Queue exhaustion ends active work. Claim slot-free
parking only when the current runtime explicitly reports it; otherwise end the turn and
resume through same-identity `SendMessage`.
Report a confirmed major review finding immediately, before finishing the routine target;
deliver ordinary findings in the target milestone.
Every review milestone also names `base_sha`, `review_round`,
`review_kind=initial-full|refreshed-full|focused-closure`, `closes_findings`,
`failure_family`, and `test_model_revision_required`.

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
- **Idle-first dispatch** — for normal writer/reviewer work, publish one bounded ready batch,
  check task status once, and use `SendMessage` only to wake an idle consumer. A running
  consumer discovers routine additions at an item boundary. This enqueue-side inspection is
  event-driven, not polling; no ready work means idle without filler.
- On the agent's completion event, process its milestone/stop first, inspect the queue once,
  and wake it only if work remains and no unresolved stop exists. This completion-side check
  closes the running-to-idle race. Direct messages remain for wake-up, planner/hard-critical
  work, urgent correction, major finding, retract, and stop.
- The spool is at-least-once. If delivery succeeded but removal did not, reconcile item ID,
  Git, and milestone evidence instead of repeating work. When `SendMessage` is unavailable,
  the same-identity capability rule still applies; never respawn and call it continuation.

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
