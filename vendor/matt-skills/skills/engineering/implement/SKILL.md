---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Choose validation from the work's intent. Use /tdd when the behavior warrants a red-first loop at a
meaningful seam; otherwise use focused direct checks.

Run typechecking and focused tests regularly, then the applicable full suite at the end.

When independent review is requested, use /code-review, binding it to the fixed subject that
procedure requires.

Commit, land, or otherwise mutate repository history only with applicable user authority; otherwise
return the validated subject without forcing persistence.

Implementation is complete when every supplied spec or ticket criterion is accounted for, every
changed path is characterized, every applicable check and outcome is recorded, and unresolved
blockers or residual risks are reported with the fixed subject.
