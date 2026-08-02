# Orchestrate — runtime-neutral dispatch contract

Before dispatch Root runs `lane check --task-id <task> --lane-id <lane>`, which must exit 0, and reads `status
--task-id <task>` to record the exact lane tip SHA. That SHA is the expected base carried in the
dispatch together with the frozen objective, `Validation mode: TDD` or `Validation mode: direct —
<specific reason>`, canonical lane cwd, expected Git root/common-dir, branch, write scope, immutable
paths, primary-checkout dirt snapshot, focused commands, evidence, and stop conditions. When the task
has a durable record, the dispatch also carries its `Envelope` and any `Standing orders`: the worker
cannot honour a boundary the user froze, or an instruction the user issued, that never reached it.
Root chooses the mode at admission; a worker cannot downgrade TDD. File type never chooses the mode.

Working inside the canonical lane cwd is the only hard contract; the agent, its skills, and its context
mode are recommendations. The worker reports the cwd, Git root/common-dir, branch, HEAD, and clean state
it observes, and Root judges whether they match the admitted lane. The worker runs no mechanical
self-check and does not block itself. Every later operation is path-bound. Root verifies identity and
primary dirt before `lane check`, then reviews mode-appropriate pre-collect evidence: in TDD mode,
the Contract-first commits and red evidence; in direct mode, the frozen Contract pointer,
changed/protected paths, and direct validation results. Root alone invokes `lane sync` or collection.
The worker resolves and commits a sync conflict in its lane; shared integration is never the conflict
workspace.

Root invokes `acceptance start [--sha <exact>]` to create one detached snapshot from the managed
integration branch's first-parent history. Canonical tests and ReviewGate run there; Root records an
agent or current-user decision with required `acceptance result --verifier`. Agent pass establishes
landing authority in `accepted`; user pass records independent evidence in `user-accepted`. A
persistence advance routes through an admitted writer lane and `integration reconcile`; after collection
the exact snapshot must receive agent acceptance again before it can become landed. `timing pause` and `timing
resume` bracket external waits without granting lifecycle authority.

The current CLI has no lane group or consumption policy: `lane create` accepts an optional bounded
annotation, `lane comment --text|--clear` overwrites or clears it, and status projects active lanes
as `{sha, comment?}` objects while omitting the managed acceptance checkout field. The ninth and
later active-lane creates warn factually but remain successful.

Continuation is admissible only while the frozen Contract, provider, cwd, and lane identity all remain
unchanged. A semantic Contract, observable behavior, public Interface, liveness, or identity change
requires fresh dispatch and Root re-admission.

The terminal lane-ready handoff is mode-specific: TDD names every Contract commit SHA with its
exact red command, observed red reason, and green result; direct mode names the frozen Contract
pointer, changed and protected paths, direct validation commands/results, and the final exact clean
SHA.

## Authority

Root owns status, collection, acceptance, landing, report, removal, and recovery.
