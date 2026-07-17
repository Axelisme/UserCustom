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

Dispatch contents and the lean-boilerplate rule live in
[Delegation and review](references/delegation-and-review.md); stable boilerplate sits in the
profile and this binding, reached by pointer. Codex-specific: alongside the worker's
discrete-unit cadence, root measures its own wall-clock bound while waiting. Add the absolute
queue path/lease generation for a spool consumer. For a long direct contract, send the
immutable dispatch-packet absolute path and SHA-256 plus the immediate action; file existence
alone is inert.

## Milestones

The envelope schema, delivery rule, review-continuation rule, and liveness triggers live in
[Delegation and review](references/delegation-and-review.md). Per-commit progress gives root
real-time position without touching the assignee; **cross-identity pipelining bases only on
a seam-ready SHA** ([Git coordination](references/git-coordination.md)).

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
- A reviewer or other non-writing role that confirms a **retract-class finding ends the turn
  immediately** — with no mid-turn transport, the terminal envelope is the only way to
  deliver the stop root must issue.

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
- For an urgent invalidation prefer the interrupt capability, then continue the same
  identity with a corrective follow-up when the generation allows it (v2); on v1, close and
  respawn with a recovery delta — the worktree remains evidence.

## Runtime limits

Use observed tools for concurrency, nesting, parking, retirement, and role-switch capability.
Config files are not proof. A role switch reloads the new profile and cannot satisfy
different-identity review for work that identity implemented. If a required capability is
unavailable, return `needs_decision` rather than inventing an adapter.
