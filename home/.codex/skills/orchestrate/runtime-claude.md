# Orchestrate — Claude runtime binding

Claude role agents start fresh. Each prompt carries the frozen objective, exact workdir,
base SHA, write scope, acceptance commands, authority, stop conditions, and artifact paths.

## Dual-role handoff

Run `wave-oracle` for public Interface, contract tests, fixtures, adapters, and red Contract;
run `wave-implementer` after Root merges that Contract to fill production behavior. Ready commits use Git trailers `Wave: <wave-id>`, `Slice: <slice-id>`, and the role-specific `Role: oracle` or `Role: implementation`; both roles emit one terminal `slice-ready` handoff with Slice and the full exact SHA, then immediately end this turn. Workers do not create child agents.

## Blocked checkpoint contract

If Implementation is blocked by a contradictory Contract, it creates a clean Git checkpoint commit carrying `Wave: <wave-id>`, `Slice: <slice-id>`, and `Role: implementation-checkpoint`. Terminal blocked output/hold includes the concrete counterexample and exact checkpoint SHA; ready and terminal contracts remain unchanged.

## Continuation and acceptance

Use native messaging and continuation only when exposed; otherwise return the terminal
handoff in the final response rather than inventing continuity. Root owns dependency depth,
Git merges, and repository authority. Dev-flow runs simplify, canonical tests, and one
clean-detached exact-SHA code-review before any repository-policy integration.
