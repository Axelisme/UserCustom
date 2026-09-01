---
name: collab
description: "Orchestrator coordination for one bounded change: use when the Orchestrator bounds a change, chooses an execution shape, judges the lane, collects, or lands."
---

# Collab

Collab coordinates one bounded change without owning a durable lifecycle.

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
- **Writer** — whoever holds the lane's single write token: a dispatched `collab-implementer`, or
  the Orchestrator writing the change itself.
- **Reviewer** — whoever reads the stopped lane read-only and judges it: a dispatched
  `collab-acceptor`, a specialized procedure such as [code-review](../code-review/SKILL.md), or the
  Orchestrator when it places no separate reader. Both are positions; the profiles specialize them
  and are never the positions themselves.
- **Protected current lane** — the lane's current clean checkout state while its one writer is
  stopped; the ordinary object under review.
- **Runtime pointer** — this skill directory's `runtime-<name>.md` for the runtime in use. Boundary 2
  states when to read it and what its absence means.

## Core guardrails

1. **One writer at a time per checkout.** That checkout is the lane. Parallelize read-only work;
   give each concurrent writer a separate writable checkout.
2. **Review reads the protected current lane.** Where a review is placed, a reviewer inspects the
   lane's current clean state while its writer is stopped. A correction or reconciliation changes
   that lane, so review runs again against its new current state (see Reconciliation for lane versus
   integration reconciliation).
3. **Results carry semantics; identities belong to operations.** Exact commit and tree identities
   stay with the operations that require them — collection, landing, and runtime tracking. Ordinary
   worker and reviewer results carry only what workflow branching needs.

## Dispatch brief Interface

A dispatch names the ticket and carries only the operational deltas — placement, authority,
validation, stop conditions, and role-specific deltas — without copying the ticket's prose. Carry a
needed conclusion inline; point to supporting material with the condition for opening it. Before
sending the brief, inspect the selected receiver profile's `Dispatch contract` and `Result` sections
and close every required value, path, mutation authority, evidence owner, and stop condition in it,
with explicit values rather than repository guesses. Those two sections are the Orchestrator's share
of a profile and carry that role's authoritative field list; the rest of the profile is the
receiver's own workflow.

## Responsibility boundaries

1. **Bound the change.** Close the applicable goal, scope, Acceptance, validation, authority, and
   stop conditions in the ticket, which owns Outcome and Acceptance. The Dispatch brief Interface
   above owns what the brief itself then carries.
   The ticket contract also closes **operating assumptions** beside the existing envelope pointer:
   what a reviewer may assume about concurrency, caller trust, input provenance, and adversary
   presence. The envelope says which changes belong to the task; operating assumptions say which
   world the code runs in.
   Name the observer of every Acceptance claim you do not want the lane's writer to toggle, and the
   observation that decides each claim, in the ticket rather than in the brief: a claim naming no
   observer belongs to whoever holds the lane's write token, and that is you when you write the
   change yourself. A claim no one can decide by an action is not Acceptance, it is intent, and it is
   rewritten before dispatch.
   A ticket whose Acceptance cannot be closed by one correction is two tickets. The ticket is the single source
   both dispatched roles already read, so a brief needs no separate checkbox grant and none can drift
   from it across correction rounds.
   [lane-authority](../dev-flow/references/lane-authority.md) owns the writer position, which
   observer owns which checkbox, and the closing sweep every writer runs before declaring its lane
   finished.
   This step is complete when the writer can distinguish in-scope implementation from an Orchestrator
   decision and every receiver field is supplied.
2. **Choose the execution shape.** The Orchestrator selects direct writing, separate dispatches,
   runtime composition, or another fitting shape, and safely places the next writer. The
   Orchestrator may be that writer for a bounded change: one-writer lane exclusivity still applies.

   **Placement is two independent questions**, and the asymmetry of answering only one is what
   leaves a lane overstaffed or unguarded.

   **Who writes.** A dispatched implementer is cheap and literal: it succeeds where scope is closed
   and the steps are concrete, and drifts where the work needs judgement no brief can carry. So two
   shapes of work stay with the Orchestrator — the change small enough that describing it costs about
   as much as making it, because the brief would have to state the change itself to be intelligible,
   and the change hard enough that no closed brief would carry it. Otherwise dispatch a writer.

   **Who verifies.** Walk every Acceptance claim and write the gate that decides it. A claim is
   **mechanically decidable** when one command's exit status *is* that claim — the same answer for
   anyone who runs it, with nothing in its output left to read. Every such claim gets that command
   listed as a Mechanical gate, and is then **proved**. **Residue is what remains after that
   subtraction**: the claims no command can decide, and what a reviewer exists to judge. Residue
   places one and its absence does not. All four combinations are ordinary.

   With no residue no independent reader is placed, and the judgement does not move: the Orchestrator
   holds final Acceptance in every case (boundary 4), and with the gates' pass/fail as the whole
   judgement there is nothing for a second reader to be independent about. A claim a command could
   decide that no gate lists is the signal to check the gate list before dispatching, not to staff
   around it.

   A check that only becomes decidable after the gate phase cannot be a lane gate — the gate list
   runs before the writer commits. Assign it to the first reader that exists after it: the reviewer
   when one is placed, and otherwise you at boundary 4.

   When implementation is delegated and its brief, delegated Acceptance
   criteria, placement, mutation authority, and escalation boundary are closed, prefer runtime
   composition of a worker → reviewer → bounded correction loop; coordinate a transition separately
   when it depends on Orchestrator judgement. Account for pre-existing state; isolate when another
   writer is active or existing work needs protection.
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
   correction budget. The runtime pointer carries the registered composition path
   and its terminal outcomes. Generic Acceptance below reviews the protected current lane. This
   step is complete when the lane carries a worker result and, where boundary 2 placed a reviewer, an
   independent review result — or a terminal blocker or decision request.
