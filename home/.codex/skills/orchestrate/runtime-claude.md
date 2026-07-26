# Orchestrate v127 — Claude runtime binding

Claude v127 role agents start fresh. Each prompt carries the frozen objective, exact workdir, base SHA, write scope, acceptance commands with the environment they require, the Oracle-declared immutable paths, authority, stop conditions, and artifact paths.

## Dual-role handoff

Run `wave-oracle` for public Interface, contract tests, fixtures, adapters, and red Contract; run `wave-implementer` after Root merges that Contract to fill production behavior. Ready commits use Git trailers `Wave: <wave-id>`, `Slice: <slice-id>`, and the role-specific `Role: oracle` or `Role: implementation`; both roles emit one terminal `slice-ready` handoff with Slice and the full exact SHA, then immediately end this turn. Once Root collects that SHA, close both role identities and remove their clean worktrees; a later correction is a new Wave. Workers do not create child agents.

## Continuation and acceptance

Use native messaging and continuation only when exposed; otherwise return the terminal handoff in the final response rather than inventing continuity. A blocked role reports through the same terminal path with its reason and evidence, not a ceremony commit. A successor in the same role stream keeps the identity but not necessarily the context: continue the session while the frozen input is unchanged, and start a fresh one — same identity, optionally a different model — once the Contract SHA, frozen spec, or base has moved, or after a provider or liveness failure. A stale session replays conclusions it drew about an input that no longer exists. One writer per role stream either way. Root owns dependency depth, Git merges, and repository authority. Dev-flow runs simplify, canonical tests, and one clean-detached exact-SHA code-review before any repository-policy integration. Dispatch two fresh read-only `acceptance-reviewer` agents against that SHA, one per `Axis: standards | spec`; neither continues into implementation. Root follows the shared dev-flow S5/S6/S7 scheduling and machine-rework contract; this binding adds no landing or acceptance authority, and no runtime state file substitutes for Git.
