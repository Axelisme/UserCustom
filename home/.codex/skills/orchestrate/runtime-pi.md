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
builtins. For orchestrate roles use the Sol family at `low` through `high` or the Luna family
at `medium` through `xhigh`; do not route them to Terra. `wave-reviewer` defaults to Sol
`low`; launch critical checkpoint and authority-publication reviews with an explicit Sol
`high` override, and keep long implementation work on Luna. Model depth never changes
review depth or grants authority.
A long direct contract travels as a plain file whose absolute path the dispatch names.

Every dispatch carries an explicit handoff baseline rather than asking a fresh child to infer
ownership from its initial `git status`: frozen base or subject SHA, exact `cwd` and write
scope, pre-existing user-owned dirty paths, root-owned concurrent artifacts, and the required
terminal envelope/artifact path. Name an existing durable task-plan or contract path when one
exists; do not create one only to satisfy this transport rule. A child treats listed
concurrent artifacts as expected and reports only unlisted scope collisions. After
compaction, root re-reads the skill and any live durable plan, then refreshes this baseline
before the next dispatch; the compaction summary is not a handoff contract.

## Pipeline adoption

Pi recommends pipeline attachment for wave roles: root ordinary-launches then attaches by
`runId`, even for one ready item. First verify the loaded runtime advertises `pipeline`, then
queue the eligible ready set. Root retains policy authority over
scope, dependencies, findings, queue placement, hold/release, and acceptance; runtime treats
tasks as opaque. Keep one writer pipeline per lane and one latest cumulative reviewer
frontier; ordinary findings continue, while only review-authority failure holds successors.
`integration-reviewer` stays fresh and one-shot. If capability or source lifecycle is
unavailable, name any fallback reason and use the ordinary one-deep fallback.

## Profile routing and launch modes

Use orchestrate-specific user profiles for frozen pipeline work (`wave-implementer`,
`wave-reviewer`, and `integration-reviewer`); use Pi builtins for generic delegation that
has no frozen orchestrate seam. A child that can independently reach the next decision or
milestone boundary defaults to `async: true`. Wave implementation and review, integration
review, wave-ahead planning, and reconnaissance therefore default to fresh async launches
(the same identity may continue through `steer` or `resume` when its lease allows it).

Root-serial Git and authority actions — collect, integrate, release, and landing — are root's
control flow and are never dispatched as children. Use foreground only for a short query that
immediately blocks the root's next decision; root mediation for a longer question works via
supervisor asks and replies rather than a child taking root authority.

Foreground detach is a supervisor-wait transport state: the child is neither paused nor
complete, and root cannot treat it as a result until a completion wake or status says so. It
is unrelated to a Git detached HEAD. Root creates and proves each clean detached exact-SHA
review job; the initial reviewer is fresh with `artifacts: false` and an external receipt.
Every frontier or finding closure gets a new immutable job/worktree. Continue the same
reviewer through its pipeline when available; otherwise start a fresh reviewer because an
ordinary resume cannot retarget the persisted cwd. Unreadable placement evidence or
cwd/subject drift fails closed.

## Recommended launch presets

These are orchestrate launch recipes, not a `preset` tool field. The Pi
`wave-implementer`, `wave-reviewer`, and `integration-reviewer` profiles carry the stable
`defaultContext: fresh`, `async: true`, and orchestrate-owned acceptance defaults. The
recipes below show the remaining placement and delivery choices that must be visible at the
call site. Do not apply these presets to generic Pi delegation: generic agents retain their
runtime-inferred acceptance and launch behavior.

Orchestrate disables the generic Pi acceptance report for its dedicated profiles because
Git SHAs, frozen gates, terminal envelopes, canonical receipts, the findings ledger, and
root integration are the authoritative acceptance surface. This does not weaken process exit,
completion guards, exact-SHA review, or required gates. Every dispatch still names cwd,
frozen base or subject SHA, write or review scope, pre-existing dirt, required evidence, and
stop conditions; no preset may grant Git or landing authority.

