---
orchestrate_compat: 78
---

# Wave pipeline

The trigger is the SKILL pipeline-shapes row. Idle capacity is cheaper than blocking the
main writer with handoffs, repeated context loading, and duplicate gates.

## Freeze the wave

Root freezes one natural wave, commonly a few coherent items and sometimes a one-item tail.
Each item is self-contained: objective, exact base, write authority, acceptance/oracle,
dependencies, discretion, and any root-named review barrier. Contract or same-file authority
is serialized. Planner keeps the whole known dependency chain stocked with ready proposals
while N runs; root alone freezes and releases them, wave by wave.

Prefer one writer for a coherent vertical slice. Split at independently verifiable ownership
or dependency seams, not at each parser, field, callback, or mechanical edit. A slice may
contain several progress observations without creating several review checkpoints.

## Keep work flowing

- A **non-blocking milestone** reports observed progress/evidence; an authorized writer
  continues immediately. The runtime/profile owns its transport and schema.
- A completed micro-step is not itself a reason to stop, commit, switch identity, or ask root.
- Root observes delivered events; contact rules are the root contact discipline in
  [Delegation and review](delegation-and-review.md).

## Writer, reviewer, and root

A writer retains context across the whole slice and stops only at its declared barrier or a
genuine decision boundary; for normal work the writer is the default reviewer.

An independent reviewer exists only where root named a risk at freeze and consumes complete
exact-state targets at the cumulative cadence in
[Delegation and review](delegation-and-review.md). It may continue to an already-ready
independent target after pass; idle review time never justifies blocking the writer or
implementing against an unstable interface.

Root harvests milestones, assigns findings, and batch-collects with one narrative update per
batch. Localized finding fixes get a **focused re-review**; one full review closes a
named-risk surface. Only integration runs the repo/risk-required **broader gate**, whose
evidence binds to the final tree.

## Wave close

Reconcile Git and the durable narrative, retain open/deferred findings, and collapse every
closed decision into a one-line ADR/evidence pointer — task_plan carries active items and
pointers only. Record lightweight counts (findings per review, review rounds, wait) and tune
**review amplification** with them: two consecutive reviews yielding only minor findings drop
the next wave's default depth one level (focused → root spot-check → none); any major finding
restores named-risk review immediately.

Normal queue mechanics live in [Durable delivery spool](durable-delivery-spool.md). A boundary
that needs independent adversarial proof leaves this branch for [Critical review](critical-review.md).
