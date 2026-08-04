# Orchestrate — runtime-neutral dispatch contract

Before dispatch Root runs `lane check --task-id <task> --lane-id <lane>`, which must exit 0 and
reports the exact lane `sha`, `base`, and `protected_paths`. That `sha` is the expected base carried
in the dispatch, and those `protected_paths` are its immutable paths — both are read from the check
that just computed them, never rebuilt by hand. The dispatch carries them together with the frozen
objective, `Validation mode: TDD` or `Validation mode: direct —
<specific reason>`, canonical lane cwd, expected Git root/common-dir, branch, write scope,
primary-checkout dirt snapshot, focused commands, evidence, and stop conditions. When the task
has a durable record, the dispatch also carries its `Envelope` and any `Standing orders`: the worker
cannot honour a boundary the user froze, or an instruction the user issued, that never reached it.
Root chooses the mode at admission; a worker cannot downgrade TDD. File type never chooses the mode.

Working inside the canonical lane cwd is the only hard contract; the agent, its skills, and its context
mode are recommendations. The worker reports the cwd, Git root/common-dir, branch, HEAD, and clean state
it observes, and Root judges whether they match the admitted lane. The worker runs no mechanical
self-check and does not block itself. Every later operation is path-bound. Root verifies identity and
primary dirt, then holds the mode-appropriate pre-collect evidence the admission standard's S2.5
requires — proven by executing it at the exact bound SHA, not read out of the diffs that produced
it. In direct mode that evidence is the frozen Contract pointer, changed and protected paths, and
the direct validation results. Root alone invokes `lane sync` or collection.
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
lane or session. Provider and liveness recovery use the worker context classification below. A first
dispatch binds the full envelope above. A continuation into a session that already attested its cwd,
Git root/common-dir and branch rebinds only the exact HEAD and the scope of this call; those
attestations carry, and restating them each time is where a hand-copied envelope drifts from the
lane it describes. Exact cwd, Git identity, branch, HEAD, and write scope remain hard-bound either
way, and an identity mismatch fast-fails on the next path-bound operation.

| worker context | Root action |
| --- | --- |
| context is an asset | Resume the same session. |
| context is debt | Start a fresh run in the same lane. |
| lane is unnecessary | `lane drop`. |

The worker's terminal reports are normal runtime output. A TDD lane reports twice: first at the
frozen Contract before any production line, naming every Contract commit SHA with its exact red
command and observed red reason plus the exact clean SHA and tree it stopped at, and again at
lane-ready with the green result, changed and protected paths, and final exact clean SHA. Root
proves the Contract state and admits implementation between them; a worker does not cross that stop
on its own judgement that the Contract looks complete. A direct lane reports once at lane-ready,
naming the frozen Contract pointer, changed and protected paths, direct validation
commands/results, and final exact clean SHA. Root proves the public process-terminal result and Git
facts at every stop; no external worker artifact is required.

## Authority

Root owns status, collection, acceptance, landing, report, removal, and recovery.
