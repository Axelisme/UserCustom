# Dev-flow — S0 design admission

S0 runs as a four-stage sequence — Need, Design, Slicing, Triage — in that order; each stage's
output is what the next stage designs, slices or triages. Read this before wayfinding, spec, or
ticket admission. Whether a task may skip the sequence is decided in
[SKILL.md](../SKILL.md#s0--design-admission), not here.

## Need

Before designing, record the smallest current observable user-visible need and its usage envelope,
and ground the design in that observable rather than in hypothetical robustness. The envelope is
agreed with the current user, not inferred: confirm the expected behavior, the usage scenarios and
which cases are out of envelope before designing. If they cannot be confirmed, stop and ask; do not
design past the gap.

Record the agreed envelope in the task record's `Envelope` section, or point that section at the
artifact that carries it (for example a frozen `spec.md`). This landing point is the evidence
downstream stages use to reject an out-of-envelope finding: S3 already requires `contract_basis`
against a closed blocking enum, but that gate only holds when the envelope has somewhere to point.

## Design

Generate the smallest complete end-to-end design that satisfies the need, starting from the need
itself rather than from what already exists. Carry forward an existing mechanism only when it is
the smallest way to satisfy the current need, not because it is already there.

Module depth is a deliverable of this stage, produced deliberately, not a side effect discovered
during implementation. For the vocabulary and technique for designing a deep Module, see
[`codebase-design`](../../codebase-design/SKILL.md); S0 does not restate it.

**An existing mechanism includes third-party packages.** Before designing any Module that provides
general-purpose infrastructure — schema derivation, validation, serialization, HTTP or WebSocket
transport, path resolution, file locking, retry, config parsing — check whether a package the
project already depends on, or one it could reasonably take on, already covers it. Record the check
and its outcome in the design: the packages considered, and for each rejection the current need it
cannot satisfy — a security boundary, a determinism requirement, a licence constraint. Already
being written in this repo is not such a reason, and neither is a preference for owning the code.
An unrecorded check counts as not performed, because there is nothing later stages can audit.

## Slicing

Deliver one usable tracer through the whole required path before deepening any one Module, then
advance slice by slice — never big-bang. Depth on a single Module waits until the tracer shows the
usable whole cannot be correct without it. A Slice that leaves this stage is admitted by S1.

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
