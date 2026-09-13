---
name: collab
description: "Orchestrator feature-branch workflow: always use with dev-flow to assign implementation or review, judge results, integrate, or land."
---

# Collab

Collab owns writer placement, fixed-subject review, correction, Git integration, and landing.
[Dev-flow](../dev-flow/SKILL.md) owns task scope, tickets, review records, and lifecycle state. Read both
short entries when orchestrating a task, then open only the operation sections routed below.

A lane is a feature branch and worktree. Integration accumulates task-local results. Persistence is
the user's target branch. Every checkout has one writer at a time. A fixed subject is one exact clean
commit and tree with a baseline and bounded criteria. Every review binds to one fixed subject. The
Orchestrator owns intent, assignment, formal tests, interface declarations, observation sufficiency,
acceptance, and final disposition. Durable workflow conclusions go to the owning ticket or review
record as a semantic checkpoint or bounded review history. INDEX changes only at a routing edge.
Dev-flow defines both terms in
[record operations](../dev-flow/references/records.md#maintain-the-record).

On reorientation, reread the selected operation section and receiver contract when their original text
is absent, changed, or uncertain. Existing attempts retain the contract injected at dispatch; a profile
currently on disk governs only a fresh spawn. Workflow documents being changed are candidate material,
not authority to adopt their proposed rules.

## Routing

Use dev-flow's `scripts/section.py <absolute-path>#anchor` for operation sections.

- Choose direct work or delegation and prepare a writer: [Placement](references/execution.md#placement)
  and [Prepare](references/execution.md#prepare).
- Seed interfaces or formal tests: [Contract seed](references/execution.md#contract-seed) and
  [Test ownership](references/execution.md#test-ownership).
- Dispatch implementation or judge its result: [Implement](references/execution.md#implement) and
  [Results and continuity](references/execution.md#results-and-continuity).
- Prepare and run ticket or batch acceptance: [Review](references/review.md#review).
- Count a verdict, correct, accept, or cutoff: [Correct and decide](references/review.md#correct-and-decide).
- Reconcile or collect branches: [Integrate](references/integration.md#integrate).
- Land and retire resources: [Land and clean up](references/integration.md#land-and-clean-up).

Before a runtime operation, open [Pi routing](runtime-pi.md#routing) or
[Claude routing](runtime-claude.md#routing), then its selected section. Codex uses installed profiles
and native Git/dispatch capabilities. Tool schemas own their parameters. Missing runtime mechanics are
a blocker, not permission to invent a replacement.

## Role entries

The Orchestrator reads INDEX, active grants, the current record, the selected operation section, and
only the receiver's `Dispatch contract` and `Result` sections. A dispatch gives the receiver exact
paths and anchors for applicable repository instructions, technical skills, contract, observations,
authority, environment, gates, and stop conditions. It states explicit `none` where a field has no
source. A receiver does not scan INDEX or the task graph to infer its brief.

Installed role filenames are `collab-implementer` and `collab-acceptor`:

| Runtime | Directory | Format |
|---|---|---|
| Pi | `~/.pi/agent/herdr-subagents/profiles/` | `.md` |
| Claude | `~/.claude/agents/` | `.md` |
| Codex | `~/.codex/agents/` | `.toml` |

Use dev-flow's `scripts/section.py <absolute-profile-path>#dispatch-contract` and `#result`. The
implementer writes one bounded internal change. The acceptor reads one immutable subject and one
bounded criterion set, whether owned by a ticket or batch review record. Specialized Standards and
Spec review remains a separate code-review assignment, not the default ticket loop.

## Core invariants

- Current user authority or an in-force task grant is required for persistence mutation. Push needs
  separate authority.
- Preserve user dirt and evidence. Never stash, reset, overwrite, or delete them to prepare work.
- Accept complete, traceable gate observations when candidate, environment, selection, method, result,
  and limitations still apply. Role changes alone do not require reruns.
- The acceptor stays read-only and does not run tests, imports, linters, formatters, builds, or runtime
  gates. Missing or stale observations return to their execution owner.
- New ticket and batch reviews default to one effective BLOCKED verdict on a reviewable candidate.
  Questions and assignment defects consume no allowance. Recorded historical or user-granted limits
  remain authoritative.
- Launch children in the background and continue independent work. Return control rather than polling
  or blocking on them.
