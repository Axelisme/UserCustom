---
id: {{TICKET_ID}}
state: {{STATE}}
---
# {{TICKET_ID}}: {{TITLE}}

<!-- Use drafted or pending under ~/.codex/skills/dev-flow/SKILL.md#tickets.
     The Orchestrator owns this file. Keep any exceptional evidence file beside it and retain
     Resolution after closure. -->

| Ticket field | Value |
|---|---|
| depends_on | <required ticket outcomes, or none> |
| completes | <ticket completing this partial increment, or none> |
| scope | <task scope or approved spec pointer> |

## Outcome
{{OUTCOME}}

## Scope and assumptions
<!-- Module-level write scope, exclusions, and relevant deployment, trust, or concurrency assumptions.
     Identify facts needing confirmation and stop when they affect correctness or authority. -->
{{SCOPE}}

## Interface changes
<!-- Existing contract owners and authorized public changes; none if no public change.
     Document non-obvious obligations at the owning module. New scope or interface decisions
     return to the Orchestrator; ADR changes need explicit user authority. -->
{{INTERFACE_CHANGES}}

## Contract starting point
<!-- The Orchestrator names the seed commit, or the existing complete contract, with exact interface,
     declaration, shipped caller, and contract-test locations. These contract and test edits belong
     to the Orchestrator. Record agreed key data structures, important algorithm choices, expected
     test failures, and a short implementation sequence for the implementer's remaining small task.
     Point to existing declarations where they already own these facts.
     For work without a code interface, write Not applicable.
     Preparation: ~/.codex/skills/collab/SKILL.md#contract-seed -->
{{CONTRACT_STARTING_POINT}}

## Scenarios
<!-- Agreed starting situation, user action, system response, and responsible modules.
     Include a requirement-backed boundary or failure case when it changes the design. -->
{{SCENARIOS}}

## Alignment
<!-- The Orchestrator records the user's confirmation of this ticket's design and scenarios,
     including confirmation during a batch alignment.
     Record confirmation of the resulting proposal after questions and revisions are resolved.
     Design facts stay in their owning sections. -->
Awaiting design discussion and user confirmation.

## Acceptance
<!-- The Orchestrator turns every agreed behavior, responsibility allocation, and public interface
     choice into explicit acceptance criteria before implementation. Each names its observation and
     responsible check/person; related decisions may share a criterion.
     Tests or scenario observations verify behavior; direct review verifies responsibilities,
     interface placement, prose, configuration, and repository data.
     The Orchestrator updates checkboxes from recorded observations. -->
- [ ] A1: <observable criterion>. Check: <command, reviewer, Orchestrator, user, or external operator>.

## Mechanical gates
<!-- Required checks in execution order. Point to repository-owned commands where available.
     The Orchestrator owns formal test edits. Implementer probes stay in run-owned temporary locations
     and are removed before final commit and handoff.
     Record completion from observed execution results. Re-run affected checks after any mutation. -->
{{CHECKS}}

## Progress
<!-- Record reviewer BLOCKED verdicts on reviewable candidates, including the cap-reaching verdict.
     Preserve the count across dispatches and corrections. Questions and unreviewable subjects return
     for clarification. Final correction and cutoff follow ~/.codex/skills/collab/SKILL.md#correct-and-decide. -->
Reviewer BLOCKED count: 0. Work: not started.

## User decisions
<!-- The Orchestrator collects this ticket's issues for batch handoff, before the next batch's alignment.
     Each entry states scenario, impact, options, and recommendation; record the user's answer when given.
     Continue the feasible authorized work under the agreed design. Identify a concrete blocker when
     required behavior depends on a user decision. Procedure: ~/.codex/skills/dev-flow/SKILL.md#ticket-handoff -->
None.

## Resolution
<!-- Final disposition, candidate, concise verification results or pointers, and outstanding criteria.
     Keep the ticket's scenarios, design discussion and decisions, findings, and cited observations in
     their owning files through closure and task archive. Read historical context on demand.
     Cutoff records the final bounded correction and passing gates, remaining findings and scenarios,
     and verification still awaiting independent review. Retain this record for user-triggered revisiting.
     Disposition: ~/.codex/skills/dev-flow/SKILL.md#cutoff -->
Pending.
