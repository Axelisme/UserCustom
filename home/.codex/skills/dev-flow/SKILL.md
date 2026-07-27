---
name: dev-flow
description: Route frozen work through planning, Git task coordination, acceptance, and close-out.
---

# Dev Flow

Use this skill for work that needs a frozen Contract and more than one session. It is a short
routing and coordination layer; each station owns its own interface and implementation details.
The [admission standard](references/admission-standard.md) is the sole authority for S1–S7.

## Route

```text
wayfinder → to-spec → to-tickets → orchestrate → acceptance → checkpoint → explicit close-out
```

`to-spec` freezes the user-visible envelope and `to-tickets` publishes dependency-addressable
Slices. `orchestrate` coordinates Git task lanes and returns an exact candidate SHA. Acceptance
uses the admission standard and the runtime adapter; it does not create another state model.

## Coordination

At each Slice, keep the Contract surface immutable to Implementation, run the named focused and
canonical gates, and hand off only a clean exact SHA with its evidence. Findings use the closed
classification and routing in the admission standard. A bounded delta stays on its originating
axis; a new behavioral Contract starts from Oracle and then Implementation. Root owns placement,
merges, and repository authority.

After compaction, reread this skill, the frozen spec, the task plan, and the admission standard.
Keep task narrative in planning-with-files' schemas and Git evidence in commits, refs, and
trailers. Runtime continuation belongs to the matching runtime binding. Explicit final close-out
follows S7; this skill does not add a second landing or acceptance policy.
