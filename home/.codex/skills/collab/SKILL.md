---
name: collab
description: "Orchestrator coordination for one bounded change: use when the Orchestrator bounds a change, chooses an execution shape, judges a reviewed lane, collects, or lands."
---

# Collab

Collab coordinates one bounded change without owning a durable lifecycle. The Orchestrator retains task
intent, acceptance criteria, final Acceptance judgement, and every scope or authority decision.

**This is the Orchestrator's document; the agent profiles are the workers'.** Execution shape, writer
placement, review placement, collection, and landing are decided here, by the Orchestrator. A
dispatched writer or reviewer carries out one bounded brief inside those decisions, working from its
own profile.

## Load-bearing objects

Define each at its first use:

- **Orchestrator** — the agent that holds task intent and every scope or authority decision, chooses
  the execution shape, dispatches writers and reviewers, makes the final Acceptance judgement, and
  may itself write a bounded change.
- **Integration branch** — the task-local cumulative result already accepted by the Orchestrator. This is
  the only meaning `accepted` needs here.
- **Lane** — one writable branch, checkout, worktree, and its lane-owned temporary state, assigned
  to one live writer at a time. A lane is an execution resource, not durable narrative.
- **Protected current lane** — the lane's current clean checkout state while its one writer is
  stopped; the ordinary object under review.
- **Collect** — movement of the Orchestrator-accepted current lane into integration.
- **Land** — movement from task integration into a persistence branch.

## Core guardrails

1. **One writer at a time per checkout.** This is concurrent exclusivity, not a lifetime binding:
   a checkout carries one live writer, and reassigning it once that writer's run is over is not a
   second writer. That checkout is the lane. Parallelize read-only work; give each concurrent
   writer a separate writable checkout.
2. **Review reads the protected current lane.** A reviewer inspects the lane's current clean state
   while its writer is stopped. A correction or collection-time reconciliation changes that lane, so
   review runs again against its new current state.
3. **Results carry semantics; identities belong to operations.** Exact commit and tree identities
   stay with the operations that require them — collection, landing, and runtime tracking. Ordinary
   worker and reviewer results carry only what workflow branching needs. Temporary efficiency
   telemetry remains operation evidence in the child run artifact or lane-owned sidecar; it does not
   add fields to the typed semantic result or move commit or tree identity into it.

## Dispatch brief Interface

A dispatch names the ticket and carries only operational deltas. Before sending it, the Orchestrator
closes the receiver profile's required fields with explicit values rather than repository guesses.
For a writer, include these compact blocks:

- `Orientation`: the owning Module or class, plus each named seam that deserves attention; use `none`
  when no seam is relevant. Do not supply a symbol inventory or predicted call chain.
- `Execution parameters`: the exact authorized command runtime or interpreter (or `none`), exact
  environment variables (or `none`), lane-local pytest basetemp (or `not-applicable`), ticket-specific
  test budgets or exceptions (or `none`), and cleanup or retention exceptions (or `none`).

Every collab role dispatch states `efficiency_probe = enabled | disabled`. When enabled, include a
lowercase filename-safe run label matching `[a-z0-9][a-z0-9._-]*`. An implementer dispatch also names
`.pi/telemetry/efficiency/` as its lane-relative target and an Orchestrator-owned custody destination
outside the lane; those values authorize exclusive creation of exactly one ignored telemetry file and
its byte-for-byte preservation before lane retirement. An acceptor remains read-only and emits its
probe data only as a distinct stdout record retained by the child run artifact, before returning the
unchanged typed verdict. Missing or unsafe required values stop at the receiver rather than
selecting fallback environment or identity.

## Responsibility boundaries

1. **Bound the change.** Close the applicable goal, scope, Acceptance, validation, authority, and
   stop conditions in the ticket. The ticket owns Outcome and Acceptance; a dispatch brief names the
   ticket and carries only the operational deltas — placement, authority, validation, stop
   conditions, and role-specific deltas — without copying the ticket's prose. Carry needed
   conclusions inline; point to supporting material with the condition for opening it. Before
   dispatch, inspect the selected receiver profile's `Preconditions` and `Result` sections and close
   every required value, path, mutation authority, evidence owner, and stop condition in the brief.
   This step is complete when the writer can distinguish in-scope implementation from an Orchestrator
   decision and every receiver field is supplied.
2. **Choose the execution shape.** The Orchestrator selects direct writing, separate dispatches,
   runtime composition, or another fitting shape, and safely places the next writer. The
   Orchestrator may be that writer for a bounded change: one-writer lane exclusivity still applies,
   and review is performed separately; when delegation would cost about as much as the change, no
   worker subagent is needed. When implementation is delegated and its brief, delegated Acceptance
   criteria, placement, mutation authority, and escalation boundary are closed, prefer runtime
   composition of a worker → reviewer → bounded correction loop; coordinate a transition separately
   when it depends on Orchestrator judgement. This is a preference, not a restriction on
   Orchestrator placement. Preserve one live writer per writable checkout and account for
   pre-existing state; isolate when another writer is active or existing work needs protection.
   **Runtime pointer:** before dispatching a writer, before collecting (boundary 5), or before
   landing, read this skill directory's `runtime-<name>.md` for your runtime when one exists; its
   Routing section names the section each step reads, and general mechanics stay behind conditional
   pointers within the file. A runtime needs no file when ordinary generic means — plain git and
   ordinary agent dispatch — already carry out everything the core states above; the core is then
   directly actionable as written. Treat any other absence as unwritten rather than as license to
   proceed: if your runtime works through specialized tooling the core does not name (an extension,
   a dedicated API) and no `runtime-<name>.md` documents it, stop and ask before guessing its
   mechanics. This step is complete when the writer has one bounded brief and one safe writable
   checkout.
