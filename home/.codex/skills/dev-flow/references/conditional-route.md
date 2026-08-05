# Dev-flow — conditional route

Which producer applies, and when `archive` is appropriate. That dev-flow transcribes producer output
and the producers never write into the record is in [SKILL.md](../SKILL.md#one-task-record); this
file states only the routing decisions.

**Wayfinder is user-invoked** — while the route to a durable destination is not yet clear, say so and
ask the user to run `/wayfinder`; do not attempt to start it on their behalf.

Use to-spec before a landed change, unless it inherits a frozen contract (mark it inherited, refined,
or contradicted) or the delivery itself is text.

Use to-tickets when work will be dispatched through an admission gate; Root completing work in one
context still records a generic ticket but does not need to-tickets.

A handoff is a decision-authority transfer event, not a route stage, and the record continues to own
implementation work after it.

**Orchestrate derives no task narrative.** It consumes task and ticket IDs and owns Git and runtime
coordination; it never infers what a task is about, what stage it reached, or why. An orchestrate
command that appears to know the plan is reporting something a human wrote down — treat narrative
read out of Git state as absent, not as a second opinion.

`archive` is a neutral directory move and never implies completion, but use it only after
implementation completes or the task is explicitly abandoned; a handoff alone does not qualify.
Final close-out follows orchestrate's S5.
