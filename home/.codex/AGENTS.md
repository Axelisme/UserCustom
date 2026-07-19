# Standing orders

## Orchestration iron rules

These apply whenever this session coordinates sub-agents (see the `orchestrate` skill).
They live here — always resident — because they must survive context compaction; the rest
of the skill degrades gracefully, these do not.

1. After dispatch, contact a running assignee only for a cost-growing finding — a
   public-contract correction, contract overturn, root-cause propagation, or successor
   stacking on a broken invariant — a user override/stop, or a fired liveness trigger;
   never for progress or status, and never on a fixed polling interval.
2. Review and integration bind to an exact commit SHA inspected from a clean detached
   checkout — never a live writer tree, and never a compaction summary's claim of green.
3. Landing on a persistence branch requires current user authority.
4. After a context compaction, re-read the orchestrate SKILL.md and the durable task plan
   before the next dispatch; the summary is hypothesis, not authority.
