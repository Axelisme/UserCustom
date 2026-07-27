# Admission standard

These are the sole normative S1–S7 checks for dev-flow. Every check is decided from
artifacts, not persuasion. Routing skills, runtime bindings, planners, and reviewers reference
this file and do not restate its policy.

## S1 — Slice admission

- **S1.1 Observable sentence.** Record one sentence: “the user does X at `<production entrypoint>`
  and sees Y.” If it cannot be written without naming internal objects, refuse the Slice.
- **S1.2 Named deletion.** Name at least one existing production `file:symbol` deleted by the
  Slice. A first seam may say `deletes: none` once per task only, and must name the predecessor's
  deleting Slice.
- **S1.3 Size.** The estimated non-test production diff is **≤ 1500** lines; otherwise recut
  before dispatch.
- **S1.4 Independently landable.** The Slice is useful and testable without a later Slice; its
  first accepted checkpoint is days, not weeks away. A Slice failing any check is refused and
  recut before implementation.

## S2 — Invariant admission

- **S2.1 Observability.** Name the difference a user, or a client outside this module, observes
  when the invariant is violated. If it can only be stated in terms of internal objects, it is
  hardening: send it to `candidate-backlog` and do not put it in the Contract.
- **S2.2 Red evidence.** A focused test must be red without the device and red for that specific
  missing behavior; record the red evidence. Timing, locking, retention, and replay devices need
  a test that fails without the device.
- **S2.3 Envelope.** The violating scenario must be inside the frozen spec's recorded usage envelope.
  Anything outside it is hardening or a later spec decision, not a Contract invariant.

## S3 — Milestone admission

Before acceptance, run these artifact checks. They are answered from machine evidence, never
persuasion.

| # | Check | Query | Refuse when |
|---|---|---|---|
| 1 | Reachability | The production entrypoint import graph reaches the milestone's new modules | not reached |
| 2 | Deletion | `git diff --numstat <base>..<tip> -- <declared production paths>` shows deletions in non-test production files | 0 or production paths undeclared |
| 3 | Loop | `git log --grep="Collect Wave" <base>..<tip>` counted per Slice prefix | any Slice ≥ 3 |
| 4 | Mass | `git diff --numstat` top-10 single files plus a per-file reachability probe | any file proven not yet reachable > 2000 lines; missing per-file evidence is undetermined |
| 5 | Focus | Slice-attributed commit subjects over the last 3 days | every attributed commit is on one Slice |
| 6 | Burn-down | The task plan's Slice × status table exists and its current and previous digests differ | either digest missing or unchanged |
| 7 | Downgrade | Backlog items created ÷ review findings raised | approximately 0 (see S4.3) |

**S3.8 Stall.** Two consecutive reachability or deletion refusals stop implementation and report
 to the user. Do not dispatch the next Wave first.

## S4 — Machine rework admission

- **S4.1** `machine_rework_cycles` for one Slice is **≤ 2**. Increment once when a batched
  `simplify`, Standards review, or Spec review finding sends the candidate back to implementation;
  never once per finding.
- **S4.2** The third machine rework is a **scope event**, not an implementation event. Exactly three
  actions are legal: shrink the Slice (return to S1), downgrade the remaining findings to backlog,
  or report to the user. Opening another correction Wave on the same Slice is not legal.
- **S4.3** A review round producing **100% blocking** findings marks the spec `spec-too-wide` and
  returns to S1. A spec broad enough to give every finding a Contract basis has disabled the
  blocking enum.
- **S4.4** A `cost-alarm` is a scope signal. First shrink the Slice or report to the user.
  Assigning a cheaper writer to the same Slice is legal only after it passes S1.3 again.
- **S4.5 Provenance.** Every rework records one origin from the closed set
  `user_acceptance | simplify | standards_review | spec_review`. Initial simplify, backlog,
  `blocked_on_decision`, and user acceptance do not increment `machine_rework_cycles`. Provenance
  follows the finding even when the user later authorizes its fix.

Blocking is a **closed enum**: `spec_violation | data_loss | security |
reproducible_behavior_failure` within the frozen envelope. Every blocker carries
`contract_basis`; without one, classify it as backlog. A missing product or policy decision is
`blocked_on_decision`, not `needs_fix`. A bounded delta is reviewed by **one reviewer on the
originating axis**; do not reopen both axes for a local delta.

