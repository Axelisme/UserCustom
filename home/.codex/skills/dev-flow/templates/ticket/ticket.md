---
id: {{TICKET_ID}}
state: pending
---
# {{TICKET_ID}} — {{TITLE}}

<!-- Copy this to tickets/<ticket-id>/ticket.md. The frontmatter `id` must equal that directory name.
     This ticket's durable evidence lives beside this file in the same directory — copy
     the evidence.md beside this template for each piece — and the whole directory is what closure
     discharges. Guiding script location: `<ticket>/scripts/` for the assigned writer's helpers; the Orchestrator owns `<task>/scripts/` and the acceptor is read-only. The Orchestrator owns this ticket. Keep state pending until the Orchestrator resolves the ticket;
     only the Orchestrator sets state closed or writes Resolution. -->

| Ticket field | Value |
|---|---|
| depends_on | <the ticket ids that must close before this one starts, or `none`> |
| envelope | <pointer to the frozen file holding this task's out-of-scope boundary — what belongs to this task at all, as against this ticket's own scope, which Outcome and Acceptance below already carry — or `none` if the task has no boundary> |

## Outcome
<!-- State the bounded goal and expected usable result. The Orchestrator owns this contract. -->
{{OUTCOME}}

## Seam contract
<!-- Contract rules: ~/.codex/skills/dev-flow/references/ticket-seam-contract.md. The reference owns
     mode fields, S# coverage, graduation, decision stops, and ADR authority. The Orchestrator owns
     this section. Keep this pointer in the published ticket. -->
<!-- Before publication or dispatch, replace this instruction and the placeholder below with exactly
     one complete `None`, `Existing`, or `Change` mode from the reference. -->
**Mode:** {{SEAM_MODE}}

## Acceptance
<!-- The Orchestrator owns this whole checklist and may revise it. Start every claim unchecked: unchecked
     means unproven, not necessarily that an executable test is red. Name an Orchestrator, user, manual,
     external, or production-path observer when it is not obvious. Stable labels are encouraged but
     optional. A worker-reviewer loop is complete when every delegated claim is verified; its
     handoff reports remaining Orchestrator or user observations without treating them as blockers. -->
- [ ] **A1** — <observable criterion>

## Mechanical gates
<!-- Ordered binary gate plan owned by this ticket. Every listed gate must pass before `COMPLETED`.
     Do not duplicate repository-owned commands: use pointer or existing owner, only add ticket-specific gates and execution order.
     Implementer runs in order: focused (or explicitly failing) → affected → formatter/style (re-run affected after any mutation) → broader/full.
     State a different order here only when this ticket needs one. The implementer profiles carry
     that same default, so the order holds whether or not this comment survives publication.
     Gate-mapping test (canonical definition: ~/.codex/skills/collab/SKILL.md boundary 2): an
     Acceptance claim above is mechanically provable iff some listed gate below's pass/fail is
     exactly that claim. Map each claim while drafting this list; any claim left unmapped means an
     acceptor is dispatched for this ticket.
     Example gates (replace with ticket-specific ones): -->
- [ ] Focused behavior gates for changed reviewed-workflow schema and prompt composition
- [ ] Affected TypeScript/JavaScript static checks and profile/configuration format checks
- [ ] Formatter and import/style checks (re-run affected gates if files were mutated)
- [ ] Broader reviewed-lane and Dev-flow template selections after focused gates pass

## Resolution
<!-- The Orchestrator writes this once when closing the ticket. Normal closure follows completion of all
     applicable Acceptance claims. An abandoned, superseded, or rejected closure may leave claims
     unchecked when this conclusion explains why. Keep only pointers needed to understand it. -->
Pending.
