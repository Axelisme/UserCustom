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

When the shape of that interface is itself in question — how deep the module is, where the seam belongs, what the interface should expose — use the `/codebase-design` skill for the vocabulary. It is the shared source of the module, interface, depth, seam, adapter, leverage and locality terms, and it is a reference to consult, not a session to run.

## Anti-patterns

- **Implementation-coupled** — mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological** — the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth — a known-good literal, a worked example, the spec.
- **Horizontal slicing** — writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead — one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.
- **Setup-heavy** — the test spends more lines reaching the behaviour than asserting it. The tell: the same construction or handshake prologue appears verbatim across many tests. Two separate failures hide here. The prologue is shared infrastructure nobody extracted — see [Test-suite hygiene](#test-suite-hygiene). And a long prologue is the interface telling you the seam is too deep or too wide: read it as design feedback first, test debt second.
- **Type-narrowing as assertion** — `assert isinstance(x, T)` (or its equivalent) written to satisfy the type checker rather than to verify behaviour, then repeated before every real assertion. The test body stops reading like a specification because most of its lines are not claims. Extract one narrowing helper that returns the narrowed value — `def expect_success(r) -> Success: ...` — so what is left in the test is only what the test claims.

## Test-suite hygiene

The loop only adds. Nothing in red-green ever removes a test, so a suite grows monotonically unless something else is made responsible for contraction. That responsibility is here.

- **Extract on the third repeat.** A construction or handshake sequence that has appeared in three tests becomes a fixture or a named helper before the fourth is written. This is the one carve-out from _Refactoring is not part of the loop_ below: that rule governs the code under test, which must not change shape while you are proving its behaviour. Test scaffolding is not under test, and deferring its extraction is what produces a suite nobody can afford to change.
- **A pin has an expiry.** Tests that freeze a contract, an inventory, or a parity baseline for a migration are written with their retirement condition stated in the test module's docstring, and are deleted by the ticket that removes what they pinned. A pin with no stated expiry is not a pin — it is a permanent test of a temporary arrangement, and it should not be admitted.
- **Ask what else fails.** Before adding a test, ask which existing tests would also fail if this behaviour broke. When a layered architecture tests one behaviour at every layer, keep the test closest to the seam that owns the behaviour and let the other layers cover their own.
- **Coverage is not the goal.** Past the point where a new test's most likely effect is to make a future refactor more expensive, an added test is a net cost. A suite that blocks the change it was written to protect has inverted its own purpose.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One cycle at a time.** One seam, one test, one minimal implementation per cycle.
- **Refactoring is not part of the loop.** Green ends the cycle. **If you are about to reshape code that already passes — rename, extract, move, deduplicate — stop: that is review work**, and it belongs to `/code-review`. Folding it into the cycle is the failure this rule exists to prevent — the change lands as another passing green, so nothing afterwards distinguishes the behaviour you proved from the structure you altered on the way past. This rule governs the code under test; extracting test scaffolding is carved out of it under [Test-suite hygiene](#test-suite-hygiene).
