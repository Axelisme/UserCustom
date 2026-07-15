---
orchestrate_compat: 60
---

# Durable delivery spool

Read this reference before creating or consuming a per-agent filesystem queue. Also read
`slice-queues.md`, `delegation-and-review.md`, and the current runtime binding. The spool is a
closed transport exception, not a workflow database: Git, agent context, and the plan remain
the three authoritative carriers.

## Scope and authority

The v60 spool carries only frozen, already-ready **normal writer/reviewer** role items. Root
is the only producer; one assigned lease holder is the single consumer. Planner work remains
one direct in-band item, and hard-critical or structure-gated successors remain direct
one-item dispatches after their required gate. Named risks are allowed only when their frozen
treatment still permits normal pipelining.

Queue presence means delivery/removal is still unreconciled; normally work has no delivered
terminal report, but the crash-after-send window may leave a completed item present. Queue
absence is not completion evidence. Git SHA, acceptance, review verdicts, and root-observed
milestones remain authoritative. A file creates no review debt, collection or phase authority.

The spool is **at-least-once**, not an exactly-once protocol. Root and the consumer reconcile
duplicates by `item_id`, Git, and milestone evidence rather than repeating work blindly.

## Location and immutable envelope

The task-local, gitignored layout is:

```text
.agent_state/orchestrate/<task-id>/queues/<lease-id>/g<generation>/
  000010-<item-id>.md
  000020-<item-id>.md
```

Use stable semantic lease IDs such as `writer1` or `reviewer1`, never runtime UUIDs. Every
item has strict UTF-8 front matter followed by the ordinary role packet:

```text
---
queue_version: 1
item_id: slice-a
order: 10
role: writer
lease_id: writer1
lease_generation: 1
basis_sha: <exact commit SHA>
hard_critical_axes: none
---

# slice-a
objective: ...
dependencies: already satisfied
scope: ...
acceptance: ...
named_review_risks: ...
stop_conditions: ...
```

Reviewer bodies contain the complete review-readiness packet. The adapter validates only the
minimal envelope, exact Git object, binding, uniqueness, and file integrity; it must never
infer readiness from prose or Git. Published files are immutable.

## Explicit adapter

Use the entrypoint aliases; do not hand-edit a published item:

```text
orchestrate queue publish --root <repo> --task-id <task> --role writer|reviewer \
  --lease-id <lease> --generation <n> --input <item.md> [--input <item.md> ...]
orchestrate queue inspect --root <repo> --task-id <task> --role writer|reviewer \
  --lease-id <lease> --generation <n>
orchestrate queue remove --root <repo> --task-id <task> --role writer|reviewer \
  --lease-id <lease> --generation <n> --item-id <id> --order <n> \
  --expected-sha256 <hash> --terminal-delivery-confirmed
# root-only stale cleanup after proving the old consumer ended:
orchestrate queue remove ... --expected-sha256 <hash> \
  --stale-reconciliation-confirmed --consumer-ended-confirmed --reason <why>
```

`publish` validates the whole supplied batch before writing, creates a same-directory
`.pending-*` file, fsyncs it, and atomically renames it. It never overwrites an existing ID or
order. `inspect` is read-only, including when the queue is absent, and reports stale pending
or unexpected artifacts without cleaning them. `remove` checks the exact envelope and hash;
the terminal-delivery flag is a consumer declaration, not proof. JSON results therefore say
that readiness, delivery, producer authority, and completion were not inferred.

The adapter has no runtime-agent credentials, so ownership is a standing-order invariant.
Root publishes; the named consumer normally removes. Root may remove only during explicit
stale reconciliation after proving that consumer ended and recording a reason. Any other
producer or consumer is a contract violation even if it can access the directory.

## Root publish and wake handshake

Root may append one or a bounded batch of already-ready items inside the frozen wave:

1. Publish all ready files through the adapter.
2. Check agent status once. If the bound identity is idle, use same-identity follow-up with a
   short wake instruction naming the absolute queue path and generation. If running, send no
   routine inbound message; it checks at its next item boundary.
3. When root later observes that identity's completion event, process its milestone or stop
   first, then inspect the queue once. If it is nonempty and no unresolved stop exists, wake
   the idle identity.

The enqueue-side check and completion-side check close the running-to-idle **lost wakeup**
race. They are event-driven inspections, not polling. Repeated status probes, shell sleep
loops, background daemons, or using `running` to infer phase remain forbidden.

## Consumer loop and deletion

The consumer receives its absolute queue path, role, lease ID, and `lease_generation` in the
spawn prompt and confirms them in its inventory milestone. It reads no other queue. It
inspects only after inventory, after each item boundary, and immediately before ending a
turn—never on a timer.

For the first ordered item:

1. Revalidate basis, scope, acceptance, readiness, and stop conditions before doing work.
2. Keep the file present while working. A progress checkpoint, stale basis, malformed packet,
   send failure, retract-class finding, or other unresolved stop retains the file and ends or
   pauses according to the role contract.
3. Deliver the existing terminal milestone to root. Only after delivery succeeds, call
   `queue remove` with the observed item hash. Then inspect the next item.

For a writer, `validated` or `review` is terminal for the item; `progress` is not. For a
reviewer, `pass|needs_fix|blocked|needs_decision` is terminal for that exact review target.
The root-observed milestone remains authoritative even though the consumer removes the file.

No `active/` directory exists: the current file stays in place. No `done/` directory or
receipt exists: terminal evidence remains in-band and in Git/plan where appropriate. The
adapter never dequeues automatically and never dispatches or wakes an agent.

## Crash, resume, and lease rebinding

- Crash before a terminal report: retain the file and resume or reconcile.
- Commit/verdict delivered but crash before removal: the file may be redelivered. Compare the
  item ID, expected Git SHA, milestone, and acceptance; resend only missing evidence, then
  remove it. Never rerun blindly.
- Send failure: retain the file and end the turn so root can recover delivery.
- Stale `.pending-*`: inspect and reconcile manually. No command silently removes it.
- New session: the queue does not auto-resume. Root reconciles it with Git, plan Current State,
  open findings, and current authority before waking anything. It may retract a stale item
  through the guarded reconciliation form only after proving the old consumer ended.

A queue generation binds to at most one live consumer. Reuse the same generation only after
proving the old consumer ended and the runtime preserves the intended identity. If proof is
unavailable, increment the generation, revalidate and republish remaining items into the new
path, and quarantine the old generation from consumption. A canonical agent task name should
include `<task>-<lease>-g<n>` so root can reconstruct the binding without relying solely on
compressed conversation context.

## Urgent control and prohibited expansion

Routine ready work uses the spool. Wake-up, confirmed major findings, urgent correction,
retract, and stop instructions remain direct collaboration messages; stop/invalidation may
interrupt first. The instruction explicitly says whether the current file is retained,
replaced after a safe boundary, or abandoned after root reconciliation. Root never silently
edits or removes a file that a live consumer may be executing.

This exception does not authorize worktree/branch registries, readiness solvers, finding or
review databases, phase markers, `done.json`, autonomous dequeue/dispatch/merge controllers,
background polling, or completion inference from absence. Git topology still comes only from
Git; decisions and stops still come from root; milestones still carry outcomes.
