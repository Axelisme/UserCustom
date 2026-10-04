# Maintainer notes

Dev-flow owns durable task scope, tickets, alignment, INDEX, and lifecycle state. Its
short `SKILL.md` routes agents to planning and record operations. Collab owns writer placement, review,
Git integration, and landing.

The shared design rationale, role information matrix, range review, gate results, runtime split,
profile synchronization duties, walkthrough, and measurement limits live in
[`../collab/README.md`](../collab/README.md). Keep that file as the single owner rather than copying its
rules here. This README is maintainer material and is not part of routine agent startup.

`plan.py locate` counts tickets by Kanban status and regenerates INDEX's `## Tickets` board. It reads
only ticket frontmatter. The board has Ticket, Status, Depends on, and Branch columns; its JSON rows
also report dependency status and startability. Task-level pending work stays in tracker Plan.
Other readable status values count as unknown without declaring their work accepted. An INDEX
without a `## Tickets` heading, an unreadable INDEX, and archived records are left unchanged.
`create` scaffolds the task from `templates/task/`, including the `tracker` ticket, a draft
`spec/scope.md`, and the empty `decisions/README.md` routing list, and refuses a Git repository that would track `.agent_state`, because task records
and lane worktrees both live there. The board lists the tracker first, like a pinned issue.

Records hold only what an agent needs now or later and cannot recover from code, Git, or the collab
tools; the user rarely reads them. Mutable sections (Plan, Notes, Resources, the decision routing
list, gate summaries) are rewritten whole as snapshots instead of appended, so they cannot grow into
a diary. Only decision files accumulate, and `decisions/README.md` routes them by domain.
User decisions bind; `spec/` is design reference the Orchestrator may redesign. Review covers ranges
of integration rather than tickets; see Collab's `references/review.md`.

These rules apply to tasks created under the current record convention. Legacy-task resumption and
migration are not supported; the reader does not detect or convert earlier narrative layouts.