4. **Judge the result.** The Orchestrator makes the final Acceptance judgement. Compare the ticket's
   `Swept at` against the lane head first when no reviewer was placed to do it: behind the head, the
   writer's sweep is stale and its checked claims are unconfirmed against the delivered tree, so
   confirm them yourself or return the lane for a fresh sweep before accepting it. Then
   choose what follows: accept the judged lane, return a bounded defect for correction, return a decision
   request or exhausted correction budget to its owner, or select another shape. A correction the
   Orchestrator itself dispatches returns to boundary 2, so placement is decided once per dispatch
   rather than once per ticket; a correction inside a composed loop is the loop's own and returns to
   boundary 3, because that loop's placement was fixed when it was composed. When the task owns an integration branch, an
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
   condition. Collab's own implementation-time scaffolding is a dispatched writer's
   `probe/<ticket-id>/`: that writer's profile puts its still-open questions there, outside the
   review surface, and the directory comes down before the ticket closes — so a lane that retires
   with one still standing hands the Orchestrator a directory to clear. This step is complete when
   no orphaned lane-owned resource remains.

## Continuity is a cache

Evidence and the protected current lane carry continuity: the bounded brief, direct observations,
and the lane's current clean state.

When a writer's run ends before its work does, dispatch a fresh compatible child carrying the original
bounded contract, the current typed blockers, and the applicable authority and escalation boundary.
In the composed loop every correction and rereview is such a child; Review placement below states
what each of those two briefs carries.

**A replacement reads its ticket, not the task.** Its context is that ticket and whatever the ticket
points to; the task record and sibling tickets belong to the Orchestrator, and handing them over invites
scope creep. The ticket therefore names the next single step and the unverified boundary — which
edits are validated, which are not, and what must not be redone or widened.

**Mechanical finish.** When a run ends after its semantic work is validated but before the checkout
is clean and committed, dispatch a fresh writer for that close-out alone: no semantic edits, lane-owned
temporary state removed, staged paths and diff inspected, ancestry checked, one clean commit. It
carries no semantic edit, so it leaves no residue and is judged on its gates.

## Worker results are semantic

**Gates.** dev-flow's [ticket template](../dev-flow/templates/ticket/ticket.md) gives the ticket
the ordered binary gate plan and requires every listed gate to pass before `COMPLETED`. The implementer fixes failures within scope in the order that
ticket section states, or the default its own profile carries when the section states none, and
returns one complete `BLOCKED` result when closure exceeds authority. Ticket-owned gates are validated by the implementer and proved only by lane state;
reviewed roles neither re-execute them nor reopen run artifacts to judge them. Judging gate integrity from the lane diff alone is not re-execution.

