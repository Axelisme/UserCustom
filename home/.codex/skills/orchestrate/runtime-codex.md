---
orchestrate_compat: 60
---

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

- **This runtime does not load named-agent profiles.** Default delivery: at the first spawn
  of a role identity, the first line of `message` instructs the agent to read its standing
  orders from `~/.codex/agents/<role>.toml` (the `developer_instructions` block) and follow
  them, and to confirm **in its inventory milestone** which profile file it loaded. This
  keeps the profile text out of root's context and always delivers the file's current
  version; the inventory confirmation turns "hope it read it" into a checked handshake.
- Fallback: if the sandbox blocks reading `~/.codex/agents` (or the agent reports it
  cannot), root pastes the `developer_instructions` block verbatim into `message` — read
  from the file, never summarized from memory. Either way, follow-ups to the same identity
  never repeat it; with domain leases the cost is once per agent, not per slice.
- Write the profile name, task boundary, file scope, delivery format, and constraints
  explicitly into `message`. A v60 normal writer/reviewer spawn also names the absolute queue path,
  role, lease ID, `lease_generation`, and canonical task name. Its inventory milestone must
  echo that binding before consumption. Provide the exact `orchestrate queue` adapter command;
  agents never hand-edit published files. Planner and hard-critical work remain direct.
- Note `profile_requested=<profile>`, `profile_effective=generic_role_adapter` in the report;
  do not claim a TOML profile took effect.
- If the task hard-requires a specific model, sandbox, or named-agent identity that the
  current tools cannot guarantee, return `needs_decision`.
- Bootstrap identity with the entrypoint's `orchestrate identity` pseudo command when
  different identity or a warm reviewer matters. Supply the runtime-observed agent id,
  effective adapter, profile path, writer id, and park capability; the command hashes the
  profile/standing orders but never claims the runtime loaded them.

For any pipelined role, use the same compact contract. Omit fields that add no value for a
small or exploratory task:

```text
profile_requested=<profile>
profile_effective=generic_role_adapter
lease: <role/domain; writer scope or reviewer immutable scope>
wave + basis: <wave id; exact SHA/ADR/contract assumptions>
ordered items or spool binding:
  <direct items, or absolute queue path + role + lease_id + lease_generation>
continue_without_ack: <qualifying outcome and dependency rule>
turn queue: <recommended frozen batch; allowed mid-turn control exceptions>
stop conditions: <when to checkpoint and return needs_decision>
milestone delivery: send_message(<role milestone and next>), then continue when authorized
```

The labels make runtime adaptation visible; they are not a mandatory report schema. Because
this Codex collaboration runtime does not load the requested project profile, a multi-slice
dispatch must also include the runtime-effective milestone contract itself; naming
`profile_requested=<role>` is insufficient. The prompt must include the runtime-effective
contract for that role.

Writer milestones use:

```text
milestone delivery:
- after every completed slice or required stop, before starting any next slice, call
  collaboration.send_message to /root
- common payload: MILESTONE delivery_phase=milestone slice=<id>
  checkpoint_kind=<progress|validated|review> next=<current/next slice or final>
- progress adds: completion=<done/remaining> stop_reason=<none|reason>
  finding_class=<none/mechanically-propagatable/design-invalidating/dangerous-intermediate/scope-collision>
  diagnostics=<optional provisional commands/results|none>; omit SHA/validation
  diagnostics are non-gating, non-review evidence and never authorize run-ahead
- validated/review add: sha=<exact clean SHA>
  validation=<tdd-green(red=<test/reason>;green=<same test + regression>)|targeted-acceptance(<commands/results>)>
  remaining_uncertainty=<behavior-only|structural|hard-critical|anomaly>
  finding_class=<none/mechanically-propagatable/design-invalidating/dangerous-intermediate/scope-collision>
- checkpoint_kind=review freezes that SHA and creates review debt; validated does not
- continue through the pre-authorized normal wave without acknowledgement unless a stop
  condition or review-before-next-slice marker applies; validated (or normal review) plus
  behavior-only uncertainty authorizes run-ahead; progress never authorizes the next slice;
  hold for structural, hard-critical, or anomaly uncertainty; stop at the wave boundary
- if send_message is unavailable or fails, end the turn at this boundary; root will use
  followup_task to continue the same identity; retain the current spool file
- for a spool item, successful terminal milestone delivery precedes exact-hash `queue remove`;
  progress never removes it. Inspect after inventory, each item boundary, and pre-final only
- pre-final checklist: `delivery_phase=milestone` was sent before the final response, payload
  enum/required fields are valid, and root was the recipient. A single-item turn is not
  exempt; the final response never substitutes for the milestone
```

