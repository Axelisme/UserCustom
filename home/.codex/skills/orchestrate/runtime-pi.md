# Orchestrate — Pi runtime binding

Pi dispatches one native `lane-worker` subagent for the lane identity `<task-id>.<lane-id>`.
The dispatch carries the frozen objective, canonical lane cwd, expected Git root/common-dir,
branch, base or subject SHA, write scope, immutable paths, primary-checkout dirt snapshot,
focused commands, evidence, and stop conditions.

The worker's first action is to change into the canonical cwd and attest `pwd -P`, Git identity,
and clean state. Pi may provide a typed cwd, but the shared worker contract does not depend on
that capability: every later operation is path-bound and a mismatch is terminal. Root verifies
lane identity and primary dirt immediately before collect; after the lane worktree is removed,
Root verifies the collected SHA and that primary dirt is unchanged.

Use Pi's native subagent lifecycle and continuation only while the frozen input and lane identity
remain unchanged. A semantic Contract, observable behavior, public Interface, provider, liveness,
or cwd change requires a fresh dispatch and Root re-admission. The terminal lane-ready handoff
identifies every Contract commit SHA with its exact red evidence, plus the final clean SHA; Root
owns collect, candidate, landing, and recovery.
