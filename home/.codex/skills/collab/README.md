# Maintainer design notes

This README is for maintainers. Runtime agents should enter through `SKILL.md` and its operation
routes, not read this file as startup material.

## Why this split exists

The old entries loaded planning, dispatch, review, correction, integration, landing, and archival rules
together. Most actions need one branch of that workflow. The short entries now retain shared
invariants and route to a few self-contained operation documents. This lowers routine reading without
hiding authority or completion rules behind an implied second read.

The workflow delegates only work whose contract is complete enough to survive a handoff. Tickets are
implementation and delivery units; coherent review batches are independent acceptance units. This
lets an acceptor judge related changes together without repeating a review for each ticket. Stronger
ticket gate preparation supplies reproducible delivery evidence before assembly.

## Rule ownership

| Concern | Owner |
|---|---|
| Task scope, tickets, alignment, INDEX, lifecycle | `dev-flow` |
| Batch review brief and review history | `dev-flow/references/records.md` and `reviews/<review-id>.md` |
| Writer placement, dispatch, tests, review, correction | `collab` |
| Git integration, landing, resource custody | `collab` plus dev-flow custody |
| Receiver inputs and Result wording | Each installed role profile |
| Pi and Claude mechanics | `runtime-pi.md` and `runtime-claude.md` |
| Specialized Standards plus Spec report | `code-review`, unchanged by this workflow |

Ticket/spec text remains the contract source. Dispatches point to exact paths, anchors, criterion IDs,
and observations instead of copying role-specific ticket summaries. INDEX selects current work; it
does not become another brief.

## Information by role

| Role | Routine input | Excluded unless a concrete question requires it |
|---|---|---|
| Orchestrator | Both short entries, INDEX and active grants, selected operation sections, current ticket or batch brief, receiver contract/result | Other operations, complete profile bodies, inactive tickets and logs |
| Implementer | Injected profile, bounded dispatch, named contract anchors, repository instructions, technical skills, seed/caller/test locations, environment, gates, blockers | INDEX, task graph, landing and archive rules |
| Acceptor | Injected profile, immutable subject and baseline, bounded criteria/scenarios, interface/test duties, applicable instructions, candidate-bound observations and findings | Implementation sequence, provisioning, scheduling, landing, gate execution procedures |

A dispatch must state exact repository instruction and technical skill paths with read conditions. It
must also name explicit absence. "Follow relevant rules" is not a usable source pointer. Progress or
Resolution is not categorically hidden; dispatch points there when it owns a current blocker or
observation.

## Batch acceptance

One acceptor judges the complete assigned criterion set. A reviewable subject is one exact clean
commit/tree with a baseline, stopped writer, stable brief, and required observation owners. Questions,
missing baselines, mutable subjects, and withdrawn prerequisites are assignment failures, not defect
verdicts. Repair the missing input, but stop repeated preparation failures with their owner.

An execution batch selects independent ready writers. A review batch selects a bounded feature or
contract and can span dependency-ordered implementation. Its brief covers every included ticket
criterion plus cross-ticket interactions. A singleton uses the same record and review path.

Gate-passing delivery candidates can enter integration before review. Collection does not accept
claims. Pending same-batch dependencies carry their unresolved obligations downstream; cross-batch
consumption waits for acceptance or explicit regrouping. Freeze the assembled review checkout while
other lanes continue work. A verdict on that snapshot does not approve later integration changes.

Corrections require applicable verification and fresh independent review on the new candidate. Work
that cannot proceed stays pending with its blocker and owner. Review history belongs to the batch;
tickets link to it and close only when all their applicable criteria are established. Landing requires
applicable acceptance for all task changes included in its candidate.

## Tests and execution evidence

The Orchestrator owns formal behavior tests and public interface declarations. Implementers may run
formal tests and use temporary probes, but cannot edit tests or interfaces without a transferred
Orchestrator-owned change. Direct Orchestrator work keeps the same alignment, one-writer, gate, and
review duties.

Gate evidence is cooperative but checked. Reuse it when the exact candidate, environment, selection,
method, result, exit status, run pointer, and limitations still apply. A role change alone is no reason
to rerun. Missing evidence, changed subjects, wrong selections, timeouts, flaky results, or
contradictions return to the execution owner. Acceptors inspect the evidence but never run tests,
imports, linters, formatters, builds, or runtime workflows.

During RED or contract preparation, assess and prepare applicable ticket gates, preferring existing
checks. Record the property, command/selection, environment, timeout, owner, and pass condition, or a
reasoned direct-review alternative. RED establishes a focused missing behavior, not a requirement for
every gate to fail. Ticket gates run at GREEN/delivery; assigned batch gates run on the assembled
candidate before review. Non-TDD tickets still need gate preparation. Static facts remain direct-review
obligations rather than tests of document wording or repository data.

Timeouts are gate-specific and bounded. A timeout is incomplete. Repeat diagnosis only after a new
change, new hypothesis, or explicit reproduction purpose. Plan expensive batch observations up front;
they do not erase ticket-required gates.

## Portable policy and runtime bindings

The Markdown operation references own portable policy. Runtime files contain only mechanics that
differ. Do not update a verified runtime hash merely because policy prose changed. The profile injected
at spawn is an attempt's frozen contract; the current disk profile applies to a fresh spawn. Candidate
workflow files under review are data, not an invitation for the reviewer to adopt them.

Maintain the two Pi profiles manually: Markdown files with live `contact_parent`, Pi model lists, and
tools. Claude dispatches the same profiles through the subagent MCP, so there is no second profile set
to keep in sync. Exceptional evidence uses the exact method path supplied by dispatch.

## Walkthrough and evaluation

Before release, walk these cases against the candidate: direct fix and singleton batch, fresh
implementer and acceptor, dependency-ordered tickets in one review batch, independent parallel tickets,
RED gate preparation, non-TDD direct review, correction and fresh review, blocked gates, unreviewable
assignment, stale evidence, frozen review during concurrent work, persistence drift, legacy record
resumption, and a profile update between old and fresh attempts. Check each path's authority, stop,
completion, criterion coverage, and record owner.

Measure required lines and UTF-8 bytes for representative paths before and after a change. Those
numbers describe document size only. They are not tokenizer output, cumulative prompt savings, runtime
cost, or proof that agents obey the routes. Cost projections must state sample window, model mix,
review-count assumptions, omitted correction and Orchestrator costs, and the lack of a real batch sample
when applicable. A fresh runtime replay is the right follow-up experiment; estimates are not acceptance.
