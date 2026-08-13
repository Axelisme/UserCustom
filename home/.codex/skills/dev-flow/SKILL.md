---
name: dev-flow
description: "Root/Caller durable task lifecycle and narrative record: use to start, resume, locate, archive, or close a multi-session task and manage its INDEX and tickets."
skill_version: 13
---

# Dev Flow

## Orienting

After compaction, or in a session that did not create the task, run `locate <task-id>`. If the task ID is unknown, run `list` first. `locate` resolves the active or archived container and points to its `INDEX.md`; it does not assess narrative correctness or choose the next ticket. After a handoff, begin with this guidance, the located `INDEX.md`, and the handed-off ticket, then follow only their pointers needed for current work. If that closure cannot identify the next action, maintain the record rather than scanning tickets, artifacts, or the task DAG to infer one. Read the [Custody reference](references/custody.md) whenever this task's `Standing orders` section is about to change, or when you quote or apply an entry it already holds. A section reading `None` has no entry to quote or apply, so that second condition stays shut; admitting its first order is a change, so the first still fires. Read the reference as well when a decision falls outside the frozen `Envelope` — a separate section, and an independent condition. Orientation is complete when you can state the task and its next action from the authoritative sources.

## Jurisdiction

Dev-flow owns the durable task lifecycle, record structure, the conditional route through wayfinder,
to-spec and to-tickets, and S0 design admission. It remains the sole durable narrative, status, and
authority record before and after delegated work. Candidate-backlog owns backlog eligibility.
When delegating implementation, selecting generic Acceptance, or choosing writer placement, read
[collab](../collab/SKILL.md); it consumes bounded task intent and returns evidence without creating
another task lifecycle.

Point to the owner and stop; restatement creates a drifting second authority. When evolving this
workflow, read the [design principles](references/design-principles.md).

## S0 — Design admission: Need → Design → Slicing → Triage

S0 admits new design work through Need, Design, Slicing, then Triage; each output feeds the next.
Before starting any stage, read
[references/s0-design-admission.md](references/s0-design-admission.md). `S0` names the full sequence.

Decision-only tasks without implementation output and small corrections completed in Root's single
context may skip the sequence. They still record an `Envelope` value.

## One task record

Durable work lives under `.agent_state/plans/<task-id>/`, managed by `scripts/plan.py` in this
skill's directory, not a repository-local `scripts/` directory. Use `scripts/plan.py --help` for the
command Interface and `templates/` for the current scaffold and frontmatter shape.

The script owns container lifecycle, not narrative truth: archive restoration reverses the opaque
container move, locate is read-only, and narrative sections remain human-authored rather than
script-validated schema. INDEX owns task identity and the optional spec pointer. Ticket frontmatter
owns ticket identity and lifecycle state; Outcome and Acceptance own the bounded contract; state and
Resolution own closure. Artifacts own durable evidence only when that evidence must persist.

The Caller owns all ticket content and exclusively changes lifecycle state and Resolution. A
delegated writer may only toggle the Acceptance claims explicitly assigned to it; a reviewer reads
and verifies without editing the ticket.

Use one **single-store**: durable ticket state comes from this record. Session task lists are
temporary projections and never overwrite durable state merely because their UI differs. A
competing phase, progress, or acceptance store leaves the next reader choosing authority by accident.

Read [references/record-hygiene.md](references/record-hygiene.md) when you are the one writing
`INDEX.md`: it holds what stays there and where every other content kind already lives, so
compaction is a **move** to that owner rather than a rewrite. A dispatched writer or reviewer never
writes `INDEX.md`.

## Closing a ticket

Treat closure as one Caller-owned coordinated record transition. Confirm the applicable Acceptance
state, write Resolution once, set the ticket frontmatter to `state: closed`, then reconcile
`INDEX.md`'s `Current` and `Next` with the task's remaining work. Normal closure follows completion of
all applicable Acceptance claims. Abandoned, superseded, or rejected closure may retain unchecked
claims when Resolution explains why. Closure is complete when both files reflect the transition; a
session task list or review result alone is not durable closure.

Close a ticket when [`probe/<ticket-id>/`](../tdd/SKILL.md#durable-behavior-tests-and-probes) is
empty or absent, or when every remaining entry carries an owner and a retirement condition.
Scaffolding still standing means the job is unfinished, so this is where it comes down. The clearing
change skips a new verdict on one condition you confirm: it touches only `probe/<ticket-id>/`.

## Reading the record

When the task ID is unknown, `list` returns narrow references for immediate active containers without
reading INDEX or ticket content; use a returned `lookup_id` with `locate`. Here, **active** means only
that the container is placed under `.agent_state/plans/`, not that work or tickets remain.

`locate` reports active, archived, missing, or ambiguous location; canonical container and INDEX
paths; readable task identity and spec; exact pending, closed, and total counts when all ticket
headers are readable; and bounded parse limitations. It does not list ticket paths, inspect
narrative sections, dependencies, or artifacts, select focus, infer completion, or claim health.
Read `INDEX.md` and the relevant ticket narratives for those judgements.

## Conditional route

An unresolved planning owner or destination for a Slice, spec, ticket publication, artifact,
dispatch decision, or archive triggers
[references/conditional-route.md](references/conditional-route.md); it supplies the applicable
planning owner and archive condition.
