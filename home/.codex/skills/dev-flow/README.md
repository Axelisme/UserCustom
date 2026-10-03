# Maintainer notes

Dev-flow owns durable task scope, tickets, alignment, INDEX, review records, and lifecycle state. Its
short `SKILL.md` routes agents to planning and record operations. Collab owns writer placement, review,
Git integration, and landing.

The shared design rationale, role information matrix, ticket review, gate results, runtime split,
profile synchronization duties, walkthrough, and measurement limits live in
[`../collab/README.md`](../collab/README.md). Keep that file as the single owner rather than copying its
rules here. This README is maintainer material and is not part of routine agent startup.

`plan.py locate` counts tickets by Kanban status and regenerates INDEX's `## Tickets` board. It reads
only ticket frontmatter. The board has Ticket, Status, Depends on, and Branch columns; its JSON rows
also report dependency status and startability. Task-level pending work stays in tracker Plan, and
execution identities stay in the relevant dispatch or round records, not a latest-line projection.
Other readable status values count as unknown without declaring their work accepted. An INDEX
without a `## Tickets` heading, an unreadable INDEX, and archived records are left unchanged.
`create` scaffolds the task from `templates/task/`, including the `tracker` ticket and a draft
`spec/scope.md`, and refuses a Git repository that would track `.agent_state`, because task records
and lane worktrees both live there. The board lists the tracker first, like a pinned issue.

The record design follows four conventions agents already know: the INDEX board is a Kanban view,
a ticket is a GitHub issue whose Log indexes necessary events, the tracker is the task's tracking
issue, and a review round is a PR review.
Each file has one writer and a next reader, so a missing file surfaces at the step that needs it.

These rules apply to tasks created under the current record convention. Legacy-task resumption and
migration are not supported; the reader does not detect or convert earlier narrative layouts.
