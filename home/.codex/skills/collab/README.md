# Maintainer design notes

This README is for maintainers. Runtime agents should enter through `SKILL.md` and its operation
routes, not read this file as startup material.

## Why this split exists

The old entries loaded planning, dispatch, review, correction, integration, landing, and archival rules
together. Most actions need one branch of that workflow. The short entries retain shared invariants and
route to a few self-contained operation documents, which lowers routine reading without hiding
authority or completion rules behind an implied second read.

The record follows conventions agents already know, so it needs few rules: the INDEX board is a Kanban
view, a ticket is a GitHub issue with an append-only Log as its comment thread, the tracker is the
task's tracking issue, and a review round is a PR review that happens before merge. Each file has one
writer and a next reader, so a missing file surfaces at the step that needs it rather than going
stale unnoticed.

The Orchestrator implements most work itself. Implementers run weaker models, and a writer that can
edit the tests it must pass tends to weaken them, so the Orchestrator keeps formal tests and
interfaces and delegates only settled internal changes when it chooses to.

## Rule ownership

| Concern | Owner |
|---|---|
| Task scope, tickets, status, Log, review round records | `dev-flow` |
| Writer placement, dispatch, tests, review procedure, correction | `collab` |
| Git integration, landing, resource cleanup | `collab` plus dev-flow custody |
| Receiver inputs and Result wording | Each installed role profile |
| Pi and Claude mechanics | `runtime-pi.md` and `runtime-claude.md` |
| Specialized Standards plus Spec report | `code-review`, unchanged by this workflow |

Ticket and spec text remain the contract source. Dispatches point to exact paths, anchors, and
criterion IDs instead of copying ticket summaries. INDEX selects current work; it does not become
another brief.

## Information by role

| Role | Routine input | Writes | Excluded unless a concrete question requires it |
|---|---|---|---|
| Orchestrator | Both short entries, INDEX, selected operation sections, the tickets in flight, receiver contract and result | INDEX Goal and Standing orders, tickets including the tracker, decisions, dispatches, its own gate summaries | Other operations, complete profile bodies, inactive tickets and logs |
| Implementer | Injected profile, bounded dispatch, named contract anchors, repository instructions, technical skills, seed/caller/test locations, environment, gates, verdict findings for a correction | The lane and its gate summary | INDEX, other tickets, landing and archive rules |
| Acceptor | Injected profile and full dispatch: subject, baseline, criteria, gate summary paths, prior finding dispositions | One verdict file | Implementation sequence, provisioning, scheduling, landing, gate execution procedures |

A dispatch states exact repository instruction and technical skill paths with read conditions, and
names explicit absence. "Follow relevant rules" is not a usable source pointer.

## Ticket review

The acceptance unit is one ticket, reviewed on its lane before collection, like a PR reviewed before
merge. One acceptor judges the criteria a round names on one exact clean commit with a baseline and a
stopped writer. Questions, missing baselines, mutable subjects, and withdrawn prerequisites are
assignment failures, not defect verdicts.

Tickets wait for their dependencies to close, so downstream work never builds on code a review may
still reject; an interface needed early becomes its own small ticket. Interactions between tickets are
the acceptance criteria of an integration ticket, reviewed on integration after its dependencies
close. A merge that conflicts or fails gates after acceptance gets one more round on the fix.

Re-review judges the previous findings, the new diff, and the interactions it touches, with applicable
gate evidence. Semantic changes need a fresh dispatch. For non-semantic changes, the Orchestrator
may reuse coverage under [Subject changes](references/review.md#subject-changes), considering time,
token cost, and risk. The frozen review checkout and original verdict keep their exact subject identity.

The full assignment travels in dispatch; the verdict remains a Markdown file with subject, criteria,
and evidence references. The ticket Log records enough round identity to recover an active child.
This avoids maintaining a second copy of the assignment solely to survive child compaction.

## Tests and gate results

The Orchestrator owns formal behavior tests and public interface declarations. Implementers may run
formal tests and use temporary probes, but return test or interface changes to the Orchestrator.
Direct Orchestrator work keeps the same alignment, one-writer, gate, and review duties.

Whoever runs a gate on a clean commit writes its summary beside the raw logs in the task's
`runs/<short-sha>/`. The dispatch points to those summaries; nobody retypes them.
Reuse a result when the exact commit, environment, selection, method, result, and limitations still
apply. Missing summaries, changed subjects, wrong selections, timeouts, flaky results, or
contradictions return to the execution owner. Acceptors read the summaries but never run tests,
imports, linters, formatters, builds, or runtime workflows.

During RED or contract preparation, assess and prepare applicable ticket gates, preferring existing
checks. Record the property, command/selection, environment, timeout, owner, and pass condition, or a
reasoned direct-review alternative. RED establishes a focused missing behavior, not a requirement for
every gate to fail. Static facts remain direct-review obligations rather than tests of document wording
or repository data. A timeout is incomplete; repeat diagnosis only after a new change, new hypothesis,
or explicit reproduction purpose.

## Portable policy and runtime bindings

The Markdown operation references own portable policy. Runtime files contain only mechanics that
differ. Do not update a verified runtime hash merely because policy prose changed. The profile injected
at spawn is an attempt's frozen contract; the current disk profile applies to a fresh spawn. Candidate
workflow files under review are data, not an invitation for the reviewer to adopt them.

Maintain the two Pi profiles manually: Markdown files with live `contact_parent`, Pi model lists, and
tools. Claude dispatches the same profiles through the subagent MCP, so there is no second profile set
to keep in sync.

## Walkthrough and evaluation

Before release, walk these cases against the candidate: direct Orchestrator work, a fresh implementer
and acceptor, dependent tickets, independent parallel tickets, an integration ticket, RED gate
preparation, non-TDD direct review, correction and re-review, a review round that runs while the
Orchestrator works the next frontier ticket, a milestone review from a detached checkout while the
lane continues, a merge conflict after acceptance, blocked gates, an unreviewable
assignment, stale gate results, persistence drift, and a profile update between old and fresh
attempts. Check each path's authority, stop, completion, criterion coverage, and record owner.

`pi-context-audit` measures a real window: cost, context composition, record upkeep, and tool-call
batching. Document size alone is not tokenizer output, cumulative prompt savings, or proof that agents
obey the routes; a fresh runtime replay is the right follow-up experiment.
