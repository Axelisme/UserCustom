# Integration operations

## Integrate

Collect a ticket after its review rounds have accepted every applicable criterion, the way a PR merges
after approval. Collect one ticket at a time with the selected runtime's collection operation while
other tickets continue.

Integration is the branch `wave/<task>/integration`, checked out at
`.agent_state/worktrees/<task>/integration`, and each lane branches from it as `wave/<task>/<ticket>`.
Merge the accepted lane into integration and run the ticket's gates on the result. A clean merge whose
gates pass is collected: close the ticket with its Log line and retire the lane. A conflict, or a clean
merge whose gates fail, produces an unreviewed change: fix it on the lane under one writer, rerun the
gates, and hold one more review round on the fix before collecting. The ticket returns to `review` for
that round.

Interactions between tickets are an integration ticket's criteria; after its dependencies close, the
Orchestrator runs its gates on integration and reviews it like any ticket. If persistence moved,
reconcile it into integration through the runtime route, rerun affected checks, and review the imported
interactions as an integration ticket before landing.

Stop collection on conflicts, tracked dirt, missing gate results, or a commit without accepted
coverage. A different commit needs a new verdict or the Orchestrator's recorded non-semantic reuse
decision under [Subject changes](review.md#subject-changes). Collection is complete when integration
contains the accepted work, its gates pass, and the ticket's Log records the collected commit.

## Land and clean up

Landing needs a current user message or in-force task grant naming persistence mutation and conditions.
Read dev-flow custody before applying a durable grant. Push needs separate authority. Without landing
authority, stop at reviewed integration.

Before landing, confirm every ticket in the landing candidate is `closed`, including its integration
tickets (the tracker delivers no candidate and stays `doing` until archive), and that integration's
gates pass. Inspect persistence's local state for conflicts, overwrite risk, and index changes that
could enter the merge commit. Unrelated local modifications may remain when the runtime can preserve
them without including them in the landed commit. A globally clean checkout is not the policy.
Check the selected runtime's admission and failure behavior before mutation; stricter runtime limits
remain blockers, not permission to discard, commit, or stash unrelated work.

Reconcile persistence drift into integration and regain applicable judgement before landing. Managed
landing creates a two-parent merge with the previous persistence head first and the judged integration
head second; its tree must equal the judged integration tree.

Inventory owned resources before retirement, then remove the task-owned temporary files, processes,
worktrees, and branches whose purpose is complete. Delete only files this task created; stop and ask
about an unrecognized untracked file. Managed retirement may delete a lane's untracked and ignored
files; gate logs live in the task's `runs/` and stay. Record each retained resource's owner and
cleanup condition in its ticket's Log, or in the tracker's when no ticket owns it.

Stop on missing authority, conflicts, local-state overwrite or inclusion risk, unsupported runtime
preservation, live consumer handoff risk, candidate drift, hook failure, or unaccepted changes. Ask
before handling unrecognized files; their presence alone does not authorize cleanup. Completion
requires confirmed integration or landing, verification that retained local state is preserved, and
retirement or explicit retention of every execution resource.
