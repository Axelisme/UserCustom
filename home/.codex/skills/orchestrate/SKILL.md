---
name: orchestrate
description: Act as the repo-wide orchestrator — plan, delegate to specialized agents, coordinate parallel worktrees, and integrate with verification proportional to risk.
skill_version: 60
---

# Orchestrate

Plan, delegate, integrate, and verify repo-wide work. Authority lives in three authoritative
carriers: **Git** (code/topology), **agent context** (active reasoning), and the **plan
directory** (cross-session narrative). One closed transport exception is the task-local
**durable delivery spool**: immutable, already-ready normal writer/reviewer items. It is
at-least-once delivery, not workflow authority. Queue absence is not completion evidence.

Root is the only control plane. The spool never represents readiness, validation,
review, findings, phase, collection, or landing and has no autonomous controller. Read-only
inspectors and explicit safety adapters may expose or mutate only their named primitive; they
never infer a transition. The ephemeral merge slot (lock + FIFO) likewise stores no task
state.

This skill is **root-only**: sub-agents do not load it. Standing role orders live in role
profiles; prompts carry the lease/binding and either an in-band item or an absolute spool
path. A rule a sub-agent needs belongs in its profile or prompt, never only here.

Except for the closed list below, these are defaults rather than a workflow state machine.
Choose the cheapest route that retires the actual uncertainty and state a non-obvious
deviation briefly.

## Hard rules (this is all of them)

1. A branch that has not passed targeted acceptance is not merged. Only the integration owner
   runs the **broadest gate required by the repo and risk**; task-scoped `pass` or qualified
   `baseline-relative` evidence must bind to the final integrated tree. Any later code change
   invalidates it by default.
   Lanes, writers, and reviewers do not duplicate that gate. If that is not the full suite,
   record the selected broader gate and rationale.
2. `hard_critical_axes` is the closed list **hardware operation, persistence/migration,
   public wire schema, security**; such diffs require different-identity review.
   `named_review_risks` are task-scoped review shaping and may choose the same depth, but they
   never expand the hard-rule list.
3. Persistence branches (`main`, feature branches) are never amended or force-pushed, and
   landing on them requires the user's explicit authority — always as one squashed commit
   through the merge slot. **MCCT** grants final merge authority for this task; push is not
   included.

## Routing fast paths

| changed surface | default execution | review / waiting |
|---|---|---|
| Q&A, read-only research, one-round review | root only; no branch or plan | none |
| mechanical batch | one writer and targeted checks | root spot-check; one final gate |
| normal single writer | task branch in the main checkout | root self-review unless a named risk justifies a reviewer |
| normal multi-slice wave (target 3–5; tail 1–2) | planner may draft one wave ahead; writer consumes a pre-authorized queue | validated writer run-ahead; cumulative/selected reviewer pipeline |
| structure-dependent foundation or named review risk | freeze one foundation checkpoint when needed | risk-shaped review/waiting |
| hard-critical diff | freeze one foundation checkpoint | review-before-next-slice; different identity required |

The two-agent `code-review` skill is a formal Standards/Spec milestone audit, used when the
user requests it or both axes carry material risk. It is never an automatic per-wave gate.

## Load only the branch you need

The entrypoint is deliberately bounded. Before acting on a branch below, read its linked file
completely; do not load references for branches the task does not enter.
Every loaded reference/runtime must declare `orchestrate_compat` equal to this entrypoint's
`skill_version`; `doctor` verifies the release manifest before complex work. A mismatch
returns `needs_decision` instead of mixing contracts. `diff` may narrow rereading only when
the current context can name the manifest version it already loaded; a new session reads each
triggered document completely.

| trigger | required reference |
|---|---|
| create/change task or lane branches, use worktrees, collect/delete lanes, or land | [Git coordination and landing](references/git-coordination.md) |
| spawn/follow-up/interrupt/wait for agents, assign roles, or request/close review | [Delegation and review](references/delegation-and-review.md), then the matching `runtime-<runtime>.md` before the first agent action |
| dispatch more than one role item, use planner/writer/reviewer pipelines, a finding ledger, or wave metrics | [Slice queues](references/slice-queues.md) |
| create, inspect, consume, recover, or rebind a filesystem role queue | [Durable delivery spool](references/durable-delivery-spool.md) plus Slice queues |
| a gate aborts/times out/crashes, the task needs durable narrative, or the session must hand off | [Evidence and handoff](references/evidence-and-handoff.md) |

