# Record operations

## Maintain the record

Records live under `.agent_state/plans/<task-id>/` in the main checkout while code worktrees remain
separate. Inputs are the current ticket or batch brief, candidate-bound observations, role results,
and current authority. The Orchestrator is the record writer unless an exact delegated method says
otherwise.

INDEX contains Goal, one Scope pointer and its read condition, Current, one bounded Next action and
owner, and verbatim active `STDO:` orders with source and lapse condition. Replace Current and Next
from the present state; move every unique removed fact to its owning ticket, review record, scope file,
or decision record. Do not turn INDEX into a history log.

Record routine verification at its owner with exact candidate, command or observer, concise result,
and limitation. Raw logs stay with their runs. Use a separate evidence file only for a costly,
external, manual, ephemeral, audit-required, or user-requested observation, following the assigned
method in `references/lane-authority.md`.

Stop if subject identity, observation ownership, or mutation authority is uncertain. The update is
complete when INDEX selects the next action and every retained fact has one durable owner.

## Batch review records

A batch review evaluates named claims on one integration candidate. Create
`reviews/<review-id>.md` from `templates/review/review.md`; the Orchestrator owns it. Inputs are the
feature boundary, included tickets and criterion IDs, relevant cutoff claims, interaction risks,
baseline, exact clean integration commit/tree, candidate-bound observations, and prior findings.

The record owns the batch's stable claim set, effective BLOCKED allowance and count, reviewed
candidates, final correction, findings, observations, and disposition. New batches default to one
reviewable BLOCKED allowance. Renaming or repackaging the same claims does not create another
allowance. An explicit historical or user-granted allowance wins over the default and stays recorded.

Stop before dispatch if the writer is active, the subject is dirty or mutable, the brief is ambiguous,
required observations lack owners, or the baseline is missing. A review entry is ready when one
acceptor can judge the bounded criteria without reconstructing scope from unrelated tickets or INDEX.
After the verdict, record whether it was reviewable, the count, candidate, findings, and next owner.
Approval establishes only the claims named in the brief; uncovered cutoff claims remain cutoff.

## Ticket handoff

Inputs are the ticket result, observations, findings, and any user-owned choice. The Orchestrator
records completed or blocked handoff when it occurs and continues feasible work under the confirmed
contract. In-contract corrections, finding disposition, and cutoff continue while independent tickets
run.

Put each user matter in the owning ticket with the affected scenario, impact, options, and
recommendation. At the batch boundary, present those decisions together and record the answers. Stop
when a decision blocks required behavior; keep the ticket pending with the concrete blocker. Handoff
is complete when required choices are settled and INDEX names the next bounded action and owner.

## Close

Normal closure requires an observation for every applicable acceptance criterion. Update the
checkboxes, record the final candidate and concise verification in Resolution, set `state: closed`,
and replace INDEX Current and Next. Abandoned or superseded work may retain unchecked criteria with
reasons. Preserve scenarios, alignment, decisions, findings, and cited observations.

Stop if any required criterion lacks a valid observation or unresolved work lacks a stated terminal
disposition. Closure is complete when ticket and INDEX agree and execution resources are retired or
have an owner and cleanup condition.

## Cutoff

Cutoff follows Collab's final correction after the recorded effective BLOCKED allowance is exhausted.
Inputs are the final clean commit/tree, passing required gates, Orchestrator judgement, prior verdicts,
and claims still awaiting independent confirmation.

Record claims established on the final candidate, final fixes, remaining findings and affected
scenarios, and unconfirmed claims. State that independent review ended before the final correction.
Set `state: cutoff` only when required gates pass and the Orchestrator can judge the bounded result.
Otherwise retain `pending` with the blocker and decision owner. Preserve the count and history; only a
new user grant adds review allowance.

A cutoff satisfies scheduling dependencies but carries its limitations downstream. It is complete
when Resolution and INDEX name those limitations and the next action.

## Archive

Archive only when the user completes or abandons the task. First reconcile unfinished work, surface
cutoff tickets and review records, preserve required evidence, and clean owned temporary resources.
Run `scripts/plan.py archive` only after INDEX and all owners state final disposition. Preserve
pre-existing user state.

A decision that must outlive the task becomes a tracked ADR only on user request. Archive is complete
when the full task record moved intact and every retained execution resource has an owner and cleanup
condition.
