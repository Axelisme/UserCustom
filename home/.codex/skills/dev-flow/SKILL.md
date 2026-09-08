---
name: dev-flow
description: "Orchestrator task records: always use with collab to plan, resume, hand off, close, or archive a task."
---

# Dev-flow

Always read this Orchestrator entry with [collab](../collab/SKILL.md), which owns assignment, review,
and Git operations. Every task has a container; every bounded implementation has a ticket, including
work completed directly by the Orchestrator. Implementers and reviewers enter through their profiles,
dispatch, and assigned ticket.

## Resume

Run this skill's `scripts/plan.py locate <task-id>` from the main checkout. For an unknown ID, run
`list` and use a returned `lookup_id`. Read the located INDEX, all its active Standing orders, the
handed-off ticket, and the pointers needed for the current action.

INDEX selects work; `locate` supplies its address. Repair an insufficient Current or Next, involving
the user when the decision is theirs. Resume when the bounded action, owner, and relevant ticket are
known. Dependency analysis belongs to batch planning after that action has been selected.

## Plan

Create a task with this skill's `scripts/plan.py create` and fill INDEX's Goal, Scope pointer, Current,
and Next. `scripts/plan.py --help` owns arguments. Record the user-visible outcome and its observation;
confirm facts about deployment, compatibility, trust, or usage when they affect correctness or scope.

Keep the confirmed task scope outside INDEX. Use its approved spec as the owner, or create a scope
file under `spec/` when needed. Read that source before ticket planning/alignment, new-scope decisions,
or review-driven design changes. Apply [custody](references/custody.md) before changing its boundary.
Translate task scope into explicit ticket work and exclusions for the implementer.

Design the smallest end-to-end change and reuse dependencies that meet the need. Read
[codebase-design](../codebase-design/SKILL.md) when deciding module boundaries or public interfaces;
place non-obvious interface obligations at the owning module. Split work into usable increments,
each with an outcome or a pointer to the ticket completing its partial increment.

Use **to-spec** for a frozen implementation contract and **to-tickets** for explicit slicing and
dependency planning. Keep producer artifacts under `spec/`, link lifecycle tickets to them, and map
`Blocked by:` to `depends_on`. When an external tracker is explicitly in use, link its artifacts.

Planning is complete when the next batch's tickets have bounded outcomes, known dependencies,
module-level write scopes, and checkable acceptance criteria. Uncertain later work stays drafted.

## Tickets

Copy `templates/ticket/ticket.md` to `tickets/<ticket-id>/ticket.md`; frontmatter ID matches the
directory. Keep the state vocabulary understood by `plan.py`:

- `drafted`: requirements or prerequisites are being resolved.
- `pending`: the contract is ready; includes implementation and blocked work.
- `closed`: completed, abandoned, rejected, or superseded, as recorded in Resolution.
- `cutoff`: the review cap and final correction are complete, gates pass, and further independent
  review is left to the user's choice.

Before `pending`, check the contract against current code and instructions. Before implementation,
complete this ticket's [design alignment](#design-alignment). A ready ticket has:

