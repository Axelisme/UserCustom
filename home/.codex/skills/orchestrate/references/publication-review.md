# Publication review

A canned risk-axis checklist for slices that touch **authority publication**: ownership
schedulers, projections, event streams, receipts, callbacks, delivery queues. Root names
this file as a risk axis in the dispatch; it then binds twice — the writer walks it as the
adversarial self-check before terminal, and the reviewer verifies the same axes
independently. It is not loaded for slices outside these domains.

## The authority transaction

Model every authority as a transaction; the seam is correct only if each transition names
**owner, lock, witness, rollback, capacity effect** and what a concurrent actor observes.
Name the transition — do not re-derive claim/settle/rollback per review:

`provisional claim → reserved authority → externally published → recoverably retained → retired`

- **→ provisional claim** — can two actors claim the same authority? Is the claim published
  atomically with its precondition check?
- **→ reserved authority** — is the claimed-but-unpublished window observable? Who may
  supersede here (generation/epoch bump), and does the callback re-validate its epoch before
  it publishes?
- **→ externally published** — direct reply vs live queue: can both deliver (double
  publication)? Which is authoritative, and how is the loser suppressed?
- **→ recoverably retained / retired** — if the subject is detached or replaced at any
  point, name the witness that proves the old authority stopped publishing.

Three concerns cut across every transition: **ordinals** (cursor, delivery ordinal, and
resource revision are three sequences; any comparison across them is a finding); **capacity**
(is each limit process-wide or per-instance, and is that the contract's intent? do terminal
waiters run after rollback/cleanup, never before?); **resource exhaustion** (at every
transition, what does it do to the half-published state?).

## Post-commit failure taxonomy

Outward publication makes the work a saga: before each outward transition, bind an
idempotent compensation to the transaction's existing `rollback` slot; on failure unwind
completed transitions in reverse. This is not snapshot rollback — when success is
ambiguous, compensation must be safe whether the step landed or not.

After a truth-changing attempt, expose exactly four outcomes: **not committed** (safe
retry), **committed and published** (done), **committed but publication incomplete**
(repair), or **durability uncertain** (reconcile, never blind retry). Each names a witness,
cleanup owner, and caller-visible closed outcome; missing any is a major finding.
