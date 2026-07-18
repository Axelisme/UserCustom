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
verifies the same axes independently. For slices touching ownership schedulers,
projections, event streams, receipts, or callbacks, name
[publication-review](publication-review.md) as a risk axis. Boilerplate lives in the
profile; root writes only the contract, risk axes, acceptance, and non-goals. Long
contracts go in a plain file whose path the dispatch names.

Double-buffer each lane per the SKILL pipeline model; contract-planner can keep the
one-deep chain stocked, refreshed at each harvest.

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
final response. A runtime completion event means only that the turn ended. Envelope
Git facts (`subject_sha`, parents, tree, clean state, trailers) are generated with
`slice milestone --item <id>`, never hand-transcribed — retyped SHAs have bound reviews
to the wrong commit. A schema-complete milestone that was received stands as evidence
even if the sender's final transport later errors — a runtime completion error never
retroactively voids it; conversely, with no terminal milestone, no verdict may be
inferred from any other signal.

Liveness recovery has three triggers: the runtime reports the identity errored; the runtime
declares its lease lost; or the declared checkpoint budget passes with no milestone.
Everything else is healthy — silence is model reasoning, a wait timeout is normal. On a
trigger: read runtime metadata, send one ping, then interrupt and resume the same identity
with a recovery delta; replace only when continuity is unavailable.

## Review

Depth scales with risk: mechanical → none or a root spot-check; normal internal behavior →
writer self-review plus root spot-check; root-named risk → cumulative independent review;
critical boundary → the barrier below. Two consecutive reviews yielding only minor findings
**on the same risk surface** drop that surface's next default depth one level — a new
domain or risk axis starts at its own default; any major finding restores it.

A reviewer inspects source first, then runs thin probes from a **detached checkout at the
exact target SHA** (`review checkout`; a live-writer tree voids the evidence). For a
finding-closure chain, `review advance --from <reviewed> --to <fix>` moves the same
detached workspace to the new subject with the same proofs, instead of piling up one
worktree per round. Challenge
the oracle, ownership, lifecycle, and dangerous failures — green tests prove behavior, not
that the seam is correct. The verdict is `pass` or `needs_fix`, delivered in the terminal
milestone with subject SHA, findings (severity, path, observed behavior, evidence), and a
proposed routing: gates-the-slice, follow-up-to-writer, task-plan concern, or backlog.
Root decides deferral. Findings route in three tiers: a **confirmed major** is sent
mid-review the moment it is confirmed — root routes it to the original writer at once
while the reviewer keeps scanning independent surfaces; **ordinary findings** accumulate
into the one terminal milestone; a **contract-overturning** finding stops the review and
holds every axis that depends on the broken invariant. Root delivers accumulated ordinary
findings to the assignee at that assignee's next declared milestone (commit or item
envelope) — replying at a declared boundary is harvest, not an unsolicited
running-assignee contact. A **public-contract correction** means the frozen seam itself
changed — interface, acceptance, write scope, or base; anything that leaves the frozen
contract intact is a finding or advice and waits for a milestone boundary. Waiting for a terminal exact SHA
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
  serial (a scope conflict is a structural hazard — recut per the SKILL pipeline model).
  The sole overlap exception is a root-declared **append-only shared** file (registration
  lists, import blocks, changelogs — no semantic coupling between entries); writers touch
  it concurrently and the textual merge is trusted.
- While two lanes run, a zero-cost `git merge-tree <merge-base> <laneA> <laneB>` dry run
  surfaces textual collisions before either terminals — an early warning to correct a
  contract, never a license to overlap. A clean result proves nothing semantic: interface
  conflicts live across files where Git cannot see them, which is why write scopes are
  declared in prose, not derived from paths.
- Shared foundation lands on integration first; dependent lanes start from that SHA.
  **Cross-identity work bases only on a seam-ready SHA** (the writer's declared-stable
  commit, `Seam-Ready: true` trailer, or the slice's terminal validated SHA) — never an
  announced SHA that later work already stacks on; findings land as follow-up commits.
- A successor needing **two seam-ready but unvalidated lanes** starts from a
  `compose-base` composite: a merge of the named lane SHAs on `spec/<task>/<name>`,
  marked `Speculative-Base: true` with one `Depends-Lane` per input. It is a base for
  run-ahead only — `collect` refuses any lane whose history carries a composite whose
  dependencies are not yet on the task branch, so speculation never leaks into
  validated integration. A textual conflict while composing is a structural hazard
  surfacing early: recut or serialize, never hand-resolve the composite.
- Commit trailers carry attribution across run-ahead: every slice commit names
  `Item: <id>`; a finding fix adds `Closes-Finding: <id>`, even when it lands on a
  successor's branch. Re-review binds to the commits carrying `Closes-Finding`, not the
  whole branch, so a successor's terminal SHA may include predecessor corrections without
  blurring whose closure they are.
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
task_plan carries active items only. Reconcile `git worktree list` against the plan's
lanes and review debt, sorting every worktree into: active writer, holding open review
debt, validated/closed (delete now, one batch), or orphan with no durable evidence —
an orphan is an adoption defect, counted, then deleted. Record three discipline counters, each expected zero —
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

Pin the task at start with `orchestrate pin set`; every command that creates or mutates
lane/spec/review/integration/persistence state fails fast if the installed skill moves
mid-task, while read-only and maintenance commands stay unguarded so a stale pin never
blocks closing down. Adopt a new version at a safe boundary with `orchestrate pin migrate`,
which repins and reports the changed documents so root re-reads exactly those; removed
documents are listed separately (`acknowledge_removed`) — acknowledge they are gone, do
not hunt for them. Sub-agents never load orchestrate; root sends only the effective delta.
Releases are cut only with the one-shot `orchestrate release` (version bump + manifest +
doctor succeed or roll back together); rerunning it after an abort finishes or confirms the
release (`recovered: already-released`). Because the installed skill is a live overlay, cut
the release inside a task worktree and land it by merge — the worktree is the staging area,
the merge the atomic switch — so the installed path never shows a half-written release,
then `doctor` the installed path once after the merge.
