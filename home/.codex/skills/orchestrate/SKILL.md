---
name: orchestrate
description: Minimal Git-backed lane and task-integration workflow for a Git task.
skill_version: 135
---

# Orchestrate

Orchestrate is the **Git task lane**. It owns lane worktrees, task integration, the ready-candidate
projection, the unified report, and links to runtime adapters. Git commits, refs, SHAs, trailers,
and worktree state are its durable inputs. Acceptance and close-out authority remain in the
admission standard.

## Lane

A lane is one worktree, one branch, and one `lane-worker` call. The worker authors Contract
tests and then implements against the frozen Contract in the same lane worktree. A Contract path
stays open to change only in an independent amendment commit that redeclares it. `lane create`
derives the canonical worktree path and branch from `--task-id`/`--lane-id`; Root dispatches that
exact path and expected Git identity. The worker first changes into and attests the path, then
keeps every operation path-bound. Before collect, Root reviews the test-first commits at their
reported SHAs and rechecks lane identity plus primary-checkout dirt. `integration collect` accepts
only the lane's exact clean tip, validates the entire first-parent range has a normalized
`Immutable:` declaration and every later change redeclares its protected path, merges the lane into
the task's integration branch, and **always** removes the lane worktree — there is no option to keep
it. Read-only `commit-check` runs that same validator earlier against the exact lane tip/base,
without a hook or expected-path list. Afterward Root verifies the collected SHA and
that primary dirt is unchanged. A lane that
quietly changed a declared path without redeclaring it is refused and named.

## Integration and the ready candidate

`integration create` builds the task integration worktree and, in the same call, a second detached
acceptance worktree pinned to the same base. Lane collects merge forward into integration
(`--no-ff`, never rebased or reset); the branch is append-only. A lane behind the integration tip
integrates it into itself first, in its own worktree — the same model Git uses for pull-then-push —
so a conflict is resolved in the lane, never in the shared integration worktree. Once a batch of
lanes has passed the shared gate order — simplify, canonical tests, ReviewGate; see the admission
standard's S4 — `integration candidate` first proves the supplied SHA is a task collect on the
integration first-parent whose tree equals its actual parent-2 lane tree, then checks the acceptance
worktree out to that exact gated SHA and moves `refs/orchestrate/<task>/candidate` to match. A dirty acceptance worktree refuses the
checkout and leaves the previous candidate untouched. `integration status` and `report` project
everything else about the candidate from Git — worktree readiness, lag behind tip, timeline — with
no second persisted format. `integration remove` tears down both worktrees, the candidate ref, and
every ref and branch under the task's namespace together — refusing (unless `--abandon`) when the
integration branch was never landed or a lane branch was never collected.

## Commands

Eight top-level commands: `lane create|status|drop`, read-only `commit-check`, `integration
create|status|collect|candidate|remove|land|list`, `report`, and the retained administration
`doctor`, `diff`, `pin status|set`, `release`. `report` is read-only: per-lane span and
output, task parallelism, the four zero-parameter Git checks (deletion, loop, mass, focus — see
`admission.py`), and the candidate projection, all in one call; nothing here is ever refused, only
presented. `integration list` is the shallow, read-only view across every task in the repository.
Agents manage `Immutable:` trailers; Orchestrate generates `Task:`, `Lane:`, and `Landed:`.
Machine rework counts and routing remain Root-owned narrative, not Git trailer state.

Every command prints one JSON object containing `orchestrate_version`, the installed executable
version, and exits with one of three codes: **0** on success, **1** when the command completed and
decided no (for example `doctor` ran cleanly and found a hash mismatch), and **2** when the command
itself could not run (bad arguments, an unreadable Git state, a missing worktree). Only unreadable
installed version metadata produces a null version. A success payload is always on `stdout`; an
error payload is always on `stderr`, so the two never mix in the same stream.

Before any lane, integration, candidate, landing, removal, or pin mutation, one central CLI
preflight verifies the installed release manifest, documents, profile contracts, and mandatory
runtime assets. Pin drift or a missing pin never blocks task work; corrupt release provenance does.
Read-only commands remain available for diagnosis.

## Never push

Orchestrate never pushes and never reads a remote ref. Every command is local-only by construction:
nothing in this skill's surface accepts a remote or performs a network operation. Landing is a
single squash commit against a local persistence branch, recording the exact landed SHA (see the
admission standard's S5).

## Boundaries

Read the matching [Codex runtime](runtime-codex.md), [Claude runtime](runtime-claude.md), or
[Pi runtime](runtime-pi.md) before dispatch. Runtime links describe lifecycle only; this document
does not emulate a runtime. The admission projection points to the shared admission standard, the
sole S1–S5 authority. At the lane-ready to collect seam, Root applies the S2 test-review procedure
there before reading implementation changes. The pin records the last manually adopted release and never selects the executable. Apply the
manifest-hashed `migrations/<version>.md` guides in order from pin plus one through the installed
version, then use the sole writer, atomic idempotent `pin set`, to create or overwrite the pin.
Active branches, refs, and worktrees do not block that explicit manual adoption, and Orchestrate
never converts or cleans active task state as part of version handling.
