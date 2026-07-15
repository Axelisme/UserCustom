---
name: orchestrate
description: Act as the repo-wide orchestrator — plan, delegate to specialized agents, coordinate parallel worktrees, and integrate with verification proportional to risk.
skill_version: 47
---

# Orchestrate

You are the repo-wide orchestrator: plan, delegate, integrate, verify. Coordination state
lives in exactly three native carriers — **Git** (code and branch topology), **agent context**
(work in progress), and the **plan directory** (cross-session narrative). This skill defines
conventions plus a few hard rules; it never creates state files.

This skill is **root-only**: sub-agents never load it. Knowledge is three-layered — this
skill holds root's coordination doctrine; each role's standing orders live in its role
profile; task specifics (SHAs, scope, queue, packet) arrive in the spawn/follow-up prompt.
A rule a sub-agent needs belongs in a profile or the prompt, never in this file alone.

## Design principles

1. **Git is the database.** Branches, SHAs, worktrees, and merges are the records.
   `git worktree list` is the registry, `git status` is the diagnostic, and a merged branch
   is a completed lane. No shadow state, no receipts.
2. **Conventions over enforcement.** Write scope, lease, and review assignments live in spawn
   prompts; violations are caught by merge conflicts and review, not preflight machinery.
3. **Ceremony proportional to risk.** The critical list is short and closed (see hard rules);
   everything else is self-reviewed with a one-line rationale in the conversation.
4. **No re-bloat.** Log process friction with `candidate-backlog` instead of adding rules on
   the spot; this skill must not grow task-state files or new coordination CLIs. The single
   sanctioned primitive is the ephemeral merge slot (`$SKILL_DIR/scripts/merge_slot.py`,
   lock + FIFO only); it must never record task state.

Except for the closed list in **Hard rules**, the patterns below are recommended defaults,
not a workflow state machine. The orchestrator may simplify, reorder, or omit them when task
risk and runtime capabilities justify it, while preserving the hard rules and briefly stating
the reason when the choice is not obvious.

## Terms and branch hierarchy

- **Main checkout** = the repo-root working directory — a *place*, not a branch. It normally
  stays on the user's feature branch and is the only place with the full environment (e.g.
  the repo's `.venv`); every gate that needs the full environment runs here.
- **Persistence branches** = `main` and the user's feature branches. Their history is
  immutable: never amended, never force-pushed; work lands on them only as reviewed, squashed
  commits with the user's explicit authority.
- Branch hierarchy: persistence branch ← `task/<task>` (integration branch, exactly one per
  task) ← `agent/<task>/<lane>` (lane branches, zero or more, one writer each). Everything
  below the persistence boundary is orchestrator-owned and **mutable**: amend, rebase, and
  merge freely — but rewrite integration history only between waves (never under a lane that
  is based on the rewritten range), and any SHA whose review mattered must be re-reviewed
  after rework.

## Single writer (the default path)

Pure Q&A, read-only research, and single-round reviews create nothing — no branch, no plan
directory. Single-writer code changes work directly on the task branch with **no worktree
and no lanes**: `git switch -c task/<task>` in the main checkout, implement in place, run
targeted tests and the full gate with the real environment, then land it (see "Landing") and
delete the task branch. Use a worktree for a single writer only when the main checkout must
stay available (the user is using it, a GUI runs from it) or dirty state would conflict.

## Multi-writer parallelism

A multi-writer task = multiple worktrees; **one writer per worktree at a time** (a Git-index
physical constraint, not bureaucracy).

Parallel writers rally on the task's integration branch — all plain git:

```bash
git branch "task/<task>" <base>
git worktree add ".agent_state/worktrees/<task>-<lane>" -b "agent/<task>/<lane>" "task/<task>"
# spawn one implementer per worktree; the prompt states exactly which files it owns
# collect lanes as they finish (inside the integration worktree):
git merge --no-ff "agent/<task>/<lane>"   # resolve conflicts in place, or send back for rebase
# resolving in place: recover each side's intent (commit messages, task plan) and preserve
# both; where incompatible, pick per the task's goal and note the trade-off — a conflict
# resolution never invents new behavior
git worktree remove ".agent_state/worktrees/<task>-<lane>"
# after verifying that the lane was collected, remove its branch (see guidance below)
# all collected → run the full gate once → land on the persistence branch (see "Landing")
```

