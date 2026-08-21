# Collab — Claude runtime

This file contains only Claude's native binding delta. The shared Collab skill remains the policy
authority, and the [implementer](../../../.claude/agents/collab-implementer.md) and
[acceptor](../../../.claude/agents/collab-acceptor.md) profiles remain the role and Result
authorities.

## Routing

Read only the section needed for the current step. Shared mechanics remain in the linked Collab
sections rather than being copied here.

- **Capability selection** — [Capability check](#capability-check)
- **Initial implementation, review, correction, or rereview** — [Composed delegation](#composed-delegation)
- **Continuation after a correction** — [Continuity](#continuity)
- **Worker or reviewer terminal handoff** — [Terminal handoff](#terminal-handoff)
- **Selecting the saved Workflow instead of native composition** — [Saved-Workflow
  selection](#saved-workflow-selection)
- **Collection** — [Collab collection boundary](SKILL.md#collection-boundary), only after the
  Orchestrator judges the reviewed lane
- **Landing** — [Collab land boundary](SKILL.md#land), only when its authority is present

## Capability check

At dispatch time, use the current Claude agent and tool inventory as the capability source of truth.
Require the exact `collab-implementer` and `collab-acceptor` profiles and Claude's native child-agent
dispatch capability. If a required role or dispatch capability is unavailable, report a runtime
capability gap to the Orchestrator. Do not silently select a generic writer, emulate a child with
shell processes, or rely on a cached tool signature, version, or feature catalogue.

The profile's declared tools and Result contract are authoritative for that child. Do not infer extra
capabilities from a session's optional task, plan, monitor, artifact, scheduling, or messaging tools.
Those tools, when present, are not Collab lifecycle stations.

## Composed delegation

For delegated closed work, compose the following native role calls over the one lane selected by the
Orchestrator. Follow [Collab's core guardrails](SKILL.md#core-guardrails) and [review placement and
the correction loop](SKILL.md#review-placement-and-the-correction-loop) for lane protection, finite
correction bounds, and escalation.

1. **Initial implementation:** dispatch a fresh `collab-implementer` with the bounded worker brief,
   assigned lane, mutation authority, validation expectations, and stop conditions. No second writer
   is introduced.
2. **Initial review:** after the implementer has returned and mutation has stopped, dispatch a fresh
   `collab-acceptor` against the protected current lane. The acceptor uses its read-only profile and
   independently reviews the current state.
3. **Authorized correction:** when the acceptor returns a bounded blocker and the Orchestrator
   authorizes correction, dispatch a compatible implementer with the original role, Result, and
   authority contract plus the current typed evidence. Use [Continuity](#continuity) only to choose
   whether that child reuses context.
4. **Rereview:** after any correction, mutation stops again and a fresh `collab-acceptor` reviews the
   changed protected lane. A previous review never covers a changed lane.
5. **Completion:** project the worker and acceptor semantic Results through the shared Collab
   handoff. Return blockers or decisions to the Orchestrator; do not perform final Acceptance,
   collection, landing, or escalation inside this binding.

## Continuity

Continuity is only a context-cache optimization. A resumed implementer is permitted only when it
preserves the `collab-implementer` role, its declared Result, and the original authority contract.
A fresh compatible implementer can continue from the bounded brief and current evidence without a
resume and is the default when context preservation is uncertain. See [Continuity is a
cache](SKILL.md#continuity-is-a-cache).

Every review and rereview uses a fresh compatible `collab-acceptor`; implementer context is never
carried into independent review. Session identity is not an Acceptance identity and is not durable
Collab state.

## Saved-Workflow selection

`collab-reviewed-lane` is an optional saved Claude Workflow that composes the same exact
`collab-implementer` and `collab-acceptor` roles as [Composed delegation](#composed-delegation). It
is an Orchestrator execution-shape selection over that same composition, not a new lifecycle,
authority, or Result contract.

Select it only after current implementation authority is closed, one pre-provisioned lane exists, and
the complete bounded input is closed. Discussion, planning, and unbounded requests do not produce
authority to select it. Its input is the six values: assigned lane, starting head, ticket pointer,
envelope pointer or `null`, a correction budget of `0` or `1`, and operator notes (free-form text or
`null`) whose authority is closed — no scope, no Acceptance criterion, no mutation authority, and a
note that contradicts the ticket means the ticket wins. The Workflow itself owns its Result schemas
and terminal projection; this adapter does not restate them.

Native composition through [Composed delegation](#composed-delegation) remains the default and stays
complete whenever the Workflow is not selected.

The Workflows feature is host and plan gated and can be absent from a correctly installed
environment: account entitlement, plan default, a remote gate, or a `disableWorkflows` setting each
turn it off, none of which is visible from this repository. Finding no `collab-reviewed-lane` means
the feature is unavailable here, not that the installation is broken; fall back to native composition.

## State and authority

The native binding dispatches roles; it does not create a second task or lane store. Durable task
authority remains with [dev-flow](../dev-flow/SKILL.md), while the Orchestrator retains scope,
Acceptance judgement, collection, landing, and escalation. Session task tools may serve the current
conversation but do not extend that authority.

No command, alias, additional lifecycle, result schema, or runtime-specific tool catalogue is added
here. The shared skill owns portable policy, and the role profiles own behavior and Results; this
adapter only selects and composes those existing contracts.

## Terminal handoff

Use the [semantic worker-result rules](SKILL.md#worker-results-are-semantic), the generic
[Acceptance result](SKILL.md#generic-acceptance), and the two role profiles for result shape. Project
semantic outcomes only; runtime/session identities and operation evidence remain outside the terminal
semantic handoff. A reviewed result is returned for the Orchestrator's judgement rather than treated
as final task Acceptance.
