---
orchestrate_compat: 71
---

# Durable delivery spool

The spool is a narrow at-least-once transport for frozen, already-ready normal
writer/reviewer items. It is not a workflow database. Planner work, hard-critical successors,
and structure-gated work remain direct.

## Authority and layout

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
hard_critical_axes: none
---
```

The body is the ordinary role item or a reference to an immutable dispatch packet. The
adapter validates envelope/binding/integrity, never readiness. Queue presence means
delivery/removal is unreconciled and may include the crash-after-send duplicate window.
Queue absence is not completion evidence. A file creates no review, finding, collection,
phase, or landing authority.

## Adapter

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

## Event-driven consumption

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

## Recovery and rebinding

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
