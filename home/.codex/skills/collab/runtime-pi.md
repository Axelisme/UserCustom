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

Launch subagents asynchronously so the caller can continue independent work. In an interactive
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

## Bounded composition

Collab leaves workflow shape to the caller. An optional worker → fixed-subject reviewer → bounded
correction loop can be expressed with `runs.run` and `runs.all`, or as successive background
workflows when the next brief depends on Caller judgement. The caller supplies the bounded brief,
delegated Acceptance criteria, and escalation boundary; fresh read-only reviewers inspect the exact
subject; one writer applies accepted bounded corrections.

A scope, architecture, authority, or contract question terminates the loop back at the caller.
Subagent output, mission state, telemetry, and completion status are observations rather than
collection or landing authority. The runtime provides placement and control mechanics; it does not
mandate the workflow or acquire Caller judgement.
