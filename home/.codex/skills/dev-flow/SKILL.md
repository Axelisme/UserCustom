---
name: dev-flow
description: "Orchestrator durable task lifecycle and narrative record: use to start, resume, locate, archive, or close a multi-session task and manage its INDEX and tickets."
---

# Dev Flow

## Orient

Run `locate <task-id>`; when the task ID is unknown, run `list` first and use a returned `lookup_id`.
Read the located `INDEX.md`, and the handed-off ticket when a handoff named one, following only the
pointers current work needs.

If those sources cannot name the next action, repair `INDEX.md`'s `Current` and `Next` — with the
user when the answer is not yours to write — rather than scanning tickets, artifacts, or the task DAG
to infer one.

Orientation is complete when you can state the task and its next action from the authoritative
sources.

## Jurisdiction

Dev-flow owns the durable task lifecycle, record structure, the conditional route through to-spec
and to-tickets, and S0 design admission. It remains the sole durable narrative, status, and
authority record before and after delegated work. Candidate-backlog owns backlog eligibility.

The task-level fork: a task that owns a managed integration runs every ticket through
[collab](../collab/SKILL.md), where collab's own two placement axes decide writer and verifier; a
task with no managed integration keeps its tickets with the Orchestrator, which holds the lane's
write token itself under [lane-authority](references/lane-authority.md). Collab consumes bounded
task intent and returns evidence without creating another task lifecycle.

Point to the owner and stop; restatement creates a drifting second authority.

### The conditional route

Which planning owner applies, and what `archive` means.

