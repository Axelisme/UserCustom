# Orchestrate — Codex runtime binding

Codex dispatches one native `lane-worker` call for the lane identity `<task-id>.<lane-id>`.
The dispatch carries the frozen objective, canonical lane cwd, expected Git root/common-dir,
branch, base or subject SHA, write scope, immutable paths, primary-checkout dirt snapshot,
focused commands, evidence, and stop conditions.

The worker first changes into the canonical cwd and attests `pwd -P`, Git identity, and clean
state. This is a fail-closed worker contract, not a typed provider cwd guarantee. Every later
operation is path-bound. Root verifies identity and primary dirt before `lane check`, reviews the
Contract-first commits, and alone invokes `lane sync` or collection. The worker resolves and
commits a sync conflict in its lane; shared integration is never the conflict workspace.

After all collects and shared gates, Root invokes `acceptance start` for the exact integration
subject and records the decision with `acceptance result`. Only a passing exact snapshot becomes
accepted. A persistence advance routes through an admitted writer lane and `integration
reconcile`; after collection the exact snapshot must be accepted again before it can become
landed. `timing pause` and `timing resume` bracket external waits without granting lifecycle
authority.

Use native continuation only while the frozen input, provider, cwd, and lane identity remain
unchanged. A semantic Contract, observable behavior, public Interface, liveness, or identity
change requires fresh dispatch and Root re-admission. The terminal lane-ready handoff identifies
every Contract commit SHA with exact red evidence and the final clean SHA. Root owns status,
collection, acceptance, landing, report, removal, and recovery.
