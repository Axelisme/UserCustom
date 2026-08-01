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

- Short work may remain in the current conversation.
- Durable work uses the workflow-neutral `scripts/plan.py` task record under
  `.agent_state/plans/<task-id>/`.
- Its public Interface is exactly `create | archive | resume | refresh`.
- `INDEX.md` holds `Goal`, `Current`, `Next`, `Envelope`, and `Standing orders`.
- `Envelope` carries the frozen minimum need and usage envelope, or a pointer to the artifact that
  owns it. A task with no implementation output records `Not applicable` with a reason. It is never
  blank: a blank Envelope is the visible evidence that the need was never frozen, and every later
  out-of-envelope refusal cites it.
- `Standing orders` carries the user-issued instructions still in force for this task — a mode
  activation, an ad-hoc grant, or a rule under test — each with its scope and when it lapses.
- Its generated files block is a projection of the record directory.
- Agents maintain the prose.
- `Current stage` says where the conditional route stopped or why a stage was skipped, when useful.
- `tickets/*.md` hold ordinary generic work; their container is a three-field header, a
  `Resolve by` action, and `Outcome`/`Current`.
- Decision-making work keeps its decisions in the producer-owned `decisions.md` artifact, not in
  the generic container.

Write a standing order only from words the user actually said: **quote the user's sentence verbatim**,
stamp when it was issued, and list the new entries in the same reply so the user can disown them on
the spot. A paraphrase of the user, or a rule the agent inferred for itself, is not a standing order.
When an entry activates another skill's contract, name that skill and point at it; its grants and
exclusions stay in that skill.

See [`references/example-record/`](references/example-record/) for a worked example of this shape.

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
Final close-out follows S5. After compaction, reread this skill, the frozen spec, the admission
standard, and the task record — including its `Envelope` and `Standing orders`, which carry what the
user froze and granted and are the first things a compacted session loses.