- **to-spec** when the task or Orchestrator needs a frozen implementation contract; landing alone
  creates no such need and `spec: none` stays valid. Publish the producer-format spec under the
  task's `spec/` directory (see [the container
  shape](references/record-hygiene.md#the-container-shape)) and set the INDEX spec pointer; to-spec
  owns the format.
- **to-tickets** when several dispatched slices need explicit dependency edges; work the
  Orchestrator completes in one context still records a generic ticket. Keep the producer artifact
  under `spec/` beside the spec it slices, then transcribe approved work into separate conforming
  lifecycle tickets, each producer ticket's `Blocked by:` edges landing in the lifecycle ticket's
  `depends_on` and each lifecycle ticket pointing back to the producer artifact. A lifecycle ticket
  is a `tickets/<ticket-id>/ticket.md`, so a producer-format file kept elsewhere leaves the path
  `locate` parses free.

When an external repository tracker is explicitly in use, link its spec or issues from the record
instead of publishing them here.

A handoff routes and guides; the record keeps factual authority and continues to own implementation
work after it. A handoff is neither a durable stage of the route nor a factual owner: what the task
means, what durable stage it reached, and why all stay with the record.

`archive` is a neutral directory move that implies no completion. Reconcile the evidence and
close-out in the task record before moving it, whether work completed or was abandoned.

## S0 — Design admission: Need → Design → Slicing → Triage

S0 admits new design work through Need, Design, Slicing, then Triage; each output feeds the next,
and `S0` names the full sequence. Read the stage you are starting, and only that stage:
[Need](references/s0-design-admission.md#need), [Design](references/s0-design-admission.md#design),
[Slicing](references/s0-design-admission.md#slicing),
[Triage](references/s0-design-admission.md#triage).

Decision-only tasks without implementation output and small corrections completed in Orchestrator's
single context may skip the sequence. They still record the `Envelope` pointer to the frozen file
holding the task's out-of-scope boundary.

## The record

Durable work lives under `.agent_state/plans/<task-id>/`, managed by `scripts/plan.py` in this
skill's directory, not a repository-local `scripts/` directory. `plan.py --help` owns the command
Interface and `templates/` the current scaffold and frontmatter shape. Four things neither one
tells you:

- `.agent_state` is gitignored, so a worktree carries no task record. Run `plan.py` from the main
  checkout.
- The control root is the explicit `--repo` directory when supplied, otherwise the Git worktree root
  derived from the current directory; an explicit path is used directly without Git discovery.
- `list` returns narrow references for immediate active containers without reading INDEX or ticket
  content. **Active** means only that the container is placed under `.agent_state/plans/`, not that
  work or tickets remain.
- `locate` is read-only. It reports active, archived, missing, or ambiguous location; canonical
  container and INDEX paths; readable task identity and spec; exact pending, closed, and total counts
  when all ticket headers are readable; and bounded parse limitations. It does not list ticket paths,
  inspect narrative sections, dependencies, or artifacts, select focus, infer completion, or claim
  health — read `INDEX.md` and the relevant ticket narratives for those judgements.

The script owns container lifecycle, not narrative truth: archive restoration reverses the opaque
container move, and narrative sections remain human-authored rather than script-validated schema.

**What owns what.** INDEX owns task identity and the optional spec pointer. A ticket is a directory
whose `ticket.md` frontmatter owns ticket identity and lifecycle state; Outcome and Acceptance own
the bounded contract; state and Resolution own closure. Files beside `ticket.md` own that ticket's
durable evidence, and only when the evidence must persist. The ticket owns the ordered binary
Mechanical gates plan; `templates/ticket/ticket.md` holds its rules.

**Who may write what.** The Orchestrator owns all ticket content and exclusively changes lifecycle
state and Resolution. The lane's **writer** — whoever holds its single write token, a dispatched
implementer or the Orchestrator writing the change itself — toggles the Acceptance claims whose
observer is itself, writes the Acceptance section's `Swept at`, and may use its ticket's `scripts/`
subtree. A reviewer reads and
verifies without editing the ticket. A dispatched writer or reviewer never writes `INDEX.md`.
[lane-authority](references/lane-authority.md) owns the writer position, the three mutation classes
that are never inferred from one another, which observer owns which checkbox, and the closing sweep
every writer runs before declaring its lane finished.

Use one **single-store**: durable ticket state comes from this record. Session task lists are
temporary projections and never overwrite durable state merely because their UI differs. A
competing phase, progress, or acceptance store leaves the next reader choosing authority by accident.
Compaction is a **move** to the owning document rather than a rewrite.

## Closing a ticket

Treat closure as one Orchestrator-owned coordinated record transition. Confirm the applicable
Acceptance state, write Resolution once, set the ticket frontmatter to `state: closed`, then
reconcile `INDEX.md`'s `Current` and `Next` with the task's remaining work. Normal closure follows
completion of all applicable Acceptance claims. Abandoned, superseded, or rejected closure may retain
unchecked claims when Resolution explains why. Closure is complete when both files reflect the
transition; a session task list or review result alone is not durable closure.

Clear implementation-time temporary files, tests, and data before closure, and give every deliberate
retention an owner and a discharge condition. Each skill that creates implementation-time state
declares what its own scaffolding is and when it comes down (for example
[tdd](../tdd/SKILL.md#durable-behavior-tests-and-probes), and
[collab](../collab/SKILL.md#responsibility-boundaries) for a dispatched writer's
`probe/<ticket-id>/`).

## Graduating a decision to an ADR

`decisions/` lives in the untracked task container, so a decision whose force outlives its task
needs a home in the repository itself — one ticket whose whole output is one ADR. Two conditions
govern that ticket, cheapest test first:

1. **Self-contained.** The ADR references nothing under `.agent_state/`; tracked content — commit
   identities, module Interface declarations, source paths — is unrestricted. Write the
   self-contained version to find out: a decision that cannot be stated without pointing back into
   its task record has not finished separating from that task, and does not graduate. This is also
   what licenses the ADR to restate reasoning `decisions/` already holds, which
   [design-principles](references/design-principles.md) has you point at everywhere else: the record
   it restates is designed to disappear, so here alone the ADR is its heir rather than a competing
   copy.
2. **The user opens it.** Dev-flow supplies the route and waits. The rate at which ADRs appear
   stays a human decision, which is why this is a separate ticket rather than a closure obligation,
   and a decision still moving is one the user has not asked to record.

Whether a decision qualifies at all, and what an ADR looks like, belong to `domain-modeling`: read
[its ADR format](../domain-modeling/ADR-FORMAT.md) for the gates under "When to offer an ADR", the
template, and the numbering.

## When to read what

- **This task's `Standing orders` is about to change, or you quote or apply an entry it already
  holds** → [custody](references/custody.md).
- **A decision falls outside the task's out-of-scope boundary** → [custody](references/custody.md),
  following the `Envelope` section's pointer to its frozen artifact.
- **You are writing `INDEX.md`, or creating a ticket, spec, research note, scripts container, or
  durable evidence of any other kind** → [the container
  shape](references/record-hygiene.md#the-container-shape) for what stays in INDEX and where each
  content kind lives; [the Acceptance
  appendix](references/record-hygiene.md#workflow-scoped-acceptance-appendix) when a target is
  named; [durable
  validation](references/record-hygiene.md#durable-validation-that-must-persist-a14a15) when an
  observation must survive the session.
- **You are writing or publishing a ticket's `Seam contract`, or a dispatched role returns
  `BLOCKED` against one** → [ticket-seam-contract](references/ticket-seam-contract.md), which owns
  the three modes, `S#` coverage and its `A#` observers, graduation, and the publication
  preconditions that stop a dispatch. Every ticket discloses this path in its own `Seam contract`
  section, because that is where the roles you dispatch look for it.
- **This task requested Collab `efficiencyFeedback`**, at the first request or when approaching
  managed integration removal and archive →
  [collab-feedback-closeout](references/collab-feedback-closeout.md), which holds the pending
  closeout obligation and the snapshot-before-retirement sequence.
- **You are about to toggle an Acceptance checkbox, hold a lane's write token, or judge whether
  someone else's mutation was authorized** → [lane-authority](references/lane-authority.md), which
  owns the writer position, the three mutation classes, the observer that owns each checkbox, the
  closing sweep and its `Swept at` record, and how an evidence file is created from its template.
- **You are evolving dev-flow itself** → [design-principles](references/design-principles.md).
