---
name: dev-flow
description: "Orchestrator task records: always use with collab to plan, resume, hand off, close, or archive a task."
---

# Dev-flow

Dev-flow owns task commitments and durable records. [Collab](../collab/SKILL.md) owns execution,
review, and Git delivery. Read both entries when orchestrating; use the routes below for the action
at hand. Workflow edits remain candidate material until authorized activation.

A task lives in `.agent_state/plans/<task-id>/` in the main checkout, separate from code worktrees.
INDEX is its entry: Goal, generated ticket board, and verbatim Standing orders. Every bounded
implementation has a ticket, including direct Orchestrator work; the tracker holds task-level work.

Before planning or changing a decision, contract, or execution arrangement, read
[Document authority](references/records.md#document-authority). This is the shared change decision
for both skills, including helper-generated plans and review corrections.

## The lifecycle

Open operation sections with `mdsec <absolute-path>#anchor ...`.

- Resume: [Resume](references/planning.md#resume).
- Transfer context: [Handoff](references/planning.md#handoff).
- Plan or change work: [Plan](references/planning.md#plan), then [Tickets](references/planning.md#tickets).
- Schedule concurrent work: [Parallel tickets](references/planning.md#parallel-tickets).
- Record shared design and scenarios: [Design alignment](references/planning.md#design-alignment).
- Save changed facts: [Maintain the record](references/records.md#maintain-the-record).
- Prepare review records: [Review rounds](references/records.md#review-rounds).
- Finish a ticket or task: [Close](references/records.md#close), [Archive](references/records.md#archive).

Read [custody](references/custody.md) when recording or applying user authority, including standing
orders and landing grants. Read [record permissions](references/lane-authority.md) before running
gates or dispatching a role that writes evidence. Capture valuable out-of-scope findings through
candidate-backlog; current acceptance gaps stay in this task.
