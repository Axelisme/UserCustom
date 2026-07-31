---
name: to-tickets
description: Break a spec into dependency-addressable tracer-bullet ticket artifacts.
---

# To Tickets

This skill produces **artifacts only**: tracer-bullet tickets with explicit blocking edges. Work
from the conversation or a supplied spec, use the repository glossary, and preserve the recorded
usage envelope. Each ticket records S1 evidence and dependency-addressable DAG artifacts; named
deletions or seam predecessors remain the ticket shape.

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

In a plan-directory repo, write each Slice directly as a shared generic `tickets/*.md` record:
use the three-field header, a `Resolve by` action, and `Outcome`/`Current`; encode blocking only in
`depends_on` and do not create a second ticket store. Its Slice evidence belongs in the producer's
content rather than a dev-flow schema. In a tracker, publish issues with native blocking edges.
Otherwise write numbered local ticket files under `.scratch/<feature-slug>/issues/`. Use authority
pointers for Oracle, merge and Implementation coordination. Never modify the source issue.
