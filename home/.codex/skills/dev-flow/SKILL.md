---
name: dev-flow
description: Durable task record for work that must survive compaction and handoff. Use when starting multi-session work, resuming or archiving an existing task record, asking what a task's current state is, or when another skill needs the shared plan-directory record. Not for single-session edits that need no durable record.
skill_version: 6
---

# Dev Flow

## Orienting

After compaction, or in any session that did not create this task, run `locate` and read what it
names — it derives the record's health, its frontier and where to look, all at read time. Then read
the Custody section below and the `Envelope` and `Standing orders` it points you at: those carry
what the user froze and granted, and are the first things a compacted session loses.

That is enough to say what the task is and what is next. Everything below is for acting on it.

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

S0 governs admission of new design work, before there is anything to dispatch. It runs as a
four-stage sequence — Need, Design, Slicing, Triage — in that order; each stage's output is what the
next stage designs, slices or triages. Read
[references/s0-design-admission.md](references/s0-design-admission.md) for the four stages before
starting any of them. `S0` remains the cross-reference anchor for the whole sequence.

Purely decision-only tasks (no implementation output) and small corrections completed within Root's
single context do not need the full sequence. They still owe the `Envelope` slot a value; it is
never left blank.

## Custody

The record holds no authority of its own. It is **custody** of the user's — what they froze and what
they granted, and nothing else. What follows.

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
  archived record back; `locate` mutates nothing and orients the reader.
- `INDEX.md` holds `Goal`, `Current`, `Next`, `Envelope`, and `Standing orders`.
- `Current` says where the conditional route stopped or why a stage was skipped, when useful.
- `tickets/*.md` hold ordinary generic work; their container is a three-field header, a
  `Resolve by` action, and `Outcome`/`Current`.
- Decision-making work keeps its decisions in the producer-owned `decisions.md` artifact, not in
  the generic container.

**Never create a second ticket store.** No phase file, no progress file, no acceptance queue that
**replaces** `.agent_state/plans/<task-id>/`. The failure is two stores competing to be believed:
when they disagree, the copy that wins is whichever one the next agent reads first, and nothing
marks which was authoritative. A session's own task list coexists with the record as a projection of
the moment; what must not happen is a ticket taking its state *from* that projection — ticket status
is the closed enum in the header, decided in the record.

Wayfinder, to-spec and to-tickets are independent producers that publish wherever the repo tracks
work; they know nothing about this record. When their output becomes the durable work, **dev-flow
transcribes it** into these ordinary generic tickets and keeps a pointer back to the producer's
artifact — the producers are never asked to write here. Unfinished implementation and repair are
generic ticket work too.

When `refresh` reports the record over budget, or before adding a new entry to `INDEX.md`, read
[references/record-hygiene.md](references/record-hygiene.md) for where each kind of content moves —
the rule is a move, never a rewrite.

## Reading the record

- The frontier, the largest ticket ID, and the complete dependency graph are the ticket headers in
  `tickets/*.md`.
- Superseded decisions are the `Status` cells in `decisions.md`.
- The complete record inventory is `locate`, which lists the directory when asked and stores
  nothing.

`refresh` validates ticket status, reports a record that has gone stale, and names frozen state
written into `Current` or `Next`. It does not validate the dependency graph or the frontier these
queries reveal — a record can still contradict them, and the reader carries the cost of noticing.

## Conditional route

Which producer applies — wayfinder, to-spec, to-tickets — and when `archive` is appropriate, is
[references/conditional-route.md](references/conditional-route.md). Read it once a Slice, a spec, or
a dispatch decision is on the table.
