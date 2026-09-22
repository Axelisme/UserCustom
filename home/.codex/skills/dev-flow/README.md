# Maintainer notes

Dev-flow owns durable task scope, tickets, alignment, INDEX, review records, and lifecycle state. Its
short `SKILL.md` routes agents to planning and record operations. Collab owns writer placement, review,
Git integration, and landing.

The shared design rationale, role information matrix, batch acceptance, evidence model, runtime split,
profile synchronization duties, walkthrough, and measurement limits live in
[`../collab/README.md`](../collab/README.md). Keep that file as the single owner rather than copying its
rules here. This README is maintainer material and is not part of routine agent startup.

`plan.py` reports drafted, pending, and closed tickets. Other readable state values contribute to the
unknown count without a state-value error; this does not declare their work accepted. Malformed or
unreadable records retain their existing diagnostics. Historical files are left unchanged.
