# Admission standard

`standard_version: 3`. Cite this number when reporting which checks a task was admitted under; it
is maintained by hand, so a report that needs certainty cites the Git subject as well.

These are the sole normative S0–S5 checks for dev-flow. Every check is decided from artifacts,
not persuasion. Routing skills, runtime bindings, planners and reviewers reference this file and
do not restate its policy.

## S0 — Design admission: Need → Design → Slicing → Triage

S0 governs admission of new design work. It runs as a four-stage sequence — Need, Design, Slicing,
Triage — in that order; each stage's output is what the next stage designs, slices or triages.
`S0` remains the cross-reference anchor for the whole sequence.

Purely decision-only tasks (no implementation output) and small corrections completed within
Root's single context do not need the full sequence. They still owe the Envelope slot in the task
record a value — see Need below — it is never left blank.

### Need

Before designing, record the smallest current observable user-visible need and its usage envelope,
and ground the design in that observable rather than in hypothetical robustness. The envelope is
agreed with the current user, not inferred: confirm the expected behavior, the usage scenarios and
which cases are out of envelope before designing. If they cannot be confirmed, stop and ask; do not
design past the gap.

Record the agreed envelope in the task record's `Envelope` section, or point that section at the
artifact that carries it (for example a frozen `spec.md`). This landing point is the evidence
downstream stages use to reject an out-of-envelope finding: S3 already requires `contract_basis`
against a closed blocking enum, but that gate only holds when the envelope has somewhere to point.

### Design

Generate the smallest complete end-to-end design that satisfies the need, starting from the need
itself rather than from what already exists. Carry forward an existing mechanism only when it is
the smallest way to satisfy the current need, not because it is already there.

Module depth is a deliverable of this stage, produced deliberately, not a side effect discovered
during implementation. For the vocabulary and technique for designing a deep Module, see
[`codebase-design`](../../codebase-design/SKILL.md); S0 does not restate it.

### Slicing

Deliver one usable tracer through the whole required path before deepening any one Module, then
advance slice by slice — never big-bang. Depth on a single Module waits until the tracer shows the
usable whole cannot be correct without it.

### Triage

Both questions below are asked about something that has actually been observed. A case that exists
only as speculation is not triaged at all: it is neither built nor backlogged.

For each admitted requirement, ask two questions:

1. Is it common in the expected usage scenarios?
2. Did the current user ask for it?

When the answer to both is no, give it the simplest correct handling in the current Contract — a
clear refusal, a fast-fail or a report all qualify — and send the more elaborate treatment to the
backlog instead of building it now.

Guardrail: the simplest handling must itself be safe — it must preserve current data and current
authority. When no safe simple handling exists, the case is not "rare, therefore simple"; it is a
current correctness gap and stays in the current Contract.

Candidate-backlog's hard gates are the sole authority for backlog eligibility, required fields and
lifecycle; S0 does not restate them. An edge returns from backlog only through explicit planning,
after frequency, impact or a real resumed scenario makes it part of a current minimum need.

## S1 — Slice admission

- **S1.1 Observable sentence, bound to its oracle.** Record one sentence: “the user does X at
  `<production entrypoint>` and sees Y.” If it cannot be written without naming internal objects,
  refuse the Slice.

  Then say how the Slice's oracle reaches that entrypoint. Naming an entrypoint is free; the check
  is whether the evidence will be taken there. An oracle that proves a **stand-in** — a factory
  rather than the production composition that ships, a message substring rather than the exact type,
  a decoded value rather than the bytes that actually cross the boundary — passes while the shipped
  path stays broken, and the gap surfaces only after the Contract is written and the rework budget
  is half spent. Refuse the Slice when the binding cannot be stated.
- **S1.2 Named deletion.** Name at least one existing production `file:symbol` deleted by the
  Slice. A first seam may say `deletes: none` once per task and names the predecessor's deleting
  Slice.
- **S1.3 Size.** Estimated non-test production diff is at most 1500 lines; otherwise recut before
  dispatch.
- **S1.4 Independently landable.** The Slice is useful and testable without a later Slice and its
  first accepted checkpoint is days, not weeks, away.

## S2 — Invariant admission

- **S2.1 Observability.** Name the difference a user or client outside this Module observes when
  the invariant is violated. An internal-only difference is hardening and is not Contract work.
- **S2.2 Red evidence.** A focused test must be red without the device and red for that specific
  missing behavior. Record the command and observed reason.
- **S2.3 Envelope.** The violating scenario must be inside the frozen usage envelope. A test that is
  red against a stand-in rather than against the production path is not S1.1 evidence, whatever it
  proves about the stand-in.
