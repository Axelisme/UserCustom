# Design research

Reached from the designer's [Design research](SKILL.md#design-research) section.

## Fan-out

Give each independent angle or option its own pi subagent (`spawn_subagent`), all dispatched
together. Typical angles: the current code and its callers; precedents and principles; outside
practice; cost or measurement. Each gets one shared brief for the question and its own angle brief.
An angle that runs experiments also gets its own worktree; a read-only angle needs none. Each
reports by [dossier.md](dossier.md#angle-report): its findings, its own recommendation, and its
coupling points with the other angles. You then write the dossier from the reports and take it to
the challenger.

## Spike

A **spike** answers "can this work?", not "how fast exactly?":

- Use small workloads and run each variant once. Reuse baselines already measured, and run the old
  path at most once per variant.
- Report within about 30 minutes. Rigorous benchmarks belong to the acceptance of the task that
  adopts the result.
- Run spikes in parallel even on a busy machine, and note the load in the report. Only
  thread-scaling measurements run one at a time.

## When research calls for a large refactor

Open the refactor as its own task beside the running optimisation, which keeps going. Slice the
refactor expand-only first and land those slices early. Then move its remaining tickets into the
optimisation task as candidates, ordered by what the algorithm needs; drop those it does not need.

Every spike and angle worktree is removed when its report is accepted: the worktree, its branch, and
each parent directory left empty.
