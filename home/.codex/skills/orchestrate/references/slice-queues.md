# Slice queues

Read this reference before dispatching more than one slice, allowing green-checkpoint
run-ahead, maintaining a finding ledger, or recording wave metrics. Read
`delegation-and-review.md` and the current runtime binding as well when agents are involved.

## Queue shape

Use a pre-authorized queue only when the contract is frozen and each slice has independent
acceptance. Prefer 3–5 slices per wave; longer plans lose steering points. The writer commits,
runs targeted checks, sends a milestone at each boundary, and continues without an ack unless
a stop condition fires. Exploratory work stays single-slice.

```text
profile: <requested role; runtime-effective role when relevant>
lease + write scope: <domain owner; only files this writer may change>
slices: <ordered 3–5 slices, each with acceptance and targeted checks>
critical shaping: <axes; foundation or review-before-next-slice; rationale>
stop conditions: <task-specific additions; standing ones remain in profile>
milestone delivery: <runtime mechanism and deviations from standing contract>
```

The queue lives in agent context (spawn plus follow-up deltas) or, across sessions, the domain
packet. Never create a queue file or CLI. Items are pre-authorized and same-scope; a writer
does not invent the next item. An exhausted queue ends the turn but retains the domain lease.

## Execution units and green checkpoint

A **TDD cycle** is implementer-local: one confirmed seam, one test that fails for the intended
missing behavior, minimal implementation to green, then optional local cleanup while behavior
stays green. A slice may contain several cycles and ends at one coherent vertical behavior
plus a clean commit. Report compact red/green evidence at the slice boundary, not each cycle.

A checkpoint qualifies for run-ahead only when all are true:

- the writer observed the intended red;
- the same test and affected regression are green;
- the test crosses the module interface with an independent oracle;
- the seam was already frozen and the slice is non-critical;
- there is no anomaly or retract-class finding; and
- the next slice is **behavior-dependent** on verified behavior, not
  **structure-dependent** on an unreviewed seam, ownership, or lifecycle choice.

It is run-ahead evidence, never review sign-off. Normal qualified checkpoints continue
through the wave without per-slice review debt. Structure-dependent foundations and all
critical slices keep `review-before-next-slice`. Mechanical work may use targeted acceptance
instead of artificial TDD. Final normal review is cumulative/asynchronous or root
self-review according to the entrypoint route.

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

Normal green checkpoints need not create per-slice review debt. Root may explicitly designate
a named-risk SHA for asynchronous exact-SHA review or choose one cumulative wave-boundary
review/self-review. A warm reviewer consumes only assigned targets. Announced commits stay
append-only while the writer runs ahead; the 3–5-slice wave is the accumulation bound.

Critical slices do not pipeline. Building on an unreviewed persistence/wire/security change
is the compounding risk the model rejects.

## Wave-boundary fix wave

Drain the ledger once at the wave boundary. Apply contract/interface propagation first
(widest surface, cut once against every known caller), then local fixes. Re-verify each fix on
current HEAD with its own thin evidence; never rerun a whole-wave review by habit. Retract
classes never reach this wave because they already stopped or pulled forward.

## Shaping the wave

- Before dispatch, check the area's candidate backlog for same-scope riders; never use it to
  expand scope. Close items the task actually resolves or obsoletes.
- Label every slice's closed-list critical axes. Two or more axes require either a shared
  foundation checkpoint or `review-before-next-slice` when splitting creates an untestable
  half-change. Three or more authority boundaries (critical axes plus lifecycle/projection
  surfaces) default to foundation-first splitting; keeping one slice needs a stated reason.
- Prefer a medium vertical slice: one authoritative contract, one real consumer, end-to-end
  acceptance, and deletion of the old path. A foundation deserves its own checkpoint only
  when multiple later slices consume it.
- A slice without a clean checkpoint after roughly 60–90 minutes reports the bottleneck. An
  over-budget reviewer reports confirmed deterministic findings and continues by follow-up.
- Standing milestone/stop/report contracts live in the role profile and runtime binding;
  prompts send only deltas. Inventory must confirm the loaded profile or root supplies the
  standing contract before further dispatch.

## Per-wave metrics

At wave close, append one compact line to task_plan current state, or state it in conversation
when there is no plan:

```text
wave N — mode=<route> work=<slices> handoff=<count> wall=<time>
wait=<review/gate/resource/decision time>
ledger=<findings>(<retract-class>) rework=<fixes/time>
review=<count/time> re-verify=<count/time> rounds=<n>
```

Parallel durations may overlap. This is disposable tuning telemetry for communication cost,
rework/re-review, parallelism, wave size, and retract boundaries — not coordination state or
a machine-read schema.
