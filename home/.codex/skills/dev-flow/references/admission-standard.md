# Admission standard

These are the sole normative S1–S7 checks for dev-flow. Every check is decided from
artifacts, not persuasion. Routing skills, runtime bindings, planners, and reviewers reference
this file and do not restate its policy.

## S1 — Slice admission

- **Observable:** record one sentence: “the user does X at `<production entrypoint>` and sees Y.”
- **Deletion:** name at least one existing production `file:symbol` deleted by the Slice; a first
  seam may say `deletes: none` only once and must name its predecessor's deleting Slice.
- **Size:** estimated non-test production diff is at most 1500 lines; otherwise recut first.
- **Independence:** the Slice is useful and testable without a later Slice.
- The first accepted checkpoint is **days, not weeks** away.

## S2 — Invariant admission

An invariant enters the Contract only when its violation has an observable user/client effect,
a focused test is red for that specific missing behavior, and the scenario is inside the frozen
usage envelope. Internal-only hardening belongs in candidate-backlog. Timing, locking, retention,
and replay devices need a test that fails without the device.

## S3 — Milestone admission

Before acceptance, run the artifact checks for production reachability, declared deletion,
correction-loop count, file mass/reachability, Slice focus, changed plan digest, and backlog
downgrade. Two consecutive reachability or deletion refusals stop implementation and report to
the user.

## S4 — Machine rework admission

- Machine rework for one Slice is at most two cycles; a third is a scope event.
- Blocking is a **closed enum**: `spec_violation | data_loss | security |
  reproducible_behavior_failure` within the frozen envelope.
- Every blocker carries `contract_basis`. Without a contract basis, classify it as backlog.
- A missing product or policy decision is `blocked_on_decision`, not `needs_fix`.
- A bounded delta is reviewed by **one reviewer on the originating axis**; do not reopen both axes
  for a local delta. Cost alarms recut the Slice or report to the user.

## S5 — Day acceptance

Day runs the shared machine order **simplify → canonical tests → ReviewGate**, then presents the
reviewed exact SHA for user acceptance. ReviewGate is integration-first: its review bracket records
pre and post status for the same path, branch, HEAD, and clean tree; no `collect` or `mutate` is
allowed inside the bracket, and any mismatch invalidates evidence. Two fresh axes use the same
exact SHA and same source. A bounded delta uses one reviewer on the originating axis.

## S6 — Night deferral

Night runs the same **simplify → canonical tests → ReviewGate** order but defers S5 user
acceptance. Record the reviewed exact SHA as `reviewed_awaiting_user` in the phase deferred-row
schema; it is provisional, never accepted or landed. Day drains deferred rows oldest-first.
Night never lands and integration remains append-only.

## S7 — Final landing and cleanup

Landing requires current user authority, the exact accepted SHA, ancestor topology, and
fast-forward-only application: no squash, cherry-pick, rebase, merge commit, reset, or push.
Final close-out requires every item accepted, no stale or unresolved row, and the target equal to
the current clean integration tip. Then remove the task integration worktree, role worktrees,
integration branches, `refs/orchestrate/<task-id>`, and task phase records. Protect pre-existing
user dirt and non-task evidence: inspect and prove they are unchanged before and after cleanup;
never delete, stash, reset, overwrite, or include them in the task.
