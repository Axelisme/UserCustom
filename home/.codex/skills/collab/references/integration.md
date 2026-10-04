# Integration operations

## Integrate

Collect one ticket at a time through the selected runtime after its gates pass on the lane. Review
happens later, over ranges of integration ([Range review](review.md#range-review)). Other tickets may
continue.

Integration is `wave/<task>/integration` at `.agent_state/worktrees/<task>/integration`; lanes
branch from it as `wave/<task>/<ticket>`. Reconcile before collection. Before collection, perform
[Resource custody](#resource-custody)'s preflight; managed collect retires the lane during the operation.
Collect the lane, then run ticket gates on integration. When they pass, close the ticket
and retire any remaining lane resources through the same custody procedure.
A conflict or failed result gate needs a fix: prepare a repair lane if collection already retired
the original, assign one writer, fix, and rerun gates.

Stop for tracked dirt, conflicts, or missing results. Finish when integration holds the collected
work and its gates pass.

Integration tickets observe interactions after dependencies close. Persistence drift enters through
the runtime reconciliation route; rerun affected checks, and the next range review judges the merge
resolution.

## Land and clean up

Landing requires current user authority or an in-force task grant naming persistence mutation and
conditions; apply dev-flow custody. Push requires separate authority. Otherwise retain reviewed
integration.

Before mutation, confirm every delivering ticket is closed (including integration tickets; tracker
delivers no candidate), integration gates pass, and the range review is complete:
`refs/collab/<task>/reviewed` equals integration HEAD and the latest verdict is COMPLETED. Inspect persistence conflicts, overwrite risks,
and index changes that could enter the merge. Unrelated edits may remain only when runtime preserves
them without inclusion; inspect its admission/failure behavior. Stricter limits block landing,
not authorize discarding, committing, or stashing unrelated work.

Reconcile drift first; the reconciled head needs its range review. Managed landing creates a two-parent merge:
previous persistence first, judged integration second, with the judged integration tree.
Stop on missing authority, conflicts, overwrite/inclusion risk, unsupported preservation, live
consumer handoff risk, candidate drift, hook failure, or unreviewed changes.

After landing, apply [Resource custody](#resource-custody) to remaining execution resources.
Finish with observed landing, preserved local state, and retired or explicitly retained resources.

## Resource custody

Preflight any operation that retires resources by inventorying owned files, processes, worktrees,
and branches. Remove only task-created resources whose purpose is complete. Ask about unrecognized untracked files; their
presence gives no deletion authority. Managed retirement deletes untracked and ignored lane files.
Move into the task's `runs/` only files that a gate summary or verdict cites; the rest is disposable.
A resource that must outlive the lane goes to tracker Resources.

Proceed only after ownership is established and evidence is safe. After the operation, verify actual
retirement and preservation of retained local state; put any incomplete cleanup in tracker Resources.