Coordination conventions:

- Declare each writer's file scope in one sentence in its spawn prompt. A merge conflict means
  root split the work badly — fix the plan, don't add rules.
- Work touching the same files or the same public API/schema/fixture is never parallelized;
  it goes into one worktree, serialized under one agent.
- Root merges serially, always. Root is single-threaded — that *is* the merge queue.
- Shared foundation that multiple lanes depend on lands on the integration branch first;
  other worktrees start from that SHA.
- Never copy, create, or repair environments (`.venv`, `node_modules`, caches) in worktrees.
  Run targeted tests with the main checkout's toolchain pointed at the worktree sources — in
  a Python repo a reliable recipe is
  `PYTHONPATH=<worktree>/<pkg-root> <main-checkout>/.venv/bin/python -m pytest ...`; follow
  the repo's documented test recipe when it names one. Anything needing the full environment
  runs in the main checkout.
- Before deleting a collected lane branch, hold evidence it was absorbed —
  `git merge-base --is-ancestor <lane> <task>`, or tree identity via
  `git diff --quiet <lane> <task>`. With such evidence `git branch -D` is fine; `-D` itself
  is never the evidence.

## Landing on a persistence branch

Landing = squash. A finished task lands as **one squashed commit** on the persistence branch,
with the user's explicit authority; afterwards delete `task/<task>` and any remaining lanes
(a squash commit shares no ancestry with the integration branch, so the branch is dead once
landed — one task, one integration branch, one landing).

Multi-task contention is serialized by the **merge slot** (`$SKILL_DIR/scripts/merge_slot.py`,
skill-relative; an ephemeral lock + FIFO queue, never task state — deleting
`.agent_state/merge-slot/` at any time is safe, the worst case is re-queueing):

```bash
<repo-python> "$SKILL_DIR/scripts/merge_slot.py" --root <repo> \   # e.g. .venv/bin/python
  status | claim <task> [--wait N] | renew <task> | release <task> | yield <task>
```

Do the expensive work **off-slot**; hold the slot only for the final seconds:

1. Off-slot: rebase `task/<task>` onto the persistence tip, run the full gate once, note the
   tip SHA the gate ran against.
2. `claim <task>`; once acquired, re-read the persistence tip.
3. Tip unchanged → squash-merge, `release`. Tip moved → probe with
   `git merge-tree --write-tree` (no worktree needed): conflict-free **and** the new commits
   are path-disjoint from this task's diff → rebase in place, rerun the thin checks, merge,
   `release` (`renew` once if needed); anything else → `yield` and restart from step 1.

## Persistent agents and roles

- **Domain lease (convention).** The next slice of the same domain goes to the same agent by
  default, as a follow-up carrying only the delta (current SHA, new finding / next slice,
  scope changes). Spawning a new agent requires an articulable reason (independent identity
  needed, domain changed, genuinely parallel scope). A finished turn, checkpoint, or commit
  does **not** end ownership.
- Finding fixes return to the original implementer; closure and refreshed-SHA reviews return
  to the original reviewer.
- **Warm reviewer lease.** A warmed-up reviewer is paused and resumed, not respawned: pause =
  end of turn, resume = follow-up with only the refreshed target SHA and finding/evidence
  delta; idle or completed does not end the lease. Warm-up delivers exactly four artifacts
  (source map, acceptance/adversarial matrix, stop conditions, deletion checklist); the
  formal review cites that matrix and adds only exact-diff inspection.
- If same-identity continuation is needed but the runtime lacks the capability, report to the
  user for a decision; do not silently respawn a fresh identity and rebuild context.
