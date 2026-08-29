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

Dev-flow owns the durable task lifecycle, record structure, the conditional route through wayfinder,
to-spec and to-tickets, and S0 design admission. It remains the sole durable narrative, status, and
authority record before and after delegated work. Candidate-backlog owns backlog eligibility.

The task-level fork: a task that owns a managed integration runs every ticket through
[collab](../collab/SKILL.md), where collab's own two placement axes decide writer and verifier; a
task with no managed integration works its tickets through [implement](../implement/SKILL.md).
Collab consumes bounded task intent and returns evidence without creating another task lifecycle.

Point to the owner and stop; restatement creates a drifting second authority.

## S0 — Design admission: Need → Design → Slicing → Triage

S0 admits new design work through Need, Design, Slicing, then Triage; each output feeds the next.
Before starting any stage, read
[references/s0-design-admission.md](references/s0-design-admission.md). `S0` names the full sequence.

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
state and Resolution. A delegated writer may toggle only the Acceptance claims its dispatch
explicitly assigns, and may use its ticket's `scripts/` subtree. A reviewer or acceptor reads and
verifies without editing the ticket. A dispatched writer or reviewer never writes `INDEX.md`.

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

## When to read what

- **This task's `Standing orders` is about to change, or you quote or apply an entry it already
  holds** → [custody](references/custody.md).
- **A decision falls outside the task's out-of-scope boundary** → [custody](references/custody.md),
  following the `Envelope` section's pointer to its frozen artifact.
- **You are about to create a ticket, an Acceptance appendix, a research note, a spec, or a
  scripts container, or you are the one writing `INDEX.md`** →
  [record-hygiene](references/record-hygiene.md), which holds what stays in INDEX, the container
  shape every task already has, where each content kind lives, and the workflow-scoped Acceptance
  appendix for a difficult claim a read-only acceptor cannot reproduce.
- **You are writing or publishing a ticket's `Seam contract`, or a dispatched role returns
  `BLOCKED` against one** → [ticket-seam-contract](references/ticket-seam-contract.md), which owns
  the three modes, `S#` coverage and its `A#` observers, graduation, and the publication
  preconditions that stop a dispatch. Every ticket discloses this path in its own `Seam contract`
  section, because that is where the roles you dispatch look for it.
- **The user opens a ticket to record a decision whose force outlives its task** →
  [adr-graduation](references/adr-graduation.md).
- **The planning owner or destination for a Slice, spec, ticket publication, artifact, dispatch
  decision, or archive is unresolved** → [conditional-route](references/conditional-route.md), which
  supplies the applicable planning owner and archive condition.
- **This task requested Collab `efficiencyFeedback`**, at the first request or when approaching
  managed integration removal and archive →
  [collab-feedback-closeout](references/collab-feedback-closeout.md), which holds the pending
  closeout obligation and the snapshot-before-retirement sequence.
- **You are evolving dev-flow itself** → [design-principles](references/design-principles.md).
