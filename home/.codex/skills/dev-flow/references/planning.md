# Planning operations

## Resume

Inputs are the task ID or lookup ID and the main checkout. Run `scripts/plan.py locate <task-id>`; for
an unknown ID, run `list` and use a returned `lookup_id`. Read the located INDEX, active Standing
orders, the Current/Next ticket or review brief, and pointers required by that action. The Orchestrator
is read-only until it identifies the bounded action, owner, checkout, and applicable authority.
`size_warnings` names an INDEX or ticket past the line limit; condense it under
[Maintain the record](records.md#maintain-the-record) at its next record update.

Preserve historical records and the contract of already dispatched attempts. An unknown historical
state is not acceptance under this workflow. Before resuming unfinished legacy work, record the
authorized transition to pending batch review and carry forward its unresolved claims and findings.
Ask its owner when the applicable contract or transition authority is unclear.

Stop when Current or Next is insufficient, or historical scope or authority cannot be recovered, and
repair the record. Ask the user only when the unresolved choice belongs to them. Resume is complete
when one bounded action and owner are known; dependency analysis then belongs to batch selection.

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

Create `tickets/<ticket-id>/ticket.md` from `../templates/ticket/ticket.md`. Valid states are `drafted`,
`pending` and `closed` for new work. The Orchestrator owns wording, dependencies, state, criteria,
checkboxes, Progress, User decisions, and Resolution. Delegated record writes require the exact method
from `lane-authority.md`.

Before `pending`, confirm the ticket against current code and instructions. Record:

- outcome, write scope, exclusions, dependencies, runtime assumptions, and decision boundaries;
- existing interface owners and authorized public changes;
- confirmed scenarios and an Alignment pointer;
- acceptance criteria naming the observation and its owner;
- applicable mechanical gates prepared under Collab's
  [Gate preparation](../../collab/references/execution.md#gate-preparation), or the reason none applies
  and the direct-review alternative;
- the owning review-batch pointer, with every acceptance criterion included;
- an existing complete contract or Collab contract seed with exact interface, caller, test, and
  remaining implementation locations.

Tests and scenarios establish behavior. Direct review establishes responsibilities, interface
placement, prose, structure, configuration, and repository data. Within the same review batch, a
collected pending dependency satisfies implementation scheduling only when its required ticket gates
passed and its contract is ready to consume. Record the consumed candidate and inherited unconfirmed
obligations in the dependent ticket; changed upstream work requires affected downstream verification.
Cross-batch dependencies require acceptance, or an explicit batch regrouping before consumption. An
abandoned dependency needs an identified replacement outcome.

Stop before implementation if material design is unconfirmed, a dependency is unresolved, public
interface ownership is missing, or the required observation has no owner. Ticket preparation is
complete when its contract is small, settled, and independently checkable.

## Parallel batches

Inputs are all drafted and pending dependency edges, module write scopes, shared interfaces, and the
settled tickets under consideration. Select the largest ready set that can finish independently. Put
interacting changes in explicit dependency order and materialize shared interface prerequisites first.

An execution batch is this ready parallel set. A review batch groups a coherent feature or contract
for independent acceptance and may span several execution batches, including dependency-ordered tickets.
A singleton is a review batch too. Choose its membership before implementation and create the brief
under [Batch review records](records.md#batch-review-records); fill its final subject and observations
when assembly is ready. Bound the set so one acceptor can judge all member criteria and interactions.

Present the batch relationships and align each ticket. Dispatch a ticket as soon as its contract,
formal tests or seed, prepared gates, isolated checkout, and environment are ready. While children run,
prepare or judge independent members. Collect gate-passing delivery candidates as they become ready;
keep them pending for batch acceptance. A blocked member does not stop unrelated implementation.
Before splitting a review batch, record dependency and criterion ownership so no outstanding obligation
is lost or treated as approved. Dispatch review only when the selected batch is complete and reviewable.

When selection creates a routing edge, INDEX names the active batch and next coordination outcome.
Ticket files own their semantic checkpoints and evidence. Stop when write scopes collide, dependencies
are unclear, or a shared choice lacks user confirmation. Selection is complete when each active member
has one owner, one writer, a ready contract, and an independent completion path.

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
