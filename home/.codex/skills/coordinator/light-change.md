# Light change

Reached from the coordinator's [Light change](SKILL.md#light-change) section. One implementer writes the
change on `light/<slug>`; you write its brief and merge it.

## Brief

Write `scratch/<slug>/brief.md` in the map:

- **Source**: the ruling, decision, or bug report the change carries out, quoted or linked.
- **Change points**: each file and function to change, and what it becomes.
- **Verification**: the tests to add or run, with the repository's red-green rule when behaviour
  changes.
- **Delivery**: branch `light/<slug>` from the branch it merges into; report when the gates pass.

## Run

1. Start one implementer on a clean context in your own herdr workspace and send it the brief path.
   When a start fails or a name is lost, find the first implementer with `herdr agent list` before
   starting a second writer.
2. A later ruling on the same files goes to the same implementer: update the brief and `steer` it
   there.
3. On its report, check the merge with `git merge-tree --write-tree <target> light/<slug>`. When it
   conflicts, steer the implementer to merge the target into its branch and finish the conflict
   commit with `git commit --no-edit --cleanup=strip`, so trailers stay last. When it is clean,
   `git merge --no-ff light/<slug>` and run the tests the change affects.
4. While a task-flow task runs its final full gates against the same target, hold merges until they
   finish.

A light change is done when its branch is merged, the affected tests are green, and its branch,
its worktree with each parent directory left empty, and `scratch/<slug>/` are deleted.
