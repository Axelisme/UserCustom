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
as `{sha, comment?, uncollected}` objects with top-level `pending` while omitting the managed
acceptance checkout field. `uncollected` is Git-derived first-parent work outside integration;
pending independently counts collected lanes awaiting agent acceptance. The ninth and later active
lane creates warn factually when projected `uncollected > 0` but remain successful.

The ticket carries the admitted Contract and validation mode. Continuation keeps the same persistent
lane: a semantic Contract change requires fresh admission, while rework does not automatically change
lane or session. Provider and liveness recovery use the worker context classification below; exact
cwd, Git identity, branch, HEAD, and write scope remain hard-bound and an identity mismatch fast-fails.

| worker context | Root action |
| --- | --- |
| context is an asset | Resume the same session. |
| context is debt | Start a fresh run in the same lane. |
| lane is unnecessary | `lane drop`. |

The worker's terminal lane-ready report is normal runtime output: TDD names every Contract commit SHA
with its exact red command, observed red reason, and green result; direct mode names the frozen Contract
pointer, changed and protected paths, direct validation commands/results, and final exact clean SHA.
Root proves the public process-terminal result and Git facts; no external worker artifact is required.

## Authority

Root owns status, collection, acceptance, landing, report, removal, and recovery.
