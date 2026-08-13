# Collab — Pi runtime

Verified against `pi-subagents` 0.47.1. Check the installed package before trusting runtime-specific
placement details; Collab's core guidance remains runtime-neutral.

## Placement

Discover the live profiles with `subagent({ action: "list" })`, then select only an executable,
non-disabled agent. Execute every placement through `workflowScript`: use one stable-key
`runs.run(...)` for one child and `runs.all(...)` for parallel read-only placements. Keep execution
and management separate — a call with `workflowScript` omits `action`; status, steering, stopping,
and other controls use `action` without execution fields.

Use `context: "fresh"` for independent review. Use `context: "fork"` only when the child should
inherit the persisted parent conversation; it is not a filtered review context. A profile's configured
default applies when the call omits context.

One writable checkout still has one live writer. `worktree: true` creates a managed isolated
worktree for a writing child when the source checkout is clean. Parallel reviewers may remain
read-only; parallel writers each need their own worktree.

## Background execution and control

Launch subagents asynchronously so the Orchestrator can continue independent work. In an interactive
session, return control or use the active goal's yield mechanism and let completion wake the session.
Use `subagent_wait` only when the current request must finish in the same turn; waiting does not make
a child more authoritative.

Inspect a run with `subagent({ action: "status", id })`. Guide a live top-level run with
`action: "steer"`, stop it with `action: "stop"`, and revive a failed, paused, or completed run with
`action: "resume"` when its persisted session is available. Prefer resume before replacement.
Inside a later workflow, a retained completed child may continue through
`runs.run(key, { resume: runId, task })`; use the latest returned run id for another continuation.

Turn, tool, runtime, and usage budgets are optional controls rather than role-wide defaults. A turn
budget first asks the child to wrap up and then allows its configured grace turns. Do not use a tight
budget as a mutation-safe checkpoint: after a writing run is interrupted, inspect its changed files,
tests, and commit state before choosing the next owner.

## Operations

Placement, collection, and landing are carried out through the `collab_op` tool's `method`
parameter. `integration_adopt` accepts `dry_run: true` to preview the adoption it would perform;
preview it before authorizing the mutation, per the preview-before-mutation discipline the core
points to. No other method in this set takes `dry_run`.

- `integration_create` — establishes the task-local integration branch collection needs before any
  lane can be collected into it.
- `integration_adopt` — the Collection boundary's adoption step: makes an existing branch, passed
  as `source_branch`, the complete managed integration state. Preview with `dry_run: true` before
  authorizing.
- `lane_create` — Place the writer: creates the one writable branch, checkout, worktree, and
  lane-owned state a dispatched writer needs.
- `lane_reconcile` — Collect's lane-side prerequisite: synchronizes a stale lane with current
  integration before that lane's subject can be collected.
- `lane_collect` — Collect: moves an Orchestrator-accepted lane subject into the integration branch
  and retires the lane when clean.
- `lane_drop` — Retire the lane: removes a lane's managed branch and worktree without collecting
  it, for a lane whose subject is not going into integration.
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

## Bounded composition

Collab leaves workflow shape to the Orchestrator. An optional worker → fixed-subject reviewer → bounded
correction loop can be expressed with `runs.run` and `runs.all`, or as successive background
workflows when the next brief depends on Orchestrator judgement. The Orchestrator supplies the bounded brief,
delegated Acceptance criteria, and escalation boundary; fresh read-only reviewers inspect the exact
subject; one writer applies accepted bounded corrections.

A scope, architecture, authority, or contract question terminates the loop back at the Orchestrator.
Subagent output, mission state, telemetry, and completion status are observations rather than
collection or landing authority. The runtime provides placement and control mechanics; it does not
mandate the workflow or acquire Orchestrator judgement.
