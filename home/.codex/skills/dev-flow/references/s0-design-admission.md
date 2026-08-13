# Dev-flow — S0 design admission

S0 runs as a four-stage sequence — Need, Design, Slicing, Triage — in that order; each stage's
output is what the next stage designs, slices or triages. Read this before wayfinding, spec, or
ticket admission. Whether a task may skip the sequence is decided in
[SKILL.md](../SKILL.md#s0--design-admission), not here.

## Need

Before designing, record the smallest current user-visible need, its expected result, and its usage
envelope. Ground the design in that need rather than hypothetical robustness. The envelope is agreed
with the current user, not inferred: confirm expected behavior, usage scenarios, and out-of-envelope
cases before designing. If they cannot be confirmed, stop and ask; do not design past the gap.

For behavior, Interface, data-format, or external-effect changes, identify applicable validation
through the production path. Evidence may be an automated test, instrument, manual reproduction, or
captured artifact; it exercises the shipped entrypoint rather than a stand-in that can pass while the
production path stays broken. Purely editorial or organizational work may have no production path.

Record the agreed envelope in the task record's `Envelope` section, or point that section at the
artifact that carries it (for example a frozen `spec.md`). This exact boundary lets downstream
Implement and Acceptance distinguish current work from out-of-envelope findings.

Need is complete when the smallest need, expected result, agreed envelope, and applicable
production-path validation have one exact landing point.

## Design

Generate the smallest complete end-to-end design that satisfies the need, starting from the need
itself rather than from what already exists. Carry forward an existing mechanism only when it is
the smallest way to satisfy the current need, not because it is already there.

Module depth is a deliverable of this stage, produced deliberately, not a side effect discovered
during Implement. For the vocabulary and technique for designing a deep Module, see
[`codebase-design`](../../codebase-design/SKILL.md); S0 does not restate it.

**An existing mechanism includes third-party packages.** Before designing any Module that provides
general-purpose infrastructure — schema derivation, validation, serialization, HTTP or WebSocket
transport, path resolution, file locking, retry, config parsing — check whether a package the
project already depends on, or one it could reasonably take on, already covers it. Record the check
and its outcome in the design: the packages considered, and for each rejection the current need it
cannot satisfy — a security boundary, a determinism requirement, a licence constraint. Already
being written in this repo is not such a reason, and neither is a preference for owning the code.
An unrecorded check counts as not performed, because there is nothing later stages can audit.

Design is complete when the end-to-end design identifies the Modules, Interfaces, seams, production
reachability, and each applicable infrastructure package's adoption or need-grounded rejection.

## Slicing

Deliver one usable tracer through the whole required path before deepening any one Module, then
advance slice by slice — never big-bang. Depth on a single Module waits until the tracer shows the
usable whole cannot be correct without it. A Slice that leaves this stage is ready for bounded
Implement; collab owns writer-placement guidance for that work.

**Concurrency is decided here, once, so the downstream steps stay decision-free.** Read the
candidates off the ticket DAG: a set may run together when it forms an antichain — no member
reachable from another. Declare each ticket's write scope as the Modules the Design stage produced,
in [`codebase-design`](../../codebase-design/SKILL.md)'s sense of the term, rather than as paths,
functions, or the lines a diff touches: two tickets that change different functions of one Module
share that Module's scope. Overlapping Module scope between two tickets with no edge between them is
a missing edge: add the edge or split the tickets. Grant concurrency where assembled evidence would
surface an interaction between the candidate Modules; an increment with thin coverage stays serial.

An append to a shared wiring surface — a registry, export list, permissions array, index — lies
outside Module scope and counts as no intersection. An edit that reorders entries, restructures the
surface, or rewrites an existing entry is Module scope. Judge that on the shape of the actual diff:
a regenerated lockfile grows by one logical entry and rewrites the file.

Slicing is complete when every admitted implementation requirement belongs to a bounded usable Slice,
and each Slice's dependency edge, Module write scope, applicable production-path validation, and
concurrency disposition are explicit.

## Triage

Both questions below are asked about something that has actually been observed. A case that exists
only as speculation is not triaged at all: it is neither built nor backlogged.

For each admitted requirement, ask two questions:

1. Is it common in the expected usage scenarios?
2. Did the current user ask for it?

When the answer to both is no, give it the simplest correct handling in the current Contract — a
clear refusal, a fast-fail or a report all qualify — and send the more elaborate treatment to the
backlog instead of building it now.

Guardrail: the simplest handling must itself be safe — it must preserve current data and current
authority. When no safe simple handling exists, the case is not "rare, therefore simple"; it is a
current correctness gap and stays in the current Contract.

Candidate-backlog's hard gates are the sole authority for backlog eligibility, required fields and
lifecycle; S0 does not restate them. An edge returns from backlog only through explicit planning,
after frequency, impact or a real resumed scenario makes it part of a current minimum need.

Triage is complete when every observed requirement is in the current Contract, has a safe simple
handling, or has passed Candidate-backlog admission, and no speculative case was admitted.
