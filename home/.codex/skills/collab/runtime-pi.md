# Collab — Pi runtime

Verified against `pi-herdr-subagents` at commit `486a527`. Check the installed package before
trusting runtime-specific placement details; Collab's core guidance remains runtime-neutral.

## Routing

Read only the section named for the step you are taking.

- **Managed lane environment** — after canonical lane creation succeeds and the repository declares
  a worktree bootstrap: establish its dispatch precondition and lane-lifetime ownership.
- **Dispatch** — the canonical branch: launch one role onto one lane.
- **Results and decisions** — how a child's outcome and questions reach you.
- **Post-launch** — after launching a child: the ordinary return-or-yield step that lets a terminal
  notification wake the session.
- **Run control** — only when a run is interrupted or needs status, steering, or stopping.
- **Placement** — only when the canonical lane placement does not fit the chosen shape.
- **Collection** — only after the Orchestrator judges the lane and chooses collection.
- **Operations** — only when selecting which `collab_*` tool carries out a Collab step.

## Managed lane environment

Read this section after `collab_lane` with `action: create` succeeds when the repository declares a
worktree bootstrap. Apply that repository-owned contract to the exact managed lane before
dispatching. Successful bootstrap and presence of the ordinary-path environment are preconditions
for dispatch; if either is observed to fail, report `BLOCKED` and stop there; the Orchestrator
decides what follows.

After the precondition succeeds, roles consume the provisioned environment through their exact
dispatched execution parameters without syncing or provisioning it. Keep the runtime as lane-owned
state through implementation, correction, review, and owner-decision waits. Existing `collab_lane`
retirement (`collect` or `drop`) removes it with the lane; no separate runtime cleanup operation is
introduced.

Follow this canonical positive path without speculative guards or negative probes. If a concrete
observation exposes environment mis-selection, return it to the Orchestrator for a separate
control-strength decision before adding enforcement.

## Dispatch

`spawn_subagent({ cwd, role, dispatch })` launches one child and returns a `subagent_id`. `cwd` is
the exact managed lane worktree, `role` names a profile, and `dispatch` is the whole bounded brief.
Every call creates a new durable subagent, so a correction, a rereview, and a replacement are each
their own spawn — there is no resume-with-a-new-brief.

The profile owns the child's models and tools, and the tool schema rejects caller-supplied model,
effort, profile, tool, extension, path, and session fields. There is nothing to omit and no override
to authorize.

Role profiles live at `~/.pi/agent/herdr-subagents/profiles/<role>.md`; Collab ships
`collab-implementer` and `collab-acceptor` there. `control_subagent({ action: "roles" })` returns
the current valid role ids without restarting the session. An empty or missing profile directory
exposes no roles at all, so an unknown-role failure on a first spawn means the registry, not the
brief.

**Both tools exist only inside a Herdr pane** — the package registers them only when the session has
`HERDR_ENV=1` and a non-empty `HERDR_PANE_ID`. When they are absent, dispatch is unavailable: report
`BLOCKED` naming the missing capability and stop. Do not substitute a handwritten loop or another
runtime's mechanism.

## Results and decisions

A child reaches you as an attributed notification carrying one of three outcomes:

- `COMPLETED` with an optional `message` — the declared result. Residual risks ride in `message`.
- `BLOCKED` with a `blocker` — the declared stop, in prose.
- `FAILED` with a `reason` — manager-derived, never submitted by the child. The process ended
  without declaring a result.

`FAILED` is not a verdict on the work. Its durable state is `interrupted`, so
`control_subagent({ action: "resume", subagent_id })` relaunches the same attempt against the exact
session file and the child can still declare a result afterwards. Judge whether resuming or
replacing is right from the lane's actual state, not from the notification alone; Collab's core owns
that judgement.

A child asks a question through `contact_parent`, which reaches you as a decision notification with
a `request_id`. Answer it with `control_subagent({ action: "reply", subagent_id, request_id, answer })`
and the child continues on the same context. A question is never a result branch: a child that
submitted `BLOCKED` to ask something has already ended, and the answer has nowhere to land.

Durable state stays authoritative when a notification is missed or the session was inactive; read it
with `control_subagent({ action: "status" })` rather than assuming silence means still running.

## Post-launch

Read this section after launching a child, when the Orchestrator continues independent work before
completion wakes the session.

Launch asynchronously so the Orchestrator can continue independent work. In an interactive session,
return control or use the active goal's yield mechanism and let the terminal notification wake the
session. Blocking on a child does not make it more authoritative.

After a terminal handoff, if the lane's writer owned any Acceptance claims in the assigned
`ticket.md` — the claims naming no other observer — reread that exact ticket before final Acceptance
judgement, Resolution, lifecycle state, or task-progress reconciliation. Read only the assigned
ticket. That reread is where the Orchestrator rebuilds the Acceptance list from what each claim's
deciding observer reported, rather than from the writer's checkboxes.

## Run control

