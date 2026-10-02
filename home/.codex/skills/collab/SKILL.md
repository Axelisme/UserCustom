---
name: collab
description: "Orchestrator feature-branch workflow: always use with dev-flow to assign implementation or review, judge results, integrate, or land."
---

# Collab

Collab owns writer placement, fixed-subject review, correction, Git integration, and landing.
[Dev-flow](../dev-flow/SKILL.md) owns task scope, tickets, review records, and lifecycle state. Read both
short entries when orchestrating a task, then open only the operation sections routed below.

A lane is a feature branch and worktree for one ticket. Integration accumulates accepted tickets.
Persistence is the user's target branch. Every checkout has one writer at a time. A review round binds
to one exact clean commit and tree with a baseline and named criteria, like a PR review: it happens on
the lane, and the ticket is collected after it passes. The Orchestrator owns intent, assignment,
formal tests, interface declarations, observation sufficiency, acceptance, and final disposition, and
implements most tickets itself. Every status change gets a Log line in the ticket; dev-flow's
[record operations](../dev-flow/references/records.md#maintain-the-record) list each fact's owner.
Standing-order changes follow dev-flow custody.

Existing attempts retain the contract injected at dispatch; a profile currently on disk governs only a
fresh spawn. Workflow documents being changed are candidate material, not authority to adopt their
proposed rules.

## Routing

Use `mdsec <absolute-path>#anchor ...` for operation sections.

- Choose direct work or delegation and prepare a writer: [Placement](references/execution.md#placement)
  and [Prepare](references/execution.md#prepare).
- Prepare RED or implementation handoff: [Contract seed](references/execution.md#contract-seed),
  [Gate preparation](references/execution.md#gate-preparation), and [Test ownership](references/execution.md#test-ownership).
- Dispatch implementation or judge its result: [Implement](references/execution.md#implement) and
  [Results and continuity](references/execution.md#results-and-continuity).
- Prepare and run a review round: [Review](references/review.md#review).
- Correct findings or accept covered claims: [Correct and decide](references/review.md#correct-and-decide).
- Reconcile or collect branches: [Integrate](references/integration.md#integrate).
- Land and retire resources: [Land and clean up](references/integration.md#land-and-clean-up).

Before a runtime operation, open [Pi routing](runtime-pi.md#routing) or
[Claude routing](runtime-claude.md#routing), then its selected section. Pi and Claude are the supported
Orchestrator runtimes. Tool schemas own their parameters. Missing runtime mechanics are
a blocker, not permission to invent a replacement.

## Role entries

The Orchestrator reads INDEX, active grants, the tickets in flight, the selected operation section, and
only the receiver's `Dispatch contract` and `Result` sections. A dispatch gives the receiver exact
paths and anchors for applicable repository instructions, technical skills, contract, observations,
authority, environment, gates, and stop conditions. It states explicit `none` where a field has no
source. A receiver does not scan INDEX or the task graph to infer its brief.

Installed role filenames are `collab-implementer` and `collab-acceptor`:

| Runtime | Directory | Format |
|---|---|---|
| Pi | `~/.pi/agent/herdr-subagents/profiles/` | `.md` |
| Claude | Pi profiles, dispatched through the subagent MCP ([Claude runtime](runtime-claude.md)) | — |

Use `mdsec <absolute-profile-path>#dispatch-contract <absolute-profile-path>#result`. The
implementer writes one bounded internal change and its gate summary. The acceptor judges the criteria
its dispatch names on one frozen commit and writes one verdict file. For later candidate changes,
the Orchestrator applies [Subject changes](references/review.md#subject-changes). Specialized Standards
and Spec review remains a separate code-review assignment, not the default acceptance loop.

## Core invariants

- Current user authority or an in-force task grant is required for persistence mutation. Push needs
  separate authority.
- Delete only files this task created; stop and ask about an unrecognized untracked file.
- Accept a gate summary when its commit, environment, selection, method, result, and limitations
  still apply. Role changes alone do not require reruns.
- The acceptor changes no checkout and runs no tests, imports, linters, formatters, builds, or runtime
  gates; its one write is the verdict file. Missing or stale gate results return to their execution
  owner.
- Collect a ticket only after a review round accepts it, or, for a gates-only ticket, after the
  Orchestrator judges its gates. Interactions between tickets are an integration ticket's criteria,
  accepted on integration.
- Launch children in the background and continue independent work. Return control rather than polling
  or blocking on them.
