# Porting a skill from another ecosystem

A skill written for someone else's workflow carries their ecosystem's assumptions along
with its portable content. Porting is the act of separating the two: **rebinding, not
rewriting**.

## 1. Inventory the bindings

Read the skill hunting for every place it assumes the source ecosystem:

- **Work backend**: where work items live (an issue tracker, local files, a plan system).
- **Doc layout**: where glossaries, decision records, and notes are expected to sit.
- **Execution model**: who acts (a solo agent end-to-end, or orchestrated roles) and who
  it confirms things with (the user live, or a frozen upstream artifact).
- **Companion skills**: invocations of skills you don't have, and setup skills that
  configure the source ecosystem.
- **Tooling and paths**: hard-coded interpreters, directories, CLI names.

## 2. Classify each piece

- **Portable content**: disciplines, checklists, anti-pattern catalogs, **leading words**:
  the reason you want the skill. Keep verbatim where possible; heavy rewriting destroys the
  distributed definitions the leading words have accumulated.
- **Ecosystem bindings**: everything in the inventory above. These get rebound.
- **Dead weight**: setup references, triage labels, branches of the skill your ecosystem
  will never take. Delete.

## 3. Decide its fate against your existing fleet

Measure **net new content per unit of context load**, then pick one:

- **Adopt**: enough unique portable content to justify a skill slot.
- **Merge**: it overlaps an existing skill; fold the missing parts in, keep one name.
- **Absorb**: only a few lines are load-bearing; fold them into an existing carrier
  (another skill, a role definition, a convention doc) and take no new skill.
- **Skip**: the content contradicts your ecosystem's design philosophy, or duplicates
  what you already have. Record why, so the question isn't reopened.

## 4. Rebind

- **Backends become conditional**: "your repo's documented convention wins; the source
  skill's layout is the fallback for repos that document nothing."
- **Confirmations move to where your flow already settles them**: a "confirm with the
  user" step stays interactive in interactive use, but reads from the frozen upstream
  artifact when a pipeline already answered the question; reopening it there is a
  reported gap, not a fresh interview.
- **Missing companions**: replace invocations of skills you lack with your equivalent, or
  inline the one behavior you needed from them.

## 5. Check for cross-skill contradictions

Load the ported skill mentally *alongside* the skills it will co-fire with: do any two
rules give the agent conflicting orders (one says write immediately, another says batch)?
Resolve by keeping a **single source of truth** with an explicit override slot the caller
can declare; never by letting both texts stand.

## 6. Record the deltas

Note what you changed and why (a commit message is enough). Upstream evolves; a delta
record is what lets you re-apply your localizations to a newer version instead of
re-deriving them.
