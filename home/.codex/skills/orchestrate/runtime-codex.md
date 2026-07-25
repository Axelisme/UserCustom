# Orchestrate — Codex runtime binding

Codex uses the native tools exposed by the current session. This document maps v123 roles
without emulating runtime state.

## Dual-role native agents and terminal handoff

Run two persistent native role agents per Wave: `wave-oracle` authors the public Interface,
contract tests, fixtures, and intended red Contract; `wave-implementer` fills shared
production paths after Root merges the exact Contract SHA. Native messaging, follow-up, and
continuation are used when available in v1 and v2. The role stream identity is exactly
`<task-id>.<wave-id>.<role>`, and the stable runtime item identity is `slice-<slice-id>`;
it has no attempt detail. After a restart or compaction, native continuation coexists with
Git/task-plan recovery: recover position from the task plan and Git refs/history. Root consumes a ready
SHA only after the corresponding runtime task has completed.

A terminal `slice-ready` message carries Slice and a full exact SHA; the role then
immediately ends its turn. In degraded v1 transport, the terminal response carries the exact commit
SHA while the commit uses Git trailers `Wave: <wave-id>`, `Slice: <slice-id>`, and `Role: <role>` (oracle or implementation).

Codex has no simulated queue. Root owns dependency depth and placement. A blocked role reports through the native hold/message path with its reason and evidence, not a
ceremony commit.

## Native generations

In v1, `spawn_agent` loads the named profile and `send_input` is notification; use
`resume_agent` for same-identity continuation. In v2, `spawn_agent` is generic and native
`send_message`/`followup_task` provide messaging and continuation. A successor in the same role stream keeps the identity but not necessarily the context: continue the session while the frozen input is unchanged, and start a fresh one — same identity, optionally a different model — once the Contract SHA, frozen spec, or base has moved, or after a provider or liveness failure. A stale session replays conclusions it drew about an input that no longer exists. One writer per role stream either way. `wait_agent` is the event
wait in either generation. Identify the observed tool generation at session start and do not
invent a missing capability.

## Profile bootstrap and safety

At first use, verify the role profile instructions are active. Every dispatch names exact
cwd, frozen base or subject SHA, write scope, pre-existing dirt, required evidence, and stop
conditions. A dispatch also names the exact gate commands with the environment they require, the Oracle-declared immutable paths, and the production paths this role may write. Workers do not create child workers or claim repository authority. Root proves
clean Git state before consuming a handoff.

## Acceptance

Dev-flow runs simplify, canonical tests, and one clean-detached exact-SHA code-review. A
behavior correction returns to Oracle then Implementation in the same Wave; a quality
correction returns to Implementation. Repository integration requires current user authority
and is outside the workflow CLI.