- Role profiles: `contract-planner`, `repo-investigator`, `implementer`,
  `mechanical-implementer`, `reviewer`, `integration-reviewer`; `web-researcher` and
  `mcp-skill-tester` as needed. Read-only roles not writing files is behavioral discipline,
  not runtime enforcement. Reviewers are **not** sandbox-read-only: executing gates
  inherently writes (their own detached worktree under `.agent_state/worktrees/`, tool
  caches), so they hold workspace-write with behavioral guardrails — the invariant is the
  immutability of the reviewed SHA, not the absence of writes.
- **When to delegate planning.** Root plans inline by default. `repo-investigator` when the
  open question is factual; `contract-planner` when the contract or write split has not
  converged **and** the reading is too deep for root to carry, an unanchored derivation
  matters on a critical axis, or the next wave can converge during the current one. Planner
  output is evidence, never the decision; a frozen contract dispatches straight to writers
  (reviewer verifies implementations against contracts, never unconverged contracts).
- Profiles may point a role at **content** skills (vocabulary, checklists, conventions —
  e.g. `codebase-design`, `domain-modeling`) to *read* as reference. Sub-agents never
  *invoke* **coordination** skills (`code-review`, `research` — anything that spawns agents
  or re-derives dispatch inputs); those are root's. To apply a coordination skill's
  checklist inside a review, root names that lens in the packet's `reviewer_focus`.
- The mapping of abstract capabilities (spawn / follow-up / interrupt / wait) to the current
  runtime's actual tools lives at `$SKILL_DIR/runtime-<runtime>.md` — `runtime-claude.md` for
  Claude Code, `runtime-codex.md` for Codex (hand-maintained; read the one matching the
  runtime you are running in).

## Review closure guidance

**Review depth follows the changed surface, not the task's highest global risk.** Label each
checkpoint's diff by what it actually touches:

- **Critical** — the closed hard-rule list (hardware, persistence/migration, public wire
  schema, security) plus any surface the packet's `critical_axes` explicitly declares for
  this task → **one** different-identity reviewer covering the whole diff. This is not the
  two-agent `code-review` skill: that two-axis audit is a **milestone gate** root runs once
  at wave end or before landing, never per slice and never by a sub-agent.
- **Normal** — internal presenters, adapters, GUI glue, private lifecycle → one focused
  single-pass review of the changed behavior, or root self-review with a one-line rationale.
- **Mechanical** — deletions, renames, fixture moves, docs wording → root spot-check
  (scope, tree identity, a targeted scan); no reviewer dispatch.

A critical *task* does not make every checkpoint critical; only checkpoints whose diff
crosses a critical surface pay the full gate.

**Evidence ownership is deliberately non-duplicative.** Writer: functional acceptance plus
affected regression. Reviewer: adversarial repros, finding-specific tests, source audit —
never a rerun of the writer's suites. Root: identity checks (SHA, parent, scope, tree
identity) plus at most one thin critical slice. Integration: the single broad gate (hard
rule 1). Rerunning another role's evidence requires a stated reason (e.g. suspected
environment skew), not habit.

Before dispatching a frozen diff, root gives the reviewer a compact **review-readiness packet**.
It is an in-band checklist, not a new file or schema; trim fields that genuinely do not apply:

```text
base_sha: <review base>
target_sha: <exact immutable SHA>
frozen_contract: <task-plan / ADR pointer plus required invariants>
critical_axes: <hardware / persistence / public wire / security / none>
changed_surface: <paths, boundaries, lifecycle or wire behavior>
acceptance_and_evidence: <targeted commands and results>
known_anomalies: <exact failed command, classification, replacement evidence>
invalid_substitutes: <old-SHA reviews, partial suites, or unproved tree equivalence>
reviewer_focus: <dangerous failure modes and explicit non-goals>
```

Missing base/target SHA, frozen contract, or changed surface is a readiness failure, not a
request for the reviewer to reconstruct the assignment. For each critical axis, name the
dangerous failure mode. A review of an old SHA, an aborted suite, or tree equivalence that does
not cover the changed surface is never silently promoted into target-SHA sign-off. Finding
closure returns to the same reviewer with only the refreshed target, finding delta, and changed
evidence.

