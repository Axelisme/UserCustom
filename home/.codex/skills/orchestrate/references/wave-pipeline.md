---
orchestrate_compat: 61
---

# Wave pipeline

Use a wave only when two or more ready slices are genuinely independent. Optimize
**critical-path lead time**, not agent utilization: idle capacity is cheaper than blocking the
main writer with handoffs, repeated context loading, and duplicate gates.

## Freeze the wave

Root freezes one natural wave, commonly a few coherent items and sometimes a one-item tail.
Each item is self-contained: objective, exact base, write authority, acceptance/oracle,
dependencies, discretion, and any real review barrier. Contract or same-file authority is
serialized. Planner may advise Wave N+1 while N runs; root alone freezes it, and planning stops
one wave ahead.

Prefer one writer for a coherent vertical slice. Split at independently verifiable ownership
or dependency seams, not at each parser, field, callback, or mechanical edit. A slice may
contain several progress observations without creating several review checkpoints.

## Keep work flowing

- A **non-blocking milestone** reports observed progress/evidence; an authorized writer
  continues immediately. The runtime/profile owns its transport and schema.
- A checkpoint blocks only for a declared dependency or critical review barrier. A completed
  micro-step is not itself a reason to stop, commit, switch identity, or ask root.
- Dispatch a frozen bounded turn rather than drip-feeding a running identity. Routine additions
  use the spool; major finding, correction, retract, or stop may interrupt directly.
- Root observes delivered events. Short absence of tool/fs activity is model reasoning, not
  evidence of a stall; the runtime binding owns liveness recovery.

## Writer, reviewer, and root

Writer runs targeted tests and affected type/lint checks during development, retains context
across the whole slice, and stops only at its declared barrier or genuine decision boundary.

Reviewer consumes complete exact-state targets. For normal work, review one coherent slice or
a cumulative/selected batch rather than every small commit. It may continue to an already-ready
independent target after pass. Idle review time may prepare a stable spec audit, hostile oracle,
or source inventory; it does not justify blocking the writer or implementing against an
unstable interface.

Root harvests milestones, assigns findings, and serially collects accepted work. Localized
finding fixes get a **focused re-review**; one full slice review closes the coherent surface.
Only integration runs the repo/risk-required **broader gate**, whose evidence binds to the final
tree. Any later code change invalidates the affected evidence.

## Wave close

Reconcile Git and the durable narrative, retain open/deferred findings, and collapse closed
details into evidence pointers. Record lightweight counts only when they help tune slice size,
handoffs, review amplification, or wait; omit timings the runtime did not observe.

Normal queue mechanics live in [Durable delivery spool](durable-delivery-spool.md). A boundary
that needs independent adversarial proof leaves this branch for [Critical review](critical-review.md).
