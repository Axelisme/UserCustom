# Dev-flow — keeping INDEX.md small

`INDEX.md` is reread whole on every re-orientation, so a long one is a cost paid forever and a dense one is
skimmed exactly where it matters. It holds what changes the next action.

The size problem is downstream of a state problem. **Frozen state has no home here at all** — a SHA,
a tree, a ReviewGate id, a node count. Not because it is long, but because it is the one kind of
content that goes wrong silently: it stays readable and confident long after it stops being true,
and the next session acts on it. `refresh` names such tokens in `Current` and `Next`; move them to
the artifact of the gate that produced them rather than rewording them.

Everything else already has a home too, so compaction is a **move**, never a rewrite:

- The scope of a standing order — what it authorizes, what it excludes, what it supersedes — is the
  agent's own conclusion, so it belongs in `decisions.md` where a later decision can supersede it.
  The entry keeps the quote, the pointer and the lapse condition, and nothing else.
- Lapsed orders move to `standing-orders-lapsed.md`, whole and verbatim.
- Evidence that a past gate passed — counts, SHAs, baselines — belongs to that gate's artifact. The
  record keeps the frontier, not the receipts.
- The artifact inventory is `locate` and `artifacts/README.md`. A hand-kept list beside them is a
  second copy that drifts.

`refresh` measures the authored region against a budget and reports it; it never refuses on size,
because the one moment the record must open is the moment a compacted session needs it. Compact at
the next accepted frontier rather than mid-slice, and list what moved in the same reply. Summarizing
to hit the budget is the failure this rule exists to prevent: a record that is short because custody
was paraphrased away is worse than one that is long.
