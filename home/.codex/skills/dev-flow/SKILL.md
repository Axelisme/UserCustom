---
name: dev-flow
description: "Orchestrator task records: always use with collab to plan, resume, hand off, close, or archive a task."
---

# Dev-flow

Dev-flow owns the durable task record. [Collab](../collab/SKILL.md) owns writers, review, Git integration,
and landing. Read both short entries when orchestrating a task, then open only the operation sections
routed below.

Every task has one container under `.agent_state/plans/<task-id>/`: INDEX with the Goal, a Kanban
board of tickets, and the Standing orders; the approved scope in `spec/scope.md`; the user's answers
under `decisions/`; investigation output and inventories under `research/`; task scripts under
`scripts/`; and one directory per ticket holding the ticket, its review rounds, and its history. The `tracker` ticket carries the task's own status. Every bounded implementation has a
ticket, including direct Orchestrator work. Each fact has one owner record;
[Maintain the record](references/records.md#maintain-the-record) lists them.

On reorientation, run `scripts/plan.py locate <task-id>` from the main checkout and follow
[Resume](references/planning.md#resume). Locate regenerates the INDEX board from ticket frontmatter.

## The lifecycle

Use `mdsec <absolute-path>#anchor ...` to open the selected operation sections; one call reads
several pointers in order.

- Resume an existing task: [Resume](references/planning.md#resume).
- Create a task, define scope, or slice tickets: [Plan](references/planning.md#plan) and
  [Tickets](references/planning.md#tickets).
- Select tickets to run together: [Parallel tickets](references/planning.md#parallel-tickets) and
  [Design alignment](references/planning.md#design-alignment).
- Change a ticket's status, write its Log, or record a user decision:
  [Maintain the record](references/records.md#maintain-the-record).
- Write a review brief or read a verdict: [Review rounds](references/records.md#review-rounds).
- Close or archive work: [Close](references/records.md#close) and [Archive](references/records.md#archive).

Each selected section states its inputs, stop conditions, and completion condition. Open
[custody](references/custody.md) before admitting or applying a Standing order, changing approved
scope, or landing. Open [record permissions](references/lane-authority.md) when dispatching a role
that writes a gate summary or a verdict, and before running gates yourself.

## Core invariants

- Preserve approved obligations. Missing historical authority or scope returns to its owner; a new
  default does not rewrite it.
- Tests establish observable behavior through interfaces. Direct review establishes prose, structure,
  configuration, repository data, responsibility placement, and other static facts.
- Every status change gets a Log line. Maintain Standing orders under [custody](references/custody.md).
- A ticket closes when a COMPLETED review round, or the gates of a gates-only ticket, covers every
  applicable criterion and its candidate, if any, is collected. The tracker stays `doing` until the
  user completes or abandons the task.
- Capture valuable out-of-scope findings through candidate-backlog. Current acceptance gaps remain in
  this task.
