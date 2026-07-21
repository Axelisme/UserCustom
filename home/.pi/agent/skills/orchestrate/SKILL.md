---
name: orchestrate
description: Control loop for repo-wide work that needs multi-agent pipelines, independent risk review, parallel worktrees, or integration across task branches.
skill_version: 115
---

# Orchestrate

This skill exists for two things: **parallel lanes and the pipeline that keeps them
full**; everything else is supporting infrastructure. You **own the control flow** — the
loop, its stops, its dispatch and its integration are yours, not a framework's and not the
assignees'. Run it to retire the most consequential uncertainty with the largest move you
can still prove safe. **Git is the durable log**: commits, SHAs, and trailers are the
state of record — current state, what was reviewed, whether a lane is absorbed are each a
*derived read* of git, never a hand-kept copy that drifts. The task plan carries only what
git cannot derive: intent, decisions, judgment. Optimize **critical-path lead time**, not
agent utilization; a redone slice is cheaper than machinery that prevents redoing it.

## Iron rules

Installed in the matching always-resident runtime context (`~/.codex/AGENTS.md` or
`~/.pi/agent/APPEND_SYSTEM.md`) because they must
survive context compaction; everything else in this skill degrades gracefully — these do not.

1. After dispatch, contact a running assignee only for a cost-growing finding — a
   public-contract correction, contract overturn, root-cause propagation, or successor
   stacking on a broken invariant — a user override/stop, or a fired liveness trigger;
   never for progress or status, and never on a fixed polling interval.
2. Review and integration bind to an exact commit SHA inspected from a clean detached
   checkout — never a live writer tree, and never a compaction summary's claim of green.
3. Landing on a persistence branch requires current user authority.
4. After a context compaction, re-read the orchestrate SKILL.md and the durable task plan
   before the next dispatch; the summary is hypothesis, not authority.

## Pipeline model

The unit that flows is a **slice**; its lifecycle is **issued → executing → seam-ready →
validated → retired**: seam-ready = dependents may speculatively build on the published
SHA; validated = every named review debt closed; retired = integrated with the final gate
green. "The successor can run" reads seam-ready and never implies "the predecessor can
integrate", which reads validated. The stations are **freeze → implement → integrate**, with independent
review as a **shadow station** beside the line — most slices never enter it (depth
ladder), and it blocks the line only at a critical checkpoint. Review's unit is the **diff**
at a seam-ready SHA, advancing against the validated base — never a re-scan of settled
surface. Two altitudes ride two risk classes: *intra-slice* correctness reviews in the
shadow during the wave; *inter-slice/emergent* risk (contract parity, lifecycle ordering,
cross-module regression) is visible only once integrated, so it sits at the **wave boundary**
by data dependency, not policy, batched into root's next-wave freeze. Freeze and integrate are
root-serial; implement and review fan out. Root is therefore the throughput ceiling:
batch harvests, keep the serial stations short, keep the parallel stations fed.

Read the same loop as a cooperative scheduler — lanes are processes (isolated worktrees),
agents threads, slices the scheduled tasks, root the scheduler, an agent's context its
cache: same-domain work returns to its original writer for cache affinity, and
interrupting a running assignee is a preemption that discards a reasoning cache, so it is
spent only on a fault (liveness trigger) or a contract fault (correction), never on a
poll.

Two axes of parallelism:

- **Lanes (spatial)** — disjoint write scopes, one writer + worktree each.
- **Overlap (temporal)** — within a lane: review of slice N runs beside implementation of
  N+1; finding fixes run beside the remaining review.

A stall is legitimate only as one of three hazards:

- **Structural** — two slices need the same file/interface: first try splitting the seam
  so the scopes become disjoint (prefactor), else serialize — and read it as a poor cut;
  fix the plan, not the machinery. Sole overlap exception: a root-declared append-only
  shared file, where the textual merge is trusted.
- **Data** — a successor needs a predecessor's seam: forward on the **seam-ready SHA**; a
  review verdict is never the wait condition.
- **Control** — a finding overturns the contract: flush only the work stacked on the
  broken invariant.

**Run-ahead is the default, not a concession.** Once a slice is seam-ready, its successor
starts immediately while review proceeds in the shadow; a finding lands as a follow-up
commit on the published SHA. *Holding* a successor is what needs a named reason: a
critical checkpoint, an unstable public seam, or a write-scope conflict. The speculation
test: if a follow-up commit can absorb a wrong bet, run; only where it cannot, barrier.

**Ready critical-path work left undispatched is a root scheduling defect** — an idle slot
alone is not; filling it with low-value speculative work costs more than the idleness.
Keep each lane double-buffered — one slice running, its successor already *drafted*, not
frozen: the draft is a proposal re-confirmed against the running slice's actual result at
harvest before it dispatches, since that result can overturn it. Depth one only: deeper
stock goes stale and rots into ritual.

## Control loop — root's serial duty cycle