### `lane-writer`

Use for a `wave-implementer` in a durable orchestrate lane. The profile already supplies the
fresh async launch and external acceptance contract; the call supplies the lane lease and
keeps runtime artifacts out of the Git-evidenced worktree:

```json
{
  "agent": "wave-implementer",
  "cwd": "/absolute/orchestrate/lane",
  "task": "<frozen contract and handoff baseline>",
  "artifacts": false,
  "progress": true
}
```

Do not add `turnBudget`, a hard `toolBudget`, Pi `worktree: true`, or an arbitrary wall-clock
completion deadline. A required `timeoutMs` remains an outer process-safety cap sized beyond
the observable milestone lease, never a delivery budget.

### `exact-sha-review`

Use for an initial `wave-reviewer` or `integration-reviewer` launch in the root-created clean
detached checkout:

```json
{
  "agent": "wave-reviewer",
  "cwd": "/absolute/clean/detached-review-checkout",
  "task": "<exact subject/base, risks, and external receipt path>",
  "artifacts": false
}
```

The task names one canonical receipt path outside the checkout. The reviewer writes and
validates that file directly; do not point runtime `output` at the canonical receipt path,
because runtime final-output persistence is a different transport. Critical depth changes
the explicit model/thinking override, not this placement contract. A same-identity continuation is not a fresh launch preset: enqueue the root-created immutable
review job on the reviewer pipeline. Without that capability, use a fresh reviewer; never
retarget an ordinary resume's persisted cwd.

### `read-only-evidence`

Use for orchestrate reconnaissance or external research whose artifact root will inspect
before making a decision. The output path must be outside every writer/reviewer checkout:

```json
{
  "agent": "<read-only agent>",
  "cwd": "/absolute/read-only/source",
  "task": "<bounded evidence question and citation contract>",
  "async": true,
  "context": "fresh",
  "artifacts": false,
  "output": "/absolute/external/evidence.md",
  "outputMode": "file-only",
  "acceptance": {
    "level": "none",
    "reason": "Root will inspect the cited evidence artifact before using it."
  }
}
```

This preset makes the named evidence file authoritative and requires root to read it; a
successful runtime result alone is not acceptance. For a generic non-orchestrate read-only
query, omit this acceptance override and let Pi's normal `auto` inference apply.

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

## Runtime budgets

Pi exposes independent limits that must not be collapsed into one "budget": the session
spawn budget limits new launches; `turnBudget` limits assistant turns; `toolBudget` limits
child tool calls; `timeoutMs` / `maxRuntimeMs` is a wall-clock outer cap. Inspect the terminal
status to classify a failure: `turnBudget.outcome == "exceeded"`,
`toolBudget.outcome == "hard-blocked"`, or `timedOut == true`. Spawn-budget exhaustion never
explains a child that was already running.

Long runs are normal in orchestrate. Do not set `turnBudget` or a hard `toolBudget` on a
mutation-capable implementer, finding-fix continuation, reviewer that may write temporary
reproducers, or a wave identity expected to continue across several milestones. Counts of
turns and tools are not safe delivery boundaries; in particular, `toolBudget.block: "*"`
can strand a writer before commit, validation, or its terminal envelope. Omit those count
budgets rather than choosing an arbitrarily large number. Explicitly bounded read-only
reconnaissance may still use them when partial output is an acceptable stop.

A wall-clock cap is process safety only. When one is required, leave enough margin beyond the
observable milestone lease; expiry fires liveness inspection and same-identity recovery, not
a verdict that the work failed, the writer is stale, or its worktree is safe to replace. Keep
the parent session spawn budget unlimited (`maxSubagentSpawnsPerSession` unset or `0`) for an
open-ended wave pipeline, and bound simultaneous cost with `globalConcurrencyLimit`, ready
work, one writer per lane, and the review depth ladder. If a managed environment enforces a
spawn cap, exhaustion is a control-plane blocker: never skip review or finding closure, or
change identity merely to fit the cap. Compaction does not reset it; a new parent session
does, and an in-session grant requires current user confirmation.

