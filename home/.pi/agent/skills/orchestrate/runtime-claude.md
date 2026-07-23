# Orchestrate — Claude runtime binding

Claude role agents start fresh. Each prompt carries the frozen objective, exact workdir,
base SHA, write scope, acceptance commands, authority, stop conditions, and artifact paths.

## Dual-role handoff

Run `wave-oracle` for public Interface, contract tests, fixtures, adapters, and red Contract;
run `wave-implementer` after Root merges that Contract to fill production behavior. Both
roles emit one terminal `slice-ready` handoff with Slice and exact SHA, then immediately end this turn. Workers do not create child agents.

## Continuation and acceptance

Use native messaging and continuation only when exposed; otherwise return the terminal
handoff in the final response rather than inventing continuity. Root owns dependency depth,
Git merges, and repository authority. Dev-flow runs simplify, canonical tests, and one
clean-detached exact-SHA code-review before any repository-policy integration.
