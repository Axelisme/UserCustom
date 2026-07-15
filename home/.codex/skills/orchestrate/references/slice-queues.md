---
orchestrate_compat: 60
---

# Role pipelines and slice queues

Read this reference before dispatching more than one role item, allowing pipeline
continuation, maintaining a finding ledger, or recording wave metrics. Read
`delegation-and-review.md` and the current runtime binding as well when agents are involved.

## Shared Role Pipeline Contract

Planner, writer, and reviewer consume bounded ordered items under root control. Planner items
and hard-critical items remain direct in-band dispatches. A v60 normal writer/reviewer wave
may instead use the [durable delivery spool](durable-delivery-spool.md), whose files carry only
already-ready items inside the same frozen bounded wave. Root is its only producer and the
bound lease holder its only consumer. Each initial dispatch carries the useful subset of:

```text
profile: <requested role; runtime-effective role when relevant>
lease: <role/domain; write scope for writers, immutable scope for reviewers>
wave + basis: <wave id; exact SHA/ADR/contract assumptions>
ordered items or spool binding: <bounded items, or absolute path + generation>
milestone delivery: <runtime event and kind-specific evidence>
continue_without_ack: <qualifying outcome and dependency rule>
stop conditions: <task-specific additions plus profile defaults>
```

Item completion is not turn completion. A role sends its milestone before the final response,
then consumes the next already-ready item when policy permits. It never invents or polls for
work. Queue exhaustion ends the turn but retains the lease; root resumes it with a delta.

Dispatch is idle-first. Direct mode follows up an idle agent and accumulates ordinary busy
work until its next turn. Spool mode publishes ready files, checks status once, wakes only an
idle consumer, and checks once more at its completion event. A running consumer discovers
routine additions at item boundaries. Confirmed major finding, retract, and invalidation stay
direct and may interrupt. No work means idle, never filler. Count direct mid-turn exceptions
as `mid-turn-inbound=<n>`; zero is preferred.

The spool is the sole workflow-file exception: it transports frozen work but does not create
review debt, prove completion, or advance a phase. Across sessions, task_plan/domain packets
still carry conclusions and current narrative; root reconciles both narrative and spool
against Git before republishing or waking. No queue manager, receipt, polling daemon, or
autonomous controller is allowed.

## Planner rolling horizon

The planner profile supports `planning_mode=contract-resolution|wave-ahead`:

- `contract-resolution` settles an uncertain contract/dependency split before writers start.
- `wave-ahead` proposes exactly Wave N+1 while frozen Wave N executes. It includes basis and
  assumptions, target 3–5 proposed slices, behavior/structure dependencies, test
  seams/oracles, write scopes, hard axes, named risks, review policy, and invalidation
  triggers. A tail/final wave may contain 1–2 natural slices; never pad, split, or add scope
  merely to reach three.

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

Prefer a bounded batch of already-ready packets. In normal v60 mode root may publish a newly
ready exact-SHA packet into the reviewer's current spool generation without interrupting a
running review. The reviewer discovers it at the next item boundary. No ready packet means
idle, not Git polling. A runtime-declared slot-free park may retain identity; otherwise the
turn ends and root wakes the same lease if its completion-side inspection finds work. Finding
closure and refreshed-SHA review return to that lease. A confirmed major finding still gets
immediate direct notification before the routine verdict.

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
review targets concurrently. The normal writer turn targets one frozen wave; reviewer turns
consume ready target batches. Foundation-gated mode pauses the writer until the foundation
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

Normal validated checkpoints need not create per-slice review debt. A queue file does not create review debt. Root follows the frozen
cadence: promote selected SHAs to `checkpoint_kind=review`, or create one cumulative
wave-boundary review/self-review. A warm reviewer consumes only complete review targets and
may pipeline PASS results. Announced commits stay append-only while the writer runs ahead;
the target 3–5-slice wave (tail/final 1–2) bounds implementation and review accumulation.

Hard-critical slices do not use the durable spool, do not pipeline, and normally use one
direct writer slice plus one reviewer target per turn. Building on an unreviewed
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
- A source map crossing at least two hard axes or three authority boundaries is oversized.
  Root either splits out shared foundation gates, or freezes one atomic critical vertical
  with exactly one acceptance domain; target 2–4 summarized progress checkpoints and an exit
  condition for every dangerous intermediate. Root may aggregate low-level events; an
  immediate major finding notification does not count against this budget. The latter has
  one final review checkpoint/formal review; progress milestones never become review targets
  and no dependent slice starts before that final review clears.
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
wave N — mode=<route> work=<slices> turns=<count> handoff=<count> mid-turn-inbound=<count>
[wall=<observed, e.g. ~18m|unknown>]
[wait=<observed review/gate/resource/decision time, e.g. unknown>]
ledger=<findings>(<retract-class>) rework=<fixes/time>
review=<initial reviews/time> re-review=<closure or refreshed-SHA reviews/time>
re-verify=<writer/root fix checks/time> rounds=<n>
```

Use only runtime timestamps or durations explicitly reported by an agent/tool. Omit timing
fields with no observation; `wall=~18m` and an explicitly reported `wait=unknown` are valid.
Never reconstruct or guess timing after the fact. Tool-emitted operation duration is only
that command's runtime, not wave wall/wait time. Parallel
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
5. after those semantic updates, run `planning-with-files checkpoint <task-id>`; and
6. remove disposable artifacts only when their evidence is summarized and no unresolved
   finding points to them.

This maintenance records and compacts narrative only. It never dispatches work or changes
decision, validation, review, or merge state.
