# Collab — Pi runtime

Verified against `pi-subagents` 0.47.1. Check the installed package before trusting runtime-specific
placement details; Collab's core guidance remains runtime-neutral.

## Routing

Read only the section named for the step you are taking; every section after Composed delegation and
Typed results states its own enabling condition.

- **Composed delegation** — the canonical branch: invoke `collab_run_reviewed_lane` for one
  shared lane, including bounded corrections.
- **Typed results** — the typed terminal outcomes returned by the reviewed-lane workflow.
- **Post-launch** — after launching an asynchronous workflow: the ordinary return-or-yield step
  that lets completion wake the session.
- **Run control** — only when a run is interrupted or needs status, steering, or revival.
- **Placement** — only when the canonical lane placement does not fit the chosen shape.
- **Collection** — only after the Orchestrator judges the reviewed lane and chooses collection.
- **Operations** — only when selecting which `collab_*` tool carries out a Collab step.

## Composed delegation

For delegated closed work — bounded brief, delegated Acceptance criteria, placement, mutation
authority, and escalation boundary all closed — invoke the registered
`collab_run_reviewed_lane` tool. It is the canonical and only accepted Pi composition path for a
worker, reviewer, and bounded correction over one Collab-managed lane. The tool uses the configured
`collab-implementer` and `collab-acceptor` profiles. The Orchestrator supplies an explicit finite
`correction_budget`: initial implementation does not consume it, each `BLOCKED → writer correction`
transition consumes one, and exhausting it is a terminal seam that returns to the Orchestrator
without selecting a redesign procedure. Do not use turn, tool, or usage budgets as the correction
budget.

**Profile model contract.** The selected agent profile owns its configured `model` and `thinking`.
The Orchestrator preserves both unchanged, omitting `model` and `thinking` from the outer
`subagent(...)` options and every child call. Only a current user instruction that explicitly names
an override grants authority for that launch; task difficulty, retries, and review results grant
none. This contract is satisfied only when every workflow- and child-level `model` and `thinking`
field is absent or directly authorized by that instruction.

A Collab lane is already one writable checkout with one live writer. The reviewed-lane tool keeps
the delegated worker and reviewer on that exact lane, with fresh role-specific structured results;
corrections carry the original bounded contract plus current typed blockers, and rereviews carry the
original review expectations against the changed protected lane. Child run IDs remain runtime
operation evidence, not continuation handles, and appear in no terminal projection. Every branch and
terminal projection reads parsed `structuredOutput`, never free-form output text.

Supply the tool only these bounded fields:

```json
{
  "task_id": "task identifier",
  "ticket_id": "Dev-flow ticket identifier",
  "lane_id": "existing managed lane",
  "worker_brief": "bounded implementation brief",
  "review_brief": "bounded read-only acceptance brief",
  "correction_budget": 1
}
```

`worker_brief` names the ticket — the ticket owns Outcome and Acceptance — and carries only the
operational deltas a brief needs: placement, mutation authority, validation expectations, stop
conditions, and role-specific deltas, without copying the ticket's prose. `review_brief` is a ticket
pointer naming the delegated Acceptance identifiers and the acceptor's read-only scope and
authority, validation expectations, protected-lane and writer-stopped stop conditions, lifecycle
and cleanup ownership as applicable, role-specific deltas, and the optional task-boundary pointer.
The tool rejects extra fields and unbounded or empty briefs.

Terminal outcomes:

- `REVIEWED` — the worker returned `COMPLETED` and the reviewer returned `PASS`. It projects the
  latest worker's semantic validation and optional residual risks plus the reviewer's optional
  out-of-envelope findings.
- `BLOCKED` — the worker returned `BLOCKED`; it carries the worker blocker.
- `NEEDS_DECISION` — a worker or reviewer returned it; it carries why, the exact question, and any
  bounded suggestion the reviewer offered, and returns immediately to the Orchestrator.
- `CORRECTION_BUDGET_EXHAUSTED` — the reviewer still returns `BLOCKED` after the budget is spent; it
  carries the reviewer's remaining blockers. It is only a terminal seam; it does not start a
  redesign.

The tool returns only an asynchronous launch receipt — `workflow_id`, `async_id`, and `async_dir`.
The receipt is not Acceptance or a continuation handle: the ordinary asynchronous workflow result
must wake the session through the Post-launch guidance, and the Orchestrator judges the typed result
while the lane remains available. Child run IDs remain runtime operation evidence; Git, the lane
runtime, and the Orchestrator own later coordination. Any correction, rereview, or
collection-time reconciliation review uses a fresh compatible child under the tool's bounded
contract rather than resuming a run.

The launch fails closed before spawn when the exact managed lane, either configured profile, or the
pi-subagents Extension RPC v1 `spawn`/`asyncSpawn` capability is missing or incompatible. There is
no fallback launcher. The tool schema and launch contract add no tracing, child feedback, model,
thinking, effort, collection, landing, or push controls.

