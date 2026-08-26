# Collab — Pi runtime

Verified against `pi-subagents` 0.56.0. Check the installed package before trusting runtime-specific
placement details; Collab's core guidance remains runtime-neutral.

## Routing

Read only the section named for the step you are taking; every section after Composed delegation and
Typed results states its own enabling condition.

- **Managed lane environment** — after canonical lane creation succeeds and the repository declares
  a worktree bootstrap: establish its dispatch precondition and lane-lifetime ownership.
- **Composed delegation** — the canonical branch: invoke `collab_run_reviewed_lane` for one
  shared lane, including bounded corrections.
- **Typed results** — the typed terminal outcomes returned by the reviewed-lane workflow.
- **Post-launch** — after launching an asynchronous workflow: the ordinary return-or-yield step
  that lets completion wake the session.
- **Run control** — only when a run is interrupted or needs status, steering, or stopping.
- **Placement** — only when the canonical lane placement does not fit the chosen shape.
- **Collection** — only after the Orchestrator judges the reviewed lane and chooses collection.
- **Operations** — only when selecting which `collab_*` tool carries out a Collab step.

## Managed lane environment

Read this section after `collab_lane_create` succeeds when the repository declares a worktree
bootstrap. Apply that repository-owned contract to the exact managed lane before invoking
`collab_run_reviewed_lane`. Successful bootstrap and presence of the ordinary-path environment are
preconditions for reviewed dispatch; if either is observed to fail, report `BLOCKED`, do not invoke
the reviewed-lane tool, and do not discover or create a fallback environment.

After the precondition succeeds, roles consume the provisioned environment through their exact
dispatched execution parameters without syncing or provisioning it. The reviewed-lane tool retains
its existing composition responsibility and gains no provisioning behavior or runtime-specific
parameter. Keep the runtime as lane-owned state through implementation, correction, review, and
owner-decision waits. Existing `collab_lane_collect` or `collab_lane_drop` retirement removes it with
the lane; no separate runtime cleanup operation is introduced.

Follow this canonical positive path without speculative guards or negative probes. If a concrete
workflow observation exposes environment mis-selection, return it to the Orchestrator for a separate
control-strength decision before adding enforcement.

## Composed delegation

For delegated closed work — bounded brief, delegated Acceptance criteria, placement, mutation
authority, and escalation boundary all closed — invoke the registered
`collab_run_reviewed_lane` tool. It is the canonical and only accepted Pi composition path for a
worker, reviewer, and bounded correction over one Collab-managed lane. The tool uses the configured
`collab-implementer` and `collab-acceptor` profiles. The Orchestrator supplies an explicit finite
`correction_budget`: initial implementation does not consume it, each `BLOCKED → writer correction`
transition consumes one, and exhausting it is a terminal seam that returns to the Orchestrator
without selecting a redesign procedure. Do not use turn, tool, or usage budgets as the correction
budget.

**Profile model contract.** The selected agent profile owns its configured `model` and `thinking`.
The Orchestrator preserves both unchanged, omitting `model` and `thinking` from the outer
`subagent(...)` options and every child call. Only a current user instruction that explicitly names
an override grants authority for that launch; task difficulty, retries, and review results grant
none. This contract is satisfied only when every workflow- and child-level `model` and `thinking`
field is absent or directly authorized by that instruction.

A Collab lane is already one writable checkout with one live writer. The reviewed-lane tool keeps
the delegated worker and reviewer on that exact lane, with role-specific structured results;
corrections follow the retained-correction contract below, and rereviews carry the original review
expectations against the changed protected lane. Child run IDs remain runtime operation evidence and
appear in no terminal projection. Every branch and terminal projection reads parsed
`structuredOutput`, never free-form output text.

### Retained correction

The initial implementer and every reviewer or rereviewer are fresh children. Before spawning the
workflow, the reviewed-lane tool consumes only RPC v1
`ping.capabilities.foregroundStructuredResume`; retained correction is enabled only when that value
is an object with `version: 1` and `recoveryDescriptorVersion: 1`. Missing, false, malformed,
unsupported, or future-version values preselect the fresh correction path without package or version
inference.

