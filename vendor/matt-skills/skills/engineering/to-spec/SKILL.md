---
name: to-spec
description: "Turn the current conversation into a spec and publish it where this repo tracks work: no interview, just synthesis of what you've already discussed."
---

This skill takes the current conversation context and codebase understanding and produces a spec. Do NOT interview the user; just synthesize what you already know.

**Where the spec lives is repo-specific.** If CLAUDE.md / AGENTS.md documents an issue tracker, follow it. If it documents none, default to local markdown at `.scratch/<feature-slug>/spec.md`.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better - the ideal number is one.

Check with the user that these seams match their expectations.

3. Write the spec using the template below, publish it as an **entry file**, then apply the tracker's `ready-for-agent` label equivalent if it uses a triage vocabulary; no need for additional triage.

## Keep the spec an entry file

A spec outlives the conversation that wrote it, and every later reader opens it looking for one
clause. Its length is a cost each of them pays in full: one 37KB spec cost a worker ~9k tokens on a
ticket whose whole delivery was five files and 77 lines, and the clauses it actually needed were two
sections of thirty lines.

So the published spec is an **entry file**: what every reader needs, plus one pointer per section
that only some readers reach.

- **Stays in the entry**: Problem Statement, Solution, Out of Scope, and any frozen clause a later
  gate cites by name (a usage envelope, a hard gate). Frozen clauses are quoted from, so they live
  where the quote is checked.
- **Moves behind a pointer**: long interface and contract detail, a per-slice or per-phase map,
  anything one kind of reader opens and the others never do. One file per section, beside the spec.

**Write each pointer as a condition, not a path.** *When you need the wire format, read
`spec/protocol.md`* reaches the reader who needs it. A bare list of paths under a heading reads as
an instruction to open all of them, and gets obeyed; measured on an admission that listed four
supporting reports and had all four opened by a worker that needed none of them.

Splitting a spec that already exists is a **move**, never a rewrite: every section keeps its bytes,
so frozen text stays byte-identical to what earlier gates cited.

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

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
