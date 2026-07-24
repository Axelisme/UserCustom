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

A Wave collects into the task integration branch after its machine gates (contract suite,
focused tests, lint/format/type) are green; the next Wave bases on the integration tip.
Root decides dependency depth and placement. Pi maps the roles to generic pipelines: Oracle
starts at C0 and Implementation starts lazily at its first real task. Codex maps them to two
persistent native role agents using native messaging and continuation. Neither binding
creates a simulated queue; task plan plus Git recover position after restart.

## CLI surface

The JSON-only workflow commands are `worktree create|status|remove`, `contract merge`,
`integration create|status|collect|remove`, and `profile report`. Retained administration is
`doctor`, `diff`, `pin status|set|migrate`, and `release`. Creation refuses an existing path
or branch. Removal requires a clean worktree and leaves its branch. Contract merge leaves
ordinary conflicts visible. Integration collect merges one exact implementation SHA into the
task integration branch with `Role: collect` trailers; conflicts stay visible; the collected
list is a read-only Git projection. Profile statistics use Git committer timestamps and
numstat only; non-monotonic timestamps are warnings.

## Acceptance and migration

Simplify, canonical full suite, and the one clean-detached two-axis review run at an
integration milestone — by default once per task, before landing, over the whole
base..integration-tip diff. Root may insert an earlier milestone after a high-risk Wave (new
seam, cross-authority change); never per-Wave formal review by default. A behavior
correction returns through Oracle and Implementation in the same Wave; a quality correction
stays with Implementation. Landing publishes the integration tip to the persistence branch
under current user authority, once per task. For an older pin, `pin migrate` preserves the
existing JSON shape and reports manual v118-to-v119 requirements: stop old dispatch,
preserve read-only evidence, select an exact base, create a new Wave, and continue as v119
without automatic conversion.

## Runtime bindings

Read the matching runtime binding before dispatch: [Codex](runtime-codex.md),
[Claude](runtime-claude.md), or [Pi](runtime-pi.md). Generic pipeline lifecycle authority
is linked by the Pi binding rather than copied here. Release manifests cover shipped runtime
packages and profile contracts; every retained Markdown document fits the single-read
budget.
