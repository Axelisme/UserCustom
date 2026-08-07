# Orchestrate — admission

These are the normative S1–S5 checks for dispatched work. They ship with the package, so the
`skill_version` a task was admitted under is the version of these checks; there is no separate
hand-kept number to cite. Every check is decided from artifacts, not persuasion. Runtime bindings,
workers and reviewers reference this file and do not restate its policy.

Design admission before a Slice exists is dev-flow's S0, which owns the need, the frozen usage
envelope, and the task record those land in. S1 starts once there is something to dispatch.

## S1 — Slice admission

- **S1.1 Observable sentence, bound to its oracle.** Record one sentence: “the user does X at
  `<production entrypoint>` and sees Y.” If it cannot be written without naming internal objects,
  refuse the Slice.

  Then say how the Slice's oracle reaches that entrypoint. Naming an entrypoint is free; the check
  is whether the evidence will be taken there. An oracle that proves a **stand-in** — a factory
  rather than the production composition that ships, a message substring rather than the exact type,
  a decoded value rather than the bytes that actually cross the boundary — passes while the shipped
  path stays broken, and the gap surfaces only after the Contract is written and several corrections
  have been spent against it. Refuse the Slice when the binding cannot be stated.
- **S1.2 Named deletion.** Name at least one existing production `file:symbol` deleted by the
  Slice. A first seam may say `deletes: none` once per task and names the predecessor's deleting
  Slice.
- **S1.3 Independently landable.** The Slice is useful and testable without a later Slice and its
  first accepted checkpoint is days, not weeks, away.

### Citing evidence in the admission

The admission is the worker's brief, and every path it prints is a pointer the worker will follow.
A list of supporting report paths therefore reads as an instruction to open all of them: one
measured lane opened four axis reports, the frozen spec, the ticket and the record index — 70KB
before its first edit — beside an admission that already carried every conclusion it needed.

Carry the conclusion, and print a path only with the condition that reaches it: *if the admission
and the source disagree, the axis reports are in `<dir>`*. One conditional pointer replaces a list;
the reports stay available to the reader who needs them and stop recruiting the reader who does not.

There is no production-diff line limit. One existed and thresholded the wrong variable: the Slice
with the largest rework had the smallest production diff, while frozen Contract depth ordered the
same Slices monotonically. S2.8 thresholds that variable instead, and S1.3 with S0's Slicing stage
carry what size was standing in for.

## S2 — Invariant admission

Root records the validation mode here and the ticket carries it. `Validation mode: TDD` when a
reasonable production red oracle exists: the worker commits Contract tests, fixtures, and test
adapters before implementation, records focused red evidence, and keeps Contract paths protected by
normalized `Immutable:` trailers. `Validation mode: direct — <specific reason>` when no reasonable
production red state exists: the delivery is validated against a frozen acceptance surface without
fabricating Contract tests, fixtures, red evidence, or `Immutable:` trailers. File type never
selects the mode. Execution that changes the mode judgment stops and returns to Root for
re-admission; a worker cannot downgrade TDD to direct, and `lane check --expect-mode tdd` refuses
the lane that tried.

In TDD mode a Contract commit declares `Origin: contract` and the normalized `Immutable:` paths it
protects; an implementation commit declares neither, and `lane check` reports both projections. That
pair is what makes S2.5's first stop and S2.8 derivable from the lane's first-parent range rather
than from prose about it. A direct lane freezes no Contract commits, so neither check has a subject
there — S2.5 proves only its lane-ready state and S2.8 never fires.

### S2.1 — Observability

Name the difference a user or client outside this Module observes when
the invariant is violated. An internal-only difference is hardening and is not Contract work.

### S2.2 — Red evidence

A focused test must be red without the device and red for that specific
missing behavior. Record the command and observed reason.

### S2.3 — Envelope

The violating scenario must be inside the frozen usage envelope. A test that is
red against a stand-in rather than against the production path is not S1.1 evidence, whatever it
proves about the stand-in.

### S2.4 — Lane-ready binding

Before collect, Root binds the exact clean lane-ready SHA. A test
correction that preserves observable behavior, public Interface, envelope and acceptance surface
uses an independent amendment commit; a semantic change requires lane re-admission. Which of the
two a correction is, the originating axis reviewer decides — never the party proposing it. That
party is the one the preserving answer releases, and S3 already exempts contract-only correction
from its counter, so nothing else prices the choice.

### S2.5 — Root's mechanical guarantee

Root proves each stop the lane has by executing it at an
exact bound SHA, and holds the result rather than the diff that produced it. What runs is the
repository's own [gate script](gate.md) at `.agent_state/orchestrate/<task-id>/gate.sh`, so the
check set is written down once rather than reassembled from memory at each stop; only the
exit-code direction below is this standard's:

| stop | mode | expects | proven state |
| --- | --- | --- | --- |
| Contract frozen | TDD only | non-zero | the focused command is red, red for the named missing behavior, and free of collection, import, type and environment failure |
| lane-ready | both | zero | the declared selection is green and static checks over the changed paths are clean |

Neither depends on the invariant class. A green focused selection is not the lane-ready state:
the broader affected selection and the static checks belong inside the declared one, because a
focused green has passed while both were failing.

### S2.6 — No hand-derived expected value

A digest, identity, byte count, payload or protected
path that a Contract asserts is produced by the production code or by a script that computes it,
never rebuilt by hand — Root included. A hand-built expectation is indistinguishable from a
correct one until something recomputes it, so it enters the Contract wearing the authority of the
check it was supposed to be. `lane check` reports the protected paths it measured for this reason.

### S2.7 — Satisfiable together

