# Ticket Seam contract

Use this reference when publishing or working from a Dev-flow ticket. The ticket's `## Seam contract`
is a transition record: it identifies the seam in force, records only this ticket's change, and names
where the result will live. It is not a second durable Interface declaration.

## Modes

Resolve exactly one mode before publication or dispatch:

### None

```md
## Seam contract

**Mode:** None
```

Use `None` only when the ticket neither depends on nor changes a non-obvious seam. If implementation
would require one, return `NEEDS_DECISION` rather than designing it locally.

### Existing

```md
## Seam contract

**Mode:** Existing

**Executable authority:** <exact code Interface pointer>

**Durable authority:** <exact Module README, docstring, ADR, or accepted `code-only` pointer>

**Ticket seam delta:** none
```

Both pointers must resolve. The ticket consumes and preserves this seam; it does not restate it.

### Change

```md
## Seam contract

**Mode:** Change

**Current authority:** <exact executable and durable authority pointers>

**Ticket delta:**

- **S1 — <name>:** <new or changed seam fact>
- **Decision stop:** <specific finding that needs Orchestrator judgement>

**Graduation:** <non-empty executable owner>; <non-empty durable declaration owner>
```

Use stable `S#` identifiers for only the placement, caller-visible Interface, authority, variation,
lifecycle, or decision-stop facts the implementer may not choose. Do not prescribe private helpers,
algorithms, fixture construction, complete call graphs, candidate identities, or validation commands.
Do not copy the seam's full current description into the ticket.

`Current authority` identifies both the code Interface and its existing durable declaration. Each
`S#` must have a covering Acceptance observer, written as `A# covers S#`. Behavior and Interface
claims may use tests. Composition, responsibility, and documentation ownership are reviewed directly;
do not introduce prose, AST, static-source, configuration, or repository-data tests for them.

## Graduation ownership

A changed non-obvious seam has one non-empty durable Interface declaration owner:

1. Prefer the owning Module README for a seam spanning files, callers, or tests, or carrying
   non-obvious authority, variation, ordering, error, or lifecycle rules.
2. A concise Module, class, or function docstring may own a complete small local Interface. An
   arbitrary file-header comment may not.
3. `code-only` is valid only when types, names, and structure completely express the seam and the
   reviewer explicitly accepts that no non-obvious semantic fact requires prose.
4. One semantic fact has one declaration owner; the ticket, code, README, docstring, and ADR must not
   compete by repeating it.

A Change ticket includes a reviewer-owned documentation claim covering the affected `S#` values. The
review confirms that the declared durable owner exists, is non-placeholder, states the applicable
responsibility, authority, variation, invariants, and lifecycle, and agrees with the candidate.

ADR content is user-maintained. Do not create, modify, or graduate seam content into an ADR unless the
governing spec explicitly authorizes that ADR update. When an ADR change appears necessary without
that authority, return `NEEDS_DECISION`; another document cannot silently substitute for it.

## Publication and change control

The Orchestrator exclusively owns mode selection, seam prose, `S#` placement, graduation, and
Acceptance wording. A correction blocker does not authorize a writer or a reviewer to amend the
contract.

**Satisfying this list is what `drafted` → `pending` means.** A ticket may exist without satisfying
it — that is the `drafted` state, and it is how a ticket carries a question whose answer would have
to be guessed. Reaching `pending` is reaching the whole list, and only a `pending` ticket is
dispatched.

A `depends_on` edge is satisfied by either terminal state, `closed` or `cutoff`. A cut-off dependency
stopped with verification unbought, so the downstream ticket inherits its unproven claims as world
facts under [ticket-alignment](ticket-alignment.md#inheriting-an-unverified-base); what it does not do
is block, because a task whose cap fires and then deadlocks has bought nothing.

Stop publication or dispatch when the mode is missing, unresolved, or a placeholder; an authority
pointer does not resolve; a Change `S#` lacks an `A# covers S#` observer; an Acceptance claim names
no observation that decides it, names no deciding observer to read that observation, or names an
observation whose surface cannot carry the promise it makes; the ticket declares no Module write scope, in
[codebase-design](../../codebase-design/SKILL.md#glossary)'s sense of Module rather than as paths;
graduation has an empty executable or durable owner; the `## Alignment` section is absent, unfilled,
or still a placeholder, which
[ticket-alignment](ticket-alignment.md) owns and which stops a dispatch as well as a publication,
because that section is settled at every ticket's start rather than once at graduation; or an ADR
target lacks explicit governing-spec authority. This is a
narrative Orchestrator check: do not add parser or schema validation until repeated evidence supports
a separately accepted stable schema.

While a ticket is `drafted` the Orchestrator may rewrite its `Outcome` inside the task's Envelope,
split the ticket, merge it into a neighbour, or drop it; a change that leaves the Envelope goes
through [custody](custody.md) instead. Every ticket naming this one as the completer of its
user-visible sentence is fixed in the same edit — a dangling completer edge is worse than none,
because it still reads as agreed. Investigation may be dispatched read-only; the Orchestrator writes
the contract, because a writer that authors the Acceptance it will be measured against leaves
[lane-authority](lane-authority.md#every-claim-names-the-observer-that-decides-it)'s deciding
observer answering to the party it is meant to measure.

If evidence shows that placement, authority, graduation, or the recorded Interface must change, return
`NEEDS_DECISION` with the contradiction and exact question. The Orchestrator coordinates the owning
`S#` and every affected Acceptance edge before authorizing resumed implementation.

## Role guidance ownership

This reference owns the contract's mode, content, coverage, graduation, change-control, and ADR
rules, and the preconditions that stop a ticket's publication or dispatch — including the Acceptance
drafting preconditions above, which are not seam facts but stop the same dispatch.
Lightweight retrieval and role-specific application are owned by the `collab-implementer` and
`collab-acceptor` agent profiles — every runtime copy of them, not the Pi pair alone. Their
source paths in this repository are `home/.pi/agent/agents/`, `home/.claude/agents/` and
`home/.codex/agents/`; a maintainer editing one of these rules edits all three. Do not copy that workflow
guidance into tickets.
