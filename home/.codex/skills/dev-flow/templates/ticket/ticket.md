---
id: {{TICKET_ID}}
status: todo
depends_on: []
---
# {{TICKET_ID}}: {{TITLE}}

<!-- Fill the ticket contract below. Record operations:
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
     Procedure: ~/.codex/skills/collab/references/execution.md#delegate -->
{{CONTRACT_STARTING_POINT}}

## Scenarios
<!-- Confirmed start, action, response, responsible modules, and meaningful boundaries. -->
{{SCENARIOS}}

## Alignment
<!-- Cite the governing decision or contract and this ticket's differences. Identify any unresolved
     user decision. Procedure: ~/.codex/skills/dev-flow/references/planning.md#design-alignment -->
Not yet recorded.

## Acceptance
<!-- Each criterion names the required observation and its owner. -->
- [ ] A1: <observable criterion>. Check: <command, acceptor, Orchestrator, user, or external operator>.

## Mechanical gates
<!-- One line per gate: the criterion it checks and a command that runs as written, with its cwd; or
     why no gate applies and the direct observation that replaces it. Run results go to
     runs/<short-sha>/summary.md. Preparation:
     ~/.codex/skills/collab/references/execution.md#gate-preparation -->
{{CHECKS}}

## User decisions
<!-- Open question: scenario, impact, options, recommendation. Once answered, replace the entry with
     a link to `../../decisions/NNNN-slug.md`, which holds the question, adopted option, and verbatim
     answer. Rules: ~/.codex/skills/dev-flow/references/records.md#user-decisions -->
None.

## Plan
<!-- Optional execution milestones, tagged with criterion IDs. -->

## Notes
<!-- Facts a later agent needs that code, Git, and decisions cannot supply: dead ends, non-obvious
     reasons, constraints found during work. Rewrite the whole section on every write; keep only what
     is still true and useful. Rules: ~/.codex/skills/dev-flow/references/records.md#maintain-the-record -->
