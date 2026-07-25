# Admission standard

Decidable admission checks for dev-flow work. Every check is answered from artifacts — a
sentence that exists or does not, a number, a git query — never from argument. **A check that
needs persuasion has already failed.** A well-argued exception is the strongest evidence that
the check is doing its job.

Each role reads only its own section. The sections share one file so they cannot drift apart.

Incident of record: a 3-week effort produced 504 commits and +128,805 lines with zero
production-reachable behavior, then spent its last 3 days on 16 correction Waves of one
non-observable invariant. Every individual rule was obeyed. These checks are what was missing.

---

## S1 — Slice admission (Root, before cutting a Slice)

- **S1.1 Observable sentence.** Write one sentence: *"the user does X at `<production entrypoint>` and sees Y."* If it cannot be written without naming internal objects, **refuse the Slice**.
- **S1.2 Named deletion.** The Slice names at least one existing path it deletes on completion, as `file:symbol`. Pure addition accumulates unreachable code. **Once per task**, a seam-establishing first Slice may declare `deletes: none`, and must name the Slice that deletes its predecessor.
- **S1.3 Size.** Estimated non-test production diff ≤ 1500 lines. Over → split before dispatch, not after.
- **S1.4 Independently landable.** The Slice carries user-visible value without any later Slice. If its value only appears after a future cutover, it is not a Slice; it is half of one.

A Slice failing any check is recut. Recutting is cheap; the cheapest moment is now.

---

## S2 — Invariant admission (Oracle, before an assertion enters the Contract)

- **S2.1 Observability.** Name the difference a user, or a client outside this module, observes when this invariant is violated. If the answer can only be stated in terms of internal objects — descriptors, handles, cache entries, sequence numbers, ownership records — it is **hardening**: send it to `candidate-backlog` and do not put it in the Contract.
- **S2.2 Red evidence.** A test that is red without the device, red for its own specific reason.
- **S2.3 Envelope.** The violating scenario lies inside the frozen spec's recorded usage envelope.

```
admitted  "if this is violated, the user's save reports success and the file is absent"
refused   "if this is violated, a reused fd may observe a stale tombstone descriptor"
```

S2.1 governs `design-principles.md` #13: atomicity, ordering, resource lifetime, and
idempotency are interface decisions **only at the granularity a caller can observe**. Below
that granularity they are hardening, whatever they are called. The refused example above is a
real one; it consumed eleven acceptance cycles.

---

## S3 — Milestone admission (Root, machine-run before acceptance)

Run these. They are cheap, and unlike prose they cannot be reasoned with.

| # | Check | Query | Refuse when |
|---|---|---|---|
| 1 | Reachability | production entrypoint import graph reaches the milestone's new modules | not reached |
| 2 | Deletion | `git diff --numstat <base>..<tip> -- <declared production paths>` deletions in non-test production files | 0 or production paths undeclared |
| 3 | Loop | `git log --grep="Collect Wave" <base>..<tip>` — count per Slice prefix | any Slice ≥ 3 |
| 4 | Mass | `git diff --numstat` top-10 single files plus a per-file reachability probe | any file proven not yet reachable > 2000 lines; missing per-file evidence is undetermined |
| 5 | Focus | Slice-attributed commit subjects over the last 3 days | every attributed commit is on one Slice |
| 6 | Burn-down | the task plan's Slice × status table exists and its current and previous digests differ | either digest missing or unchanged |
| 7 | Downgrade | backlog items created ÷ review findings raised | ≈ 0 (see S4.3) |

**S3.8 Stall.** Two consecutive milestones with check 1 or 2 refusing → stop implementation
and report to the user. Do not dispatch the next Wave first.

---

## S4 — Machine rework admission (Root, when a machine finding sends work back)

- **S4.1** `machine_rework_cycles` for one Slice: **≤ 2**. Increment once when a batched `simplify`, Standards review, or Spec review finding sends the candidate back to an implementation pass; never once per finding.
- **S4.2** The third machine rework is not an implementation event, it is a **scope event**. Exactly three actions are legal: shrink the Slice (return to S1), downgrade the remaining findings to backlog, or report to the user. Opening another machine-finding correction Wave on the same Slice is not among them.
- **S4.3** If a review round produces 100% blocking findings, mark the spec `spec-too-wide` and return to S1. A spec broad enough to give every finding a contract basis has disabled the blocking enum.
- **S4.4** A `cost-alarm` is a scope signal. The first response is to shrink the Slice or report. Assigning a cheaper writer to the same Slice is legal only after the Slice has passed S1.3 again.
- **S4.5 Provenance.** Every rework records `origin: user_acceptance | simplify | standards_review | spec_review`. Initial simplify, backlog, `blocked_on_decision`, and user acceptance do not increment `machine_rework_cycles`. Provenance follows the finding even when the user later authorizes its fix.

---

## S5 — User acceptance (Root, before landing a Slice)

- **S5.1** The user exercises the S1.1 sentence against the real entrypoint and accepts or rejects it. This happens **per Slice**, not once per effort, and the evidence binds to the exact candidate SHA.
- **S5.2** Rejection returns the Slice to S1. User acceptance does not increment `machine_rework_cycles`: a person may discover incomplete feedback across several attempts, so attempts have no hard numerical cap.
- **S5.3** Feedback outside the frozen usage envelope is a spec amendment or a new Slice, not unbounded rework hidden under acceptance. A rejection makes dependent provisional checkpoints `stale` until rebuilt from a valid base.

---

## S6 — Deferred user acceptance (Root, at mode selection and Night checkpoints)

- **S6.1 Mode.** `mode_override = day | night | auto`; explicit wins. In `auto`, a user-authored task turn is Day Mode and an autonomous continuation with an active goal and no live user turn is Night Mode. Inferred mode is recomputed, not durable state.
- **S6.2 Queue.** Night Mode records each deferred S5 item in the current release phase record using planning-with-files' phase template as the storage schema. `reviewed_awaiting_user` is provisional and never means accepted or landed.
- **S6.3 Depth.** The max speculative dependency depth is 10 from the last accepted landing. Independent pending Slices do not add chain depth. A later Slice must not overwrite a pending acceptance surface or make its scenario independently untestable.
- **S6.4 Drain.** Day Mode processes the queue oldest-first in dependency order. Same-SHA acceptance preserves machine evidence and permits immediate per-Slice landing; rejection returns to S1 and marks descendants stale.
- **S6.5 Landing.** Night Mode may defer S5 and continue bounded minimal Slices, but it never defers the requirement itself and never lands without user acceptance.
