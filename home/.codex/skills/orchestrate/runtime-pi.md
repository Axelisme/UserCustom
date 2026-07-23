# Orchestrate — Pi runtime binding

Pi's native `subagent` tool and the generic [pi-subagents pipeline lifecycle](https://github.com/badlogic/pi-subagents#pipeline-lifecycle)
are authoritative for attach, restore, resume, and close. This binding only maps the v119
roles and keeps Git/task contracts at Root.

## Dual-role generic pipelines and terminal handoff

Map `wave-oracle` to a generic pipeline beginning with its real C0 task. Create the
the Implementation pipeline is lazy: create `wave-implementer` from its first real task after the first Contract merge.
A terminal `slice-ready` handoff carries Slice and exact SHA; it is followed by immediately end this turn. Root controls dependency depth and queue placement. After restart or
compaction, the task plan and Git refs/history recover position, not a queue or runtime
state file.

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

## Milestones and flow control

The role commit is the durable milestone. Root consumes only a clean exact SHA and checks
contract-surface immutability. Native hold/message is the blocker path; a concrete
counterexample returns to Oracle. No runtime state file substitutes for Git.
