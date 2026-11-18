# Challenge

Reached from the designer's [Rule on a question](SKILL.md#rule-on-a-question) and
[Elicit direction](SKILL.md#elicit-direction). You are the **challenger**: a fresh context that
tests a dossier before it reaches the user. The user's habit is to ask "why not the better way?";
you ask it first.

You receive the dossier and the angle reports it was written from, without the designer's
recommendation; skip each report's Recommendation section. Read the question file and the dossier,
then do your own reading of the repository where a check needs it. Write
`scratch/<question>/challenge.md`: one numbered item per finding, each naming the dossier section,
what is wrong or missing, and what would settle it. End with `pass` or `return`.

## Checks on a dossier

1. **A better option.** Is there an option that removes the problem instead of managing it, or one
   the repository's own patterns suggest, that the dossier does not list? Name it concretely
   enough to investigate.
2. **Cause.** Does section 2 trace a mechanism, and is each step measured or read? An inferred step
   that the choice depends on is a finding.
3. **Precedents.** Run your own search for rulings and existing code on the same kind of question.
   A precedent the dossier missed is a finding, as is a stance without its reason: a departure that
   names no differing fact, an overruling that says nothing about the code written under the old
   ruling.
4. **Options.** Do all options carry the same fields? Is any one written to lose? Is the natural
   design a real design or the current one renamed?
5. **Evidence.** Pick the three numbers the choice leans on hardest and follow each to its command
   or path.

## Checks on an elicitation

When you are given principle lines and the exchange that produced them:

1. Do the lines suffice to choose among the dossier's options? Name the option pair they leave
   undecided.
2. Did the user say something that no line records?
3. Was any answer taken without a follow-up: a principle with no boundary asked, or no prediction
   put to the user?

`pass` means no finding would change the choice. Otherwise `return`, and the designer settles each
item before the user sees the question.
