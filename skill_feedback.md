# Skill feedback — prefer chained worker → reviewer loops

## User preference

The preferred default is to compose `worker → reviewer → bounded correction` as one subagent
workflow rather than have the Orchestrator manually dispatch and inspect each handoff. Manual control
should be the exception for a decision or boundary the chain cannot own, not the ordinary way to move
between implementation and review.

## Friction observed in the current collab guidance

The current guidance permits composition but does not prefer it. Several correct guardrails combine
to bias the Orchestrator toward manual phase control:

1. **The sequence assigns a completion boundary to every phase but no default carrier across those
   boundaries.** `Implement and identify`, `Review the fixed subject`, and `Resolve the result` are
   written as separate Caller actions. The runtime reference calls a composed loop optional and
   supplies no canonical chain, so the safest literal reading is to return to the Orchestrator after
   each child.
2. **The writer's terminal identity is prose rather than a machine-consumable contract.** The
   reviewer requires an exact commit and tree, placement, criteria, evidence path, and clean-state
   expectation. With a free-form writer result, an Orchestrator is pushed to inspect the checkout,
   parse the SHA/tree, and build a second brief manually rather than pass a typed terminal envelope
   directly to a reviewer.
3. **The fixed-subject invariant is clear, but automation around it is not.** A chain can preserve
   the invariant by passing the writer's exact identity to a fresh reviewer and letting the reviewer
   verify it independently. The current text emphasizes that a wrong or changed identity voids the
   pass without equally emphasizing that this verification belongs inside a chain and does not
   require a human-style inter-stage pause.
4. **Background execution advice makes each stage look like a separate run.** Returning control
   while a child works is appropriate, but it is orthogonal to whether worker and reviewer are
   composed in one asynchronous workflow. The guidance does not make that distinction prominent.
5. **Correction routing is described semantically but not packaged operationally.** The rules already
   distinguish a bounded defect, which may return to the writer, from scope/architecture/authority/
   contract decisions, which must return to the Orchestrator. That is enough to drive a workflow
   branch, but the skill presents it mainly as a Caller-managed sequence.
6. **Collection introduces a second kind of subject change.** A stale managed lane must reconcile
   with integration, producing a new subject and requiring a new verdict. `collab_op` performs this
   with a merge, not a rebase: `lane_reconcile` and stale `lane_collect` return the new `lane_sha`
   before collection. Without a canonical composed collection path, the Orchestrator still has to
   schedule reconciliation, review, judgement, and collection manually. The single-use verdict rule
   should remain strict; the missing piece is orchestration that puts reconciliation before the
   review whose pass will be collected.

## Evidence from this task

- T010 was a stable, bounded one-file correction. It was dispatched to a writer, inspected manually
  by the Orchestrator, and then dispatched in a second workflow to an independent acceptor. Nothing
  about the contract required that manual inter-stage pause; a typed worker result and canonical
  chain could have carried it directly into review.
- T004 and T006 arrived as already-written, **unmanaged plain-Git** lanes created under another
  runtime. `collab_op status` returned `task_not_found`; the inherited task record prescribed its
  legacy rebase-and-patch-comparison close-out. That rebase was not `collab_op` behavior and is not a
  model for managed lanes. A managed stale lane uses merge reconciliation and reviews the resulting
  exact subject before collection.
- T009 then demonstrated the structured-result gap directly. A composed validation → reviewer
  workflow checked the free-form Markdown result with a regex. The writer correctly returned
  `**Outcome**: \`COMPLETED\``, but Markdown backticks defeated the parser and terminated the chain
  before reviewer launch. Validation succeeded; orchestration failed. A typed result or strict
  `outputSchema` would have made the branch deterministic.
- The cumulative close-out review found a genuine contract contradiction. Returning that question to
  the user was the correct chain termination. A chain-first design must preserve this escalation,
  not attempt to automate the decision.

## Suggested skill changes

1. **State a chain-first default.** When goal, Acceptance, write scope, validation, placement,
   mutation authority, and escalation boundaries are closed, prefer one asynchronous
   `worker → fresh reviewer → bounded correction` workflow. Use separate manual dispatches when a
   required value is unresolved or a scope, product, architecture, authority, or contract decision
   returns to the Orchestrator.
2. **Define a structured worker handoff.** Make the terminal result machine-consumable and require at
   least base identity, subject commit/handoff identity, tree, changed paths, validation artifact,
   checkout cleanliness, residual risks, and decision status. The reviewer still verifies identity
   independently; structure removes the need for the Orchestrator to translate prose.
3. **Provide a canonical Pi workflow in `runtime-pi.md`.** It should:
   - run one writer in its isolated lane;
   - stop on `BLOCKED` or `NEEDS_DECISION`;
   - pass the exact structured subject to a fresh read-only acceptor;
   - return bounded acceptance blockers to the same writer when resume is available;
   - repeat with a new subject and verdict;
   - terminate to the Orchestrator for any contract/scope/authority decision;
   - return the final reviewed fixed subject without claiming collection or landing authority.
4. **Separate asynchronous execution from manual orchestration.** Say explicitly that the whole chain
   may run in the background; returning control to the user does not require splitting it into
   separate worker and reviewer workflows.
5. **Add a collection-oriented composition.** For parallel managed lanes, serialize the final
   `lane_reconcile → review new subject → Orchestrator judgement → lane_collect exact subject`
   boundary. Review a lane only after its final reconciliation with current integration, and do not
   collect another lane between that review and collection. This gate is downstream of ordinary
   worker/reviewer correction; it should not be used to justify manual handoffs inside that loop.
6. **Keep the safety exits.** A chain must stop rather than repair autonomously when findings require
   new product, architecture, scope, contract, or mutation authority. Dirt, ambiguous identity, and
   mutable review placement remain hard stops.
7. **Do not weaken the fixed-subject rule.** The problem is missing composition support, not excessive
   review strictness. Every correction or synchronization still produces a new subject and consumes
   a new verdict.

## Desired resulting behavior

For an ordinary closed ticket, the Orchestrator should make one placement decision and receive one
terminal handoff: either a reviewed fixed subject, a bounded blocker after the correction budget is
exhausted, or an explicit decision request. The Orchestrator should not need to copy SHAs between
free-form child messages, manually reconstruct the reviewer brief, or manually resume the writer for
routine in-contract findings.