## Typed results

The reviewed-lane tool owns concrete JSON Schema objects for its worker and reviewer results; core
Collab and the profiles express the same semantics without repeating the schema. Each child finishes
through Pi's structured-output protocol instead of free-form Markdown, so formatting cannot change
control flow. The parsed child result is `structuredOutput`; free-form output never drives control
flow. Implementer launches use Pi's v1 effects projection so a schema-valid `BLOCKED` or
`NEEDS_DECISION` result can stop without mutation; the composition separately requires an observed
file mutation before routing any `COMPLETED` result to review. This effects check changes no typed
result field. When the temporary efficiency probe is enabled, its stdout record and implementer sidecar are
operation evidence retained by the child/lane artifacts and add no property to either schema below.
They never drive workflow branching. Use one structured result per child and do not combine it with
Pi's generic acceptance report:
both default Collab profiles set `acceptance: { level: none, ... }` with a reason, and a launch needing
another acceptance policy selects it explicitly.

Worker (`collab-implementer`) — `COMPLETED` carries the behavior/Interface semantic checks actually
performed, each with `check`, `result: PASSED | FAILED`, and a concise `summary`, and may carry
`residualRisks`; operational Git and runtime checks — status, diff, diff-check, staged state,
cleanliness, ancestry, commit identity, and lifecycle — are categorically ineligible for `validation`
even when the worker runs them and receive no semantic check name or summary; each check name and
summary describes only the behavior/Interface outcome observed, never the operational command or
checkout, tree, lane, branch, commit, diff, staged, clean, ancestry, runtime, or lifecycle state it
ran against; `BLOCKED` carries
`blocker`; `NEEDS_DECISION` carries `decision: { why, question }`:

```json
{
  "type": "object",
  "oneOf": [
    {
      "type": "object",
      "properties": {
        "outcome": { "const": "COMPLETED" },
        "validation": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["check", "result", "summary"],
            "properties": {
              "check": { "type": "string" },
              "result": { "enum": ["PASSED", "FAILED"] },
              "summary": { "type": "string" }
            }
          }
        },
        "residualRisks": { "type": "array", "items": { "type": "string" } }
      },
      "additionalProperties": false,
      "required": ["outcome", "validation"]
    },
    {
      "type": "object",
      "properties": {
        "outcome": { "const": "BLOCKED" },
        "blocker": { "type": "string" }
      },
      "additionalProperties": false,
      "required": ["outcome", "blocker"]
    },
    {
      "type": "object",
      "properties": {
        "outcome": { "const": "NEEDS_DECISION" },
        "decision": {
          "type": "object",
          "additionalProperties": false,
          "required": ["why", "question"],
          "properties": {
            "why": { "type": "string" },
            "question": { "type": "string" }
          }
        }
      },
      "additionalProperties": false,
      "required": ["outcome", "decision"]
    }
  ]
}
```

Reviewer (`collab-acceptor`) — `PASS` needs no filler; `BLOCKED` carries `blockers`, each with its
`location`, `reason`, and bounded `fix`; `NEEDS_DECISION` carries `decision: { why, question }`; any
verdict may add optional `outOfEnvelopeFindings`:

```json
{
  "type": "object",
  "oneOf": [
    {
      "type": "object",
      "properties": {
        "verdict": { "const": "PASS" },
        "outOfEnvelopeFindings": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["location", "evidence"],
            "properties": {
              "location": { "type": "string" },
              "evidence": { "type": "string" }
            }
          }
        }
      },
      "additionalProperties": false,
      "required": ["verdict"]
    },
    {
      "type": "object",
      "properties": {
        "verdict": { "const": "BLOCKED" },
        "blockers": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["location", "reason", "fix"],
            "properties": {
              "location": { "type": "string" },
              "reason": { "type": "string" },
              "fix": { "type": "string" }
            }
          }
        },
        "outOfEnvelopeFindings": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["location", "evidence"],
            "properties": {
              "location": { "type": "string" },
              "evidence": { "type": "string" }
            }
          }
        }
      },
      "additionalProperties": false,
      "required": ["verdict", "blockers"]
    },
    {
      "type": "object",
      "properties": {
        "verdict": { "const": "NEEDS_DECISION" },
        "decision": {
          "type": "object",
          "additionalProperties": false,
          "required": ["why", "question"],
          "properties": {
            "why": { "type": "string" },
            "question": { "type": "string" }
          }
        },
        "outOfEnvelopeFindings": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["location", "evidence"],
            "properties": {
              "location": { "type": "string" },
              "evidence": { "type": "string" }
            }
          }
        }
      },
      "additionalProperties": false,
      "required": ["verdict", "decision"]
    }
  ]
}
```

## Post-launch

Read this section after launching an asynchronous workflow, when the Orchestrator continues
independent work before completion wakes the session.

