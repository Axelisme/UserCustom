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
| subject | <exact clean assembled commit and tree; required before dispatch> |
| review checkout | <frozen integration or separate pinned checkout> |
| writer stopped | <observation for this checkout> |

## Criterion coverage
<!-- Map every included ticket criterion to an observation and owner. Preparation starts during
     planning; the complete claim set and observations must be ready before review dispatch. -->
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
<Owner, method or command, selection, environment, result, run pointer, and limitations for each claim.
Include assigned batch gates. Reassess applicability after assembly or correction.>

## Prior findings
None.

## Progress
<Record each candidate, reviewability, verdict, findings with affected criteria/tickets, correction
owner, verification, and next action. Review history belongs here rather than in member tickets.>

## Ticket dispositions
| Ticket | Established criteria and accepted candidate | Outstanding obligations / owner | Disposition |
|---|---|---|---|
| <ticket-id> | <review and observation pointers> | <none or concrete blocker> | pending |

## Disposition
Pending. Approval establishes only the bounded claims on the reviewed subject. Corrections require
applicable verification and fresh independent review; gates alone do not establish acceptance.
