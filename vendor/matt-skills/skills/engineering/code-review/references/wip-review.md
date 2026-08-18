# WIP advisory review

Use this branch only when the intended subject includes staged, unstaged, or non-ignored untracked
files. A WIP snapshot has no immutable commit identity, so its output is advisory even when the
snapshot stays stable throughout review.

## Capture

The caller or execution environment owns snapshot creation and cleanup. It provides an isolated,
read-only snapshot path; code-review neither mutates the source checkout nor chooses an isolation
mechanism.

Capture these facts together:

- `fixed_sha`: the user-supplied comparison point resolved to a full commit SHA.
- `source_head`: the source checkout's full `HEAD` SHA.
- `base_sha`: the merge-base of `fixed_sha` and `source_head`.
- `snapshot_tree`: a Git tree OID for the isolated snapshot.

The snapshot includes `source_head`, staged changes, unstaged tracked changes, and non-ignored
untracked files. It excludes ignored files, Git metadata, and environment caches. Compute
`snapshot_tree` with a temporary Git index so neither the source nor snapshot index changes.

Read the source state immediately before and after capture. If `source_head`, index, tracked changes,
or non-ignored untracked files changed during capture, discard the snapshot and capture again.

Capture is complete when one isolated path resolves to the recorded `snapshot_tree` and the source
state remained unchanged across capture.

## Review

Review `git diff <base_sha> <snapshot_tree>` from the isolated path. Give each fresh, read-only
reviewer the four identities above, the path, the diff command, and the same Standards or Spec input
used by the fixed-candidate process.

Begin the aggregate report with:

```text
Mode: WIP advisory
Fixed point: <fixed_sha>
Comparison base: <base_sha>
Source HEAD: <source_head>
Snapshot tree: <snapshot_tree>
```

Recompute the isolated snapshot tree after both reviewers finish. A mismatch means the reports no
longer describe one subject: discard them and recapture instead of choosing one result. Label the
result advisory throughout; do not translate it into a fixed-candidate report or Acceptance verdict.

Review is complete when both axes name the same stable `snapshot_tree`, the advisory label is
visible, and the caller has either performed its owned cleanup or retained the snapshot deliberately.
