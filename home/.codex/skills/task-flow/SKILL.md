---
name: task-flow
description: "Task delivery from spec to landing: plan a task into a spec and tickets, run the ticket frontier in parallel lanes, review once, land. Use when starting a task, or resuming or landing one whose directory under .agent_state/plans/ has spec.md at its root."
---

# Task flow

A **task** delivers one spec on one integration branch. You are the Orchestrator: you plan, dispatch
implementers, collect their lanes, and land. Task records are **read** material. Each record has
one write moment, named below, and nothing else writes it.

## The task directory

A task lives at `.agent_state/plans/<task-id>/` in the main checkout (the parent of
`git rev-parse --git-common-dir`), never inside a worktree.

| Path | Holds | Written when |
|---|---|---|
| `INDEX.md` | `## Goal` and `## Standing orders`, nothing else | See [Writes](#writes) |
| `spec.md` | The current target design: the to-spec entry file | Planning; later only with user approval |
| `spec/<topic>.md` | Spec detail that only some tickets need, behind a conditional pointer in `spec.md` | Same as `spec.md` |
| `decisions/NNNN-<slug>.md` | One user ruling on the target design: the reason behind spec text; absent in a [mapped task](#mapped-tasks) | The user answers a design question |
| `tickets/NN-<slug>.md` | One tracer-bullet ticket in the to-tickets local template | Planning; later only with user approval, except `Status:` |
| `retired/` | Superseded standing orders and decisions | When a later ruling replaces them |
| `scratch/` | Exploration notes, gate logs, bulky output | Any time; the one free-write area |

The structure is closed: no other files, no extra INDEX sections, no ticket sections beyond the
to-tickets template. A fact that has no home here belongs in code, Git, or `scratch/`.
`python3 <skill-dir>/scripts/check.py <task-dir>` reports structure violations and prints the
frontier.

**Standing orders** say how this task is run (process). **Decisions** say what is built (target
design). Classify a new user ruling by that line before writing it.

Read rules:

- On entry, read `INDEX.md` whole. Open spec, decisions, and tickets when the action needs them.
- `spec.md` is the current design; implementers read it and never need a decision. Read a
  decision only when changing the design area it governs.
- Read `retired/` only during the [ADR discussion](#close).
- Read a `scratch/` file only when a dispatch or the user names it.

## Writes

Each write replaces or adds a whole entry. Records never accumulate appended history.

- **Goal**: only when the user redefines the outcome.
- **Standing orders**: only when the current user message carries a `STDO:` marker. Copy the marked
  text verbatim into INDEX with its date. A new order may replace an old one or add beside it; move a
  replaced order to `retired/` with the replacing message quoted. When the message accepts suggested
  grants by reference ("STDO: 1 and 3"), record each referenced suggestion in full beside the user's
  words. Show the recorded entry in the same reply so the user can correct it.
- **Spec and ticket content**: only after the user approves the change, or, in a mapped task, to
  match an advisor ruling. Changes that alter behaviour
  or scope come back to the user; implementation detail lives in code and never enters the spec.
  Keep `spec.md` an entry file: move detail only some readers need into `spec/<topic>.md`, pointed
  to by a condition ("when you need X, read `spec/x.md`").
- **Decisions**: when the user answers a design question. Ask in the reply with scenario, options,
  and a recommendation. The file starts with `Supersedes: <numbers>` or `Supersedes: none`, then
  holds the question as asked, the adopted option in full, and the answer verbatim in 「」; a
  rejected option keeps one line with its reason. In the same write, update the spec text the
  decision changes and move every superseded decision to `retired/`.
- **Ticket `Status:`**: the Orchestrator alone sets `ready` → `doing` once the dispatch succeeds and
  `doing` → `done` at collection. A ticket the user drops moves to `retired/`.
- **Scratch**: one file per purpose, overwritten in place; no versioned copies, no checkout copies.
  A ticket's files go under `scratch/<ticket>/`, deleted when the ticket is collected.

Handoff is written only when the user asks, with the handoff skill, outside the task directory.

## Resume

After compaction or a session change:

1. Read `INDEX.md` whole and run `check.py` for the frontier and the `doing` tickets.
2. Each `doing` ticket's lane is `wave/<task-id>/<ticket-stem>`, for example
   `wave/calc-ops/02-multiply`. Observe the lane and the live children with the runtime's status
   operations ([runtime.md](runtime.md)). A lane on a detached HEAD goes back to its branch first. A
   live child keeps working; wait for it. With no live child, inspect the lane: a **finished
   candidate** (clean tree, an implementation commit, and for a behaviour ticket a separate test
   commit before it) goes to the [gates](#gates); anything else gets a fresh dispatch on the same
   lane.
3. In a mapped task, re-send every question still in `scratch/questions/`.

Then continue the frontier.

## Plan

1. Create the task directory with `INDEX.md` holding the Goal.
2. Run to-spec, then to-tickets, publishing into this task directory instead of `.scratch/`. Their
   confirmation steps (seams, ticket breakdown) are the user approval of spec and tickets. Each
   ticket gets `**Status:** ready`.
3. Create the integration branch from the user's target branch, or from the base task's integration
   for a [stacked task](#stacked-tasks); read [runtime.md](runtime.md) for the operations.

Planning is done when INDEX points to an approved spec and tickets whose blocking edges the user
confirmed.

## Run the frontier

The **frontier** is every `ready` ticket whose blockers are all `done`.

1. For each frontier ticket, create a lane from integration named after the ticket file stem
   (`02-multiply`) and dispatch a `task-implementer` in the background. The dispatch carries pointers, not copies: task path, ticket path, lane path, the
   gate commands, and `scratch/<ticket>/` for logs.
2. Continue independent work while lanes run. When nothing independent remains, end the turn.
3. On a COMPLETED result, run the [gates](#gates) yourself on the lane. Pass: collect the lane into
   integration, set `done`, and delete `scratch/<ticket>/`. Fail: send the failure back through a
   fresh dispatch on the same lane. On BLOCKED, settle the blocker as a question, then dispatch fresh
   on the same lane.
4. A collected ticket can widen the frontier; dispatch the newly unblocked tickets.

An implementer question about scope or behaviour becomes a user question (an advisor question in a
mapped task); once it is settled, update the spec, then reply to the implementer.

A settled change that touches a `doing` ticket interrupts it rather than waiting: update the ticket,
then steer its implementer to the updated ticket (runtime steer). When the change makes the ticket
obsolete, terminate the implementer, drop the lane, and move the ticket to `retired/`.

## Gates

Every ticket runs the repository's declared checks (test, lint, typecheck, as AGENTS.md or
CLAUDE.md states) plus any check its acceptance criteria name. Logs go to `scratch/`; results are
read from exit status, not recorded.

**Red-green proof.** A ticket that adds or changes behaviour delivers its new tests in their own
commit before the implementation commit. Before collecting, check out that test commit in the lane
(`git checkout --detach <test-commit>`) and run the new tests. Each must fail because what the ticket
adds is still missing: a failed assertion, or a missing function or attribute the ticket introduces.
A failure unrelated to the target (collection, an unrelated import, setup, environment) is no proof.
Then check out the lane branch again and run every gate green. A ticket that keeps behaviour
unchanged (prefactor, migration batch, expand or contract step) and a ticket wholly outside the
test surface (prose, configuration, data) skip the proof: the existing tests stay green, and land
review covers the rest.

## Stacked tasks

A task that needs code from another unlanded task **stacks** on it: its INDEX Goal carries
`Base: <task-id>`, and its integration starts from the base task's integration, which becomes its
persistence. Each task has at most one base, and code flows only from base to stacked task. Two
tasks that need each other's code are one task, or both stack on a third task holding the shared
part.

- **Pull** by reconciling persistence, at two moments only: when a ticket needs the base's new code,
  and after retargeting, from the target branch, before land review. A pull lane whose gates fail is
  fixed on that lane like a ticket. With every ticket `done` and the base unlanded, wait for the base
  to land.
- **Retarget** once the base has landed: rebind persistence to the target branch. Land review and
  landing wait for this.
- **Remove** a base task's integration only after every task stacked on it has retargeted. Pi's
  remove refuses until then; under Claude, find those tasks by `Base: <task-id>` in other INDEX files.

## Mapped tasks

A task whose INDEX Goal carries `Map: <map-dir>` belongs to an effort run by an advisor. The advisor
owns design and decisions in the map; this task's spec covers its slice and points into the map's
design. The map's `## Standing orders` bind this task like its own; read them on entry. The
advisor's herdr name is `<name>` in the `Advisor: <name>` line of the map's `## Tasks`.

- **On `start(<task>)`**: the advisor has done Plan steps 1 and 2; do step 3, then run the frontier.
- **Design questions** go to the advisor, not the user: write the scenario, options, and a
  recommendation to `scratch/questions/<slug>.md`, send
  `herdr agent prompt <advisor> "question(<task-id>): <one line>; <file path>"`, and continue
  independent work. Delete the file once its ruling arrives, so a remaining file is an unanswered
  question.
- **On `ruling(<task>): <decision>` or `design-change(<task>): <decision>`**: read the decision and
  the map design it changed, then update this task's spec and tickets to match. A `doing` ticket is
  interrupted as in [Run the frontier](#run-the-frontier); a `done` ticket whose behaviour the ruling
  changes gets a new ticket.
- **On `base-landed(<task>)`**: retarget and pull per [stacked tasks](#stacked-tasks).
- **After land review**, write the report of step 5 to `scratch/land-review.md` and send
  `review-done(<task-id>): <its path>` instead of reporting to the user. The advisor's
  `land(<task-id>): <authority>` reply quotes the user's instruction or names a standing order; it
  counts as the user's instruction to land.
- **Report** `landed(<task-id>)` after landing, and `blocked(<task-id>): <one line>` when no frontier
  ticket can move for a reason other than waiting on the base.

## Land review

When every ticket is `done` (and, for a stacked task, persistence is retargeted to the target
branch):

1. Run the gates on the integration head.
2. Run code-review with the target branch as the fixed point, the integration head as candidate, the
   integration worktree as the checkout, and `spec.md` as the spec.
3. For each finding, choose fix or decline. Decline with a one-line reason; a finding whose fix
   would contradict a decision goes to the user.
4. Dispatch one `task-implementer` with every finding to fix, on a fresh lane. A behaviour-defect
   finding gets the [red-green proof](#gates) with a reproducing test; other findings need only the
   gates. Collect it. Review again only when the user asks.
5. Report to the user: the change, the gate result, and each finding's disposition.

## Land

Landing needs the user's current instruction or a standing order that grants it. Push needs its own
grant. Land with the operation in [runtime.md](runtime.md).

## Close

1. If the repository keeps ADRs, propose which decisions and spec content deserve one, and write the
   ones the user picks with domain-modeling. Read `retired/` here for the history.
2. List `scratch/` to the user, then delete it.
3. Move the task directory to `.agent_state/archives/<task-id>/`. Deleting the archive is the user's
   call.
