# Collab — Pi runtime

Pi's binding delta, and nothing else; [Collab](SKILL.md) owns the policy. Verified against
`pi-herdr-subagents` at commit `1a8070f` — check the installed package before trusting placement
details here.

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
effort, profile, tool, plugin, extension, path, session, and id fields. There is nothing to omit
and no override to authorize.

Role profiles live at `~/.pi/agent/herdr-subagents/profiles/<role>.md`; Collab ships
`collab-implementer` and `collab-acceptor` there. `query_subagent({ action: "roles" })` returns
the current valid role ids without restarting the session. An empty or missing profile directory
exposes no roles at all, so an unknown-role failure on a first spawn means the registry, not the
brief.

**All three tools exist only inside a Herdr pane** — the package registers `spawn_subagent`,
`query_subagent` and `control_subagent` only when the session has `HERDR_ENV=1` and a non-empty
`HERDR_PANE_ID`. When they are absent, dispatch is unavailable: report `BLOCKED` naming the missing
capability and stop. Do not substitute a handwritten loop or another runtime's mechanism.

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

Durable state stays authoritative when a notification is missed or the session was inactive. Recover
it with exact-id `query_subagent({ action: "result", subagent_id })`, never the live-only `status`
listing. It returns `{ subagent_id, role, status, result, cleanup_note? }` without taking a lease,
acknowledging the notification, or touching the child, and stays readable after an ACK and after a
same-session reopen. A live child answers `NOT_TERMINAL`; an explicit termination that declared no
result answers `RESULT_UNAVAILABLE`.

## Post-launch

Launch asynchronously so the Orchestrator can continue independent work. In an interactive session,
return control or use the active goal's yield mechanism and let the terminal notification wake the
session. Blocking on a child does not make it more authoritative.

Yielding means you were away from the lane while it was written. Reread the assigned `ticket.md` —
only that one — when the terminal notification lands, so Collab's Acceptance judgement rebuilds from
what each claim's deciding observer reported rather than from what you remember dispatching.

## Run control

`query_subagent({ action: "status" })` lists this session's live children, each with its role,
lifecycle status, active model and effort, update time, explicitly reported progress, pending
decision, and most recent non-coordination tool activity. Terminal and interrupted children never
appear here; read those with `action: "result"`.

`query_subagent({ action: "inspect", subagent_id })` snapshots one exact child, ended ones included:
committed observation times, progress, pending decision, model and diagnostics, every running tool
call and the last completed one, with bounded argument previews. Reach for it to see what a child is
actually doing before steering or ending it.

Guide a live child with `control_subagent({ action: "steer" })`, relaunch an interrupted one with
`action: "resume"`, and end one with `action: "terminate"`. After a writing child is interrupted,
examine its changed files and commit state before choosing the next owner.

## Placement

For a gates-only lane, spawn `collab-implementer` onto the exact managed lane worktree. This lane
has no reviewer, so the direct writer dispatch is not a handwritten worker/reviewer loop. After the
writer stops, an in-scope correction is another ordinary spawn onto the same lane, and the
Orchestrator judges the writer's mechanical-gate result before collection.

## Collection

`collab_lane` with `action: collect` carries its own stale-lane behavior and is the default
collection path. A `collected` result completes collection. A `reconciled` result stops before
collection: apply the core lane-reconciliation placement test to the reconciled protected current
lane, have the Orchestrator judge again, and only then retry collection. Where that test places a
reviewer, spawn a fresh `collab-acceptor` onto the reconciled lane with a brief saying so. A
`conflicted` result returns to the Orchestrator. `collab_lane` with `action: reconcile` remains
available but is not an extra default pre-step.

## Operations

Each `collab_*` tool is independently registered, and its own description and parameter schema are
authoritative for what it accepts and returns. This section owns only what a schema cannot state:
which Collab step selects each tool, and the contracts cutting across all of them.

Select by step:

- `collab_integration_create` — establish the task-local integration branch, before any lane exists
  to collect into it. That worktree's attached branch becomes the task's persistence branch.
- `collab_integration_adopt` — the Collection boundary's adoption step: make an existing
  `source_branch` the complete managed integration state.
- `collab_lane` — `create` the lane for a dispatched writer, `reconcile` it against integration,
  `collect` it, or `drop` it uncollected.
- `collab_integration_reconcile` — merge current persistence back into integration through a lane,
  when persistence has moved ahead of integration.
- `collab_integration_land` — merge the accepted integration into persistence.
- `collab_integration_remove` — retire the managed integration and its remaining lanes at task
  scope, once the task's collab-owned state is no longer needed.
- `collab_status` — read a task's integration and lane state, mutating nothing.
- `collab_report` — snapshot task state and telemetry to fixed report artifacts, judging nothing.

Every tool resolves the acting repository from the session working directory unless `repo` names
another Git worktree root. Freshness is ordinary branch ancestry and shared heads.

**Dirt** means staged or unstaged tracked changes. Ordinary untracked and ignored paths raise no
dirt, presence, preservation, status, or report warning on their own; active merge/conflict state
and unclassifiable Git state keep their explicit protections.

Custody follows the Git operation used or modeled, which no schema states:

- `collect` fast-forwards integration to the lane tip, then force-retires the lane worktree through
  native `git reset --hard`: untracked and ignored files there are lost. Tracked dirt or a merge
  conflict keeps the lane instead, with a custody warning.
- `drop` force-retires without advancing integration, discarding uncollected work, and warns when
  the lane is dirty, conflicted, or incomplete.
- Landing requires no staged, no unstaged tracked, and no ordinary untracked persistence state
  before it mutates; ignored files are allowed. It verifies the merge commit's tree equals the
  accepted integration tree before advancing either branch.
- Merge-backed reconciliation and stale collection keep native `git merge` collision behavior. Hooks
  execute natively, and a merge or hook failure surfaces as an actionable Git error exposing Git's
  resulting state, with no synthetic publication and no dirt-preservation rollback.
- Failure compensation removes a newly created managed worktree with non-force `git worktree remove`
  and retains the resource when Git refuses. Collection, lane drop, and task removal are explicit
  retirements and use force removal.
