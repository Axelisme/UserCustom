---
id: {{TICKET_ID}}
state: pending
---
# {{TICKET_ID}} — {{TITLE}}

<!-- Copy this to tickets/<ticket-id>/ticket.md. The frontmatter `id` must equal that directory name.
     This ticket's durable evidence lives beside this file in the same directory — copy
     the evidence.md beside this template for each piece — and the whole directory is what closure
     discharges. Guiding script location: `<ticket>/scripts/` for the lane writer's helpers; the Orchestrator owns `<task>/scripts/` and the acceptor is read-only. The Orchestrator owns this ticket. Keep state pending until the Orchestrator resolves the ticket;
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
     means unproven, not necessarily that an executable test is red. Stable labels are encouraged but
     optional. A worker-reviewer loop is complete when every claim its writer owns is verified; its
     handoff reports remaining Orchestrator or user observations without treating them as blockers. -->
<!-- Each claim's checkbox belongs to its named observer, and a claim naming none belongs to the
     lane's writer, so name an Orchestrator, user, manual, external, or production-path observer on
     every claim you do not want the writer to toggle. Checkbox ownership, the closing sweep, and
     `Swept at`: ~/.codex/skills/dev-flow/references/lane-authority.md. Both role profiles carry the
     same rules, so they hold whether or not this comment survives publication.
     Every claim also states the observation that decides it and the surface it is observed on. A
     claim whose promise is about the shipped path is mis-stated when a static assertion or a
     test-only composition satisfies it; ~/.codex/skills/dev-flow/references/s0-design-admission.md
     owns what makes a surface adequate. A claim that names no deciding observation stops
     publication — see that reference's publication preconditions in
     ~/.codex/skills/dev-flow/references/ticket-seam-contract.md. -->
**Swept at:** <the commit every writer-owned claim was last re-confirmed against, or `not yet`>

- [ ] **A1** — <observable criterion>. *Observed by:* <the observation that decides it, on its
  surface; name a non-writer observer here when the claim is not the writer's to toggle>

## Mechanical gates
<!-- Ordered binary gate plan owned by this ticket. Every listed gate must pass before `COMPLETED`.
     Do not duplicate repository-owned commands: use pointer or existing owner, only add ticket-specific gates and execution order.
     Implementer runs in order: focused (or explicitly failing) → affected → formatter/style (re-run affected after any mutation) → broader/full.
     State a different order here only when this ticket needs one. The implementer profiles carry
     that same default, so the order holds whether or not this comment survives publication.
     Gate-mapping test (canonical definition: ~/.codex/skills/collab/SKILL.md boundary 2): draft
     this list by walking every Acceptance claim above and writing the gate that decides it. A claim
     is mechanically decidable when one command's exit status is that claim, with nothing in its
     output left to read. A claim becomes residue — what the dispatched acceptor judges — only once
     you have established that no command can decide it.
     Example gates (replace with ticket-specific ones): -->
- [ ] Focused behavior gates for changed reviewed-workflow schema and prompt composition
- [ ] Affected TypeScript/JavaScript static checks and profile/configuration format checks
- [ ] Formatter and import/style checks (re-run affected gates if files were mutated)
- [ ] Broader reviewed-lane and Dev-flow template selections after focused gates pass
- [ ] Absence scan: a retired symbol, path, or alias returns no hit across the tracked tree
- [ ] Inventory equality: the generated catalog's count equals the number this ticket declares
- [ ] Reachability: the shipped entrypoint, not a test-only composition, exercises the path
- [ ] Vacuous assertion: no test body asserts a constant or asserts nothing
- [ ] Acceptance sweep is current: `Swept at` equals the lane head

## Resolution
<!-- The Orchestrator writes this once when closing the ticket. Normal closure follows completion of all
     applicable Acceptance claims. An abandoned, superseded, or rejected closure may leave claims
     unchecked when this conclusion explains why. Keep only pointers needed to understand it. -->
Pending.
