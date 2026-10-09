# Task flow runtime operations

Tool schemas own parameters and return shapes. This file maps each task-flow step to its operation.
A missing tool blocks the step; report the missing capability instead of substituting another
mechanism.

## Branch names

Integration is `wave/<task-id>/integration` at `.agent_state/worktrees/<task-id>/integration`. A
lane is `wave/<task-id>/<ticket>`, branched from integration. Both runtimes use these names, so
either can pick up the other's task.

## Pi

| Step | Operation |
|---|---|
| Create integration | `collab_integration` `create`, from the session's checked-out target branch |
| Create stacked integration | `collab_integration` `create` with `repo` set to the base task's integration worktree |
| Pull persistence (target drift or base) | `collab_lane` `reconcile_persistence`, then gate and collect that lane |
| Retarget a stacked task | `collab_integration` `retarget` with `persist` set to the target branch |
| Create a lane | `collab_lane` `create`, then the repository's declared worktree bootstrap if any |
| Collect | `collab_lane` `collect`. `reconciled` means integration moved: rerun gates on the lane, then collect again. `conflicted` returns to you |
| Drop a lane | `collab_lane` `drop` |
| Steer or stop an implementer | `control_subagent` `steer` or `terminate` |
| Observe state | `collab_status` for integration and lanes; `query_subagent` `status` for live children |
| Land | `collab_integration` `land` |
| Remove after landing | `collab_integration` `remove`; `integration_in_use` means a stacked task has not retargeted yet |

Collect and drop delete untracked files in the lane. Move anything worth keeping to `scratch/` first.

## Claude

The `collab_*` tools are absent; use native Git with the same names.

- Create integration: `git worktree add -b wave/<task-id>/integration <path> <target>`.
- Create stacked integration: the same command with `wave/<base-id>/integration` as start point.
- Pull persistence: create a lane, merge the target branch (or the base's integration) into it, gate,
  and collect. Retargeting needs no command: after the base lands, pull from the target branch.
- Create a lane: `git worktree add -b wave/<task-id>/<ticket> <path> wave/<task-id>/integration`.
- Collect: in the integration worktree, `git merge --ff-only <lane-branch>`. When it refuses, merge
  integration into the lane, rerun gates there, then retry. Remove the lane worktree and branch.
- Land: in the main checkout on the target branch, `git merge --no-ff wave/<task-id>/integration`.
  Stop on staged changes or files the merge would overwrite; leave unrelated local work untouched.

## Dispatch

Both runtimes dispatch through the herdr subagent tools; Claude reaches them as the
`mcp__subagents__*` MCP, which requires a Herdr pane.

- `spawn_subagent({ cwd: <lane>, role: "task-implementer", dispatch })`. A correction after the
  child returned its result is a fresh spawn; a change while the child is live is a
  `control_subagent` `steer`.
- A question arrives as a decision notification; answer with `control_subagent` `reply`.
- `FAILED` means the process ended without a result. Inspect the lane, then `control_subagent`
  `resume` or dispatch fresh.
- Pi: a child's result arrives as a notification that starts a new turn; after dispatching, end the
  turn.
- Claude only: after each spawn and after handling notifications, call `wait_subagent_events` with
  every received `notification_id` in `ack`, then end the turn.
