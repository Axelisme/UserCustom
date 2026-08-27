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
- Durable ticket validation that must persist across sessions belongs to `validation.md` or `validation-<scenario>.md` under the owning ticket (see Durable validation below); routine mechanical gates remain ephemeral and stay with the run artifact. Cheap reproducible observations may remain in the terminal handoff instead.
- Guiding script locations are `scripts/` under the task (Orchestrator-owned) and `scripts/` under each ticket (assigned writer's subtree, acceptor read-only); ticket scripts remain with closed ticket content and no cleanup, use-restriction, graduation or deduplication policy is introduced.

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

## Guiding script locations (S5)

`templates/task/` provides `<task>/scripts/` and `templates/ticket/` provides `<ticket>/scripts/` as guiding locations. The Orchestrator owns task-level scripts; the assigned writer may create or modify its ticket's `scripts/` subtree without gaining wider record mutation authority (no per-file grant needed, but no extension to other ticket-folder content). The acceptor remains read-only. Dispatch provides the ticket folder path; roles derive the needed container from it. Ticket closure retains scripts with the same lifecycle as other ticket content; no cleanup, use-restriction, graduation or deduplication policy is introduced.

## Durable validation that must persist (A14–A15)

Reserve `validation.md` for a single durable scenario and `validation-<scenario>.md` for multiple independent owners beside the owning `ticket.md`. Routine mechanical gates (pytest, type/lint, formatter) remain ephemeral. Durable validation is for production, manual, MCP, external-service, hardware, benchmark or migration observations that must survive the session.

It must record 5W1H and be authored by its execution owner:

- **Who:** execution operator and evidence writer; Orchestrator writes itself/user/external-owner validation, delegated worker writes only the exact assigned difficult-claim appendix, acceptor is read-only.
- **What:** covered Acceptance IDs, scenario, expected/actual observations, PASSED/FAILED, bounded artifact pointers and residual limitations.
- **When:** exact clean candidate formed after final Acceptance and before closure, with timezone; candidate change invalidates prior evidence.
- **Where:** exact candidate identity (commit/tree, lane) and execution environment/backend/device/MCP host identity.
- **Why:** why observation cannot be cheaply reproduced, depends on external mutable state, needs operator judgement, is costly or explicitly requires durable audit.
- **How:** shipped entry point, bounded inputs, script or MCP sequence, judgement and cleanup method; when a task-record script is used, record its path and SHA-256.

Durable script/MCP/production validation binds exact candidate, environment, covered claims, method, observations, limitations and cleanup; referenced task-record scripts include path and SHA-256. Evidence uses the `Subject / Evidence / Residuals` shape from `templates/ticket/evidence.md`; large logs and transcripts remain outside the evidence body with bounded pointers. Only `evidence.md` owns that Subject/Evidence/Residuals spine; do not duplicate it.