3. **Implement and review.** Execute the chosen shape; for delegated closed work, prefer runtime
   composition of worker, reviewer, and bounded correction under a finite Orchestrator-supplied
   correction budget. The runtime pointer under boundary 2 carries the registered composition path
   and its terminal outcomes. Generic Acceptance below reviews the protected current lane; specialized
   procedures (such as code-review) remain alternatives with their own identity contracts. This
   step is complete when the lane carries a worker result and an independent review result, or a
   terminal blocker or decision request.
4. **Judge the result.** The Orchestrator makes the final Acceptance judgement and chooses what
   follows: accept the reviewed lane, return a bounded defect for correction, return a decision
   request or exhausted correction budget to its owner, or select another shape. A correction
   returns to boundary 3 against the changed lane. When the task owns an integration branch, an
   accepted lane goes to the collection boundary below before its lane retires. This step is
   complete when the Orchestrator accepts the result or identifies the unresolved decision and its
   owner.
5. **Collect.** Move the Orchestrator-accepted current lane into the integration branch one lane at
   a time. A stale lane is synchronized with current integration first and stops at the reconciled
   lane or a conflict; the reconciled lane needs its own review and Orchestrator judgement before
   collection. This step is complete when the accepted lane is the integration head and its lane is
   retired or its retention is reported.
6. **Retire the lane.** When a writer or reviewer lane reaches its terminal handoff and will not
   resume, first discharge any enabled implementer efficiency artifact: inventory the canonical
   lane directory, resolve the unique file for the dispatched label and recorded runtime identity,
   copy it byte-for-byte to the dispatched custody destination, verify the copy, and preserve its
   role, label, and runtime identity. Then inventory and remove lane-owned
   worktree registrations, temporary files or directories, sessions or processes, and agent-created
   branches that no longer carry required evidence. Preserve pre-existing user state and evidence
   still needed for Acceptance or landing; give every deliberate retention an owner and discharge
   condition. This step is complete when required telemetry has custody and no orphaned lane-owned
   resource remains.

## Continuity is a cache

Evidence and the protected current lane carry continuity: the bounded brief, direct observations,
validation results, and the lane's current clean state. Reusing the same writer or reviewer can
preserve useful context and diagnosis, but it is a context-cache optimization rather than a liveness
or authority requirement.

**Resume is an Orchestrator option, not a first step.** When a writer's run ends before its work
does, resume that session only when it preserves the required role, result, and authority contract;
a resume that drops or weakens the child's structured result or acceptance contract is not an
option. Otherwise dispatch a fresh compatible child carrying the original bounded contract, the
current typed blockers, and the applicable validation, authority, and escalation boundary. In the
composed loop, every correction and rereview is a fresh compatible child: a correction brief carries
the original bounded worker contract plus the current typed blockers; a rereview brief carries the
original review expectations and inspects the changed protected current lane. Give the replacement
the evidence, not unverified role narration.

**A replacement reads its ticket, not the task.** Its context is that ticket and whatever the ticket
points to; the task record and sibling tickets belong to the Orchestrator, and handing them over invites
scope creep. The ticket therefore names the next single step and the unverified boundary — which
edits are validated, which are not, and what must not be redone or widened. A ticket that leaves the
replacement to re-derive those is an unfinished brief, not a terse one.

**Mechanical finish.** When a run ends after its semantic work is validated but before the checkout
is clean and committed, and resuming the run cannot preserve the required role, result, and
authority contract, dispatch a fresh writer for that close-out alone: no semantic edits, lane-owned
temporary state removed, staged paths and diff inspected, ancestry checked, one clean commit. The
lane still needs a review result.

## Worker results are semantic

Worker Validation reports the behavior and Interface semantic checks the worker actually ran — each
with `check`, `result: PASSED | FAILED`, and a concise `summary` — plus residual risks for
non-blocking discoveries. Operational Git and runtime checks are categorically ineligible for
Validation and terminal semantic projection even when the worker runs them: status, diff, diff-check,
staged state, cleanliness, ancestry, commit identity, and runtime or lifecycle checks remain
operation evidence and receive no semantic check name or summary. Each semantic check name and
summary describes only the behavior/Interface outcome observed, never the operational command or
checkout, tree, lane, branch, commit, diff, staged, clean, ancestry, runtime, or lifecycle state
it ran against. The obligation to report every check run applies only to behavior/Interface
semantic checks. A check may be a command or direct
inspection; guidance prose is not turned into an automated test. Check results are observations, not
workflow routing: an unrelated failed check may remain on a `COMPLETED` handoff when its non-blocking
significance is explained in residual risks. Workers write no repo-local validation receipt; the run
artifact and Git own the evidence, and reviewers read the lane directly. Results state only
role-relevant checks, conclusions, and residual risks, without restating ticket prose, command
output, or evidence the ticket, Git, or the run artifact already own.

