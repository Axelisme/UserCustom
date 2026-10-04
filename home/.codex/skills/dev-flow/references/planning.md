# Planning operations

## Resume

Run `scripts/plan.py locate <task-id>`; for an unknown ID, use `list` and its returned lookup_id.
Read INDEX Goal, board, and all active Standing orders, then the tracker Plan's `Next:` lines. Each
line names one action in flight or waiting, whom it waits on, and its owning ticket, question, or
decision.

For the selected line, read the ticket's Acceptance, Plan, and Notes. Observe the named checkout with
Git log/status and the collab status tool; past records are not current runtime state. Stop if the
checkout or executor state is uncertain. When a `Next:` line disagrees with Git or a decision, the
observed fact or the decision wins; repair the line.

Remain read-only until one bounded action, owner, checkout, and applicable authority are known.
If Plan cannot name it, repair Plan from known owners and observed Git/runtime facts, or ask for the
missing decision. Do not scan the task graph to infer state.
Open other contracts and source when that action needs them.

Before compaction or a session change, keep the `Next:` lines and Notes current; snapshot records
leave nothing else to save. A context transfer message, such as a runtime handoff tool's, gives the
INDEX path plus only what records cannot hold: an unverified hypothesis, interrupted reasoning, or
user dialogue not yet recorded, each labelled. It grants no authority and copies no record content.

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
criteria, checkboxes, Plan, and Notes. Fill the template's sections against current code and
instructions. A ticket is ready when its Mechanical gates list commands that run as written and, for
TDD, a formal test fails for the intended missing behavior. An unresolved user decision or an unknown
interface owner keeps it todo. Collab's [Prepare](../../collab/references/execution.md#prepare) sets up
the checkout and gates; a delegated ticket also needs its
[Delegate](../../collab/references/execution.md#delegate) brief.

Start after dependencies close (gates passed and collected). If a downstream needs an interface early,
give the interface a small prerequisite ticket. Before a ticket starts using a public interface from an unreviewed range of integration, run a
[range review](../../collab/references/review.md#range-review) covering that interface. An
integration ticket owns interaction scenarios and depends on the interacting tickets; defects become
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