| step | action |
|---|---|
| **1. Observe** | Read repo instructions, Git state, worktrees, user dirt, the durable plan, and existing evidence. Name the largest unresolved uncertainty. |
| **2. Freeze** | Freeze only the public seam of the next bounded outcome: objective, contract, acceptance, non-goals, write scope, exact base. Internal design is writer discretion. |
| **3. Shape** | Pick the cheapest shape (below). When freeze+dispatch+harvest overhead would exceed the work, root does it directly. Serialize shared files, contracts, and authority. |
| **4. Dispatch** | Issue only ready, self-contained work with a bounded lease and explicit stop boundary. The assignee must be able to act without chat history. |
| **5. Harvest** | Batch routine harvests rather than reacting per slice; bind conclusions to exact SHAs; give each finding an owner. |
| **6. Integrate** | Merge accepted lanes serially in the integration checkout after any named review risk is resolved; prove absorption before deleting a lane. |
| **7. Re-observe or close** | Integration changes reality: repeat, or close against the final integrated tree with the repo/risk-required final gate. At a wave boundary run the wave-close steering review ([coordination](references/coordination.md)). |

## Shaping heuristics

Not a taxonomy — judgment guides, in the spirit of "simple = 1 agent, complex = many":

- **Root-only** when root can retire the uncertainty faster than writing a dispatch.
- **Single writer** when one coherent surface dominates: one vertical slice, targeted
  gates, writer self-review, root spot-check.
- **Wave** when two or more slices are genuinely independent (disjoint write sets): one
  writer per worktree, root batch-collects; the pipeline model above governs run-ahead
  within each lane.
- **Critical checkpoint** only where a wrong intermediate state cannot be undone by a
  follow-up commit **and** named dependent work is about to stack on it (both, named at
  freeze — a scary-sounding domain alone never qualifies). Carve that core into its own
  small slice, review it before the fan-out, keep the shell normal.

Root's cost scales with **round-trips, not fields per dispatch**: a contract is written
once and cheaply, while every harvest re-enters context that was exported at dispatch. So
the lever is fewer exchanges, not shorter ones — return same-domain work to the writer that
already holds the context (a reuse costs no export at all), batch harvests instead of
reacting per slice, and when freeze plus harvest would cost more than the work, keep it.
A slice cut so thin that coordinating it exceeds doing it is a cut defect, not diligence.

Default review posture is **cumulative**: one review closes a coherent surface; per-slice
review needs a root-named risk. Prefer one writer for a coherent vertical slice; split at
ownership or dependency seams, not per mechanical edit. The scheduler dispatches an eligible
cumulative frontier immediately when its same-surface `wave-reviewer` is idle; while that
reviewer is busy, it accumulates the frontier for the next follow-up instead of spawning a
second identity. This does not make review mandatory per slice: preserve the depth ladder,
and keep `integration-reviewer` as the wave-boundary review of the integrated tree.

## Machinery

Everything optional; create nothing without a live need, and count unused artifacts at
close as defects. What remains:

- **Git guards** — `lane create`, `review checkout|advance|audit`, `compose-base`,
  `revalidate`, `findings record|status` (`--path`/`--sweep` pulls a surface's prior findings
  across waves), `slice status|milestone`, `collect`, `reconcile`,
  `wave status` (read-only rollup + restart handoff, surfacing `validated_unlanded` — the
  reviewed-but-not-yet-collected SHAs to resume without a second review), `cleanup`
  (`--worktree` for one exact
  target; `--wave-boundary` to sweep this task's leftover lanes at a boundary you judge
  safe), and `land status|finish` via
  `<repo-python> <skill-dir>/scripts/orchestrate.py --help`. They derive or validate Git
  facts only: `git_safe_to_remove` is Git/data safety, `safe_to_remove` is its equal
  compatibility alias for this release, and runtime lease safety is unchecked. Consult
  per-command `--help`, never restate arguments.
- **Process feedback** — `feedback record` gives a dispatched subagent an append-only channel
  for reactions to orchestrate itself, separate from findings and gating nothing. Invite it
  at a boundary; read the file on demand — when the human asks or at close — and organize it
  by judgment, never folding it into standing context. Details in
  [coordination](references/coordination.md).
- **Version pin** — `pin set` at task start guards the state-entering commands; `pin
  migrate` adopts a release at a safe boundary and names the documents to re-read; cut
  releases only with the one-shot `release`, never a hand-edited `skill_version`. The
  lifecycle and the worktree-staged release flow live in
  [coordination](references/coordination.md).
- **Task plan** — planning-with-files at `.agent_state/plans/<task-id>/` for cross-session
  or information-heavy work. It carries only intent, decisions, anomalies, and next gates,
  with Git state as SHA pointers; never procedure or finding status.
- **Landing declaration** — a tiny hand-written JSON naming the user's landing policy
  (`validate-only | land-with-confirmation | commit-authorized | publish-authorized`); it
  carries landing authority so the close never stalls at "validated but unlanded".

Read [coordination](references/coordination.md) before the first dispatch, review, or
landing of a task; the matching runtime binding ([runtime-codex.md](runtime-codex.md),
[runtime-claude.md](runtime-claude.md), or [runtime-pi.md](runtime-pi.md)) before the first
agent action;
[publication-review](references/publication-review.md) only when a slice touches authority
publication (schedulers, projections, event streams, receipts, callbacks).

## Definition of done

The requested outcome holds on the final integrated tree; consequential uncertainty has
current evidence; remaining risk is explicit; authorized persistence and cleanup are
complete; the wave-close counters and steering answers are recorded.
