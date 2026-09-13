# Planning operations

## Resume

Inputs are the task ID or lookup ID and the main checkout. Run `scripts/plan.py locate <task-id>`; for
an unknown ID, run `list` and use a returned `lookup_id`. Read the located INDEX, active Standing
orders, the Current/Next ticket or review brief, and pointers required by that action. The Orchestrator
is read-only until it identifies the bounded action, owner, checkout, and applicable authority.

Stop when Current or Next is insufficient and repair the record. Ask the user only when scope,
authority, or behavior belongs to them. Resume is complete when one bounded action and owner are known;
dependency analysis then belongs to batch selection.

## Plan

Inputs are the requested outcome, its observation, repository facts that affect scope, and current user
authority. The Orchestrator creates the task with `scripts/plan.py create`, records Goal, a single scope
pointer, Current, and Next, and preserves any existing Envelope pointers. Put confirmed scope in an
approved spec or `spec/` file, not INDEX. Read it before ticket planning, alignment, new-scope choices,
or review-driven design changes.

Design the smallest end-to-end increment that meets the request. Read codebase-design when deciding
module boundaries or public interfaces. Use to-spec for a frozen implementation contract and
to-tickets for explicit slicing when those producer steps are needed. Keep their tracked artifacts
under `spec/` and transcribe lifecycle pointers into this task.

Stop for unresolved deployment, compatibility, trust, authority, or public-behavior choices that can
change correctness or scope. Planning is complete when the next batch has bounded outcomes, known
dependencies, non-conflicting write scopes, observable acceptance, and named owners. Later uncertain
work stays drafted.

## Tickets

Create `tickets/<ticket-id>/ticket.md` from `templates/ticket/ticket.md`. Valid states are `drafted`,
`pending`, `cutoff`, and `closed`. The Orchestrator owns wording, dependencies, state, criteria,
checkboxes, Progress, User decisions, and Resolution. Delegated record writes require the exact method
from `references/lane-authority.md`.

Before `pending`, confirm the ticket against current code and instructions. Record:

- outcome, write scope, exclusions, dependencies, runtime assumptions, and decision boundaries;
- existing interface owners and authorized public changes;
- confirmed scenarios and an Alignment pointer;
- acceptance criteria naming the observation and its owner;
- required gates and their execution owner;
- an existing complete contract or Collab contract seed with exact interface, caller, test, and
  remaining implementation locations.

Tests and scenarios establish behavior. Direct review establishes responsibilities, interface
placement, prose, structure, configuration, and repository data. A cutoff dependency satisfies
scheduling but passes its unconfirmed claims and limitations downstream. An abandoned dependency
needs an identified replacement outcome.

Stop before implementation if material design is unconfirmed, a dependency is unresolved, public
interface ownership is missing, or the required observation has no owner. Ticket preparation is
complete when its contract is small, settled, and independently checkable.

## Parallel batches

Inputs are all drafted and pending dependency edges, module write scopes, shared interfaces, and the
settled tickets under consideration. Select the largest ready set that can finish independently. Put
interacting changes in explicit dependency order and materialize shared interface prerequisites first.

Present the batch relationships and align each ticket. Dispatch a ticket as soon as its contract,
formal tests or seed, isolated checkout, and environment are ready. While children run, prepare or
judge independent members. Collect accepted or cutoff work as it becomes ready; a blocked member does
not stop unrelated members.

INDEX names the active batch and next coordination action. Ticket files own their progress and
evidence. Stop when write scopes collide, dependencies are unclear, or a shared choice lacks user
confirmation. Selection is complete when each active member has one owner, one writer, a ready
contract, and an independent completion path.

## Design alignment

Inputs are current code, the approved scope, and the proposed ticket or batch. The Orchestrator shows:

- module responsibilities and callers;
- key data structures, owners, lifecycle, and role in the scenarios;
- concrete start, action, response, and responsible-module scenarios, including meaningful boundaries;
- deliberate exclusions such as compatibility, recovery, abstractions, and extension points.

For a batch, explain shared design once. Each ticket records its differences, scenarios, and the same
confirmation pointer. Tickets outside that discussion remain unconfirmed. The user decides public
behavior, responsibilities, data structures affecting correctness or maintenance cost, and scope.
Implementers retain local coding choices within the confirmed plan.

Stop while a material question remains. Alignment is complete only when the user confirms the resulting
proposal and each covered ticket records that confirmation in Scenarios, Alignment, and Acceptance.
