---
name: tdd
description: Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests.
---

# Test-Driven Development

TDD is the red → green loop. This skill is the reference that makes that loop produce tests worth keeping: what a good test is, where tests go, the anti-patterns, and the rules of the loop. Every section applies on every cycle — consult them before and during the loop, not after.

When exploring the codebase, read the module README / domain glossary (`docs/glossary.md` or `CONTEXT.md`, whichever the repo uses) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching.

**Scope**: test-first pays off at logic seams — state machines, schemas, pure computation, wire contracts. At GUI or hardware edges where behavior is only observable through rendering or instruments, follow the repo's documented test conventions instead of forcing the loop.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification — "user can checkout with valid cart" tells you exactly what capability exists — and survives refactors because it doesn't care about internal structure.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Seams — where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

**Test only at pre-agreed seams.** Before writing any test, write down the seams under test and confirm them. In an interactive session, confirm with the user ("What's the public interface, and which seams should we test?"). Inside an orchestrated task, the seams come from the frozen spec/contract — to-spec already confirmed them with the user; do not re-open them mid-implementation. A missing seam there is a contract gap to report (`Scope changes requested`), not a question to improvise. No test is written at an unconfirmed seam — agreeing seams up front is how testing effort lands on critical paths instead of every edge case.

## Ownership in orchestrated work

Root or the contract planner freezes the seams, acceptance examples, independent oracles,
and dangerous failure modes. The implementer owns the permanent executable tests and works
vertically through test → implementation cycles; do not create a parallel test-writer lane
that collides on the same interface, fixture, or files. A reviewer contributes an independent
adversarial matrix or temporary reproducer. When review finds missing behavior, the finding
returns to the implementer, who first adds the failing permanent regression test and then the
fix.

A TDD cycle is smaller than an orchestration slice. One slice may contain several cycles and
reports their compact red/green evidence only at its clean checkpoint, not after every test.
Green behavior evidence never overrides an orchestrator's structural stop condition or
mandatory critical review.

## Anti-patterns

- **Implementation-coupled** — mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological** — the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth — a known-good literal, a worked example, the spec.
- **Horizontal slicing** — writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead — one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One cycle at a time.** One seam, one test, one minimal implementation per cycle.
- **Local cleanup after green.** The implementer may refactor implementation details while
  the same interface behavior stays green. A change to the seam, ownership, contract, or
  lifecycle is not local cleanup: stop and return it for design/review rather than hiding it
  inside the TDD cycle.
