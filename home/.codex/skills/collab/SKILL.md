---
name: collab
description: "Orchestrator feature-branch workflow: always use with dev-flow to assign implementation or review, judge results, integrate, or land."
---

# Collab

Collab owns writer placement, execution, review, integration, and landing.
[Dev-flow](../dev-flow/SKILL.md) owns commitments and records; read both entries when orchestrating.
Its Document authority decision governs changes throughout this workflow.

A lane is one ticket's branch/worktree. Integration accumulates accepted tickets; persistence is the
user's target branch. Each checkout has one writer. The Orchestrator owns intent, assignment, interface
declarations, formal tests, observation sufficiency, acceptance, and final disposition, and usually
implements directly. Existing attempts retain their injected contract; a newer profile governs only
a fresh spawn. Candidate workflow documents do not authorize their own adoption.

## Routing

Use `mdsec <absolute-path>#anchor ...` for the action's sections.

- Prepare work: [Placement](references/execution.md#placement), then [Prepare](references/execution.md#prepare).
- Implement or recover a result: [Implement](references/execution.md#implement),
  [Results and continuity](references/execution.md#results-and-continuity).
- Review: [Review](references/review.md#review), then [Correct and decide](references/review.md#correct-and-decide).
- Reconcile/collect: [Integrate](references/integration.md#integrate).
- Land or retire resources: [Land and clean up](references/integration.md#land-and-clean-up).
- Present reviewed integration or report delivery: [Delivery summary](references/delivery-summary.md#delivery-summary).

Before runtime operations, read [Pi routing](runtime-pi.md#routing) or
[Claude routing](runtime-claude.md#routing), then the selected section. Tool schemas own parameters;
missing runtime mechanics or capability blocks the operation.

## Role entries

For a fresh dispatch, use runtime role queries to discover roles and read the selected public
contract. Missing roles or invalid registries block dispatch. The Orchestrator reads INDEX, active
grants, the assigned ticket, and its operation section; receivers get a bounded brief with exact
sources, not instructions to scan INDEX or the task graph.

Collab uses collab-implementer for bounded internal changes and collab-acceptor for acceptance.
Their public contracts supply role permissions and result requirements. Prepare and Review supply
the assignment-specific inputs. Launch in the background and continue independent work; when none
remains, return control rather than polling.
