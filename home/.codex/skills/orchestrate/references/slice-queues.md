---
orchestrate_compat: 55
---

# Role pipelines and slice queues

Read this reference before dispatching more than one role item, allowing pipeline
continuation, maintaining a finding ledger, or recording wave metrics. Read
`delegation-and-review.md` and the current runtime binding as well when agents are involved.

## Shared Role Pipeline Contract

Planner, writer, and reviewer are bounded queue consumers. Root is the only producer and
control plane. Each dispatch or follow-up carries the useful subset of:

```text
profile: <requested role; runtime-effective role when relevant>
lease: <role/domain; write scope for writers, immutable scope for reviewers>
wave + basis: <wave id; exact SHA/ADR/contract assumptions>
ordered items: <bounded items with dependencies and readiness>
milestone delivery: <runtime event and kind-specific evidence>
continue_without_ack: <qualifying outcome and dependency rule>
stop conditions: <task-specific additions plus profile defaults>
```

Item completion is not turn completion. A role first sends its milestone, then consumes the
next already-ready item when policy permits. It never invents or polls for work. Queue
exhaustion ends the turn but retains the lease; root resumes the same identity with a delta.

The live queue exists only in agent context (spawn plus follow-up messages). Across sessions,
the domain packet records the current item, bounded pending items, exact checkpoint, and next
gate so root can reconcile against Git and resend a delta. Never create a queue file, queue
manager, receipt, or coordination CLI. A future helper may only lint a supplied packet; it
must not write state, advance an item, dispatch, or infer phase from Git/liveness.

## Planner rolling horizon

The planner profile supports `planning_mode=contract-resolution|wave-ahead`:

- `contract-resolution` settles an uncertain contract/dependency split before writers start.
- `wave-ahead` proposes exactly Wave N+1 while frozen Wave N executes. It includes basis and
  assumptions, 3–5 proposed slices, behavior/structure dependencies, test seams/oracles,
  write scopes, hard axes, named risks, review policy, and invalidation triggers.

A wave-ahead proposal is evidence, not authority. Root reconciles it with integrated Git,
review verdicts, and open findings at the Wave N boundary, then freezes it or sends the same
planner a delta refresh. The planner never dispatches, never edits the plan as a trigger, and
never plans N+2 before root freezes N+1. Structure-dependent or hard-critical successors may
be proposed only conditionally on their preceding review gate.

## Checkpoint taxonomy

A **TDD cycle** is implementer-local: one confirmed seam, one test that fails for the intended
missing behavior, minimal implementation to green, then optional local cleanup while behavior
stays green. A slice may contain several cycles and ends at one coherent vertical behavior
plus a clean commit. Report compact red/green evidence at the slice boundary, not each cycle.

Every milestone declares one `checkpoint_kind`:

- **progress** — dirty/incomplete; report completion, stop reason, `finding_class`, and next
  step, plus optional provisional `diagnostics` (commands/results). Diagnostics are
  non-gating, non-review evidence; progress has no review target and does not authorize
  run-ahead.
- **validated** — clean exact SHA with targeted acceptance, validation subtype, and remaining
  uncertainty. It may authorize behavior-dependent normal run-ahead.
- **review** — validated plus explicitly frozen as an immutable exact-SHA review target. It
  creates review debt until the assigned reviewer closes it.

Validation subtypes are:

- **tdd-green** — the writer observed the intended red, then the same test and affected
  regression went green through an independent oracle at the frozen module interface;
- **targeted-acceptance** — non-TDD evidence for migration, deletion, adapter cutover,
  mechanical work, or other behavior where forcing a red test would add no signal.

A validated checkpoint qualifies for run-ahead only when all are true:

- its validation subtype's evidence is complete;
- the seam was already frozen and the slice crosses no hard-critical axis;
- there is no anomaly or retract-class finding; and
- the next slice is **behavior-dependent** on verified behavior, not
  **structure-dependent** on an unreviewed seam, ownership, or lifecycle choice.

It is run-ahead evidence, never review sign-off. A `review` checkpoint is the only kind that
creates per-slice review debt. Structure-dependent foundations and all hard-critical slices
keep `review-before-next-slice`; a named review risk follows its declared treatment. Final
normal review is cumulative/asynchronous or root
self-review according to the entrypoint route.

## Reviewer target queue

Root appends a reviewer item only when its full review-readiness packet and immutable exact
SHA exist. The reviewer sends a verdict milestone after every target. `PASS` permits immediate
consumption of the next already-ready target without root acknowledgment. `needs_fix`,
`blocked`, `needs_decision`, readiness failure, target drift, or queue exhaustion stops by
default. Root may pre-authorize continuation after a non-retract finding only when the next
target is explicitly independent and surface-disjoint; the reviewer still reports the
finding immediately and never decides its deferral.

If the next packet arrives while the reviewer is running, the runtime delivers it as a queue
delta. If the reviewer is already idle, root uses same-identity follow-up. No ready packet
means idle, not Git polling. Finding closure and refreshed-SHA review return to the same
reviewer lease.

## Review policy

Pipeline mechanics do not imply per-slice review. Freeze three independent fields per wave:

```text
review_cadence: none | cumulative | selected | per-slice
review_waiting: async | before-dependent | before-next
review_continuation: pass-only | independent-nonblocking
```

| mode | cadence | waiting | continuation |
|---|---|---|---|
| mechanical | none | async | pass-only |
| normal wave | cumulative | async | pass-only |
| named-risk wave | selected | declared treatment | pass-only by default |
| structure-dependent foundation | selected | before-dependent | pass-only |
| hard-critical | per-slice | before-next | pass-only |