When retained correction is enabled and the latest successful writer supplied a non-empty run ID, a
blocking review resumes that exact writer on the protected lane with only the latest typed blockers.
The public capability guarantees recovery of the original profile/model/tools/cwd, structured output
schema, agent and acceptance contracts, and capability ceiling. Each successful correction replaces
the target with its returned run ID. A resume rejection terminates the workflow; it is never followed
by a fresh writer in the same correction round.

The preselected fresh fallback starts exactly one compatible implementer on the current lane. Its
payload contains only the original ticket contract and exact execution parameters, the latest typed
blockers, and current lane placement; it contains no INDEX, sibling-ticket narrative, or reconstructed
task history. Correction selection does not change budget accounting: each blocked-review transition
consumes one slot, and exhausted-budget behavior is unchanged. Retained correction prompts may
request optional native `efficiencyFeedback` following the shared Collab efficiency-feedback guidance
when a concrete avoidable cost was observed; a fresh fallback receives that request only when it is
already present in the original bounded worker brief.

Supply the tool only these bounded fields: `task_id` (the task identifier), `ticket_id` (the
Dev-flow ticket identifier), `lane_id` (the existing managed lane), `worker_brief` (the bounded
implementation brief), `review_brief` (the bounded read-only acceptance brief), and
`correction_budget` (the finite correction budget). The tool declares each field's own bound and
description in its input schema, which Pi surfaces to the calling Orchestrator; this list names the
fields, not their bounds.

`worker_brief` names the ticket — the ticket owns Outcome and Acceptance — and carries only the
operational deltas a brief needs: placement, mutation authority, validation expectations, stop
conditions, and role-specific deltas, without copying the ticket's prose. `review_brief` is a ticket
pointer naming the delegated Acceptance identifiers and the acceptor's read-only scope and
authority, validation expectations, protected-lane and writer-stopped stop conditions, lifecycle
and cleanup ownership as applicable, role-specific deltas, and the optional task-boundary pointer.
The tool rejects extra fields and unbounded or empty briefs.

Terminal outcomes:

- `REVIEWED` — the worker returned `COMPLETED` and the reviewer returned `PASS`. It projects the
  latest worker's semantic validation and optional residual risks plus the reviewer's optional
  out-of-envelope findings.
- `BLOCKED` — the worker returned `BLOCKED`; it carries the worker blocker.
- `NEEDS_DECISION` — a worker or reviewer returned it; it carries why, the exact question, and any
  bounded suggestion the reviewer offered, and returns immediately to the Orchestrator.
- `CORRECTION_BUDGET_EXHAUSTED` — the reviewer still returns `BLOCKED` after the budget is spent; it
  carries the reviewer's remaining blockers. It is only a terminal seam; it does not start a
  redesign.
- `REVIEWER_RUNTIME_RECOVERY_EXHAUSTED` — the reviewer child failed with a runtime or provider
  transport error and the bounded recovery allowance was exhausted. It carries the failed phase
  (`REVIEW` or `REREVIEW`) and a bounded error summary. It is distinct from `BLOCKED`,
  `NEEDS_DECISION`, and correction-budget exhaustion and does not masquerade as a semantic outcome.

### Reviewer runtime recovery

The reviewed-lane workflow owns bounded recovery for read-only reviewer transport failures. Each
review and rereview round allows exactly two fresh replacement attempts after its initial failed
reviewer child (three attempts total per round). Every replacement runs with fresh context
(`context: "fresh"`) against the same protected lane, the same ticket expectations and review brief
as the failed round, and the same runtime-owned immutable integration baseline (`integrationTip`
and the canonical `git diff --find-renames <tip>...HEAD --` command). Recovery attempts do not
consume or reset the semantic correction budget — only a `BLOCKED` reviewer verdict followed by a
writer correction consumes that budget. Only a schema-valid structured verdict (`PASS`, `BLOCKED`,
`NEEDS_DECISION`) returned by a successful child may drive workflow branching; free-form output
text and failed-child structured-output capture artifacts remain diagnostic and never drive
branching. If the bounded allowance is exhausted, the workflow returns the typed
`REVIEWER_RUNTIME_RECOVERY_EXHAUSTED` outcome with bounded phase and error diagnostics instead of
throwing or returning an unclassified workflow failure. Writer (implementer/correction) runtime
failures are never automatically retried or resumed because the lane may contain partial
mutations; recovery is left to the Orchestrator. Profile-owned model and thinking settings remain
unchanged and the immutable review subject is never altered by recovery.

