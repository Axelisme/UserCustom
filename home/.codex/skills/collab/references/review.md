# Review and correction

## Review

Inputs are one exact clean candidate commit/tree, baseline, confirmation the writer stopped, and one
stable bounded brief. The brief may be a ticket or `reviews/<review-id>.md`. It names criterion IDs,
scenarios, interface and test obligations, relevant candidate-bound observations and owners, prior
findings, stop conditions, and limitations. A batch brief also names included tickets, cutoff claims,
and interactions.

The Orchestrator verifies those preconditions, records the subject, then dispatches one acceptor by
default. The acceptor reads the candidate, tests, declarations, callers, and supplied observations. It
reviews every assigned criterion and directly related instances. It directly judges prose, structure,
configuration, repository data, responsibility placement, and test assertions. It does not execute
runtime gates.

A missing baseline, mutable or dirty subject, active writer, ambiguous criterion, missing authority,
or unavailable required observation makes the assignment unreviewable. Repair that concrete input and
use a fresh dispatch; these assignment failures are not defect verdicts and consume no BLOCKED
allowance. Repeated failure to prepare the same missing input stops with its owner rather than spawning
indefinitely.

Review completes with `COMPLETED` approving only the named claims on that exact subject, or `BLOCKED`
containing all supported defects with locations, violated requirements, evidence, affected scenarios,
and bounded advisory fixes. Specialized Standards and Spec review uses code-review under its own
contract.

## Correct and decide

The Orchestrator classifies the result against the stable claim set. New ticket and batch records
default to one effective BLOCKED allowance. Count only a supported defect verdict on a reviewable
candidate. Preserve each verdict, candidate, count, prior finding, and explicit allowance across
agents, sessions, candidate changes, and review names. Existing recorded limits remain in force; only
the user grants more.

A COMPLETED verdict plus valid observations establishes the assigned claims and allows normal
acceptance. Non-contract suggestions receive a recorded disposition. User-owned behavior, scope,
authority, data structure, or responsibility choices go to dev-flow ticket handoff while feasible work
continues.

The first effective BLOCKED reaches the default cap. Select one final bounded correction. The
Orchestrator changes interfaces and formal tests; the implementer changes assigned internal logic.
Run required gates, form a new clean candidate, and record the fixes. Independent review ends unless a
user grant adds allowance. Do not rename or repartition the same claims to obtain another review.

After final correction, cutoff is allowed only when gates pass and the Orchestrator can judge the
bounded candidate. Record established claims, remaining findings, affected scenarios, and fixes or
claims not independently confirmed after correction. Otherwise keep the ticket or batch pending with
the blocker and owner. Batch approval or cutoff changes only covered claims; it never upgrades
uncovered historical cutoff work.
