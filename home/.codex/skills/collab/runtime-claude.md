# Collab: Claude runtime

Claude's native binding delta, and nothing else. [Collab](SKILL.md) owns policy; the installed
implementer and acceptor profiles own receiver contracts and Results.

## Routing

- Before dispatch, read [Capability check](#capability-check), then [Dispatch](#dispatch).
- For native Git collection or landing, apply [Integrate](references/integration.md#integrate) and
  [Land and clean up](references/integration.md#land-and-clean-up).
- Specialized operations not documented here require a decision before use.

## Capability check

At dispatch, use the current Claude agent and tool inventory as the capability source of truth. Require
exact `collab-implementer` and `collab-acceptor` profiles plus Claude's native child dispatch. If a
required capability is missing, report `BLOCKED` with the missing item. Do not substitute a generic
writer, shell process, or cached tool catalogue.

The profile's declared tools and Result contract are authoritative. Optional planning, monitoring,
artifact, scheduling, or messaging tools add no Collab lifecycle operation.

## Dispatch

The Orchestrator dispatches each role over the selected lane. Read Collab
[Prepare](references/execution.md#prepare), [Results and continuity](references/execution.md#results-and-continuity),
and [Correct and decide](references/review.md#correct-and-decide) for the portable loop.

Each dispatch is a fresh child of the exact profile: `collab-implementer` writes or corrects, and
`collab-acceptor` reviews one stopped immutable assembled subject against its batch brief. Corrections
produce a new clean candidate with applicable verification for a fresh acceptor dispatch.

A Claude child has no live parent channel. A needed decision returns as `BLOCKED` with the question
first. The answer starts a fresh dispatch. Do not brief a child to wait for an answer it cannot receive.