The tool returns only an asynchronous launch receipt — `workflow_id`, `async_id`, and `async_dir`.
The receipt is not Acceptance: the ordinary asynchronous workflow result must wake the session
through the Post-launch guidance, and the Orchestrator judges the typed result while the lane remains
available. Child run IDs remain runtime operation evidence; Git, the lane runtime, and the
Orchestrator own later coordination. Rereviews and collection-time reconciliation reviews use fresh
compatible children under the tool's bounded contract; correction writers use the retained-correction
selector above.

The launch fails closed before spawn when the exact managed lane, either configured profile, or the
pi-subagents Extension RPC v1 `spawn`/`asyncSpawn` capability is missing or incompatible. There is
no fallback launcher. The tool schema and launch contract add no tracing, child feedback, model,
thinking, effort, collection, landing, or push controls.

## Typed results

The reviewed-lane tool owns concrete JSON Schema objects for its worker and reviewer results; core
Collab and the profiles express the same semantics without repeating the schema. Each child finishes
through Pi's structured-output protocol instead of free-form Markdown, so formatting cannot change
control flow. The parsed child result is `structuredOutput`; free-form output never drives control
flow. Implementer launches retain Pi's v1 effects projection as optional runtime diagnostics, but
Collab never branches on mutation effects. Every schema-valid `COMPLETED` result proceeds to a fresh
reviewer even when effects are absent, empty, missing, or `not-applicable`; a schema-valid `BLOCKED`
or `NEEDS_DECISION` result can still stop without mutation. This changes no typed result field. Use
one structured result per child and do not combine it with Pi's generic acceptance report:
both default Collab profiles set `acceptance: { level: none, ... }` with a reason, and a launch needing
another acceptance policy selects it explicitly.

Worker (`collab-implementer`) — `COMPLETED` carries the behavior/Interface semantic checks actually
performed, each with `check`, `result: PASSED | FAILED`, and a concise `summary`, and may carry
`residualRisks`; operational Git and runtime checks — status, diff, diff-check, staged state,
cleanliness, ancestry, commit identity, and lifecycle — are categorically ineligible for `validation`
even when the worker runs them and receive no semantic check name or summary; each check name and
summary describes only the behavior/Interface outcome observed, never the operational command or
checkout, tree, lane, branch, commit, diff, staged, clean, ancestry, runtime, or lifecycle state it
ran against; `BLOCKED` carries
`blocker`; `NEEDS_DECISION` carries `decision: { why, question }`; every branch may also carry optional
`efficiencyFeedback` (plain string, `maxLength: 10000`, no `minLength`; empty string is valid) as
qualitative feedback for a requested efficiency investigation — not a substitute for runtime counts or
timing. `outcome` discriminates the three branches (`COMPLETED`, `BLOCKED`, `NEEDS_DECISION`); each
branch is closed to exactly its own fields plus the shared `outcome` and optional
`efficiencyFeedback`. The child's own `outputSchema` is authoritative for the exact shape; this
paragraph names the fields, not their JSON Schema encoding.

Reviewer (`collab-acceptor`) — `PASS` needs no filler; `BLOCKED` carries `blockers`, each with its
`where`, `why`, bounded `howToFix`, and a required `trigger` — the concrete input or call sequence
that produces the defect, and the existing entry point it reaches from; `NEEDS_DECISION` carries
`decision: { why, question }`; any verdict may add optional `outOfEnvelopeFindings`, each with
`location` and `evidence`; every verdict branch may also carry optional `efficiencyFeedback` (plain
string, `maxLength: 10000`, no `minLength`; empty string is valid) as qualitative feedback for a
requested efficiency investigation — not a substitute for runtime counts or timing. `verdict`
discriminates the three branches (`PASS`, `BLOCKED`, `NEEDS_DECISION`); each branch is closed to
exactly its own fields plus the shared `verdict`, optional `outOfEnvelopeFindings`, and optional
`efficiencyFeedback`. The child's own `outputSchema` is authoritative for the exact shape; this
paragraph names the fields, not their JSON Schema encoding.

