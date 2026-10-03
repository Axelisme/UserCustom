# Review and correction

## Review

Review one ticket's candidate before collection. A gates-only ticket may skip the round only if it
is trivial, has no behavior/contract at stake, and every criterion is mechanical; the Orchestrator
judges its gates. Any criterion gates cannot establish needs review.

Reconcile the lane with current integration and run applicable gates. Prepare an exact clean commit
and tree, baseline, stopped writer, gate summaries, and named criteria. Send the complete assignment
under dev-flow [Review rounds](../../dev-flow/references/records.md#review-rounds), mark review, and
save its round identity. Freeze the checkout until the verdict. To continue the next milestone,
give the acceptor a detached worktree at the subject and work in the lane; otherwise work independent
tickets.

The acceptor judges assigned criteria and directly related instances from the contract, diff,
declarations, callers, tests, and observations, including static facts and gate sufficiency. It keeps
checkouts unchanged and runs no tests, imports, linters, formatters, builds, or runtime gates.
Its only write is the dispatched verdict; missing/stale observations return to their execution owner.

Missing baseline/authority/evidence, dirty or mutable subject, active writer, or ambiguous criteria
makes a round UNREVIEWABLE. Repair the input and start the next round; repeated preparation failure
stops with its owner. A verdict completes the judgement as COMPLETED for named criteria at that
commit, or BLOCKED with all supported defects, locations, criteria, evidence, and bounded fixes.
Specialized Standards and Spec review uses code-review's separate contract.

## Correct and decide

Read the verdict and choose fix, decline with reason, or refer to a user decision for every finding.
Revisions enter dev-flow Plan's common change decision; corrections do not have a separate approval
policy. Continue feasible independent work while a decision is pending.

For fixes, set doing and assign verdict path/finding IDs to the proper writer: Orchestrator for
interfaces/formal tests, implementer for assigned internal logic. Rerun applicable gates and use
Subject changes below. The next dispatch includes all prior finding dispositions and judges fixes,
new diff, and touched interactions rather than unrelated history.

On COMPLETED, check established criteria and save the verdict pointer. Once all applicable criteria
have coverage, [collect](integration.md#integrate). Gates alone cannot establish review coverage.
If correction/verification/decision cannot proceed, mark blocked and record blocker/owner; resume
after a change, new evidence, or owner decision supplies a defensible action.

## Subject changes

Semantic changes need a fresh dispatch. Meaning includes behavior, contract, document content,
configuration, responsibility placement, and validation sufficiency; diff size proves no equivalence.
A changed review contract voids the round; identify the change in the next numbered dispatch.

For non-semantic changes, inspect the delta and decide reuse versus another round by risk and cost.
Log old/new commits and trees, affected criterion IDs, evidence of unchanged meaning, gate
applicability, and time/token/risk rationale. Keep summaries at actual execution commits; their owner
supplies missing observations. If equivalence or applicability is uncertain, dispatch again.

An active acceptor may finish on its frozen subject while the lane changes elsewhere. Its verdict
always keeps that subject; only the Orchestrator's recorded decision carries completed coverage
forward. BLOCKED/UNREVIEWABLE cannot become approval through reuse, and a dirty or unexplained
review checkout remains UNREVIEWABLE.
