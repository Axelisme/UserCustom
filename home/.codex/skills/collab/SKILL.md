---
name: collab
description: "Orchestrator Feature Branch Workflow: always use with dev-flow to assign implementation or review, judge results, integrate, or land."
---

# Collab

Always read this Orchestrator entry with [dev-flow](../dev-flow/SKILL.md), which owns the task record
and tickets. Use **Feature Branch Workflow** for implementation, validation, review, and authorized
merge. Use **Agile, incremental delivery** to align concrete scenarios, deliver small usable increments,
and learn from integration. Bound review to the agreed contract; record remaining uncertainty through
[cutoff](../dev-flow/SKILL.md#cutoff). A hosted pull request is optional.

The Orchestrator holds intent, scope, assignments, and final judgement. Tool vocabulary: a **lane** is
a feature branch and its worktree; **integration** accumulates task-local results; **persistence** is
the user's target branch.

## Plan and assign

Use dev-flow's [parallel batches](../dev-flow/SKILL.md#parallel-batches) and
[scenario-based alignment](../dev-flow/SKILL.md#design-alignment). The user confirms each ticket's
design; its contract supplies scope, assumptions, criteria, checks, and decision boundaries.

Materialize shared interface prerequisites first. Dispatch each ticket as soon as its
[seed](#contract-seed), formal tests, and worktree are ready. Overlap preparation with implementation,
review, corrections, and collection. Each child receives one small, explicit assignment.

The Orchestrator presents key data structures during alignment and decides algorithms and supporting
structures affecting correctness, performance requirements, or maintenance cost. Record decisions and
short implementation steps in Contract starting point. Implementers choose variables, loop forms, and
private helper organization within that plan. Further design tradeoffs return to the Orchestrator.
Resolve ambiguity, split further, or implement directly when that is cheaper than describing the work.
Repeated failed corrections are a reason to take over or re-align.

Map mechanically decidable criteria to commands whose exit status establishes them. Assign independent
review where judgement is needed, and name user or external observation owners separately. For wholly
mechanical criteria, a second reader is optional. Schedule observations requiring a commit after that
commit exists. The Orchestrator evaluates the results in every case.

Read the receiver's `Dispatch contract` and `Result` sections before dispatch. Supply its absolute
ticket path and execution fields: checkout, environment, mutation authority, evidence targets, and
stop conditions. Review and correction also need candidate/baseline and prior findings as applicable.
Reference ticket-owned criteria and checks. Direct Orchestrator implementation follows the same
contract, test ownership, and checkout constraints.

## Role entries

- Orchestrator: both skills, INDEX, and the ticket for the current action. Select runtime sections by
  operation and receiver input/output contracts by assignment.
- Implementer: profile, dispatch, ticket, and relevant code/interface declarations. Evidence authoring
  rules apply when assigned a durable evidence target.
- Reviewer: profile, dispatch, ticket, fixed candidate, and relevant evidence; prior findings for
  rereview. Its profile owns evidence assessment.

Installed profiles use filenames `collab-implementer` and `collab-acceptor`:

| Runtime | Directory | Format |
|---|---|---|
| Pi | `~/.pi/agent/herdr-subagents/profiles/` | `.md` |
| Claude | `~/.claude/agents/` | `.md` |
| Codex | `~/.codex/agents/` | `.toml` |

Read sections with dev-flow's `scripts/section.py <absolute-profile-path>#dispatch-contract` and
`#result`. Load technical skills for the concrete assigned work.

## Prepare the branch

Use one writer per checkout, including the Orchestrator. Concurrent writers get separate worktrees
and independent dependency/module scopes. Preserve pre-existing dirt and evidence; never stash,
reset, overwrite, or delete them to prepare the branch.

Before runtime operations, open [Pi routing](runtime-pi.md#routing) or
[Claude routing](runtime-claude.md#routing) with dev-flow's `scripts/section.py`, then its operation
section. Codex uses installed profiles and current native Git/dispatch capabilities. Specialized
operations require a documented binding; recover missing mechanics before proceeding. Tool schemas
own parameters and capabilities.

Run repository-declared worktree bootstrap before dispatch. Roles consume the exact provisioned
environment; a failed bootstrap returns a concrete blocker. Retain it through implementation, review,
and correction until worktree retirement. Preparation ends with a bounded assignment, one writer,
a safe checkout, and a working environment.

## Contract seed

For a new or changed public interface, the Orchestrator writes the confirmed design on the feature
branch: interface and declaration, result/error types, a real shipped-path caller, and contract tests
for the agreed scenarios. Hold checkout write ownership, commit the seed, then transfer ownership to
the implementer. Work preserving an existing complete contract uses that starting point.

Tests reach the intended interface through the shipped path and assert observable results. A seed
may leave expected failures for assigned implementation work. Preparation is complete when the ticket
names the seed commit, exact interface/caller/test locations, expected failures, and a small remaining
implementation sequence.

The Orchestrator owns interface and declaration changes throughout corrections. Take back write
ownership for those edits, then resume the implementer from the updated starting point. Design changes
follow user confirmation at [batch handoff](../dev-flow/SKILL.md#ticket-handoff).

Assign independent review of interface conformance, shipped-path reachability, and contract-test
assertions, including Orchestrator-authored tests. Keep the seed on its feature branch until the
completed increment qualifies for normal acceptance or the bounded [cutoff route](#correct-and-decide).

## Test ownership

The Orchestrator authors and updates all formal behavior and regression tests. Test confirmed normal,
error, and boundary scenarios through public interfaces; helpers receive coverage through their
contribution to that behavior. A helper promoted to a public interface gains a contract in alignment.

Implementers run formal tests and use run-owned temporary probes to inspect helpers and diagnose their
assignment. Remove probes before final commit and handoff. Report useful scenarios to the Orchestrator
for formal tests. The final candidate contains implementation and Orchestrator-owned formal tests.

A coverage blocker identifies a reachable behavior defect or an agreed validation obligation and its
evidence gap. Route formal-test corrections to the Orchestrator and internal-logic corrections to the
implementer. Apply mutating checks within the acting writer's edit authority.

## Implement and review

The writer completes the assignment, passes required checks, commits under branch-local authority,
and stops writing. Gate evidence establishes the required property of the final candidate.

Before review, record the exact clean commit/tree and baseline and confirm the writer is stopped.
Each verdict binds to that immutable subject; apply the relevant correction or integration procedure
to changed candidates. Coordination evidence owns identities, while role payloads carry results.

The reviewer reads the candidate, tests, and existing observations for assigned criteria. Validation
execution belongs to observation owners; send requests for new observations to them. Interpret its
Result contract to distinguish defects, unreviewable subjects, and decisions. For separate Standards
and Spec findings, use [code-review](../code-review/SKILL.md) under its own review contract.

Review ends with a verdict or named blocker/decision for the assigned criteria. The Orchestrator
resolves remaining observations before normal acceptance or records cutoff's outstanding verification.

## Correct and decide

Count reviewer `BLOCKED` verdicts on reviewable candidates, default cap three per ticket unless the
user sets another. Record every verdict and cumulative count in Progress, including the cap-reaching
verdict. Questions and unreviewable subjects return for clarification or preparation. Preserve counts
across agents, sessions, and design corrections; the user grants a fresh allowance when wanted.

Read evidence and classify findings: in-contract defects become small owner-assigned corrections;
additional suggestions receive recorded disposition; user-level design, data-structure, scope, or
authority choices go to [batch handoff](../dev-flow/SKILL.md#ticket-handoff). Continue feasible work
under the confirmed contract and report a blocker when a decision prevents required behavior.

Below the cap, correct and rereview. Save the reviewed commit before correction, then send a fresh
reviewer the original brief, prior findings, that baseline, and the new exact candidate. Rereview
covers prior blockers and correction-related effects. Scope the review to the actual change.

At the cap, select the remaining in-scope fixes for one final bounded correction. Internal logic goes
to the implementer; formal-test edits go to the Orchestrator. Run required gates, form the final clean
commit, and record the final candidate's evidence. Independent review ends at the cap. Complete
[cutoff disposition](../dev-flow/SKILL.md#cutoff) from gates and Orchestrator observations; collect with
its recorded limitations. If correction or gates stay blocked, retain pending state and the concrete
decision owner.

For normal acceptance, establish each criterion from its assigned observation. For cutoff, distinguish
established claims from outstanding verification. Landing retains its separate user-authorization gate.

## Results and continuity

Role payloads retain these branches:

- `COMPLETED`: required `outcome`, optional `message`.
- `BLOCKED`: required `outcome`, `blocker`.

Writer completion attests passing required checks, a clean committed candidate, and complete assigned
evidence. Reviewer completion approves its fixed subject. The Orchestrator owns final disposition.
Non-blocking findings use `Residual risks:` in message or after a blocker. Runs own raw command output;
assigned evidence files own durable observations.

Use the live parent channel for decisions when available. Single-return runtimes report a clearly
marked question in `BLOCKED`, and the answer starts a fresh dispatch. An interrupted process needs
checkout/result inspection before deciding whether to resume or replace it.

A replacement receives the original assignment, blockers, verified and unverified work, environment,
and authority. It reads its ticket and needed pointers. Mechanical close-out assignments grant cleanup
and commit operations within already validated work.

Launch children in the background, continue independent work, then return control or yield an active
goal for completion notifications. Avoid block-waiting and polling. After compaction or handoff,
reread governing instructions and relevant records; recover uncertain parameters or authority first.

## Integrate

Record deferred paths and residual risks in their ticket; queue user decisions for batch handoff.
Collect ready accepted or cutoff branches into integration one at a time while other members continue.

Reconcile a stale feature branch with current integration. Resolve conflicts and verify the assembled
result with checks and review appropriate to the introduced changes. Judge the resulting candidate
before collection. Review inherited history as inherited; integration review focuses on its new
interactions, while existing cutoff findings retain their recorded disposition.

If persistence moved, reconcile it into integration through the runtime route. Reassess affected
task-level criteria and independently review imported changes before landing.

Collection verifies exact candidate identity, clean tracked state, and inclusion of current integration.
It advances task integration. Adoption previews the branch state being adopted and displaced managed
work; retain uncollected branches and evidence until their retirement is authorized.

## Land and clean up

Land under a current user message or in-force task-scoped grant naming the mutation and conditions;
read [custody](../dev-flow/references/custody.md) for durable grants. Otherwise stop at integration.
Push requires its own authority.

Managed landing creates a two-parent merge: previous persistence head first, judged integration head
second, with the judged integration tree. Both branches advance to it. Require persistence free of
staged changes, tracked unstaged changes, and ordinary untracked files. Ignored-file collisions and
hooks use native Git behavior; report failure with the resulting state. Changed candidates regain
the applicable judgement before landing.

Before destructive retirement, inventory owned resources and move required evidence to its durable
owner. Managed retirement can remove untracked and ignored files too. Remove owned temporary files,
processes, worktree registrations, and branches whose purpose is complete. Preserve user state and
record each retained resource's owner and cleanup condition. Finish when integration or landing is
confirmed and every execution resource is retired or explicitly retained.