Launch subagents asynchronously so the Orchestrator can continue independent work. In an interactive
session, return control or use the active goal's yield mechanism and let completion wake the session.
Use `subagent_wait` only when the current request must finish in the same turn; waiting does not make
a child more authoritative.

## Run control

Read this section only when a run is interrupted or needs status, steering, stopping, or revival.

Inspect a run with `subagent({ action: "status", id })`. Guide a live top-level run with
`action: "steer"`, stop it with `action: "stop"`, and revive a failed, paused, or completed run with
`action: "resume"` only when the persisted session preserves the original launch contract. Revival
restores the persisted profile model contract unchanged.
Retained foreground continuation does not forward `outputSchema` or an explicit acceptance policy,
so a workflow child resumed by `runId` loses its `structuredOutput` and falls back to inferred
generic acceptance; the composed loop above therefore never resumes children and launches a fresh
compatible child with the full launch controls instead. Turn, tool, runtime, and usage budgets are
optional controls rather than role-wide defaults and are not a correction budget. After a writing
run is interrupted, inspect its changed files and commit state before choosing the next owner.

## Placement

Read this section only when the canonical lane placement does not fit the chosen shape: discovering
live profiles, selecting another compatible profile, a fork context, managed isolation around a
non-Collab checkout, or parallel writers.

Discover the live profiles with `subagent({ action: "list" })`, then select only an executable,
non-disabled agent. The canonical reviewed-lane placement is `collab_run_reviewed_lane`, which
preflights the configured profiles and exact lane before asking pi-subagents to launch. A different
shape requires an explicit Orchestrator choice and its own supported placement mechanism; do not
replace the canonical tool with a handwritten worker/reviewer loop. Keep execution and management
separate: status, steering, stopping, and other controls use their management action without
execution fields.

Use `context: "fresh"` for independent review. Use `context: "fork"` only when the child should
inherit the persisted parent conversation; it is not a filtered review context. A profile's configured
default applies when the call omits context.

`worktree: true` remains for a writing child when the source checkout is clean and the Orchestrator
deliberately wants managed isolation around a non-Collab checkout. Parallel reviewers may remain
read-only; parallel writers each need their own writable checkout.

## Collection

Read this section only after the Orchestrator judges the reviewed lane and chooses collection.

`lane_collect`'s own stale-lane behavior is the default collection path after the Orchestrator
judges the reviewed lane. A `collected` result completes collection. A `reconciled` result stops
before collection: launch a fresh typed reviewer against the reconciled protected current lane, have
the Orchestrator judge again, and only then retry collection. A `conflicted` result returns to the
Orchestrator. `lane_reconcile` remains available but is not an extra default pre-step.

```javascript
// lane_collect returned "reconciled": stop before collection
const reconciledReview = await runs.run("review-reconcile-1", {
  agent: "collab-acceptor",
  cwd: lane,
  worktree: false,
  context: "fresh",
  task: REVIEW_BRIEF + " — rereview the reconciled protected current lane",
  outputSchema: reviewerSchema
});
// The Orchestrator judges reconciledReview.structuredOutput, then retries lane_collect
```

## Operations

Read this section only when selecting which `collab_*` tool carries out a Collab step. Each tool is
independently registered; its own description and parameter schema are authoritative for what it
accepts and returns. This section states only which Collab step selects which tool.

- Establishes the task-local integration branch collection needs before any lane can be collected
  into it — `collab_integration_create`.
- The Collection boundary's adoption step: makes an existing branch, passed as `source_branch`, the
  complete managed integration state — `collab_integration_adopt`.
- Choose the execution shape: creates the one writable branch, checkout, worktree, and lane-owned
  state a dispatched writer needs — `collab_lane_create`.
- Compose a reviewed lane: launches the configured implementer and acceptor asynchronously in one
  exact managed lane with bounded corrections — `collab_run_reviewed_lane`.
- Optional lane-side synchronization: brings a stale lane up to current integration when the
  Orchestrator explicitly chooses the separate pre-step. Collection normally relies on
  `collab_lane_collect`'s stale-lane handling instead — `collab_lane_reconcile`.
- Collect: moves an Orchestrator-accepted lane into the integration branch and retires the lane —
  `collab_lane_collect`.
- Retire the lane: removes a lane's managed branch and worktree without collecting it, for a lane
  whose work is not going into integration — `collab_lane_drop`.
- Keeps the integration branch able to receive collection by merging current persistence back into
  it through a lane, when persistence has moved ahead of integration — `collab_integration_reconcile`.
- Land: moves the exact current integration result into a persistence branch, preserving the
  integration tree under a new commit identity — `collab_integration_land`.
- Retire the lane, at task scope: tears down the managed integration and its remaining lanes once
  the task's collab-owned state is no longer needed — `collab_integration_remove`.
- Read-only inspection of a task's integration and lane state; supports every step above without
  mutating anything — `collab_status`.
- Snapshot task state and telemetry to fixed report artifacts, with no cleanup or readiness
  judgement performed — `collab_report`.
