# Orchestrate — Pi runtime binding

Pi's native subagent tool has its own `PipelineManager` and an explicit **pipeline capability**.
The linked pi-subagents lifecycle supplies `attach`, `enqueue`, `resume`, `close`, and wake
behavior. Pipeline declarations are runtime metadata, not workflow policy. The role stream identity
is exactly `<task-id>.<wave-id>.<role>` and the stable runtime item identity is `slice-<slice-id>`
with no attempt detail. Git/task-plan evidence recovers position after restart or compaction; use Git to recover
position when runtime state is ambiguous, then re-enqueue from the recovered position.

After the exact Contract merge, Root lazily declares `wave-oracle` and `wave-implementer` items,
attaches or enqueues the real task, and resumes the same identity when the frozen input is
unchanged. After a terminal `slice-ready` carrying Slice and the full exact SHA, the role ends
immediately; Root consumes the ready SHA only after the runtime task is completed and closes the
runtime item after consuming a clean SHA. A completion wake is evidence; a timeout is not a
verdict.

Pi's reviewer tools `read,bash` do not prove filesystem read-only capability, so full review uses
the shared detached fallback unless a stronger capability is explicitly verifiable. See the shared
ReviewGate for exact SHA, same path, branch, HEAD, and clean-state bracket checks. Runtime
frontmatter is the only eligibility surface: Pi wave profiles carry `pipeline: true`; other
runtime profiles do not.

Every dispatch names cwd, base or subject SHA, scope, immutable paths, user dirt, evidence, stop
conditions, and exact commands. Runtime lifecycle ends with `close`; Git remains the authority for
identity, commits, refs, and recovery.
