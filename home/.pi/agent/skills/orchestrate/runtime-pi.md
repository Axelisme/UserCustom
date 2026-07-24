# Orchestrate — Pi runtime binding

Pi's native `subagent` tool and the generic [pi-subagents pipeline lifecycle](https://github.com/badlogic/pi-subagents#pipeline-lifecycle)
are authoritative for attach, restore, resume, and close. This binding maps v119 role
streams and keeps Git/task contracts at Root. The role stream identity is exactly
`<task-id>.<wave-id>.<role>`, and the stable runtime item identity is `slice-<slice-id>`;
it has no attempt detail. After a restart or compaction, native continuation coexists with
Git/task-plan recovery: recover position from the task plan and Git refs/history. Root
consumes a ready SHA only after the corresponding runtime task has completed.

## Dual-role generic pipelines and terminal handoff

Root creates and attaches the wave-oracle pipeline from the real C0 task. Root lazily
creates and attaches the wave-implementer pipeline from the first real Implementation task
after the first Contract merge. Root controls dependency depth and queue placement. Ready commits use Git trailers `Wave: <wave-id>`, `Slice: <slice-id>`, and the role-specific `Role: oracle` or `Role: implementation`.

After emitting the terminal `slice-ready` handoff, the role immediately ends its turn and
makes no further worktree changes. The handoff carries Slice and the full exact SHA. After

## Profile routing

Use the shipped `wave-oracle` and `wave-implementer` profiles for this frozen workflow and
Pi builtins for unrelated delegation. Independent work defaults to `async: true`; same-role
continuation uses native `steer` or `resume` according to observed state. Every dispatch
names cwd, explicit base or subject SHA, scope, pre-existing dirt, evidence, and stop
conditions. Do not claim Git or repository authority from a runtime preset.

## Activation and leases

Inspect native status before continuing an identity when state is uncertain. A completion
wake or status result is evidence; a timeout alone is not a verdict. Runtime lifecycle
semantics remain in the linked pi-subagents pipeline lifecycle authority.

## Runtime budgets

Keep runtime spawn, turn, tool, and wall-clock limits distinct. Do not impose arbitrary
count budgets on a mutation-capable role expected to commit and hand off. A wall-clock cap is
process safety and requires inspection on expiry, not a delivery verdict.

## Blocked checkpoint contract

If Implementation is blocked by a contradictory Contract, it creates a clean Git checkpoint commit carrying `Wave: <wave-id>`, `Slice: <slice-id>`, and `Role: implementation-checkpoint`. Terminal blocked output/hold includes the concrete counterexample and exact checkpoint SHA; ready and terminal contracts remain unchanged.

## Milestones and flow control

The role commit is the durable milestone. Root consumes only a clean exact SHA and checks
contract-surface immutability. Native hold/message is the blocker path; a concrete
counterexample returns to Oracle. No runtime state file substitutes for Git.
