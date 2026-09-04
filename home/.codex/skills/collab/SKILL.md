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
- **Anchored pointer** — a reference ending in `#<anchor>`, which addresses one section rather than a
  document. Open it there with `python3 ~/.codex/skills/dev-flow/scripts/section.py <pointer>`, copying the
  pointer verbatim; read a document whole when its pointer carries no anchor.

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
sending the brief, read the selected receiver profile's `#dispatch-contract` and `#result` sections
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
   Name every Acceptance claim's deciding observer, and the observation that decides it, in the
   ticket rather than in the brief: a claim naming no observer is not publishable, and the writer's
   checkbox settles nothing either way. A claim no one can decide by an action is not Acceptance, it is intent, and it is
   rewritten before dispatch.
   A ticket whose Acceptance cannot be closed by one correction is two tickets. The ticket is the single source
   both dispatched roles already read, so a brief needs no separate checkbox grant and none can drift
   from it across correction rounds.
   [lane-authority](../dev-flow/references/lane-authority.md) owns the writer position and the
   deciding observer every claim names.
   This step is complete when the writer can distinguish in-scope implementation from an Orchestrator
   decision and every receiver field is supplied.
2. **Prepare the contract, then place the remaining implementation.** Boundary 2 has two steps in
   that order. Contract preparation closes the Interface shape; placement assigns only the work left
   inside it.

   **Step 1 — Prepare the contract.** Compare the ticket's `## Seam contract` with the lane before
   implementation placement. A ticket is **contract-bearing** when the Interface itself is part of
   its deliverable, rather than only behavior behind an Interface already present in the lane. The
   Orchestrator first writes a **contract seed** for such a ticket and commits it to the lane.

   The seed is four things: the minimal Interface, its result and error types, one real caller, and
   the happy-path contract tests the ticket states. A real caller means one on the shipped path; a
   test-only composition is what the seed exists to prevent, because it lets an Interface be shaped
   by nothing but its own tests. The seed commit stays in the ticket's lane and is never collected
   on its own: it is a starting position, not a deliverable, and collecting it would land an
   Interface with no implementation behind it.

   Contract preparation is complete when the lane contains the committed contract that the remaining
   implementation must fill. A ticket that only fills behavior behind an Interface already present in
   the lane needs no seed and completes this step as-is. Repeated same-shape blocks against one ticket
   reveal a missed contract-bearing case after the fact: its writer rebuilt a boundary from the code
   and the reviewer could only block local symptoms.

   The seed needs no protected-path list. Once it is in the lane it is what the ticket's `## Seam
   contract` names, so the later writer's existing obligation covers it: an `Existing` candidate
   preserves the named authorities, a `Change` candidate implements only the recorded `S#` deltas,
   and a required change to either returns `NEEDS_DECISION` rather than an edit. A second list of the
   same boundary would read as a guarantee while enforcing nothing.

   **Step 2 — Place the remaining implementation.** Start from the committed seed, or from the lane
   that needed none, and evaluate only the work left inside that contract. Placement now answers two
   independent questions: who writes that remainder, and who verifies it.

   **Who writes the remainder.** A dispatched implementer is cheap and literal: it succeeds where
   scope is closed and the steps are concrete, and drifts where the work needs judgement no brief can
   carry. So two shapes of remaining work stay with the Orchestrator — the change small enough that
   describing it costs about as much as making it, because the brief would have to state the change
   itself to be intelligible, and the change hard enough that no closed brief would carry it.
   Otherwise dispatch a writer.

   Both shapes are usually predicted. Two arrive already observed. **Three of one ticket's
   implementer runs ending anywhere but an accepted lane** — a `COMPLETED` the reviewer then
   blocked, or a run that timed out — is the second shape measured rather than guessed: the brief
   has failed to carry that work three times, so the ticket's remaining work is yours to write. A
   timeout counts because it is the same failure wearing a different result. Three is sufficient,
   not necessary; a ticket can be too hard on its first return. **Deferred work** is the first
   shape: a path the writer rejected and the user later asks for is small by construction and
   arrives while the user is watching, so describing it costs about what making it costs.

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

   This boundary is complete when contract preparation is complete, the remaining implementation has
   one writer with one bounded contract and one safe writable checkout, verification placement is
   decided, and the repository-declared bootstrap has run when the repository requires one.
3. **Implement and review.** Execute the chosen shape; for delegated closed work that places a
   reviewer, prefer runtime composition of worker, reviewer, and bounded correction under a finite Orchestrator-supplied
   correction budget. The runtime pointer carries the registered composition path
   and its terminal outcomes. Generic Acceptance below reviews the protected current lane. This
   step is complete when the lane carries a worker result and, where boundary 2 placed a reviewer, an
   independent review result — or a terminal blocker or decision request.
