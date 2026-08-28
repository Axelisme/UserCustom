---
name: dev-flow
description: "Orchestrator durable task lifecycle and narrative record: use to start, resume, locate, archive, or close a multi-session task and manage its INDEX and tickets."
---

# Dev Flow

## Orienting

After compaction, or in a session that did not create the task, run `locate <task-id>`. If the task ID is unknown, run `list` first. `locate` resolves the active or archived container and points to its `INDEX.md`; it does not assess narrative correctness or choose the next ticket. After a handoff, begin with this guidance, the located `INDEX.md`, and the handed-off ticket, then follow only their pointers needed for current work. If that closure cannot identify the next action, maintain the record rather than scanning tickets, artifacts, or the task DAG to infer one. Dev-flow's control root is the explicit `--repo` directory when supplied, otherwise the Git worktree root derived from the current directory; an explicit path is used directly without Git discovery. Read the [Custody reference](references/custody.md) whenever this task's `Standing orders` section is about to change, or when you quote or apply an entry it already holds. A section reading `None` has no entry to quote or apply, so that second condition stays shut; admitting its first order is a change, so the first still fires. Read the reference as well when a decision falls outside the task's out-of-scope boundary — follow the `Envelope` section's pointer to its frozen artifact — an independent condition. Orientation is complete when you can state the task and its next action from the authoritative sources.

## Jurisdiction

Dev-flow owns the durable task lifecycle, record structure, the conditional route through wayfinder,
to-spec and to-tickets, and S0 design admission. It remains the sole durable narrative, status, and
authority record before and after delegated work. Candidate-backlog owns backlog eligibility.
The task-level fork: a task that owns a managed integration runs every ticket through
[collab](../collab/SKILL.md), where collab's own two placement axes decide writer and verifier; a
task with no managed integration works its tickets through [implement](../implement/SKILL.md).
Collab consumes bounded task intent and returns evidence without creating another task lifecycle.

Point to the owner and stop; restatement creates a drifting second authority. When evolving this
workflow, read the [design principles](references/design-principles.md).

## S0 — Design admission: Need → Design → Slicing → Triage

S0 admits new design work through Need, Design, Slicing, then Triage; each output feeds the next.
Before starting any stage, read
[references/s0-design-admission.md](references/s0-design-admission.md). `S0` names the full sequence.

Decision-only tasks without implementation output and small corrections completed in Orchestrator's
single context may skip the sequence. They still record the `Envelope` pointer to the frozen file
holding the task's out-of-scope boundary.

## One task record

Durable work lives under `.agent_state/plans/<task-id>/`, managed by `scripts/plan.py` in this
skill's directory, not a repository-local `scripts/` directory. Use `scripts/plan.py --help` for the
command Interface and `templates/` for the current scaffold and frontmatter shape.

The script owns container lifecycle, not narrative truth: archive restoration reverses the opaque
container move, locate is read-only, and narrative sections remain human-authored rather than
script-validated schema. INDEX owns task identity and the optional spec pointer. A ticket is a
directory whose `ticket.md` frontmatter owns ticket identity and lifecycle state; Outcome and
Acceptance own the bounded contract; state and Resolution own closure. Files beside `ticket.md` own
that ticket's durable evidence, and only when the evidence must persist.

The Orchestrator owns all ticket content and exclusively changes lifecycle state and Resolution. A
delegated writer may only toggle the Acceptance claims explicitly assigned to it; a reviewer reads
and verifies without editing the ticket. The ticket owns the ordered binary Mechanical gates plan (see `templates/ticket/ticket.md`); every listed gate must pass before `COMPLETED` and repository-owned commands are referenced by pointer rather than duplicated.

Guiding script locations are `templates/task/scripts/` and `templates/ticket/scripts/`; Orchestrator owns task scripts, assigned writer may use its ticket `scripts/` subtree, acceptor is read-only; no cleanup, use-restriction, graduation or deduplication policy is introduced and ticket scripts remain with the closed ticket content. See `references/record-hygiene.md`.

Durable ticket validation that must persist across sessions uses `validation.md` or `validation-<scenario>.md` beside the ticket with 5W1H content and execution-owner authorship; routine mechanical gates remain ephemeral. See `references/record-hygiene.md`.

Workflow-scoped Acceptance appendix: for named difficult claims that a read-only acceptor cannot
adequately reproduce, the Orchestrator copies `templates/ticket/evidence.md` to one fresh exact
target under the ticket directory before dispatch and places that exact path plus covered claim IDs
in both role briefs. The template alone owns the `Subject`, `Evidence`, and `Residuals` shape. The
worker may mutate only that exact target, binding the fixed candidate and covered claims to method,
observations, artifact pointers when needed, and explicit limitations without judging Acceptance; if
a required appendix cannot be completed, `COMPLETED` is unavailable. A dispatch without an assigned
target grants no task-record evidence mutation. Automatic corrections update the same target
sequentially for the latest candidate; a later separately dispatched workflow receives a fresh target
and leaves earlier workflow evidence unchanged. The acceptor stays read-only, directly checks
observable claims, and judges only whether the appendix describes a reasonable process for the
covered difficult claims.

Use one **single-store**: durable ticket state comes from this record. Session task lists are
temporary projections and never overwrite durable state merely because their UI differs. A
competing phase, progress, or acceptance store leaves the next reader choosing authority by accident.

Read [references/record-hygiene.md](references/record-hygiene.md) when you are the one writing
`INDEX.md`, and again before writing durable evidence anywhere: it holds what stays in INDEX, the
container shape every task already has, and where each content kind lives. Compaction is a **move**
to that owner rather than a rewrite. A dispatched writer or reviewer never writes `INDEX.md`.

## Closing a ticket

Treat closure as one Orchestrator-owned coordinated record transition. Confirm the applicable Acceptance
state, write Resolution once, set the ticket frontmatter to `state: closed`, then reconcile
`INDEX.md`'s `Current` and `Next` with the task's remaining work. Normal closure follows completion of
all applicable Acceptance claims. Abandoned, superseded, or rejected closure may retain unchecked
claims when Resolution explains why. Closure is complete when both files reflect the transition; a
session task list or review result alone is not durable closure.

Close a ticket only when implementation-time temporary files, tests, and data are cleared before
closure — give every deliberate retention an owner and a discharge condition. This obligation names
no specific scaffolding: each skill that creates implementation-time state declares what its own
scaffolding is and when it comes down (for example
[tdd](../tdd/SKILL.md#durable-behavior-tests-and-probes)).

## Graduating a decision to an ADR

A decision whose force outlives its task needs a home outside the task container, which is not
tracked where this workflow runs. When the user opens a ticket to record one, read
[references/adr-graduation.md](references/adr-graduation.md) for the two conditions that ticket meets
and the owner of the format it produces.

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

When a Dev-flow task requested Collab `efficiencyFeedback` — whether at the first request or when approaching managed integration removal and archive — follow [collab-feedback-closeout.md](references/collab-feedback-closeout.md) for the pending closeout obligation and snapshot-before-retirement sequence.
