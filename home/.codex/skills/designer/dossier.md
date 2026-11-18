# Dossier

Reached from the designer's [Rule on a question](SKILL.md#rule-on-a-question). Investigators each
research one **angle** of a design question in parallel and write an angle report; the designer
writes the dossier from the reports. The designer and the user decide.

Every factual claim, in a report or in the dossier, is marked **measured** (command and output
path), **read** (`path:line`), or **inferred** (from what). An unmarked claim counts as missing.

## Angle report

You are an **investigator**: a fresh context that owns one angle of one question. Start from these,
in order, before reading the code in question:

1. The question file and your angle brief.
2. The map's `design.md`, its `## Principles` section first.
3. The repository's ADR index and the ADRs of the domains the question touches; then its record of
   past discussions, by the index.
4. The repository's agent instructions on code quality and module placement.

Then dig into your angle. Write `scratch/<question>/angle-<name>.md`, at most 80 lines, with bulky
evidence in files beside it:

1. **Angle.** The question and the part of it you own, one sentence each.
2. **Findings.** What is there and why. For a cause, the mechanism traced to code or measurement;
   a symptom restated is not a cause. For precedents, the search: terms, places, what each returned.
3. **Options from this angle.** Each option your angle bears on, with what it costs or breaks here.
   Include the design you would choose starting from nothing where your angle reaches it.
4. **Coupling.** Each point where another angle's answer would change yours, one line each. A
   finding outside your angle goes here too.
5. **Recommendation**, last: the option you would choose from this angle, and the finding that
   would change it.

The report is complete when every claim carries its mark and every option you name has its cost
from your angle. Report its path and stop.

Work read-only. An experiment needs bounds stated in your dispatch: the commands, the paths you may
write, and the time. Without them, list the experiment under Findings as what would establish the
claim.

## Writing the dossier

The designer writes `scratch/<question>/dossier.md` from the angle reports, as an entry file of at
most 150 lines. A claim taken from a report cites the report; the citation carries the report's
mark.

1. **Question.** One sentence, worded so that every option is an answer to it.
2. **Cause.** Why the current state is what it is: the mechanism behind the error, cost, or
   friction, traced to code or measurement. When the cause is not established, say what would
   establish it and what that costs.
3. **Direction.** The principle lines and ADR rulings that bear on the choice, quoted with their
   source. Then the **direction gaps**: what choosing between the options needs that no document
   answers, each phrased as a concrete scenario the user can decide.
4. **Precedents.** Past rulings on the same kind of question, and the ways the repository already
   solves it, with the search that found them (ADRs, discussion index, map decisions, archived
   decisions, the codebase). For each precedent, say whether an option follows it, departs from
   it, or would require overruling it.
5. **Options.** At least these three, each with the same fields:
   - **Keep** what is there.
   - **Fix the cause** found in section 2.
   - **Natural**: the design you would choose starting from nothing, with what moving to it costs.

   Fields: what changes; who calls it and what they must change; failure modes; cost to build;
   whether it can be walked back; which precedents and principles it follows or breaks. Add further
   options where they differ in a decision the reader could act on.
6. **Evidence.** For each number and each claim the options rest on, the command, path, or report
   that reproduces it.
7. **Recommendation**, in a separate file `recommendation.md`: the option you would choose, the
   finding that would change your mind, and where you depart from an angle's recommendation, why.

The dossier is complete when every option has every field, every claim carries its mark, and the
search in section 4 is recorded.
