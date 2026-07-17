---
orchestrate_compat: 79
---

# Critical review

Use this branch only when a checkpoint shows **both** features, named explicitly at freeze:

1. **A dangerous state a follow-up commit cannot cheaply undo.** Before landing, repo work is
   reversible by default; qualifying failures are external or cascading — verification
   touches real hardware/process/device state, a capability or security exposure is live
   while agents run, a persistence/migration step acts on real data, or a wrong seam would
   invalidate the reviewed evidence of several dependent lanes at once.
2. **Named dependent work about to stack on the invariant** before a cumulative review would
   close it. If root cannot name the specific slice being held, the barrier protects nothing.

Touching a critical-sounding domain — lifecycle, ownership, persistence code,
security-adjacent plumbing — never qualifies by itself, and accumulated findings that land as
batched follow-up fixes are normally cheaper than serializing the pipeline. A checkpoint
failing either feature is at most a **named review risk**: the same independent review depth,
no barrier, work runs ahead. Ordinary HTTP composition, codec wiring, client adapters, tests,
typing, formatting, documentation, and mechanical refactors stay normal. At task close,
recalibrate: a critical checkpoint whose findings would all have landed as follow-up fixes
proved the review's value, not the barrier's.

**Carve the critical core out of its normal shell.** Critical identity attaches to the
boundary surface itself — the admission gate, the capability mint, the cutover switch — and is
not inherited by the plumbing that feeds it. Freeze the core as its own small slice behind this
barrier and let the shell flow as normal verticals; a batch is never critical wholesale.

## Freeze the barrier

Freeze one coherent critical outcome, its exact base, dangerous intermediate states, hostile
oracles, and the dependent work held behind the barrier. For security, name the adversary and
containment level—public API, serialization, or in-process reachability—and whether private
attributes, closures, bound owners, or nested object graphs are observable.

The writer owns permanent regression tests and targeted acceptance. Progress inside the slice
is non-blocking; the writer stops when the coherent critical checkpoint is an exact immutable
SHA ready for review. The barrier holds only the dependent work: while the review runs, the
writer runs ahead on an independent slice rather than idling.

## Try to disprove it

A **different-identity** reviewer audits source and the exact immutable SHA from a detached
checkout. It challenges the writer's oracle with a **hostile reproducer**, including negative
paths and dangerous intermediate states. Green writer tests are input evidence, not the review
verdict.

Report confirmed major boundary invalidation immediately so root can hold dependent work;
the report/stop split in [Delegation and review](delegation-and-review.md) applies. Other
findings stay in the checkpoint verdict with severity, path, observed behavior, evidence,
and propagation shape. Root owns deferral.

## Close findings economically

The finding returns to the **original implementer**. Closure returns to the original reviewer
and is finding-focused by default. Use a **refreshed full review** only when the fix changes an
authority boundary, threat/test model, persistence behavior, ownership/lifecycle, or enough of
the coherent slice that prior review evidence no longer applies.

After pass, root may release dependent work. Collection still requires reviewed/integration
tree identity; if critical content differs, review the integration SHA. At final integration,
run one coherent full review and the repo/risk-required broader gate rather than replaying every
intermediate review.
