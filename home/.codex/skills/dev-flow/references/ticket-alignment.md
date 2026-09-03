# Ticket alignment

Read this when a ticket starts, before placing or dispatching any writer for it.

Alignment is the Orchestrator showing the user, in the user's terms, what this one ticket is about
to build and what it rests on — then waiting. S0 fixed the whole task once; alignment fixes one
ticket against the tree as it stands now, because the earlier Slices have since changed that tree
and the user's world may have moved with it.

## When it runs

At the start of every ticket, including a ticket that has been `pending` since an earlier alignment.
Alignment is not `graduation`: graduation is the one-way `drafted` → `pending` transition, and a
ticket that graduated last month starts today against a different tree. A filled `## Alignment`
section records the last alignment; it is not a reason to skip this one, and it is rewritten rather
than appended to.

## World fact

A **world fact** is a fact about the user's situation outside the code — what already exists, what is
deployed, who uses it, what compatibility or retention is owed — that no frozen record states and
that reading the code cannot settle. The code can only show what it is prepared for, never whether
the thing it prepares for exists.

This is not the same as **operating assumptions**, which say what world the code runs in —
concurrency, caller trust, input provenance, adversary presence — and which the dispatch declares for
the reviewer to size a blocker against. Operating assumptions describe the runtime; world facts
describe the user's situation. A ticket can have a complete set of one and none of the other.

## The five steps

1. Name the Module seams this ticket creates, moves, or consumes, working from the frozen envelope,
   the S0 Design, and the ticket's Outcome.
2. Show the user each seam's minimal Interface, ownership and locality, invariants, errors and
   ordering, real adapters, and what stays private or does not cross.
3. Name the legacy seam or duplication this ticket removes when it closes. A pure scaffolding ticket
   names the usable tracer it serves instead.
4. List the **world facts this ticket rests on that no frozen record states**, each written as a
   question the user can answer yes or no. Beside them, list what this ticket will **not** do — the
   nearby work a reader could reasonably expect it to include and that it deliberately leaves out.
5. Wait for the user's explicit agreement or correction. Place no writer before it arrives.

Step 4 is where a ticket stops inheriting a fact nobody supplied. Its cost is bounded: it lists only
the facts *this* ticket rests on, not an inventory of the world.

## What lands in the ticket

The confirmed result of step 4, and only that, goes into the ticket's `## Alignment` section — the
world-fact list with each item marked confirmed or unconfirmed, and the non-goals list. Steps 1
through 3 are shown to the user and stay in the conversation; the seam facts they settle already have
an owner in the `## Seam contract`, and copying them would create a second authority for the same
fact.

Write conclusions there, not the reasoning that produced them.

## An unconfirmed fact does not stop the ticket

The user is not a bottleneck inside a ticket. A world fact the user has not confirmed stays listed as
unconfirmed and the ticket proceeds. You need not hold it back: the writer's own profile carries the
obligation to deliver the happy path and the functionality the ticket states and to reject every
other path explicitly, so nothing is inferred into existence to fill the gap, and the deferred paths
return to the user before the ticket is collected.

Inference is what this step exists to stop. A ticket that reasons its way to "the code reads a v1
file, so v1 files must exist" has answered a world fact by reading code, which is the one thing code
cannot answer.

## Inheriting an unverified base

A dependency that ended at `cutoff` satisfies this ticket's `depends_on` edge, but it stopped before
its remaining verification was bought. List its unproven claims among this ticket's world facts,
marked unconfirmed, naming the ticket they came from.

They qualify because they are exactly what step 4 exists to catch: reading the code cannot tell you
whether an unchecked claim holds, only what the code is prepared for. Left off the list, a cut-off
dependency reads to the next reader as a verified base, and the ticket built on it inherits a promise
no one ever made.

## Stop conditions

An absent, unfilled, or placeholder `## Alignment` section stops publication and dispatch. That
condition lives with every other one in
[ticket-seam-contract](ticket-seam-contract.md#publication-and-change-control), which owns the whole
stop list; this file adds no second list.
