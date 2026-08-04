---
name: dev-flow
description: Durable task record for work that must survive compaction and handoff. Use when starting multi-session work, resuming or archiving an existing task record, asking what a task's current state is, or when another skill needs the shared plan-directory record. Not for single-session edits that need no durable record.
skill_version: 5
---

# Dev Flow

Use this skill for work that needs durable orientation across sessions.

## Jurisdiction

Dev-flow owns the durable task lifecycle, the record's structure, the conditional route through
wayfinder, to-spec and to-tickets, and the S0 design admission below — the stages that run before
there is anything to dispatch. Candidate-backlog owns backlog eligibility. **Orchestrate owns
[S1–S5](../orchestrate/references/admission.md)** along with Git and runtime coordination: once
work is a Slice in a lane, every check that admits it is decided from Git artifacts orchestrate
holds, and it ships and versions with the machinery that enforces it.

When this skill's work reaches one of those, **point at it and stop there**. A restatement is a
second copy that drifts from the original, and the reader cannot tell which copy is current — so
the obligation runs both ways. When evolving the workflow itself, read the
[design principles](references/design-principles.md) for the altitude and evidence behind these
checks.

## S0 — Design admission: Need → Design → Slicing → Triage

S0 governs admission of new design work. It runs as a four-stage sequence — Need, Design, Slicing,
Triage — in that order; each stage's output is what the next stage designs, slices or triages.
`S0` remains the cross-reference anchor for the whole sequence. Read it before wayfinding, spec, or
ticket admission.

Purely decision-only tasks (no implementation output) and small corrections completed within
Root's single context do not need the full sequence. They still owe the Envelope slot in the task
record a value — see Need below — it is never left blank.

### Need

Before designing, record the smallest current observable user-visible need and its usage envelope,
and ground the design in that observable rather than in hypothetical robustness. The envelope is
agreed with the current user, not inferred: confirm the expected behavior, the usage scenarios and
which cases are out of envelope before designing. If they cannot be confirmed, stop and ask; do not
design past the gap.

Record the agreed envelope in the task record's `Envelope` section, or point that section at the
artifact that carries it (for example a frozen `spec.md`). This landing point is the evidence
downstream stages use to reject an out-of-envelope finding: S3 already requires `contract_basis`
against a closed blocking enum, but that gate only holds when the envelope has somewhere to point.

### Design

Generate the smallest complete end-to-end design that satisfies the need, starting from the need
itself rather than from what already exists. Carry forward an existing mechanism only when it is
the smallest way to satisfy the current need, not because it is already there.

Module depth is a deliverable of this stage, produced deliberately, not a side effect discovered
during implementation. For the vocabulary and technique for designing a deep Module, see
[`codebase-design`](../codebase-design/SKILL.md); S0 does not restate it.

### Slicing

Deliver one usable tracer through the whole required path before deepening any one Module, then
advance slice by slice — never big-bang. Depth on a single Module waits until the tracer shows the
usable whole cannot be correct without it. A Slice that leaves this stage is admitted by S1.

### Triage

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

## Custody

The record holds no authority of its own. It is **custody** of the user's — what they froze and what
they granted, and nothing else. Six things follow.

**A held item is the original.** A standing order is the user's own sentence, **quoted verbatim**,
stamped with when it was issued and when it lapses. A paraphrase is the agent's understanding
wearing the user's name. List new entries in the same reply, so the user can disown them on the
spot.

**An order is what the user granted, not what they asked for.** Most instructions are spent by
being carried out — "go ahead", "collect that", "start the next ticket" — and the record of them is
the work itself. Admit a sentence only if it still binds the decision after the requested act is
done; ask it plainly: *doing this, does the sentence go away?* A one-off instruction that enters the
list never leaves it on its own, and arrives wearing the same authority as a real grant. One
sentence often carries both — "collect this, you don't need to ask me for collect" — so admit it on
its binding clause and hold the whole sentence; **never quote half of one**.

**A quote must resolve.** Most grants are ratifications — "agreed", "option A", "do it your way" —
whose content lives in the proposal they answer. Hold them by address, never by retelling: write the
proposal down as durable text *before* asking, then keep the quote plus a pointer to it. Text is
frozen at the moment of assent; later changes are amendments the user ratifies in turn, never edits
in place — otherwise the agent widens what was agreed while the quote still reads as consent. Where
an antecedent was never written down, reconstruct it under an explicit `reconstructed` label, so the
reader can see whose sentence it is.

**Only the user retires an order.** An entry leaves the in-force list when its own stated condition
fires, when a later user message revokes or replaces it, or when the task is archived — never
because it looks obsolete. Retirement is a move, not a deletion: the entry keeps its wording and
gains the date and reason it lapsed. Overlapping orders are never merged into one sentence; the most
recent wins on the points it addresses, and every in-force order still binds everywhere else. When
it is unclear whether a new order narrows an old one or replaces it, ask.

**An empty slot says the evidence never arrived.** `Envelope` carries the frozen minimum need and
usage envelope, or points at the artifact that owns it; a task with no implementation output records
`Not applicable — <reason>`. It is never blank, because a blank Envelope is the visible evidence
that the need was never frozen, and every later out-of-envelope refusal cites it.

**A custodian cannot issue what it holds.** Current user messages remain the only mutation
authority. A standing order records what the user granted; it never manufactures authority the user
did not give. When an entry activates another skill's contract, name that skill and point at it —
its grants and exclusions stay there.

