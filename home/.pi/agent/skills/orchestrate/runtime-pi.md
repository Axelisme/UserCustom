# Orchestrate — Pi runtime binding

Current Pi tool availability is authoritative. This binding translates the orchestrate
control loop onto Pi's subagent state machine; do not import Codex mailbox or Claude task
semantics. Use the native `subagent` tool only after `subagent({ action: "list" })` confirms
that the requested agent is executable and not disabled. User-scope Pi agents live in
`~/.pi/agent/agents/*.md` and project agents in `.pi/agents/*.md`; these profiles are
Markdown frontmatter plus body prompts, not Codex TOML. The always-resident orchestration
iron rules are installed through `~/.pi/agent/APPEND_SYSTEM.md`.

## Tool and profile binding

| capability | Pi binding |
|---|---|
| spawn | `subagent({ agent, task, ... })`; use `async: true` only when the work can proceed independently |
| fanout / chains | top-level `tasks` or `chain` forms; keep one writer per active worktree |
| same-identity continuation | `steer` for a live eligible async child; `resume` for paused/completed/failed children that Pi can revive |
| child request/reply | supervisor/intercom channels are for child-initiated requests and parent replies; proactive guidance uses `steer`/`resume`, not notification |
| interrupt / stop | `subagent({ action: "interrupt" | "stop", id })`; stopped runs are non-resumable |
| wait/status | Pi completion wakeups, `subagent_wait` only when this turn must receive results, and event-driven `subagent({ action: "status", id })` inspection |
| durable lane isolation | create lanes with `orchestrate.py lane create` and dispatch the child with that worktree as `cwd`; do not use Pi `worktree: true` for orchestrate writer lanes |

Pi builtin role agents inherit the parent model unless overridden in agent files,
`settings.subagents.agentOverrides`, or the run. Custom user agents with the same name shadow
builtins. A long direct contract travels as a plain file whose absolute path the dispatch
names.

Every dispatch carries an explicit handoff baseline rather than asking a fresh child to infer
ownership from its initial `git status`: frozen base or subject SHA, exact `cwd` and write
scope, pre-existing user-owned dirty paths, root-owned concurrent artifacts, and the required
terminal envelope/artifact path. Name an existing durable task-plan or contract path when one
exists; do not create one only to satisfy this transport rule. A child treats listed
concurrent artifacts as expected and reports only unlisted scope collisions. After
compaction, root re-reads the skill and any live durable plan, then refreshes this baseline
before the next dispatch; the compaction summary is not a handoff contract.

## Activation and leases

Treat Pi children as a small state machine with run states `queued`, `running`, `complete`,
`failed`, `paused`, and `stopped`; `needs_attention` / `active_long_running` are activity
signals, not terminal states. A message or reply associated with a `complete` or `stopped`
child is not work in progress. Before continuing the same identity, inspect status when the
state is not known; use the continuation binding above, or declare `needs_decision` if
continuity is not available. This rule exists only to avoid false idle waits and accidental
identity changes.

Long-running dispatches need an observable lease in commits, item envelopes, terminal
outputs, or artifacts. Wall-clock limits such as `maxRuntimeMs` are outer runtime safety caps:
expiry is an error to inspect and recover from, not proof that a writer is stale or safe to
replace. A wait timeout by itself is healthy silence; it becomes a liveness event only when
Pi reports failure/lost attention, the child ends without the required terminal evidence, or
the declared observable lease is exceeded. Do not add periodic progress pings.

Pi top-level `worktree: true` is patch-oriented ephemeral isolation: pi-subagents may clean
up the temporary worktree and branch after the child finishes. It is useful for disposable
non-pipelined experiments, not for orchestrate writer lanes that require durable
`agent/<task>/<lane>` branches, seam-ready SHAs, exact-SHA review, and `collect`.

## Cleanup lease check

Before any `cleanup` operation, inspect the Pi fleet with `subagent({ action: "list" })` and
exclude every active/paused child whose declared cwd lease is the target worktree or a
worktree swept by the command. If an active/paused cwd lease cannot be excluded, do not clean
up. Core `reconcile`, `wave status`, and cleanup output prove Git/data safety only; they do
not inspect a Pi fleet. Runtime lease safety is unchecked (`runtime_lease_safety:
"unchecked"`). In particular, `git_safe_to_remove` is the explicit Git-only projection;
`safe_to_remove` remains an equal compatibility alias for this release.

`steer` delivers guidance; it does not preempt active tools. For cancellation, use `interrupt`;
do not treat steering as cancellation.

## Milestones and flow control

The envelope schema, delivery rule, and liveness triggers live in
[coordination](references/coordination.md). Pi async runs produce status/artifact paths;
root binds harvest and review conclusions to exact Git SHAs, not to child summaries.

- Spawn independent children before waiting; do not contact running assignees for progress
  and do not poll on a fixed interval.
- In an interactive Pi session, normally return control after starting async work and let Pi
  wake the session; use `subagent_wait` only for run-to-completion requests where this turn
  must include the result.
- Use fresh-context read-only reviewers for independent review. Use forked context only when
  inherited session state is the subject of review. On the fresh launch, set `artifacts: false`
  for a child whose `cwd` is the clean detached review worktree, or place its artifact/session
  directory outside that worktree; Pi's default `.pi-subagents/` output would otherwise dirty
  the evidence tree. Do not `resume` that child when checkout cleanliness depends on
  `artifacts: false`: current Pi resume may recreate cwd-local artifacts instead of preserving
  the launch setting. Start a fresh exact-SHA reviewer instead. If artifacts unexpectedly
  appear during a live run, stop the runner before cleanup; deleting its output directory
  mid-run can make terminal result publication fail.
- Ordinary child subagents must not spawn subagents. If a delegated fanout child is ever
  used, its prompt and tool allowlist must explicitly grant and bound that responsibility.

## Capability boundaries

Pi subagent management settings are not proof of runtime capability; the resolved tool list
and `subagent({ action: "list" })` output are. Role switching is a new child/profile and
never makes an implementer an independent reviewer. Read-only review remains a behavioral
contract even when a profile has write-capable tools for temporary reproducers or artifacts.
If a required capability is unavailable, return `needs_decision` rather than inventing an
adapter.
