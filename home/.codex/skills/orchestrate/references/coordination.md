# Coordination

Delegation, review, Git topology, landing, and handoff in one place. Read it once per task
before the first dispatch; the iron rules in `../SKILL.md` stay authoritative.

## Roles and dispatch

Root alone freezes work, grants authority, decides deferral, and integrates. A dispatch
names the bounded objective, scope/workdir, exact base, acceptance, non-goals, stop
conditions, and a checkpoint budget in observable units (commits/items, never wall-clock);
acceptance gates are verbatim command + workdir + environment. Named risks are both writer
self-check and reviewer scope; authority-publication slices name
[publication-review](publication-review.md). Boilerplate stays in the profile; long
contracts travel by named file. For speculative work, stop conditions also name the
idempotent compensation to run in reverse if a later finding overturns its prerequisite.

Double-buffer each lane per the SKILL pipeline model; contract-planner can keep the
one-deep chain stocked as drafts, each re-confirmed against the predecessor's actual result
at harvest before it dispatches. Successive items on one authority surface stay in that
surface's single lane and writer; collect them once cumulatively after the surface's review
passes, never a fresh lane/worktree per item.

Keep the same identity for the same domain; finding fixes return to the original writer,
finding closure to the original reviewer. Spawn a new identity for independent review, a
changed domain, or genuine parallel scope. An identity can never independently review work
it implemented. Writers own every internal design decision inside the frozen seam and
report notable ones in their milestone. Reviewers are read-only toward the reviewed tree.
Agents never spawn coordination sub-agents or decide landing/deferral.

## Milestones and liveness

At each observable boundary, emit one semantic envelope; delivery is at-least-once,
deduplicated by `item_id`, and an unacknowledged terminal envelope repeats in the final
response. Read its Git facts from `slice milestone --item <id>`. A received schema-valid
terminal envelope remains evidence if transport later fails; without one, runtime
completion proves only that the turn ended.

The expected milestone is the **heartbeat**. Pair it with the runtime binding's wait bound
and classify absence before acting:

- **never-started** — no start or first boundary arrived; repair or reissue only after
  runtime or lease evidence says the dispatch was not claimed.
- **died-mid-work** — start was observed, then runtime error, lease loss, or the paired
  heartbeat bound fired; resume the same identity from its last SHA, replacing it only
  when continuity is unavailable.
- **in-budget** — the latest boundary remains within its declared checkpoint budget; wait.

Only the first two fire liveness. Inspect runtime metadata once; never poll, send progress
pings, or treat a wait timeout alone as failure.

## Review

Depth scales with risk: mechanical → none or a root spot-check; normal internal behavior →
writer self-review plus root spot-check; root-named risk → cumulative independent review;
critical boundary → the barrier below. Two consecutive reviews yielding only minor findings
**on the same risk surface** drop that surface's next default depth one level — a new
domain or risk axis starts at its own default; any major finding restores it.

A reviewer reads source, then probes the named oracle, ownership, lifecycle, and dangerous
failure axes from `review checkout` at the exact target SHA; `review advance` reuses that
checkout for closure commits, and `review audit` flags mechanical oracle weakening. The
terminal milestone carries `pass|needs_fix`, subject SHA, and evidence; record `needs_fix`
items through `findings record`. `findings status` derives closure from `Closes-Finding`,
and `collect` blocks open `gates-the-slice` debt. A finding whose cause is a named pattern,
not a lone instance, is recorded `sweep_required` — which forces `gates-the-slice`: fix
every occurrence in the frozen scope in one commit, and re-review verifies enumeration
completeness, not just the reported site. The ledger is each surface's accumulating hostile
checklist: before terminal on a surface with prior findings, writer self-review re-runs
their probes (via `findings status`) so review confirms rather than first-discovers. Root
decides routing.

Send a confirmed major immediately while review continues on independent surfaces; batch
ordinary findings in the terminal receipt and deliver them at the assignee's next
milestone. Routing a confirmed major never by itself preempts the successor: flush its
stacked work through the predeclared reverse-order compensations only when the finding
overturns an invariant the successor relied on, and record that call — a finding local to
the reviewed slice lands as a follow-up while the successor runs on. A
public-contract correction changes interface, acceptance, scope, or base; anything else
waits as finding or advice. Review needs a terminal exact SHA, but successors and
confirmed-major fixes do not wait for its verdict or end. Re-review is finding-focused;
refresh fully only when a fix invalidates prior authority, threat, persistence, or other
reviewed boundary evidence.