- **S2.4 Lane-ready test review.** Before collect, Root binds the exact clean lane-ready SHA and
  reads each Contract commit's test, fixture and adapter diff plus its red evidence before reading
  implementation. For timing, locking, retention, replay, security, data-loss and concurrency
  invariants, Root personally reruns the focused red command at the exact pre-implementation
  Contract SHA in an isolated checkout. A test correction that preserves observable behavior,
  public Interface, envelope and acceptance surface uses an independent amendment commit; a
  semantic change requires lane re-admission.

## S3 — Machine rework admission

- Root keeps one monotonic `Machine rework: N/2` prose line in the active Slice ticket's Current
  section before a Standards or Spec production correction.
- Contract-only correction, backlog, decision blocking and rollout correction do not increment it.
- A proposed third production correction is a scope event. Recut at S1 or report it; never dispatch
  `Machine rework: 3/2` and never add another counter store.

Recutting resets that counter, because the recut Slice is a new ticket. Nothing here survives that
reset: a need re-cut five times has spent five admission and dispatch cycles, and no check in this
standard fires on it. Whoever notices reads the lane history and notices it themselves.

- **Active lane reminder.** Orchestrate's ninth warning counts only current active lanes whose
  projected `uncollected` count is greater than zero. Untouched lanes and pending lanes with
  `uncollected == 0`, plus collected, closed, dropped, and historical lanes, do not count. Pending
  remains independent and unbounded; creation still succeeds, and this factual warning is not a
  durable admission or closeability policy.

Blocking is a closed enum: `spec_violation | data_loss | security |
reproducible_behavior_failure` within the frozen envelope. Every blocker has `contract_basis`;
without one it is backlog. A missing product or policy decision is `blocked_on_decision`. A bounded
delta is reviewed by one reviewer on its originating axis.

## S4 — Review and validation

- The shared gate order is **canonical tests → ReviewGate** on one managed acceptance snapshot.
- Root binds the exact clean detached acceptance path, HEAD, tree and base…subject diff. Integration
  may advance without changing or invalidating that snapshot.
- Standards and Spec reviewers are read-only, report their axis and exact SHA, and never mutate the
  acceptance checkout. Each writes that same report to one `Report path` Root binds to its axis and
  exact SHA outside that checkout; the file is its only write and becomes evidence when Root accepts
  it. Root records the verdict, counts and both paths in the receipt it already writes, and does not
  restate the reviews — an axis is heard in its own words or not at all.
- A passing agent-verifier result records ReviewGate authority for that exact snapshot. A bounded
  delta uses only its originating axis.

Each accepted increment closes by bringing the task record with it. The record is the only
authority a compacted session inherits, and a `Current` naming a frontier three increments behind
reads as correct while being wrong — the failure mode that made this step explicit. Four mechanical
actions, in order:

1. Update `INDEX.md`'s `Current` and `Next` to the accepted state, then run `refresh`.
2. Move the receipts `refresh` names out of `Current` and `Next`, into the artifact of the gate
   that produced them.
3. Verify automatic clean closure for every named lane attempted by agent acceptance. Any retained
   lane and its warning remain an active current-task finding and require explicit correction or
   `lane drop` before closeout; do not unconditionally drop lanes.
4. Clear the temporary directories and test basetemps this increment created.

**What this stage owes is named by `refresh` and the locating output, not by a list written here.**
That is deliberate: a hand-kept checklist in this file would grow with every remembered incident
and still miss the one that mattered, while the instruments report the actual record in front of
you. If they name nothing, there is nothing to move.

Steps 3 and 4 are orchestrate's and the repo's own contracts; run them there and do not restate
their policy in the task record.

## S5 — Landing and close-out

- Landing requires current user authority and targets the exact reviewed candidate Git ref.
- The target is an ancestor of integration and follows the last landed target. Landing is one
  squash commit whose persistence tree exactly equals the target tree; never cherry-pick, rebase,
  reset or merge-commit the target. Integration remains append-only.
- A partial landing never cleans task state. Final landing requires the clean current integration
  tip, every generic ticket closed with recorded final state, a successful current-version
  task-record `refresh` (or a recognized confined legacy bridge), exact
  candidate/landing/topology/tree checks and any task-specific rollout checklist closed.
- Generic task-record `archive` is a neutral move and never implies completion. Each landing,
  archive and cleanup mutation requires current user authority at its own gate. Protect and recheck
  pre-existing dirt and non-task evidence. Never push.