Pure Q&A and root-only read work need no reference. A single-writer change reads Git
coordination only when branch or landing operations are actually needed.

## Operating loop

1. **Orient.** Read repo instructions and relevant module notes/ADRs; inspect Git status,
   current branch, worktrees, and any user-owned dirty state. When dispatching into an area,
   check its candidate backlog for same-scope riders without expanding scope.
2. **Freeze.** State objective, acceptance, non-goals, write scope, test seams/oracles,
   `hard_critical_axes`, `named_review_risks`, dependencies, and review cadence/waiting.
   Unfrozen contract or ownership is not writer-ready.
3. **Route.** Pick the fast path, load only its references, and choose root execution versus
   delegation. Same-file or same public contract/schema/fixture work stays serial.
4. **Execute.** Preserve user changes; keep useful work committed at coherent checkpoints.
   Root merges lanes serially. Findings return to their original implementer; refreshed-SHA
   closure returns to the original reviewer.
5. **Verify.** Run targeted evidence and review in proportion to the changed surface. The
   integration owner runs the repo/risk-required broader gate on the final tree; a failure or
   later code change requires a fresh final-tree run. Record the gate/rationale when it is not
   the full suite. Qualified baseline-relative evidence is usable but never called pass; an
   aborted or unusable gate is neither.
6. **Land and close.** Obtain explicit authority before persistence landing, squash once,
   clean task-owned worktrees/branches, update durable narrative/backlog when applicable, and
   report decisions plus evidence.

## Core coordination model

- **Main checkout** is the repo-root working directory — a place, not a branch — and normally
  the only checkout with the full environment.
- **Persistence branches** are `main` and user feature branches. Below them: persistence ←
  `task/<task>` (one integration branch per task) ← `agent/<task>/<lane>` (zero or more lane
  branches, one writer each). Task/lane history is mutable between safe checkpoints;
  persistence history is not.
- Single writer is the default. Use worktrees only for multiple writers, conflicting dirty
  state, or when the main checkout must stay available. One worktree has one writer at a
  time; root is the only merger.
- Git is the database: `git worktree list` is the registry, status is the diagnostic, and
  ancestry/tree identity proves collection. No shadow workflow state.
- Root directly dispatches planner/hard-critical work; for normal writer/reviewer waves it may
  publish bounded already-ready items to one lease generation. It consumes milestones,
  classifies findings, and serializes collection. Item completion is not turn completion.
- Domain continuity is a convention: continue the same identity with a delta-only follow-up
   unless the domain changed, independent identity is required, or genuinely parallel scope
   exists. If the runtime cannot preserve required identity, return `needs_decision`.

## Inspection and safety aliases

These are pseudo aliases; use `--help` for arguments. Every mutation is an explicit authorized
role action and emits JSON evidence. Git mutations recheck Git immediately. Queue adapters
validate transport declarations only; they never infer readiness, delivery, or completion.

```text
orchestrate := <repo-python> <skill-dir>/scripts/orchestrate.py
orchestrate doctor | diff <old-version> <new-version> --runtime codex|claude
orchestrate identity --requested <role> --effective <role> --profile <path> --agent-id <id> [--writer-agent-id <id> --require-different-identity] [--park-capability slot-free|slot-held|unknown]
orchestrate packet lint --role writer|reviewer --input <packet.json|->
orchestrate queue publish ...; orchestrate queue inspect ...; orchestrate queue remove ...
orchestrate status --root <repo> --task-id <task>
orchestrate lane create --root <repo> --task-id <task> --lane <lane> --base <exact-sha>
orchestrate review checkout <exact-sha> --root <repo> | review cleanup --root <repo> --worktree <path>
orchestrate collect --root <task-worktree> --task-ref <task-branch> --lane-ref <lane-branch> --expected-lane-sha <sha> --authorized-sha <sha> --review-kind different-identity|focused|root-spot|mechanical
orchestrate lane cleanup --root <repo> --task-ref <task-branch> --lane-ref <lane-branch> --worktree <path>
plan := <repo-python> <planning-skill-dir>/scripts/plan.py --root <repo>
plan checkpoint <task-id>
```

## Review and test ownership

