---
name: orchestrate
description: Control loop for repo-wide work that needs multi-agent pipelines, independent risk review, parallel worktrees, or integration across task branches.
skill_version: 88
---

# Orchestrate

Run a control loop that retires the most consequential uncertainty with the largest move
you can still prove safe. Git is the only topology truth carrier; the planning-with-files
task plan is the only durable narrative; everything else is root judgment, not protocol.
Optimize **critical-path lead time**, not agent utilization; a redone slice is cheaper
than machinery that prevents redoing it.

## Iron rules

Installed in the always-resident runtime context (`~/.codex/AGENTS.md`) because they must
survive context compaction; everything else in this skill degrades gracefully — these do not.

1. After dispatch, contact a running assignee only for a public-contract correction, a
   confirmed major finding, a user override/stop, or a fired liveness trigger — never for
   progress or status, and never on a fixed polling interval.
2. Review and integration bind to an exact commit SHA inspected from a clean detached
   checkout — never a live writer tree, and never a compaction summary's claim of green.
3. Landing on a persistence branch requires current user authority.
4. After a context compaction, re-read this SKILL and the durable plan before the next
   dispatch; the summary is hypothesis, not authority.

## Control loop

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
  writer per worktree, writers run ahead on their own unreviewed SHAs, root batch-collects.
  A later finding lands as a follow-up fix, not a rewrite.
- **Critical checkpoint** only where a wrong intermediate state cannot be undone by a
  follow-up commit **and** named dependent work is about to stack on it (both, named at
  freeze — a scary-sounding domain alone never qualifies). Carve that core into its own
  small slice, review it before the fan-out, keep the shell normal.

Default review posture is **cumulative**: one review closes a coherent surface; per-slice
review needs a root-named risk. Prefer one writer for a coherent vertical slice; split at
ownership or dependency seams, not per mechanical edit.

## Machinery

Everything optional; create nothing without a live need, and count unused artifacts at
close as defects. What remains:

- **Worktree/lane commands** — `lane create`, `review checkout`, `collect`, `cleanup`,
  `slice status`, `land status|finish` via
  `<repo-python> <skill-dir>/scripts/orchestrate.py --help`. Idempotent guards over plain
  git: a rerun after an aborted turn reports what already happened (`recovered: …`).
- **Version pin** — `pin set` at task start; state-entering commands fail fast if the
  installed skill moves mid-task; adopt a release at a safe boundary with `pin migrate`,
  which reports the changed documents to re-read. Cut a release with the one-shot
  `release` command (bump + manifest + doctor, rolled back together on failure); never
  edit `skill_version` by hand.
- **Task plan** — planning-with-files at `.agent_state/plans/<task-id>/` for cross-session
  or information-heavy work. It carries state (decisions, open findings, review debt,
  lane positions), never procedure.
- **Landing declaration** — a tiny hand-written JSON naming the user's landing policy
  (`validate-only | land-with-confirmation | commit-authorized | publish-authorized`); it
  carries landing authority so the close never stalls at "validated but unlanded".

Read [coordination](references/coordination.md) before the first dispatch, review, or
landing of a task; the matching runtime binding ([runtime-codex.md](runtime-codex.md) or
[runtime-claude.md](runtime-claude.md)) before the first agent action.

## Definition of done

The requested outcome holds on the final integrated tree; consequential uncertainty has
current evidence; remaining risk is explicit; authorized persistence and cleanup are
complete; the wave-close counters and steering answers are recorded.
