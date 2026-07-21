# Coordination

Delegation, review, Git topology, landing, and handoff in one place. Read it once per task
before the first dispatch; the iron rules in `../SKILL.md` stay authoritative.

## Roles and dispatch

Root alone freezes work, grants authority, decides deferral, and integrates. A dispatch
names the bounded objective, scope/workdir, exact base, the task-id (the ledger key an
assignee needs to self-query `findings status` for a surface's prior findings), acceptance,
non-goals, and stop
conditions; add a checkpoint budget in observable units (commits/items, never wall-clock)
only when the work spans several boundaries — on a single-boundary slice the terminal
milestone is the budget, and stating one is ceremony;
acceptance gates are verbatim command + workdir + environment. Named risks are both writer
self-check and reviewer scope; authority-publication slices name
[publication-review](publication-review.md). Boilerplate stays in the profile; long
contracts travel by named file. For speculative work, stop conditions also name the
idempotent compensation to run in reverse if a later finding overturns its prerequisite.

Before freezing, run the cross-cutting readiness checks a first implementation usually
misses — cheaper here than a re-freeze after the writer stacks work on a half-frozen seam:
do success and failure paths share one commit fence; is every public digest/fixture the
contract exposes updated in the same freeze; does the failure path terminate at the real
production owner, not a stub; is restart/recovery semantics backed by test evidence, not
assumed. These are prompts, not a gate — a contract that cannot answer them is not ready to
dispatch.

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
failure axes from its own `review checkout` at the exact SHA the dispatch froze — root
names the SHA, the reviewer opens the checkout, and the terminal `subject_sha` must equal
that checkout's HEAD, so a wrong target is caught on arrival rather than prevented by an
extra root round-trip. `review advance` reuses that checkout for closure commits, and `review audit` flags mechanical oracle weakening. The
terminal milestone carries `pass|needs_fix|blocked|needs_decision`, subject SHA, and the
receipt's path — the findings themselves are written once, in the receipt, not restated in
the envelope. Record it through `findings record`, which takes those same four outcomes and
keeps each finding's observable behavior and evidence: a gate the environment could not run
is recorded `blocked`, never silently dropped. `findings status` derives closure from `Closes-Finding`,
and `collect` blocks open `gates-the-slice` debt. A finding whose cause is a named pattern,
not a lone instance, is recorded `sweep_required` — which forces `gates-the-slice`: fix
every occurrence in the frozen scope in one commit, and re-review verifies enumeration
completeness, not just the reported site. The ledger is task-long, so a finding an earlier
wave logged on a file outlives that wave: on opening a surface, a reviewer or a writer's
self-review pulls the prior findings on it — keyed on its own diff's paths
(`findings status --path <file>`, plus `--sweep` for the cross-cutting root-cause patterns
a path query cannot reach) — so review confirms rather than first-discovers. That query is
what makes the ledger consultable across identities and waves rather than write-and-forget;
for it to reach, a file-local finding must carry its `path`. Root decides routing.

Deliver a finding mid-flight only when delay would grow the rework — the writer is still
propagating a root-cause (`sweep_required`) pattern, or a running successor is stacking on
the flawed invariant; a finding local and static to the reviewed diff batches into the
terminal receipt for the assignee's next milestone. Severity alone is not the trigger — the
question is whether not knowing now costs more later. And delivering mid-flight still never
by itself preempts the successor: flush its stacked work through the predeclared
reverse-order compensations only when the finding overturns an invariant the successor
relied on, and record that call — a finding local to the reviewed slice lands as a follow-up
while the successor runs on. A
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
surface, and keep unexplained risk blocking. Distinguish a product failure from a gate the
sandbox could not run — a required capability the environment withheld (loopback socket,
real adapter, network) makes the gate `blocked`/inconclusive, not `needs_fix`; name the
missing capability and rerun in an authorized environment rather than reading the
environment's refusal as a defect.

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
- All scratch stays **repo-local**: `review checkout`, `lane create`, and the managed
  aliases place worktrees under `.agent_state/worktrees/` and reject any path outside it, so
  no gate depends on the mount, permissions, or cleanup policy of the system `/tmp`. Reach
  for the alias rather than a raw `git worktree add /tmp/...`; a hand-placed out-of-repo
  checkout forfeits that guarantee and the tool's exact-input and cleanup checks.
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

The wave boundary is where inter-slice risk first becomes reviewable: dispatch the
integration review — contract parity, lifecycle ordering, cross-module regression on the
integrated tree — to an integration-reviewer here, not a re-run of slice diffs, and let it
run under root's serial freeze of the next wave and this retrospective (its cost hides under
root-serial time). `wave status` rolls the slice states, finding ledger, and worktree reconciliation into one
read-only report with a restart handoff summary — read it to steer, but it never dispatches,
lands, or writes the plan for you. Its `--summary` reports `wave_boundary_removable`: this
task's lane worktrees. When it is non-empty and you judge the boundary safe, `cleanup
--wave-boundary` clears them — abandoned, dirty, or absorbed alike, since a half-finished
lane is the target, not work to protect — scoped to `agent/<task>/*`, never the integration
checkout. It skips detached review worktrees, which carry no task identity; remove those by
exact-target `cleanup --worktree`. When the count is zero, skip the step. The summary also
carries `validated_unlanded`: SHAs that passed review but are not yet on the task branch —
the resumable state after a restart or a collect blocked by a tool-permission failure (a
cherry-pick escalation limit, a read-only integration checkout). Collect these without a
second review; the pass marker is a durable ledger row, so the interruption costs no rework.

Invite process feedback here: ask the subagents this wave dispatched for any reaction to
orchestrate or to working under you, recorded via `feedback record` — append-only, gating
nothing, deduped by no machine (a word's difference defeats a hash). The human may ask only
after several waves, so the file, not your memory, carries it; read it on demand — when
asked and at close — and merge by judgment then. Read task_plan and the ledgers the same
way: when a decision needs them, not wholesale.

Re-baseline task_plan to active intent, decisions, unresolved anomalies, and next gates;
closed items become pointers and Git-derived state disappears. The finding ledger is not part
of that compaction: it is append-only, and its closed rows are the correct steady state, since
closure is derived by pairing a raw row with its `Closes-Finding` commit — rewriting it would
only fork a lossy second copy. Narrative compaction of the plan itself follows
planning-with-files.

Write one retrospective every wave — waves are few, so the cost of writing beats the cost of
root skipping it — appended to the task's durable memory, judging **root and the subagents**
through three lenses:

- **efficiency** — critical-path idleness, riskless per-slice reviews, repeat dispatches,
  poor cuts (a stall read as a plan defect, not machinery to add).
- **process-following** — unprompted running-assignee contacts, review bound to an exact SHA,
  run-ahead held only for a named reason.
- **tool-utilization** — unused artifacts (a defect at close), aliases used over hand-run git,
  adoption of the derived reads.

Each nonzero or adjustment becomes one forward-only next-freeze note; deviations worth acting
on promote to the next Next gate.

## Handoff

Stop dispatching and drain to a slice boundary; writers commit and milestone, reviewers
flush findings. Run `reconcile` and `slice status`; task_plan stores only unresolved
intent, decisions, anomalies, next gates, receipt pointers, and exact SHAs — not copied
topology. Remove only tool-declared safe worktrees. The next session repeats the same
derived reads before dispatch. A handoff document — say from the `handoff` skill — is a
one-shot snapshot, not durable state: it lives in OS-temp, references artifacts rather than
copying them, and is consumed on read. The receiving root rebuilds live state from `wave
status --summary` and task_plan; it never promotes that snapshot into a maintained third
copy in the workspace, which would only drift from Git and the plan and demand endless
re-syncing.

## Skill upgrades

Pin at task start with `pin set`; state-entering commands fail if the installed release
moves, while read-only maintenance stays available. At a safe boundary `pin migrate`
repins and reports exactly what root must re-read or acknowledge removed. Cut releases only
with the one-shot `release` transaction. Because the installed skill is a live overlay,
release in a task worktree, land by merge as the atomic switch, then `doctor` the installed
path.
