# Dev-flow — conditional route

Which planning owner applies, and when `archive` is appropriate.

**Wayfinder is user-invoked** — while the route to a durable destination is not yet clear, say so and
ask the user to run `/wayfinder`; do not attempt to start it on their behalf.

Use to-spec when the task or Caller needs a frozen implementation contract; landing alone does not
create that need, and `spec: none` remains valid. When selected inside a dev-flow task, publish the
producer-format spec under that task's `artifacts/` directory and set its INDEX spec pointer; to-spec
still owns the spec format. If an external repository tracker is explicitly in use, link its spec
from the record instead.

Use to-tickets when multiple dispatched slices need explicit dependency edges; Root completing work
in one context still records a generic ticket but does not need to-tickets. Inside a dev-flow task,
keep the to-tickets producer artifact under `artifacts/`, then transcribe approved work into separate
conforming dev-flow lifecycle tickets under `tickets/`, each producer ticket's `Blocked by:` edges
landing in the lifecycle ticket's `depends_on` field. Each lifecycle ticket points to the producer
artifact when one exists; producer-format tickets never occupy the lifecycle-ticket path parsed by
`locate`. If an external repository tracker is explicitly in use, link those issues from the record
instead.

A handoff routes and guides rather than transferring factual authority or forming a route stage. The
record continues to own implementation work after it. For a handed-off Dev-flow task, start from the
active guidance, `INDEX.md`, and handed-off ticket, then follow only current-work pointers. If those
sources cannot name the next action, maintain them rather than inferring focus from a broad scan.

**Collab derives no task narrative.** It consumes bounded intent and Acceptance criteria, then
coordinates Implement and Acceptance; follow its guidance when writer placement is in question.
Review evidence identifies its fixed subject separately. Handoffs and collaboration evidence never
say what the task means, what durable stage it reached, or why; point back to this record instead of
creating a second status store.

`archive` is a neutral directory move and never implies completion. Root reconciles the evidence and
close-out in the task record before moving it, whether work completed or was abandoned.
