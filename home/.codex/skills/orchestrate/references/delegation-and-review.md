# Delegation and review

Read this before the first agent action or review decision, then read the matching runtime
binding. Runtime tools—not config files or this reference—define available identity,
continuation, parking, retirement, model, and sandbox capabilities.

## Roles and continuity

Root alone freezes work, grants authority, classifies deferral, and integrates. A role gets a
bounded objective, workdir/scope, basis, acceptance, stop conditions, checkpoint budget, and
either inline content, a dispatch-packet path/hash, or a spool binding. The budget's
worker-facing cadence is declared in discrete observable units (commits, items, sub-steps),
never wall-clock. Keep the dispatch lean: stable boilerplate — profile standing orders, the
milestone schema, tool recipes — is referenced by pointer, and root writes only the contract,
risk axes, acceptance, and non-goals.

Root does the work itself when the next result directly gates the next decision, the scope
is smaller than its own readiness packet, or delegating would leave root idle. Delegate what
is genuinely parallel with disjoint write sets.

Keep the same identity for the same domain when the runtime supports it. Finding fixes return
to the original implementer; finding closure and refreshed-SHA review return to the original
reviewer. Spawn a new identity for independent review, a changed domain, or genuine parallel
scope—not merely because a turn ended. Role switching requires a new profile bootstrap and
cannot make an identity independent from work it implemented.

Planner output is advice: contract resolution or a stocked chain of conditional wave
proposals. Root freezes it. Writers own scoped implementation and every internal design
decision inside the frozen seam, reporting notable ones in the milestone for post-hoc
recording. Reviewers are read-only with respect to the reviewed tree;
workspace write exists only for detached worktrees and test caches. Agents never spawn
coordination sub-agents or decide landing/finding deferral.

## Root contact discipline

The four contact reasons in the SKILL dispatch row are a closed list. Report to the user
from the last milestone, read-only Git state, and the frozen dispatch description —
commentary never touches the assignee. Dispatch a frozen bounded turn rather than
drip-feeding a running identity; routine additions merge into one spool batch, and only
major finding, correction, retract, or stop may interrupt directly.

## Milestones and liveness

A milestone is one semantic envelope per observable boundary — for a writer, after every
commit (`outcome=working`) — plus one terminal envelope per item. The core is three fields;
the rest is optional and validated only when present (`orchestrate milestone lint`):

```text
item_id=<stable id>
outcome=working | <role terminal outcome>
evidence=<compact result or artifact pointer>
subject_sha=<exact SHA; required for validated|review|pass|needs_fix>
findings=<ids; required for needs_fix>
```

Delivery is **at-least-once, deduplicated by `item_id`**: a milestone counts as delivered
only when root observably received it; until then the sender repeats the envelope verbatim
in its final response — a duplicate is cheap, a lost terminal envelope (findings, verdicts)
is the one thing this protocol must never drop. A runtime completion event means only that
the turn ended. A reviewer `pass` may continue to a complete pre-authorized target; other
outcomes stop unless independent continuation was frozen, and hard-critical dependent work
always waits.

Liveness recovery has exactly three triggers: the runtime reports the identity errored or a
model/capacity failure; the runtime declares its lease/continuation lost; or the
dispatch-declared checkpoint budget passes with no milestone. Everything else is healthy —
absent tool/filesystem activity is model reasoning, a wait timeout is normal silence to wait
on again, fixed-interval status polling of a sub-agent is forbidden, and there is no
universal timer. When a trigger fires: read runtime activity metadata first (never guess
from `ps`/Git); send one liveness ping asking for progress, blocker, or the nearest coherent
checkpoint; without a response, interrupt and resume the same identity with a recovery
delta, spawning a replacement only when continuity is unavailable or the
domain/independence requirement changed.

## Evidence ownership

Evidence is intentionally non-duplicative:

- Root/planner freezes seams, acceptance examples, independent oracles, and dangerous failure
  modes.
- **Writer owns permanent executable tests**, functional acceptance, and affected regression.
- **Reviewer owns** source audit, adversarial matrix, temporary reproducers, and
  finding-specific probes—not a second permanent-test lane or habitual suite rerun.
- **Integration owns** SHA/parent/tree checks and the final repo/risk-required broader gate.

A missing behavior returns to the writer for a failing permanent regression before the fix.
Duplicate evidence needs a reason, such as suspected environment skew.

