# Dev-flow — keeping INDEX.md small, and where the rest lives

`INDEX.md` is reread whole on every re-orientation, so it holds only what changes the next action.
Keep current judgement separate from long review history, command logs, SHAs, trees, and receipts;
those belong to the evidence file or gate that produced them.

Everything else already has a home, so compaction is a **move**, never a rewrite:

- A standing order's scope stays in its frozen owning file. If none exists, dev-flow creates the
  custody source at `standing-orders/<YYYY-MM-DD>-<slug>.md` before admitting the order. Its INDEX
  entry keeps the verbatim quote, exact pointer, and lapse condition.
- Lapsed orders move to `standing-orders/lapsed.md`, whole and verbatim.
- Evidence that must outlive a past gate belongs to one gate-owned file under its ticket.
- Durable validation commands, results, and subject identities belong to one `validation.md` under
  the owning ticket; a later judgement points to it only when needed. Cheap reproducible observations
  may remain in the terminal handoff instead.

Compact at an accepted boundary rather than mid-slice, and list what moved in the same reply.
Summarizing custody to make the record shorter is a failure: preserve the authoritative text.

## The container shape

`plan.py create` materializes `templates/task/`, which is the single source of this shape. Every
directory it creates already exists in a new task, so nothing has to be invented at write time:

```
<task-id>/
  INDEX.md
  tickets/<ticket-id>/ticket.md      the lifecycle ticket, plus that ticket's own evidence beside it
  spec/                              frozen contracts — to-spec owns their format
  research/                          external findings and task-wide process findings with their supporting raw snapshots — research owns their format
  decisions/                         decisions this task made and must not relitigate
  standing-orders/                   custody sources; see custody.md
```

Task-wide process findings and their supporting raw snapshots live under `research/`; receipt-only or empty results are preserved without fabricated findings and source-grounded findings keep an exact raw artifact pointer. `research/` does not enter `INDEX` history, which remains limited to current judgement and next action.

**A ticket is a directory, not a file.** `tickets/<ticket-id>/ticket.md` carries the lifecycle
frontmatter, and its `id` must equal the directory name — `locate` reports the ticket unreadable when
they disagree, so a rename that touches only one of the two fails loudly instead of silently
splitting the record. Everything that ticket produces sits beside it: `admission.md`,
`validation.md`, `acceptance.md`, `gate-<timestamp>.log`, whatever the work actually needed. One
ticket, one directory, and `ls` over it is that ticket's whole story.

Start a ticket by copying `templates/ticket/ticket.md` to `tickets/<ticket-id>/ticket.md`, and each
piece of evidence by copying `templates/ticket/evidence.md` beside it — that template carries the
Subject / Evidence / Residuals spine every evidence kind shares, and the situational sections are
yours to add. Copy an evidence file when you are ready to write it: an empty `validation.md` sitting
in a ticket directory reads as validation that exists, so let absence stay honest.

The filesystem is the inventory; a second inventory drifts. That holds only while every file is
reachable from the scope that owns it, so a flat pile beside these directories is a defect, not a
variant — and a file at the container root that `templates/task/` did not put there is the beginning
of one.

A ticket's directory is also its discharge unit: whatever [closing a
ticket](../SKILL.md#closing-a-ticket) does not retain leaves with the directory, and every deliberate
retention states its owner and discharge condition in Resolution. An unbounded directory surviving
closure means that obligation went unpaid.
