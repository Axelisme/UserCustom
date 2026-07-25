---
name: to-spec
description: Turn the current conversation into a spec and publish it to the repo's plan directory or issue tracker — no interview, just synthesis of what you've already discussed.
---

This skill takes the current conversation context and codebase understanding and produces a spec (you may know this document as a PRD). Do NOT interview the user — just synthesize what you already know. Closed exception: before freezing the spec, confirm the usage envelope with 3-5 short questions, not an open-ended interview: concurrency model (single caller, multiprocess, lock/atomic needs), realistic data scale and call frequency, failure tolerance (recovery or rerun), and caller population (personal/internal script or external users).

## Process

0. **Source conformance.** If the user supplied a source document — a design note, a handoff, a prior plan — walk its normative statements and tag each one `inherited`, `refined`, or `contradicted`. Every `contradicted` item is listed in the spec with the reason, and the spec does not freeze until the user has explicitly overridden it. Silently reversing a constraint the user wrote is the single most expensive failure this station can produce: it is authored at full clarity on day one, reads as good engineering, and survives every later quality gate because those gates check conformance to *this* spec. When there is no source document, say so in the spec rather than leaving the section absent.

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better - the ideal number is one.

Check with the user that these seams and the usage envelope match their expectations.

The published spec is the frozen Contract consumed by the Oracle and Implementation roles.
Only final code-review's Spec axis checks the implementation against this Contract. The workflow records Git evidence and does not assess source or spec. A review finding about behavior outside the recorded usage envelope has no contract basis.

3. Write the spec using the template below, then publish it to whichever backend this repo uses:

- **Plan-directory repo** (CLAUDE.md / AGENTS.md documents a `planning-with-files` / `.agent_state/plans/` convention): write the spec to `.agent_state/plans/<task-id>/spec.md`, initializing the plan directory via `planning-with-files` if it doesn't exist yet. This spec is the **frozen Contract** that the Oracle and Implementation roles consume and whose Spec axis is checked only by `/code-review`.
- **Tracker repo** (an issue tracker is documented, e.g. `docs/agents/issue-tracker.md`): publish it as an issue and apply whatever "ready for agent" triage convention the repo documents — no additional triage.
- **Neither**: write it to `.scratch/<feature-slug>/spec.md` and tell the user where it landed.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions
- The recorded usage envelope: concurrency model, scale/call frequency, failure tolerance, and caller population.

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts — not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Source Conformance

Only when a source document was supplied. A table of its normative statements tagged `inherited` / `refined` / `contradicted`, with the user's explicit override recorded for every `contradicted` row.

## Slice Map

The vertical Slices this spec decomposes into, in landing order. When a `wayfinder` map exists, these rows refine its acceptance staircase — one staircase step becomes one or more Slices, and a Slice that belongs to no step is either missing from the staircase or outside the destination. Each row carries the S1.1 observable sentence — *"the user does X at `<entrypoint>` and sees Y"* — and the `file:symbol` it deletes on completion. The first row is the **first production-reachable increment**, and its landing is days away, not weeks.

A spec that cannot be written as such a table has not been decomposed, and must not be frozen: it will be implemented as one atomic cutover regardless of what the migration section says. A completion definition that only holds when every row is finished is likewise not frozen — each row is independently acceptable by the user, or the decomposition is wrong.

## Out of Scope

A description of the things that are out of scope for this spec. Include explicit non-goals for behavior outside the recorded usage envelope; envelope-outside robustness findings are backlog, not Contract.

## Further Notes

Any further notes about the feature.

</spec-template>