Planner milestones use:

```text
PLAN_MILESTONE wave=<N+1> planning_mode=<contract-resolution|wave-ahead>
outcome=<proposal|needs_decision> basis=<SHA/ADRs> invalidators=<conditions>
items=<target=3-5;tail=1-2 slices with dependencies/acceptance/risk/review policy> next=<idle|stop>
- wave-ahead proposes one wave only; it never freezes/dispatches or advances to N+2
- notify root, then end the turn and retain the planner lease
```

Reviewer milestones use:

```text
REVIEW_MILESTONE delivery_phase=milestone base=<SHA> target=<exact SHA>
outcome=<pass|needs_fix|blocked|needs_decision>
findings=<severity/path/behavior/evidence/propagation|none>
evidence=<source audit/adversarial probes/thin commands> next=<target id|idle|stop>
review_round=<1..N> review_kind=<initial-full|refreshed-full|focused-closure>
closes_findings=<ids|[]> failure_family=<family|none>
test_model_revision_required=<true|false>
- pass plus a complete queued readiness packet continues without acknowledgment
- other outcomes stop by default; independent-nonblocking continuation must be pre-authorized
- confirmed major findings notify root immediately before the routine target verdict
- no ready packet means idle; never poll Git
- queue exhaustion ends the active turn; this runtime does not expose a proven slot-free park,
  so report `park_capability=unknown` and resume by same-identity `followup_task`
- if send_message is unavailable or fails, end the turn; root resumes by followup_task
- for a spool target, send the terminal verdict before exact-hash `queue remove`, then inspect
  the next item; retain malformed, stale, or undelivered items
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
| worktree isolation | plain `git worktree` or the entrypoint's explicit aliases | per `references/git-coordination.md`; aliases add guards but no workflow state. |

Collaboration tools must be called directly, never wrapped in `functions.exec`. Repeated
event-driven `wait_agent` calls after a timeout are allowed for long tasks, with a user update
when ongoing work would otherwise be silent. Do not build shell sleep loops, tight status/Git
probe loops, or use liveness as phase evidence. Do not infer an agent's phase from `running`.

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
- **Idle-first dispatch** — for normal writer/reviewer work, publish one bounded ready batch,
  call `list_agents` once, and use `followup_task` only when that consumer is idle. A running
  consumer sees routine additions at its item boundary. No ready work means idle, never
  filler. This enqueue-side check is event-driven, not polling.
- On the identity's completion event, root processes its milestone/stop first, inspects the
  queue once, and wakes it only when work remains and no unresolved stop exists. This
  completion-side check closes the running-to-idle race. `running` still proves only liveness.
- Direct `followup_task` work is reserved for wake-up, planner/hard-critical dispatch, urgent
  correction, major review finding, retract, or stop. For invalidation, prefer
  `interrupt_agent` and then corrective follow-up. `send_message` remains pure notification
  or context that must not start a turn.
- `running` proves only liveness, not the current phase; root uses repeated event-driven waits
  and does not build a polling loop. If expected milestones arrive only as final responses,
  repeat the runtime contract and degrade that role to one item per turn. The final event plus
  immediate `followup_task` preserves identity. Use this simpler rhythm whenever contract or
  review uncertainty needs steering.
- Root may run `orchestrate packet lint --role writer|reviewer --input <json|->` against a
  supplied milestone before accepting its evidence. The linter is stateless and never repairs
  or advances a queue. It validates the payload declaration only and **does not prove
  delivery ordering**; root still observes that the milestone arrived before the final event.
- The spool is at-least-once: delivery followed by a crash before removal may expose the same
  item again. Reconcile item ID, Git, and milestone evidence; never repeat it blindly.

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
