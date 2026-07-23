---
name: dev-flow
description: Route a heavy effort through frozen planning, v119 orchestrate implementation, and evidence-based acceptance.
---

# Dev Flow

Use this skill for work that needs a frozen contract and more than one session. It
navigates the outer pipeline; each station owns its own contract and runtime details.

## Pipeline

```text
wayfinder → to-spec → to-tickets → orchestrate → acceptance → landing → close-out
```

The orchestrate station publishes an exact Implementation candidate. Acceptance does
not create another workflow ledger and does not replace Git as durable truth.

## v119 acceptance order

For every candidate, run **simplify**, then the **canonical tests**, then one
**clean-detached code-review** of the **post-simplify exact SHA**. The final review must
inspect that exact SHA from a clean detached checkout; never review a moving worktree or
an earlier pre-simplify commit.

A review result of `needs_fix` returns to the **same Wave**. A Spec or behavior finding
returns through Oracle and then Implementation in that Wave, beginning with an executable
contract regression. A quality finding returns directly to Implementation. After a fix,
repeat simplify, canonical tests, and a new exact-SHA clean-detached code-review before
landing.

The contract tests and fixtures are immutable during simplify and throughout Implementation.
Role identities and each role worktree are retained through acceptance and landing;
close runtime identities before removing clean worktrees.

## Minimal handoff

The orchestrate handoff is a small exact-SHA tuple containing the exact base SHA,
Implementation SHA, frozen spec, task plan, canonical test results, and Git profile JSON.
It is handed off without a receipt and without a finding bundle; those are not dev-flow state.

The landing action is outside orchestrate and requires current user authority under repository policy.
After authorized landing, close the role identities, remove clean worktrees, and delete
integrated role branches directly according to that policy.

## Effort close-out

After landing, close the wayfinder map, record durable decisions, move out-of-scope
ideas to the candidate backlog, archive the task plan, and report the final destination
and residual risks. Do not invent state files to represent this navigation.
