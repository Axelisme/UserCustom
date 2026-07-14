---
name: orchestrate
description: Act as the repo-wide orchestrator — plan, delegate to specialized agents, coordinate parallel worktrees, and integrate with verification proportional to risk.
skill_version: 33
---

# Orchestrate

You are the repo-wide orchestrator: plan, delegate, integrate, verify. Coordination state
lives in exactly three native carriers — **Git** (code and branch topology), **agent context**
(work in progress), and the **plan directory** (cross-session narrative). This skill defines
conventions plus a few hard rules; it never creates state files.

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
- For routine `--no-ff` collection, `git merge-base --is-ancestor <lane> <task>` is a useful
  absorption check before branch cleanup. If `git branch -d` complains only because the
  current checkout does not see that ancestry, root may use `git branch -D` after establishing
  equivalent evidence (for example, expected tree identity via `git diff --quiet <lane> <task>`).
  These are suggested proofs, not a mandatory command sequence; `-D` itself is never evidence
  that a lane was collected.

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
- **Warm reviewer lease.** A warmed-up reviewer (failure matrix built, surface understood) is
  paused and resumed, not respawned: ending its turn after warm-up or a review round is the
  standard pause; the standard resume is a follow-up carrying only the refreshed target SHA
  and the finding/evidence delta. An idle or completed state does not end the lease.
- If same-identity continuation is needed but the runtime lacks the capability, report to the
  user for a decision; do not silently respawn a fresh identity and rebuild context.
- Role profiles: `contract-planner`, `repo-investigator`, `implementer`,
  `mechanical-implementer`, `reviewer`, `integration-reviewer`; `web-researcher` and
  `mcp-skill-tester` as needed. Read-only roles not writing files is behavioral discipline,
  not runtime enforcement.
- The mapping of abstract capabilities (spawn / follow-up / interrupt / wait) to the current
  runtime's actual tools lives at `$SKILL_DIR/runtime-<runtime>.md` — `runtime-claude.md` for
  Claude Code, `runtime-codex.md` for Codex (hand-maintained; read the one matching the
  runtime you are running in).

## Review closure guidance

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

**Review execution is immutable.** Naming an exact SHA is necessary but not sufficient — a
reviewer must never *execute* anything from a checkout a writer may still touch:

- Pure reading reviews can work from `git show <sha>:<path>` / `git diff <base> <sha>` without
  any checkout.
- Any reviewer-run gate (tests, type checks, reproducers) executes in a detached temporary
  review worktree at the exact SHA (`git worktree add --detach <path> <sha>`, removed after),
  or in a lane checkout that is provably frozen and clean — never in a worktree with a live
  writer.
- The moment the writer resumes work in a lane, that lane's checkout is invalid for validating
  any previously announced SHA. Results already collected from a checkout that turns out to
  have been live are void — discard them and rerun from an immutable checkout; they are never
  evidence.

Two checkpoint kinds, not one. A **code checkpoint** is writer-side and may be dirty — it
exists for progress, blast-radius classification, and cherry-pick safety, and never enters a
formal gate. A **review checkpoint** is a clean committed SHA explicitly announced for review;
only these start reviewer gates.

Reviews attach to the exact SHA they inspected. After a reviewed lane is collected, the
orchestrator chooses evidence proportional to the merge:

- When the integration tree is expected to equal the reviewed lane tree,
  `git diff --quiet <reviewed-lane-sha> <integration-sha>` is a cheap, strong equivalence check;
  record the reviewed tree identity rather than requesting a ceremonial review of a merge SHA.
- When the trees differ, decide whether composition or conflict resolution changed the reviewed
  surface. If a critical surface may have changed or unchanged content cannot be demonstrated,
  send the integration SHA to the different-identity reviewer. For noncritical composition, a
  concise root self-review rationale is normally sufficient.

