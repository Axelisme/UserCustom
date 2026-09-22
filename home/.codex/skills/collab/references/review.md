# Review and correction

## Review

The acceptance unit is a review batch, which may contain one ticket. Inputs are one exact clean
assembled candidate commit/tree, the batch baseline, confirmation the subject's writer stopped, and a
stable `reviews/<review-id>.md` brief. The brief maps every included ticket's acceptance criteria to
observations and names interaction scenarios, interface and test obligations, prior findings, stop
conditions, and limitations. It covers member criteria as well as interactions, not only merge changes.

The Orchestrator checks delivery completeness and required batch gates, records the subject in the
review record, then dispatches one acceptor. Freeze the review checkout until the verdict. Independent
implementation may continue in other lanes; to keep integration moving, use a separate clean checkout
pinned to the reviewed commit. Later changes are outside that verdict.

The acceptor reads the candidate, tests, declarations, callers, and supplied observations. It reviews
every assigned criterion and directly related instances. It directly judges prose, structure,
configuration, repository data, responsibility placement, test assertions, and gate sufficiency. It
does not execute runtime gates.

A missing baseline, mutable or dirty subject, active writer in the review checkout, ambiguous criterion,
missing authority, or unavailable required observation makes the assignment unreviewable. Repair that
concrete input and use a fresh dispatch. Repeated failure to prepare the same missing input stops with
its owner rather than spawning indefinitely.

Review completes with `COMPLETED` approving only the named claims on that exact subject, or `BLOCKED`
containing all supported defects with locations, violated criterion IDs, evidence, affected tickets and
interaction scenarios, and bounded advisory fixes. Specialized Standards and Spec review uses
code-review under its own contract.

## Correct and decide

The Orchestrator classifies the result against the stable claim set. The review record owns candidates,
verdicts, findings, observation applicability, corrections, and disposition. Tickets reference that
record rather than duplicating its review history. Non-contract suggestions receive a recorded
disposition. User-owned behavior, scope, authority, data structure, or responsibility choices go to
dev-flow ticket handoff while feasible work continues.

For supported defects, assign bounded corrections. The Orchestrator changes interfaces and formal
tests; the implementer changes assigned internal logic. Run affected ticket and batch gates, form a
new clean assembled candidate, and dispatch a fresh acceptor with the same bounded criteria and prior
findings. Reassess the applicability of earlier observations to the new subject. Review covers the
corrections and their interactions while accounting for every assigned criterion.

A COMPLETED verdict plus valid observations allows acceptance of the covered claims. Close a ticket
only when all its applicable criteria are established on the accepted candidate. Absence from a defect
list is not approval. A changed candidate needs applicable independent judgement before acceptance;
passing gates alone does not establish it. Findings outside the batch remain with their existing owner.

If correction, verification, or a needed decision cannot proceed, keep the batch and affected tickets
pending with the concrete blocker and next owner. Continue only after a change, new evidence, or an
owner decision provides a defensible next action. Review is complete when the record establishes the
covered claims and each member ticket has an evidence-backed disposition.