## Review depth and readiness

Review the checkpoint's changed surface:

| surface | default depth |
|---|---|
| mechanical | none, or root scope/tree spot-check |
| normal internal behavior | writer self-review + root spot-check — no independent identity |
| named review risk | cumulative independent review at explicitly chosen depth/waiting |
| critical boundary | enter [Critical review](critical-review.md) |

Cadence defaults to **cumulative**: one review closes a coherent surface or selected batch.
Per-slice review is the exception root must justify. Wait only where a declared dependency or
named critical barrier requires it; normal work runs ahead unreviewed. A queue entry never
creates review debt; root creates a review target by authorizing an exact immutable SHA.

A readiness packet—inline or via [dispatch packet](transports.md)—names at least:

- base and exact target SHA;
- frozen contract/invariants and changed surface;
- hard axes/named risks and dangerous failures;
- acceptance evidence and known anomalies;
- reviewer focus/non-goals;
- findings/round context when closing prior review.

Missing target, contract, scope, or dangerous oracle is a readiness failure. Old-SHA review,
aborted suites, and unproved tree equivalence are invalid substitutes.

Word review dispatches in neutral engineering vocabulary — correctness, negative path,
boundary probe, lifecycle probe, transaction safety — and reserve hostile/adversarial/security
framing for surfaces that genuinely cross a security boundary. Only `pass` and `needs_fix`
are review verdicts; `blocked` and `needs_decision` are valid non-verdict terminal outcomes
of the same receipt field — findings carriers that route to root and never authorize
collect. An incomplete turn, execution failure, platform-classifier abort, or invalid
checkout evidence is **unusable evidence** with its own small root-set retry budget (reword
the dispatch, rerun with a fresh identity). Finding rounds are unlimited and never count
against that budget.

## Wave pipeline

Idle capacity is cheaper than blocking the main writer with handoffs, repeated context
loading, and duplicate gates.

### Freeze the wave

Root freezes one natural wave, commonly a few coherent items and sometimes a one-item tail.
Each item is self-contained: objective, exact base, write authority, acceptance/oracle,
dependencies, discretion, and any root-named review barrier. Contract or same-file authority
is serialized. Planner keeps the whole known dependency chain stocked with ready proposals
while N runs; root alone freezes and releases them, wave by wave.

Prefer one writer for a coherent vertical slice. Split at independently verifiable ownership
or dependency seams, not at each parser, field, callback, or mechanical edit. A slice may
contain several progress observations without creating several review checkpoints.

### Keep work flowing

- A **non-blocking milestone** reports observed progress/evidence; an authorized writer
  continues immediately. The runtime/profile owns its transport and schema.
- A completed micro-step is not itself a reason to stop, commit, switch identity, or ask root.
- Root observes delivered events; the root contact discipline above governs contact.

### Writer, reviewer, and root

A writer retains context across the whole slice and stops only at its declared barrier or a
genuine decision boundary; for normal work the writer is the default reviewer.

An independent reviewer exists only where root named a risk at freeze and consumes complete
exact-state targets at the cumulative cadence above. It may continue to an already-ready
independent target after pass; idle review time never justifies blocking the writer or
implementing against an unstable interface.

Root harvests milestones, assigns findings, and batch-collects with one narrative update per
batch. Localized finding fixes get a **focused re-review**; one full review closes a
named-risk surface. Only integration runs the repo/risk-required **broader gate**, whose
evidence binds to the final tree.

### Wave close

Reconcile Git and the durable narrative, retain open/deferred findings, and collapse every
closed decision into a one-line ADR/evidence pointer — task_plan carries active items and
pointers only. Record lightweight counts (findings per review, review rounds, wait) and tune
**review amplification** with them: two consecutive reviews yielding only minor findings drop
the next wave's default depth one level (focused → root spot-check → none); any major finding
restores named-risk review immediately.

Add three discipline counters, each expected zero — unprompted contacts to a running
assignee, per-slice reviews without a named risk, repeat dispatches for one slice. A nonzero
count is drift to name in the wave record, not defend. Then answer four steering questions
against the wave's evidence before the next freeze:

- **Shape fit** — did any slice's freeze+dispatch+harvest overhead exceed the work itself
  (demote to root-only), or did serialization hide genuine independence?
- **Cut quality** — did any slice exceed a single context, stall, or need repeat dispatch?
  Recut the next wave.
