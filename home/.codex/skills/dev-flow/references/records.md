# Record operations

## Maintain the record

Records live under `.agent_state/plans/<task-id>/` in the main checkout while code worktrees remain
separate. Inputs are the current ticket or batch brief, candidate-bound observations, role results,
and current authority. The Orchestrator is the record writer unless an exact delegated method says
otherwise.

INDEX has two jobs. It carries verbatim active `STDO:` orders with source and lapse condition, and it
routes a newly arriving Orchestrator through Goal, one Scope pointer and read condition, Current, and
one bounded Next outcome with its owner. Its routing tuple is the active record, bounded outcome,
owner, blocker, and lifecycle state. A **routing edge** occurs when that tuple changes. Update INDEX at
that edge. Ordinary reads, edits, commands, dispatch, review progress, correction, collection, and
landing leave it unchanged while the tuple stays the same.

A ticket owns its stable contract, dependencies, acceptance criteria, user decisions, current
resumable state, and terminal disposition. Prepare contract fields before `pending`. After work starts,
change them only when current authority changes approved scope, behavior, acceptance, dependency, or a
decision boundary. Keep implementation results out of the contract. Change an acceptance checkbox only
when its assigned stable observation supports the conclusion.

A ticket's **semantic checkpoint** is the smallest current statement that changes how the next owner
resumes, verifies, or decides. Replace Progress when a stable candidate, gate conclusion, reviewable
verdict, blocker, or handoff creates a new checkpoint. Keep file reads, ordinary edits, transient
commands, retries, child events, and raw logs with Git, the tool, or the role result.

Use this update gate before changing a durable record: would the fact change how a newly arriving
authorized owner resumes, verifies, decides, or establishes terminal disposition? If not, leave it at
its fine-grained owner. Record routine verification with exact candidate, command or observer, concise
result, and limitation in the ticket or review record that owns the claim. Raw logs stay with their
runs. Use a separate evidence file only for a costly, external, manual, ephemeral, audit-required, or
user-requested observation, following `lane-authority.md`.

A review record may retain each reviewable candidate, effective verdict count, findings, and correction
disposition because those facts govern fixed-subject allowance and acceptance. This bounded review
history is not a general operation log.

Stop if routing, subject identity, observation ownership, or mutation authority is uncertain. The
update is complete when the current routing edge and semantic checkpoint are sufficient and every
retained fact has one durable owner.

## Batch review records

A batch review evaluates named claims on one integration candidate. Create
`reviews/<review-id>.md` from `../templates/review/review.md`; the Orchestrator owns it. Inputs are the
feature boundary, included tickets and criterion IDs, relevant cutoff claims, interaction risks,
baseline, exact clean integration commit/tree, candidate-bound observations, and prior findings.

The record owns the batch's stable claim set, effective BLOCKED allowance and count, reviewed
candidates, final correction, findings, observations, and disposition. New batches default to one
reviewable BLOCKED allowance. Renaming or repackaging the same claims does not create another
allowance. An explicit historical or user-granted allowance wins over the default and stays recorded.

Stop before dispatch if the writer is active, the subject is dirty or mutable, the brief is ambiguous,
required observations lack owners, or the baseline is missing. A review entry is ready when one
acceptor can judge the bounded criteria without reconstructing scope from unrelated tickets or INDEX.
After the verdict, record whether it was reviewable, the count, candidate, findings, and next owner as
bounded review history. Approval establishes only the claims named in the brief; uncovered cutoff
claims remain cutoff.

## Ticket handoff

Inputs are the ticket result, observations, findings, and any user-owned choice. The Orchestrator
replaces the ticket's semantic checkpoint when a completed or blocked handoff changes how work resumes,
then continues feasible work under the confirmed contract. In-contract corrections, finding
disposition, and cutoff continue while independent tickets run.

Put each user matter in the owning ticket with the affected scenario, impact, options, and
recommendation. At the batch boundary, present those decisions together and record the answers. Stop
when a decision blocks required behavior; keep the ticket pending with the concrete blocker. Handoff
is complete when required choices are settled and the ticket names the next owner. Update INDEX only
when the handoff creates a routing edge.

## Close

Normal closure requires an observation for every applicable acceptance criterion. Update the
checkboxes, record the final candidate and concise verification in Resolution, and set `state: closed`.
Update INDEX when that lifecycle change creates a routing edge. Abandoned or superseded work may retain
unchecked criteria with reasons. Preserve scenarios, alignment, decisions, findings, and cited
observations.

Stop if any required criterion lacks a valid observation or unresolved work lacks a stated terminal
disposition. Closure is complete when the ticket and any changed INDEX route agree and execution
resources are retired or have an owner and cleanup condition.

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
when Resolution names those limitations and the next owner. Update INDEX only if cutoff creates a
routing edge.

## Archive

Archive only when the user completes or abandons the task. First reconcile unfinished work, surface
cutoff tickets and review records, preserve required evidence, and clean owned temporary resources.
Update INDEX for the final routing edge, then run `scripts/plan.py archive` only after all owners state
final disposition. Preserve pre-existing user state.

A decision that must outlive the task becomes a tracked ADR only on user request. Archive is complete
when the full task record moved intact and every retained execution resource has an owner and cleanup
condition.
