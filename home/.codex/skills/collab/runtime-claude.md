# Collab: Claude runtime

Claude's binding delta, and nothing else. [Collab](SKILL.md) owns policy; the Pi role profiles own
receiver contracts and Results. Claude dispatches Collab roles only through the herdr subagent MCP,
which runs each child as a Pi subagent. Claude-native agents remain available for work outside Collab
roles, never as a `collab-implementer` or `collab-acceptor` substitute.

## Routing

- Before dispatch, read [Capability check](#capability-check), then [Dispatch](#dispatch) and
  [Waiting](#waiting).
- When a notification arrives: [Results and decisions](#results-and-decisions).
- When interrupted work needs inspection, steering, or recovery: [Run control](#run-control).
- For native Git collection or landing, apply [Integrate](references/integration.md#integrate) and
  [Land and clean up](references/integration.md#land-and-clean-up). The Pi `collab_*` Git tools are
  not registered in Claude.
- Specialized operations not documented here require a decision before use.

## Capability check

At dispatch, the current Claude tool inventory is the capability source of truth. Require the MCP
tools `spawn_subagent`, `wait_subagent_events`, `query_subagent`, and `control_subagent` (exposed as
`mcp__subagents__*`; load deferred schemas before the first call). Then require
`collab-implementer` or `collab-acceptor` in `query_subagent({ action: "roles" })`. Those roles are the
Pi profiles under `~/.pi/agent/herdr-subagents/profiles/`. If a required tool or role is missing,
report `BLOCKED` naming the missing item. Do not substitute a Claude-native agent, shell process, or
cached tool catalogue.

The profile's declared tools and Result contract are authoritative. Optional planning, monitoring,
artifact, scheduling, or messaging tools add no Collab lifecycle operation.

## Dispatch

Read Collab [Prepare](references/execution.md#prepare),
[Results and continuity](references/execution.md#results-and-continuity), and
[Correct and decide](references/review.md#correct-and-decide) for the portable loop.

`spawn_subagent({ cwd, role, dispatch })` launches one fresh child and returns its `subagent_id`.
`cwd` is the exact prepared checkout: the lane worktree for `collab-implementer`, and the frozen
review checkout for `collab-acceptor`. `dispatch` is the whole bounded brief. Each correction,
rereview, and replacement is its own spawn; no call resumes a child with a new brief. Pi
[Dispatch](runtime-pi.md#dispatch) describes the profile registry and the parameters the schema
rejects. Its Herdr-pane availability rule does not apply here, because the MCP server owns pane placement.

A child can ask its parent a question, so brief it to request a decision through `contact_parent`
and stay live rather than ending `BLOCKED` with a question.

## Waiting

Children report only through `wait_subagent_events`. After each spawn, and after handling each
notification batch, call it with `ack` listing every `notification_id` received in the previous call.
Unacknowledged notifications are delivered again. Only the main conversation may call it; a
Claude-native subagent that calls it blocks. Do not poll `status` or block on a child instead.

Branch on the returned `state`:

- A backgrounded call (Claude reports that the call moved to the background) is armed. End the turn;
  its completion starts a new turn.
- `notifications`: handle each one under [Results and decisions](#results-and-decisions), then wait
  again with their ids in `ack`.
- `idle`: no child is running and nothing is pending. Wait again only after a spawn or resume.
- `poll`: Claude background tasks are disabled, so nothing is armed and no turn will wake you. Continue
  independent work and call again at the next natural point. With nothing else to do, tell the user
  which children are still running, and check again when the user next responds.
- `superseded`: a newer wait replaced this call and consumed nothing. Do nothing; the newer call
  stands.
- `session_changed`: notifications addressed to the previous Claude session stay pending until that
  session resumes. Recover each child dispatched from it by exact-id `result` (see below).

While a child runs, continue independent work. On each wake, reread the exact ticket or batch review
record named by the dispatch, as in Pi [Post-launch](runtime-pi.md#post-launch).

## Results and decisions

Outcome semantics follow Pi [Results and decisions](runtime-pi.md#results-and-decisions): terminal
`COMPLETED`, `BLOCKED`, or manager-derived `FAILED`, with `FAILED` resumable. Recovery uses
exact-id `query_subagent({ action: "result", subagent_id })`. The MCP differs in delivery:

- Each notification carries a `notification_id` and one of three kinds. A `terminal` notification is the
  child's result. A `decision` notification is a question awaiting a reply. A `recovery` notification
  reports that the child is alive in `provider-wait` for its model provider. It needs no reply and is
  neither a result nor a failure: acknowledge it and keep waiting.
- Answer a decision with `control_subagent({ action: "reply", subagent_id, answer })`, where
  `subagent_id` is the id named in the notification. A prose response or `steer` does not unblock the
  child, and a steer is rejected while its decision is pending. An unanswered decision gets one
  reminder after five minutes.
- Record each decision and its answer in the owning ticket or batch review record before the next wait.

## Run control

Use Pi [Run control](runtime-pi.md#run-control) unchanged: `query_subagent` `status` and `inspect`
for reads, and `control_subagent` `steer`, `resume`, and `terminate` for control. After resuming a
child, return to [Waiting](#waiting).
