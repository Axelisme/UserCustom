# Collab — Pi runtime

Verified against `pi-subagents` 0.47.1. Check the installed package before trusting runtime-specific
placement details; Collab's core guidance remains runtime-neutral.

## Routing

Read only the section named for the step you are taking; every section after Composed delegation and
Typed results states its own enabling condition.

- **Composed delegation** — the canonical branch: dispatching the implementer and acceptor over one
  shared lane, including bounded corrections.
- **Typed results** — the worker and reviewer result schemas the canonical branch launches with.
- **Post-launch** — after launching an asynchronous workflow: the ordinary return-or-yield step
  that lets completion wake the session.
- **Run control** — only when a run is interrupted or needs status, steering, or revival.
- **Placement** — only when the canonical lane placement does not fit the chosen shape.
- **Collection** — only after the Orchestrator judges the reviewed lane and chooses collection.
- **Operations** — only when carrying out the named `collab_op` method.

## Composed delegation

For delegated closed work — bounded brief, delegated Acceptance criteria, placement, mutation
authority, and escalation boundary all closed — compose worker, reviewer, and bounded correction in
one asynchronous `workflowScript` over one Collab-managed lane. The default profiles are
`collab-implementer` and `collab-acceptor`. The Orchestrator supplies a finite correction budget per
composed workflow: initial implementation does not consume it, each `BLOCKED → writer correction`
transition consumes one, and exhausting it is a terminal seam that returns to the Orchestrator
without selecting a redesign procedure. Do not use turn, tool, or usage budgets as the correction
budget.

**Profile model contract.** The selected agent profile owns its configured `model` and `thinking`.
The Orchestrator preserves both unchanged, omitting `model` and `thinking` from the outer
`subagent(...)` options and every child call. Only a current user instruction that explicitly names
an override grants authority for that launch; task difficulty, retries, and review results grant
none. This contract is satisfied only when every workflow- and child-level `model` and `thinking`
field is absent or directly authorized by that instruction.

A Collab lane is already one writable checkout with one live writer. The delegated worker and its
reviewer share that lane as `cwd`, and neither initial call asks pi-subagents for a second writer
worktree around it: both state `worktree: false` explicitly. Every child call — initial
implementation, each correction round, initial review, and each rereview — states `agent`,
`cwd: lane`, `worktree: false`, `context: "fresh"`, the role's concrete `outputSchema`, and a
distinct stable key explicitly, and no call retains a previous `runId`. A correction launches a
fresh worker whose brief carries the original bounded contract plus the current typed blockers; a
rereview launches a fresh reviewer carrying the original review expectations against the changed
protected current lane. Run IDs remain runtime evidence for diagnostics; they are not continuation
handles and appear in no terminal projection. Every branch and terminal projection reads the child
result's `structuredOutput` — the parsed `outputSchema` value — never its `output` text.

The script below is the canonical recipe. `workerSchema` and `reviewerSchema` are the JSON Schema
objects defined under Typed results; `LANE` is the shared managed-lane `cwd`. `WORKER_BRIEF` names
the ticket — the ticket owns Outcome and Acceptance — and carries only the operational deltas a
brief needs: placement, mutation authority, validation expectations, stop conditions, and
role-specific deltas, without copying the ticket's prose.

`REVIEW_BRIEF` is a ticket pointer: it names the applicable delegated Acceptance identifiers and
carries the review operational deltas a review brief needs — placement, the acceptor's read-only
scope and authority, validation expectations, protected-lane and writer-stopped stop conditions,
lifecycle and cleanup ownership as applicable, role-specific deltas, and the optional task-boundary
pointer — without copying the ticket's prose.

```javascript
subagent({
  workflowScript: `
    const budget = CORRECTION_BUDGET;   // Orchestrator-supplied finite correction budget
    const lane = LANE;                  // one shared Collab-managed lane
    let writer = await runs.run("impl-0", {
      agent: "collab-implementer",
      cwd: lane,
      worktree: false,
      context: "fresh",
      task: WORKER_BRIEF,
      outputSchema: workerSchema
    });
    if (writer.structuredOutput.outcome === "NEEDS_DECISION") {
      return { outcome: "NEEDS_DECISION", why: writer.structuredOutput.decision.why, question: writer.structuredOutput.decision.question };
    }
    if (writer.structuredOutput.outcome === "BLOCKED") {
      return { outcome: "BLOCKED", blocker: writer.structuredOutput.blocker };
    }
    let reviewer = await runs.run("review-0", {
      agent: "collab-acceptor",
      cwd: lane,
      worktree: false,
      context: "fresh",
      task: REVIEW_BRIEF,
      outputSchema: reviewerSchema
    });
    if (reviewer.structuredOutput.verdict === "NEEDS_DECISION") {
      return { outcome: "NEEDS_DECISION", why: reviewer.structuredOutput.decision.why, question: reviewer.structuredOutput.decision.question };
    }
    let round = 1;
    while (reviewer.structuredOutput.verdict === "BLOCKED" && round <= budget) {
      writer = await runs.run("impl-" + round, {
        agent: "collab-implementer",
        cwd: lane,
        worktree: false,
        context: "fresh",
        task: "Round " + round + " correction within the original bounded worker contract: " + WORKER_BRIEF + " — current typed blockers: " + JSON.stringify(reviewer.structuredOutput.blockers),
        outputSchema: workerSchema
      });
      if (writer.structuredOutput.outcome === "BLOCKED") {
        return { outcome: "BLOCKED", blocker: writer.structuredOutput.blocker };
      }
      if (writer.structuredOutput.outcome === "NEEDS_DECISION") {
        return { outcome: "NEEDS_DECISION", why: writer.structuredOutput.decision.why, question: writer.structuredOutput.decision.question };
      }
      reviewer = await runs.run("review-" + round, {
        agent: "collab-acceptor",
        cwd: lane,
        worktree: false,
        context: "fresh",
        task: REVIEW_BRIEF + " — rereview the changed protected current lane",
        outputSchema: reviewerSchema
      });
      if (reviewer.structuredOutput.verdict === "NEEDS_DECISION") {
        return { outcome: "NEEDS_DECISION", why: reviewer.structuredOutput.decision.why, question: reviewer.structuredOutput.decision.question };
      }
      round += 1;
    }
    if (reviewer.structuredOutput.verdict === "BLOCKED") {
      return { outcome: "CORRECTION_BUDGET_EXHAUSTED", blockers: reviewer.structuredOutput.blockers };
    }
    return { outcome: "REVIEWED", validation: writer.structuredOutput.validation, residualRisks: writer.structuredOutput.residualRisks, outOfEnvelopeFindings: reviewer.structuredOutput.outOfEnvelopeFindings };
  `,
  async: true
});
```

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

