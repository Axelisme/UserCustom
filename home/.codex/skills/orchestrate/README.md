# Maintaining orchestrate

Read this before editing any file in this skill. It is the **design constitution** — the
principles that keep orchestrate a *mental model + tools*, not a rulebook. It is
maintainer-facing and **not loaded at runtime**: it sits at the skill root, so
`document_paths` (in `scripts/_orchestrate/release.py`) never enumerates it, it is absent from the
release manifest, a `pin migrate` never asks anyone to re-read it, and it costs the running
agent zero context. Change it freely; it ships nothing.

## The thesis

orchestrate's durable-execution runtime is **git**. Commits, SHAs, and trailers are the
state of record; everything else — current state, what was reviewed, whether a lane is
absorbed — is a *derived read* of git. The skill therefore holds only what git cannot
decide, in exactly four registers:

- **mental model** — how the root *judges* (`SKILL.md`: the pipeline, the hazards, the four
  judgment calls). Prose, because no tool can decide it.
- **tool** — how work is *executed safely* (`scripts/orchestrate.py`, commands over git).
- **schema** — how state is *persisted* (milestone envelopes, finding ledgers).
- **validator** — how wrong states are *rejected* (a precondition the tool refuses to cross).

Schema and validator live in `scripts/`; the skill text points at them, never restates them.

## Two disciplines — apply both before adding anything

1. **Litmus test.** A rule becomes a real mechanism only if *the absence of the right state
   is itself detectable or blocking* — a missing SHA, a status the tool derives from git, a
   gate that refuses. If the agent could silently skip it and nothing downstream would
   notice, it is discipline wearing a mechanism's costume: leave it as judgment or delete
   it. Never pretend a tool call the agent must *remember* to make is enforcement.
2. **Narrow waist.** Add capability by composing the existing small primitive set, not by
   growing it. Before adding a command, trailer, or rule, ask: can this be expressed with
   what already exists? Widen the waist only when composition genuinely cannot. This is the
   direct defence against "the skill keeps accreting rules."

The success metric for any edit is **fewer rules, not more**. Re-framing existing content
with a leading word, or collapsing duplication, is progress. A net-new rule must clear both
disciplines above; most proposed rules do not, and should be dropped or expressed as one of
the four registers instead.

## The state test (for anything written to a task plan)

Before persisting a fact ask: *is this a fact I recorded, or a conclusion I am re-deriving
from facts I recorded?* Only recorded facts (SHAs, verdicts, decisions) deserve storage;
re-derivable conclusions must never be persisted independently — that is exactly how a plan
grows zombie state. The current-state cache holds pointers to SHAs, never copies of them.

## The irreducible judgment (stays prose forever)

Four calls no tool can make; they are the only rules that survive *as rules*:

- when it is worth splitting off another agent;
- when a stall is a structural / data / control hazard;
- when a seam is ready enough to run ahead;
- when a risk warrants independent review.

Everything else that reads like a rule is a candidate to become a tool, a schema, a
validator, or a deletion.

## Leading words (the shared vocabulary)

Each anchors a region of behavior in the model's priors; reuse the exact word across
prompts, commits, and docs so it stays load-bearing. This roster is the source of the
vocabulary; `SKILL.md` and the references *use* it.

- **own the control flow** — the root owns the loop, its stops, dispatch, integration.
- **git is the durable log / derived read** — state is read from git, never hand-copied.
- **single-threaded writes, parallel readers** — one writer per artifact; review and
  successors read in parallel.
- **the SHA is the checkpoint** — the seam-ready SHA is what a successor builds on and what
  a review binds to.
- **authority transaction** — `provisional claim → reserved authority → externally
  published → recoverably retained → retired`; each transition names owner, lock, witness,
  rollback, capacity.
- **saga / compensation** — predeclare idempotent reverse actions for speculative or outward
  transitions; unwind completed steps in reverse.
- **heartbeat + timeout taxonomy** — a milestone is the heartbeat; distinguish
  never-started, died-mid-work, and in-budget before acting.
- **narrow waist** — compose over the primitive set; do not grow it.

## What must not change

The **Iron rules** and the **Pipeline model** in `SKILL.md` are the survival core (the iron
rules are mirrored into the always-resident runtime context so they survive compaction).
Change them only with the user's explicit intent, never as a side effect of another edit.

## Shipping a change

Every skill/profile edit goes through a git worktree, then the one-shot `release`, then a
`--ff-only` merge — the worktree is the staging area, the merge the atomic switch, so the
live overlay never shows a half-written release. Never hand-edit `skill_version`; the
release command bumps it, writes the manifest, and runs the doctor as one transaction that
rolls back together. Full lifecycle: [coordination](references/coordination.md) →
*Skill upgrades*.
