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

- **Acceptance state mutation** — toggling a claim's `- [ ]`, governed by the observer rule below,
  and writing the Acceptance section's `Swept at`, whose observer is the lane's writer.
- **Evidence mutation** — writing one exact granted target beside the ticket, plus the ticket's
  `scripts/` subtree, which needs no per-file grant.
- **Lifecycle mutation** — `state`, `Resolution`, dependencies, claim wording, adding or removing
  claims, and `INDEX.md`. The Orchestrator holds this whether or not it is the writer, and never
  delegates it.

Holding one class grants nothing in another. A named appendix target and its covered claim IDs bound
what may be written into that file; they are not a grant to toggle those claims' checkboxes. Assigned
checkboxes are not a grant to touch the surrounding prose beyond `Swept at`, which this class names.
When a mutation falls in a class you do not hold, report it instead of making it.

## Acceptance checkboxes belong to their observer

`unchecked` means unproven. Each claim's checkbox belongs to the observer its ticket names for it;
when the ticket names none, it belongs to the lane's current writer, because a claim with no named
observer is one that doing the work proves.

The writer toggles its own claims **as each becomes proven** — as the gate passes, as the appendix
lands — keeping each truthful: check only while the criterion is presently satisfied, and uncheck it
when evidence contradicts it. Toggle as you go rather than deferring every claim to one pass at the
end: a ticket that stays all-unchecked through the lane and goes all-checked at closure carries no
information at any moment, which is the failure this rule exists to prevent.

Toggle only your own claims. A claim naming an Orchestrator, user, manual, external, or
production-path observer waits for that observation no matter who is writing. Closure never requires
every box checked: `Resolution` may explain what stayed unproven.

For a reviewer: a truthful toggle by the writer is authorized metadata maintenance, not an
out-of-envelope write, and an unchecked claim is not by itself a defect. A checkbox whose state
contradicts your direct evidence is reportable through your ordinary verdict channels with location
and evidence, rather than authoritative on its face.

## The closing sweep

Toggling keeps a checkbox truthful at the moment it is set. It supplies no moment when the writer is
obliged to look again, so a claim proved in the first hour stays checked while later edits in the
same lane invalidate it — the writer is not lying, it is remembering.

The writer's last act before declaring the lane finished is therefore a per-claim pass over the
Acceptance list against the final committed tree. Re-confirm each writer-owned claim by an action
taken during the sweep — reading the current file, running the gate, checking the appendix — rather
than by recalling that it held when it was checked. Uncheck any claim the sweep cannot re-confirm;
when that claim is required, closure is unavailable. A dispatched writer returns `BLOCKED`; the
Orchestrator writing the change itself stops and decides placement again. Claims naming another
observer are not swept.

Record the sweep in the Acceptance section's `Swept at`: the commit every writer-owned claim was last
re-confirmed against. It is written after the lane's final commit, so it names that commit, and a
`Swept at` behind the lane head means the sweep is stale rather than that a claim is false. It shows
the sweep was declared against this tree and never that it was done well.

A close-out writer with no semantic edit sweeps like any other writer: that path is where a run died
mid-lane, which is where a stale checkbox is likeliest.

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