**`COMPLETED` is a binary attestation** that the required gates passed and that every writer-owned
Acceptance claim was re-verified against the final tree — dev-flow's
[lane-authority](../dev-flow/references/lane-authority.md#the-closing-sweep) owns that closing sweep
and its `Swept at` record. It carries no free-text `Validation` array and creates no durable receipt. Ordinary gate
commands and raw outputs stay with the run artifact; a judging process worth keeping belongs only to
the workflow-scoped Acceptance appendix at the exact dispatched target. Name that target in the brief;
its writer creates the file from dev-flow's `templates/ticket/evidence.md` and fills it with targeted
edits, so the grant you issue is a path and never a file you precreate.
[record-hygiene](../dev-flow/references/record-hygiene.md#workflow-scoped-acceptance-appendix) owns
when an appendix is required and what an assigned target does and does not grant. Operational Git and runtime checks — status, diff,
diff-check, staged state, cleanliness, ancestry, commit identity, and lifecycle — are operation
evidence and never belong in an appendix.

**`residualRisks: string[]`** is optional and carries every non-blocking codebase finding, from any
worker or reviewer outcome branch, whether inside or outside the task envelope. Every terminal branch
preserves available risks; `REVIEWED` merges the latest worker's then the final reviewer's without
changing routing.

**`efficiencyFeedback`** is optional process feedback about the skill, profile, or runtime: one
concrete avoidable cost with its cause, and its measurement when available, omitted otherwise. It
never carries codebase findings and never affects verdicts, budgets, or routing.

Results state only role-relevant routing, risks, and stop reasons, without restating ticket prose,
command output, or evidence the ticket, Git, or the run artifact already own.

## Generic Acceptance

Ordinary Generic Acceptance reviews the protected current lane: the writer is stopped, the lane is
clean, and the reviewer reads its current state directly, read-only. Bash use is limited to read-only retrieval (`git diff`, `git show`, `git status`, `git log`, `rg`, `grep`, `find`, Grove); it excludes pytest, type/lint/format gates, Python/import probes and runtime/process workflows. The reviewer does not execute mechanical gates; it judges ticket gate coverage, the Acceptance claims no gate proved, and gate integrity. **Gate integrity**: a gate's pass is part of the lane under review, and when the lane obtains that pass by changing what the gate measures, the pass is hollow and the lane is `BLOCKED` — no Acceptance claim need have been violated, because the violated expectation is the ticket's own gate entry. Reading the lane diff for the two shapes this is bounded to — a test or assertion whose subject changed inside this lane, and an added construct whose only effect is to silence a checker — is not re-executing a gate. Beyond those two shapes a hollow pass is unobservable to a read-only role, so it is not pursued. It returns only, in this order:

- `Verdict`: `PASS | BLOCKED | NEEDS_DECISION`
- for each blocker (only for `BLOCKED`):
  - `Where`: the affected location
  - `Why`: the violated ticket expectation or Interface promise, plus direct evidence — for a hollow pass, the ticket's own Mechanical gate entry; for a stale sweep, the `Swept at` record
  - `How to fix`: a bounded advisory suggestion; when the blocker was mechanically decidable, also the gate that should have caught it — except a stale sweep, which no gate can catch because the gate list runs before the commit `Swept at` names
  - `Trigger`: the concrete production-reachable input or call sequence that produces the defect, and the existing entry point it reaches from — for a hollow pass, the gate invocation and the property it no longer measures; for a stale sweep, the recorded `Swept at` against the lane head
- for `NEEDS_DECISION`: why a decision is needed and the exact question
- `Residual risks`: optional `residualRisks: string[]` for all non-blocking codebase findings, whether inside or outside the envelope

A hollow pass and a stale sweep are the only two blocker classes that may omit a production-reachable input; each substitutes the entry point and trigger named above. Every other safety or non-happy-path blocker must be production-reachable under the stated operating assumptions: identify the existing production entry point, a concrete reachable input or event sequence, the current observable failure, the violated Acceptance or Interface promise, and the smallest requirement-compliant bounded fix. When Acceptance does not require recovery, tolerance, fallback, compatibility or graceful degradation, safe explicit rejection or Fast Fail is complete; a reviewer demanding more must prove why Fast Fail violates a named promise, using
bounded advisory fixes that stay inside the ticket's stated outcome rather than expanding scope via
robustness or future-proofing. A finding that depends on a wider operating model than the dispatch declared is reported via residual risks, not as a blocker.

A `PASS` ends after Verdict and any residual risks; it needs no empty filler. The verdict
is a review result, not ticket Acceptance: the Orchestrator owns the final judgement and closure.
`NEEDS_DECISION` returns a contract contradiction or new-scope question to the Orchestrator instead
of routing rework. Generic Acceptance carries no fixed-subject result fields and no `correctionBase` projection; public terminal results never expose the internal base. Specialized procedures such as [code-review](../code-review/SKILL.md) keep their own identity
contracts and produce separate Standards/Spec findings rather than a PASS/BLOCKED Acceptance verdict.

When delegated red/green validation needs several commands, a fixed working directory, or owned
temporary state, use [TDD Gate mode](../tdd/gate.md). Keep a one-command loop direct.

## Review placement and the correction loop

Boundary 2 decides whether a reviewer is placed, at every dispatch the Orchestrator issues. This section governs the review once one is.

**The loop is drafted to close in one correction.** Gates carry the mechanical mass, so the first
candidate arrives nearly complete and the first review returns few, small blockers. A first review
that returns several independent blocker classes is evidence that the gate list or the ticket's width
was drafted wrong — repair the ticket before spending another correction against it. Budget
consumption is a diagnostic signal, not progress.

Reviewer placement may be composed by the runtime or an external workflow. For delegated closed work
— bounded brief, delegated Acceptance criteria, placement, mutation authority, and escalation
boundary all closed — prefer a runtime-composed worker → reviewer → bounded correction loop that
consumes one terminal handoff: a reviewed lane, a worker blocker, a decision request, or an
exhausted correction budget. The Orchestrator supplies a finite correction budget per composed
workflow, `1` by default; initial implementation does not consume it, each `BLOCKED → writer correction` transition
consumes one, and exhausting it returns to the Orchestrator without selecting a redesign procedure.
Scope, architecture, authority, or contract decisions terminate the loop at the Orchestrator.
Intermediate rounds stay in workflow context unless an observation independently justifies a durable
record.

**Initial review** (fresh reviewer, protected current lane, runtime-owned `integrationTip` baseline, `git diff --find-renames <integrationTip>...HEAD --`) exhausts every Acceptance claim no gate decided and directly reachable siblings in the same failure class handled by the same owning function and governed by the same ticket expectation, before returning one complete `BLOCKED` set with `correctionBase` set to the exact reviewed lane HEAD. It does not equate a new fixed subject with a full review restart.

**Rereview** is performed by a fresh reviewer — not a resume of the prior one — against the changed protected lane. Its brief carries the original review brief, the prior typed blockers, and that internal `correctionBase` SHA, and nothing else: no ancestry, reconciliation, scope or incremental-eligibility policy, and no diff content or changed-path cache. Git is the delta authority (`git diff --find-renames <correctionBase>...HEAD --`). A correction brief is the same shape, carrying the original bounded worker contract plus the current typed blockers. Rereview verifies every prior blocker is closed, and checks correction-reachable semantic effects. It does not rerun mechanical gates and does not restart the whole review: a new fixed subject after correction is not a full review restart, because initial review and rereview carry distinct responsibilities. A correction that leaves the lane unchanged still consumes one budget slot; the single count is never reset.

Public terminal projections of `BLOCKED`, `CORRECTION_BUDGET_EXHAUSTED` and `REVIEWED` carry blockers (with `trigger`), `residualRisks` and `efficiencyFeedback`, and nothing else; `correctionBase` is internal and never projected.

A **seam correction** is one of those decisions carried back into the loop rather than a separate
stage or a new task: a reviewer may propose where the seam belongs, the Orchestrator decides, and
the next correction brief authorizes moving that named seam and so lifts the writer's original write
scope for that move alone. Its lane is reviewed like any other changed lane. It consumes one
correction budget slot like any other correction and never resets the budget — that single count is
what measures the cost this ticket has accumulated, and resetting it erases the evidence that the
design, not the implementation, is what keeps failing.

The terminal handoff carries the reviewed lane's outcome, the decision that is
needed, applicable direct observations, and residual risk. Orchestrator- and user-observed
Acceptance items are reported there rather than mislabelled as blockers.

## Reconciliation

Two operations share this name and carry different review costs; each is defined here once.

**Lane reconciliation** brings a stale lane up to current integration. Its review stays bounded to
the current ticket: boundary 2's proved/residue test applies to the reconciled lane exactly as it
applies to any other lane state.

**Integration reconciliation** brings persistence into integration when persistence has moved ahead of
it; the runtime pointer names the operation that carries it out.
What it brings in was covered by no ticket's Acceptance, so the Orchestrator re-evaluates the task's
Acceptance, not only the current ticket's. Boundary 2 places a reviewer for residue, and content no
ticket ever claimed has no gate to prove it, so residue is never empty for integration reconciliation: a reviewer is always placed there.

Either reconciliation's review brief names the parent provenance it introduced, so a reviewer reports
inherited history as inherited rather than judging it as current-task scope creep.

## Collection boundary

When existing work becomes the managed integration, adoption previews its mutation before
authorizing it, and uses an existing branch as the complete managed integration state. It discards
changes from that integration when their lane has not been collected. It leaves any pre-existing
lane branch or worktree outside the adopted integration unless a separate lifecycle operation
retires it. The runtime pointer names the operations that carry these out.

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
synthetic publication or dirt-preservation rollback. Freshness and continued landing eligibility are
determined by ordinary branch ancestry and shared heads.
Landing evidence applies only to the reviewed lane; a changed lane first needs a new review result.
The runtime pointer names the operation that carries out landing.

Land is the authority boundary Collab owns: its guidance ends once integration has moved into the
persistence branch. Push and later persistence-branch handling stay outside Collab.

## Evolving this skill

Read [dev-flow's design principles](../dev-flow/references/design-principles.md) before changing
this document or an agent profile. They own altitude, evidence, and where a rule's text belongs
against where its readers stand; both skills are governed by them.
