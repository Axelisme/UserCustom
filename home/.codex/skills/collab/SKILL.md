---
name: collab
description: "Orchestrator coordination for one bounded implementation: use when the Orchestrator places a writer, selects a review procedure, resolves a correction handback, collects, or lands."
---

# Collab

Collab coordinates one bounded change without owning a durable lifecycle. The Orchestrator retains task
intent, acceptance criteria, final Acceptance judgement, and every scope or authority decision.

**This is the Orchestrator's document; the agent profiles are the workers'.** Writer placement, review
placement, collection, and landing are decided here, by the Orchestrator. A dispatched writer or reviewer
carries out one bounded brief inside those decisions, working from its own profile.

## Load-bearing objects

Define each at its first use:

- **Orchestrator** — the agent that holds task intent and every scope or authority decision,
  dispatches writers and reviewers, and never writes the subject itself.
- **Integration branch** — the task-local cumulative result already accepted by the Orchestrator. This is
  the only meaning `accepted` needs here.
- **Lane** — one writable branch, checkout, worktree, and its lane-owned temporary state, assigned
  to one live writer at a time. A lane is an execution resource, not durable narrative.
- **Fixed subject** — the immutable state under review; a Git-backed subject is an exact commit and
  tree. A branch name, `HEAD`, diff summary, or agent claim is not a fixed subject.
- **Review result** — findings or a verdict tied only to its fixed subject.
- **Collect** — movement of the Orchestrator-accepted lane subject into integration without introducing
  another subject.
- **Land** — movement from task integration into a persistence branch.

## Core guardrails

1. **One writer at a time per checkout.** This is concurrent exclusivity, not a lifetime binding:
   a checkout carries one live writer, and reassigning it once that writer's run is over is not a
   second writer. That checkout is the lane. Parallelize read-only work; give each concurrent
   writer a separate writable checkout.
2. **One fixed subject per review result — a verdict is a single-use pass.** Identify the subject
   with an exact clean Git commit and tree, or an immutable runtime handoff that resolves to one
   state.
3. **A changed subject voids the pass.** Corrections return to implementation and review as a new
   fixed subject needing its own review result. Exception: a change confined to state that a
   declaring skill marks as non-shipping scaffolding does not void an existing verdict, when the
   Orchestrator confirms the confinement each time.

These are the universal collaboration invariants. All other placement and procedure choices depend
on the bounded change.

## Suggested sequence

The sequence below is suggested guidance for one bounded change.

1. **Bound the change.** Give the writer the goal, write scope, constraints, expected result,
   validation, and stop conditions. Carry needed conclusions inline; point to supporting material
   with the condition for opening it. Before dispatch, inspect the selected receiver profile's
   `Preconditions` and `Result` sections and close every required value, path, mutation authority,
   evidence owner, and stop condition in the brief. This step is complete when the writer can
   distinguish in-scope implementation from an Orchestrator decision and every receiver field is supplied.
2. **Place the writer.** Preserve one live writer per writable checkout and account for pre-existing
   state. Isolate when another writer is active or existing work needs protection. **Runtime
   pointer:** before dispatching a writer, before collecting a lane (step 6), or before landing,
   read this skill directory's `runtime-<name>.md` for your runtime when one exists; it carries
   that runtime's dispatch, limit, resume behaviour, and the operations that carry out collection
   and landing. A runtime needs no file when ordinary generic means — plain git and ordinary agent
   dispatch — already carry out everything the core states above; the core is then directly
   actionable as written. Treat any other absence as unwritten rather than as license to proceed:
   if your runtime works through specialized tooling the core does not name (an extension, a
   dedicated API) and no `runtime-<name>.md` documents it, stop and ask before guessing its
   mechanics. This step is complete when the writer has one bounded brief and one safe writable
   checkout.
3. **Implement and identify.** The writer returns the fixed subject identity, changed paths, the
   validation outcome with the artifact holding its evidence, and residual risks, or a specific
   blocker or decision. This step is complete when the subject and its evidence are attributable to
   one immutable state.
4. **Review the fixed subject.** The Orchestrator selects a review procedure — generic Acceptance below
   or the specialized [code-review](../code-review/SKILL.md) — and its placement. Use a separate
   read-only checkout when the writer may continue concurrently, validation may write temporary
   state, or review duration would lock the writer checkout. Serialized protected, non-mutating
   review may use the writer checkout. This step is complete when the chosen procedure returns a
   review result tied to the unchanged subject.
5. **Resolve the result.** The Orchestrator makes the final Acceptance judgement and selects the next
   owner. Send a bounded defect for correction; return new scope, product, architecture, or
   authority decisions to the Orchestrator. A correction returns to step 3. When the task owns an
   integration branch, an accepted lane subject goes to the collection boundary below before its
   lane retires. This step is complete when the Orchestrator accepts the result or identifies the
   unresolved decision and its owner.
6. **Collect.** Move the Orchestrator-accepted lane subject into the integration branch one lane at a
   time, without creating another subject. A stale lane is synchronized with current integration
   first and stops at the new subject or conflict state; that new subject needs its own review and
   Orchestrator judgement. This step is complete when the accepted subject is the integration head and
   its lane is retired or its retention is reported.
7. **Retire the lane.** When a writer or reviewer lane reaches its terminal handoff and will not
   resume, inventory and remove its lane-owned worktree registrations, temporary files or
   directories, sessions or processes, and agent-created branches that no longer carry required
   subject evidence. Preserve pre-existing user state and evidence still needed for Acceptance or
   landing; give every deliberate retention an owner and discharge condition. This step is complete
   when no orphaned lane-owned resource remains.

