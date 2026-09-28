# Planning operations

## Resume

Run `scripts/plan.py locate <task-id>`; for an unknown ID, run `list` and use a returned `lookup_id`.
Locate regenerates the INDEX board. Read INDEX: Goal, the board, and every active Standing order.

On the board, the tickets in `doing`, `review`, and `blocked` are the work in flight, and `ready ▶`
marks tickets that can start. For each ticket in flight, read its `#acceptance`, `#plan`, and the
tail of `#log` in one `mdsec` call, and for a ticket in `review`, its latest `review-NN.md` and
verdict. When a Log line names a checkout, its `git log` and `git status` supply the commits since.
Open contracts, specs, and source when the action that uses them starts.

The Orchestrator stays read-only until it has one bounded action, its owner, its checkout, and the
applicable authority. When the board or a Log cannot say what a ticket is doing, repair that ticket's
record from its checkout and Git, or ask the user when the choice is theirs. Resume is complete when
one bounded action and owner are known.

## Plan

Inputs are the requested outcome, repository facts that affect scope, and current user authority.
Create the task with `scripts/plan.py create`, write Goal, and set `spec:` to the approved scope
file. Put confirmed scope in `spec/`, not INDEX. The task records only authority that differs from
the skill and repository defaults. Read the scope before ticket planning, alignment, new-scope
choices, or review-driven design changes.

Design the smallest end-to-end increment that meets the request. Read codebase-design when deciding
module boundaries or public interfaces. Use to-spec for a frozen implementation contract and
to-tickets for explicit slicing; keep their artifacts under `spec/`.

Stop for unresolved deployment, compatibility, trust, authority, or public-behavior choices that can
change correctness or scope. Planning is complete when the next tickets have bounded outcomes, known
dependencies, non-conflicting write scopes, observable acceptance, and named owners. Later uncertain
work stays `todo`.

## Tickets

Create `tickets/<ticket-id>/ticket.md` from `../templates/ticket/ticket.md`. The Orchestrator owns
its wording, dependencies, status, criteria, checkboxes, Plan, and Log.

Before `ready`, confirm the ticket against current code and instructions and record:

- outcome, write scope, exclusions, dependencies, runtime assumptions, and decision boundaries;
- existing interface owners and authorized public changes;
- confirmed scenarios and an Alignment pointer;
- acceptance criteria naming the observation and its owner;
- mechanical gates prepared under Collab's
  [Gate preparation](../../collab/references/execution.md#gate-preparation), or the reason none
  applies and the direct-review alternative;
- a complete existing contract or a Collab contract seed with exact interface, caller, test, and
  remaining implementation locations.

Tests and scenarios establish behavior. Direct review establishes responsibilities, interface
placement, prose, structure, configuration, and repository data.

A ticket starts from its dependencies once they are `closed`, which means accepted and collected.
When a downstream ticket needs an upstream interface early, give that interface its own small ticket
so it closes first. Interactions between tickets belong to an **integration ticket**: its acceptance
criteria are the interaction scenarios, its `depends_on` lists the interacting tickets, and it is
reviewed on integration after they close. A defect it finds becomes a new fix ticket.

Stop before implementation if material design is unconfirmed, public interface ownership is missing,
or a required observation has no owner. Ticket preparation is complete when its contract is small,
settled, and independently checkable.

## Parallel tickets

Select the largest set of `ready ▶` tickets whose write scopes do not collide, and materialize shared
interface prerequisites first. Present the tickets' relationships, align each one, and dispatch a
ticket as soon as its contract, seed, gates, checkout, and environment are ready. While children run,
prepare or judge other tickets. A blocked ticket does not stop unrelated work.

Stop when write scopes collide, dependencies are unclear, or a shared choice lacks user confirmation.
Selection is complete when each active ticket has one owner, one writer, a ready contract, and an
independent completion path.

## Design alignment

Inputs are current code, the approved scope, and the proposed ticket or tickets. The Orchestrator
shows:

- module responsibilities and callers;
- key data structures, owners, lifecycle, and role in the scenarios;
- concrete start, action, response, and responsible-module scenarios, including meaningful boundaries;
- deliberate exclusions such as compatibility, recovery, abstractions, and extension points.

For several tickets, explain shared design once. Each ticket records its differences, scenarios, and
the same confirmation pointer. The user decides public behavior, responsibilities, data structures
affecting correctness or maintenance cost, and scope. Implementers retain local coding choices within
the confirmed plan.

Stop while a material question remains. Alignment is complete only when the user confirms the resulting
proposal and each covered ticket records that confirmation in Scenarios, Alignment, and Acceptance.
