# Design research

Reached from the advisor's [Design research](SKILL.md#design-research) section.

## Fan-out

Give each independent angle or option its own pi subagent (`spawn_subagent`), all dispatched
together. Each gets one shared brief for the question, its own angle brief, and its own worktree,
and reports its findings plus its coupling points with the other angles. Synthesize two or three
options with a recommendation, and bring them to the user as a design question.

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
