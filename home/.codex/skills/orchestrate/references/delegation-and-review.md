---
orchestrate_compat: 63
---

# Delegation and review

Read this before the first agent action or review decision, then read the matching runtime
binding. Runtime tools—not config files or this reference—define available identity,
continuation, parking, retirement, model, and sandbox capabilities.

## Roles and continuity

Root alone freezes work, grants authority, classifies deferral, and integrates. A role gets a
bounded objective, workdir/scope, basis, acceptance, stop conditions, checkpoint budget, and
either inline content, a dispatch-packet path/hash, or a spool binding.

Keep the same identity for the same domain when the runtime supports it. Finding fixes return
to the original implementer; finding closure and refreshed-SHA review return to the original
reviewer. Spawn a new identity for independent review, a changed domain, or genuine parallel
scope—not merely because a turn ended. Role switching requires a new profile bootstrap and
cannot make an identity independent from work it implemented.

Planner output is advice: contract resolution or a stocked chain of conditional wave
proposals. Root freezes it. Writers own scoped implementation and every internal design
decision inside the frozen seam, reporting notable ones in the milestone for post-hoc
recording. Reviewers are read-only with respect to the reviewed tree;
workspace write exists only for detached worktrees and test caches. Agents never spawn
coordination sub-agents or decide landing/finding deferral.

## Root contact discipline

After dispatch, root MUST NOT send progress or status prompts to a running assignee. Root
contacts it only for a public-contract correction, confirmed major finding, user override/stop,
or a liveness failure the runtime binding explicitly identifies. Short absence of tool or
filesystem activity is model reasoning, not a stall signal; the runtime binding owns liveness
recovery and its triggers are closed. Commentary obligations to the user never justify
contacting the assignee — report from the last milestone, read-only Git state, and the frozen
dispatch description. Dispatch a frozen bounded turn rather than drip-feeding a running
identity; routine additions merge into one spool batch, and only major finding, correction,
retract, or stop may interrupt directly.

## Evidence ownership

Evidence is intentionally non-duplicative:

- Root/planner freezes seams, acceptance examples, independent oracles, and dangerous failure
  modes.
- **Writer owns permanent executable tests**, functional acceptance, and affected regression.
- **Reviewer owns** source audit, adversarial matrix, temporary reproducers, and
  finding-specific probes—not a second permanent-test lane or habitual suite rerun.
- **Integration owns** SHA/parent/tree checks and the final repo/risk-required broader gate.

A missing behavior returns to the writer for a failing permanent regression before the fix.
Duplicate evidence needs a reason, such as suspected environment skew.

## Review depth and readiness

Review the checkpoint's changed surface:

| surface | default depth |
|---|---|
| mechanical | none, or root scope/tree spot-check |
| normal internal behavior | writer self-review + root spot-check — no independent identity |
| named review risk | cumulative independent review at explicitly chosen depth/waiting |
| critical boundary | enter [Critical review](critical-review.md) |

Cadence defaults to **cumulative**: one review closes a coherent surface or selected batch.
Per-slice review is the exception root must justify. Wait only where a declared dependency or
named critical barrier requires it; normal work runs ahead unreviewed. A queue entry never
creates review debt; root creates a review target by authorizing an exact immutable SHA.

A readiness packet—inline or via [dispatch packet](dispatch-packets.md)—names at least:

- base and exact target SHA;
- frozen contract/invariants and changed surface;
- hard axes/named risks and dangerous failures;
- acceptance evidence and known anomalies;
- reviewer focus/non-goals;
- findings/round context when closing prior review.

Missing target, contract, scope, or dangerous oracle is a readiness failure. Old-SHA review,
aborted suites, and unproved tree equivalence are invalid substitutes.

## Reviewer mental model

Inspect source/diff first. Run only thin adversarial commands from a detached checkout at the
target SHA; a live-writer checkout voids evidence. Challenge the oracle, ownership, lifecycle,
scope, and dangerous failures—green tests prove behavior, not that the seam is correct.

Report findings with severity, path, observable behavior, evidence, and propagation shape.
Root decides deferral. A confirmed major finding (P0/P1, contract invalidation, retract class,
or dangerous intermediate) is sent immediately so root can stop affected work; ordinary
findings stay in the target's one terminal milestone.

Normal re-review is finding-focused. Critical hostile proof, refreshed-review criteria, and
dependent-work release live together in [Critical review](critical-review.md). After collection,
prove reviewed/integration tree identity or review the integration SHA when reviewed content
may differ.

## Skill upgrades

Pin a role turn to the profile/dispatch it loaded. Adopt a new orchestrate version at a safe
boundary—before dispatch, after a milestone, or after turn completion. An immutable review
restarts only when the release changes an applicable hard rule, readiness condition, or
review meaning. Sub-agents never load orchestrate; root sends only the effective delta.
