# Example record

These are examples, not schemas. Every shape here can be violated when the task calls for it; the
reader judges, in context, whether a deviation is warranted. Where anything here conflicts with
[`admission-standard.md`](../admission-standard.md), the standard wins.

## How to read this directory

Read it as one task record frozen mid-flight, not as a form to fill in. `INDEX.md` is the single
moment "in progress": `Goal`, `Current` (including `Current stage`), and `Next` are all live prose,
and the fenced block at the bottom is a mechanical projection of this directory's own file tree —
compare it against the actual files here as a sanity check, not as something to imitate by hand in
a real record (a real record gets that block from `scripts/plan.py refresh`).
`Envelope` and `Standing orders` show the two shapes those slots take: a frozen boundary written out
in full, and one instruction quoted in the user's own words with the date it was issued.
`tickets/config-single-source.md` is a rich, dispatched implementation ticket.
`tickets/config-single-source-validation.md` is thin on purpose: it is blocked, so there is nothing
yet to say. `decisions.md` holds the standing decisions that both tickets rely on but never restate.
`artifacts/config-single-source-source-map.md` is where an evidence pointer in a ticket actually
lands.

## Other moments this INDEX does not show

- **Just created.** Right after `create`, `Goal` holds the one-sentence need, `Current` says only
  "Task created," and `Next` points at writing or selecting the first ticket. There is no
  `Current stage` yet because no stage has been entered.
- **Handoff-ready.** Before a decision-authority transfer, `Current` names the exact clean
  integration SHA/tree, which tickets are closed versus open, and any blocking condition a
  successor must see first; `Next` becomes the successor's first action rather than the current
  agent's own.

## Guardrails

- Progress lives in `INDEX.md`'s `Current` and in each ticket's `Outcome` — not in a phase or
  progress file you invent for this task.
- Dependencies live in each ticket's `depends_on` header — not in a second ticket store.

This directory is reference material under `references/`, not a task record under
`.agent_state/plans/`; `refresh` never runs against it.
