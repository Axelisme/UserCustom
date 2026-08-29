---
name: collab
description: "Orchestrator coordination for one bounded change: use when the Orchestrator bounds a change, chooses an execution shape, judges the lane, collects, or lands."
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
2. **Review reads the protected current lane.** Where a review is placed, a reviewer inspects the
   lane's current clean state while its writer is stopped. A correction or reconciliation changes
   that lane, so review runs again against its new current state (see Reconciliation for lane versus
   integration reconciliation).
3. **Results carry semantics; identities belong to operations.** Exact commit and tree identities
   stay with the operations that require them — collection, landing, and runtime tracking. Ordinary
   worker and reviewer results carry only what workflow branching needs.

## Dispatch brief Interface

A dispatch names the ticket and carries only operational deltas. Before sending it, the Orchestrator
closes the receiver profile's required fields with explicit values rather than repository guesses.
For a writer, include these compact blocks:

- `Orientation`: the owning Module or class, plus each named seam that deserves attention; use `none`
  when no seam is relevant. Do not supply a symbol inventory or predicted call chain.
- `Execution parameters`: the exact authorized command runtime or interpreter (or `none`), exact
  environment variables (or `none`), lane-local pytest basetemp (or `not-applicable`), ticket-specific
  test budgets or exceptions (or `none`), and cleanup or retention exceptions (or `none`).

## Responsibility boundaries

1. **Bound the change.** Close the applicable goal, scope, Acceptance, validation, authority, and
   stop conditions in the ticket. The ticket owns Outcome and Acceptance; a dispatch brief names the
   ticket and carries only the operational deltas — placement, authority, validation, stop
   conditions, and role-specific deltas — without copying the ticket's prose. Carry needed
   conclusions inline; point to supporting material with the condition for opening it. Before
   dispatch, inspect the selected receiver profile's `Preconditions` and `Result` sections and close
   every required value, path, mutation authority, evidence owner, and stop condition in the brief.
   The ticket contract also closes **operating assumptions** beside the existing envelope pointer:
   what a reviewer may assume about concurrency, caller trust, input provenance, and adversary
   presence. The two terms stay distinct — the envelope says which changes belong to the task,
   operating assumptions say which world the code runs in — and neither stands in for the other.
   Delegated ticket-checkbox authority is owned by dev-flow's record rules, not redefined here: a
   dispatched writer may toggle only the Acceptance claims its dispatch explicitly assigns, keeping
   them truthful, while a reviewer reads the ticket without editing it. Child role profiles carry
   that rule directly, so dispatched children need only their profiles and assigned ticket inputs —
   never a dev-flow read just to learn their checkbox authority.
   This step is complete when the writer can distinguish in-scope implementation from an Orchestrator
   decision and every receiver field is supplied.
