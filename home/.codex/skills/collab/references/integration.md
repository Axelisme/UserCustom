# Integration operations

## Integrate

Collect a ticket after its review rounds have accepted every applicable criterion, the way a PR merges
after approval. Collect one ticket at a time with the selected runtime's collection operation while
other tickets continue.

Merge the accepted lane into integration and run the ticket's gates on the result. A clean merge whose
gates pass is collected: close the ticket with its Log line and retire the lane. A conflict, or a clean
merge whose gates fail, produces an unreviewed change: fix it on the lane under one writer, rerun the
gates, and hold one more review round on the fix before collecting. The ticket returns to `review` for
that round.

Interactions between tickets are an integration ticket's criteria; after its dependencies close, the
Orchestrator runs its gates on integration and reviews it like any ticket. If persistence moved,
reconcile it into integration through the runtime route, rerun affected checks, and review the imported
interactions as an integration ticket before landing.

Stop collection on conflicts, tracked dirt, a commit that differs from the accepted one, or missing
gate results. Collection is complete when integration contains the accepted work, its gates pass, and
the ticket's Log records the collected commit.

## Land and clean up

Landing needs a current user message or in-force task grant naming persistence mutation and conditions.
Read dev-flow custody before applying a durable grant. Push needs separate authority. Without landing
authority, stop at reviewed integration.

Before landing, confirm every ticket in the landing candidate is `closed`, including its integration
tickets, and that integration's gates pass. Confirm persistence has no staged changes, tracked unstaged
changes, or ordinary untracked files; ask the user about untracked files you do not recognize.
Reconcile persistence drift into integration and regain applicable judgement before landing. Managed
landing creates a two-parent merge with the previous persistence head first and the judged integration
head second; its tree must equal the judged integration tree.

Inventory owned resources before retirement, then remove the task-owned temporary files, processes,
worktrees, and branches whose purpose is complete. Delete only files this task created; stop and ask
about an unrecognized untracked file. Managed retirement may delete a lane's untracked and ignored
files, including its gate logs. Record each retained resource's owner and cleanup condition in its
ticket's Log.

Stop on missing authority, persistence dirt, live consumer handoff risk, candidate drift, hook failure,
unaccepted changes, or unrecognized files. Completion requires confirmed integration or landing and
retirement or explicit retention of every execution resource.
