---
outcome: {{COMPLETED|BLOCKED|UNREVIEWABLE}}
---
# {{TICKET_ID}} review {{NN}} verdict

<!-- Written by the acceptor, once, at the absolute path its dispatch names.
     This file must identify what was judged without the original parent conversation. -->

## Subject
<!-- Reviewed commit/tree, baseline commit, and review checkout. Preserve actual reviewed identity.
     For UNREVIEWABLE, distinguish dispatched identity from observed identity; mark unknowns. -->

## Criteria and evidence
<!-- Assigned criterion IDs with exact ticket anchors, verdict for each, and evidence references,
     including gate summary paths, applicability, and limitations.
     Include applicable instruction/skill sources. State None or unavailable explicitly. -->

## Prior findings
<!-- From round 2 on: each previous finding ID, resolved or still open, with evidence. -->

## Findings
<!-- One subsection per finding, ID `R{{NN}}-F<m>`: criterion, location, evidence, and a bounded suggested
     fix. Keep contract defects apart from new scope or design proposals. Write None when there are
     none. For UNREVIEWABLE, name the missing or broken input instead. -->

## Residual risks
<!-- Non-blocking findings, or None. -->
