# Range review {{NN}}

<!-- Message template: send the filled body as the child dispatch. No task file is required.
     Procedure: ~/.codex/skills/collab/references/review.md#range-review -->

## Range
<!-- Integration checkout, base commit (refs/collab/<task>/reviewed, or the commit integration was
     created from), and head commit. A split names its commit sub-range. -->

## Tickets and criteria
<!-- Tickets whose changes fall in the range, with exact #acceptance and #scenarios paths. Name the
     criteria that need judgement; gates already establish the rest. -->

## Gate results
<!-- Absolute path of runs/<head-short-sha>/summary.md, or None. -->

## New dependencies
<!-- Package-level import edges the range adds, each marked covered or not covered by an existing
     import contract; or None. An uncovered edge needs a contract or a stated reason. -->

## Prior findings
<!-- Findings from earlier reviews that this range fixes, each with its fix commit; or None. -->

## Sources
<!-- Repository instruction and technical skill paths with read conditions, or None. -->

## Authority
<!-- Read-only. The verdict file is the one permitted write. No tests, imports, linters, formatters,
     builds, or runtime gates. Ask the parent through contact_parent when a decision is needed. -->

## Verdict path
<!-- Absolute path of runs/<head-short-sha>/review.md. -->
