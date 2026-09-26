---
review_id: {{REVIEW_ID}}
disposition: pending
---
# {{REVIEW_ID}}: {{TITLE}}

| Review field | Value |
|---|---|
| feature or contract boundary | <coherent outcome; singleton batches are valid> |
| included tickets | <ticket paths> |
| baseline | <exact commit before the batch changes> |

## Criterion coverage
<!-- Map every included ticket criterion to an observation method and owner; results go in
     Candidate-bound observations. Preparation starts during planning; the complete claim set and
     observations must be ready before review dispatch. -->
| Criterion | Observation | Owner |
|---|---|---|
| <ticket-id.A1> | <candidate-bound observation pointer> | <owner> |

## Bounded claims
<Named criteria, inherited unresolved claims, and deliberate exclusions. An exclusion does not waive
an included ticket's acceptance obligation; regroup membership explicitly if necessary.>

## Interaction scenarios
<Interaction ID, starting state, assembled change or action, expected response, responsible modules,
affected tickets, and observation/owner.>

## Candidate-bound observations
<Owner, method or command, selection, environment, result, run pointer, and limitations for each claim
on the current candidate. Include assigned batch gates and each collected delivery's gate results.
Reassess applicability after assembly or correction; superseded observations move with their round
to the history file.>

## Current round
<Subject commit and tree, review checkout, writer-stopped observation, reviewability, verdict,
blockers, correction owner, and next action and owner. Record the subject before dispatch. When a new
round starts, move this round to `<review-id>.history.md`.>

## Findings
| ID | Criterion and tickets | Status | Resolved by |
|---|---|---|---|
| none | | | |

## Ticket dispositions
| Ticket | Established criteria and accepted candidate | Outstanding obligations / owner |
|---|---|---|
| <ticket-id> | <review and observation pointers> | <none or concrete blocker> |

## Disposition
<!-- Accepted claims and their subject once review establishes them. Procedure:
     ~/.codex/skills/collab/references/review.md#correct-and-decide -->
Pending.
