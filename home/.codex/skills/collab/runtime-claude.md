# Collab — Claude runtime

Claude's native binding delta, and nothing else. [Collab](SKILL.md) owns the policy, and the
[implementer](../../../.claude/agents/collab-implementer.md) and
[acceptor](../../../.claude/agents/collab-acceptor.md) profiles own their roles and Results.

## Capability check

At dispatch time, use the current Claude agent and tool inventory as the capability source of truth.
Require the exact `collab-implementer` and `collab-acceptor` profiles and Claude's native child-agent
dispatch capability. If a required role or dispatch capability is unavailable, report a runtime
capability gap to the Orchestrator rather than selecting a generic writer, emulating a child with
shell processes, or trusting a cached tool signature, version, or feature catalogue.

The profile's declared tools and Result contract are authoritative for that child. A session's
optional task, plan, monitor, artifact, scheduling, or messaging tools imply no further capability
and are not Collab lifecycle stations.

## Composed delegation

**Claude has no composed reviewed-lane tool.** Where the Pi runtime hands the whole worker → reviewer
→ bounded correction loop to one call, here the Orchestrator dispatches each role itself, over the
one lane it selected. That is the entire binding: the loop's shape, its finite correction bounds, and
its escalation are [Collab's](SKILL.md#review-placement-and-the-correction-loop), unchanged.

Each dispatch is a fresh child of the exact profile — `collab-implementer` to write, `collab-acceptor`
to review the protected current lane once mutation has stopped, a fresh compatible implementer to
correct under the original authority contract, and a fresh acceptor to rereview. Every one of those
is an Orchestrator dispatch, so each re-enters boundary 2 and has its placement decided again.
Project the results
through Collab's [worker-result](SKILL.md#worker-results-are-semantic) and [Generic
Acceptance](SKILL.md#generic-acceptance) rules, and return blockers or decisions to the Orchestrator;
final Acceptance, collection, landing, and escalation happen outside this binding.

## Saved-Workflow selection

`collab-reviewed-lane` is an optional saved Claude Workflow composing those same two profiles. It is
an Orchestrator execution-shape selection over the same composition, not a new lifecycle, authority,
or Result contract, and it owns its own Result schemas and terminal projection.

Its correction is the Workflow's own: placement was fixed when the Workflow was launched, so
Collab's boundary-2 re-entry reaches a correction the Orchestrator dispatches after the Workflow
hands back, never one issued inside it.

Select it only after current implementation authority is closed, one pre-provisioned lane exists, and
the complete bounded input is closed; discussion, planning, and unbounded requests close none of
those. Its input is six values: assigned lane, starting head, ticket pointer, envelope pointer or
`null`, a correction budget of `0` or `1`, and operator notes — free-form text or `null` — carrying no
scope, no Acceptance criterion, and no mutation authority. A note that contradicts the ticket loses to
the ticket.

The Workflows feature is host and plan gated and can be absent from a correctly installed
environment: account entitlement, plan default, a remote gate, or a `disableWorkflows` setting each
turn it off, none of which is visible from this repository. Finding no `collab-reviewed-lane` means
the feature is unavailable here, not that the installation is broken; native composition above stays
complete whenever the Workflow is not selected.
