---
id: {{TICKET_ID}}
state: {{STATE}}
---
# {{TICKET_ID}} — {{TITLE}}

<!-- Copy this to tickets/<ticket-id>/ticket.md. The frontmatter `id` must equal that directory name.
     This ticket's durable evidence lives beside this file in the same directory — copy
     the evidence.md beside this template for each piece — and the whole directory is what closure
     discharges. Guiding script location: `<ticket>/scripts/` for the lane writer's helpers; the Orchestrator owns `<task>/scripts/` and the reviewer is read-only. The Orchestrator owns this ticket.
     Lifecycle is `drafted` -> `pending` -> `closed`, or `pending` -> `cutoff` when the review that
     would settle the rest is no longer bought, and only the Orchestrator moves it. Create the
     ticket in whichever of the first two states fits, and replace `{{STATE}}` with that choice:
     `pending` when its contract can already be written from the code, `drafted` when writing it now
     would mean guessing, in which case fill only what is known and leave the rest. Neither is a
     default; an unreplaced `{{STATE}}` is an unreadable ticket, which is the point.
     A ticket is `pending` before its implementation starts; what it must satisfy to get there is
     the publication precondition list at
     ~/.codex/skills/dev-flow/references/ticket-seam-contract.md#publication-and-change-control. -->

| Ticket field | Value |
|---|---|
| depends_on | <the ticket ids that must reach a terminal state — `closed` or `cutoff` — before this one starts, or `none`. A `drafted` ticket reaches neither, so naming one here blocks this ticket until that one graduates and terminates.> |
| completes | <when this ticket only partly delivers its user-visible sentence, the ticket id that completes that sentence — which may itself still be `drafted`. `none` when this ticket delivers its whole sentence.> |
| envelope | <pointer to the frozen file holding this task's out-of-scope boundary — what belongs to this task at all, as against this ticket's own scope, which Outcome and Acceptance below already carry — or `none` if the task has no boundary> |

## Outcome
<!-- State the bounded goal and expected usable result. The Orchestrator owns this contract. -->
{{OUTCOME}}

## Alignment
<!-- The five steps, when they run, and what a world fact is:
     ~/.codex/skills/dev-flow/references/ticket-alignment.md. Step 4's confirmed result lands here;
     steps 1-3 settle seam facts `## Seam contract` owns. The Orchestrator writes this section fresh
     at every start of this ticket, replacing both placeholders below. -->

**World facts:** {{WORLD_FACTS}}
<!-- One line per fact this ticket rests on that no frozen record states, each marked `confirmed` or
     `unconfirmed`; `none` when the frozen records settle what this ticket needs. -->

**Not doing:** {{NON_GOALS}}
<!-- The nearby work a reader could reasonably expect this ticket to include and that it
     deliberately leaves out. -->

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
     Every claim also states the observation that decides it, on the surface it is observed on, in
     its own `Decided by` slot. Keep that separate from `Observed by`: `Observed by` names the party
     whose checkbox it is and is omitted when that party is the writer, while `Decided by` is always
     present. A claim whose promise is about the shipped path is mis-stated when a static assertion
     or a test-only composition satisfies it; ~/.codex/skills/dev-flow/references/s0-design-admission.md
     owns what makes a surface adequate. A claim that names no deciding observation stops
     publication under the preconditions in
     ~/.codex/skills/dev-flow/references/ticket-seam-contract.md. -->
**Swept at:** <the commit every writer-owned claim was last re-confirmed against, or `not yet`>
<!-- Checked after handoff, by the reviewer when one is placed and otherwise by the Orchestrator at
     boundary 4. Never a Mechanical gate: the gate list runs before the writer commits. -->

- [ ] **A1** — <observable criterion>. *Decided by:* <the observation that decides it, on its
  surface>
  *Observed by:* <the non-writer party this checkbox belongs to; omit the whole slot when it is the
  writer>

## Mechanical gates
<!-- Ordered binary gate plan owned by this ticket. Every listed gate must pass before `COMPLETED`.
     Do not duplicate repository-owned commands: use pointer or existing owner, only add ticket-specific gates and execution order.
     Implementer runs in order: focused (or explicitly failing) → affected → formatter/style (re-run affected after any mutation) → broader/full.
     State a different order here only when this ticket needs one. The implementer profiles carry
     that same default, so the order holds whether or not this comment survives publication.
     Gate-mapping test: draft this list by walking every Acceptance claim above and writing the
     gate that decides it. A claim becomes residue — what a dispatched reviewer judges — only once
     you have established that no command can decide it. `mechanically decidable` and `residue` are
     defined at ~/.codex/skills/collab/SKILL.md boundary 2; read it when a claim is borderline.
     Example gates (replace with ticket-specific ones): -->
- [ ] Focused behavior gates for changed reviewed-workflow schema and prompt composition
- [ ] Affected TypeScript/JavaScript static checks and profile/configuration format checks
- [ ] Formatter and import/style checks (re-run affected gates if files were mutated)
- [ ] Broader reviewed-lane and Dev-flow template selections after focused gates pass
- [ ] Absence scan: a retired symbol, path, or alias returns no hit across the tracked tree
- [ ] Inventory equality: the generated catalog's count equals the number this ticket declares
- [ ] Reachability: the shipped entrypoint, not a test-only composition, exercises the path
- [ ] Vacuous assertion: no test body asserts a constant or asserts nothing

## Reviewer block ledger
<!-- The Orchestrator writes this when a review returns. It counts the reviewer `BLOCKED` verdicts
     this ticket has accumulated since its design was last fixed; the third one is where review stops
     being placed. It lives here rather than with the run because a composed loop's correction budget
     starts over at the next dispatch. Only a user-approved re-alignment that changed `Outcome` or an
     `S#` resets it, and the reset records the prior count and the reason:
     ~/.codex/skills/dev-flow/references/record-hygiene.md#the-reviewer-block-ledger -->
Reviewer blocks: 0. Resets: none.

## Resolution
<!-- The Orchestrator writes this once at the ticket's terminal transition. Normal closure follows
     completion of all applicable Acceptance claims. An abandoned, superseded, or rejected closure may
     leave claims unchecked when this conclusion explains why. A `cutoff` ticket separates the proved
     claims from the declared ones and names who declared each:
     ~/.codex/skills/dev-flow/references/record-hygiene.md#a-cutoff-tickets-resolution
     Keep only pointers needed to understand it. -->
Pending.
