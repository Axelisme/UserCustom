---
name: orchestrate
description: Minimal Git-backed lane and task-integration workflow for a Git task.
skill_version: 131
---

# Orchestrate

Orchestrate is the **Git task lane**. It owns lane worktrees, task integration, the ready-candidate
projection, the unified report, and links to runtime adapters. Git commits, refs, SHAs, trailers,
and worktree state are its durable inputs. Acceptance and close-out authority remain in the
admission standard.

## Lane

A lane is one worktree, one branch, and one subagent call: it authors a Contract test (a commit
declaring `Immutable: <path>`) and then implements against it, in the same worktree and the same
turn. Multiple oracle → implement rounds inside one lane are normal; a declared Contract path stays
open to change only in the same commit that redeclares it. `lane create` derives the worktree path
and branch from `--task-id`/`--lane-id`. `integration collect` accepts only the lane's exact clean
tip, proves every declared `Immutable:` path still resolves to the object that first declared it,
merges the lane into the task's integration branch, and **always** removes the lane worktree — there
is no option to keep it. A lane that quietly changed a declared path without redeclaring it is
refused and named.

## Integration and the ready candidate

`integration create` builds the task integration worktree and, in the same call, a second detached
acceptance worktree pinned to the same base. Lane collects merge forward into integration
(`--no-ff`, never rebased or reset); the branch is append-only. A lane behind the integration tip
integrates it into itself first, in its own worktree — the same model Git uses for pull-then-push —
so a conflict is resolved in the lane, never in the shared integration worktree. Once a batch of
lanes has passed the shared gate order — simplify, canonical tests, ReviewGate; see the admission
standard's S4 — `integration candidate` checks the acceptance worktree out to that exact gated SHA
and moves `refs/orchestrate/<task>/candidate` to match. A dirty acceptance worktree refuses the
checkout and leaves the previous candidate untouched. `integration status` and `report` project
everything else about the candidate from Git — worktree readiness, lag behind tip, timeline — with
no second persisted format. `integration remove` tears down both worktrees, the candidate ref, and
every ref and branch under the task's namespace together — refusing (unless `--abandon`) when the
integration branch was never landed or a lane branch was never collected.

## Commands

Seven top-level commands: `lane create|status|drop`, `integration
create|status|collect|candidate|remove|land|list`, `report`, and the retained administration
`doctor`, `diff`, `pin status|set|migrate`, `release`. `report` is read-only: per-lane span and
output, task parallelism, the four zero-parameter Git checks (deletion, loop, mass, focus — see
`admission.py`), and the candidate projection, all in one call; nothing here is ever refused, only
presented. `integration list` is the shallow, read-only view across every task in the repository.
Trailers are `Task:`, `Lane:`, `Immutable:`, `Origin:`, `Landed:`.

Every command prints one JSON object and exits with one of three codes: **0** on success, **1**
when the command completed and decided no (for example `doctor` ran cleanly and found a hash
mismatch), and **2** when the command itself could not run (bad arguments, an unreadable Git state,
a missing worktree). A success payload is always on `stdout`; an error payload is always on
`stderr`, so the two never mix in the same stream.

## Never push

Orchestrate never pushes and never reads a remote ref. Every command is local-only by construction:
nothing in this skill's surface accepts a remote or performs a network operation. Landing is a
single squash commit against a local persistence branch, recording the exact landed SHA (see the
admission standard's S5).

## Boundaries

Read the matching [Codex runtime](runtime-codex.md), [Claude runtime](runtime-claude.md), or
[Pi runtime](runtime-pi.md) before dispatch. Runtime links describe lifecycle only; this document
does not emulate a runtime. The admission projection points to the shared admission standard, the
sole S1–S5 authority. For an older pin, use the executable `pin migrate`; it refuses to advance a
repo that still carries `wave/` branches, `refs/orchestrate/*` refs, or leftover managed worktree
directories from an earlier workflow model, and lists exactly what remains instead of guessing.
