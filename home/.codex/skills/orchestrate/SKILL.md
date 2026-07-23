---
name: orchestrate
description: Minimal Git-backed Oracle and Implementation workflow for v119.
skill_version: 119
---

# Orchestrate v119

Orchestrate provides one small workflow surface: two role worktrees, exact Contract merge,
and a read-only Git profile. Git commits, refs, SHAs, trailers, and worktree state are the
only durable workflow truth. Runtime lifecycle is owned by the runtime binding; acceptance
uses the dev-flow contract.

## Iron rules

Installed in the matching always-resident runtime context (`~/.codex/AGENTS.md` or
`~/.pi/agent/APPEND_SYSTEM.md`) because they must survive context compaction.

1. Root contacts a running role only for a cost-growing Contract correction, user stop, or liveness failure; never for routine status.
2. Any handoff binds to an exact clean commit SHA inspected from Git, never to a summary.
3. Mutation of a persistence branch requires current user authority.
4. After compaction, re-read this skill and the durable task plan before dispatch.

## Pipeline model

The workflow is two role streams joined by one exact Contract merge; runtime lifecycle remains
with the native binding.

## Workflow

A Wave has one `wave-oracle` and one `wave-implementer`, each with a deterministic Git
worktree and branch from the same explicit base. Oracle owns the public Interface, skeleton,
contract tests, fixtures, and test adapters. The tests are immutable to Implementation.
Implementation may overlap Oracle production paths and fills hidden behavior after Root merges
the exact Contract SHA with no fast-forward. `slice-ready` is the one terminal handoff and
carries Slice plus exact SHA; the role ends its turn immediately afterward.

Root decides dependency depth and placement. Pi maps the roles to generic pipelines: Oracle
starts at C0 and Implementation starts lazily at its first real task. Codex maps them to two
persistent native role agents using native messaging and continuation. Neither binding
creates a simulated queue; task plan plus Git recover position after restart.

## CLI surface

The JSON-only workflow commands are `worktree create|status|remove`, `contract merge`, and
`profile report`. Retained administration is `doctor`, `diff`, `pin status|set|migrate`, and
`release`. Creation refuses an existing path or branch. Removal requires a clean worktree
and leaves its branch. Contract merge leaves ordinary conflicts visible. Profile statistics
use Git committer timestamps and numstat only; non-monotonic timestamps are warnings.

## Acceptance and migration

Dev-flow acceptance is simplify, canonical tests, then one clean-detached exact-SHA
code-review. A behavior correction returns through Oracle and Implementation in the same
Wave; a quality correction stays with Implementation. Landing is repo policy and current
user authority, outside this CLI. For an older pin, `pin migrate` preserves the existing
JSON shape and reports manual v118-to-v119 requirements: stop old dispatch, preserve
read-only evidence, select an exact base, create a new Wave, and continue as v119 without
automatic conversion.

## Runtime bindings

Read the matching runtime binding before dispatch: [Codex](runtime-codex.md),
[Claude](runtime-claude.md), or [Pi](runtime-pi.md). Generic pipeline lifecycle authority
is linked by the Pi binding rather than copied here. Release manifests cover shipped runtime
packages and profile contracts; every retained Markdown document fits the single-read
budget.