- Outcome, module write scope, exclusions, dependencies, and relevant runtime assumptions.
- Existing interface owners and authorized public changes. Use collab's
  [contract seed](../collab/SKILL.md#contract-seed) for new or changed interfaces and record its exact
  locations and remaining implementation steps in Contract starting point.
- Acceptance covering every agreed behavior, responsibility allocation, and public interface choice.
  Each criterion names its observation and responsible check or person; related decisions may share
  a criterion. Tests or scenarios establish behavior. Direct review establishes responsibilities,
  interface placement, prose, structure, configuration, and repository data.
- Required checks referencing repository-owned commands, with completion based on actual candidate
  observations. Apply collab's [test ownership](../collab/SKILL.md#test-ownership).

The Orchestrator owns ticket wording, checkboxes, dependencies, state, Resolution, and INDEX. Read
[record permissions](references/lane-authority.md) before delegating record writes. ADR edits require
explicit user authority. Implementers receive a complete small assignment with local coding freedom.

A cutoff satisfies scheduling dependencies. Carry its outstanding findings and unverified claims
into the dependent ticket's assumptions. If an observed defect blocks a required downstream behavior,
record the affected path for user decision at handoff while independent work proceeds. Abandoned or
superseded dependencies need an identified replacement outcome.

Preserve existing tickets and approved obligations. Recover retired reference versions from the task's
recorded commit or repository history when resuming an old ticket. Ask before replacing those
obligations; report missing authority when its source cannot be recovered.

## Parallel batches

Check dependency paths through the whole ticket graph, including drafted tickets, plus module edits
and shared interfaces. Select the largest ready set that can complete independently under settled
contracts. Put interacting changes in explicit dependency order.

Present the batch's relationships and complete [design alignment](#design-alignment) for each ticket.
Materialize shared interface prerequisites first. Prepare each ticket's seed, formal tests, and
isolated worktree, then dispatch as soon as that ticket is ready. Prepare the next independent ticket
while dispatched work runs.

Interleave preparation, results, corrections, review, and integration. Integrate completed or cutoff
tickets as ready, checking interactions with current integration. A blocked member records its stop
while independent members continue. INDEX names the active batch and next coordination action;
individual progress and evidence stay in each ticket. Each child receives its own bounded assignment.

## Design alignment

Before every ticket starts, show its design against current code and obtain the user's confirmation.
Discuss a parallel batch together, giving each ticket its own proposal:

- Module responsibilities and callers, with a small diagram when useful.
- The few key data structures: contents, owner, lifecycle, and role in the scenarios.
- Concrete scenarios: starting situation, user action, system response, and responsible modules.
  Include observed or requirement-backed failures and boundaries when they affect design choices.
- Deliberate exclusions, including abstractions, extension points, compatibility, and recovery work.

Expose choices and consequences. Invite challenges to assumptions, responsibilities, behavior, and
complexity; revise the proposal and scenarios with the user. Start after they confirm the resulting
design. Non-code tickets use the corresponding owners, scenarios, and exclusions.

Record each agreed fact in its owning ticket section, including Scenarios and Acceptance. Alignment
holds the user's confirmation pointer. This step is complete when material questions are resolved,
the user has confirmed the proposal, and the ticket reflects it.

Continue implementation and corrections autonomously within that design. Collect proposed changes
for [ticket handoff](#ticket-handoff); implement a changed design after user confirmation.

## Ticket handoff

Record each ticket's completion or blocked handoff when it occurs. Concentrate user decisions at
batch handoff, after feasible batch work and before the next batch's alignment. The Orchestrator
handles in-contract corrections, finding disposition, and cutoff while independent tickets continue.

Collect user matters in each ticket's User decisions: affected scenario, impact, options, and
recommendation. Distinguish deferred proposals from current acceptance defects. Continue feasible
authorized work. If a decision blocks required behavior, retain pending state with its concrete
blocker and preserve state and evidence at the authority boundary.

At batch handoff, present decisions together and record the user's answers at their owning locations.
Then align the next batch. INDEX points to the handoff when user input is next. Handoff is complete
when required decisions are settled and the next bounded action and owner are recorded.

## Maintain the record

Records live under `.agent_state/plans/<task-id>/` in the main checkout. This gitignored directory
stays there while code worktrees operate separately. `templates/` owns scaffolding; explicit `--repo`
sets the control directory, otherwise `plan.py` discovers the current Git root.

INDEX contains:

- `Goal`: a short user-visible outcome.
- `Scope`: the approved source pointer and its read condition: planning/alignment, a new-scope
  decision, or a review-driven design change. Preserve existing `Envelope` pointers and their owners.
- `Current`: active batch ticket pointers, current status, and unresolved judgement. Include a scope
  issue while it blocks the next action; move its resolution to its owner once settled.
- `Next`: one bounded coordination action and owner, or `None` when no action remains.
- `Standing orders`: full verbatim active user-marked `STDO:` orders, read on every reorientation.
  Use [custody](references/custody.md) for admission, application, changes, and retirement.

Replace Current and Next from the present situation, preserving each unique removed fact at its
owner. Keep approved grants verbatim. Session task lists project this record. A handoff names factual
owners and next actions; tickets retain their contracts, progress, and Resolution.

Keep ticket evidence beside its ticket; task-wide specs, research, decisions, and scripts use their
corresponding directories. Preserve durable validation for costly, external, manual, or audit-required
observations. Use `templates/ticket/evidence.md`: exact commit/tree, covered claims, operator, time and
environment, method, expected/actual observations, limitations, and cleanup. Referenced record scripts
include path and SHA-256. Routine outputs remain with their runs. Revalidate changed candidates.

## Close and archive

For normal closure, establish every applicable acceptance criterion from its evidence. Update the
checklist, write Resolution, set terminal state, then replace INDEX's Current and Next. Abandoned or
superseded work may retain unchecked criteria with reasons. A review-capped ticket follows
[cutoff](#cutoff). Closure is complete when the ticket and INDEX agree.

Preserve complete ticket context through closure and archive: scenarios, recorded design discussion,
decisions, findings, and evidence stay in their owning files. Resolution states the final disposition
and points to its basis. Read historical tickets on demand; INDEX stays focused on current work.

Clean implementation-time temporary files, processes, probes, and worktrees whose integration and
evidence preservation are complete. Retained temporary resources have an owner and cleanup condition.
Preserve pre-existing user state. Capture evidence-backed out-of-scope opportunities through
candidate-backlog admission; current acceptance gaps stay with the task and its recorded disposition.

## Cutoff

After collab's [review cap and final correction](../collab/SKILL.md#correct-and-decide), record the
final clean commit/tree and set `state: cutoff` once required gates and Orchestrator judgement are
complete. Resolution separates:

- Claims established for the final candidate, with observations and owners.
- Final fixes, remaining findings and affected scenarios, and claims awaiting independent confirmation.
  State that independent review ended before the final correction.

Update INDEX and proceed with downstream work under the recorded limitations. The user triggers
revisiting cutoff findings against the integrated result at that time. Preserve cutoff status and
evidence until then. A new review allowance records the user's decision and retains prior counts
and dispositions as history.

## Archive

When the user completes or abandons the task, reconcile unfinished work and surface cutoff tickets.
Move the complete record into archive with ticket contents and verification status intact. A decision
that must outlive the task may become a self-contained repository ADR through **domain-modeling** when
the user requests it. Its readers obtain the decision entirely from tracked repository material.
