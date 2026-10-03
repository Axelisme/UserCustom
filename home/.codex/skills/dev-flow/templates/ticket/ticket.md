---
id: {{TICKET_ID}}
status: todo
depends_on: []
---
# {{TICKET_ID}}: {{TITLE}}

<!-- The sections through User decisions hold the specification contract, settled before `ready`.
     Change authority: ~/.codex/skills/dev-flow/references/records.md#document-authority
     Plan is execution planning; Log indexes necessary events. Status values and when to write:
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
<!-- Cite the governing decision or contract and this ticket's differences. Identify any unresolved
     user decision. Procedure: ~/.codex/skills/dev-flow/references/planning.md#design-alignment -->
Not yet recorded.

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
<!-- Each entry: the question (scenario, impact, options, recommendation) and a link to the user's
     answer in `../../decisions/NNNN-slug.md`. -->
None.

## Plan
<!-- Execution plan: optional milestones, tagged with their criteria.
     Change authority: ~/.codex/skills/dev-flow/references/records.md#document-authority -->

## Log
<!-- Necessary collaboration events and acceptance grounds, newest last. Status lives in frontmatter.
     Recording rules: ~/.codex/skills/dev-flow/references/records.md#maintain-the-record -->