## Cleanup lease check

Before any `cleanup` operation, inspect the Pi fleet with
`subagent({ action: "status", view: "fleet" })` and
exclude every active/paused child whose declared cwd lease is the target worktree or a
worktree swept by the command. If an active/paused cwd lease cannot be excluded, do not clean
up. Core `reconcile`, `wave status`, and cleanup output prove Git/data safety only; they do
not inspect a Pi fleet. Runtime lease safety is unchecked (`runtime_lease_safety:
"unchecked"`). In particular, `git_safe_to_remove` is the explicit Git-only projection;
`safe_to_remove` remains an equal compatibility alias for this release.

`steer` delivers guidance; it does not preempt active tools. For cancellation, use `interrupt`;
do not treat steering as cancellation.

## Pi goal yield policy

In an active interactive `pi-goal` session, root may call `yield_goal({ reason })` only when
all three conditions hold: no blocking tool remains in progress, no synchronous autonomous
root work can make progress, and the next prerequisite requires a future agent turn. This
includes an async child or provider completion, a future ordinary user reply, or another
external result. Do not yield while autonomous work remains.

A blocking `ask_user_question` is an in-run wait for an answer, so do not yield while it is
waiting. `yield_goal` is terminal: provide a concise visible reason and make it the sole
final tool action; do not emit another wait or speculative work afterward. Retain
`subagent_wait` for explicit run-to-completion or headless cases. Never claim that Enter
wakes `subagent_wait`.

Yield is Pi-specific and does not change generic runtime defaults or `pi-subagents` tool
semantics.

## Cumulative review scheduling

Review is not mandatory per slice. When a same-surface `wave-reviewer` is idle, dispatch the
currently eligible cumulative frontier immediately; when it is busy, accumulate that
frontier for the next follow-up rather than spawning a second same-surface identity. Keep
the review depth ladder unchanged, and reserve `integration-reviewer` for the wave-boundary
contract-parity and emergent-risk review on the integrated tree.

## Milestones and flow control

The envelope schema, delivery rule, and liveness triggers live in
[coordination](references/coordination.md). Pi async runs produce status/artifact paths;
root binds harvest and review conclusions to exact Git SHAs, not to child summaries.

- Spawn independent children before waiting; do not contact running assignees for progress
  and do not poll on a fixed interval.
- In an interactive Pi session, normally return control after starting async work and let Pi
  wake the session; use `subagent_wait` only for run-to-completion requests where this turn
  must include the result.
- Use fresh-context read-only reviewers for independent review. Use fork only when inherited
  session state is the subject. For every clean detached review cwd, set `artifacts: false` or
  place artifacts outside it; defaults can dirty the evidence tree. Root creates a new
  immutable checkout per frontier; a reviewer
  pipeline may carry the new cwd, while ordinary fallback uses a fresh reviewer. Re-prove HEAD
  and cleanliness before using the verdict. If artifacts appear during a live run, stop it
  and observe terminal state before cleanup; never delete a live runner's output directory. Do not `resume` that child after unsafe placement.
- Ordinary child subagents must not spawn subagents. If a delegated fanout child is ever
  used, its prompt and tool allowlist must explicitly grant and bound that responsibility.

## Capability boundaries

Pi subagent management settings are not proof of runtime capability; the resolved tool list
and `subagent({ action: "list" })` output are. Role switching is a new child/profile and
never makes an implementer an independent reviewer. Read-only review remains a behavioral
contract even when a profile has write-capable tools for temporary reproducers or artifacts.
If a required capability is unavailable, return `needs_decision` rather than inventing an
adapter.
