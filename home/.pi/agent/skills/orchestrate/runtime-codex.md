# Orchestrate — Codex runtime binding

Session-injected collaboration tool definitions are authoritative.

## Pipeline capability and named fallback

Codex remains runtime-neutral: this binding does not implement or emulate a durable `pipeline`
queue. `wave-implementer` and `wave-reviewer` retain an explicit pipeline-capable profile
contract only as cross-runtime eligibility wording; they have no machine opt-in and claim no
Codex runtime capability. Codex roots use the ordinary async path. Root records a concrete
non-attach reason (`pipeline capability unavailable in Codex runtime`) and uses the named ordinary
one-deep fallback: dispatch one ready item, harvest its completion, then dispatch the next.
This is the only one-deep policy; it is an explicit no-durable-runtime fallback, not a global
review-lag cap. `integration-reviewer` remains a fresh one-shot role.

The fallback preserves root ownership of scope, queue placement, cross-lane blocked work,
ordinary finding accumulation, and cost-growing invariant holds. Runtime neutrality means
Codex must not claim pipeline persistence, milestone scheduling, reviewer frontier semantics,
or Git/review/finding interpretation. Codex ships **two
sub-agent generations** and either may be injected; identify the generation at session start
from the injected tool names, note the resolved capability matrix once in root context, and
use it consistently (re-derive it from the injected tool names after a context compaction —
the matrix lives nowhere durable):

- **v1** (`multi_agent_v1__*`: `spawn_agent` with `agent_type`, `send_input`,
  `resume_agent`, `close_agent`, `wait_agent`; no `list_agents`): spawn **loads the named
  agent profile** — `~/.codex/config.toml` registration plus the profile toml's
  model/effort/instructions take effect.
- **v2** (`spawn_agent`, `send_message`, `followup_task`, `interrupt_agent`, `wait_agent`,
  `list_agents`): spawn does **not** select named profiles/models/sandboxes.

## Profile bootstrap and dispatch

When the generation loads profiles (v1), verify on the identity's first milestone that the
standing orders are in effect. When it does not (v2), instruct the identity on its first
turn to read `~/.codex/agents/<role>.toml` `developer_instructions` and confirm the file in
its inventory; if inaccessible, paste that block verbatim — do not summarize it from memory.
Alongside the worker's discrete-unit cadence, root measures its own wall-clock bound while
waiting. A long direct contract travels as a plain file whose absolute path the dispatch
names, with the immediate action inline.

## Milestones

The envelope schema, delivery rule, and liveness triggers live in
[coordination](references/coordination.md).

- **v2 transport**: workers hold a mid-turn message tool — send each progress and terminal
  envelope through it at the boundary, and a confirmed major finding immediately. If a send
  fails, end the turn with the envelope in the final response.
- **v1 transport**: workers cannot message root mid-turn. **A writer's commit is its
  progress milestone** — envelope semantics travel as commit trailers (`Item: <id>`,
  `Seam-Ready: true`). Root harvests position by event-driven read-only reads of lane
  branches when a decision needs it; this touches no identity and is not polling. A
  non-writing role that confirms a retract-class finding ends the turn immediately — the
  terminal envelope is the only way to deliver the stop root must issue.

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
events plus the declared cadence; no true interrupt (v1's `close_agent` is terminal) —
dispatch smaller bounded turns, deliver corrections at the next item boundary, and accept
that urgent invalidation costs the identity (the worktree remains evidence); no mid-turn
transport — the final-response envelope is the milestone of record. Note the degraded mode
next to the resolved matrix instead of improvising per event.

## Runtime limits

Use observed tools for concurrency, nesting, parking, retirement, and role-switch
capability. Config files are not proof. A role switch reloads the new profile and cannot
satisfy different-identity review for work that identity implemented. If a required
capability is unavailable, return `needs_decision` rather than inventing an adapter.
