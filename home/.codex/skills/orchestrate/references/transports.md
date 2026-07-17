# File transports

Two closed file transports carry frozen work from root to an assignee; neither ever
carries outcomes, and file existence never authorizes execution.

## Immutable dispatch packets

The trigger is the SKILL machinery-triggers row. A packet carries only task-specific
content; standing orders, milestone schema, and tool recipes stay pointers. This is prompt
indirection, not a new control plane: the direct collaboration message grants authority and
names the packet; file existence does not authorize execution.

### Boundary

Packets are immutable, content-addressed task artifacts under:

```text
.agent_state/orchestrate/<task-id>/packets/<SHA-256>.md
```

Root publishes a packet and sends the assigned identity its absolute path, SHA-256, role,
explicit authority, and immediate stop condition. The consumer verifies the hash and basis
before acting. A stale, malformed, unreferenced, or hash-mismatched packet is inert.

Packets carry frozen input only. They never carry milestones, findings, current phase,
completion, collection authority, or landing state. Root may replace a contract only by
publishing new content and directly authorizing its new hash; published content is not edited.

### Format

The strict envelope is deliberately small:

```text
---
dispatch_packet_version: 1
packet_id: critical-slice-a
role: planner|writer|reviewer
basis_sha: <exact commit SHA>
hard_critical_axes: none|hardware|persistence|security|atomic-cutover[, ...]
---
```

The Markdown body requires five headings with concise task-specific content or `none`:

- `## Authority` — what the role may write/decide and what remains root/user-owned.
- `## Acceptance` — externally observable completion conditions and commands.
- `## Non-goals` — explicit exclusions that prevent scope growth.
- `## Write scope` — owned/excluded/shared-read-only path patterns or a scope manifest path.
- `## Stop conditions` — when to report instead of improvising.

Four more are optional; absence means none: `## Dependencies` (upstream SHAs this work
stacks from), `## Exact literals` (schema names, status codes, protocol values),
`## Oracles` (independent expected values and dangerous failure probes), `## Review policy`
(hard axes, named risks, cadence/waiting).

For a security hard-critical packet, `Oracles` should state the adversary capability and
containment level: public API, serialization, or in-process reachability. Name whether private
attributes, closures, bound owners, and nested object graphs are inside the oracle. This is a
conditional threat-model lens, not a universal checklist for unrelated work.

### Adapter and lifecycle

```text
orchestrate packet publish --root <repo> --task-id <task> --input <packet.md>
orchestrate packet inspect --root <repo> --task-id <task> --sha256 <hash>
```

`publish` validates the envelope, required headings, exact basis commit, UTF-8, Git ignore,
and release compatibility before an atomic content-addressed write. Republishing identical
content is idempotent. `inspect` is read-only and verifies filename/content identity; neither
command infers readiness, dispatch, or authority.

The packet may be removed after every referenced role has reached a terminal milestone and
root no longer needs it for recovery. Cleanup is ordinary task-artifact maintenance, never a
workflow transition. A cross-session handoff records the path/hash pointer in current state;
the next root revalidates before redispatch.

## Durable delivery spool

The spool is a narrow at-least-once transport for frozen, already-ready normal
writer/reviewer items. It is not a workflow database. Planner work, hard-critical successors,
and structure-gated work remain direct.

### Authority and layout

Root is the only producer; the bound lease holder is the single consumer. Files live under a
gitignored task-local generation:

```text
.agent_state/orchestrate/<task-id>/queues/<lease-id>/g<generation>/
  000010-<item-id>.md
```

The minimal immutable front matter is:

```text
---
queue_version: 1
item_id: slice-a
order: 10
role: writer|reviewer
lease_id: writer1
lease_generation: 1
basis_sha: <exact commit SHA>
---
```

The body is the ordinary role item or a reference to an immutable dispatch packet. The
adapter validates envelope/binding/integrity, never readiness. Queue presence means
delivery/removal is unreconciled and may include the crash-after-send duplicate window.
Queue absence is not completion evidence. A file creates no review, finding, collection,
phase, or landing authority.

### Adapter

```text
orchestrate queue publish --root <repo> --task-id <task> --role writer|reviewer \
  --lease-id <lease> --generation <n> --input <item.md> [--input ...]
orchestrate queue inspect --root <repo> --task-id <task> --role writer|reviewer \
  --lease-id <lease> --generation <n>
orchestrate queue remove --root <repo> --task-id <task> --role writer|reviewer \
  --lease-id <lease> --generation <n> --item-id <id> --order <n> \
  --expected-sha256 <hash> --terminal-delivery-confirmed
```

`publish` prevalidates the batch and atomically renames same-directory pending files without
overwrite. `inspect` is read-only and reports anomalies without cleanup. The consumer calls
`remove` only after its terminal milestone is delivered. Root may remove stale work only
after declaring stale reconciliation, proving the consumer ended, and recording a reason.
JSON reports caller declarations but never infers authority, delivery, or completion.

### Event-driven consumption

Root publishes a bounded ready batch, checks status once, and wakes an idle consumer. A
running consumer receives no routine prompt and checks at its next item boundary. When root
observes that identity's completion event, it processes milestone/stop first, inspects once,
and wakes only if work remains. The enqueue-side and completion-side checks close the lost
wakeup race; timers, daemons, and status polling remain unnecessary.

The consumer checks after inventory, after each item milestone, and before ending its turn.
It keeps the current file while working. Progress, malformed/stale input, a stop condition,
or delivery failure retains the file. Successful terminal delivery precedes exact-hash
removal and the next inspection.

No `active/` directory exists; work-in-progress stays at the same path. No `done/` directory
or receipt exists; milestones and Git remain evidence. Scripts do not dequeue, dispatch,
wake, or infer phase.

### Recovery and rebinding

- Before terminal delivery: retain and resume/reconcile.
- Delivery succeeded but removal failed: compare item ID, Git, and milestone evidence; do not
  repeat work blindly.
- New session: reconcile queue, Git, plan, findings, and authority before waking anything.
- Stale pending artifact: report and reconcile explicitly; never auto-delete.

One generation binds to at most one live consumer. Reuse it only after proving the old
consumer ended and identity continuity is valid. Otherwise increment generation, revalidate
and republish authorized items, and quarantine the old generation. Urgent correction,
confirmed major findings, retract, and stop stay direct; root never silently edits/removes a
file a live consumer may be using.
