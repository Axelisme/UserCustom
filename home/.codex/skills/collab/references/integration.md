# Integration operations

## Integrate

Collect one ticket at a time through the selected runtime after every applicable criterion has
accepted review coverage or the gates-only judgement. Other tickets may continue.

Integration is `wave/<task>/integration` at `.agent_state/worktrees/<task>/integration`; lanes
branch from it as `wave/<task>/<ticket>`. Reconcile before acceptance. Before collection, perform
[Resource custody](#resource-custody)'s preflight; managed collect retires the lane during the operation.
Collect the accepted lane, then run ticket gates on integration. When they pass, close the ticket
and retire any remaining lane resources through the same custody procedure.
A conflict or failed result gate leaves an unreviewed change: prepare a repair lane if collection
already retired the original, assign one writer, fix, rerun gates, and review before accepting it.

Stop for tracked dirt, conflicts, missing results, or absent accepted coverage. Changed commits
follow [Subject changes](review.md#subject-changes). Finish when integration holds accepted work,
its gates pass, and Log records the collected commit.

Integration tickets observe interactions after dependencies close. Persistence drift enters through
the runtime reconciliation route; rerun affected checks and review imported interactions in an
integration ticket before landing.

## Land and clean up

Landing requires current user authority or an in-force task grant naming persistence mutation and
conditions; apply dev-flow custody. Push requires separate authority. Otherwise retain reviewed
integration.

Before mutation, confirm every delivering ticket is closed (including integration tickets; tracker
delivers no candidate), and integration gates pass. Inspect persistence conflicts, overwrite risks,
and index changes that could enter the merge. Unrelated edits may remain only when runtime preserves
them without inclusion; inspect its admission/failure behavior. Stricter limits block landing,
not authorize discarding, committing, or stashing unrelated work.

Reconcile drift and regain applicable judgement first. Managed landing creates a two-parent merge:
previous persistence first, judged integration second, with the judged integration tree.
Stop on missing authority, conflicts, overwrite/inclusion risk, unsupported preservation, live
consumer handoff risk, candidate drift, hook failure, or unaccepted changes.

After landing, apply [Resource custody](#resource-custody) to remaining execution resources.
Finish with observed landing, preserved local state, and retired or explicitly retained resources.

## Resource custody

Preflight any operation that retires resources by inventorying owned files, processes, worktrees,
and branches. Remove only task-created resources whose purpose is complete. Ask about unrecognized untracked files; their
presence gives no deletion authority. Managed retirement may delete untracked/ignored lane files,
so preserve evidence in task runs first. Record retained owner/cleanup conditions in the owning
ticket's Log, or tracker when no ticket owns the resource.

Proceed only after ownership is established and evidence is safe. After the operation, verify actual
retirement and preservation of retained local state; record any incomplete cleanup and its owner.
