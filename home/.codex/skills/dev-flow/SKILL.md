---
name: dev-flow
description: "Orchestrator task records: always use with collab to plan, resume, hand off, close, or archive a task."
---

# Dev-flow

Dev-flow owns the durable task record. [Collab](../collab/SKILL.md) owns writers, review, Git integration,
and landing. Read both short entries when orchestrating a task, then open only the operation sections
routed below.

Every task has one container under `.agent_state/plans/<task-id>/`. Every bounded implementation has a
ticket, including direct Orchestrator work. The approved spec or scope file owns scope. `INDEX.md`
carries active Standing orders and routes current work. Each fact has one owner record and is
written at a phase boundary; [Record operations](references/records.md#maintain-the-record) defines
owner records, phase boundaries, and routing edges. The Orchestrator owns INDEX, tickets, review
records, acceptance checkboxes, and lifecycle state.

On reorientation, run `scripts/plan.py locate <task-id>` from the main checkout and follow
[Resume](references/planning.md#resume).

## The lifecycle

Use `mdsec <absolute-path>#anchor ...` to open the selected operation sections; one call reads
several pointers in order.

- Resume an existing task: [Resume](references/planning.md#resume).
- Create a task, define scope, or slice tickets: [Plan](references/planning.md#plan) and
  [Tickets](references/planning.md#tickets).
- Select execution and review batches: [Parallel batches](references/planning.md#parallel-batches) and
  [Design alignment](references/planning.md#design-alignment).
- Record a completed or blocked ticket and collect user decisions: [Ticket handoff](references/records.md#ticket-handoff).
- Create or update a bounded integration review brief: [Batch review records](references/records.md#batch-review-records).
- Update INDEX, tickets, observations, or evidence: [Maintain the record](references/records.md#maintain-the-record).
- Close or archive work: [Close](references/records.md#close) and [Archive](references/records.md#archive).

Each selected section states its inputs, authority, stop conditions, completion condition, and record
updates. Open [custody](references/custody.md) before admitting or applying a durable grant, changing
approved scope, landing, or retiring resources. Open [lane authority](references/lane-authority.md)
only for delegated record or evidence writes.

## Core invariants

- Preserve approved obligations and pre-existing user state. Missing historical authority or scope
  returns to its owner; a new default does not rewrite it.
- Tests establish observable behavior through interfaces. Direct review establishes prose, structure,
  configuration, repository data, responsibility placement, and other static facts.
- Update INDEX's routing fields at a routing edge. Maintain Standing orders under
  [custody](references/custody.md). When INDEX cannot route the next owner, repair the record or ask
  the decision owner instead of scanning every ticket, artifact, or log.
- A ticket closes when batch acceptance covers every applicable criterion.
- Capture valuable out-of-scope findings through candidate-backlog. Current acceptance gaps remain in
  this task.
