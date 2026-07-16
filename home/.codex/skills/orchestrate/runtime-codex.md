---
orchestrate_compat: 63
---

# Orchestrate — Codex runtime binding

Session-injected collaboration tool definitions are authoritative. Current `spawn_agent`
does not select named profiles/models/sandboxes even when config files describe them.

## Profile bootstrap and dispatch

On an identity's first turn, instruct it to read
`~/.codex/agents/<role>.toml` `developer_instructions` and confirm the file in its inventory.
If inaccessible, paste that block verbatim; do not summarize it from memory. Record
`profile_requested=<role>` and `profile_effective=generic_role_adapter`.

Every dispatch names objective, workdir/scope, basis, acceptance, authority, stop conditions,
and checkpoint budget. Add the absolute queue path/lease generation for a spool consumer. For
a long direct contract, send the immutable dispatch-packet absolute path and SHA-256 plus the
immediate action; file existence alone is inert.

## One milestone

After each item—or when its checkpoint budget is exceeded—send exactly one semantic envelope
to root before continuing or ending:

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

Use `send_message` for this event. Run `orchestrate milestone lint` when machine validation is
useful. The final response does not repeat the envelope; one short confirmation is enough.
The runtime completion event means only turn completion. If milestone delivery fails, end the
turn and retain any spool item.

## Tool binding

| capability | tool |
|---|---|
| spawn | `spawn_agent` |
| milestone / pure notification | `send_message` (does not wake idle agents) |
| same-identity follow-up / wake | `followup_task` |
| interrupt | `interrupt_agent` |
| event wait | `wait_agent` |
| liveness/status | `list_agents` |

Call collaboration tools directly, never through shell execution. Spawn independent agents
before waiting. Repeated event-driven waits after timeouts are valid; shell sleep loops,
tight Git/status probes, and phase inference from `running` are not.

## Flow control

- Ready direct work wakes an idle identity with `followup_task`. Routine work for a running
  spool consumer is published without a prompt; it discovers it at the item boundary.
- On a consumer completion event, process milestone/stop first, inspect its spool once, then
  wake only if work remains and no unresolved stop exists.
- Major findings, retract, correction, and stop are direct. Prefer `interrupt_agent` for
  urgent invalidation, then resume the same identity with a corrective follow-up.
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
