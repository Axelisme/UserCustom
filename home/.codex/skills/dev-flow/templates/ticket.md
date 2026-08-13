---
id: {{TICKET_ID}}
state: pending
---
# {{TICKET_ID}} — {{TITLE}}

<!-- The Caller owns this ticket. Keep state pending until the Caller resolves the ticket;
     only the Caller sets state closed or writes Resolution. -->

| Ticket field | Value |
|---|---|
| depends_on | <the ticket ids that must close before this one starts, or `none`> |

## Outcome
<!-- State the bounded goal and expected usable result. The Caller owns this contract. -->
{{OUTCOME}}

## Acceptance
<!-- The Caller owns this whole checklist and may revise it. Start every claim unchecked: unchecked
     means unproven, not necessarily that an executable test is red. Name a Caller, user, manual,
     external, or production-path observer when it is not obvious. Stable labels are encouraged but
     optional. A delegated writer may only toggle claims explicitly assigned to it; a reviewer is
     read-only. A worker-reviewer loop is complete when every delegated claim is verified; its
     handoff reports remaining Caller or user observations without treating them as blockers. -->
- [ ] **A1** — <observable criterion>

## Resolution
<!-- The Caller writes this once when closing the ticket. Normal closure follows completion of all
     applicable Acceptance claims. An abandoned, superseded, or rejected closure may leave claims
     unchecked when this conclusion explains why. Keep only pointers needed to understand it. -->
Pending.
