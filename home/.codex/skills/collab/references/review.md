# Review and correction

## Review

A review round is a PR review of one ticket on its lane, before collection. A **gates-only** ticket
skips the round: a trivial change with no behavior or contract at stake, such as formatting or a
comment, whose every acceptance criterion is a mechanical gate. The Orchestrator judges those gates,
checks the boxes, and collects it; anything the gates cannot establish needs a review round.

A round's inputs are one exact clean commit and tree, the baseline, the stopped writer, the gate
summaries for that commit, and the criteria the round judges. Reconcile the lane with current
integration and rerun gates first, the way a PR is rebased before review.

The Orchestrator sends the whole bounded assignment in the acceptor's dispatch, using the dev-flow
[review round](../../dev-flow/references/records.md#review-rounds) fields. Set the ticket to `review`
and log the round's child ID, subject commit/tree, baseline, criterion IDs, and absolute verdict path.
The dispatch carries the task; source and observation files remain exact path/anchor references.
Freeze the review checkout until the verdict, and while the round is out, work the next
[frontier](../../dev-flow/references/planning.md#parallel-tickets) ticket. To keep working on the
ticket's next milestone instead, give the acceptor a detached worktree at the subject commit and
continue in the lane.

The acceptor reads the dispatch, the ticket's `#acceptance` and `#scenarios`, the diff, declarations,
callers, tests, and gate summaries. It judges every criterion the round names and directly related
instances, including prose, structure, configuration, repository data, responsibility placement, test
assertions, and gate sufficiency. It runs no gates and changes no checkout; it writes the verdict file.

A missing baseline, mutable or dirty subject, active writer, ambiguous criterion, missing authority, or
unavailable gate summary makes the round `UNREVIEWABLE`. Repair that input and start the next round.
Repeated failure to prepare the same input stops with its owner.

Review completes when the verdict file exists with outcome `COMPLETED`, approving only the named
criteria on that exact commit, or `BLOCKED`, listing every supported defect with location, criterion,
evidence, and a bounded suggested fix. Specialized Standards and Spec review uses code-review under its
own contract.

## Correct and decide

Read the verdict. For each finding decide: fix it, decline it with a reason, or move it to a user
decision under dev-flow's [Maintain the record](../../dev-flow/references/records.md#maintain-the-record)
while feasible work continues. A user-owned choice of behavior, scope, authority, data structure, or
responsibility is never decided inside a correction.

For fixes, set the ticket back to `doing` and assign bounded corrections by pointing at the verdict
path and finding IDs. The Orchestrator changes interfaces and formal tests; the implementer changes
assigned internal logic. Rerun applicable gates and use [Subject changes](#subject-changes) to decide
whether another dispatch is needed. A new dispatch includes each previous finding's disposition.
The next round judges those findings, the new diff, and the interactions it touches; it does not
reopen unrelated history.

On `COMPLETED`, check the boxes the round established and log it. When every applicable criterion is
checked, collect the ticket under [Integrate](integration.md#integrate). For a changed candidate,
establish coverage under [Subject changes](#subject-changes); passing gates alone does not establish it.

If correction, verification, or a needed decision cannot proceed, set the ticket to `blocked` with a
Log line naming the blocker and its owner. Continue only after a change, new evidence, or an owner
decision provides a defensible next action.

## Subject changes

A semantic change affects behavior, a contract, or a fact judged by the assigned criteria, including
document meaning, configuration, responsibility placement, and validation sufficiency. It needs a
fresh dispatch. A small diff is not evidence that meaning stayed the same.

For formatting or other non-semantic changes, the Orchestrator inspects the old-to-new delta and
decides whether to reuse coverage or dispatch again, weighing review risk against time and token
cost. Record the old and new commit/tree, affected criterion IDs, evidence of unchanged meaning,
gate applicability, and the decision's cost/risk rationale in the ticket Log. Keep gate summaries
at their actual execution commits; the execution owner supplies any newly needed observations.
If equivalence or evidence applicability cannot be established, dispatch a new round.

Keep an active acceptor's checkout frozen at its dispatched commit. It can finish that review while
the lane changes elsewhere. Its verdict names only the commit it actually reviewed. The Orchestrator
may carry a completed verdict's coverage to the new candidate through the recorded decision, without
rewriting that verdict. A BLOCKED or UNREVIEWABLE verdict remains unresolved; reuse cannot turn it
into approval. An unexplained or dirty review checkout is still UNREVIEWABLE.

A changed review contract voids the round. A replacement dispatch identifies the change and uses
the next round number.
