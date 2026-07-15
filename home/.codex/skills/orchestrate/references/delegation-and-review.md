---
orchestrate_compat: 54
---

# Delegation and review

Read this reference before the first agent action, assigning roles, or requesting/closing a
review. Then read `../runtime-<runtime>.md` completely for the current runtime's actual
spawn/follow-up/interrupt/wait capabilities. Runtime tools, not config files, determine what
is available.

## Persistent agents and roles

- **Domain lease.** The next slice in the same domain returns to the same agent by default as
  a follow-up carrying only the delta: current SHA, finding/next slice, and scope changes.
  Spawning a new identity requires a reason: independent review, changed domain, or genuinely
  parallel scope. A completed turn or commit does not end ownership.
- Finding fixes return to the original implementer. Finding closure and refreshed-SHA review
  return to the original reviewer.
- **Warm reviewer lease.** Pause and resume a warmed reviewer; do not respawn it. Warm-up
  produces exactly four artifacts: source map, acceptance/adversarial matrix, stop conditions,
  and deletion checklist. Formal review reuses them and adds exact-diff inspection.
- If same-identity continuation is needed but the runtime cannot provide it, return
  `needs_decision`; never silently rebuild context in a fresh identity.
- Roles: `contract-planner`, `repo-investigator`, `implementer`,
  `mechanical-implementer`, `reviewer`, `integration-reviewer`; `web-researcher` and
  `mcp-skill-tester` as needed. Read-only discipline is behavioral. A reviewer may need a
  detached workspace-write checkout for gates; the invariant is reviewed-SHA immutability.
- Root plans inline by default. Use `repo-investigator` for a deep factual question and
  `contract-planner` only when contract/write split has not converged and the reading is too
  deep for root, a critical derivation needs independent anchoring, or planning can converge
  during the current wave. Planner output is evidence; root freezes the decision.
- Profiles may read content skills such as `codebase-design` or `domain-modeling`. They never
  invoke coordination skills that spawn agents or re-derive dispatch inputs. Root names any
  desired coordination lens in `reviewer_focus`.

## Review depth

Classify the checkpoint's changed surface, not the task's maximum global risk:

- **Hard-critical** — a diff crossing `hard_critical_axes` (hardware,
  persistence/migration, public wire schema, security): one mandatory different-identity
  reviewer over that diff.
- **Named review risk** — a task-scoped `named_review_risk`: root explicitly chooses extra
  depth, identity, and waiting. It may mirror hard-critical treatment but never expands the
  closed list.
- **Normal** — internal presenters, adapters, GUI glue, private lifecycle: one focused review
  or a root self-review with a one-line rationale.
- **Mechanical** — deletion, rename, fixture move, docs wording: root spot-checks scope, tree
  identity, and a targeted scan; no reviewer dispatch.

The two-agent `code-review` skill is a Standards/Spec milestone audit that root runs only
when requested or materially justified, never automatically per slice or by a sub-agent.

## Evidence ownership

Root/planner freezes test seams, acceptance examples, independent oracles, and dangerous
failure modes. Writer owns permanent executable tests, functional acceptance, and affected
regression. Reviewer owns the adversarial matrix, temporary reproducers, finding-specific
probes, and source audit — not a parallel permanent-test lane or habitual rerun of writer
suites. A missing behavior returns to the writer for a failing permanent regression before
the fix. Root owns SHA/parent/scope/tree-identity checks and at most one thin critical slice.
Integration owns the single repo/risk-required broader gate. Duplicate evidence needs a
stated reason such as suspected environment skew.

## Review-readiness packet

Before dispatching a frozen diff, root sends a compact in-band **review-readiness packet**;
trim only fields that truly do not apply:

```text
base_sha: <review base>
target_sha: <exact immutable SHA>
frozen_contract: <task-plan / ADR pointer plus required invariants>
hard_critical_axes: <hardware / persistence / public wire / security / none>
named_review_risks: <task-scoped risks plus chosen depth/identity/waiting / none>
changed_surface: <paths, seams, lifecycle or wire behavior>
acceptance_and_evidence: <targeted commands and results>
known_anomalies: <exact failed command, classification, replacement evidence>
invalid_substitutes: <old-SHA reviews, partial suites, unproved tree equivalence>
reviewer_focus: <dangerous failures and explicit non-goals>
```

Missing base/target SHA, frozen contract, or changed surface is a readiness failure, not an
invitation for the reviewer to reconstruct the task. Name the dangerous failure for every
hard-critical axis and named review risk. Old-SHA review, aborted suites, or incomplete
tree-equivalence proof never become target-SHA sign-off.

## Re-review and immutable execution

- Re-review is finding-focused: the finding delta plus its high-risk adjacent surface. Start
  a fresh full review only when rework changes authority, persistence, public schema, or
  process lifecycle. Docs-only closure checks current wording, links, and negative scans.
- One checkpoint gets one full review and one focused closure. A new P1 in round three means
  the contract, source map, or test model is wrong: stop patching and re-freeze. Two rounds of
  one failure family (for example lifecycle races) likewise trigger a test-model correction.
- Execute review gates only from immutable checkouts: `git show`/`git diff` for reading, or a
  detached temporary worktree at the exact SHA. A live-writer checkout voids the evidence.
  Only an announced clean **review checkpoint** starts a gate; a dirty progress/code
  checkpoint does not.
- Reviews attach to exact SHAs. After collection, if the integration tree should equal the
  reviewed lane, prove it with `git diff --quiet <lane-sha> <integration-sha>`. If trees
  differ and a critical surface may have changed (or unchanged content cannot be proved),
  review the integration SHA; otherwise record a concise root self-review rationale. A
  conflict-free merge alone is not equivalence.
