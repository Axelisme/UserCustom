---
name: tdd
description: Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests.
---

# Test-Driven Development

TDD is the red → green loop. This skill is the reference that makes that loop produce tests worth keeping: what a good test is, where tests go, the anti-patterns, and the rules of the loop. Every section applies on every cycle — consult them before and during the loop, not after.

When exploring the codebase, read the module README / domain glossary (`docs/glossary.md` or `CONTEXT.md`, whichever the repo uses) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching.

**Scope — where the loop applies.** Test-first earns its cost at logic seams: state machines, schemas, pure computation, wire contracts. A GUI or hardware edge is a boundary, not one of those seams — behaviour there is observable only through rendering or an instrument, and building that observation costs more than the bug it would have caught. **If the seam under test sits at one of those edges, the loop does not apply**: follow the repo's documented test conventions instead, and name the convention you followed. Declining the loop there is a scoping call, not a shortcut — forcing it is the worse failure, because the tests it produces still read as coverage while nobody keeps them.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification — "user can checkout with valid cart" tells you exactly what capability exists — and survives refactors because it doesn't care about internal structure.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Seams — where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

**Test only at pre-agreed seams.** Before writing any test, write down the seams under test and confirm them with the user. No test is written at an unconfirmed seam. You can't test everything — agreeing the seams up front is how testing effort lands on the critical paths and complex logic instead of every edge case.

Ask: "What's the public interface, and which seams should we test?"

## Anti-patterns

- **Implementation-coupled** — mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological** — the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth — a known-good literal, a worked example, the spec.
- **Horizontal slicing** — writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead — one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One cycle at a time.** One seam, one test, one minimal implementation per cycle.
- **Refactoring is not part of the loop.** Green ends the cycle. **If you are about to reshape code that already passes — rename, extract, move, deduplicate — stop: that is review work**, and it belongs to `/code-review`. Folding it into the cycle is the failure this rule exists to prevent — the change lands as another passing green, so nothing afterwards distinguishes the behaviour you proved from the structure you altered on the way past.
