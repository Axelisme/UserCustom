# Dev-flow — graduating a decision to an ADR

The task record is ephemeral: `decisions/` lives inside the task container, which is not tracked
where this workflow runs. A decision whose force outlives its task therefore needs a home in the
repository itself, and one ticket carries it there — a ticket whose whole output is one ADR.

Two conditions govern that ticket:

1. **The user opens it.** Dev-flow supplies the route and never takes it on its own. The rate at
   which ADRs appear stays a human decision, which is the whole reason this is a separate ticket
   rather than a closure obligation. Timing follows from this: a decision still moving is one the
   user has not asked to record.
2. **The ADR is self-contained.** It references nothing under `.agent_state/`: that content is not
   in git, so the reference dangles for every later reader. What git holds is unrestricted — commit
   identities, module Interface declarations, source paths, any tracked file.

The second condition is also the cheapest admission test, and it runs first. Attempt the
self-contained version: a decision that cannot be stated without pointing back into its task record
has not finished separating from that task, and does not graduate.

Condition 2 makes the ADR **restate** reasoning that `decisions/` already holds, which
[the design principles](design-principles.md) require pointing at everywhere else. Here the record
being pointed at is designed to disappear, so the ADR is the heir rather than a competing copy. That
is what licenses the restatement in this one case, and nowhere else.

Whether a decision qualifies at all, and what an ADR looks like, belong to `domain-modeling`. When
this ticket is opened, read [its ADR format](../../domain-modeling/ADR-FORMAT.md) for the gates
under "When to offer an ADR", the template, and the numbering.
