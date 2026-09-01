# Dev-flow — graduating a decision to an ADR

`decisions/` lives in the untracked task container, so a decision whose force outlives its task needs
a home in the repository itself — one ticket whose whole output is one ADR. Two conditions govern
that ticket, cheapest test first:

1. **Self-contained.** The ADR references nothing under `.agent_state/`; tracked content — commit
   identities, module Interface declarations, source paths — is unrestricted. Write the
   self-contained version to find out: a decision that cannot be stated without pointing back into
   its task record has not finished separating from that task, and does not graduate. This is also
   what licenses the ADR to restate reasoning `decisions/` already holds, which
   [design-principles](design-principles.md) has you point at everywhere else: the record it restates
   is designed to disappear, so here alone the ADR is its heir rather than a competing copy.
2. **The user opens it.** Dev-flow supplies the route and waits. The rate at which ADRs appear stays
   a human decision, which is why this is a separate ticket rather than a closure obligation, and a
   decision still moving is one the user has not asked to record.

Whether a decision qualifies at all, and what an ADR looks like, belong to `domain-modeling`: read
[its ADR format](../../domain-modeling/ADR-FORMAT.md) for the gates under "When to offer an ADR", the
template, and the numbering.
