# Coordination

Delegation, review, Git topology, landing, and handoff in one place. Read it once per task
before the first dispatch; the iron rules in `../SKILL.md` stay authoritative.

## Roles and dispatch

Root alone freezes work, grants authority, decides deferral, and integrates. A dispatch
names: bounded objective, workdir/scope, exact base, acceptance, stop conditions, and a
checkpoint budget in observable units (commits, items — never wall-clock). Acceptance
gates are **verbatim commands** — exact command line, workdir, environment — never a
described intent like "affected pyright" for the assignee to interpret. Named risk axes
double as the writer's adversarial self-check list before terminal; the reviewer still
verifies the same axes independently. Keep it lean: boilerplate lives in the profile;
root writes only the contract, risk axes, acceptance, and non-goals. Long contracts go
in a plain file whose path the dispatch names.

Keep each lane double-buffered: while its current slice runs, freeze the successor, so a
seam-ready writer starts the next slice instead of idling for a shadow review
(contract-planner can keep this one-deep chain stocked). Refresh at each harvest; never
stock deeper than one.

Keep the same identity for the same domain; finding fixes return to the original writer,
finding closure to the original reviewer. Spawn a new identity for independent review, a
changed domain, or genuine parallel scope. An identity can never independently review work
it implemented. Writers own every internal design decision inside the frozen seam and
report notable ones in their milestone. Reviewers are read-only toward the reviewed tree.
Agents never spawn coordination sub-agents or decide landing/deferral.

## Milestones and liveness

A milestone is one semantic envelope per observable boundary (for a writer: each commit)
plus one terminal envelope per item — `item_id`, `outcome`, `evidence`, plus `subject_sha`
for anything validated/reviewed and finding ids for `needs_fix`. Delivery is at-least-once,
deduplicated by `item_id`; a sender repeats an unacknowledged terminal envelope in its
final response. A runtime completion event means only that the turn ended.

Liveness recovery has three triggers: the runtime reports the identity errored; the runtime
declares its lease lost; or the declared checkpoint budget passes with no milestone.
Everything else is healthy — silence is model reasoning, a wait timeout is normal. On a
trigger: read runtime metadata, send one ping, then interrupt and resume the same identity
with a recovery delta; replace only when continuity is unavailable.

## Review

Depth scales with risk: mechanical → none or a root spot-check; normal internal behavior →
writer self-review plus root spot-check; root-named risk → cumulative independent review;
critical boundary → the barrier below. Two consecutive reviews yielding only minor findings
drop the next wave's default depth one level; any major finding restores it.

A reviewer inspects source first, then runs thin probes from a **detached checkout at the
exact target SHA** (`review checkout`; a live-writer tree voids the evidence). Challenge
the oracle, ownership, lifecycle, and dangerous failures — green tests prove behavior, not
that the seam is correct. The verdict is `pass` or `needs_fix`, delivered in the terminal
milestone with subject SHA, findings (severity, path, observed behavior, evidence), and a
proposed routing: gates-the-slice, follow-up-to-writer, task-plan concern, or backlog.
Root decides deferral. Findings route in three tiers: a **confirmed major** is sent
mid-review the moment it is confirmed — root routes it to the original writer at once
while the reviewer keeps scanning independent surfaces; **ordinary findings** accumulate
into the one terminal milestone; a **contract-overturning** finding stops the review and
holds every axis that depends on the broken invariant. Waiting for a terminal exact SHA
before reviewing is necessary (a moving tree voids evidence); waiting for a review
verdict before stacking the successor, or for the whole review to end before fixing a
confirmed major, is waste — review is a shadow station, and only a critical checkpoint
puts it on the line. Re-review is
finding-focused; one full review closes a named-risk surface.

