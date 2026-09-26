# Record operations

## Maintain the record

Records live under `.agent_state/plans/<task-id>/` in the main checkout while code worktrees remain
separate. Inputs are the current ticket or batch brief, candidate-bound observations, role results,
and current authority. The Orchestrator is the record writer unless an exact delegated method says
otherwise.

Each fact has one **owner record**. Other records link to it.

| Fact | Owner record |
|---|---|
| Standing orders, the governing record, and its next bounded outcome | INDEX |
| Contract, dependencies, acceptance criteria, user decisions, semantic checkpoint, terminal disposition | Ticket |
| Claim set, criterion coverage, subject and round, candidate-bound observations, verdicts, findings, corrections, established criteria per ticket | Review record |
| Commit identity, diffs, and progress between phase boundaries | Git in the lane or integration |
| Command output and raw gate logs | The run or role result |
| Source inventories, caller surveys, and design analysis | The `spec/` or `research/` file the contract cites |
| Ticket lifecycle | Ticket `state` and acceptance checkboxes |
| Batch lifecycle | Review Findings status and `disposition` |
| Authority and its limits | The approved scope or the grant that confers it |

Write records at a **phase boundary**:

- a bounded outcome is set before its work starts;
- a delivery is collected, or a subject is frozen for review;
- a verdict returns;
- work hands off to another owner, or stops on a blocker, a user decision, or the end of the session;
- a ticket closes.

At each boundary, write every changed fact once, in its owner record.
Commits, gate runs, retries, and dispatches between boundaries stay with Git, the run, and role
results. Write record prose as facts that hold now, each sentence carrying a fact that the record's
fields and linked owners lack.

INDEX has two jobs. It carries verbatim active `STDO:` orders with source and lapse condition, and it
routes a newly arriving Orchestrator through Goal, one Scope pointer and read condition, Current, and
Next. Current names the **governing record**: the ticket or review record that owns the active work's
state. Next names the bounded outcome that record drives toward and its owner. A **routing edge**
occurs when the governing record, that outcome, or a blocker awaiting the user changes. Update Current
and Next at that edge. Candidates, review rounds, and turns between writer and acceptor belong to the
governing record. Update Standing orders under [custody](custody.md), independently of routing edges.

A **history file** holds superseded record content: `history.md` beside a ticket, and
`<review-id>.history.md` beside a review record. Append to it. It sits outside the resume path and
outside dispatches; read it only to trace a specific candidate, finding, or decision to its source.
Resume, dispatch, and wake-up reads pay for INDEX, tickets, and review records by the byte, so
`plan.py locate` reports each one past its byte budget in `size_warnings`. Condense a warned record by
moving superseded content to its history file.

Prepare a ticket's contract fields before `pending`. After work starts, change them only when current
authority changes approved scope, behavior, acceptance, dependency, or a decision boundary. Amend the
affected contract text in place and move the superseded wording, with its authority pointer, to the
ticket's history file. Keep implementation results out of the contract. Change an acceptance checkbox
only when its assigned stable observation supports the conclusion.

A ticket's **semantic checkpoint** is the resume point that Git and the review record cannot supply:
the checkout and branch, the bounded outcome in progress, the obligations left, and any blocker. Git in
that checkout supplies commit identity and progress since the checkpoint. Replace the checkpoint in
Progress when a phase boundary changes one of those facts. A bounded outcome that needs its own
contract gets one under Progress, apart from the ticket's stable contract; when the next bounded
outcome starts, move the finished one to the ticket's history file. Name a consumed pending dependency
candidate by its exact commit.

Each review finding gets one Findings row with the affected criterion, status, and resolving candidate;
those rows and the current round govern fixed-subject acceptance. When a delivery is collected, add its
gate results to Candidate-bound observations: exact candidate, command or observer, concise result, run
pointer, and limitation. Use a separate evidence file only for a costly, external, manual, ephemeral,
audit-required, or user-requested observation, following `lane-authority.md`. When a new round starts,
move the ended round's candidate, observations, and verdict narrative to the review's history file and
keep its findings in the table.

Stop if routing, subject identity, observation ownership, or mutation authority is uncertain. The
update is complete when each changed fact sits once in its owner record and Current, Next, and the
semantic checkpoint route a newly arriving Orchestrator.

## Batch review records

A batch review evaluates named claims on one integration candidate. Create
`reviews/<review-id>.md` from `../templates/review/review.md`; the Orchestrator owns it. Inputs are the
feature boundary, included tickets and all their criterion IDs, interaction risks, baseline,
candidate-bound observations, and prior findings. Create the membership and coverage map during
planning; record the exact clean assembled commit/tree in Current round before dispatch. Each
criterion names its observation method and owner. Batch-only interaction scenarios have their own IDs
and observations.

Membership changes preserve criterion and finding ownership; record exclusions without dropping a
member's acceptance obligations.

Stop before dispatch if the writer is active, the subject is dirty or mutable, the brief is ambiguous,
required observations lack owners, or the baseline is missing. A review entry is ready when one
acceptor can judge the bounded criteria without reconstructing scope from unrelated tickets or INDEX.
After the verdict, update Current round with whether it was reviewable, the candidate, and the next
owner, and add or update Findings rows with affected criterion and ticket IDs. Use Collab's correction
procedure for BLOCKED results. Approval establishes only the claims named in the brief on the reviewed
subject; other work retains its disposition. Record each member's established criteria and accepted
candidate in Ticket dispositions. A batch remains pending until all its assigned claims are
established.

## Ticket handoff

Inputs are the ticket result, observations, findings, and any user-owned choice. The Orchestrator
replaces the ticket's semantic checkpoint when a completed or blocked handoff changes its resume point,
then continues feasible work under the confirmed contract. In-contract corrections, finding
disposition, and verification continue while independent tickets run.

Put each user matter in the owning ticket with the affected scenario, impact, options, and
recommendation. At the batch boundary, present those decisions together and record the answers. Stop
when a decision blocks required behavior; record the concrete blocker in the semantic checkpoint.
Handoff is complete when required choices are settled and the ticket names the next owner.

## Close

Normal closure requires valid observations for every applicable acceptance criterion and batch
acceptance covering those criteria on the final candidate. Update the checkboxes, record the accepted
candidate and a link to the owning review record in Resolution, and set `state: closed`. Abandoned or
superseded work may retain unchecked criteria with reasons. Preserve scenarios, alignment, decisions,
findings, and cited observations.

Stop if any required criterion lacks a valid observation or unresolved work lacks a stated terminal
disposition. Closure is complete when the ticket and any changed INDEX route agree and execution
resources are retired or have an owner and cleanup condition.

## Archive

Archive only when the user completes or abandons the task. First reconcile unfinished work, surface
unresolved tickets and review records, preserve required evidence, and clean owned temporary resources.
Preserve legacy dispositions as history; archival does not turn them into accepted work.
Update INDEX's routing fields for the final routing edge, then run `scripts/plan.py archive` only after
all owners state final disposition. Preserve pre-existing user state.

A decision that must outlive the task becomes a tracked ADR only on user request. Archive is complete
when the full task record moved intact and every retained execution resource has an owner and cleanup
condition.