## Generic Acceptance

Ordinary Generic Acceptance reviews the protected current lane: the writer is stopped, the lane is
clean, and the acceptor reads its current state directly, read-only. It returns only, in this order:

- `Verdict`: `PASS | BLOCKED | NEEDS_DECISION`
- for each blocker (only for `BLOCKED`):
  - `Where`: the affected location
  - `Why`: the violated ticket expectation or Interface promise, plus direct evidence
  - `How to fix`: a bounded advisory suggestion
- for `NEEDS_DECISION`: why a decision is needed and the exact question
- `Out-of-envelope findings`: optional non-blocking observations outside the supplied boundary, each
  with its location and evidence

A `PASS` ends after Verdict and any out-of-envelope findings; it needs no empty filler. The verdict
is a review result, not ticket Acceptance: the Orchestrator owns the final judgement and closure.
`NEEDS_DECISION` returns a contract contradiction or new-scope question to the Orchestrator instead
of routing rework. A correction or reconciliation changes the lane, so review runs again against its
new current state. Generic Acceptance carries no fixed-subject result fields; specialized
procedures such as [code-review](../code-review/SKILL.md) keep their own identity contracts.

When delegated red/green validation needs several commands, a fixed working directory, or owned
temporary state, use [TDD Gate mode](../tdd/gate.md). Keep a one-command loop direct.

## Review placement and the correction loop

Reviewer placement may be composed by the runtime or an external workflow. For delegated closed work
— bounded brief, delegated Acceptance criteria, placement, mutation authority, and escalation
boundary all closed — prefer a runtime-composed worker → reviewer → bounded correction loop that
consumes one terminal handoff: a reviewed lane, a worker blocker, a decision request, or an
exhausted correction budget. The Orchestrator supplies a finite correction budget per composed
workflow; initial implementation does not consume it, each `BLOCKED → writer correction` transition
consumes one, and exhausting it returns to the Orchestrator without selecting a redesign procedure.
Scope, architecture, authority, or contract decisions terminate the loop at the Orchestrator.
Intermediate rounds stay in workflow context unless an observation independently justifies a durable
record.

A **seam correction** is one of those decisions carried back into the loop rather than a separate
stage or a new task: a reviewer may propose where the seam belongs, the Orchestrator decides, and
the next correction brief authorizes moving that named seam and so lifts the writer's original write
scope for that move alone. Its lane is reviewed like any other changed lane. It consumes one
correction budget slot like any other correction and never resets the budget — that single count is
what measures the cost this ticket has accumulated, and resetting it erases the evidence that the
design, not the implementation, is what keeps failing.

Collab does not require a particular workflow engine, retry count, steering mechanism, merge
strategy, first-parent shape, review procedure, or independent reviewer. Specialized code-review
remains an alternative source of separate Standards/Spec findings rather than a PASS/BLOCKED
Acceptance verdict. The terminal handoff carries the reviewed lane's outcome, the decision that is
needed, applicable direct observations, and residual risk. Orchestrator- and user-observed
Acceptance items are reported there rather than mislabelled as blockers.

## Collection boundary

When existing work becomes the managed integration, adoption previews its mutation before
authorizing it, and uses an existing branch as the complete managed integration state. It discards
changes from that integration when their lane has not been collected. It leaves any pre-existing
lane branch or worktree outside the adopted integration unless a separate lifecycle operation
retires it. The runtime pointer under "Choose the execution shape" above names the operations that
carry these out and tells you when their absence means your runtime needs none.

The runtime verifies the exact lane tip, that current integration is contained in the judged lane,
and that managed refs and worktrees are clean and identity-exact, then advances integration to the
accepted lane and retires it when it is clean. A stale lane is reconciled first; the reconciled
current lane is reviewed and judged again before collection. Dirt or ambiguity in the lane is
preserved and reported rather than deleted or inferred away.

This task-local collection is not landing and requires no separate landing grant.

## Land

Landing moves the exact current integration result into a user or product persistence branch such
as `feat/*` or `main`, preserving the integration tree under the new commit identity. Collab
creates no landing authority; stop at task integration unless a current user message or an
in-force task-scoped user grant authorizes landing under its stated conditions. When the
Orchestrator is running a dev-flow task, verify such a grant in dev-flow's [Custody
reference](../dev-flow/references/custody.md), which owns how the record holds user authority.
When landing is authorized and neither the user nor repository guidance names a method, default to
squash. Landing evidence applies only to the reviewed lane; a changed lane first needs a new review
result. The runtime pointer under "Choose the execution shape" above names the operation that
carries out landing.

Land is the authority boundary Collab owns: its guidance ends once integration has moved into the
persistence branch. Push and later persistence-branch handling stay outside Collab.
