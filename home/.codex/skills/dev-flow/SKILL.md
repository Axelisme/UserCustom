---
name: dev-flow
description: Own the durable task-record lifecycle from exploration through neutral archive.
---

# Dev Flow

Use this skill for work that needs durable orientation across sessions. Dev-flow is the sole
active durable-task lifecycle authority. The [admission standard](references/admission-standard.md)
is the sole normative S0–S5 authority. Read it before wayfinding, spec, or ticket admission and
again after compaction; do not copy its policy into routing skills.

## One task record

Short work may remain in the current conversation. Durable work uses the workflow-neutral
`scripts/plan.py` task record under `.agent_state/plans/<task-id>/`. Its public Interface is exactly
`create | archive | resume | refresh`. `INDEX.md` holds `Goal`, `Current`, and `Next`; its generated
files block is a projection of the record directory. Agents maintain the prose, including
`Current stage` when it is useful to say where the conditional route stopped or why a stage was skipped.
`tickets/*.md` hold ordinary generic work; their container is a three-field header, a `Resolve by`
action, and `Outcome`/`Current`. Decision-making work keeps its decisions in the producer-owned
`decisions.md` artifact, not in the generic container.

Wayfinder, to-spec and to-tickets may use these ordinary generic tickets when they select the
plan-directory backend. Unfinished implementation, repair and user validation are generic ticket
work too; no phase/progress file, acceptance queue or second ticket store is created. Orchestrate
consumes task/ticket IDs but owns only Git/runtime coordination and derives no narrative.

## Conditional route

Wayfinder, to-spec, and to-tickets are independently usable producers; dev-flow only records their
chosen plan-directory work. Use wayfinder while the route to a durable destination is not yet clear.
Use to-spec before a landed change, unless it inherits a frozen contract (mark it inherited, refined,
or contradicted) or the delivery itself is text. Use to-tickets when work will be dispatched through
an admission gate; Root completing work in one context still records a generic ticket but does not
need to-tickets. A handoff is a decision-authority transfer event, not a route stage, and the record
continues to own implementation work after it.

At each Slice, freeze the Contract, run its focused and canonical gates, and hand off only a clean
exact SHA with evidence pointers. Root owns placement, merges and repository authority.
Orchestrate never pushes or reads a remote ref. Current user messages remain the only mutation
authority.

`archive` is a neutral directory move and never implies completion, but use it only after
implementation completes or the task is explicitly abandoned; a handoff alone does not qualify.
Final close-out follows S5. After compaction, reread this skill, the frozen spec, the task record and
the admission standard.