`efficiencyFeedback` is an optional plain string on every worker outcome (`COMPLETED`, `BLOCKED`,
`NEEDS_DECISION`) and every reviewer verdict (`PASS`, `BLOCKED`, `NEEDS_DECISION`): `maxLength: 10000`,
no `minLength`, no nested format/taxonomy/score, and an explicitly present empty string is valid and
produces an artifact. Omit the field to produce no artifact. The Orchestrator requests it in
ordinary worker/reviewer dispatch content whenever efficiency diagnosis is useful — not as a runtime
parameter and not restricted to an explicit user reminder. A request never makes it mandatory; omission
or empty is never a runtime or acceptance failure and never drives workflow branching, mutation
enforcement, review verdict, correction budget, or composed terminal projection. It is not copied into
`.collab_op/lane_loop_report` or lifecycle `telemetry.jsonl` and does not reintroduce a lane sidecar or
stdout probe. Acceptor child `PASS` is the child’s own acceptance verdict; the composed workflow
terminal `REVIEWED` projects the latest writer’s validation plus optional reviewer findings and is
not the same as child `PASS`.

## Post-launch

Read this section after launching an asynchronous workflow, when the Orchestrator continues
independent work before completion wakes the session.

Launch subagents asynchronously so the Orchestrator can continue independent work. In an interactive
session, return control or use the active goal's yield mechanism and let completion wake the session.
Use `subagent_wait` only when the current request must finish in the same turn; waiting does not make
a child more authoritative.

After the workflow reaches a terminal handoff, if the worker dispatch granted authority to toggle named Acceptance claims in the assigned `ticket.md`, reread that exact ticket before final Acceptance judgement, Resolution, lifecycle state, or task-progress reconciliation. Read only the assigned ticket; do not rescan the task or sibling tickets. This adds no post-wake `collab_status` read and no generic record-edit reread; completion processing, collection selection, and ticket mutation ownership remain unchanged.

## Run control

Read this section only when a run is interrupted or needs status, steering, or stopping.

Inspect a run with `subagent({ action: "status", id })`. Guide a live top-level run with
`action: "steer"` and stop it with `action: "stop"`. Turn, tool, runtime, and usage budgets do not
replace the correction budget. After a writing run is interrupted, inspect its changed files and
commit state before choosing the next owner.

## Placement

Read this section only when the canonical lane placement does not fit the chosen shape: discovering
live profiles, selecting another compatible profile, a fork context, managed isolation around a
non-Collab checkout, or parallel writers.

Discover the live profiles with `subagent({ action: "list" })`, then select only an executable,
non-disabled agent. The canonical reviewed-lane placement is `collab_run_reviewed_lane`, which
preflights the configured profiles and exact lane before asking pi-subagents to launch. A different
shape requires an explicit Orchestrator choice and its own supported placement mechanism; do not
replace the canonical tool with a handwritten worker/reviewer loop. Keep execution and management
separate: status, steering, stopping, and other controls use their management action without
execution fields.

Use `context: "fresh"` for independent review. Use `context: "fork"` only when the child should
inherit the persisted parent conversation; it is not a filtered review context. A profile's configured
default applies when the call omits context.

`worktree: true` remains for a writing child when the source checkout is clean and the Orchestrator
deliberately wants managed isolation around a non-Collab checkout. Parallel reviewers may remain
read-only; parallel writers each need their own writable checkout.

## Collection

Read this section only after the Orchestrator judges the reviewed lane and chooses collection.

