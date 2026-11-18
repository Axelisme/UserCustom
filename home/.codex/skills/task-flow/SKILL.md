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

Decision numbers are task-local: every task numbers its own, so `0012` names a different ruling in
each archive. Tracked files (code, comments, tests, repository docs) carry the reason itself, or the
repository's ADR that holds it; decision numbers stay inside `.agent_state/`.

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
  match a designer's ruling. Changes that alter behaviour
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
  A ticket's files go under `scratch/<ticket>/`, deleted when the ticket is collected. Evidence a
  later decision still needs moves first: in a mapped task to the map's `scratch/<task-id>/`,
  otherwise to `scratch/` itself. Data and conclusions others rely on go into Git where the
  repository's instructions say. Raw output no conclusion needs is deleted at [Close](#close).

Handoff is written only when the user asks, with the handoff skill, outside the task directory.

## Resume

After compaction or a session change:

1. Read `INDEX.md` whole and run `check.py` for the frontier and the `doing` tickets.
2. Each `doing` ticket's lane is `wave/<task-id>/<ticket-stem>`, for example
   `wave/calc-ops/02-multiply`. Observe the lane and the live children with the runtime's status
   operations ([runtime.md](runtime.md)). A lane on a detached HEAD goes back to its branch first. A
   live child keeps working; wait for it. With no live child, inspect the delivered diff against
   acceptance, the worktree, and scratch evidence. A clean, committed candidate with the required
   evidence goes to the [gates](#gates); incomplete work gets a fresh dispatch on the same lane.
   Commit count or layout is not proof of completeness.
3. In a mapped task, leave every file in `scratch/questions/` where it is: the coordinator's patrol
   lists open question files, so a remaining file is still queued.

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
   (`02-multiply`) and dispatch a `task-implementer` in the background. The dispatch carries pointers,
   not copies: task path, ticket path, lane path, gate commands with cwd, `scratch/<ticket>/` for
   logs, and an absolute path to the tdd `SKILL.md` readable by the child. Resolve and verify the
   skill path before dispatch; a missing or unreadable path blocks dispatch.
2. Continue independent work while lanes run. When nothing independent remains, end the turn.
3. On a COMPLETED result, check the implementer's gate receipts against acceptance and rerun one
   gate yourself as a spot check; rerun the rest only where a receipt is missing or suspect. Pass:
   collect the lane into integration, set `done`, and delete `scratch/<ticket>/`. Fail: send the
   failure back through a fresh dispatch on the same lane. On BLOCKED, settle the blocker as a
   question, then dispatch fresh on the same lane.
4. A collected ticket can widen the frontier; dispatch the newly unblocked tickets.

An implementer question about scope or behaviour becomes a user question (a design question in a
mapped task); once it is settled, update the spec, then reply to the implementer.

A settled change that touches a `doing` ticket interrupts it rather than waiting: update the ticket,
then steer its implementer to the updated ticket (runtime steer). When the change makes the ticket
obsolete, terminate the implementer, drop the lane, and move the ticket to `retired/`.

## Gates

Every ticket runs the repository's declared checks (test, lint, typecheck, as AGENTS.md or
CLAUDE.md states) on what it touches: the affected tests and the lint and typecheck of the changed
files, plus any check its acceptance criteria name. The full test suite and the whole-tree typecheck
run once, at [land review](#land-review). Logs go to `scratch/`; results are read from exit status,
not recorded.

The **record gate** applies to every ticket: each line the lane adds to a tracked file states its
reason without a decision number (`D` + digits, or `decisions/NNNN`). Rewrite a hit as the reason it
stood for.

The **doc gate** applies to every ticket that changes tracked code. Documents fall behind code,
and the ones missed are rarely the changed module's own. Before collection, list the tracked
documents the change can make stale, two ways:

- **Related**: each changed path's README chain, the decision records those READMEs and the changed
  code cite, and every other document citing the same records.
- **Search**: all tracked documents, for the names the diff removed, renamed, or changed, the
  changed files' paths, the values the diff removed, and the terms documents use for the changed
  thing. A term with too many hits to read is replaced by a narrower one.

Use the repository's tool for this when its instructions name one. Keep the list in
`scratch/<ticket>/doc-hits.md` and give every hit one word: `unrelated`, `consistent`, or `updated`.
At collection, rerun the list and collect only when every hit carries its word.

**Red-green proof.** Before implementing changed behaviour, run its new tests red on the missing
behaviour. A failed assertion or missing function or attribute introduced by the ticket qualifies;
collection, unrelated imports, setup, and environment failures do not. Keep the command, tested
state, exit status, and relevant failure output in scratch, then run green after implementation.
Test corrections may fix a mistaken test while preserving acceptance and coverage; explain the
correction and renew the relevant red-green evidence. Acceptance or scope changes need a ruling.
Commit layout is unrestricted. Before collection, review the evidence and diff against acceptance,
then run every gate green. Replay red only when evidence is suspect or explicitly required.
A ticket that keeps behaviour unchanged (prefactor, migration batch, expand or contract step), or
is wholly outside the test surface (prose, configuration, data), skips red-green proof; existing
tests stay green and land review covers the rest.

**Evidence budget.** Tie each artifact or experiment to an acceptance criterion or unresolved
question. Keep commands, tested inputs/state, outcomes, and enough output to check the conclusion;
link bulky raw output instead of copying it. Reuse evidence whose inputs and assumptions still
hold: a green result recorded with a tree hash counts for every later check of that same tree. On
reconcile, rerun the checks the incoming files affect, not unrelated artifact generation.
Stop optional evidence gathering once acceptance is supported and the named questions are resolved.
Run a measurement through the repository's own entry point, wrapped by at most one script per
ticket. Check a run by reading its receipt and outputs; write a checking script only for a check
that repeats, and reuse it across runs.

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

A task whose INDEX Goal carries `Map: <map-dir>` belongs to an effort. A **coordinator** keeps the
effort's tasks moving and a **designer** owns its design and decisions in the map; this task's spec
covers its slice and points into the map's design. The map's `## Standing orders` bind this task
like its own; read them on entry. The coordinator's herdr name is `<name>` in the
`Coordinator: <name>` line of the map's `## Tasks`.

- **On `start(<task>)`**: the designer has done Plan steps 1 and 2; do step 3, then run the
  frontier. The message names your compute grant.
- **Messages.** You send the coordinator four kinds and nothing else: `question`, `blocked`,
  `review-done`, and the replies `promoted` and `landed`. It reads your progress from your records.
- **Questions.** Write the scenario, options, and a recommendation to
  `scratch/questions/<slug>.md`, starting with a `Tier:` line, send
  `herdr agent prompt <coordinator> "question(<task-id>): <one line>; <file path>"`, and continue
  independent work. Delete the file once its ruling, or a `steer` that answers it, arrives, so a
  remaining file is an unanswered question.

  | `Tier:` | The question | Answered by |
  |---|---|---|
  | `local` | Stays inside one module, changes no public surface, data format, or acceptance text, and can be undone within this task | You: no question is sent |
  | `simple` | Changes acceptance text, one module's public detail, or a test or measurement method | A quick ruling, in about 20 minutes |
  | `full` | Adds or removes a concept; changes what a public interface or behaviour means; changes a data format; crosses a module boundary; sets a pattern others will copy; changes what the user sees; is hard to walk back | The designer, after an investigation |
  | `process` | Changes neither design nor acceptance, and is past what you [handle yourself](#mapped-tasks) | The coordinator |

  A `local` question is decided by you: adopt your recommended option and record it with its reason
  under `## Local decisions` in `spec.md`; land review lists these. When unsure between two tiers,
  take the lower; land review checks the call, and whoever receives the question may re-tier it.
  Every sent question goes to the coordinator, whatever its tier: the coordinator routes design
  questions. A `full` question can wait hours for the user; keep the frontier moving on tickets it
  does not touch.
- **Handle yourself.** Fix the cause, rerun, and log one `runs.md` line, with no question, for: a
  mistaken test or fixture (acceptance meaning and coverage unchanged); a command or tool error (a
  mistyped SHA, an empty selection, formatter, lint, or typecheck findings, a bug in a driver or a
  read-only helper); a queue or outer timeout before the payload started; a lane environment rebuilt
  with the repository's locked bootstrap; a selection that grew only because tests were added; a pane
  clean-up warning. Still ask the coordinator for: exclusive runs, and any formal timing, benchmark,
  or profile; a run over 10 minutes or over the memory limit the grant names; GPU work; a write to a
  cache other tasks read as numeric input; rerunning or extending a named once-only acceptance batch.
  Three failures from one cause in a row: walk the cause by hand before the next run.
- **Compute grant.** Run heavy commands within the grant your `start` message or a standing order
  names; the default is a non-exclusive run of up to 10 minutes at your own decision, 30 minutes of
  exclusive time per ticket, and one retry of a failed run once its cause is fixed. Keep one line
  per run in `scratch/runs.md`: the command, its bound, its outcome. Past the grant, send a
  `process` question with the itemised estimate.
- **On `ruling(<task>): <decision>` or `design-change(<task>): <decision>`**, sent by the designer:
  read the decision and the map design it changed, then update this task's spec and tickets to
  match. A `doing` ticket is interrupted as in [Run the frontier](#run-the-frontier); a `done`
  ticket whose behaviour the ruling changes gets a new ticket.
- **On `steer(<task>): <provenance>; <process instruction>`**: treat it as coordinator process
  guidance, not a user ruling. Provenance is `coordinator-observation`, a quoted user instruction,
  or a named standing order with its date. Check the cited authority and apply only within existing
  scope, acceptance, and grants. Keep red-green proof, declared gates, and unresolved findings
  intact. A steer cannot authorize spec changes, standing orders, landing, or push; ask for the
  required ruling or authority when it conflicts with those boundaries.
- **On `base-landed(<task>)`**: retarget and pull per [stacked tasks](#stacked-tasks).
- **After land review**, write the report of step 5 to `scratch/land-review.md` and send
  `review-done(<task-id>): <its path>` instead of reporting to the user. The coordinator's
  `land(<task-id>): <authority>` reply quotes the user's instruction or names a standing order; it
  counts as the user's instruction to land.
- **On `promote(<task>): <list path>`**: write each listed text at its destination as one commit on
  the integration, re-run the gates those files require, and send `promoted(<task-id>): <commit>`.
  For a mapped task this replaces Close step 1.
- **Before `promoted` and `landed`**, when the target branch has moved past your integration,
  reconcile it and run the checks the incoming files affect. A tool error on the way is yours to fix
  and continue; a red result on the candidate itself stops the step with `blocked(<task-id>)`.
- **On a planned-restart `steer`**: start no heavy run, stop a run that cannot finish by the named
  time, commit WIP, write `scratch/reboot-checkpoint-<date>.md` (lanes and HEADs, the step in
  progress, the next step), and reply `blocked(<task-id>): checkpoint <path>`. After the restart, a
  run the restart interrupted is not evidence and does not use up a retry or a once-only grant.
- **Report** `landed(<task-id>)` after landing, and `blocked(<task-id>): <one line>` when no frontier
  ticket can move for a reason other than waiting on the base or on a design question already
  asked.

## Land review

When every ticket is `done` (and, for a stacked task, persistence is retargeted to the target
branch):

1. Run the gates on the integration head, this time with the full test suite and the whole-tree
   typecheck. A green full run already recorded for this exact tree hash counts.
2. Run code-review with the target branch as the fixed point, the integration head as candidate, the
   integration worktree as the checkout, and `spec.md` as the spec.
3. For each finding, choose fix or decline. Decline with a one-line reason; a finding whose fix
   would contradict a decision goes to the user.
4. Dispatch one `task-implementer` with every finding to fix, on a fresh lane. A behaviour-defect
   finding gets the [red-green proof](#gates) with a reproducing test; other findings need only the
   checks the fix affects. Collect it. Review again only when the user asks.
5. Report to the user: the change, the gate result, and each finding's disposition.

## Land

Landing needs the user's current instruction or a standing order that grants it. Push needs its own
grant. Land with the operation in [runtime.md](runtime.md).

## Close

1. **Promote** every in-force decision to where its rule lives once the task is archived, then show
   the user the list and write the ones they confirm:
   - a component's placement, responsibility, or cross-module boundary → an ADR, written with
     domain-modeling, carrying the ruling date and the user's words in 「」;
   - one module's behaviour or format → that module's documentation, docstring, or a test;
   - how work runs in this repository → the repository's agent instructions;
   - a choice that only steered this task → stays in the archive.

   Read `retired/` here for the history.
2. Search `.agent_state/plans/`, `.agent_state/maps/`, and tracked files for paths into this task's
   `scratch/`. Move each referenced item into the archive and tell its referrer the new path; then
   list the rest of `scratch/` to the user and delete it. Data held under an earlier approval, or
   kept for a later effort, moves into the archive unchanged; name the coordinator as its owner in
   the close report.
3. Move the task directory to `.agent_state/archives/<task-id>/`. Deleting the archive is the user's
   call.

A mapped task skips step 1, because its decisions were promoted before landing. After step 3, send
the coordinator the archive path so the task's decisions can move there.
