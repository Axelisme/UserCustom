---
name: orchestrate
description: Control loop for repo-wide work that needs multi-agent pipelines, independent risk review, parallel worktrees, or integration across task branches.
skill_version: 61
---

# Orchestrate

Run a control loop that retires the most consequential uncertainty with the smallest safe
move. Keep three truth carriers consistent: **Git** for code/topology, **active reasoning**
for current hypotheses, and **durable narrative** for cross-session decisions. Transport
files carry frozen input; root remains the decision and integration authority.

## Constitution

Ground every irreversible, durable, external, or high-risk consequence in proven evidence and
current user authority. When that basis is insufficient, reduce the move, add independent
evidence, or return the decision.
Judge risk by reversibility, blast radius, boundary crossing, and evidence independence.
Evidence is valid only for the actual tree it inspected. A persistence landing requires current
user authority.

## Root control loop

| step | action | completion criterion |
|---|---|---|
| **1. Observe** | Read repo instructions and relevant decisions; inspect Git, worktrees, user dirt, current narrative, and existing evidence. | The authoritative tree, user-owned changes, live task state, and largest unresolved uncertainty are named. |
| **2. Freeze** | Freeze the next bounded outcome: objective, acceptance, non-goals, write scope, exact base, test oracle, and risk/review boundary. | The assignee can act without guessing the public contract, ownership, or acceptance. |
| **3. Shape** | Choose the cheapest pipeline that retires the uncertainty; serialize shared files, contracts, schemas, fixtures, and authority. | Every ready item has an owner, base, scope, acceptance, dependency, and review barrier; conflicting authority is serialized. |
| **4. Dispatch** | Issue only ready, self-contained work with a bounded lease and explicit discretion/stop boundary. | The consumer can act without chat history and knows when it may run ahead or must stop. |
| **5. Harvest** | Classify the returned milestone as progress, validated state, review verdict, or decision stop. | Conclusions bind to the actual exact SHA/tree; tests/anomalies are usable and each finding has an owner. |
| **6. Integrate** | Serially collect accepted work after its risk-proportional review debt is resolved. | Ancestry/tree identity is proved, every lane change is accounted for, and the integration checkout is clean. |
| **7. Re-observe or close** | Integration changes reality: repeat from Observe, or close against the final integrated tree. | Necessary final gates/review, user authority, cleanup, and durable narrative are current rather than inherited from an older tree. |

## Pipeline shapes

| shape | use when | flow |
|---|---|---|
| **root-only** | Root can retire the uncertainty more cheaply than a handoff. | inspect/change → targeted evidence |
| **single writer** | One coherent surface dominates and an independent identity adds little. | freeze → write one coherent vertical slice → targeted gates → root review → integrate |
| **normal wave** | Two or more ready slices are genuinely independent. | Planner N+1 advises → root freezes → Writer N produces a validated exact SHA → Reviewer N audits selected/cumulative slices → root serial collect → final integrated gate |
| **critical checkpoint** | Security/capability/auth, hardware or process ownership, persistence, or atomic cutover makes failure costly. | freeze → writer checkpoint → different-identity adversarial review → finding returns to the writer → focused closure or refreshed exact-state review → release dependent work |

Optimize **critical-path lead time**, not agent utilization. A milestone is non-blocking; a
checkpoint is a review barrier. Let one writer retain a coherent vertical slice and run only
targeted gates during development. Use focused re-review for localized findings; perform one
full slice review and the repo/risk-required broader gate at integration. Treat ordinary
HTTP/codec/client wiring as a normal vertical unless it crosses a critical boundary.

## Context pointers

Read a reference completely only when its branch fires:

- Before creating a branch/worktree, collecting, or landing, read [Git coordination](references/git-coordination.md).
- Before the first agent dispatch, identity decision, or review, read [Delegation and review](references/delegation-and-review.md) and the matching `runtime-<runtime>.md`.
- Before dispatching two or more ready slices concurrently, read [Wave pipeline](references/wave-pipeline.md).
- Before freezing a critical checkpoint or closing its findings, read [Critical review](references/critical-review.md).
- Before using a filesystem queue, read [Durable delivery spool](references/durable-delivery-spool.md).
- Before replacing a long direct contract with a file, read [Dispatch packets](references/dispatch-packets.md).
- When a gate is anomalous/baseline-relative or a handoff is needed, read [Evidence and handoff](references/evidence-and-handoff.md).

Use `<repo-python> <skill-dir>/scripts/orchestrate.py --help` for mechanics; adapters enforce
schemas, exact-state checks, compatibility, and safe lifecycle operations.

## Definition of done

The requested outcome holds on the final integrated tree; consequential uncertainty has
current evidence; remaining risk is explicit; authorized persistence and cleanup are complete.
