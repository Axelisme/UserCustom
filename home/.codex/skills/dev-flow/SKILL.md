---
name: dev-flow
description: Route a heavy effort through frozen planning, v127 orchestrate implementation, checkpoint acceptance, and explicit persistence landing.
---

# Dev Flow

Use this skill for work that needs a frozen contract and more than one session. It navigates the outer pipeline; each station owns its own contract and runtime details.

Every role reads its own section of the [admission standard](references/admission-standard.md) before acting: Root S1/S3/S4/S5/S6/S7, Oracle S2, reviewer S4.3. Those checks are decidable from artifacts and are not subject to argument.

## Pipeline

```text
wayfinder → to-spec → to-tickets → ( orchestrate → acceptance → accepted checkpoint )* → explicit final landing → close-out
```

The bracketed segment repeats **once per vertical Slice** on one append-only task integration branch. The orchestrate station publishes an exact Implementation candidate; S5 records the reviewed, user-accepted exact SHA as an accepted checkpoint without mutating persistence. An explicit partial landing is a user-authorized side action, not another station or ledger. Workflow evolution reads [design principles](references/design-principles.md).

## Task sizing

A dev-flow task is sized so that its **first accepted checkpoint is days away, not weeks**. If the effort cannot reach one within that budget, it is not one task: split it into several dev-flow tasks, each with its own frozen spec, and let `wayfinder` hold the map across them.

This is a hard constraint, not a preference. A task whose review and user acceptance happen only once at the end has no feedback and concentrates all risk on one day. Persistence may land once at task end only because each preceding Slice was already production-reachable in its candidate, independently landable, machine-gated, and user-accepted. A plan that batches those acceptance decisions into one final cutover has failed this check; recut it into Slices that each admit one surface and delete its predecessor.

## v127 acceptance scheduling

Acceptance opens only when the milestone passes **S3** of the admission standard. S3 is seven
git-derived checks costing seconds; running expensive judgement over an increment that is
unreachable, deletes nothing, or has looped on one Slice spends the review budget on a candidate
that cannot be accepted. S3.8 — two consecutive milestones failing reachability or deletion —
stops implementation and reports to the user instead of dispatching the next Wave.

Mode is a task-scoped scheduling policy, not durable workflow truth:
`mode_override = day | night | auto`. An explicit override wins. In `auto`, a user-authored turn
that resumes this task is Day Mode; an autonomous continuation with an active goal and no live
user turn is Night Mode. The inferred mode is recomputed each turn. Only the deferred acceptance
obligations are durable, in the current release phase record.

Both modes run the same machine gates in the same order, and differ only in when **S5** runs
against the reviewed SHA.

### Day Mode

After focused gates and S3, run **simplify**, the **canonical tests**, and one **clean-detached
code-review** of the **post-simplify exact SHA**. Only then make that reviewed SHA runnable and
obtain **user acceptance** against its S1.1 sentence. Record the accepted checkpoint in the
current phase row and continue from the task integration tip; S5 does not mutate the persistence
branch. A user's attention is the scarcest input in this loop, so anything simplify or either
review axis can find must be found before the candidate reaches them. Rejection returns the Slice
to S1, and the next candidate is a new exact SHA whose gates reopen before the next user test.

### Night Mode

When the user is unavailable, record the Slice's deferred S5 obligation, then run the same
**simplify**, **canonical tests**, and **clean-detached code-review** sequence. Update the queue
item to the final reviewed exact SHA and state `reviewed_awaiting_user`; this is a provisional
checkpoint, never acceptance or landing. The next minimal Slice may base on that provisional tip.
The default hard ceiling is `max_speculative_depth: 10`, the longest dependency chain since the
latest accepted checkpoint; independent pending Slices do not add chain depth. Stop earlier if a
later Slice would overwrite a pending acceptance surface, requires a missing product decision,
or makes an earlier scenario independently untestable.

On the next Day Mode, process deferred items oldest-first in dependency order. Acceptance of the
same reviewed SHA preserves its machine evidence and records an accepted checkpoint without
persistence mutation. A rejection returns that Slice to S1 and marks dependent provisional items
`stale`; they cannot be accepted or landed until repaired by forward commits. Night Mode never
lands because every partial or final landing requires a live explicit user request.

At either mode's machine stage, the review reads the whole committed `base..integration-tip`
range, because cross-authority composition defects are only visible in the assembled picture;
simplify reads only the increment since the last reviewed SHA. Between milestones each Wave
passes only machine gates before collect. A later commit invalidates evidence for the later tip
and reopens its gates; historical evidence remains valid for its exact accepted SHA unless that
checkpoint is marked `stale`.

The task integration branch is append-only: never reset, rebase, force-update, or recreate it.
Rejected or stale descendants remain historical evidence and are repaired by new forward commits
from the current integration tip.

## Finding provenance

Every rework records `origin: user_acceptance | simplify | standards_review | spec_review`.
`user_acceptance` rework does not consume `machine_rework_cycles`: users may discover feedback
across several attempts, and S5 rejection returns to S1. It may not silently expand the frozen
usage envelope; new requirements amend the spec or become a new Slice. Only a simplify or
code-review finding that sends the candidate back to an implementation pass consumes one
`machine_rework_cycles` entry. Count once per batched return, never per finding; the initial
simplify pass, backlog findings, and `blocked_on_decision` consume none. Provenance follows the
finding even when a user later authorizes its fix.

