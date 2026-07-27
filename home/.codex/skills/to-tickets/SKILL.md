---
name: to-tickets
description: Break a spec into dependency-addressable tracer-bullet ticket artifacts.
---

# To Tickets

This skill produces **artifacts only**: tracer-bullet tickets with explicit blocking edges. Work
from the conversation or a supplied spec, use the repository glossary, and preserve the recorded
usage envelope. Each ticket is a complete, observable Slice with a named deletion or a seam whose
predecessor is named; refuse a ticket whose value waits on a later ticket.

## Draft

For every ticket record title, blockers, observable sentence, deleted predecessor, delivered
behavior, and verbatim acceptance commands with cwd/environment. Keep the DAG dependency-addressable
and fit each Slice in one fresh context. Wide mechanical refactors may use expand–contract, with
migration tickets blocked by expand and contraction blocked by all migrations.

Present the proposed list for approval before publishing. After approval, publish dependency-
addressable Slices to the plan-directory, tracker, or local backend documented by the repository.
Across backends each Slice keeps Observable, Deletes, delivery, blockers, and acceptance criteria.
This skill owns **artifacts only**; execution and checkpoint/close-out authority remain with their
owning surfaces.

## Publish

In a plan-directory repo, publish Slices in the task plan and let Root dispatch each ready Slice
through Oracle, exact Contract merge, and Implementation. Do not create per-ticket state. In a
tracker, publish issues with native blocking edges. Otherwise write numbered local ticket files
under `.scratch/<feature-slug>/issues/`. Never modify the source issue.
