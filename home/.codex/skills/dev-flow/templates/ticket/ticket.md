---
id: {{TICKET_ID}}
status: todo
depends_on: []
---
# {{TICKET_ID}}: {{TITLE}}

<!-- The sections through User decisions are the contract, settled before `ready` and rarely edited
     after. Plan and Log are the working area. Status values and when to write:
     ~/.codex/skills/dev-flow/references/records.md#maintain-the-record -->

## Outcome
{{OUTCOME}}

## Scope and assumptions
<!-- Module write scope, exclusions, and runtime assumptions; authority stays with the approved scope
     or grant. -->
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
<!-- The user's confirmation pointer. Shared design may be referenced; this ticket names its own
     differences. Procedure: ~/.codex/skills/dev-flow/references/planning.md#design-alignment -->
Awaiting design discussion and user confirmation.

## Acceptance
<!-- The unchecked boxes are the work left. Each criterion names its observation and owner: tests for
     observable behavior, direct review for prose, structure, configuration, data, and placement.
     A box is checked when the review round covering it returns COMPLETED. -->
- [ ] A1: <observable criterion>. Check: <command, acceptor, Orchestrator, user, or external operator>.

## Mechanical gates
<!-- For each gate: property/criterion, command and working directory, environment, timeout, execution
     owner, and pass condition. Prefer existing checks. If none applies, name the direct-review
     alternative. Procedure: ~/.codex/skills/collab/references/execution.md#gate-preparation -->
{{CHECKS}}

## User decisions
<!-- Each entry: scenario, impact, options, recommendation, and the user's answer. -->
None.

## Plan
<!-- Optional milestones when the ticket is built and reviewed in parts; tag each with its criteria. -->

## Log
<!-- Always the last section; locate shows its last line on the INDEX board. Append one line per
     event, newest last: `- MM-DD HH:MM → <status>: <reason or pointer>`. -->
