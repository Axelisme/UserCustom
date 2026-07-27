---
name: orchestrate
description: Minimal Git-backed Oracle and Implementation workflow for a Git task lane.
skill_version: 128
---

# Orchestrate

Orchestrate is the **Git task lane**. It owns role worktrees, Contract merge, integration branch
mechanics, exact-SHA handoff, profile/admission projections, and links to runtime adapters. Git
commits, refs, SHAs, trailers, worktree state, and declared immutable paths are its durable
inputs. Acceptance and close-out authority remain in the admission standard.

## Git task lane

Root creates one integration worktree and branch from an explicit base. Each Wave has one Oracle
and one Implementation worktree from the same base. Oracle owns the public Interface, Contract
tests, fixtures, and test adapters; Implementation fills mutable production behavior. Contract
merge records every declared immutable path. Integration collect accepts only the exact clean
Implementation SHA whose declared paths still resolve to the same Git objects.

A terminal `slice-ready` handoff carries `Slice: <slice-id>` and the full exact `SHA`. Root
consumes only a clean SHA, verifies trailers and profile output, and records the projection. A
collected Wave is closed; its role worktrees may be removed while Git evidence remains available
for the task lane.

## Commands

The JSON workflow surface is `worktree create|status|remove`, `contract merge`,
`integration create|status|collect|remove`, `profile report`, and `admission`. Retained
administration is `doctor`, `diff`, `pin status|set|migrate`, and `release`. Creation refuses an
existing path or branch. Integration collection proves immutable-path object identity before
merging and reports conflicts without hiding them. Status is read-only and projects the selected
worktree's path, branch, HEAD, tree, and clean state.

## Boundaries

Read the matching [Codex runtime](runtime-codex.md), [Claude runtime](runtime-claude.md), or
[Pi runtime](runtime-pi.md) before dispatch. Runtime links describe lifecycle only; this document
does not emulate a runtime. The admission projection points to the shared admission standard, the sole S1–S7 authority.
For an older pin, use the executable `pin migrate`; its existing compatibility behavior remains
in the implementation and is not restated here.
