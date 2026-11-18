# Quick ruling

Reached from the coordinator's [Answer a question](SKILL.md#answer-a-question). A `simple` design
question goes to a one-shot **quick-ruling agent** instead of the resident designer, so the
designer's session stays free for `full` questions and for talking design with the user.

## Dispatch

- One agent per question, on a clean context, in the background. Use a herdr pi `research-expert`
  subagent or a Claude subagent on Opus or stronger. Run at most three Claude quick-ruling agents at
  once.
- Its brief carries pointers, not copies:
  - the question file path and the map directory;
  - the designer skill's [What you write](../designer/SKILL.md#what-you-write) (decision format),
    [Tiers](../designer/SKILL.md#tiers), [Rule on a question](../designer/SKILL.md#rule-on-a-question)
    (proxy rules), and [Precedent](../designer/SKILL.md#precedent);
  - the map's `## Standing orders`, the repository's agent instructions, and where precedents live
    (the map's `decisions/`, `.agent_state/archives/*/decisions/`, the repository's ADRs and
    discussion index);
  - the files the repository forbids reading.

## What the agent does

1. Claims the question by creating `scratch/designer-coordination/claims/<task>-<slug>`; a claim
   already present means another agent holds it, so it stops.
2. Confirms the tier. A question that is really `full`, or whose choice turns on the user's
   direction, is reported back unruled, with the reason and a recommendation.
3. Finds the precedents and takes a stance on each.
4. Reserves a number with the designer's `scripts/next-decision-number.sh`, writes the decision with
   `Ruled-by: designer-subagent (STDO <date>)`, and updates the `design.md` text it changes.
5. Sends `ruling(<task>): decisions/NNNN` to the asking task, deletes its claim, and reports the
   decision path, a one-sentence ruling, and any Follow-ups line for you to write. It leaves
   `MAP.md`, the task's files, and Git untouched.

## On its report

Write the Follow-ups lines it names. A question reported back as `full` goes to the resident
designer's queue. A design-type ruling (`Review: pending`) joins the user's proxy-review list like
any other proxy ruling.
