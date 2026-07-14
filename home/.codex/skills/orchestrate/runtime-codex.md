# Orchestrate — Codex runtime binding

This file is the hand-written companion for the current Codex collaboration runtime. It maps
the `orchestrate` skill's abstract capabilities to the tools actually exposed in the session.
Tool availability and schemas are defined by the session-injected tool definitions; do not
assume a named-agent selector, model selector, or custom sandbox selector is exposed just
because `~/.codex/config.toml` or `~/.codex/agents/*.toml` (or a repo's own `.codex/` config)
exist.

## Profiles and dispatch

The skill's profiles are work contracts, not necessarily selectable runtime profiles.
`~/.codex/agents/*.toml` and the `[agents]` sections in `~/.codex/config.toml` serve Codex
hosts that support named agents, but the collaboration tool's `spawn_agent` currently has no
`profile`, `agent_name`, `model`, `reasoning_effort`, or `sandbox_mode` parameter.

When root dispatches:

- **This runtime does not load named-agent profiles.** At the **first** spawn of a role
  identity, root pastes that role's standing orders verbatim into `message` — read the
  `developer_instructions` block from `~/.codex/agents/<role>.toml` and inline it; do not
  summarize it from memory (summaries drift from the file). Follow-ups to the same identity
  never repeat it; they carry only the delta. With domain leases this makes the profile a
  one-time cost per agent, not per slice.
- Write the profile name, task boundary, file scope, delivery format, and constraints
  explicitly into `message`.
- Note `profile_requested=<profile>`, `profile_effective=generic_role_adapter` in the report;
  do not claim a TOML profile took effect.
- If the task hard-requires a specific model, sandbox, or named-agent identity that the
  current tools cannot guarantee, return `needs_decision`.

For a pipelined slice queue, this compact prompt shape is a useful Codex-oriented starting
point. Omit fields that add no value for a small or exploratory task:

```text
profile_requested=<profile>
profile_effective=generic_role_adapter
lease + write scope: <domain ownership and the only files this writer may change>
ordered slices:
  1. <slice; acceptance; targeted tests>
  2. <slice; acceptance; targeted tests>
stop conditions: <when to checkpoint and return needs_decision>
milestone delivery: send_message(slice, sha, tests, blast_radius, next), then continue
```

The labels make runtime adaptation visible; they are not a mandatory report schema. Because
this Codex collaboration runtime does not load the requested project profile, a multi-slice
dispatch must also include the runtime-effective milestone contract itself; naming
`profile_requested=implementer` is insufficient:

```text
milestone delivery:
- after every completed slice, before starting the next, call collaboration.send_message
  to /root
- payload: MILESTONE slice=<id> sha=<exact SHA or uncommitted>
  tests=<commands/results> blast_radius=<none/localized/surface-changing/contract-level>
  next=<next slice or final>
- continue without waiting for acknowledgement unless a stop condition applies
- never run more than one unreviewed slice ahead
- if send_message is unavailable or fails, end the turn at this boundary; root will use
  followup_task to continue the same identity
```

Use the actual root canonical task name if it differs from `/root`. This explicit block is the
behavioral authority for Codex; `~/.codex/agents/*.toml` remains useful documentation and may be
effective on other Codex hosts, but it is not a substitute here.

## Tool binding

| skill capability | collaboration tool | exact semantics |
|---|---|---|
| spawn | `spawn_agent` | create an agent with `task_name`, `message`; `fork_turns` accepts `all`, `none`, or a positive-integer string. Returns the agent id and canonical task name. |
| message | `send_message` | deliver a message to an existing agent; does **not** trigger a new turn on an idle agent. |
| follow-up / same-identity continuation | `followup_task` | send a follow-up to an existing agent; triggers a new turn when idle, delivered at a message boundary when running. Preserves the same agent identity. |
| interrupt | `interrupt_agent` | abort the agent's current turn; the agent can still receive later messages or follow-ups. |
| wait / event | `wait_agent` | wait for a live agent mailbox update; timeout is not a failure. Returns a summary of which agents updated, not necessarily the full payload. |
| status | `list_agents` | list live agents in the current root thread tree; filter with `path_prefix`. |
| worktree isolation | plain `git worktree` | per SKILL.md; no separate tooling. |

Collaboration tools must be called directly, never wrapped in `functions.exec`. Do not build
sleep/poll loops; advance on agent events or a single `wait_agent` result.

## Flow control

- Spawn independent agents back-to-back before waiting, so they actually run in parallel;
  then advance on events, never on polling.
- **Warm-up = early spawn of read-only roles.** While the contract is still being discussed,
  an investigator can already build its source map — speculative read-only work costs nothing
  to discard. Writers are never spawned speculatively; they start only after the contract is
  frozen.
- **Slice long work vertically.** Deliver in reviewable slices with an event per finished
  slice, so root integrates early and steers — never wait for one giant black-box delivery.
- **Stalls: interrupt, then correct — don't respawn.** Inspect via `wait_agent`/mailbox
  summaries, stop with `interrupt_agent`, then continue the *same* agent via `followup_task`
  carrying the corrective delta. Its loaded context is an asset; respawning a fresh identity
  throws it away (and, per the skill, needs an articulable reason).
- **Pipelined slices** — a recommended option for frozen contracts; the pattern and its
  guardrails (run-ahead, append-only commits, blast-radius protocol) live in SKILL.md
  "Dispatch". Runtime mechanics here: the implementer pushes each milestone via
  `send_message` with the useful subset of `slice / sha / tests / blast_radius / next` and
  normally continues without an ack. `running` proves only liveness, not the current phase;
  root waits for agent events and does not build a polling loop. If an expected boundary arrives
  only as a final response, repeat the milestone contract and degrade subsequent dispatch to one
  slice per turn — the completion event plus an immediate `followup_task` keeps the same identity.
  Root may choose that simpler rhythm whenever review or contract uncertainty should steer the
  next dispatch.

## Runtime limits and repo config

- The session-injected collaboration runtime determines actual concurrency, nesting, and tool
  availability; the current tool instructions are authoritative.
- `~/.codex/config.toml [agents]` `max_threads` / `max_depth` only describe Codex hosts that
  read that config; they cannot be generalized to the Codex Desktop collaboration
  runtime as verified limits.
- Each `[mcp_servers.<name>]` `default_tools_approval_mode` is MCP server tool approval, not
  sub-agent approval.
- The model, reasoning effort, and sandbox in `~/.codex/agents/*.toml` are named-agent settings;
  they are effective capabilities only when the host actually selects that named agent.
