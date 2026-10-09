---
name: handoff
description: Write a portable routing handoff for another agent or session.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Write a routing and guidance document for a fresh agent. The handoff is not factual authority:
point to each owning spec, ticket, task record, ADR, issue, commit, diff, or evidence artifact instead
of copying or summarizing its contents. Carry inline only receiver guidance and operational facts that
have no owning document.

For task-flow work, route the receiver first to the task-flow skill, the task `INDEX.md`, and the
handed-off ticket; for an advisor effort, to the advisor skill and the map's `MAP.md`. Add only the
current-work pointers those sources require. When they cannot identify the next action, point the
receiver at the governing skill's resume procedure rather than at the ticket DAG or task history.

Save a user-requested file handoff in the operating system's temporary directory, outside the current
workspace. Use the same content contract when preparing an authorized Pi `handoff_context`
transition; this skill does not itself authorize or schedule that transition.

Include a `Suggested skills` section naming skills the receiver should invoke. Redact secrets and
personally identifiable information. If the user passed arguments, use them only to focus the route
and guidance for the next session.
