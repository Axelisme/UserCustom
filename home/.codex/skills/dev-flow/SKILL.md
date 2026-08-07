---
name: dev-flow
description: Durable task record for work that must survive compaction and handoff. Use when starting multi-session work, resuming or archiving an existing task record, asking what a task's current state is, or when another skill needs the shared plan-directory record. Not for single-session edits that need no durable record.
skill_version: 8
---

# Dev Flow

## Orienting

After compaction, or in a session that did not create the task, run `locate`; it derives record
health, frontier, and orientation at read time. Read what it names; the pointed record preserves the
`Envelope` and `Standing orders`, while `lint` names any section whose mechanical obligations are
violated. Open **Custody** below only when changing those sections or deciding how user authority
applies. Orientation is complete when you can state the task and its next action from the named
sources. Everything below governs acting on them.

## Jurisdiction

Dev-flow owns the durable task lifecycle, record structure, the conditional route through wayfinder,
to-spec and to-tickets, and S0 design admission — everything before dispatch. Candidate-backlog owns
backlog eligibility. **Orchestrate owns [S1–S5](../orchestrate/references/admission.md)** and Git/runtime
coordination. Once a Slice enters a lane, orchestrate decides admission from its Git artifacts.

Point to the owner and stop; restatement creates a drifting second authority. When evolving this
workflow, read the [design principles](references/design-principles.md).

## S0 — Design admission: Need → Design → Slicing → Triage

S0 admits new design work through Need, Design, Slicing, then Triage; each output feeds the next.
Before starting any stage, read
[references/s0-design-admission.md](references/s0-design-admission.md). `S0` names the full sequence.

Decision-only tasks without implementation output and small corrections completed in Root's single
context may skip the sequence. They still record an `Envelope` value.

## Custody

The record holds the user's authority in **custody**; it creates none.

**Surface new grants.** List new standing-order entries in the same reply so the user can disown
them immediately.

**Admit durable grants.** An order is authority that still binds after the requested act completes.
Test it with: *doing this, does the sentence go away?* The work itself records one-off instructions.
When one sentence combines an act and a durable grant, admit it for the grant and quote the whole
sentence.

**Resolve ratification by address.** Before asking for assent, persist the proposal; then store the
user's quote and a pointer to that frozen text. Amendments require new ratification rather than
editing the assented text. If no antecedent was recorded, preserve it under an explicit
`reconstructed` label.

**Retire by user authority.** An order lapses only when its stated condition fires, a later user
message revokes or replaces it, or the task is archived. Move it intact to the retired record with
date and reason. Keep overlapping orders separate: the newest governs addressed points and all
other in-force clauses remain. Ask whether an ambiguous new order narrows or replaces an old one.

**Apply the Envelope.** Out-of-envelope decisions cite the frozen Envelope slot.

**Mutate from current authority.** Only current user messages authorize custody changes. A standing
order records a grant; it never extends one. When it activates another skill, point to that skill's
contract for its grants and exclusions.

## One task record

- Durable work lives under `.agent_state/plans/<task-id>/`, managed by `scripts/plan.py` in this
  skill's directory, not a repository-local `scripts/` directory.
- The public Interface is `create | archive | locate | refresh`; `archive --undo` restores an
  archived record and `locate` is read-only.
- `INDEX.md` holds `Goal`, `Current`, `Next`, `Envelope`, and `Standing orders`.
- `Current` records where the conditional route stopped or why a stage was skipped, when useful.
- `tickets/*.md` use the generic three-field header, `Resolve by`, `Outcome`, and `Current`.
- Producer-owned `decisions.md`, not the generic ticket container, holds decision work.

Use one **single-store**: durable ticket state comes from this record's closed status enum. Session
task lists are temporary projections. A competing phase, progress, or acceptance store leaves the
next reader choosing authority by accident.

Wayfinder, to-spec, and to-tickets publish to the repository's normal destination and know nothing
about this record. When their output becomes durable work, dev-flow transcribes it into generic
tickets and links the producer artifact; producers never write here. Unfinished implementation and
repair are generic ticket work.

When `refresh` reports an over-budget record, or before adding to `INDEX.md`, read
[references/record-hygiene.md](references/record-hygiene.md) and **move** each content kind to its
owner without rewriting it.

## Reading the record

- Ticket headers in `tickets/*.md` are the frontier, largest ticket ID, and dependency graph.
- `Status` cells in `decisions.md` identify superseded decisions.
- `locate` derives the frontier and what to read next, never the record's contents; the filesystem
  under `artifacts/` is the inventory.

`refresh` validates ticket status and reports staleness and frozen state in `Current` or `Next`. It
does not validate dependencies or frontier consistency; the reader must reconcile those against the
headers.

## Conditional route

When a Slice, spec, dispatch decision, or archive is in question, read
[references/conditional-route.md](references/conditional-route.md) for the applicable producer and
archive condition.
