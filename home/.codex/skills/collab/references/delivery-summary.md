# Delivery summary

Use this reference when presenting reviewed integration for a landing decision or reporting delivered
work. It is not a template for routine progress messages. Write for the user's decision, in their
language and the repo's domain vocabulary.

## Change

State the user-visible change and the candidate commit or branch. Distinguish reviewed integration,
landed work and live installation; report only the state actually reached. Lead with any decision
still needed.

Choose the smallest view that explains the change: a short paragraph, a diff sketch, pseudocode, a
call tree, a file tree or a diagram. Use a visual only when it explains ownership, order or behavior
better than prose. Keep only the calls, files and states needed for this decision.

## Evidence

Describe the observable difference and point to the existing gate summary or direct-review record for
this candidate. Pair before and after when both were observed, using the exact check or observation
that establishes the change. Screenshots help with visual behavior when they already exist.

For prose, configuration or repository data, state what direct review confirmed. If an observation
was not made, name that gap; do not invent a prior failure, a passing run or a screenshot. A review
verdict and runtime validation establish different facts, so label each accurately. Summarize the
conclusion without duplicating logs or creating a second evidence store.

## Impact and recovery

Name the affected users, callers, modules or workflows and the remaining uncertainty. Explain whether
undoing the change restores the prior state, what recovery would require, and any irreversible
consequences. Ground these claims in the actual change rather than a generic risk label.

Separate repository changes from deployment, live configuration and external effects. Name any step
still waiting on authority or prerequisites, plus its owner. This summary does not grant permission to
land, install, push, open a PR, clean up or roll back anything.

A summary is complete when the reader can identify the change, inspect its evidence, understand the
impact and recovery limits, and see the decision or action still needed. Omit empty headings and keep
small deliveries small.

## Source

Adapted from [mattpocock/skills pr](https://github.com/mattpocock/skills/blob/c55ee46073ed923f86ce59a5eb3b6d895095d1b7/skills/in-progress/pr/SKILL.md).
Its summary visuals credit Dex Horthy / Humanlayer's `show-me`; see the upstream
[credits](https://github.com/mattpocock/skills/blob/c55ee46073ed923f86ce59a5eb3b6d895095d1b7/skills/in-progress/pr/CREDITS.md).
This is local delivery guidance, not a PR workflow or a requirement to install that skill.
