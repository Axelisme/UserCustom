---
name: contract-review
description: Trade-off matrix over two or more pinned contract options, one angle per reviewer.
disable-model-invocation: true
---

One decision, several pinned options, one matrix. Each **angle** runs in a fresh read-only context
across every option, so a row's cells come from one judgement rather than several, and no angle
launders its verdict through another.

This skill reviews options; it does not write them. When fewer than two options exist, the caller
investigates the codebase and drafts them first, then returns here with the set pinned;
[Design It Twice](../codebase-design/DESIGN-IT-TWICE.md) is the generator, this skill is its reviewer.

Uses the vocabulary in [codebase-design](../codebase-design/SKILL.md): **module**, **Interface**,
**seam**, **adapter**, **leverage**, **locality**.

## Terms

- **Question**: the one decision under review, stated so that every option is an answer to it.
- **Option**: one candidate contract, declaring its Interface, its callers, and its failure modes.
- **Datum**: the option every cell is scored against, usually "keep what is there". Scoring is
  relative to the datum, never an absolute number.
- **Angle**: one quality the decision turns on. Each reviewer holds exactly one.
- **Scenario**: what makes an angle checkable, a stimulus and the response measure that settles it.
  "Latency" is not a scenario; "a call arriving while the cache is cold returns inside 200ms" is.
  The reviewer writes its own scenarios from the option text and reports them with its result.
- **Sensitivity point**: a detail of one option where a single angle's outcome changes sharply.
- **Tradeoff point**: a sensitivity point that two or more angles pull opposite ways. These are the
  report's payload; the matrix is how they are found.
- **One-way door**: a cell whose cost cannot be walked back once the option ships, marked `!`.
- **Risk**: a consequence of an option that no scenario settles, stated alongside what would settle it.

## Process

### 1. Pin the question and the options

Resolve the Question to one sentence and the options to one **fixed subject**: one exact clean Git
commit and tree holding the option text, or one immutable artifact written before launch. A branch
name, a chat transcript, or "the three ideas we discussed" is not one. Record the identity once and
quote only from it afterwards.

Require at least two options that answer the same Question, that differ in a decision the reader
could act on, and that each declare the same fields (Interface, callers, failure modes, data and
migration story). Options declaring different fields produce cells that compare different things.

When the set is short, mixed-shape, or unpinned, stop and say exactly what is missing. The caller
supplies the legwork; this skill writes no options and pins no subject it was not given.

This step is complete when one Question, one immutable identity, and two or more same-shaped options
all resolve together.

### 2. Name the datum

Pick the option every cell is scored against: the status quo when the decision has one, otherwise the
option with the fewest moving parts. Name it in the report; a matrix without a named datum has no
meaning for `+` or `-`.

This step is complete when exactly one option carries the datum role.

### 3. Choose the angles

Every review carries these four **baseline angles**:

- **Depth**: how much behaviour each option puts behind how much Interface, where it puts the seam,
  and whether its promises can be asserted at that seam without reaching private state. The
  Interface is the test surface, so depth, seam placement, and testability are one judgement.
- **Failure modes**: what each option does when each dependency fails, and whether the caller sees
  that failure at the Interface rather than as silence or corruption.
- **Evolution**: which likely next requirement each option makes cheap, and which one it locks out.
- **Migration**: what existing callers and stored data must change to adopt each option.

Add a decision-specific angle only when you can name the option ordering it could flip. An angle
that flips nothing costs a full reviewer and returns a row nobody reads. A documented repo standard
overrides the baseline wording where the two disagree, and every angle stays a judgement call.

Four angles run without asking. A fifth is a question for the user: see [Stopping to
ask](#stopping-to-ask).

This step is complete when every chosen angle names the ordering it could flip, and any angle past
the fourth carries the user's agreement.

### 4. Run one reviewer per angle in parallel

Dispatch one fresh, read-only `contract-reviewer` per angle, in the background, each seeing every
option. Give each the Question, the pinned identity and path, the named datum, and its one angle.
The reviewer writes its own scenarios, scores each option `+` / `0` / `-` against the datum, marks
any **one-way door** with `!`, and names the sensitivity point behind each score.

One angle per reviewer is the point: a reviewer holding two angles silently trades one against the
other inside its own context, and the tradeoff point disappears before step 5 can find it.

This step is complete when every angle returns a report naming the pinned identity and its own
scenarios, and the subject still resolves to that identity.

### 5. Report

Write these five parts in order:

1. The Question, the pinned identity, and the named datum.
2. The **matrix**: one row per angle, one column per option, each cell carrying the reviewer's
   `+` / `0` / `-`, a `!` where the reviewer marked a one-way door, and a few words of evidence.
   No total row: see [Why the matrix carries no total](#why-the-matrix-carries-no-total).
3. The **tradeoff points**: where two or more angle reports mark the same sensitivity point with
   opposing signs, name the point and both angles.
4. The **risks** each angle left unsettled, with what would settle each. Name here any angle whose
   reported scenarios were too loose to settle what they were asked to, which is a question for the
   user: see [Stopping to ask](#stopping-to-ask).
5. The **recommendation**: which option to take and why, then the conditions that would flip it to
   another. It sits last so the reader meets the real tension before meeting your call, and can
   reject the call while keeping the matrix.

This step is complete when every angle appears as its own row, every tradeoff point cites two or
more angle reports, and the recommendation carries at least one flip condition.

## Stopping to ask

This skill runs with the user, not past them. Two moments stop the run and hand them a decision:

- **A fifth angle** (step 3). Name the angle, the ordering it could flip, and what the extra reviewer
  costs. Run it on their agreement; drop it otherwise.
- **A loose scenario** (step 5). When a reviewer's reported scenarios were too vague to settle its
  angle, say which angle and how the scenario fell short, and let the user choose between
  re-dispatching that angle with a sharper brief and keeping the weak row as reported.

The user ends both: re-dispatching until the answer looks agreeable is how a preference gets in
without ever being stated.

## Why the matrix carries no total

A weighted total is a second decision wearing the first one's clothes: whoever picks the weights has
already chosen the option, and the matrix then supplies arithmetic that looks like evidence. The
recommendation in part 5 is the honest form of the same call, because it can be rejected on its
reasoning while every cell above it still stands.

So the report earns its keep twice: the matrix and its tradeoff points make the real tension visible
(this option buys evolution and spends migration, that one buys depth and spends testability), and
the recommendation says what you would do about it. A reader who disagrees with the second still
keeps the first.

Contract-review grants no implementation authority. It reports on options; committing to one and
building it stay with the user and the Orchestrator.
