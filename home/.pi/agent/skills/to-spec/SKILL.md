---
name: to-spec
description: Turn the current conversation into a frozen spec artifact without an interview.
---

# To Spec

This skill produces **artifacts only**: a frozen spec for the user-visible behavior and its
recorded usage envelope. Do not implement, review, or create runtime state here. If a source
document exists, mark each normative statement inherited, refined, or contradicted and record the
user override for every contradiction.

## Spec artifact

Explore enough of the repository to use its domain vocabulary and choose the highest existing test
seam. Capture the problem, solution, stories, implementation and testing decisions, envelope,
source conformance, Slice map, and out-of-scope behavior. Do not put specific file paths in the
spec unless a prototype's state/schema shape is load-bearing.

The first Slice must have an observable sentence and a named deletion; it is independently
reachable and its first accepted checkpoint is days, not weeks away. The frozen Contract is an
artifact consumed by Oracle and Implementation. The Slice Map records the evidence required by
**S1/S2**; the shared admission standard decides or refuses admissibility.

## Publish

In a plan-directory repo, initialize `.agent_state/plans/<task-id>/` with planning-with-files and
write `spec.md`; otherwise use the documented tracker or `.scratch/<feature-slug>/spec.md`. Keep
acceptance criteria and usage envelope explicit. This skill owns artifacts only; acceptance,
review, execution, and close-out belong to their owning surfaces.