Blocking is closed to spec violation, data loss, security, or reproducible behavior failure
within the frozen spec's usage envelope. The final review must not expand the frozen spec; a
finding without a contract basis in the frozen spec is backlog, never a blocker. Robustness,
quality, and out-of-envelope findings go through `candidate-backlog` and do not block an accepted
checkpoint or landing. Do not implement features the frozen spec does not require.

Routing is fixed below; cost judgement stays with Root. Minimize Wave round trips: batch
everything known at the same moment into one cycle — one Oracle correction carries all
current Spec findings, one Implementation pass carries all fixes. Spending a cycle on a
single finding while others are already known is a defect, not diligence.

```text
exit: full canonical suite green ∧ review has no blocking finding
      → the machine gates are done; hand that exact SHA to S5 under the
        current mode, and add nothing

for each review finding:
  not blocking (closed enum + contract_basis)   → backlog, continue
  mechanical Contract-surface slip (import/
           format/typo ∧ AST + collected node
           IDs unchanged)                       → Root applies the reviewer patch, merges
                                                  the Contract, records an explicit empty
                                                  Implementation handoff on that branch after
                                                  the merge, reruns only
                                                  collection, lint, and directly affected
                                                  tests; consumes no machine rework budget
  bounded (≤~30 lines local logic ∧ known seam
           ∧ direct contract test exists)       → fast path: Root or current single
                                                  writer fixes directly; focused tests;
                                                  re-review only the delta from the
                                                  previously reviewed SHA
  otherwise                                     → needs_fix starts a new Wave from the
                                                  integration tip (consumes one machine
                                                  rework cycle): a Spec
                                                  or behavior finding goes through Oracle
                                                  then Implementation, starting from an
                                                  executable contract regression; a
                                                  quality finding returns directly to
                                                  Implementation. After a fix, regenerate
                                                  the Git profile output, then simplify +
                                                  canonical tests + a new exact-SHA
                                                  clean-detached code-review

budget per machine rework cycle: 1 Oracle Contract correction, 1 Implementation fix,
                                 1 focused suite, 1 full suite, 1 detached review
budget spent → the next cycle batches all remaining machine findings under the same acceptance
               record — never auto-loop per finding

machine_rework_cycles per Slice: at most 2 (S4.1). The third is a scope event, not an
               implementation event: shrink the Slice, downgrade the remainder to backlog,
               or report to the user. Opening another machine-finding correction Wave on the
               same Slice is not a legal third action. User acceptance attempts are outside
               this counter. Per-cycle budgets bound one cycle; only S4.1 bounds the number
               of machine cycles.
```

A collected Wave is closed: a milestone finding is routed to the Wave owning the defective surface, but the correction runs as a new Wave based on the integration tip and collects again, and a finding spanning several Waves is always a new Wave. Run focused tests during modification; run the full canonical suite once only after focused green on a clean writer tree. Split the reruns: the writer produces the contract-suite and focused evidence, Root reruns only the machine gates before collect, and the full canonical suite runs once per milestone — never rerun an expensive suite that a clean exact SHA already covers. If a background writer's wait time exceeds Root's own estimate for a bounded fix, Root stops that writer and takes over directly. Full Wave ceremony is reserved for new seams, cross-authority changes, or an untrusted writer.

Maintain one update-in-place acceptance record per release. In Night Mode the same phase record
uses planning-with-files' `templates/phase.md` deferred-acceptance table as its storage schema;
INDEX points to it and may state only the pending count and next item. It is never a new state
file and never a second findings or landing ledger. Once a row is accepted, its SHA, status, and
machine evidence are frozen.

The contract tests and fixtures are immutable during simplify and throughout Implementation. A collected Wave is closed: close its runtime identities and remove its clean Oracle/Implementation worktrees, while retaining its Git branches and commits until final cleanup. Keep the single task integration worktree through accepted checkpoints and any partial landing.

## Minimal handoff

The orchestrate handoff is a small exact-SHA tuple containing the exact base SHA, Implementation SHA, frozen spec, task plan, canonical test results, and Git profile JSON. It is handed off without a receipt and without a finding bundle; those are not dev-flow state.

Persistence landing remains outside orchestrate and follows **S7**. It requires current user authority and two ancestry proofs: the accepted target is an ancestor of the task integration tip, and the observed persistence tip is an ancestor of that target. Apply it fast-forward-only: no squash, cherry-pick, rebase, merge commit, or push.

## Accepted checkpoints and landing

**Checkpoint cadence is per Slice.** Every Slice retains its reviewed and user-accepted exact SHA in the phase row and as an ancestor of the append-only task integration branch. The next Slice bases on the current integration tip. This preserves frequent feedback without per-Slice persistence mutation.

At every accepted checkpoint, report in three lines: what behavior was accepted, what remains, and the largest current risk. Say explicitly that the checkpoint is not yet persistence-landed. A partial landing additionally reports what became persistence-reachable, but never cleans up, seals the phase, archives the plan, or closes the task.

The default is one **final landing** after a current explicit user request. It requires all applicable items accepted, no stale or unresolved item, and the latest accepted SHA equal to the clean integration tip. Only after that exact SHA is fast-forwarded to the persistence branch may Root remove the clean integration worktree, delete integrated role and integration branches, and delete the task's `refs/orchestrate/<task-id>/` namespace according to repository policy. There is no automatic landing and no push.

## Effort close-out

After final landing and cleanup evidence are recorded, close the wayfinder map, record durable decisions, move out-of-scope ideas to the candidate backlog, seal and archive the task plan, and report the final persistence-reachable destination and residual risks. Do not invent state files to represent this navigation.