No terminal outcome returns a run ID or other continuation handle: run IDs stay runtime evidence
for diagnostics, while Git, the lane runtime, and the Orchestrator own diff, commit identity,
cleanliness, and later coordination. Any later round — a correction, a rereview, or a
collection-time reconciliation review — launches a fresh compatible child with the full launch
controls above instead of resuming a run. The canonical launch is asynchronous; after launching,
the Post-launch section names the ordinary return-or-yield step that lets completion wake the
session.

## Typed results

The worker and reviewer result schemas are concrete JSON Schema objects owned here; core Collab and
the profiles express the same semantics without repeating the schema. A child configured with
`outputSchema` finishes through Pi's structured-output protocol instead of free-form Markdown, so
formatting cannot change control flow. The child result exposes the parsed schema value as
`structuredOutput`; its `output` field stays free-form text and never drives control flow, so the
recipe below branches on `structuredOutput` only. Use one structured result per child and do not combine it
with Pi's generic acceptance report: both default Collab profiles set `acceptance: { level: none,
... }` with a reason, and a launch needing another acceptance policy selects it explicitly.

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
non-disabled agent. Execute every placement through `workflowScript`: use one stable-key
`runs.run(...)` for one child and `runs.all(...)` for parallel read-only placements. Keep execution
and management separate — a call with `workflowScript` omits `action`; status, steering, stopping,
and other controls use `action` without execution fields.

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

Read this section only when carrying out the named method.

Placement, collection, and landing are carried out through the `collab_op` tool's `method`
parameter. `integration_adopt` accepts `dry_run: true` to preview the adoption it would perform;
preview it before authorizing the mutation, per the preview-before-mutation discipline the core
points to. No other method in this set takes `dry_run`.

- `integration_create` — establishes the task-local integration branch collection needs before any
  lane can be collected into it.
- `integration_adopt` — the Collection boundary's adoption step: makes an existing branch, passed
  as `source_branch`, the complete managed integration state. Preview with `dry_run: true` before
  authorizing.
- `lane_create` — Choose the execution shape: creates the one writable branch, checkout, worktree,
  and lane-owned state a dispatched writer needs.
- `lane_reconcile` — optional lane-side synchronization: brings a stale lane up to current
  integration when the Orchestrator explicitly chooses the separate pre-step. Collection normally
  relies on `lane_collect`'s stale-lane handling instead.
- `lane_collect` — Collect: moves an Orchestrator-accepted lane into the integration branch and
  retires the lane. Tracked modifications — staged or unstaged changes to tracked paths, including
  newly staged paths — and active merge or conflict state in the exact managed lane or integration
  worktree block collection and are preserved. Non-index state in those selected managed worktrees
  (untracked files, ignored files, ignored empty directories) is disposable and may be removed by
  collection. `collected` completes collection; `reconciled` stops before
  collection for rereview and a fresh Orchestrator judgement; `conflicted` returns to the
  Orchestrator.
- `lane_drop` — Retire the lane: removes a lane's managed branch and worktree without collecting
  it, for a lane whose work is not going into integration.
- `integration_reconcile` — keeps the integration branch able to receive collection by merging
  current persistence back into it through a lane, when persistence has moved ahead of integration.
- `integration_land` — Land: moves the exact current integration result into a persistence branch,
  preserving the integration tree under a new commit identity.
- `integration_remove` — Retire the lane, at task scope: tears down the managed integration and its
  remaining lanes once the task's collab-owned state is no longer needed.
- `integration_migrate` — housekeeping: brings a managed task's on-disk layout up to the running
  tool version; it serves no single semantic step and is resume-safe if interrupted.
- `status` — read-only inspection of a task's integration and lane state; supports every step above
  without mutating anything.