Review depth follows the checkpoint's changed surface, not the task's maximum global risk:
mechanical → root spot-check; normal → focused review or reasoned root self-review;
`named_review_risks` → explicitly chosen extra depth/waiting; `hard_critical_axes` → mandatory
different-identity review. Named risks do not become hard-critical axes.

Evidence ownership is non-duplicative. Root/planner freezes seams, examples, independent
oracles, and dangerous failures. The writer owns permanent executable tests, functional
acceptance, and affected regression. The reviewer owns the adversarial matrix, temporary
reproducers, finding probes, and source audit. A missing-behavior finding returns to the
writer for a failing permanent regression before the fix. Integration owns broad-gate
execution/final successful evidence. Reviews bind to the exact immutable SHA they inspected.

## Role pipelines and checkpoints

Planner, writer, and reviewer share one **Role Pipeline Contract**: a lease, bounded ordered
items, per-item readiness, milestone delivery, `continue_without_ack`, and stop conditions.
They never invent or poll for the next item. After notifying root, a role consumes the next
already-ready item when policy permits; queue exhaustion ends the turn but retains the lease.

Dispatch is idle-first. For v60 normal writer/reviewer waves, root publishes already-ready
items, checks status once, wakes an idle consumer, and leaves a running consumer undisturbed;
it checks again on that identity's completion event to close the lost-wakeup race. Planner,
hard-critical work, urgent correction, retract, and stop remain direct messages. No ready
work means idle—never filler or polling. Load the spool reference before using this route.

- **Planner:** in `wave-ahead` mode proposes Wave N+1 while Wave N executes. The proposal
  includes basis/assumptions, target 3–5 slices (tail/final may be 1–2), dependencies, test
  oracles, risk/review policy, and invalidators. It is not dispatch authority; root
  reconciles and freezes it at the wave boundary. Planner never advances to N+2 until N+1 is
  frozen.
- **Writer:** consumes implementation slices and emits progress/validated/review checkpoints.
  Normal behavior-dependent validation may continue without acknowledgment.
- **Reviewer:** consumes complete exact-SHA readiness packets. After each verdict it notifies
  root; PASS may continue to the next ready target without acknowledgment. `needs_fix` stops
  by default unless root pre-authorized an independent, surface-disjoint target. Queue
  exhaustion parks the logical lease without holding an active concurrency slot when the
  runtime explicitly supports that capability; otherwise end the turn and use same-identity
  follow-up.

At wave freeze, choose review policy independently of queue mechanics:
`cadence=none|cumulative|selected|per-slice`,
`waiting=async|before-dependent|before-next`, and
`continuation=pass-only|independent-nonblocking`. Mechanical defaults to none, normal waves
to cumulative/async, and hard-critical checkpoints to per-slice/before-next/pass-only.

A **TDD cycle** is implementer-local red → minimal green → optional behavior-preserving
cleanup. A slice may contain several cycles and ends at one coherent vertical behavior plus
a clean commit; do not message root for every red/green transition.

Every milestone declares `checkpoint_kind`:

- **progress** — dirty or incomplete progress; may carry provisional diagnostics, but is not
  reviewable or run-ahead evidence;
- **validated** — clean exact SHA plus targeted acceptance; eligible for normal run-ahead;
- **review** — a validated checkpoint explicitly frozen as the exact review target; creates
  review debt and stays immutable through closure.

A **green checkpoint** is the `validated` **TDD subtype**: observed red, same-test plus
affected-regression green, and an independent oracle across the frozen module interface.
Non-TDD work uses the `targeted-acceptance` subtype. Either is **run-ahead evidence, never
review sign-off** when uncertainty is behavior-dependent, with no anomaly/retract-class
finding or hard-critical axis. Structure-dependent work waits; all hard-critical slices keep
`review-before-next-slice`. Planner may prepare their next wave only conditionally. Load the
slice-queue reference before using this route.

## Durable state boundary

One-shot tasks create no plan. Cross-session, multi-round, or information-heavy work uses
`planning-with-files`; task_plan is the ledger and a domain packet only its current cache.
Decisions take effect in-band. The spool alone may carry ready work, never decisions/outcomes;
resume requires root reconciliation. Plan `checkpoint <task-id>` maintenance changes no state.

## Definition of done

Design settled; targeted evidence passes; review/final-tree gate are current; task-owned lanes/worktrees/spool items are clean; authorized landing is squashed; evidence is reported.
