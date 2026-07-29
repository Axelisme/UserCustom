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
`create | archive | resume | ticket-create | refresh | check`. The bounded `INDEX.md` keeps Goal,
Current, Next, decisions and artifact pointers; dependency-addressable `tickets/*.md` hold all
unfinished work. Domain skills continue to own maps, research, prototypes, specs and review
reports and link those artifacts from the record rather than copying their state.

Wayfinder, to-spec and to-tickets share these ordinary generic tickets. Unfinished implementation,
repair and user validation are ordinary generic ticket work too; no phase/progress file,
acceptance queue or second ticket store is created. Orchestrate consumes task/ticket IDs but owns
only Git/runtime coordination and derives no narrative.

## Route

```text
wayfinder → to-spec → to-tickets → orchestrate → review/validation → explicit close-out
```

At each Slice, freeze the Contract, run its focused and canonical gates, and hand off only a clean
exact SHA with evidence pointers. Root owns placement, merges and repository authority.
Orchestrate never pushes or reads a remote ref. Current user messages remain the only mutation
authority.

Generic `archive` is a neutral directory move and may pause open work. Final close-out follows S5:
closed tickets and green task-record checks are combined with exact Git/runtime authority and any
task-specific rollout checklist. After compaction, reread this skill, the frozen spec, the task
record and the admission standard.