4. **Judge the result.** The Orchestrator makes the final Acceptance judgement, and makes it by
   rebuilding the ticket's Acceptance list from what each claim's deciding observer reported — the
   gates that ran, the reviewer's verdict, your own reading, the user's answer. The writer's
   checkboxes are progress notes and settle nothing, so there is no sweep to date and nothing to
   compare against the lane head. Then choose what follows: accept the judged lane, return a bounded defect for correction, return a decision
   request or exhausted correction budget to its owner, or select another shape. A correction the
   Orchestrator itself dispatches returns to boundary 2, so placement is decided once per dispatch
   rather than once per ticket; a correction inside a composed loop is the loop's own and returns to
   boundary 3, because that loop's placement was fixed when it was composed. When the task owns an integration branch, an
   accepted lane goes to the collection boundary below before its lane retires. This step is
   complete when the Orchestrator accepts the result or identifies the unresolved decision and its
   owner.
5. **Collect.** Before moving anything, assemble the ticket's **deferred paths** — the rejections
   its writer left a comment beside, and the reviewer's `residualRisks` — into `<ticket>/deferred.md`,
   which sits in the ticket directory the way its `scripts/` subtree does and needs no separate
   grant. Put the entries named by neither the ticket's `World facts` nor its `Not doing` in front of
   the user: those are the ones no alignment covered, so this is the first moment the user could see
   them, and what they ask for becomes deferred work you write under boundary 2. Then move the
   Orchestrator-accepted current lane into the integration branch one lane at
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

**Gates.** dev-flow's [ticket template](../dev-flow/templates/ticket/ticket.md#mechanical-gates) gives the ticket
the ordered binary gate plan and requires every listed gate to pass before `COMPLETED`. The implementer fixes failures within scope in the order that
ticket section states, or the default its own profile carries when the section states none, and
returns one complete `BLOCKED` result when closure exceeds authority. Ticket-owned gates are validated by the implementer and proved only by lane state;
reviewed roles neither re-execute them nor reopen run artifacts to judge them. Judging gate integrity from the lane diff alone is not re-execution.

A worker result uses one exact branch contract:

- `COMPLETED`: required `outcome`; optional `residualRisks`, `efficiencyFeedback`.
- `BLOCKED`: required `outcome`, `blocker`; optional `residualRisks`, `efficiencyFeedback`.
- `NEEDS_DECISION`: required `outcome`, `decision`, `decision.why`, `decision.question`; optional
  `residualRisks`, `efficiencyFeedback`.