**Re-review scope and round budget.** Re-review is finding-focused by default — the finding
delta plus its high-risk adjacent surface — escalating to a fresh full review only when the
rework itself altered authority, persistence, public schema, or process lifecycle
(docs-only closure: current-state wording, links, negative scans — nothing more). One
checkpoint gets one full review plus one focused closure; a new P1 in a third round means
the contract, source map, or test model is wrong — stop patching and reset via the
blast-radius protocol's contract-level branch. When two consecutive rounds' findings
cluster in one failure family (races, lifecycle ordering), fix the test model before
widening the production diff.

**Review execution is immutable.** Gates run only from immutable checkouts: `git show` /
`git diff` for pure reading; a detached temporary worktree at the exact SHA (or a provably
frozen clean lane) for anything executed — never a checkout with a live writer, and results
from a checkout that turns out to have been live are void. Only a **review checkpoint** (a
clean committed SHA announced for review) starts a gate; a writer's dirty **code
checkpoint** (progress, blast-radius, cherry-pick safety) never does. Operational detail
lives in the reviewer profile.

Reviews attach to the exact SHA they inspected. After a reviewed lane is collected, choose
closure evidence proportional to the merge: integration tree expected to equal the reviewed
lane tree → `git diff --quiet <lane-sha> <integration-sha>` and record the tree identity;
trees differ → if a critical surface may have changed (or unchanged content cannot be
demonstrated) send the integration SHA to the different-identity reviewer, otherwise a
concise root self-review rationale suffices. A conflict-free merge alone never demonstrates
equivalence.

## Dispatch: slice queue guidance

When the contract is frozen and per-slice acceptance can be written down, a
**pre-authorized slice queue** is often more efficient than one order per turn. Consider handing
the writer an ordered queue (3–5 slices; split longer plans into waves so the lead keeps
steering points).
The writer works through it autonomously — checkpoint commit + targeted tests + milestone
notification at each boundary, then straight into the next slice, no ack round trip.
Single-slice dispatch remains the fallback for exploratory work where each result must steer
the next step.

A compact queue prompt will often cover the following. Treat it as a checklist to trim or
extend, not a required schema:

```text
profile: <requested role; runtime-effective role when relevant>
lease + write scope: <domain owner; the only files this writer may change>
slices: <ordered 3–5 slices, each with acceptance and targeted checks>
critical shaping: <axes; foundation checkpoint or review-before-next-slice; rationale>
stop conditions: <task-specific additions only — standing ones live in the profile>
milestone delivery: <deviations from the standing contract only>
```

- The queue lives in the agent's context (spawn prompt, extended by follow-up deltas) or, for
  cross-session work, in the domain packet. Never in a queue file or CLI — a queue that
  outlives the lead's ability to steer is a bug, not a feature.
- A queue never expands authority: items are pre-authorized and same-scope, and a writer
  never invents the next item. Preemption order: stop conditions > retract-class findings
  (design-invalidating, dangerous-intermediate, scope-collision) > next queued item >
  deferred (ledger) findings. An exhausted queue ends the turn; the lease is retained.
- **Findings default to the ledger, not to preemption.** The reviewer reports; root decides
  deferral by one question — *is the fix mechanical to propagate later, or would deferral
  force re-design?* A signature / parameter / return / naming / local-bug finding is
  mechanical, so it accumulates in the finding ledger **even when it touches an interface**:
  batching an interface fix until every call site exists yields a better fix (informed by all
  callers, cut once against them) and pays the interrupt cost zero times — "touches contract"
  is not by itself a reason to preempt, and interrupting an agent mid-flow costs more than the
  linear cost of propagating the fix later. Only three **retract classes** pull the queue back
  to single-writer immediately:
  - **design-invalidating** — the fix changes downstream *logic*, not just its call sites
    (wrong seam, approach, or ownership); every further slice would build on a refuted premise;
  - **dangerous-intermediate** — persistence/migration, public wire, or security, where a
    broken state must not exist even transiently across slices;
  - **scope-collision** — the fix must touch a file the writer is about to write (a scheduling
    constraint, not a severity one).
  Everything else waits for the wave fix; outside-task findings go to the candidate backlog.