## S5 — Day acceptance

Day runs this shared machine order, without skipping a gate: **simplify → canonical tests →
ReviewGate**. ReviewGate is integration-first. Its review bracket records pre and post status for
the same path, branch, HEAD, and clean tree; no collect; no mutate is allowed inside the
bracket, and any mismatch invalidates evidence. Any capability fallback is handled by the
ReviewGate interface, not by duplicating policy in this standard.

- **S5.1 Gated checkpoint.** Open S5 only after simplify, canonical tests, and the ReviewGate
  pass. Bind all evidence to the exact reviewed SHA. Two fresh axes use the same exact SHA and
  same source. A bounded delta uses one reviewer on the originating axis. Present the reviewed
  exact SHA for user acceptance and record that checkpoint as not persistence-landed.
- **S5.2 Per-Slice exercise.** The user exercises the S1.1 sentence against the real entrypoint
  per Slice and accepts or rejects it. Acceptance does not mutate persistence and is not
  persistence-landed.
- **S5.3 Rejection.** Rejection returns the Slice to S1; do not increment
  `machine_rework_cycles`. The next candidate has a new exact SHA and reopens the required gates;
  later commits reopen the gates for that new tip, while historical exact-SHA evidence remains
  valid unless marked stale.
- **S5.4 Staleness.** Feedback outside the frozen usage envelope requires a spec amendment or a
  new Slice. It is not unbounded rework hidden under acceptance. Rejection makes dependent provisional checkpoints
  stale until rebuilt from a valid base.

## S6 — Night deferral

- **S6.1 Mode.** `mode_override = day | night | auto`; explicit override wins. In `auto`, a
  user-authored task turn is Day Mode and an autonomous continuation with an active goal and no live user turn
  is Night Mode. Inferred mode is recomputed and is not durable state.
- **S6.2 Queue.** Night Mode records each deferred S5 item in the current release phase record,
  using the planning-with-files phase template as the queue schema. `reviewed_awaiting_user` is
  provisional and never means accepted or landed. The queue is ordered from the latest accepted checkpoint.
- **S6.3 Depth.** The max speculative dependency depth is **10** from the latest accepted
  checkpoint. Independent pending Slices do not add chain depth. A later Slice must not overwrite
  a pending acceptance surface or make its scenario independently untestable.
- **S6.4 Drain.** Day Mode drains the queue oldest-first in dependency order. Same-SHA acceptance
  preserves machine evidence and continues from the integration tip without persistence mutation.
  Rejection returns to S1 and marks descendants stale.
- **S6.5 Landing.** Night Mode may defer S5 and continue bounded minimal Slices, but never lands;
  landing requires a live explicit user request.
- **S6.6 Append-only integration.** The task integration branch is append-only: never reset,
  rebase, or force-update it. Rejected or stale work is repaired by forward commits; historical
  exact-SHA evidence remains valid unless marked stale.

## S7 — Landing and close-out

- **S7.1 Authority.** Landing is permitted only with current user authority.
- **S7.2 Exact target.** The landing target is the exact SHA recorded as accepted.
- **S7.3 Topology.** The target is an ancestor of the integration tip, and the persistence tip is an ancestor of the target.
- **S7.4 Method.** Landing is fast-forward-only: no squash, no cherry-pick, no rebase, no merge commit,
  no reset, and no push.
- **S7.5 Partial landing.** A requested partial landing never performs task cleanup. It leaves
  the task integration worktree, refs, and phase records open; closed Waves need not retain role
  worktrees.
- **S7.6 Final landing.** Final landing requires every item accepted, no stale or unresolved row,
  and the target equal to the current clean integration tip. Then, and only then, remove the task
  integration worktree, role worktrees, integration branches, `refs/orchestrate/<task-id>`, and
  task phase records. Protect pre-existing user dirt and non-task evidence: inspect and prove that
  they are unchanged before and after cleanup. Never delete, stash, reset, overwrite, or include
  them in the task; include them in neither cleanup nor the landing target.
