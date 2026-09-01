# Dev-flow — S0 design admission

S0 runs as a four-stage sequence — Need, Design, Slicing, Triage — in that order; each stage's
output is what the next stage designs, slices or triages. Read the stage you are starting, before
spec or ticket admission. Whether a task may skip the sequence is decided in
[SKILL.md](../SKILL.md#the-lifecycle), not here.

## Carrying an item to a `drafted` ticket

A stage that cannot determine an item does not invent one. It **carries** the item: opens a
`drafted` ticket holding what is known now, and re-enters for that one item at the ticket's
graduation, against the code as it stands then. Each stage's completion criterion below admits the
carry-over as an outcome beside the answers it already accepts.

The licence is uncertainty, not preference. Carry an item when determining it now would mean
guessing at the state of code that earlier Slices will change. A seam whose placement the design
already shows is decided here and written; a seam whose shape depends on what three Slices from now
leave behind is carried. An item that could be determined and was carried anyway is deferred work,
not an admitted carry-over.

A carried item stays unwritten. A `drafted` ticket carries its `Outcome` and the user-visible
sentence it delivers or partly delivers, and nothing it would have to guess — a dependency edge, a
Module write scope, a production-path validation and a seam's Interface content are all carryable. A
ticket whose uncertainty has not resolved when its batch runs stays `drafted` for the next one; that
is the fog not having lifted, not a failed graduation.

Graduation runs as a **batch over the frontier**: every `drafted` ticket whose dependencies have
closed graduates in one pass, before any of them is dispatched, so one reading of the current tree
serves them all. The batch may exceed the antichain; the dispatch drawn from it may not. `../SKILL.md`
owns where that batch sits in the lifecycle; the preconditions a ticket satisfies to leave `drafted`
are owned by
[ticket-seam-contract](ticket-seam-contract.md#publication-and-change-control).

## Need

Before designing, record the smallest current user-visible need, its expected result, and its usage
envelope. Ground the design in that need rather than hypothetical robustness. The envelope is agreed
with the current user, not inferred: confirm expected behavior, usage scenarios, and out-of-envelope
cases before designing. If they cannot be confirmed, stop and ask; do not design past the gap.

For behavior, Interface, data-format, or external-effect changes, identify applicable validation
through the production path. Evidence may be an automated test, instrument, manual reproduction, or
captured artifact; it exercises the shipped entrypoint rather than a stand-in that can pass while the
production path stays broken. Purely editorial or organizational work may have no production path.

Record the agreed envelope — the task's out-of-scope boundary: what belongs to this task at all, as
against a ticket's own scope, which its Outcome and Acceptance already carry — into one frozen file
under the task's `spec/` directory. Point the task record's `Envelope` section and every ticket's
envelope field at that file; neither record holds the boundary text itself. This exact boundary lets
downstream Implement and Acceptance distinguish current work from out-of-envelope findings.

Need is complete when the smallest need, expected result, agreed envelope, and applicable
production-path validation have one exact landing point.

## Design

Generate the smallest complete end-to-end design that satisfies the need, starting from the need
itself rather than from what already exists. Carry forward an existing mechanism only when it is
the smallest way to satisfy the current need, not because it is already there.

Module depth is a deliverable of this stage, produced deliberately, not a side effect discovered
during Implement. For the vocabulary and technique for designing a deep Module, see
[`codebase-design`](../../codebase-design/SKILL.md); S0 does not restate it.

**A seam this stage decides lands at the module, not only in this task's `spec/`.** The task record
is archived when the task ends, while the next module that couples to the seam has to read it long
after — and a caller that has to reconstruct the contract from the implementation is how a
downstream writer ends up inventing its own boundary. So every real seam in the design — real in
`codebase-design`'s sense, something actually varying across it — carries a written declaration of
its Interface at the module it belongs to, in whatever form this repository already documents for
module-level material (a module README, a header comment); follow the repository's own conventions
here rather than imposing a layout.

Declare only what a signature cannot carry: invariants, ordering constraints, error modes, lifecycle
and ownership, required configuration, performance characteristics. Restating names, types, or
parameter lists adds the half that goes stale and that an outline already shows. The declaration
says enough when a caller can couple to the module without reading its implementation. Writing it is
part of the Slice that creates or moves the seam, never a separate documentation pass and never a
retroactive sweep across modules this task does not touch.

**An existing mechanism includes third-party packages.** Before designing any Module that provides
general-purpose infrastructure — schema derivation, validation, serialization, HTTP or WebSocket
transport, path resolution, file locking, retry, config parsing — check whether a package the
project already depends on, or one it could reasonably take on, already covers it. Record the check
and its outcome in the design: the packages considered, and for each rejection the current need it
cannot satisfy — a security boundary, a determinism requirement, a licence constraint. Already
being written in this repo is not such a reason, and neither is a preference for owning the code.
An unrecorded check counts as not performed, because there is nothing later stages can audit.

Design is complete when the end-to-end design identifies the Modules, Interfaces, seams, production
reachability, each applicable infrastructure package's adoption or need-grounded rejection, and the
module each real seam's Interface declaration is owed at — each of them determined here, or carried
to a `drafted` ticket that Design re-enters at its graduation.

## Slicing

Deliver one usable tracer through the whole required path before deepening any one Module, then
advance slice by slice — never big-bang. Depth on a single Module waits until the tracer shows the
usable whole cannot be correct without it. A Slice that leaves this stage is ready for bounded
Implement; collab owns writer-placement guidance for that work.

**Usable**, of a Slice or of the whole a tracer proves, means one sentence in the user's terms says
what they do and what they see. Write that sentence before the Slice — it is the cheapest place to
find out that a Slice delivers nothing anyone can look at.

A Slice too small to carry a whole sentence names the one it partly delivers, and a later Slice
completes it. What that rules out is the Slice naming no sentence at all — a layer, a Module, or a
phase of construction is scaffolding for a sentence nobody has written yet. A named sentence no
Slice ever completes is the same defect, found later and more expensively.

**Concurrency is decided once per dispatch, so the downstream steps stay decision-free.** The
candidates are the tickets that are `pending`, because only those are dispatchable; a set may run
together when it forms an antichain — no member reachable from another. **Reachability is computed
over the whole ticket DAG, `drafted` tickets included as opaque blocking nodes.** An edge is an edge
whatever state its endpoint is in, and a graph restricted to `pending` tickets makes A and B look
mutually unreachable when A reaches B only through a D that is still `drafted`.

Declare each ticket's write scope as the Modules the Design stage produced, in
[`codebase-design`](../../codebase-design/SKILL.md#glossary)'s sense of the term, rather than as paths,
functions, or the lines a diff touches: two tickets that change different functions of one Module
share that Module's scope. Overlapping Module scope between two tickets with no edge between them is
a missing edge: add the edge or split the tickets. Grant concurrency where assembled evidence would
surface an interaction between the candidate Modules; an increment with thin coverage stays serial.

An append to a shared wiring surface — a registry, export list, permissions array, index — lies
outside Module scope and counts as no intersection. An edit that reorders entries, restructures the
surface, or rewrites an existing entry is Module scope. Judge that on the shape of the actual diff:
a regenerated lockfile grows by one logical entry and rewrites the file.

A Slice that partly delivers a sentence names the ticket completing it, so the sentence has one
owner rather than a copy on each partial ticket. That completer may itself be `drafted`.

Slicing is complete when every admitted implementation requirement belongs to a bounded Slice that
states its own sentence or names the one it partly delivers together with the ticket completing it,
and each Slice's dependency edge, Module write scope and applicable production-path validation are
explicit or carried to a `drafted` ticket that Slicing re-enters at its graduation. Concurrency
disposition is no longer settled here: it is decided per dispatch, above.

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

A requirement first observed after S0 — which just-in-time ticket creation makes ordinary — is
triaged when it arrives, at the graduation of the ticket that surfaces it, by these same two
questions.

Triage is complete when every observed requirement is in the current Contract, has a safe simple
handling, has passed Candidate-backlog admission, or is carried to a `drafted` ticket that Triage
re-enters at its graduation, and no speculative case was admitted.
