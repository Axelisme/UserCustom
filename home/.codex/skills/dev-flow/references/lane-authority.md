# Dev-flow — lane authority

Three parties touch a ticket: the Orchestrator that owns it, the **writer** that holds its lane, and
the read-only **reviewer** that judges it. This file owns which of them may mutate what.

## Writer and reviewer are positions, not roles

The **writer** is whoever currently holds the lane's single write token. A dispatched implementer is
one case; the Orchestrator writing a bounded change itself is another, and while it holds the
position it works under these rules rather than under its own ownership of the ticket. The position
is scoped to one lane and released when that lane stops, so it is never an identity carried between
lanes and never a permission a past writer keeps.

The **reviewer** is the same kind of object: whoever reads the stopped lane read-only and judges it.
A dispatched `collab-acceptor` is one specialization of that position, and a `code-review` dispatch
is another; both hold the position, and neither is it. A reviewer never holds the write token.

Every rule below that names the writer applies to whoever holds the position. A rule that fires only
when a dispatch assigned something leaves the Orchestrator-as-writer case unruled, and the fallback
there — the Orchestrator owns the ticket — is what turns per-claim progress into one batch edit at
closure.

## Three mutation classes, never inferred from one another

- **Acceptance progress mutation** — toggling a claim's `- [ ]`, governed by the observer rule
  below. It is a progress note and carries no Acceptance authority: what a claim's checkbox says
  never settles that claim, and the Orchestrator rebuilds the list from observer results at closure.
- **Evidence mutation** — writing one exact granted target beside the ticket, plus the ticket's
  `scripts/` subtree, which needs no per-file grant.
- **Lifecycle mutation** — `state`, `Resolution`, dependencies, claim wording, adding or removing
  claims, and `INDEX.md`. The Orchestrator holds this whether or not it is the writer, and never
  delegates it.

Holding one class grants nothing in another. A named appendix target and its covered claim IDs bound
what may be written into that file; they are not a grant to toggle those claims' checkboxes. Assigned
checkboxes are not a grant to touch the surrounding prose at all. When a mutation falls in a class
you do not hold, report it instead of making it.

## Every claim names the observer that decides it

Each Acceptance claim names one **deciding observer** — `gate`, `acceptor`, `orchestrator`, `user`,
or a named external observer — and a ticket with an unnamed claim is not publishable.
[ticket-seam-contract](ticket-seam-contract.md#publication-and-change-control) carries that among the
other publication preconditions.

The observer is what settles the claim. Nothing else does, and in particular the checkbox does not:
it is the writer's progress note, so that a fresh writer picking up a half-finished lane can see what
has already been done. The writer toggles its own claims as each becomes proven, keeping each
truthful — check only while the criterion is presently satisfied, uncheck it when evidence
contradicts it — and toggles nobody else's.

At closure the Orchestrator rebuilds the whole list from what each observer reported: the gates it
ran, the reviewer's verdict, its own reading, the user's answer. It is reading results, not the
writer's memory, so a stale or optimistic checkbox changes no outcome. Closure never requires every
box checked; `Resolution` explains what stayed unproven.

For a reviewer: a checkbox is metadata, never evidence, so its state is not a defect and not a thing
to verify. Judge the claim against the lane.

## A gate you cannot close honestly

A gate that can only be made to pass by changing what it measures is an unclosable gate, not a gate
you have closed. Name the gate and the obstruction; closure is unavailable. This is the writer
position's rule, so it holds whether a dispatched implementer or the Orchestrator holds the lane, and
it is judged per gate within the ticket's ordered gate repair rather than as a reason to stop that
repair early.

## Creating an evidence file

The Orchestrator names the exact target path; the writer creates it. Copy
`~/.codex/skills/dev-flow/templates/ticket/evidence.md` to that path, then fill its sections with
targeted edits. Never write the file whole: a whole-file write destroys the copied skeleton and
leaves nothing to show the template was used, which reduces the copy to ceremony. The template's
comments stay in the published file, so a later reader and a checker can both tell the copy was
respected.

Refuse to create over a path that already exists, and report instead: an earlier workflow's evidence
must stay byte-for-byte unchanged.
