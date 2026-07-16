---
orchestrate_compat: 68
---

# Critical review

Use this branch when failure can cross security/capability/authentication, hardware or process
ownership, persistence/migration, or an atomic cutover. Ordinary HTTP composition, codec
wiring, client adapters, tests, typing, formatting, documentation, and mechanical refactors stay
normal unless their actual failure crosses one of those boundaries.

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
SHA ready for review.

## Try to disprove it

A **different-identity** reviewer audits source and the exact immutable SHA from a detached
checkout. It challenges the writer's oracle with a **hostile reproducer**, including negative
paths and dangerous intermediate states. Green writer tests are input evidence, not the review
verdict.

Report confirmed major boundary invalidation immediately so root can hold dependent work.
Other findings stay in the checkpoint verdict with severity, path, observed behavior, evidence,
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