**`COMPLETED` is a binary attestation** that the required gates passed. It does not attest
Acceptance: dev-flow's
[lane-authority](../dev-flow/references/lane-authority.md#every-claim-names-the-observer-that-decides-it)
gives every claim a deciding observer, and the Orchestrator reads those observers at boundary 4. It
carries no free-text `Validation` array and creates no durable receipt. Ordinary gate
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
clean, and the reviewer reads its current state directly, read-only. Bash use is limited to read-only retrieval (`git diff`, `git show`, `git status`, `git log`, `rg`, `grep`, `find`, Grove); it excludes pytest, type/lint/format gates, Python/import probes and runtime/process workflows. The reviewer does not execute mechanical gates; it judges ticket gate coverage, the Acceptance claims no gate proved, and gate integrity. **Gate integrity**: a gate's pass is part of the lane under review, and when the lane obtains that pass by changing what the gate measures, the pass is hollow and the lane is `BLOCKED` — no Acceptance claim need have been violated, because the violated expectation is the ticket's own gate entry. Reading the lane diff for the two shapes this is bounded to — a test or assertion whose subject changed inside this lane, and an added construct whose only effect is to silence a checker — is not re-executing a gate. Beyond those two shapes a hollow pass is unobservable to a read-only role, so it is not pursued.

A reviewer result uses one exact branch contract:

- `PASS`: required `verdict`; optional `residualRisks`, `efficiencyFeedback`.
- `BLOCKED`: required `verdict`, `blockers`, `blockers[].where`, `blockers[].why`,
  `blockers[].howToFix`, `blockers[].trigger`, `correctionBase`; optional `residualRisks`,
  `efficiencyFeedback`.
- `NEEDS_DECISION`: required `verdict`, `decision`, `decision.why`, `decision.question`; optional
  `residualRisks`, `efficiencyFeedback`.

Each `blockers[]` item carries the affected location in `where`, the violated ticket expectation or
Interface promise plus direct evidence in `why`, a bounded advisory suggestion in `howToFix`, and the
concrete production-reachable input or call sequence plus existing entry point in `trigger`. For a
hollow pass these fields name the ticket's Mechanical gate, its invocation, and the property it no
longer measures. A mechanically decidable blocker also names the gate that should have caught it.

For `NEEDS_DECISION`, `decision.why` states why a decision is needed and `decision.question` asks the
exact question. The question may itself propose where a seam belongs and what it would carry; the
Orchestrator designs and decides. `residualRisks` is optional and carries all non-blocking codebase
findings, whether inside or outside the envelope; omit it when empty.

A hollow pass is the only blocker class that may omit a production-reachable input; it substitutes the entry point and trigger named above. Every other safety or non-happy-path blocker must be production-reachable under the stated operating assumptions: identify the existing production entry point, a concrete reachable input or event sequence, the current observable failure, the violated Acceptance or Interface promise, and the smallest requirement-compliant bounded fix. When Acceptance does not require recovery, tolerance, fallback, compatibility or graceful degradation, safe explicit rejection or Fast Fail is complete; a reviewer demanding more must prove why Fast Fail violates a named promise, using
bounded advisory fixes that stay inside the ticket's stated outcome rather than expanding scope via
robustness or future-proofing. A finding that depends on a wider operating model than the dispatch declared is reported via residual risks, not as a blocker.

A `PASS` ends after `verdict` and any `residualRisks`; it needs no empty filler. The verdict is a
review result, not ticket Acceptance: the Orchestrator owns the final judgement and closure.
`NEEDS_DECISION` returns a contract contradiction or new-scope question to the Orchestrator instead
of routing rework. Generic Acceptance carries no fixed-subject result fields and no `correctionBase` projection; public terminal results never expose the internal base. Specialized procedures such as [code-review](../code-review/SKILL.md) keep their own identity
contracts and produce separate Standards/Spec findings rather than a PASS/BLOCKED Acceptance verdict.

When delegated red/green validation needs several commands, a fixed working directory, or owned
temporary state, use [TDD Gate mode](../tdd/gate.md). Keep a one-command loop direct.

## Review placement and the correction loop

Boundary 2 decides whether a reviewer is placed, at every dispatch the Orchestrator issues. This section governs the review once one is.

**Blocks are a signal addressed to no one, so read them yourself.** A reviewer measures one candidate
against a fixed contract and has no standing to say the contract was a good one, so it will never
tell you that what it keeps blocking should not have been asked for. That leaves the diagnosis to
you: gates carry the mechanical mass, so a first review should return few small blockers, and one
returning several independent blocker classes says the gate list or the ticket's width was drafted
wrong. Repair the ticket rather than spending another correction against it. The cap below bounds
what this costs when you miss it.

**A reviewer request the contract does not carry is sized by surface, not by lines.** When a
finding names neither an Acceptance claim nor something the user asked for, ask what satisfying it
would take: staying inside the seams already in place, adding no public item, and touching no `S#`,
`A#` or write scope makes it ordinary work — do it, or defer it under the writer's own rejection
rule. Needing any one of those makes it a design question, and the ticket stops at the user rather
than absorbing another round. Count only newly public surface — a new module, seam, public method,
parameter, or cross-module call; changing the inside of an existing one is not that. Line count is a
weak proxy that misses the case this rule exists for: a forty-line function spread across six
modules is the expensive one, and it passes any threshold you would set.

Reviewer placement may be composed by the runtime or an external workflow. For delegated closed work
— bounded brief, delegated Acceptance criteria, placement, mutation authority, and escalation
boundary all closed — prefer a runtime-composed worker → reviewer → bounded correction loop that
consumes one terminal handoff: a reviewed lane, a worker blocker, a decision request, or an
exhausted correction budget. The Orchestrator supplies a finite correction budget per composed
workflow, `2` by default and overridable by a task's own standing order; initial implementation does not consume it, each `BLOCKED → writer correction` transition
consumes one, and exhausting it returns the ticket to the Orchestrator under [cutting a ticket
off](../dev-flow/SKILL.md#cutting-a-ticket-off). A budget with no defined exit is what lets a loop
keep spending: the count bounds the dispatch, and that reference owns what happens once it is
spent.

**Three blocks is where a ticket stops buying review.** At the default budget the third block already
ends a loop: initial implementation consumes nothing, the first two `BLOCKED` verdicts each buy a
correction, and the third arrives with no slot left. The cap makes that the ticket's ceiling rather
than one dispatch's, because a fresh dispatch would otherwise hand the same ticket two more blocks
against a count the runtime no longer holds. Past the third, place no reviewer for that ticket: the
remaining work finishes against its gates, and the claims a reviewer would have decided stay
unproved and are recorded as such. dev-flow's [reviewer block
ledger](../dev-flow/references/record-hygiene.md#the-reviewer-block-ledger) is where the count
survives the run, and [cutting a ticket
off](../dev-flow/SKILL.md#cutting-a-ticket-off) owns the terminal state it produces.

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