Exploratory mode has planner/investigator work only. Direct mode uses root planning and no
role pipeline. Normal mode runs planner one wave ahead, writer slices, and cumulative/selected
review targets concurrently. Foundation-gated mode pauses the writer until the foundation
review releases dependent items. Hard-critical mode remains serial across dependent
writer/reviewer items. Parallel-domain mode may have separate writer leases and one ordered
reviewer queue, but root still collects serially and plans only one wave beyond the critical
path.

## Findings, preemption, and retraction

Preemption order is: stop conditions > retract-class finding > next queued item > deferred
ledger finding.

Findings default to the ledger. Root asks whether deferral requires downstream *logic*
redesign or only later propagation. Signature, parameter, return, naming, and localized bug
fixes are **mechanically-propagatable**, even when they touch an interface; batching them
until all callers exist usually reduces interruptions and cuts propagation once.

Only three retract classes stop or pull the queue forward:

- **design-invalidating** — changes downstream logic, seam, approach, or ownership; further
  slices would build on a refuted premise;
- **dangerous-intermediate** — persistence/migration, public wire, or security cannot remain
  broken between slices;
- **scope-collision** — the fix must touch a file the writer is about to modify.

Everything else waits for the wave fix; outside-task findings go to candidate backlog. A
deferred item remains deferrable only while surface-disjoint from upcoming work; collision
reclassifies it as `scope-collision`.

When a problem in announced slice N appears during N+1, the implementer first commits the
nearest coherent checkpoint, then reports its classification. Mechanically propagatable work
joins the ledger. `design-invalidating` returns `needs_decision`; dangerous intermediate and
scope collision pull forward. Never discard useful uncommitted work merely to rewind.

## Pipelining and review targets

Normal validated checkpoints need not create per-slice review debt. Root follows the frozen
cadence: promote selected SHAs to `checkpoint_kind=review`, or create one cumulative
wave-boundary review/self-review. A warm reviewer consumes only complete review targets and
may pipeline PASS results. Announced commits stay append-only while the writer runs ahead;
the 3–5-slice wave bounds both implementation and review accumulation.

Hard-critical slices do not pipeline. Building on an unreviewed
persistence/wire/security/hardware change is the compounding risk the model rejects. Named
review risks pipeline or wait according to their frozen treatment. Planner one-wave-ahead is
allowed here only as a conditional proposal, never as dependent writer authorization.

## Wave-boundary fix wave

Drain the ledger once at the wave boundary. Apply contract/interface propagation first
(widest surface, cut once against every known caller), then local fixes. Re-verify each fix on
current HEAD with its own thin evidence; never rerun a whole-wave review by habit. Retract
classes never reach this wave because they already stopped or pulled forward.

## Shaping the wave

- Before dispatch, check the area's candidate backlog for same-scope riders; never use it to
  expand scope. Close items the task actually resolves or obsoletes.
- Label every slice's `hard_critical_axes` and `named_review_risks`. Two or more hard axes
  require either a shared foundation checkpoint or `review-before-next-slice` when splitting
  creates an untestable half-change. Three or more authority boundaries (hard axes plus
  lifecycle/projection surfaces) default to foundation-first splitting; keeping one slice
  needs a stated reason.
- Prefer a medium vertical slice: one authoritative contract, one real consumer, end-to-end
  acceptance, and deletion of the old path. A foundation deserves its own checkpoint only
  when multiple later slices consume it.
- A slice without a clean checkpoint after roughly 60–90 minutes reports the bottleneck. An
  over-budget reviewer reports confirmed deterministic findings and continues by follow-up.
- Freeze review cadence/waiting/continuation with the wave. Reviewer queueing is an execution
  optimization, not a reason to upgrade normal validated slices into review debt.
- Standing milestone/stop/report contracts live in the role profile and runtime binding;
  prompts send only deltas. Inventory must confirm the loaded profile or root supplies the
  standing contract before further dispatch.

## Per-wave metrics

At wave close, append one compact line to task_plan current state, or state it in conversation
when there is no plan:

```text
wave N — mode=<route> work=<slices> handoff=<count> wall=<observed, e.g. ~18m|unknown>
wait=<observed review/gate/resource/decision time, e.g. unknown>
ledger=<findings>(<retract-class>) rework=<fixes/time>
review=<initial reviews/time> re-review=<closure or refreshed-SHA reviews/time>
re-verify=<writer/root fix checks/time> rounds=<n>
```

Use only runtime timestamps or durations explicitly reported by an agent/tool. `wall=~18m`
and `wait=unknown` are valid. Never reconstruct or guess timing after the fact. Parallel
durations may overlap. `review` counts initial reviews, `re-review` counts closure or
refreshed-SHA reviews, and `re-verify` counts writer/root fix checks. Never infer re-review
from rounds. This is disposable tuning telemetry for communication cost, review
amplification, parallelism, wave size, and retract boundaries — not coordination state or a
machine-read schema.

## Wave-boundary narrative maintenance

At every wave close when a plan exists:

1. reconcile Current State against Git branches, worktrees, status, and exact SHAs;
2. keep only open/deferred review findings in the active Finding ledger;
3. append the per-wave metrics above;
4. collapse closed review findings into counts plus evidence pointers;
5. after those semantic updates, run `planning-with-files compact <task-id>`; and
6. remove disposable artifacts only when their evidence is summarized and no unresolved
   finding points to them.

This maintenance records and compacts narrative only. It never dispatches work or changes
decision, validation, review, or merge state.
