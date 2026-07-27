# Orchestrate — Codex runtime binding

Codex uses native role agents and native continuation. This adapter does not emulate another
runtime. The role stream identity is exactly `<task-id>.<wave-id>.<role>` and the stable runtime
item identity is `slice-<slice-id>` with no attempt detail. After restart or compaction, recover
position from the Git/task plan; consume a ready SHA only after the runtime task is completed.

Use native messaging, follow-up, continuation, and wake when exposed. A successor keeps the role
identity but starts fresh when the Contract SHA, frozen spec, base, provider, or liveness state has
changed. One writer owns each role stream. A blocked role reports through the native hold/message
path with evidence.

A full review may use the integration worktree when the reviewer has a provable read-only
capability. Otherwise the shared detached fallback is the source. See the shared ReviewGate for
exact SHA, path, branch, HEAD, and clean-state bracket checks.

Every dispatch names the exact cwd, base or subject SHA, write scope, immutable paths, user dirt,
and focused commands. The terminal output carries exact focused test command(s), observed role
result(s), Slice, and exact SHA. A terminal `slice-ready` with the full SHA ends the role turn
immediately. Git/task-plan recovery is the only durable position; runtime state is not.
