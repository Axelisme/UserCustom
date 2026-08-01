# Orchestrate — runtime-neutral dispatch contract

Before dispatch Root runs `lane check --task-id <task> --lane-id <lane>`, which must exit 0, and reads `status
--task-id <task>` to record the exact lane tip SHA. That SHA is the expected base carried in the
dispatch together with the frozen objective, canonical lane cwd, expected Git root/common-dir, branch,
write scope, immutable paths, primary-checkout dirt snapshot, focused commands, evidence, and stop
conditions. When the task has a durable record, the dispatch also carries its `Envelope` and any
`Standing orders`: the worker cannot honour a boundary the user froze, or an instruction the user
issued, that never reached it.

Working inside the canonical lane cwd is the only hard contract; the agent, its skills, and its context
mode are recommendations. The worker reports the cwd, Git root/common-dir, branch, HEAD, and clean state
it observes, and Root judges whether they match the admitted lane. The worker runs no mechanical
self-check and does not block itself. Every later operation is path-bound. Root verifies identity and
primary dirt before `lane check`, reviews the Contract-first commits, and alone invokes `lane sync` or
collection. The worker resolves and commits a sync conflict in its lane; shared integration is never the
conflict workspace.

After all collects and shared gates, Root invokes `acceptance start` for the exact integration subject
and records the decision with `acceptance result`. Only a passing exact snapshot becomes accepted. A
persistence advance routes through an admitted writer lane and `integration reconcile`; after collection
the exact snapshot must be accepted again before it can become landed. `timing pause` and `timing
resume` bracket external waits without granting lifecycle authority.

Continuation is admissible only while the frozen Contract, provider, cwd, and lane identity all remain
unchanged. A semantic Contract, observable behavior, public Interface, liveness, or identity change
requires fresh dispatch and Root re-admission.

The terminal lane-ready handoff identifies every Contract commit SHA with exact red evidence and the
final clean SHA.

## Authority

Root owns status, collection, acceptance, landing, report, removal, and recovery.
