# Dev-flow — keeping INDEX.md small

`INDEX.md` is reread whole on every re-orientation, so it holds only what changes the next action.
Keep current judgement separate from long review history, command logs, SHAs, trees, and receipts;
those belong to the artifact or gate that produced them.

Everything else already has a home, so compaction is a **move**, never a rewrite:

- A standing order's scope stays in its frozen owning artifact. If no such artifact exists, dev-flow
  creates the custody source at `artifacts/standing-orders/<YYYY-MM-DD>-<slug>.md` before admitting
  the order. Its INDEX entry keeps the verbatim quote, exact pointer, and lapse condition.
- Lapsed orders move to `artifacts/standing-orders-lapsed.md`, whole and verbatim.
- Evidence that must outlive a past gate belongs to one gate-owned artifact.
- Durable validation commands, results, and candidate identities belong to one general task artifact;
  a later judgement points to it only when needed. Cheap reproducible observations may remain in the
  terminal handoff instead.
- The filesystem under `artifacts/` is the artifact inventory; a second inventory drifts.

Compact at an accepted boundary rather than mid-slice, and list what moved in the same reply.
Summarizing custody to make the record shorter is a failure: preserve the authoritative text.
