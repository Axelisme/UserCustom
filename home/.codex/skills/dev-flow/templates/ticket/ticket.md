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
| review batch | <review record path covering every criterion> |

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
<!-- Prepare during RED or pre-implementation contract preparation. For each applicable gate, name
     property/criterion, command/selection and working directory, environment, timeout, execution owner,
     and pass condition. Prefer existing checks; new behavior tests use confirmed seams/contracts.
     If none applies, record why and the direct-review alternative with its owner. Distinguish required
     ticket gates from batch observations and their readiness conditions. Preparation does not require
     every gate to run or fail at RED. Formal-test edits belong to the Orchestrator.
     Procedure: ~/.codex/skills/collab/references/execution.md#gate-preparation -->
{{CHECKS}}

## Progress
<!-- Keep delivery candidates and gate observations here; reference the owning batch review for
     verdicts, findings and corrections. Record consumed pending dependency candidates and inherited
     obligations. Maintain one replaceable semantic checkpoint that tells the next owner how to resume,
     verify or decide. Collection leaves this ticket pending for batch acceptance.
     Procedure: ~/.codex/skills/dev-flow/references/records.md#maintain-the-record -->
Semantic checkpoint: work not started.

## User decisions
<!-- Each entry states scenario, impact, options, recommendation, and answer. Procedure:
     ~/.codex/skills/dev-flow/references/records.md#ticket-handoff -->
None.

## Resolution
<!-- Final accepted candidate, observation pointers, batch review and covered criteria, disposition,
     and any outstanding work with its owner. Normal closure requires every applicable criterion and
     batch acceptance. Otherwise stay pending with a concrete blocker.
     Procedure: ~/.codex/skills/dev-flow/references/records.md#close -->
Pending.
