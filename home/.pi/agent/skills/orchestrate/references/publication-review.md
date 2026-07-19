# Publication review

A canned risk-axis checklist for slices that touch **authority publication**: ownership
schedulers, projections, event streams, receipts, callbacks, delivery queues. Root names
this file as a risk axis in the dispatch; it then binds twice — the writer walks it as the
adversarial self-check before terminal, and the reviewer verifies the same axes
independently. It is not loaded for slices outside these domains.

## Authority publication matrix

Walk every claim/publication seam through each cut point; at each one, name who owns the
truth and what a concurrent actor observes:

- **Before claim** — can two actors claim the same authority? Is the claim itself
  published atomically with its precondition check?
- **After claim / before callback** — is the claimed-but-unpublished window observable?
  Who may supersede the claimant here (generation/epoch bump)?
- **Inside callback** — can the generation be superseded mid-callback? Does the callback
  re-validate its epoch before publishing results?
- **After callback / before settle** — direct reply vs live queue: can both deliver
  (double publication)? Which one is authoritative and how is the loser suppressed?
- **Detach / replacement at every cut** — at each point above, what happens if the
  subject is detached or replaced right now? Name the witness that proves the old
  authority stopped publishing.
- **Ordinals and revisions** — cursor, delivery ordinal, and resource revision are three
  different sequences; any comparison across them is a finding.
- **Capacity and cleanup** — is each limit process-wide or per-instance, and is that the
  contract's intent? Do terminal waiters run after rollback/cleanup, never before?
- **Resource exhaustion** — at every cut point, what does exhaustion do to the
  half-published state?

## Post-commit failure taxonomy

For any slice whose contract includes persistence or outward publication side effects,
the freeze names the outcome states the implementation must distinguish — a generic
exception for "truth changed but publication failed" is a defect, not an outcome:

1. **Definitely not committed** — truth unchanged; safe retry.
2. **Committed and published** — done; witness names the published artifact.
3. **Committed, publication incomplete** — truth changed, observers stale; requires a
   named repair path, not a raw exception.
4. **Durability outcome uncertain** — neither commit nor abort proven; must escalate to
   reconciliation, never silently retried.
5. **Reconciliation required** — a named procedure re-derives publication from truth.

Every state carries a **witness** (how the caller proves it is in this state), a
**cleanup** owner, and a **caller-visible closed outcome**. A state without all three is
an unfinished contract; the reviewer treats it as a major finding.