2. **Choose the execution shape.** The Orchestrator selects direct writing, separate dispatches,
   runtime composition, or another fitting shape, and safely places the next writer. The
   Orchestrator may be that writer for a bounded change: one-writer lane exclusivity still applies.

   **Placement is two independent questions**, and the asymmetry of answering only one is what
   leaves a lane overstaffed or unguarded.

   **Who writes.** When describing the change costs about as much as making it — the brief would
   have to state the change itself to be intelligible — the Orchestrator writes it directly;
   otherwise dispatch a writer.

   **Who verifies.** Each Acceptance claim is either **proved** — some listed Mechanical gate's
   pass/fail is that claim — or it is **residue**. Residue is what an acceptor exists to judge, so
   residue places one and its absence does not. All four combinations are ordinary.

   When implementation is delegated and its brief, delegated Acceptance
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
   mechanics.

   A managed lane is dispatch-ready only after its repository-declared worktree bootstrap succeeds.
   Roles consume the resulting environment through the exact dispatched execution parameters without
   syncing or provisioning it. An observed bootstrap failure or absent ordinary-path environment is
   `BLOCKED` before reviewed dispatch, never a reason to discover a fallback. Retain the lane-owned
   runtime through review and correction until the lane retires through collection or drop. Follow the
   positive path first; return a concrete environment-selection failure to the Orchestrator before
   strengthening controls. Pi maps this sequence to its existing operations in
   [Managed lane environment](runtime-pi.md#managed-lane-environment).

   This step is complete when the writer has one bounded brief and one safe writable checkout, with
   the repository-declared bootstrap applied when the repository requires one.
3. **Implement and review.** Execute the chosen shape; for delegated closed work that places a
   reviewer, prefer runtime composition of worker, reviewer, and bounded correction under a finite Orchestrator-supplied
   correction budget. The runtime pointer under boundary 2 carries the registered composition path
   and its terminal outcomes. Generic Acceptance below reviews the protected current lane; specialized
   procedures (such as code-review) remain alternatives with their own identity contracts. This
   step is complete when the lane carries a worker result and, where boundary 2 placed a reviewer, an
   independent review result — or a terminal blocker or decision request.
4. **Judge the result.** The Orchestrator makes the final Acceptance judgement and chooses what
   follows: accept the judged lane, return a bounded defect for correction, return a decision
   request or exhausted correction budget to its owner, or select another shape. A correction
   returns to boundary 3 against the changed lane. When the task owns an integration branch, an
   accepted lane goes to the collection boundary below before its lane retires. This step is
   complete when the Orchestrator accepts the result or identifies the unresolved decision and its
   owner.
5. **Collect.** Move the Orchestrator-accepted current lane into the integration branch one lane at
   a time. A stale lane is synchronized with current integration first and stops at the reconciled
   lane or a conflict; the reconciled lane returns to boundary 2 for review placement and needs the
   Orchestrator's judgement again before collection (see Reconciliation). This step is complete when
   the accepted lane is the integration head and its lane is retired or its retention is reported.
6. **Retire the lane.** When a writer or reviewer lane reaches its terminal handoff and will not
   continue, inventory and remove lane-owned
   worktree registrations, temporary files or directories, sessions or processes, and agent-created
   branches that no longer carry required evidence. Preserve pre-existing user state and evidence
   still needed for Acceptance or landing; give every deliberate retention an owner and discharge
   condition. This step is complete when no orphaned lane-owned
   resource remains.

## Continuity is a cache

Evidence and the protected current lane carry continuity: the bounded brief, direct observations,
and the lane's current clean state. Ticket-owned mechanical gates are validated by the implementer and proved only by lane state; they are not re-executed by reviewers.

When a writer's run ends before its work does, dispatch a fresh compatible child carrying the original
bounded contract, the current typed blockers, and the applicable authority and escalation
boundary. In the composed loop, every correction and rereview is a fresh compatible child: a
correction brief carries the original bounded worker contract plus the current typed blockers; a
rereview brief carries the original review brief, prior typed blockers and the internal `correctionBase` SHA of the exact reviewed lane HEAD that the initial reviewer inspected. The runtime carries only that original brief, prior typed blockers and correctionBase for rereview — no ancestry, reconciliation, scope or incremental-eligibility policy is added, and diff content or changed-path caches never enter the prompt; Git (`git diff --find-renames <correctionBase>...HEAD --`) is the delta authority. A new fixed subject after correction does not equate to a full review restart: initial review and rereview have distinct responsibilities (see Review placement) and reviewers obtain the delta from Git rather than receiving a copied diff.

**A replacement reads its ticket, not the task.** Its context is that ticket and whatever the ticket
points to; the task record and sibling tickets belong to the Orchestrator, and handing them over invites
scope creep. The ticket therefore names the next single step and the unverified boundary — which
edits are validated, which are not, and what must not be redone or widened. A ticket that leaves the
replacement to re-derive those is an unfinished brief, not a terse one.

**Mechanical finish.** When a run ends after its semantic work is validated but before the checkout
is clean and committed, dispatch a fresh writer for that close-out alone: no semantic edits, lane-owned
temporary state removed, staged paths and diff inspected, ancestry checked, one clean commit. It
carries no semantic edit, so it leaves no residue and is judged on its gates.

## Worker results are semantic — ticket-owned mechanical gates, no Validation field

The ticket owns the ordered binary Mechanical gates plan; every listed gate must pass before the implementer may return `COMPLETED`. The implementer fixes failures within scope in the required order — focused failures first, then affected, then formatter/style (re-running affected after any mutation), then broader — and returns one complete `BLOCKED` result when closure exceeds authority. `COMPLETED` is the binary attestation that the required gates passed; it carries no free-text `Validation` array and creates no durable receipt. Ordinary mechanical gate commands and raw outputs stay with the run artifact; durable observations for difficult claims belong only to the Orchestrator-precreated workflow-scoped Acceptance appendix at the exact dispatched target (see Dispatch brief). Reviewed roles do not reopen run artifacts to judge gates. All non-blocking codebase findings across every worker and reviewer outcome branch — whether inside or outside the task envelope — are carried as optional `residualRisks: string[]`; the former `outOfEnvelopeFindings` is removed and every terminal branch preserves available risks, with `REVIEWED` merging latest worker then final reviewer risks without changing routing. `efficiencyFeedback` is optional skill/profile/runtime process feedback only: one concrete avoidable cost with cause and measurement when available, omitted otherwise; it never carries codebase findings and never affects verdicts, budgets or routing.

Operational Git and runtime checks — status, diff, diff-check, staged state, cleanliness, ancestry, commit identity, and lifecycle — remain operation evidence and never belong in an appendix. Results state only role-relevant routing, risks, and stop reasons, without restating ticket prose, command output, or evidence the ticket, Git, or the run artifact already own.

## Generic Acceptance — read-only, production-reachable blockers only

Ordinary Generic Acceptance reviews the protected current lane: the writer is stopped, the lane is
clean, and the acceptor reads its current state directly, read-only. Bash use is limited to read-only retrieval (`git diff`, `git show`, `git status`, `git log`, `rg`, `grep`, `find`, Grove); it excludes pytest, type/lint/format gates, Python/import probes and runtime/process workflows. The acceptor does not execute mechanical gates; it judges ticket gate coverage and the Acceptance claims no gate proved. It returns only, in this order:

- `Verdict`: `PASS | BLOCKED | NEEDS_DECISION`
- for each blocker (only for `BLOCKED`):
  - `Where`: the affected location
  - `Why`: the violated ticket expectation or Interface promise, plus direct evidence
  - `How to fix`: a bounded advisory suggestion
  - `Trigger`: the concrete production-reachable input or call sequence that produces the defect, and the existing entry point it reaches from
- for `NEEDS_DECISION`: why a decision is needed and the exact question
- `Residual risks`: optional `residualRisks: string[]` for all non-blocking codebase findings (unified, whether inside or outside the envelope); `outOfEnvelopeFindings` is removed

Every safety or non-happy-path blocker must be production-reachable under the stated operating assumptions: identify the existing production entry point, a concrete reachable input or event sequence, the current observable failure, the violated Acceptance or Interface promise, and the smallest requirement-compliant bounded fix. When Acceptance does not require recovery, tolerance, fallback, compatibility or graceful degradation, safe explicit rejection or Fast Fail is complete; a reviewer demanding more must prove why Fast Fail violates a named promise, using only bounded advisory fixes that do not expand scope via robustness or future-proofing. A finding that depends on a wider operating model than the dispatch declared is reported via residual risks, not as a blocker.

A `PASS` ends after Verdict and any residual risks; it needs no empty filler. The verdict
is a review result, not ticket Acceptance: the Orchestrator owns the final judgement and closure.
`NEEDS_DECISION` returns a contract contradiction or new-scope question to the Orchestrator instead
of routing rework. A correction or reconciliation (see Reconciliation for lane versus integration) changes the lane, so review runs again against its
new current state (distinct responsibilities — see Review placement, not a full restart). Generic Acceptance carries no fixed-subject result fields and no `correctionBase` projection; public terminal results never expose the internal base. Specialized
procedures such as [code-review](../code-review/SKILL.md) keep their own identity contracts.

When delegated red/green validation needs several commands, a fixed working directory, or owned
temporary state, use [TDD Gate mode](../tdd/gate.md). Keep a one-command loop direct.

## Review placement and the correction loop — initial review versus rereview

Boundary 2 decides whether a reviewer is placed at all. This section governs the review once one is.

Reviewer placement may be composed by the runtime or an external workflow. For delegated closed work
— bounded brief, delegated Acceptance criteria, placement, mutation authority, and escalation
boundary all closed — prefer a runtime-composed worker → reviewer → bounded correction loop that
consumes one terminal handoff: a reviewed lane, a worker blocker, a decision request, or an
exhausted correction budget. The Orchestrator supplies a finite correction budget per composed
workflow; initial implementation does not consume it, each `BLOCKED → writer correction` transition
consumes one, and exhausting it returns to the Orchestrator without selecting a redesign procedure. Correction budget, accounting, reviewer recovery, lane lifecycle, collection, landing and push behavior remain unchanged by this task.
Scope, architecture, authority, or contract decisions terminate the loop at the Orchestrator.
Intermediate rounds stay in workflow context unless an observation independently justifies a durable
record.

**Initial review** (fresh acceptor, protected current lane, runtime-owned `integrationTip` baseline, `git diff --find-renames <integrationTip>...HEAD --`) exhausts every non-mechanical Acceptance claim and directly reachable siblings in the same failure class handled by the same owning function and governed by the same ticket expectation, before returning one complete `BLOCKED` set with `correctionBase` set to the exact reviewed lane HEAD. It does not equate a new fixed subject with a full review restart.

**Rereview** is performed by a fresh acceptor (not a resume of the prior reviewer) against the changed protected lane. It receives the original review brief, prior typed blockers and that `correctionBase` SHA, obtains the delta from Git (`git diff --find-renames <correctionBase>...HEAD --`) rather than receiving a copied diff or changed-path cache, verifies every prior blocker is closed, and checks correction-reachable semantic effects. It does not rerun mechanical gates and does not restart the whole review. A correction that leaves the lane unchanged still consumes one budget slot; the single count is never reset.

Public terminal projections of `BLOCKED`, `CORRECTION_BUDGET_EXHAUSTED` and `REVIEWED` carry blockers (with `trigger`), `residualRisks` and `efficiencyFeedback` only; `correctionBase` is internal and never projected, and no ancestry, reconciliation, scope or incremental-eligibility policy is added by the runtime.

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

## Reconciliation

Two operations share this name and carry different review costs; each is defined here once.

**Lane reconciliation** brings a stale lane up to current integration. Its review stays bounded to
the current ticket: boundary 2's proved/residue test applies to the reconciled lane exactly as it
applies to any other lane state.

**Integration reconciliation** brings persistence into integration when persistence has moved ahead of
it; the runtime pointer under "Choose the execution shape" names the operation that carries it out.
What it brings in was covered by no ticket's Acceptance, so the Orchestrator re-evaluates the task's
Acceptance, not only the current ticket's. Boundary 2 places an acceptor for residue — an Acceptance
claim no listed gate proves — and content no ticket ever claimed has no gate to prove it, so residue
is never empty for integration reconciliation: an acceptor is always placed there, a consequence of
boundary 2's test rather than a rule of its own.

Either reconciliation's review brief names the parent provenance it introduced, so a reviewer reports
inherited history as inherited rather than judging it as current-task scope creep.

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
current lane returns to boundary 2 for review placement and is judged again before collection (see
Reconciliation for lane versus integration reconciliation). Dirt or ambiguity in the lane is
preserved and reported rather than deleted or inferred away.

This task-local collection is not landing and requires no separate landing grant.

## Land

Landing moves the exact current integration result into a user or product persistence branch such
as `feat/*` or `main` by creating one ordinary two-parent merge commit. The commit's first parent
is the previous persistence head and second parent is the accepted integration head; the commit's
tree is verified to equal the accepted integration tree, then both the persistence branch and the
managed integration branch are advanced to that merge commit. Collab creates no landing authority;
stop at task integration unless a current user message or an in-force task-scoped user grant
authorizes landing under its stated conditions. When the Orchestrator is running a dev-flow task,
verify such a grant in dev-flow's [Custody reference](../dev-flow/references/custody.md), which
owns how the record holds user authority. Landing requires a clean persistence checkout: no staged,
no unstaged tracked, and no ordinary untracked state before mutation (ignored files are allowed);
path conflicts and ignored-file collisions follow native `git merge` behavior. Hooks run natively;
merge or hook failure is reported as an actionable Git error exposing Git's resulting state, without
synthetic publication or dirt-preservation rollback. Legacy `refs/orchestrate/<task-id>/landed` is
no longer created; an existing instance is tolerated as migration state and is deleted by the next
authorized adopt, land, or remove operation. Freshness and continued landing eligibility are
determined by ordinary branch ancestry and shared heads; no landed-identity exception participates.
Landing evidence applies only to the reviewed lane; a changed lane first needs a new review result.
The runtime pointer under "Choose the execution shape" above names the operation that carries out
landing.

Land is the authority boundary Collab owns: its guidance ends once integration has moved into the
persistence branch. Push and later persistence-branch handling stay outside Collab.
