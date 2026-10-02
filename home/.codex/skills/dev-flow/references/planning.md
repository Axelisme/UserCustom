# Planning operations

## Resume

Run `scripts/plan.py locate <task-id>`; for an unknown ID, run `list` and use a returned `lookup_id`.
Locate regenerates the INDEX board. Read INDEX: Goal, the board, and every active Standing order.

The tracker heads the board; its latest line is the task's phase and whom it waits on. The tickets in
`doing`, `review`, and `blocked`, and the `todo` ticket the tracker names, are the work in flight, and
`ready ▶` marks tickets that can start. For each ticket in flight, read its `#acceptance` and `#plan`
in one `mdsec` call and the last lines of its Log with `tail -n 5 <ticket.md>`, and for a ticket in
`review`, its logged round identity and verdict if available. Use the logged child ID and the runtime's
run-control route to recover an active attempt; a separate brief file is not required. When a Log line
names a checkout, its `git log` and `git status` supply the commits since. Open contracts, specs, and
source when the action that uses them starts.

The Orchestrator stays read-only until it has one bounded action, its owner, its checkout, and the
applicable authority. When the board cannot name the next action, record the task's phase and whom
it waits on in the tracker's Log. When a Log cannot say what a ticket is doing, repair that ticket's
record from its checkout and Git, or ask the user when the choice is theirs. Resume is complete when
one bounded action and owner are known.

## Handoff

Use this operation before handing off Orchestrator context for compaction or a session transfer.
It prepares recovery through [Resume](#resume). Parent-to-child dispatch remains a complete bounded
assignment under Collab; a recovery entry is not a substitute for that assignment.

1. Update durable facts in their [owner records](records.md#maintain-the-record) before handoff.
   Record decisions, progress, blockers, and the next bounded action where they belong. Use
   `scripts/plan.py locate <task-id>` to refresh the INDEX board. Repair missing record state rather
   than making the handoff its only copy.
2. Give the minimal recovery entry: control root, task ID, and INDEX path. Add exact source
   paths/anchors only when needed for the next action and not already reachable through that entry.
   Refer to recorded goals, instructions, authority, decisions, progress, and evidence; leave their
   content in the owning sources. Avoid recreating the record's pointer graph in the message.
3. Carry only remaining working context that the sources cannot recover. Label an unverified
   hypothesis, interrupted reasoning, unrecorded dialogue, or transient operation detail explicitly;
   include its next observation or intended record when needed. Write `None` when there is no such
   context. For mutable Git or child state, give only needed lookup information not already recorded,
   and have the receiver reobserve it rather than trust a handoff snapshot.

If required record repair is blocked, identify the affected record and blocker. Preserve otherwise
lost input as explicitly unrecorded material, with its source or verbatim text. It grants no authority
to proceed; the receiver must restore the governing source before acting on it.

Handoff is complete when durable updates are recorded or their blocked repair is explicit, the entry
leads to the next bounded action, and the message contains no duplicate task recap. The receiver uses
Resume and reads governing originals before acting; a handoff neither replaces them nor changes
their authority.

## Plan

Inputs are the requested outcome, repository facts that affect scope, and current user authority.
Create the task with `scripts/plan.py create`, which adds the tracker and a draft `spec/scope.md`;
write Goal and the scope. Put confirmed scope in `spec/scope.md` and the user's answers in
`decisions/`, not INDEX. Create the task when the first investigation starts, with the tracker
reading `planning: investigating`; investigation output and inventories go to `research/`, rerunnable
scripts to `scripts/`, and a proposal awaiting the user's answer to `spec/`. The task records only
authority that differs from the skill and repository defaults. Read the scope before ticket
planning, alignment, new-scope choices, or review-driven design changes.

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

The **frontier** is the `ready ▶` tickets on the board; to-tickets shapes it through the slicing and
its blocking edges. Work the frontier: select the largest set of frontier tickets whose write scopes
do not collide, and materialize shared interface prerequisites first. Tickets whose write scopes
collide run in turn. Present the tickets' relationships, align each one, and dispatch a ticket as
soon as its contract, seed, gates, checkout, and environment are ready. While children run or a
review round is out, implement, prepare, or judge the next frontier ticket. A blocked ticket does not
stop unrelated work.

Stop when dependencies are unclear or a shared choice lacks user confirmation.
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