- **Pipelining across the wave.** A warm reviewer consumes announced SHAs asynchronously while
  the writer runs ahead through the queue; announced commits stay append-only and the writer
  does not block on review. Review lags implementation by design — the reviewer inspects each
  frozen SHA from an immutable checkout while the writer is already further along, and findings
  collect in the ledger. The wave itself (3–5 slices) is the accumulation bound; the retract
  classes above are the only brakes, and absent them the writer never stops for review. A
  deferred fix keeps its ledger slot only while its scope stays **surface-disjoint** from what
  the writer is about to touch — a collision reclassifies it as scope-collision and pulls it
  forward. Critical slices (hard-rule surfaces or declared `critical_axes`) do not pipeline:
  they hold `review-before-next-slice`, since building on an unreviewed
  persistence/wire/security change is exactly the compounding the accumulation model refuses.
- **Wave-boundary fix wave.** The finding ledger drains at the wave boundary, not per slice:
  root dispatches one fix wave that applies contract/interface fixes **first** (widest
  propagation, cut once against all now-known call sites) then local fixes, so a local fix
  never lands in code the interface propagation is about to rewrite. Re-verify stays
  finding-focused — each fix re-checked at its own thin slice on the current HEAD SHA, an
  interface fix sweeping its call sites in one pass — never a whole-wave re-review. Retract
  classes never reach this wave: by definition they already stopped or pulled forward.
- Before dispatch into an area, check its candidate backlog
  (`candidate-backlog list --area <area> --status inbox`): rider items on the same code may
  fold into a slice at near-zero cost — never as scope expansion. At task closeout, close
  inbox items this task resolved or obsoleted.
- Before dispatch, label the closed-list critical axes each slice crosses. Two or more axes →
  root explicitly chooses (a) a foundation checkpoint freezing the shared contract/boundary
  first, or (b) `review-before-next-slice` when splitting would create an untestable
  half-change. **Three or more authority boundaries** (critical axes plus surfaces like
  operation lifecycle or frontend projection) → default to splitting, foundation first then
  vertical remainder; keeping it whole requires a stated reason. File count is only a warning
  signal; axes, boundary count, and independent acceptance determine the shape.
- The opposite bound holds too: prefer a **medium vertical slice** — one authoritative
  contract, one real consumer, end-to-end acceptance, and the old path's deletion in the
  same checkpoint — over micro-checkpoints whose review overhead exceeds their isolation
  benefit. A shared foundation earns its own checkpoint and review only when multiple later
  slices genuinely consume it.
- Wall-clock circuit breakers: a slice with no clean checkpoint after roughly 60–90 minutes
  reports the bottleneck instead of grinding on; a reviewer over budget reports its
  confirmed deterministic findings immediately and finishes the rest as a follow-up.
- **Standing vs delta.** The milestone contract (recipient, mechanism, payload, timing,
  no-ack, run-ahead limit, fallback) and the notification points (**inventory / first-green
  / failure-cluster / clean-SHA**) live in the role profile and runtime binding; prompts
  state only deviations — same for stop conditions and report formats. Delivery is
  verified, not assumed: the inventory milestone must confirm which profile was loaded; no
  confirmation → root pastes the contract verbatim before dispatching further slices.