Read this section only when a run is interrupted or needs status, steering, or stopping.

`control_subagent({ action: "status" })` lists the ids running in this session. Guide a live child
with `action: "steer"`, relaunch an interrupted one with `action: "resume"`, and end one with
`action: "terminate"`. After a writing child is interrupted, inspect its changed files and commit
state before choosing the next owner.

## Placement

Read this section only when the canonical lane placement does not fit the chosen shape.

For a gates-only lane, spawn `collab-implementer` onto the exact managed lane worktree. This lane
has no reviewer, so the direct writer dispatch is not a handwritten worker/reviewer loop. After the
writer stops, an in-scope correction is another ordinary spawn onto the same lane, and the
Orchestrator judges the writer's mechanical-gate result before collection.

Parallel reviewers may share a read-only lane; parallel writers each need their own writable
checkout.

## Collection

Read this section only after the Orchestrator judges the lane and chooses collection.

`collab_lane` with `action: collect` carries its own stale-lane behavior and is the default
collection path. A `collected` result completes collection. A `reconciled` result stops before
collection: apply the core lane-reconciliation placement test to the reconciled protected current
lane, have the Orchestrator judge again, and only then retry collection. Where that test places a
reviewer, spawn a fresh `collab-acceptor` onto the reconciled lane with a brief saying so. A
`conflicted` result returns to the Orchestrator. `collab_lane` with `action: reconcile` remains
available but is not an extra default pre-step.

## Operations

Read this section only when selecting which `collab_*` tool carries out a Collab step. Each tool is
independently registered; its own description and parameter schema are authoritative for what it
accepts and returns. This section states which Collab step selects each tool and owns the dirt,
file-handling, and managed-worktree removal contracts.

Generic Collab dirt means staged or unstaged tracked changes. Ordinary untracked and ignored paths do
not by themselves block cleanliness checks or produce dirt, presence, preservation, status, or report
warnings, except that landing requires no ordinary untracked state before mutation; active
merge/conflict state and unclassifiable Git state retain their explicit protections.

File handling follows the Git operation used or modeled. Merge-backed reconciliation and stale
collection retain native `git merge` collision behavior. Ready collection uses native
`git reset --hard`, which preserves non-obstructing untracked or ignored paths and may delete either
kind when it must write a tracked path. Landing creates a non-fast-forward merge commit in the
persistence checkout via `git merge --no-ff`, verifies the resulting tree equals the accepted
integration tree, then advances both the persistence and integration branches to that commit.
Landing requires no staged, no unstaged tracked, and no ordinary untracked persistence state before
mutation; ignored files are allowed and path collisions follow native merge behavior. Hooks execute
natively and any merge or hook failure is reported as an actionable Git error exposing Git's
resulting state without synthetic publication or dirt-preservation rollback. Failure compensation
removes a newly created managed worktree with non-force `git worktree remove`, retaining the
resource when Git refuses; successful collection, lane drop, and task removal are explicit
retirements and use force removal. Freshness is determined by ordinary branch ancestry and shared
heads.

- Establishes the task-local integration branch collection needs before any lane can be collected
  into it — `collab_integration_create`.
- The Collection boundary's adoption step: makes an existing branch, passed as `source_branch`, the
  complete managed integration state — `collab_integration_adopt`.
- Manage the task lane — `collab_lane` with `action` `create` (branch and worktree at integration tip, optional `comment` only for create), `reconcile` (merge integration into lane), `collect` (fast-forward integration to lane tip and force-retire the lane worktree — untracked or ignored files there are lost, tracked dirt or merge conflict keeps the lane with a warning), `drop` (force-retire without collecting, discarding uncollected work and warning if dirty, conflicted or incomplete). Stale-lane handling is via `collect` or explicit `reconcile`; creation is the execution shape for a dispatched writer.
- The lane tool distinguishes collection (advances integration and retires the lane) from discarding uncollected work (drop without advancing), and both retire the lane worktree via force removal. It emits a custody warning when
  removal discards tracked or staged changes or active merge/conflict state. Unclassifiable Git state
  remains warning-worthy. This classification changes reporting only: best-effort removal and custody
  of unrecognized resources remain unchanged.
- Keeps the integration branch able to receive collection by merging current persistence back into
  it through a lane, when persistence has moved ahead of integration — `collab_integration_reconcile`.
- Land: creates a non-fast-forward merge commit in the persistence checkout whose first parent
  is the previous persistence head and second parent is the accepted integration head, verifies
  the commit's tree equals the accepted integration tree, then advances both the persistence and
  integration branches to that commit — `collab_integration_land`.
- Retire the lane, at task scope: force-removes the managed integration and its remaining lanes once
  the task's collab-owned state is no longer needed — `collab_integration_remove`.
- Read-only inspection of a task's integration and lane state; supports every step above without
  mutating anything — `collab_status`.
- Snapshot task state and telemetry to fixed report artifacts, with no cleanup or readiness
  judgement performed — `collab_report`.
