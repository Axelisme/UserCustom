---
name: code-review
description: Run the fixed-point ReviewGate on one exact candidate along standards and spec axes.
---

# ReviewGate

Run only after simplify and canonical tests pass. This is a read-only, integration-first final gate
over one exact candidate. The **review bracket** records pre and post status for the same path,
same branch, same HEAD, and clean state. The candidate is post-simplify and no later mutation is
allowed.

## Source and axes

Use the clean integration source by default. When the reviewer cannot prove a read-only
filesystem capability, use the **capability-based shared detached fallback**. Dispatch two fresh
axes against the same exact SHA and same source:

- `Axis: standards`
- `Axis: spec`

The bracket has explicit pre and post checks. No `collect` or `mutate` occurs between them; any
path, branch, HEAD, or clean mismatch invalidates the evidence. Each axis reports only its own
authority and includes `contract_basis` for a blocker. S4 governs the closed blocker enum and
`blocked_on_decision` result.

A **bounded delta** is reviewed by **one reviewer** on the **originating axis**; it does not reopen
two fresh axes. The output is the formal **ReviewGate output**: exact SHA, source and checkout
proof, axis verdict, blocking/backlog findings, and immutable-path evidence. This skill owns ReviewGate output only; correction routing and close-out belong elsewhere.
