---
id: {{TICKET_ID}}
state: {{STATE}}
---
# {{TICKET_ID}}: {{TITLE}}

| Ticket field | Value |
|---|---|
| depends_on | <required ticket outcomes, or none> |
| completes | <ticket completing this partial increment, or none> |
| scope | <task scope or approved spec pointer> |

## Outcome
{{OUTCOME}}

## Scope and assumptions
<!-- Module write scope, exclusions, applicable authority, and runtime assumptions. -->
{{SCOPE}}

## Interface changes
<!-- Existing owners and authorized public changes; none if no public change. -->
{{INTERFACE_CHANGES}}

## Contract starting point
<!-- Existing complete contract, or the Orchestrator's seed commit with exact interface, declaration,
     shipped caller, formal-test locations, expected failures, and remaining internal implementation.
     Procedure: ~/.codex/skills/collab/references/execution.md#contract-seed -->
{{CONTRACT_STARTING_POINT}}

## Scenarios
<!-- Confirmed start, action, response, responsible modules, and meaningful boundaries. -->
{{SCENARIOS}}

## Alignment
<!-- Record the user's confirmation pointer. Shared batch design may be referenced, but this ticket
     names its own differences and scenarios. Procedure: ~/.codex/skills/dev-flow/references/planning.md#design-alignment -->
Awaiting design discussion and user confirmation.

## Acceptance
<!-- Every criterion names its observation and owner. Tests establish observable behavior. Direct
     review establishes prose, structure, configuration, repository data, and responsibility placement. -->
- [ ] A1: <observable criterion>. Check: <command, acceptor, Orchestrator, user, or external operator>.

## Mechanical gates
<!-- Name execution owner, command/selection, environment, timeout, and required property. Formal-test
     edits belong to the Orchestrator. Runtime output stays with its run. -->
{{CHECKS}}

## Progress
<!-- Record every reviewed candidate and whether a BLOCKED result was reviewable. New tickets default
     to one effective defect verdict; assignment problems do not count. For a pre-default ticket whose
     allowance is absent, recover and record it before review. Procedure:
     ~/.codex/skills/collab/references/review.md#correct-and-decide -->
Reviewer effective BLOCKED count: 0 of default 1. Work: not started.

## User decisions
<!-- Each entry states scenario, impact, options, recommendation, and answer. Procedure:
     ~/.codex/skills/dev-flow/references/records.md#ticket-handoff -->
None.

## Resolution
<!-- Final candidate, observations, disposition, and outstanding criteria. Cutoff separates established
     claims from final fixes and claims not independently confirmed. Procedure:
     ~/.codex/skills/dev-flow/references/records.md#cutoff -->
Pending.
