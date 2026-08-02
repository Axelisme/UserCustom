---
name: dev-flow
description: Durable task record for work that must survive compaction and handoff. Use when starting multi-session work, resuming or archiving an existing task record, asking what a task's current state is, or when another skill needs the shared plan-directory record. Not for single-session edits that need no durable record.
skill_version: 2
---

# Dev Flow

Use this skill for work that needs durable orientation across sessions.

## Jurisdiction

Dev-flow owns the durable task lifecycle and nothing beyond it. The
[admission standard](references/admission-standard.md) is the sole normative S0–S5 authority;
candidate-backlog owns backlog eligibility; orchestrate owns Git and runtime coordination. When
this skill's work reaches one of those, **point at it and stop there**. A restatement is a second
copy that drifts from the original, and the reader cannot tell which copy is current — so the
obligation runs both ways: routing skills point at the admission standard rather than repeating its
checks. Read it before wayfinding, spec, or ticket admission. When evolving the workflow itself,
read the [design principles](references/design-principles.md) for the altitude and evidence behind
those checks.

## Custody

The record holds no authority of its own. It is **custody** of the user's — what they froze and what
they granted, and nothing else. Three things follow.

**A held item is the original.** A standing order is the user's own sentence, **quoted verbatim**,
stamped with when it was issued and when it lapses. A paraphrase is the agent's understanding
wearing the user's name. List new entries in the same reply, so the user can disown them on the
spot.

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
- Its public Interface is exactly `create | archive | resume | refresh`.
- `INDEX.md` holds `Goal`, `Current`, `Next`, `Envelope`, and `Standing orders`.
- `Current` says where the conditional route stopped or why a stage was skipped, when useful.
- Its generated files block is a projection of the record directory.
- `tickets/*.md` hold ordinary generic work; their container is a three-field header, a
  `Resolve by` action, and `Outcome`/`Current`.
- Decision-making work keeps its decisions in the producer-owned `decisions.md` artifact, not in
  the generic container.

**Never create a second ticket store.** No phase file, no progress file, no acceptance queue, no
parallel task list. The specific workaround to refuse is the harness's own `TaskCreate` and
`TaskUpdate` tools: they are a non-authoritative session projection, their state does not survive
compaction, and their vocabulary — `pending`, `in_progress`, `completed` — does not enter a ticket.
Mirroring the record into them is still a second store, and the copy that gets believed is whichever
one the next agent reads first.

Wayfinder, to-spec and to-tickets may use these ordinary generic tickets when they select the
plan-directory backend. Unfinished implementation and repair are generic ticket work too.

## Reading the record

- The frontier, the largest ticket ID, and the complete dependency graph are the ticket headers in
  `tickets/*.md`.
- Superseded decisions are the `Status` cells in `decisions.md`.
- The complete record inventory is the generated files block after `refresh`.

`refresh` validates ticket status and reports a record that has gone stale. It does not validate the
dependency graph or the frontier these queries reveal — a record can still contradict them, and the
reader carries the cost of noticing.

## Conditional route

Wayfinder, to-spec, and to-tickets are independently usable producers; dev-flow only records their
chosen plan-directory work. Use wayfinder while the route to a durable destination is not yet clear.
Use to-spec before a landed change, unless it inherits a frozen contract (mark it inherited, refined,
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
Final close-out follows S5. After compaction, reread this skill, the frozen spec, the admission
standard, and the task record — including its `Envelope` and `Standing orders`, which carry what the
user froze and granted and are the first things a compacted session loses.
