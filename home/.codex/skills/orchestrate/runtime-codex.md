---
orchestrate_compat: 72
---

# Orchestrate — Codex runtime binding

Session-injected collaboration tool definitions are authoritative. Codex ships **two
sub-agent generations** and either may be injected; identify the generation at session start
from the injected tool names, note the resolved capability matrix once in root context, and
use it consistently:

- **v1** (`multi_agent_v1__*`: `spawn_agent` with `agent_type`, `send_input`,
  `resume_agent`, `close_agent`, `wait_agent`; no `list_agents`): spawn **loads the named
  agent profile** — `~/.codex/config.toml` registration plus the profile toml's
  model/effort/instructions take effect.
- **v2** (`spawn_agent`, `send_message`, `followup_task`, `interrupt_agent`, `wait_agent`,
  `list_agents`): spawn does **not** select named profiles/models/sandboxes.

## Profile bootstrap and dispatch

When the generation loads profiles (v1), verify on the identity's first milestone that the
standing orders are in effect and record `profile_requested=<role>`,
`profile_effective=<role>`. When it does not (v2), instruct the identity on its first turn to
read `~/.codex/agents/<role>.toml` `developer_instructions` and confirm the file in its
inventory; if inaccessible, paste that block verbatim — do not summarize it from memory — and
record `profile_effective=generic_role_adapter`.

Every dispatch names objective, workdir/scope, basis, acceptance, authority, stop conditions,
and checkpoint budget. The budget has two parts: a **worker-observable cadence in discrete
units** (commits, items, acceptance sub-steps — never wall-clock, which a worker cannot see)
and a wall-clock bound root itself measures while waiting. Stable boilerplate — profile
standing orders, the milestone schema, tool recipes — lives in the profile and this binding;
the dispatch carries pointers to them plus only the contract, risk axes, acceptance, and
non-goals. Add the absolute queue path/lease generation for a spool consumer. For
a long direct contract, send the immutable dispatch-packet absolute path and SHA-256 plus the
immediate action; file existence alone is inert.

## Milestones

Send one semantic envelope to root at every observable boundary — **for a writer, after every
commit** (`state=progress`); after each item or when the declared cadence passes; and one
terminal envelope per item. Per-commit progress gives root real-time position without
touching the assignee; **cross-identity pipelining bases only on a SHA the writer declared
seam-ready**, never on every progress SHA:

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

Run `orchestrate milestone lint` when machine validation is useful. Delivery is
**at-least-once, deduplicated by `item_id`**: a milestone counts as delivered only when root
acknowledged it or its receipt is otherwise observable. Until then, repeat the full envelope
verbatim in the final response — a repeated envelope is cheap, a lost terminal envelope
(findings, verdicts) is the one thing this protocol must never drop. The runtime completion
event means only turn completion.

### v2 transport — real-time messages

Workers hold a mid-turn message tool: send each progress and terminal envelope through it as
the boundary happens, and send a confirmed major finding immediately. If a send fails, end
the turn with the envelope in the final response and retain any spool item.

### v1 transport — git-carried progress

Workers cannot message root mid-turn; the terminal envelope arrives only in the final
response. Do not pretend otherwise:

- **A writer's commit is its progress milestone.** Envelope semantics travel as commit
  trailers (`Item: <id>`, `Seam-Ready: true`); no separate outbox file duplicates them.
- Root harvests position by **event-driven read-only reads of lane branches** — when a user
  question or a scheduling decision needs it. This touches no identity and is not the
  forbidden fixed-interval status polling; the liveness cadence trigger is measured the same
  way (no new commit across the declared cadence within root's wall-clock bound).
- A reviewer or other non-writing role that confirms a **retract-class finding stops work and
  ends the turn immediately** — the terminal envelope is the immediate report. Auditing on
  past the finding delays the stop root must issue.

## Tool binding

| capability | v1 binding | v2 binding |
|---|---|---|
| spawn | `spawn_agent` (+`agent_type`, loads profile) | `spawn_agent` (generic identity) |
| milestone / pure notification | `send_input` (does not wake idle agents) | `send_message` (does not wake idle agents) |
| same-identity follow-up / wake | `resume_agent` | `followup_task` |
| interrupt / stop | `close_agent` (terminal — respawn continues via dispatch delta) | `interrupt_agent` (identity survives) |
| event wait | `wait_agent` | `wait_agent` |
| liveness/status | — (degraded) | `list_agents` |

Call collaboration tools directly, never through shell execution. Spawn independent agents
before waiting. Repeated event-driven waits after timeouts are valid; shell sleep loops,
tight Git/status probes, and phase inference from `running` are not.

Degraded modes when a capability is missing: no status/list tool (v1) — rely on completion
events plus the declared cadence; no true interrupt (v1's `close_agent` is terminal) — treat
the identity as non-interruptible, dispatch smaller bounded turns, deliver corrections at the
next item boundary, and accept that urgent invalidation costs the identity; no mid-turn
message transport — the final-response envelope is the milestone of record and root harvests
it from the completion payload. Note the degraded mode next to the resolved matrix instead of
improvising per event.

## Flow control

- Ready direct work wakes an idle identity with the wake capability (`resume_agent` /
  `followup_task`). Routine work for a running spool consumer is published without a prompt;
  it discovers it at the item boundary.
- On a consumer completion event, process milestone/stop first, inspect its spool once, then
  wake only if work remains and no unresolved stop exists.
- Major findings, retract, correction, and stop are direct. Prefer the interrupt capability
  for urgent invalidation, then continue the same identity with a corrective follow-up when
  the generation allows it (v2); on v1, close and respawn with a recovery delta.
- Pass may continue to a complete pre-authorized review target. Other reviewer outcomes stop
  unless independent continuation was frozen. Hard-critical dependent work always waits.

## Stalled work

Liveness recovery has exactly three triggers: the runtime reports the agent `errored` or a
model/capacity failure; the runtime declares its lease expired; or the dispatch-declared
checkpoint budget passes with no milestone. Everything else is healthy: `running` with no
tool/filesystem activity is model reasoning, a `wait_agent` timeout is normal silence to wait
on again, and fixed 30/60-second status polling of a sub-agent is forbidden. There is no
universal timer. Updating the user never requires touching the assignee — report from the
last milestone, read-only Git, and the frozen dispatch.

When a trigger fires:

1. read available runtime activity/waiting metadata first, without guessing from `ps`/Git;
2. send one liveness ping asking for progress, blocker, or the nearest coherent checkpoint;
3. if no response, interrupt and resume the same identity with a recovery delta; the worktree
   remains evidence. Spawn a replacement only when identity continuity is unavailable or the
   domain/independence requirement changed.

## Runtime limits

Use observed tools for concurrency, nesting, parking, retirement, and role-switch capability.
Config files are not proof. A role switch reloads the new profile and cannot satisfy
different-identity review for work that identity implemented. If a required capability is
unavailable, return `needs_decision` rather than inventing an adapter.
