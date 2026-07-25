---
name: dev-flow
description: Route a heavy effort through frozen planning, v122 orchestrate implementation, and evidence-based acceptance.
---

# Dev Flow

Use this skill for work that needs a frozen contract and more than one session. It navigates the outer pipeline; each station owns its own contract and runtime details.

## Pipeline

```text
wayfinder → to-spec → to-tickets → orchestrate → acceptance → landing → close-out
```

The orchestrate station publishes an exact Implementation candidate. Acceptance does not create another workflow ledger and does not replace Git as durable truth. Workflow evolution reads [design principles](references/design-principles.md).

## v122 acceptance order

At an integration milestone candidate, run **simplify**, then the **canonical tests**, then one **clean-detached code-review** of the **post-simplify exact SHA**; never review a moving worktree or an earlier pre-simplify commit. The candidate is the integration tip. The review reads the whole committed `base..integration-tip` range, because cross-authority composition defects are only visible in the assembled picture; simplify reads only the increment since the last reviewed SHA, because accepted code cannot acquire new hygiene problems. The asymmetry is deliberate. At acceptance entry the exit condition is frozen. Between milestones each Wave passes only machine gates before collect; the expensive review context is spent once on the accumulated diff, never per Wave. Land exactly the reviewed SHA; a later commit reopens the gate.

Blocking is closed to spec violation, data loss, security, or reproducible behavior failure within the frozen spec's usage envelope. The final review must not expand the frozen spec; a finding without a contract basis in the frozen spec is backlog, never a blocker. Robustness, quality, and out-of-envelope findings go through `candidate-backlog` and do not block landing. Do not implement features the frozen spec does not require.

Routing is fixed below; cost judgement stays with Root. Minimize Wave round trips: batch
everything known at the same moment into one cycle — one Oracle correction carries all
current Spec findings, one Implementation pass carries all fixes. Spending a cycle on a
single finding while others are already known is a defect, not diligence.

```text
exit: full canonical suite green ∧ review has no blocking finding
      → land immediately, add nothing

for each review finding:
  not blocking (closed enum + contract_basis)   → backlog, continue
  mechanical Contract-surface slip (import/
           format/typo ∧ AST + collected node
           IDs unchanged)                       → Root applies the reviewer patch, merges
                                                  the Contract, records an explicit empty
                                                  Implementation handoff on that branch after
                                                  the merge, reruns only
                                                  collection, lint, and directly affected
                                                  tests; consumes no correction budget
  bounded (≤~30 lines local logic ∧ known seam
           ∧ direct contract test exists)       → fast path: Root or current single
                                                  writer fixes directly; focused tests;
                                                  re-review only the delta from the
                                                  previously reviewed SHA
  otherwise                                     → needs_fix returns to the same Wave
                                                  (consumes budget): a Spec or behavior
                                                  finding goes through Oracle then
                                                  Implementation, starting from an
                                                  executable contract regression; a
                                                  quality finding returns directly to
                                                  Implementation. After a fix, regenerate
                                                  the Git profile output, then simplify +
                                                  canonical tests + a new exact-SHA
                                                  clean-detached code-review

budget per acceptance cycle: 1 Oracle Contract correction, 1 Implementation fix,
                             1 focused suite, 1 full suite, 1 detached review
budget spent → stop; reassess scope and the shortest convergent path; the next cycle
               batches all remaining findings under the same acceptance record — never
               auto-loop per finding
```

A collected Wave is closed: a milestone finding is routed to the Wave owning the defective surface, but the correction runs as a new Wave based on the integration tip and collects again, and a finding spanning several Waves is always a new Wave. Run focused tests during modification; run the full canonical suite once only after focused green on a clean writer tree. Split the reruns: the writer produces the contract-suite and focused evidence, Root reruns only the machine gates before collect, and the full canonical suite runs once per milestone — never rerun an expensive suite that a clean exact SHA already covers. If a background writer's wait time exceeds Root's own estimate for a bounded fix, Root stops that writer and takes over directly. Full Wave ceremony is reserved for new seams, cross-authority changes, or an untrusted writer.

Maintain one update-in-place acceptance record per release with candidate SHA, blockers, focused/full gate results, review verdict, deployment, and cleanup; it lives in the task plan as a phase record, never in a new state file, and does not create overlapping review/simplify artifacts per round.

The contract tests and fixtures are immutable during simplify and throughout Implementation. Role identities and each role worktree are retained through acceptance and landing; close runtime identities before removing clean worktrees.

## Minimal handoff

The orchestrate handoff is a small exact-SHA tuple containing the exact base SHA, Implementation SHA, frozen spec, task plan, canonical test results, and Git profile JSON. It is handed off without a receipt and without a finding bundle; those are not dev-flow state.

The landing action is outside orchestrate and requires current user authority under repository policy. After authorized landing, close the role identities, remove clean worktrees including the integration worktree, delete integrated role and integration branches, and delete the task's `refs/orchestrate/<task-id>/` namespace directly according to that policy.

## Effort close-out

After landing, close the wayfinder map, record durable decisions, move out-of-scope ideas to the candidate backlog, archive the task plan, and report the final destination and residual risks. Do not invent state files to represent this navigation.
