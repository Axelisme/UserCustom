---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Validation counts when it exercises the shipped entrypoint: a check that passes against a stand-in
while the production path stays broken has validated nothing. Use /tdd when that check can be written
before the behavior exists. Where it cannot — a GUI surface, a hardware edge, a check only a human
can make — follow the test conventions the repository documents, and say which you used.

Run typechecking and focused tests regularly, then the applicable full suite at the end.

When independent review is requested, use /code-review, binding it to the fixed subject that
procedure requires.

Commit, land, or otherwise mutate repository history only with applicable user authority; otherwise
return the validated subject without forcing persistence.

Implementation is complete when every supplied spec or ticket criterion is accounted for, every
changed path is characterized, every applicable check and outcome is recorded, and unresolved
blockers or residual risks are reported with the fixed subject.