`lane_collect`'s own stale-lane behavior is the default collection path after the Orchestrator
judges the reviewed lane. A `collected` result completes collection. A `reconciled` result stops
before collection: launch a fresh typed reviewer against the reconciled protected current lane, have
the Orchestrator judge again, and only then retry collection. A `conflicted` result returns to the
Orchestrator. `lane_reconcile` remains available but is not an extra default pre-step.

```javascript
// lane_collect returned "reconciled": stop before collection
const reconciledReview = await runs.run("review-reconcile-1", {
  agent: "collab-acceptor",
  cwd: lane,
  worktree: false,
  context: "fresh",
  task: REVIEW_BRIEF + " — rereview the reconciled protected current lane",
  outputSchema: reviewerSchema
});
// The Orchestrator judges reconciledReview.structuredOutput, then retries lane_collect
```

## Operations

Read this section only when selecting which `collab_*` tool carries out a Collab step. Each tool is
independently registered; its own description and parameter schema are authoritative for what it
accepts and returns. This section states which Collab step selects each tool and owns the dirt,
file-handling, and managed-worktree removal contracts.

Generic Collab dirt means staged or unstaged tracked changes. Ordinary untracked and ignored paths do
not by themselves block cleanliness checks or produce dirt, presence, preservation, status, or report
warnings; active merge/conflict state and unclassifiable Git state retain their explicit protections.

File handling follows the Git operation used or modeled. Merge-backed reconciliation and stale
collection retain native `git merge` collision behavior. Ready collection uses native
`git reset --hard`, which preserves non-obstructing untracked or ignored paths and may delete either
kind when it must write a tracked path. Synthetic landing continues to publish without invoking
`git merge --squash`, but models its collision behavior: non-colliding untracked and ignored paths are
preserved without presence warnings, ordinary untracked exact and file/directory overwrite collisions
are refused, and ignored collisions may be overwritten. Failure compensation removes a newly created
managed worktree with non-force `git worktree remove`, retaining the resource when Git refuses;
successful collection, lane drop, and task removal are explicit retirements and use force removal.

- Establishes the task-local integration branch collection needs before any lane can be collected
  into it — `collab_integration_create`.
- The Collection boundary's adoption step: makes an existing branch, passed as `source_branch`, the
  complete managed integration state — `collab_integration_adopt`.
- Choose the execution shape: creates the one writable branch, checkout, worktree, and lane-owned
  state a dispatched writer needs — `collab_lane_create`.
- Compose a reviewed lane: launches the configured implementer and acceptor asynchronously in one
  exact managed lane with bounded corrections — `collab_run_reviewed_lane`.
- Optional lane-side synchronization: brings a stale lane up to current integration when the
  Orchestrator explicitly chooses the separate pre-step. Collection normally relies on
  `collab_lane_collect`'s stale-lane handling instead — `collab_lane_reconcile`.
- Collect: moves an Orchestrator-accepted lane into the integration branch and force-retires the lane
  after successful collection — `collab_lane_collect`.
- Retire the lane: force-removes a lane's managed branch and worktree without collecting it, for a
  lane whose work is not going into integration — `collab_lane_drop`. It emits a custody warning when
  removal discards tracked or staged changes or active merge/conflict state. Unclassifiable Git state
  remains warning-worthy. This classification changes reporting only: best-effort removal and custody
  of unrecognized resources remain unchanged.
- Keeps the integration branch able to receive collection by merging current persistence back into
  it through a lane, when persistence has moved ahead of integration — `collab_integration_reconcile`.
- Land: moves the exact current integration result into a persistence branch, preserving the
  integration tree under a new commit identity — `collab_integration_land`.
- Retire the lane, at task scope: force-removes the managed integration and its remaining lanes once
  the task's collab-owned state is no longer needed — `collab_integration_remove`. When a Dev-flow task requested `efficiencyFeedback`, follow [dev-flow's feedback closeout](../dev-flow/references/collab-feedback-closeout.md) before `collab_integration_remove`; do not duplicate the procedure or change any public tool parameter.
- Read-only inspection of a task's integration and lane state; supports every step above without
  mutating anything — `collab_status`.
- Snapshot task state and telemetry to fixed report artifacts, with no cleanup or readiness
  judgement performed — `collab_report`.
