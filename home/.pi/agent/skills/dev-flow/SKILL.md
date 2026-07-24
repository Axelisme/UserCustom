---
name: dev-flow
description: Route a heavy effort through frozen planning, v119 orchestrate implementation, and evidence-based acceptance.
---

# Dev Flow

Use this skill for work that needs a frozen contract and more than one session. It navigates the outer pipeline; each station owns its own contract and runtime details.

## Pipeline

```text
wayfinder → to-spec → to-tickets → orchestrate → acceptance → landing → close-out
```

The orchestrate station publishes an exact Implementation candidate. Acceptance does not create another workflow ledger and does not replace Git as durable truth.

## v119 acceptance order

For every candidate, run **simplify**, then the **canonical tests**, then one **clean-detached code-review** of the **post-simplify exact SHA**. The final review must inspect that exact SHA from a clean detached checkout; never review a moving worktree or an earlier pre-simplify commit. At acceptance entry the exit condition is frozen: **full canonical suite green + exact-SHA clean-detached review with no blocking finding → landing immediately**.

Blocking is closed to spec violation, data loss, security, or reproducible behavior failure within the frozen spec's usage envelope. The final review must not expand the frozen spec; a finding without a contract basis in the frozen spec is backlog, never a blocker. Robustness, quality, and out-of-envelope findings go through `candidate-backlog` and do not block landing. Do not implement features the frozen spec does not require; defenses beyond the usage envelope go to the candidate backlog.

A blocking `needs_fix` returns to the same Wave only when the fix is Wave-scale. Spec or behavior correction returns through Oracle and Implementation, beginning with an executable contract regression; Root-elected quality cleanup remains non-blocking and returns directly to Implementation. After a fix, regenerate the relevant Git profile output, then repeat simplify, canonical tests, and a new exact-SHA clean-detached code-review before landing. This full ceremony is reserved for new seams, cross-authority changes, or an untrusted writer.

Proportional fast path: if the correction is roughly ≤30 lines of local logic, touches only a known seam, and already has a direct contract test, Root or the current single writer fixes it directly. Run focused tests during modification; only after focused green and a clean writer tree run the full canonical suite once. Re-review only the incremental diff from the previously reviewed SHA to the new SHA. If a background writer's wait time exceeds Root's own estimated completion time for such a bounded fix, Root stops that writer and takes over directly.

Default correction budget per acceptance cycle is one Oracle Contract correction, one Implementation fix, one focused suite, one full canonical suite, and one clean-detached review. When the budget is spent, Root stops and reassesses scope plus the shortest convergent path; do not auto-loop. Maintain one update-in-place acceptance record per release with candidate SHA, blockers, focused/full gate results, review verdict, deployment, and cleanup; do not create overlapping review/simplify artifacts per round. Once live tracer evidence has proved the core workflow, dogfood is complete; release corrections use the shortest verifiable single-writer path, not forced dual-role ceremony.

The contract tests and fixtures are immutable during simplify and throughout Implementation. Role identities and each role worktree are retained through acceptance and landing; close runtime identities before removing clean worktrees.

## Minimal handoff

The orchestrate handoff is a small exact-SHA tuple containing the exact base SHA, Implementation SHA, frozen spec, task plan, canonical test results, and Git profile JSON. It is handed off without a receipt and without a finding bundle; those are not dev-flow state.

The landing action is outside orchestrate and requires current user authority under repository policy. After authorized landing, close the role identities, remove clean worktrees, and delete integrated role branches directly according to that policy.

## Effort close-out

After landing, close the wayfinder map, record durable decisions, move out-of-scope ideas to the candidate backlog, archive the task plan, and report the final destination and residual risks. Do not invent state files to represent this navigation.
