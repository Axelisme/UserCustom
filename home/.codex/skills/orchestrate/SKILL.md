---
name: orchestrate
description: Minimal Git-backed Oracle and Implementation workflow for v126.
skill_version: 126
---

# Orchestrate v126

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
5. Report reachable behavior to the user at every landing. Silence between landings is only safe because landings are frequent; an effort that has not landed is an effort the user cannot see.
6. A candidate reaches the user only after simplify, the canonical tests, and code-review; Night Mode may defer S5 but never landing, every provisional Slice keeps an exact acceptance item, and max speculative dependency depth is 10.

## Workflow

A Wave has one `wave-oracle` and one `wave-implementer`, each with a deterministic Git
worktree and branch from the same explicit base. Oracle owns the public Interface, skeleton,
contract tests, fixtures, and test adapters. The tests are immutable to Implementation.
Implementation may overlap Oracle production paths and fills hidden behavior after Root merges
the exact Contract SHA with no fast-forward. Because that overlap is legitimate, the Contract
commit names its own acceptance surface in repeatable `Immutable: <path>` trailers.
`slice-ready` is the one terminal handoff and carries Slice plus exact SHA; the role ends its
turn immediately afterward.

Root creates the task integration worktree once from the persistence-branch tip the task
starts at, and the first Wave uses that same base. A Wave collects into the task integration
branch after its machine gates (contract suite, focused tests, lint/format/type) are green;
the next Wave bases on the integration tip.
Root decides dependency depth and placement. Runtime bindings own lifecycle. Pi maps the
roles to generic pipelines: Oracle starts at C0 and Implementation starts lazily at its first
real task. Codex maps them to two persistent native role agents using native messaging and
continuation. Neither binding creates a simulated queue; task plan plus Git recover position
after restart.

## CLI surface

The JSON-only workflow commands are `worktree create|status|remove`, `contract merge`,
`integration create|status|collect|remove`, `profile report`, and `admission`. Retained
administration is `doctor`, `diff`, `pin status|set|migrate`, and `release`. Creation refuses an existing path
or branch. Removal requires a clean worktree and leaves its branch. Contract merge leaves
ordinary conflicts visible. Integration collect merges one exact implementation SHA into the
task integration branch with `Role: collect` trailers, after proving every declared immutable
path resolves to the same Git object id as at the Contract merge — an edited, deleted, or
relocated acceptance surface is refused before it enters. Conflicts stay visible; the collected
list is a read-only projection bounded by the base ref `refs/orchestrate/<task>/integration/base`
that `create` records, and a missing base ref fails closed. Profile statistics use Git
committer timestamps and numstat only; non-monotonic timestamps are warnings. An
Implementation endpoint belongs to the attempt whose Contract merge precedes it, empty
handoffs included; an endpoint recorded before every merge of its Slice is reported as
unattributed rather than silently dropped.

## Acceptance and migration

Acceptance scheduling, deferred S5 records, speculative depth, and machine-rework accounting
are owned by the shared dev-flow S3–S6 contract. Orchestrate contributes exact candidates,
integration tips, and the read-only `admission` projection; it has no Day/Night or acceptance
ledger authority. A collected Wave is closed. When dev-flow routes a machine finding, behavior
work starts a new Wave through Oracle and Implementation from the integration tip, while quality
work starts a new Wave with Implementation. Landing remains outside orchestrate and publishes
only a user-accepted exact checkpoint under current authority, once per Slice. For an older pin, `pin migrate` preserves the
existing JSON shape and reports the manual requirements for every boundary it crosses: from
v118, stop old dispatch, preserve read-only evidence, select an exact base and continue as a
new Wave; from v119, adopt the integration CLI, per-Wave machine gates, milestone acceptance,
declared runtime pipelines, and the blocked reason enum; from v120, declare `Immutable:` paths
on every Contract; from v121, simplify reads only the increment since the last reviewed SHA;
from v122, a timing, locking, retention, or replay mechanism needs a test that is red without
it before it may enter; from v123, adopt the dev-flow admission standard — landing per Slice,
S2 observability before an invariant enters a Contract, and the S4 cap on machine rework; from
v124, adopt Day/Night scheduling, the phase-record deferred acceptance queue, and speculative
depth 10 without weakening S5; from v125, run the same machine gates in both modes and present
only a reviewed exact SHA for user testing. Nothing converts automatically.

## Runtime bindings

Read the matching runtime binding before dispatch: [Codex](runtime-codex.md),
[Claude](runtime-claude.md), or [Pi](runtime-pi.md). Generic pipeline lifecycle authority
is linked by the Pi binding rather than copied here. Release manifests cover shipped runtime
packages and profile contracts; every retained Markdown document fits the single-read
budget.