Tree identity is one useful closure strategy, not the only valid proof. A conflict-free merge
alone does not demonstrate equivalence.

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
stop conditions: <contract uncertainty, scope collision, critical surprise, ...>
milestone delivery: <recipient, runtime mechanism, timing, payload, failure fallback>
```

- The queue lives in the agent's context (spawn prompt, extended by follow-up deltas) or, for
  cross-session work, in the domain packet. Never in a queue file or CLI — a queue that
  outlives the lead's ability to steer is a bug, not a feature.
- A queue never expands authority: items are pre-authorized and same-scope, and a writer
  never invents the next item. Preemption order: stop conditions > contract-affecting review
  findings > next queued item > deferred findings. An exhausted queue ends the turn; the
  lease is retained.
- Findings route by severity, not uniformly: a finding that invalidates a premise of upcoming
  slices (P1, contract or interface change) preempts immediately — deferring it means building
  on a known-wrong premise, and rework compounds with distance. A real but self-contained
  finding (naming, minor cleanup, a missing secondary test) does not interrupt the writer: it
  goes to the finding ledger and is fixed in one dedicated cleanup slice at the end of the
  queue, or logged to the candidate backlog when it falls outside the task. Deferral is root's
  explicit call — the reviewer reports severity, never silently downgrades.
- With a warmed-up persistent reviewer consuming announced SHAs, this pipelines review of
  slice N with implementation of N+1. By default, run at most one unreviewed slice ahead and
  keep announced commits append-only (follow-up commits only, no rewriting).
- Run-ahead is conditional, not free: slice N+1 qualifies only if it is **surface-disjoint**
  from the SHA under review — it must not modify the public wire, schema, shared fixtures, or
  the same state machine slice N touches (tests-only cleanup, docs, and independent adapters
  usually qualify; work on the reviewed contract never does). When a finding may change the
  next slice's interface — or any P1 / contract-level finding lands — run-ahead retracts to
  single-writer until the finding is resolved.
- Before dispatch, label the closed-list critical axes each slice crosses. When one slice crosses
  two or more axes, root explicitly chooses either (a) a coherent foundation checkpoint that
  freezes the shared contract/boundary first, or (b) `review-before-next-slice` when splitting
  would create an untestable half-change. A slice spanning **three or more authority
  boundaries** (critical axes plus surfaces like operation lifecycle or frontend projection)
  defaults to being split — foundation first, vertical remainder — because its review surface
  outgrows one gate; keeping it whole requires a stated reason. File count is only a warning
  signal; critical axes, boundary count, and independent acceptance determine the shape.
- The milestone contract is a fixed field of every spawn/follow-up prompt — never delegated
  to profile injection (profiles may restate it, but runtimes do not guarantee they load):
  recipient, mechanism, payload, boundary timing, no-ack continuation, run-ahead limit, and
  failure fallback. Standard notification points, trimmed per task: **inventory** (scope and
  source map confirmed), **first-green** (first slice passing targeted tests),
  **failure-cluster** (a related group of failures worth steering on), and **clean-SHA** (a
  committed review checkpoint ready for gates).

A useful event rhythm is: announce slice N's milestone, begin N+1, and let the reviewer consume
N in parallel. One unreviewed slice ahead is the safety default; root may tighten or relax it
after considering review latency, surface stability, and likely rework cost. If a finding arrives
before N+1 reaches a checkpoint, preserve the nearest coherent state and then use the
blast-radius guidance below.

When a problem with an announced slice N surfaces during N+1 (a review finding, or the
implementer's own discovery):

1. **Default to checkpointing first.** Reach the nearest coherent point and commit the N+1 work
   in progress. Avoid discarding useful uncommitted work — task/lane commits cost little because
   landing squashes them away; an abandoned attempt can remain as a dead-end commit.
2. **Classify the fix's blast radius** (the implementer judges and states the classification
   in its report):
   - *Localized* — the fix touches no surface N+1 builds on → fix N as a follow-up commit,
     rerun the thin checks, resume N+1 on top; all progress kept.
   - *Surface-changing* — the fix alters an interface/schema N+1 uses → fix N, then adapt:
     keep the checkpointed parts that don't touch the changed surface, redo the rest (the
     checkpoint stays in history as a cherry-pick source).
   - *Contract-level* — slice N's premise itself is wrong → stop the queue, report
     `needs_decision` with everything checkpointed; the lead re-plans.

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
- Agent reports are returned in-band to root by default; root digests what is worth keeping
  into the domain packet. Only two exceptions write files: artifacts worth reusing across
  sessions (e.g. an investigator's compact source map — into the plan directory), and
  cross-terminal agents that cannot return in-band. No mandatory per-agent report files.

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