## Continuity is a cache

Evidence carries continuity: the bounded brief, fixed subject, direct observations, and validation
results. Reusing the same writer or reviewer can preserve useful context and diagnosis, but it is a
context-cache optimization rather than a liveness or authority requirement.

**Resume before replacing.** When a writer's run ends before its work does, resume that session
first; it keeps working context that no record holds. Treat resume as unavailable only after
confirming it, because an agent that looks unresponsive is often compacting and recovers on its own.
Replace when resume is genuinely unavailable, or when prior context anchors a rejected approach and
has become debt; give the replacement the evidence, not unverified role narration.

**A replacement reads its ticket, not the task.** Its context is that ticket and whatever the ticket
points to; the task record and sibling tickets belong to the Orchestrator, and handing them over invites
scope creep. The ticket therefore names the next single step and the unverified boundary — which
edits are validated, which are not, and what must not be redone or widened. A ticket that leaves the
replacement to re-derive those is an unfinished brief, not a terse one.

**Mechanical finish.** When a run ends after its semantic work is validated but before the checkout
is clean and committed, and resume is confirmed unavailable, dispatch a fresh writer for that
close-out alone: no semantic edits, lane-owned temporary state removed, staged paths and diff
inspected, ancestry checked, one clean commit. Its result is still a fixed subject and still needs
a review result.

## Validation evidence has one owner

The writer's validation artifact owns the commands, their results, and the subject identity they
ran against. The ticket points to it, the task record points to it, and nobody restates it. A
changed subject appends a new attempt carrying its own identity and leaves earlier attempts
untouched: a receipt that is edited no longer attests to anything. Reviewers consume that artifact
and return a review result; the Orchestrator records it where the task's durable judgement lives.

## Generic Acceptance

A generic acceptor works read-only against the exact fixed subject and returns only, in this
order:

- `Verdict`: `PASS | BLOCKED`
- `Subject`: exact identity reviewed
- for each blocker:
  - `Where`: the affected location
  - `Why`: the violated ticket expectation or Interface promise, plus direct evidence
  - `How to fix`: a bounded advisory suggestion

A `PASS` ends after Verdict and Subject; it needs no empty filler. Common labels such as
correctness, regression, validation, scope, or their aliases may aid scanning, but the vocabulary
is non-exhaustive and never replaces Why. The verdict is a review result, not ticket Acceptance:
the Orchestrator owns the final judgement and closure. A fix that needs a new product, scope,
architecture, or authority decision goes back to the Orchestrator.

When delegated red/green validation needs several commands, a fixed working directory, or owned
temporary state, use [TDD Gate mode](../tdd/gate.md). Keep a one-command loop direct.

## Review placement and the correction loop

Reviewer placement may be composed by the runtime or an external workflow. One shape that fits a
single bounded change is a worker → reviewer → bounded correction loop: the Orchestrator supplies a
bounded brief, the delegated Acceptance criteria, and the escalation boundary, then consumes a
terminal handoff. The loop may route defects that stay inside the existing contract directly back
to the worker; scope, architecture, authority, or contract decisions terminate back at the Orchestrator.
Intermediate rounds stay in workflow context unless an observation independently justifies a
durable receipt.

Collab does not require a particular workflow engine, retry count, steering mechanism, merge
strategy, first-parent shape, review procedure, or independent reviewer. Specialized code-review
remains an alternative source of separate Standards/Spec findings rather than a PASS/BLOCKED
Acceptance verdict.

The terminal handoff carries the final fixed subject, the reviewed criteria, a verdict or the
decision that is needed, applicable direct observations, and residual risk. Orchestrator- and
user-observed Acceptance items are reported there rather than mislabelled as blockers.

## Collection boundary

When existing work becomes the managed integration, adoption previews its mutation before
authorizing it, and uses an existing branch as the complete managed integration state. It discards
changes from that integration when their lane has not been collected. It leaves any pre-existing
lane branch or worktree outside the adopted integration unless a separate lifecycle operation
retires it. The runtime pointer under "Place the writer" above names the operations that carry
these out and tells you when their absence means your runtime needs none.

The runtime verifies the exact lane tip, that current integration is contained in the judged
subject, and that managed refs and worktrees are clean and identity-exact, then advances
integration to the exact subject and retires the lane when it is clean. Dirt or ambiguity in the
lane is preserved and reported rather than deleted or inferred away.

This task-local collection is not landing and requires no separate landing grant.

## Land

Landing moves the exact current integration result into a user or product persistence branch such
as `feat/*` or `main`, preserving the integration tree under the new commit identity. Collab
creates no landing authority; stop at task integration unless a current user message or an
in-force task-scoped user grant authorizes landing under its stated conditions. When the
Orchestrator is running a dev-flow task, verify such a grant in dev-flow's [Custody
reference](../dev-flow/references/custody.md), which owns how the record holds user authority.
When landing is authorized and neither the user nor repository guidance names a method, default to
squash. Landing evidence applies only to the reviewed identity; a changed subject first needs a new
review result. The runtime pointer under "Place the writer" above names the operation that carries
out landing.

Land is the authority boundary Collab owns: its guidance ends once integration has moved into the
persistence branch. Push and later persistence-branch handling stay outside Collab.
