# Optional Contract review

TDD owns this optional branch and the Contract reviewer profile. After the intended Interface
promises have a fixed red test surface, the Orchestrator may request a read-only Contract reviewer before
implementation relies on that surface.

Select this branch when the surface is materially untrusted: for example, Interface behavior is
ambiguous, a provisional fixture is complex, or the evidence may exercise a stand-in. Selection is
an Orchestrator judgement about risk, never test line count, commit count, correction count, or a
predeclared validation mode; most cycles proceed directly from right red to implementation.

The reviewer judges only whether the fixed red surface faithfully expresses the intended Interface
promises. Evidence carries continuity: same-reviewer reuse is a cache optimization, while a fresh
replacement is normal and continues from the fixed subject and evidence. Treat the compact terminal
result as advice about that surface, resolve any accepted issue while it is still red, then bind
implementation to the resulting fixed surface.