The frozen assertions must be able to hold at once. An
unsatisfiable set is not caught by running it: a focused selection that feeds an assertion its own
output passes, and only a broader one exposes the contradiction. This is read, not executed, which
is why S2.8 sends it to an axis rather than to a command.

### S2.8 — Contract review

In a TDD lane, when more than 1000 test lines freeze before the first
production commit, the Contract is read on its own axis before implementation is admitted. The oracle is
what every later gate measures against and no later gate re-examines it, so a wrong oracle makes
every green after it meaningless. That reviewer is read-only at the exact Contract SHA and owes
an applicable correction, not a complaint. **The threshold is provisional** — it comes from three
Slices whose frozen depth ordered their rework monotonically (604 lines / 18 min, 1071 / 43,
1664 / 71) — so report what it cost or saved on this increment and propose a better one. The
depth is `lane check`'s `ticket_contract_added_lines`: the added lines across the Contract commits
this ticket froze, measured rather than estimated. A Contract commit carries tests, fixtures and
test adapters by construction, so its added lines are the test lines this threshold counts.

A correction returns to the same reviewer on the same axis, which reads only the bounded delta
and retains its prior verdicts — a correction is not self-validating, and one has already
introduced the defect that superseded it. A Contract that fails this axis a second time is an S1
signal, not a third correction: report it, naming whether the observable sentence survives, and
keep that report with the Slice. Nothing here opens a new counter or stops the lane; the same
first-parent range already carries the pre-production amendments this produces.
## S3 — Derived collect-round admission

- Root reads `status --task-id <task>.collect_rounds[<ticket>]` before a Standards or Spec
  production correction. The projection is Git-derived, counts collected rounds whose newly
  collected lane range contains a non-Contract commit, and is the only measured collect-round
  fact; there is no hand-maintained counter store.
- The projection excludes only Git-provable Contract-only and no-content carriage. Backlog,
  decision blocking, and rollout correction are human classifications; status does not infer or
  exclude them.
- Two is the advisory point, not a limit. Before making another production correction when the
  current derived value is already at least three, Root writes one line naming what the preceding
  corrections' diagnosis missed. The count alone cannot separate four independent defects found by
  successively deeper gates from one misdiagnosis corrected four times, and those two read
  identically afterwards while calling for opposite handling. The line is written where it is
  cheapest to write, which is not at review.
- The diagnosis line remains in the active Slice ticket's `Current`, which `locate` names to the
  next reader; the measured value remains in `status.collect_rounds`.

Nothing here bounds the loop mechanically. A Slice corrected eight times remains visible in its own
ticket beside the diagnosis that explains the corrections.

Blocking is a closed enum: `spec_violation | data_loss | security |
reproducible_behavior_failure` within the frozen envelope. Every blocker has `contract_basis`;
without one it is backlog. A missing product or policy decision is `blocked_on_decision`. A bounded
delta is reviewed by one reviewer on its originating axis.

## S4 — Review and validation

- The shared gate order is **canonical tests → ReviewGate** on one managed acceptance snapshot.
- Root binds the exact clean detached acceptance path, HEAD, tree, exercised selection and
  base…subject diff. Integration may advance without changing or invalidating that snapshot.
- A result that changes under a different selection of the same tree is not evidence about that
  tree; that instability is a current-task finding resolved before any verdict, never by preferring
  the passing selection. The mechanism that makes selection irrelevant belongs to the repo.
- Standards and Spec reviewers are read-only, report their axis and exact SHA, and never mutate the
  acceptance checkout. Each writes that same report to one `Report path` Root binds to its axis and
  exact SHA outside that checkout; the file is its only write and becomes evidence when Root accepts
  it. The reports carry their own counts and findings, while the Slice ticket's `Current` records the
  verdict and both bound paths. Root does not restate the reviews — an axis is heard in its own words
  or not at all.
- A bounded delta uses only its originating axis.

Each accepted increment closes by bringing the task record with it. The record is the only
authority a compacted session inherits, and a `Current` naming a frontier three increments behind
reads as correct while being wrong — the failure mode that made this step explicit. Four mechanical
actions, in order:

1. Update `INDEX.md`'s `Current` and `Next` to the accepted state, then run dev-flow's `refresh`.
2. Move every frozen token `refresh` names out of `Current` and `Next`, into the artifact of the
   gate that produced it.
3. Verify automatic clean closure for every named lane attempted by agent acceptance. Any retained
   lane and its warning remain an active current-task finding and require explicit correction or
   `lane drop` before closeout; do not unconditionally drop lanes.
4. Clear the temporary directories and test basetemps this increment created.

**What this stage owes is named by `refresh` and the locating output, not by a list written here.**
That is deliberate: a hand-kept checklist in this file would grow with every remembered incident
and still miss the one that mattered, while the instruments report the actual record in front of
you. If they name nothing, there is nothing to move.

Steps 1 and 2 are dev-flow's contract and step 4 is the repo's; run them there and do not restate
their policy in the task record.

## S5 — Landing and close-out

S1–S4 are Root's own authority, so a run with no user present carries a Slice all the way to an
accepted snapshot without asking. S5 is where that run stops.

- Landing requires current user authority and targets the exact reviewed candidate Git ref. The
  topology, squash and tree predicates are `integration land`'s own and are not restated here.
- A partial landing never cleans task state. Final landing additionally requires every generic
  ticket closed with recorded final state, a successful current-version task-record `refresh`, and
  any task-specific rollout checklist closed.
- Each landing, archive and cleanup mutation requires current user authority at its own gate.
  Protect and recheck pre-existing dirt and non-task evidence.