When a problem with announced slice N surfaces during N+1 (a review finding or the
implementer's own discovery), the implementer checkpoints first — nearest coherent point,
commit the work in progress; task/lane commits are free because landing squashes them — and
classifies the fix in its report (full protocol in the implementer profile). A mechanically
propagatable fix — localized, or a signature/interface change whose downstream cost is just
re-wiring call sites — goes to the finding ledger and lands in the wave fix while the writer
continues. Only the retract classes stop the flow: a fix that changes downstream *logic*
(design-invalidating) stops the queue with `needs_decision` for root to re-plan; a
dangerous-intermediate or scope-collision fix pulls forward. Root treats the classification
as the routing signal and never lets useful uncommitted work be discarded.

## Validation anomalies

An abort, signal, timeout, interpreter crash, Qt teardown/GC failure, or subprocess failure is
not an assertion failure and is not a pass. Preserve the first failure's exact command, target
SHA, exit status/signal, phase, and useful artifact. Re-run the same broad command at most once,
and only with a stated diagnostic purpose; never retry until green.

Build the smallest evidence ladder that covers the original acceptance surface:

1. deterministic non-GUI / non-subprocess tests;
2. focused GUI or subprocess tests;
3. a minimal lifecycle / teardown reproducer;
4. isolated-process execution when shared interpreter state may be the harness fault.

A deterministic assertion or reproducible product behavior is an ordinary blocking failure.
If only the combined harness fails while the split gates reliably cover the same surface, record
the combined command as **unusable evidence**, report the replacement evidence, and never claim
the original suite passed. If harness fault and product risk cannot be separated, keep the risk
open and block collection/landing. Carry the anomaly classification and coverage gap into the
review-readiness packet.

## Durable narrative (the only file-based state)

- Cross-session, multi-round, or information-heavy tasks use `planning-with-files`
  (`.agent_state/plans/<task-id>/`); one-shot tasks create nothing.
- **task_plan is the single ledger; a domain packet is its current-state cache.** Only tasks
  with several concurrent domains split out `domains/<domain>.md` under the plan directory
  (one page: owner/reviewer, current SHA, pointers to frozen decisions plus one-line
  summaries, next step). A new session's agent resumes from that page. Single-domain tasks
  skip `domains/` — the "current status" section of task_plan.md plays the same role.
- A packet never copies decision text (decisions are recorded once, in task_plan or an ADR).
  It is rewritten whole at lease handoffs or checkpoint boundaries and deleted when the
  domain completes; task_plan keeps its usual phase append-and-compress rules.
- **Control plane vs data plane.** Reports return in-band; messages carry events and
  decisions (milestones, finding severity, dispatch). Files carry only evidence: bulk
  payloads (raw logs, long analyses, failure matrices) go to
  `.agent_state/artifacts/<task>/<agent>-<topic>.md` — disposable, deleted at task close —
  while cross-session artifacts (an investigator's source map) go to the plan directory.
  The report carries the digest plus the path; root reads artifacts selectively
  (grep/tail). A file never signals state, carries an instruction, or substitutes for a
  report — if root must read a file to know what to do next, that is a bug. No mandatory
  per-agent report files.

## Session handoff (rate-limit or context exhaustion)

The moment root decides to hand off, it stops dispatching new work — the remaining budget
is for draining. Stop at a slice boundary when possible, else checkpoint-commit the nearest
coherent state; never stop holding the merge slot (`release`/`yield` first), mid-collection,
or with unreported findings in a reviewer's context.

Drain before writing: writers checkpoint-commit and report; reviewers flush every finding
with severity and evidence — sub-agent context evaporates, and leases do not survive the
session, so the packet must let a **new** reviewer identity take over without findings
disappearing. Then update the domain packet / task_plan Current State (the only handoff
artifact — no separate handoff document) with the orchestrate-specific state: branch
topology and live worktrees, review debt (announced SHAs not yet signed off), run-ahead
position, the finding ledger including deferred items, and any unusable-evidence anomaly.
Remove reviewer temp worktrees; keep lane worktrees and list them. The new session's first
act is reconciling the packet against `git worktree list` and branch state.

## Hard rules (this is all of them)

1. A branch that has not passed targeted tests is not merged. The full suite runs **once** in
   the main checkout against the final integrated tree (single writer: on the task branch
   before landing; multi-writer: after all lanes are collected — one or the other, never both).
2. Critical diffs require a different-identity review. The closed list: **hardware operation,
   persistence/migration, public wire schema, security.**
3. Persistence branches (`main`, feature branches) are never amended or force-pushed, and
   landing on them requires the user's explicit authority — always as a single squashed
   commit through the merge slot. **MCCT** = the user grants final merge authority for this
   task (push not included).

## Definition of done

Design settled, diff tested and reviewed proportionally to risk, all parallel lanes collected,
worktrees and temporary branches cleaned up, and a short evidence summary reported.
