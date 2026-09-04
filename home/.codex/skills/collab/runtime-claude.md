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

## Dispatch

The Orchestrator dispatches each role itself, over the one lane it selected. That is the entire
binding: the loop's shape, its finite correction bounds, and its escalation are
[Collab's](SKILL.md#review-placement-and-the-correction-loop), unchanged.

Each dispatch is a fresh child of the exact profile — `collab-implementer` to write,
`collab-acceptor` to review the protected current lane once mutation has stopped, a fresh compatible
`collab-implementer` to correct under the original authority contract, and a fresh `collab-acceptor`
to rereview. Project the results through Collab's
[worker-result](SKILL.md#worker-results-are-semantic) and [Generic
Acceptance](SKILL.md#generic-acceptance) rules, and return blockers or decisions to the Orchestrator;
final Acceptance, collection, landing, and escalation happen outside this binding.

A Claude child has no live parent channel: it returns once, and a question it needs answered has to
come back as its whole result. Where Pi's `contact_parent` keeps a child waiting, here a decision
request ends the run and its answer starts a fresh one.
