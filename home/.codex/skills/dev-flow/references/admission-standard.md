# Admission standard

These are the sole normative S1–S5 checks for dev-flow. Every check is decided from
artifacts, not persuasion. Routing skills, runtime bindings, planners, and reviewers reference
this file and do not restate its policy.

## S1 — Slice admission

- **S1.1 Observable sentence.** Record one sentence: “the user does X at `<production entrypoint>`
  and sees Y.” If it cannot be written without naming internal objects, refuse the Slice. Name the
  sentence's verifier, `user` or `agent`; Root decides which one applies and records the reason —
  no threshold is fixed in advance.
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

## S3 — Machine rework admission

- **S3.1** `machine_rework_cycles` for one Slice is **≤ 2**. Increment once when a batched
  `simplify`, Standards review, or Spec review finding sends the candidate back to implementation;
  never once per finding.
- **S3.2** The third machine rework is a **scope event**, not an implementation event. Exactly three
  actions are legal: shrink the Slice (return to S1), downgrade the remaining findings to backlog,
  or report to the user. Opening another correction lane on the same Slice is not legal.
- **S3.3 Provenance.** Every rework records one origin from the closed set
  `user_acceptance | simplify | standards_review | spec_review`, carried as the commit's `Origin:`
  trailer. Initial simplify, backlog, `blocked_on_decision`, and user acceptance do not increment
  `machine_rework_cycles`. Provenance follows the finding even when the user later authorizes its
  fix.

Blocking is a **closed enum**: `spec_violation | data_loss | security |
reproducible_behavior_failure` within the frozen envelope. Every blocker carries
`contract_basis`; without one, classify it as backlog. A missing product or policy decision is
`blocked_on_decision`, not `needs_fix`. A bounded delta is reviewed by **one reviewer on the
originating axis**; do not reopen both axes for a local delta.

## S4 — Acceptance

Every gate run follows one shared machine order, without skipping a step: **simplify → canonical
tests → ReviewGate**. ReviewGate is integration-first. Its review bracket records pre and post
status for the same path, branch, HEAD, and clean tree; no collect; no mutate is allowed inside
the bracket, and any mismatch invalidates evidence. Any capability fallback, and the simplify
self-correction boundary, are the ReviewGate and simplify interfaces' own policy — not restated
here.

- **S4.1 Gate trigger.** A gate run starts only when the integration tip carries a scenario that
  needs verification and is not yet reflected on the already-gated candidate — a new `pending`
  row, a repair's retest, or a row just marked `superseded` — and no gate run is already in
  flight. A lane whose every scenario is `verifier: agent` never triggers a gate by itself.
- **S4.2 Ready candidate.** `refs/orchestrate/<task>/candidate` names the exact gated SHA that has
  passed the shared machine order; every other property is derived and never persisted: worktree
  readiness is the acceptance worktree's HEAD equal to the ref, lag behind tip is
  `git rev-list --count ref..integration`, and the candidate timeline is that ref's reflog. The
  acceptance worktree is created once at task start; `candidate` only checks it out onto the gated
  SHA — the candidate is never persistence-landed by this step. A dirty acceptance worktree
  refuses the checkout, keeps the previous candidate ref unchanged, and reports the conflict
  instead of overwriting it.
- **S4.3 Queue and state.** Each deferred row carries one lifecycle field, `state`, not a
  status/result pair: `pending` moves to `passed | failed | blocked` on user exercise; `failed`
  moves back to `pending` when its repair lane collects; `passed` moves to `superseded` and then
  back to `pending` when a later lane touches its entrypoint; `passed` moves to `accepted` only on
  the user's confirmation of the repaired exact SHA. A `verifier: agent` row enters `passed`
  directly at creation and never joins the user's queue; that judgment is Root's, with the reason
  recorded, and no threshold is fixed in advance. The queue orders purely by dependency, oldest
  row first within a layer: what a scenario depends on already sorts ahead of it, and that is
  exactly the failure with the largest downstream cost, so priority needs no separate field.
- **S4.4 Repair is a lane.** Every acceptance finding is fixed by an ordinary lane carrying
  `Origin: user_acceptance`; it does not consume `machine_rework_cycles` and runs the shared
  machine order once collected, same as any other lane.
- **S4.5 Session stop.** Ending an acceptance session needs no reason and no closed enum. A
  partial drain — some rows tested, the rest left `pending` — is a normal end, not a failure
  requiring justification.

## S5 — Landing and close-out

- **S5.1 Authority.** Landing is permitted only with current user authority.
- **S5.2 Exact target.** The landing target is the exact SHA recorded as accepted.
- **S5.3 Topology.** The target is an ancestor of the integration tip, and the last landed SHA
  recorded on the persistence tip — or the persistence tip itself when it has landed nothing — is
  an ancestor of the target.
- **S5.4 Method.** Landing is a single squash commit that records the landed exact SHA, and the
  resulting persistence tree is identical to the accepted SHA's tree. No cherry-pick, no rebase, no
  reset, no merge commit. `integration land` enforces this: it refuses before mutating anything
  unless a dry-run tree check first confirms the squash would reproduce the accepted tree exactly.
- **S5.5 Append-only integration.** The task integration branch is append-only: never reset,
  rebase, or force-update it. Rejected or stale work is repaired by a forward repair lane;
  historical exact-SHA evidence remains valid unless marked stale.
- **S5.6 Partial landing.** A requested partial landing never performs task cleanup. It leaves
  the task integration worktree, the acceptance worktree, refs, and phase records open.
- **S5.7 Final landing.** Final landing requires every item accepted, no stale or unresolved row,
  and the target equal to the current clean integration tip. Then, and only then, archive task
  phase records through planning-with-files and remove their active task directory, the task
  integration worktree, the acceptance worktree, the integration branch, and
  `refs/orchestrate/<task-id>`. Protect pre-existing user dirt and non-task evidence: inspect and
  prove that they are unchanged before and after cleanup. Never delete, stash, reset, overwrite, or
  include them in the task; include them in neither cleanup nor the landing target.