- **Parallelism** — bounded by shared-state ownership, or by habit? Any needless wait on the
  critical path?
- **Adoption** — were fired triggers' artifacts actually used, and unfired ones left unbuilt?
  (consumes the artifacts-vs-triggers count)

Each answer is "keep" or a one-line next-freeze adjustment recorded in task_plan.
Adjustments act forward only — frozen contracts, acceptance, and dispatched work stand.
Rule-level observations get one backlog line and wait for effort close-out.

Normal queue mechanics live in [File transports](transports.md). A boundary that needs
independent adversarial proof leaves this branch for [Critical review](critical-review.md).

## Receipts

A receipt is a plain JSON file its author writes with native file tools at the
dispatch-named path; `orchestrate receipt lint` validates one and `collect --receipt`
consumes one — aliases over the file, never a required control plane. A reviewer closes
review by writing a **review receipt** whose core is small: the receipt envelope
(`receipt_version`, `kind: "review"`, `item_id`), exact `subject_sha`, `verdict`,
`findings` ids, `evidence`. The schema is closed — an unexpected field is a lint error, and
`receipt lint` reports the exact field names. Only a `pass` receipt — the one that
authorizes collect — also carries the authorization block: reviewer runtime identity
(`reviewer_agent_id`), requested/effective profile, `review_kind`, and detached/clean
checkout evidence (`checkout_detached`, `checkout_clean`, `checkout_head`) whose HEAD equals the subject SHA (a
drifted receipt cannot authorize; `profile_effective` discloses a generic adapter when the
runtime loaded no profile). `needs_fix`/`blocked` receipts are findings carriers and need
none of that block. The terminal envelope points at the receipt, and collect consumes it
directly, so root never retranscribes authority. A frozen contract overturned by evidence
returns to root as `needs_decision`; root records the adjustment as a **task_plan ADR
entry** — original contract, contradicting evidence, adjusted contract, authority, and the
affected reviewed SHAs whose evidence is void — and refreshes review for those SHAs. A
divergence beyond local reversible adjustment returns to the user. A **gate receipt**
([Evidence and handoff](evidence-and-handoff.md)) classifies a test run's status and every
exclusion, so a deselected test can never pass silently.

## Reviewer mental model

Inspect source/diff first. Run only thin adversarial commands from a detached checkout at the
target SHA; a live-writer checkout voids evidence. Challenge the oracle, ownership, lifecycle,
scope, and dangerous failures—green tests prove behavior, not that the seam is correct.

Report findings with severity, path, observable behavior, evidence, and propagation shape,
plus a proposed disposition: **contract violation** (the only one that proposes `needs_fix`
and gates the slice), **slice-local hardening** (rides the verdict; the fix returns to the
writer as a follow-up), **future-slice concern** (routes to the task plan), or **candidate
backlog** (out of task scope; record in the repo's backlog inbox). Dispositions are routing
proposals, not deferral decisions — they exist so foundation slices do not absorb downstream
scope, and severity stays orthogonal to them. Root decides deferral. A confirmed major finding (P0/P1, contract invalidation, retract class,
or dangerous intermediate) is reported immediately, whatever its disposition, so root can
hold dependent work; the
reviewer keeps scanning the surfaces independent of the broken invariant and ends the turn
early only when the contract is overturned or the remaining scope depends on it. Ordinary
findings stay in the target's one terminal milestone.

Normal re-review is finding-focused. Critical hostile proof, refreshed-review criteria, and
dependent-work release live together in [Critical review](critical-review.md). After collection,
prove reviewed/integration tree identity or review the integration SHA when reviewed content
may differ.

## Skill upgrades

Pin a role turn to the profile/dispatch it loaded. Pin the task itself at task start with
`orchestrate pin set`; the state-entering commands — packet/queue publish, `lane create`,
`review checkout`, `collect`, `land finish` — then fail fast if the installed skill moves
mid-task (maintenance commands like `cleanup` stay unguarded so a stale pin never blocks
closing down). Adopt a new orchestrate version at a safe
boundary—before dispatch, after a milestone, or after turn completion—by running
`orchestrate pin migrate`, which repins and reports the manifest delta so root re-reads
exactly the changed documents. An immutable review
restarts only when the release changes an applicable hard rule, readiness condition, or
review meaning. Sub-agents never load orchestrate; root sends only the effective delta.