## One task record

- Durable work uses the workflow-neutral task record under `.agent_state/plans/<task-id>/`, driven
  by `scripts/plan.py` **inside this skill's own directory** — the same directory as this file, not
  a `scripts/` directory in the repository being worked on.
- Its public Interface is exactly `create | archive | locate | refresh`. `archive --undo` moves an
  archived record back; `locate` mutates nothing and orients the reader. Neither name is inherited:
  `locate` replaced a `resume` that no longer resumed anything, so a stale caller fails loudly
  instead of silently receiving a different answer.
- `INDEX.md` holds `Goal`, `Current`, `Next`, `Envelope`, and `Standing orders`.
- `Current` says where the conditional route stopped or why a stage was skipped, when useful.
- `tickets/*.md` hold ordinary generic work; their container is a three-field header, a
  `Resolve by` action, and `Outcome`/`Current`.
- Decision-making work keeps its decisions in the producer-owned `decisions.md` artifact, not in
  the generic container.

**Never create a second ticket store.** No phase file, no progress file, no acceptance queue that
**replaces** `.agent_state/plans/<task-id>/`. The failure is two stores competing to be believed:
when they disagree, the copy that wins is whichever one the next agent reads first, and nothing
marks which was authoritative.

A live progress display is not that. The record is the authority and the durable one; a session's
own task list is a projection of the moment, useful while the session lasts and gone with it. They
coexist. What must not happen is a ticket taking its state *from* the projection — ticket status is
the closed enum in the header, decided in the record.

Wayfinder, to-spec and to-tickets are independent producers that publish wherever the repo tracks
work; they know nothing about this record. When their output becomes the durable work, **dev-flow
transcribes it** into these ordinary generic tickets and keeps a pointer back to the producer's
artifact — the producers are never asked to write here. Unfinished implementation and repair are
generic ticket work too.

## Reading the record

- The frontier, the largest ticket ID, and the complete dependency graph are the ticket headers in
  `tickets/*.md`.
- Superseded decisions are the `Status` cells in `decisions.md`.
- The complete record inventory is `locate`, which lists the directory when asked and stores
  nothing.

`refresh` validates ticket status, reports a record that has gone stale, and names frozen state
written into `Current` or `Next`. It does not validate the dependency graph or the frontier these
queries reveal — a record can still contradict them, and the reader carries the cost of noticing.

## Keeping INDEX.md small

`INDEX.md` is reread whole on every re-orientation, so a long one is a cost paid forever and a dense one is
skimmed exactly where it matters. It holds what changes the next action.

The size problem is downstream of a state problem. **Frozen state has no home here at all** — a SHA,
a tree, a ReviewGate id, a node count. Not because it is long, but because it is the one kind of
content that goes wrong silently: it stays readable and confident long after it stops being true,
and the next session acts on it. `refresh` names such tokens in `Current` and `Next`; move them to
the artifact of the gate that produced them rather than rewording them.

Everything else already has a home too, so compaction is a **move**, never a rewrite:

- The scope of a standing order — what it authorizes, what it excludes, what it supersedes — is the
  agent's own conclusion, so it belongs in `decisions.md` where a later decision can supersede it.
  The entry keeps the quote, the pointer and the lapse condition, and nothing else.
- Lapsed orders move to `standing-orders-lapsed.md`, whole and verbatim.
- Evidence that a past gate passed — counts, SHAs, baselines — belongs to that gate's artifact. The
  record keeps the frontier, not the receipts.
- The artifact inventory is `locate` and `artifacts/README.md`. A hand-kept list beside them is a
  second copy that drifts.

`refresh` measures the authored region against a budget and reports it; it never refuses on size,
because the one moment the record must open is the moment a compacted session needs it. Compact at
the next accepted frontier rather than mid-slice, and list what moved in the same reply. Summarizing
to hit the budget is the failure this rule exists to prevent: a record that is short because custody
was paraphrased away is worse than one that is long.

## Conditional route

Wayfinder, to-spec, and to-tickets are independently usable producers; dev-flow transcribes what they
produce and never drives them from inside their own backend. **Wayfinder is user-invoked** — while
the route to a durable destination is not yet clear, say so and ask the user to run `/wayfinder`;
do not attempt to start it on their behalf. Use to-spec before a landed change, unless it inherits a frozen contract (mark it inherited, refined,
or contradicted) or the delivery itself is text. Use to-tickets when work will be dispatched through
an admission gate; Root completing work in one context still records a generic ticket but does not
need to-tickets. A handoff is a decision-authority transfer event, not a route stage, and the record
continues to own implementation work after it.

**Orchestrate derives no task narrative.** It consumes task and ticket IDs and owns Git and runtime
coordination; it never infers what a task is about, what stage it reached, or why. An orchestrate
command that appears to know the plan is reporting something a human wrote down — treat narrative
read out of Git state as absent, not as a second opinion.

`archive` is a neutral directory move and never implies completion, but use it only after
implementation completes or the task is explicitly abandoned; a handoff alone does not qualify.
Final close-out follows orchestrate's S5. After compaction, run `locate` and read what it names — it derives the
record's health, its frontier and where to look, all at read time. Then read this skill and the
`Envelope` and `Standing orders` it points you at: those carry what the user froze and granted, and
are the first things a compacted session loses.
