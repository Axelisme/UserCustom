---
name: dev-flow
description: "Orchestrator durable task lifecycle and narrative record: use to start, resume, locate, archive, or close a multi-session task and manage its INDEX and tickets."
---

# Dev Flow

## Orient

**`locate` points; `INDEX` directs.** Run `locate <task-id>`; when the task ID is unknown, run `list`
first and use a returned `lookup_id`. `locate` returns the address of the record, so read the
`INDEX.md` at that address, then the handed-off ticket when a handoff named one, following only the
pointers current work needs.

If those sources cannot name the next action, repair `INDEX.md`'s `Current` and `Next` — with the
user when the answer is not yours to write — rather than scanning tickets, artifacts, or the task DAG
to infer one. Replace those two sections rather than editing them, and read what belongs in each:
[Current and Next](references/record-hygiene.md#current-and-next-are-replaced-not-edited).

Orientation is complete when the exact bounded action and owner in the current `Next` are in context,
any ticket that action names has been read, and you can place that action in the lifecycle below.

## The lifecycle

```
S0(task)                           once, at task start
  Need; Design; Slicing; Triage
  ticket(drafted) | ticket(pending)

while the task is live:
  graduate(frontier)
  dispatch(antichain(pending))
  implement()
  close(ticket) | cut off(ticket)

archive(task)
```

The block owns the order and nothing else. Each stage below carries its obligation and the pointer to
the file owning that stage's rules; a stage is not runnable from this page alone. One invariant spans
them: **a ticket is `pending` before its implementation starts.**

`close` and `cut off` are the two terminal transitions, and they differ in what was bought rather
than in how much work landed. A ticket closes when its applicable Acceptance is settled. A ticket is
**cut off** when the review it would take to settle the rest is no longer being purchased, so it
stops with that verification unbought and says so. Both live in [Closing a ticket](#closing-a-ticket).

- **S0** — Run Need, then Design, then Slicing, then Triage, each output feeding the next. Read the
  stage you are starting, and only that stage:
  [Need](references/s0-design-admission.md#need), [Design](references/s0-design-admission.md#design),
  [Slicing](references/s0-design-admission.md#slicing),
  [Triage](references/s0-design-admission.md#triage). Decision-only tasks with no implementation
  output, and small corrections completed in one Orchestrator context, may skip the sequence; they
  still record the `Envelope` pointer to the frozen file holding the task's out-of-scope boundary.
  When the task needs a frozen contract or explicit dependency edges, take
  [the conditional route](#the-conditional-route) first.
- **`ticket(...)`** — Create it in whichever state fits. What decides that, what a `drafted` ticket
  carries and what it may omit: [carrying an
  item](references/s0-design-admission.md#carrying-an-item-to-a-drafted-ticket). Copy
  `templates/ticket/ticket.md`, and keep its `Seam contract` pointer in the ticket you publish,
  because that is where the roles you dispatch look for it. Where each kind of content lives —
  `INDEX.md`, spec, research note, scripts container, durable evidence: [the container
  shape](references/record-hygiene.md#the-container-shape).
- **`graduate`** — Graduate the frontier before dispatching from it; [carrying an
  item](references/s0-design-admission.md#carrying-an-item-to-a-drafted-ticket) owns the batch, its
  relation to the antichain, and what stays `drafted`. What a ticket must satisfy to reach `pending`,
  and what you may rewrite in it while it is still `drafted`:
  [ticket-seam-contract](references/ticket-seam-contract.md#publication-and-change-control),
  which also owns the three modes, `S#` coverage and its `A#` observers. When a claim names a workflow
  target, [the Acceptance
  appendix](references/record-hygiene.md#workflow-scoped-acceptance-appendix) owns its shape.
- **`antichain`** — Compute it before granting concurrency;
  [Slicing](references/s0-design-admission.md#slicing) owns candidacy, reachability, write scope and
  the missing-edge check.
- **`dispatch`** — Begin with the ticket-start handshake in
  [ticket-alignment](references/ticket-alignment.md). A request to start opens the handshake; the
  Orchestrator shows its proposal, and the user's reply to that proposal accepts or corrects it and
  completes alignment. Then route the ticket through [collab](../collab/SKILL.md), entering at its
  `Responsibility boundaries` boundary 1, which prepares the contract, places the remaining
  implementation and its reviewer, and finds each Acceptance claim's deciding observation already
  settled at graduation. Collab consumes bounded task intent and returns evidence without creating
  another task lifecycle. When a dispatched role returns `BLOCKED` or `NEEDS_DECISION` against a
  Seam contract, the coordination is owned by
  [ticket-seam-contract](references/ticket-seam-contract.md#publication-and-change-control).
- **`implement`** — Hold or place the lane's single write token.
  [lane-authority](references/lane-authority.md) owns the writer position, the three mutation classes
  that are never inferred from one another, the deciding observer every claim names, and how an
  evidence file is created from its template. Read it before toggling an Acceptance checkbox, holding
  a write token, or judging whether someone else's mutation was authorized. An observation that must survive the session belongs to [durable
  validation](references/record-hygiene.md#durable-validation-that-must-persist-a14a15).
- **`close` | `cut off`** — See [Closing a ticket](#closing-a-ticket), which owns both terminal
  transitions and the reviewer cap that produces the second.
- **`archive`** — The task ends when the user completes or abandons it, not when the loop runs out of
  tickets; a ticket still `drafted` then closes as abandoned under [Closing a
  ticket](#closing-a-ticket). Put every `cutoff` ticket in front of the user before the move: each
  one is a ticket whose remaining verification was never bought, and finishing it to `closed` or
  leaving it cut off is the user's call, never an automatic one. Record which they chose. Reconcile the evidence and close-out in the record before moving it,
  whether work completed or was abandoned: the move itself is neutral and implies no completion. A
  decision whose force outlives the task takes [the ADR route](references/adr-graduation.md), which
  the user opens.

A handoff routes and guides; the record keeps factual authority and continues to own implementation
work after it. A handoff is neither a durable stage of the lifecycle nor a factual owner: what the
task means, what durable stage it reached, and why all stay with the record.

## Jurisdiction

Dev-flow owns the durable task lifecycle, record structure, the conditional route through to-spec and
to-tickets, and S0 design admission. It remains the sole durable narrative, status, and authority
record before and after delegated work. Candidate-backlog owns backlog eligibility. Collab owns one
bounded change from boundary 1 onward.

Point to the owner and stop; restatement creates a drifting second authority.

### The conditional route

Which planning owner applies.

- **to-spec** when the task or Orchestrator needs a frozen implementation contract; landing alone
  creates no such need and `spec: none` stays valid. Publish the producer-format spec under the
  task's `spec/` directory (see [the container
  shape](references/record-hygiene.md#the-container-shape)) and set the INDEX spec pointer; to-spec
  owns the format.
- **to-tickets** when several dispatched slices need explicit dependency edges; work the Orchestrator
  completes in one context still records a generic ticket. Keep the producer artifact under `spec/`
  beside the spec it slices, then transcribe approved work into separate conforming lifecycle
  tickets, each producer ticket's `Blocked by:` edges landing in the lifecycle ticket's `depends_on`
  and each lifecycle ticket pointing back to the producer artifact. A lifecycle ticket is a
  `tickets/<ticket-id>/ticket.md`, so a producer-format file kept elsewhere leaves the path `locate`
  parses free.

When an external repository tracker is explicitly in use, link its spec or issues from the record
instead of publishing them here.

## The record

Durable work lives under `.agent_state/plans/<task-id>/`, managed by `scripts/plan.py` in this
skill's directory, not a repository-local `scripts/` directory. `plan.py --help` owns the command
Interface and `templates/` the current scaffold and frontmatter shape. Four things neither one
tells you — `--help` emits usage and argument lines only, and says nothing about what these commands
read or report:

- `.agent_state` is gitignored, so a worktree carries no task record. Run `plan.py` from the main
  checkout.
- The control root is the explicit `--repo` directory when supplied, otherwise the Git worktree root
  derived from the current directory; an explicit path is used directly without Git discovery.
- `list` returns narrow references for immediate active containers without reading INDEX or ticket
  content. **Active** means only that the container is placed under `.agent_state/plans/`, not that
  work or tickets remain.
- `locate` is read-only, and its ticket counts — one per state in `TICKET_STATES`, plus `total` — are exact
  only when every ticket header is readable; one unreadable header collapses all of them. It does not
  list ticket paths, inspect narrative sections, dependencies, or artifacts, select focus, infer
  completion, or claim health — read `INDEX.md` and the relevant ticket narratives for those
  judgements.

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
deciding observer is itself, as a progress note that settles nothing, and may use its ticket's
`scripts/` subtree. A reviewer reads and verifies without editing the ticket. A dispatched writer or reviewer never
writes `INDEX.md`. [lane-authority](references/lane-authority.md) owns the writer position, the three
mutation classes that are never inferred from one another, and the deciding observer every claim names.

Use one **single-store**: durable ticket state comes from this record. Session task lists are
temporary projections and never overwrite durable state merely because their UI differs. A competing
phase, progress, or acceptance store leaves the next reader choosing authority by accident.
Compaction is a **move** to the owning document rather than a rewrite; where each kind of content
moves to is owned by [compacting every other
section](references/record-hygiene.md#compacting-every-other-section). `Current` and `Next` are the
exception, replaced whole under [Current and
Next](references/record-hygiene.md#current-and-next-are-replaced-not-edited).

## Closing a ticket

Treat closure as one Orchestrator-owned coordinated record transition. Confirm the applicable
Acceptance state, write Resolution once, set the ticket frontmatter to its terminal state, then
replace — never edit — `INDEX.md`'s `Current` and `Next`, deciding each removed fact's fate under
[Current and
Next](references/record-hygiene.md#current-and-next-are-replaced-not-edited). Normal closure follows
completion of all applicable Acceptance claims. Abandoned, superseded, or rejected closure may retain
unchecked claims when Resolution explains why. A ticket closed while still `drafted` has no claims to
retain, and its Resolution says in one line that the question never became current. A deferred path
the user did not ask you to build is recorded in Resolution with where its comment sits in the code,
because the ticket directory goes when the ticket closes and the comment is what outlives it; sending
it to candidate-backlog instead is the user's call, not an automatic one. Closure is
complete when both files reflect the transition; a session task list or review result alone is not
durable closure.

### Cutting a ticket off

Review is finite. A ticket's **reviewer block ledger** counts the reviewer `BLOCKED` verdicts it has
accumulated since its design was last fixed, and the third one is where review stops being bought:
place no further reviewer for that ticket, and let the remaining work finish against its gates alone.
Collab's [review placement](../collab/SKILL.md#review-placement-and-the-correction-loop) owns the cap
itself and why the third block is already a loop's own stopping point.

The ledger lives in the ticket because nothing else survives the run that produced it: a correction
budget bounds the dispatch it was issued for, so a count kept only there reads three separate
two-block tickets as one cheap one.
[record-hygiene](references/record-hygiene.md#the-reviewer-block-ledger) owns the ledger's shape, and
the one condition that resets it.

Such a ticket ends at `state: cutoff`, not `closed`. Its Resolution separates the claims that were
proved from the claims that were merely declared — naming, for each of the latter, who declared it
and that no independent reader confirmed it — because the whole point of the separate state is that a
reader can tell a finished ticket from one that stopped paying. A `cutoff` ticket is otherwise a
terminal ticket: its `depends_on` edge is satisfied like a `closed` one, since a downstream ticket
that cannot start would deadlock the task the cap exists to keep moving. The downstream ticket carries
the unproven claims into its own `## Alignment` as world facts, so that it builds on a base it knows
is unverified; [ticket-alignment](references/ticket-alignment.md#inheriting-an-unverified-base) owns
that inheritance.

Then read the closure for what it made determinable: open `drafted` tickets for what is now visible,
and leave what was already `drafted` to the next graduation batch. An evidence-backed finding outside
the Envelope goes to candidate-backlog.

Clear implementation-time temporary files, tests, and data before closure, and give every deliberate
retention an owner and a discharge condition. Each skill that creates implementation-time state
declares what its own scaffolding is and when it comes down (for example
[tdd](../tdd/SKILL.md#durable-behavior-tests-and-probes), and
[collab](../collab/SKILL.md#responsibility-boundaries) for a dispatched writer's
`probe/<ticket-id>/`).

## When to read what

A pointer ending in `#<anchor>` addresses one section: open it there with
`python3 ~/.codex/skills/dev-flow/scripts/section.py <pointer>`, copying the pointer verbatim. A pointer
carrying no anchor is a whole document.

The lifecycle above carries the pointer for every rule keyed to a moment in it. These are keyed to a
condition instead:

- **This task's `Standing orders` is about to change, or you quote or apply an entry it already
  holds** → [custody](references/custody.md).
- **A decision falls outside the task's out-of-scope boundary** → [custody](references/custody.md),
  following the `Envelope` section's pointer to its frozen artifact.
- **You are evolving dev-flow itself** → [design-principles](references/design-principles.md).