Presume **critical-depth independent review** when a slice changes at least two of: request
identity, authority ownership, receipt/reconciliation taxonomy, resource lifecycle,
durable recovery witness, process/credential boundary. A downgrade needs one freeze-time
reason. This sets review depth, not a barrier.

A **critical checkpoint** blocks dependent run-ahead only when a dangerous state cannot be
cheaply undone by a follow-up **and** named dependent work is about to stack. Freeze that
core as a small slice; a different identity tries to disprove it with hostile negative and
intermediate paths. Hold only its descendants; release after pass.

Evidence ownership is non-duplicative: writer owns permanent tests and functional
acceptance; reviewer owns audit, adversarial probes, and temporary reproducers;
integration owns ancestry/tree checks and the final repo/risk-required gate on the landing
candidate. A missing behavior returns to the writer for a failing regression before the
fix. An abort, crash, or timeout is not a pass and never becomes one by retrying until
green — record it, replace it with the smallest split evidence that still covers the
surface, and keep unexplained risk blocking.

## Git topology

- **Main checkout** = the repo-root working directory, the only place with the full
  environment; gates needing it run here. **Persistence branches** (`main`, user feature
  branches) have immutable history.
- Hierarchy: persistence ← `task/<task>` (one integration branch per task) ←
  `agent/<task>/<lane>` (one writer each). Rewrite integration history only between waves,
  never under a lane based on the rewritten range.
- **Single writer**: work directly on `task/<task>` in the main checkout; worktree only
  when the main checkout must stay free or user dirt conflicts.
- **Multi-writer**: one worktree per concurrent writer —
  `git worktree add .agent_state/worktrees/<task>-<lane> -b agent/<task>/<lane> task/<task>`;
  root merges serially in the integration checkout. The `orchestrate` aliases (`lane
  create`, `review checkout`, `collect`, `cleanup`, `slice status`) wrap the same
  operations with exact-input checks and idempotent rerun reports.
- Writers are **single-threaded per artifact**; declared scopes remain the semantic guard.
  A root-declared append-only shared file is the sole overlap exception.
- `slice status` derives path overlaps. If one is a shared prerequisite, recut it as a
  predecessor: record a `gates-the-slice` finding against the superseded subject (the
  ledger is the deny-list), freeze the prerequisite from the last valid base, and use
  `compose-base` when a successor also needs other still-valid seam-ready lanes. Otherwise
  serialize. `revalidate` reports whether final follow-ups require recomposition; `collect`
  rejects unlanded dependencies, open gating debt, or a conflicting final merge.
- Commits carry `Item: <id>`; fixes carry `Closes-Finding: <id>`. `findings status`,
  `collect`, `reconcile`, and `cleanup` derive closure and absorption; never copy them into
  task_plan.
- Never create or repair environments in worktrees; point the main checkout's toolchain at
  worktree sources. Resolve conflicts by recovering each side's intent; never invent
  behavior during resolution.

## Landing

Landing is one declaration-authorized squash commit. Keep expensive work off-lock: rebase
onto the persistence tip and run the final gate, then use `land status|finish` with the
exact task SHA (`--confirmed` when required). The tool re-reads under its lock and proves
tree identity; target drift means rebase and rerun, never adapt inside the lock.

## Wave close

Run `reconcile`; remove only `safe-to-remove` paths through exact-target `cleanup`.
Re-baseline task_plan to active intent, decisions, unresolved anomalies, and next gates;
closed items become pointers and Git-derived state disappears. Record the three
zero-expected counters — unprompted running-assignee contacts, riskless per-slice reviews,
repeat dispatches — and answer shape fit, cut quality, parallelism, and adoption. Each
nonzero or adjustment becomes one forward-only next-freeze note.

## Handoff

Stop dispatching and drain to a slice boundary; writers commit and milestone, reviewers
flush findings. Run `reconcile` and `slice status`; task_plan stores only unresolved
intent, decisions, anomalies, next gates, receipt pointers, and exact SHAs — not copied
topology. Remove only tool-declared safe worktrees. The next session repeats the same
derived reads before dispatch.

## Skill upgrades

Pin at task start with `pin set`; state-entering commands fail if the installed release
moves, while read-only maintenance stays available. At a safe boundary `pin migrate`
repins and reports exactly what root must re-read or acknowledge removed. Cut releases only
with the one-shot `release` transaction. Because the installed skill is a live overlay,
release in a task worktree, land by merge as the atomic switch, then `doctor` the installed
path.