**Critical checkpoint** (both features named at freeze — a dangerous state a follow-up
commit cannot cheaply undo, **and** named dependent work about to stack on it): freeze the
core as its own small slice; a different-identity reviewer tries to disprove it with a
hostile reproducer including negative paths and dangerous intermediates; the barrier holds
only the dependent work while the writer runs ahead elsewhere; after pass, release. Use a
refreshed full review only when a fix changes an authority boundary, threat model,
persistence behavior, or enough of the slice that prior evidence no longer applies.

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
- Declare each writer's file scope in a sentence; same-file or same-interface work is
  serial. A scope conflict means the split was poor — fix the plan, not the machinery.
- Shared foundation lands on integration first; dependent lanes start from that SHA.
  **Cross-identity work bases only on a seam-ready SHA** (the writer's declared-stable
  commit, `Seam-Ready: true` trailer, or the slice's terminal validated SHA) — never an
  announced SHA that later work already stacks on; findings land as follow-up commits.
- Never create or repair environments in worktrees; point the main checkout's toolchain at
  worktree sources (e.g. `UV_PROJECT_ENVIRONMENT=<main>/.venv uv run --no-sync …`, or
  `PYTHONPATH=<worktree>/<pkg> <main>/.venv/bin/python -m pytest …`).
- Resolve conflicts by recovering each side's intent; conflict resolution never invents
  behavior. Before deleting a collected lane, prove absorption
  (`git merge-base --is-ancestor <lane> <task>` or `git diff --quiet <lane> <task>`).

## Landing

Landing is one squash commit under the authority of the task's landing declaration,
serialized by the built-in lock `land finish` takes itself. Keep expensive work off-lock:
rebase `task/<task>` onto the persistence tip, run the final gate there, then
`land finish --task-sha <exact>` (plus `--confirmed` under land-with-confirmation)
re-reads the tip under the lock, squash-merges, and proves
`git diff --quiet task/<task> <landed-commit>` — content identity, not ancestry, is the
deletion authority. If the tip moved since the gate, rebase and rerun the gate; never
adapt the candidate inside the locked section. `land status` reports the finish chain
read-only and names the first missing step.

## Wave close

Reconcile Git and the durable plan; collapse each closed decision into a one-line pointer;
task_plan carries active items only. Record three discipline counters, each expected zero —
unprompted contacts to a running assignee, per-slice reviews without a named risk, repeat
dispatches for one slice — and name any nonzero count in the wave record rather than
defending it. Then answer four steering questions against the wave's evidence: **shape
fit** (overhead vs work; hidden independence), **cut quality** (any slice over one
context, stalled, or re-dispatched → recut), **parallelism** (bounded by ownership or by
habit), **adoption** (were created artifacts used). Each answer is "keep" or a one-line
next-freeze adjustment in task_plan; adjustments act forward only.

## Handoff

Stop dispatching; use remaining context to drain. Stop at a slice boundary or commit the
nearest coherent state; never hand off mid-landing or with reviewer findings trapped in
agent context — writers commit and report, reviewers flush every finding with severity and
evidence. Update task_plan Current State with branch topology, live worktrees, review
debt, run-ahead positions, and anomalies — it is the single handoff carrier; any other
handoff file holds only a pointer to it. Remove reviewer temp worktrees; list kept lane
worktrees. The next session reconciles that narrative against `git worktree list`,
branches, and exact SHAs before dispatching anything.

## Skill upgrades

Pin the task at start with `orchestrate pin set`; the state-entering commands (`lane
create`, `review checkout`, `collect`, `land finish`) fail fast if the installed skill
moves mid-task, while maintenance commands stay unguarded so a stale pin never blocks
closing down. Adopt a new version at a safe boundary with `orchestrate pin migrate`, which
repins and reports the changed documents so root re-reads exactly those. Sub-agents never
load orchestrate; root sends only the effective delta. Releases are cut only with the
one-shot `orchestrate release` (version bump + manifest + doctor succeed or roll back
together); rerunning it after an abort finishes or confirms the release
(`recovered: already-released`).
