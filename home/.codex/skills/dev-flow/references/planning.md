# Planning operations

## Resume

Run `scripts/plan.py locate <task-id>`; for an unknown ID, use `list` and its returned lookup_id.
Read INDEX Goal, board, and all active Standing orders. Tracker Plan names task-level unfinished
work and waiting conditions. If it disagrees with a question or decision, read that original and
repair Plan. An unchecked item does not prove an answer is missing; an answer does not prove work resumed.

Follow Plan to the relevant todo ticket and the doing, review, or blocked work in flight. Read the
selected ticket's Acceptance and Plan, then the corresponding dispatch/round in Log and its verdict
when available. Follow exact history pointers when an identity moved there. Verify the child by
its ID through runtime run-control; observe the named checkout with Git log/status. Past events
are not current runtime state. Stop if correspondence or executor state is uncertain.

Remain read-only until one bounded action, owner, checkout, and applicable authority are known.
If INDEX and Plan cannot name it, repair Plan from known owners and observed Git/runtime facts,
or ask for the missing decision. Do not scan the task graph or infer state from the latest Log line.
Open other contracts and source when that action needs them.

## Handoff

Before compaction or session transfer, compare needed facts with their
[owners](records.md#maintain-the-record). Repair missing authority, decisions, execution identities,
blockers, or acceptance results. If facts are already saved and unchanged, make no task changes.
Refresh the board only when changed frontmatter requires it.

Give control root, task ID, and INDEX path. Add exact source pointers only when needed for the next
action and not reachable from that entry. Leave durable content in its owners rather than copying
a task recap or pointer graph. Carry only otherwise unrecoverable working context, labelled as
hypothesis, interrupted reasoning, unrecorded dialogue, or transient detail; use None if absent.
Mutable Git/child facts need lookup information and reobservation, not a trusted snapshot.

If repair is blocked, name its record and blocker, and preserve otherwise lost input explicitly as
unrecorded material with source or verbatim text. It grants no authority. Handoff is complete when
the entry leads to the next bounded action and durable repairs are saved or explicitly blocked.
The receiver uses Resume and governing originals; child dispatch still needs its complete assignment.

## Plan

Inputs are the request, repository facts, current scope if any, and mutation authority. Apply
[Document authority](records.md#document-authority) to the proposed work or revision before choosing
its execution path. Resolve any required user decision here; unresolved scope or authority blocks
the affected work rather than being delegated to its implementer.

At the first investigation, use `scripts/plan.py create` for tracker and draft scope. Write Goal
and scope; tracker Plan points to the unfinished question or deliverable. Record only authority
that differs from skill/repository defaults. Assigned research and proposals use the record owners.

Design the smallest end-to-end increment. Use codebase-design for module/interface choices,
to-spec for the specification, and to-tickets for slicing; their artifacts stay under spec.
Their confirmation steps use the shared authority classification, not a second approval policy.
Read current scope for planning, alignment, or scope/design revisions; prepare the next tickets below.
Planning finishes with bounded outcomes, known dependencies, non-conflicting write scopes,
observable acceptance, and named owners. Later uncertain work stays todo.

## Tickets

Use `../templates/ticket/ticket.md`. The Orchestrator owns its contract, dependencies, status,
criteria, checkboxes, Plan, and Log. Before ready, check current code and instructions and supply:

- outcome, write scope, exclusions, dependencies, runtime assumptions, and decision boundaries;
- existing interface owners and authorized public changes;
- scenarios and an Alignment pointer;
- criteria with observation and execution owners;
- a complete existing contract or exact seed/interface/caller/test locations and remaining work;
- executable gates or a justified direct-review alternative.

Prepare the checkout, contract, and observations through Collab's
[preparation sequence](../../collab/references/execution.md#prepare). Missing interface ownership,
unresolved decisions from Plan, or observations without owners stop implementation. Preparation ends
with a settled, independently checkable contract, seed, and gates; then mark ready.

Start after dependencies close (accepted and collected). If a downstream needs an interface early,
give the interface a small prerequisite ticket. An integration ticket owns interaction scenarios,
depends on the interacting tickets, and is reviewed on integration after they close; defects become
fix tickets.

## Parallel tickets

Select the largest set of `ready ▶` tickets with non-colliding write scopes. Materialize shared
interface prerequisites first; colliding writers run in turn. Explain shared relationships once
under Design alignment and start each ticket when its preparation is complete. Unclear dependencies
stop the affected selection; changes to the plan reenter Plan rather than introducing local approval.

Each active ticket must have one owner, writer, ready contract, and independent completion path.
While children or reviews run, prepare, implement, or judge independent work. A blocked ticket
does not stop the rest; return control when no independent action remains rather than polling.

## Design alignment

From current code and the specification, state module responsibilities/callers, key data structures
and owners, lifecycle, concrete start/action/response scenarios, and deliberate exclusions such as
compatibility, recovery, or extension points. Explain shared design once; tickets keep their
differences and governing contract/decision pointer.

For decisions identified in Plan, present these facts to the user. Otherwise record alignment and
continue within assigned authority. Finish when Scenarios, Alignment, and Acceptance identify the
contract and any decision governing a changed commitment. Implementers keep their local coding choices.
