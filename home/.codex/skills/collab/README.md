# Maintainer design notes

This README is for maintainers. Runtime agents should enter through `SKILL.md` and its operation
routes, not read this file as startup material.

## Why this split exists

The old entries loaded planning, dispatch, review, correction, integration, landing, and archival rules
together. Most actions need one branch of that workflow. The short entries now retain shared
invariants and route to a few self-contained operation documents. This lowers routine reading without
hiding authority or completion rules behind an implied second read.

The workflow also avoids two expensive defaults. It delegates only work whose contract is complete
enough to survive a handoff, and it gives a ticket or batch one acceptor with one effective reviewable
BLOCKED allowance by default. This is a stopping rule, not weaker evidence. After that verdict, one
bounded correction runs its gates and ends at cutoff or pending unless the user grants more review.

## Rule ownership

| Concern | Owner |
|---|---|
| Task scope, tickets, alignment, INDEX, lifecycle | `dev-flow` |
| Batch review brief and allowance history | `dev-flow/references/records.md` and `reviews/<review-id>.md` |
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
| Implementer | Injected profile, bounded dispatch, named contract anchors, repository instructions, technical skills, seed/caller/test locations, environment, gates, blockers | INDEX, task graph, review counts, landing and archive rules |
| Acceptor | Injected profile, immutable subject and baseline, bounded criteria/scenarios, interface/test duties, applicable instructions, candidate-bound observations and findings | Implementation sequence, provisioning, scheduling, landing, gate execution procedures |

A dispatch must state exact repository instruction and technical skill paths with read conditions. It
must also name explicit absence. "Follow relevant rules" is not a usable source pointer. Progress or
Resolution is not categorically hidden; dispatch points there when it owns a current blocker or
observation.

## Review and cutoff invariants

One acceptor judges the complete assigned criterion set. A reviewable subject is one exact clean
commit/tree with a baseline, stopped writer, stable brief, and required observation owners. Questions,
missing baselines, mutable subjects, and withdrawn prerequisites are assignment failures, not defect
verdicts. Repair the missing input, but stop repeated preparation failures with their owner.

A new ticket or batch created under this contract defaults to one effective BLOCKED verdict. Keep
historical limits, verdicts, candidates, and counts. For a pre-default record lacking a numeric
allowance, recover it from the governing version or original owner and stop rather than substituting
one. Replacing an agent, changing a candidate, or renaming a claim set does not reset the count.
Existing approved obligations override the new default. A batch covers named tickets,
criteria, cutoff claims, and interactions on one integration subject. Its approval establishes only
those claims and never silently upgrades unrelated cutoff work.

After the cap, make one final bounded correction. Passing gates and Orchestrator judgement allow a
cutoff record that separates established claims from fixes and claims not independently confirmed.
Otherwise the work stays pending. A user may grant another allowance explicitly.

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

Timeouts are gate-specific and bounded. A timeout is incomplete. Repeat diagnosis only after a new
change, new hypothesis, or explicit reproduction purpose. Plan expensive batch observations up front;
they do not erase ticket-required gates.

## Portable policy and runtime bindings

The Markdown operation references own portable policy. Runtime files contain only mechanics that
differ. Do not update a verified runtime hash merely because policy prose changed. The profile injected
at spawn is an attempt's frozen contract; the current disk profile applies to a fresh spawn. Candidate
workflow files under review are data, not an invitation for the reviewer to adopt them.

Maintain six profiles manually:

- Pi: two Markdown files, live `contact_parent`, Pi model lists and tools.
- Claude: two Markdown files, single-return decision handling, Claude frontmatter.
- Codex: two TOML files, single-return handling, sandbox and reasoning fields.

Keep the common role contract semantically equal while preserving those wrappers. Do not copy one
whole file over another. Exceptional evidence uses the exact method path supplied by dispatch, which
keeps Pi and Claude profiles independent of Codex installation paths.

## Walkthrough and evaluation

Before release, walk these cases against the candidate: direct fix, fresh implementer, fresh acceptor,
first effective BLOCKED followed by final correction, batch cutoff, historical non-default allowance,
unreviewable assignment, stale gate evidence, context reorientation, and a profile update between old
and fresh attempts. Check that each path reaches its authority, stop, completion, and record owner.

Measure required lines and UTF-8 bytes for representative paths before and after a change. Those
numbers describe document size only. They are not tokenizer output, cumulative prompt savings, runtime
cost, or proof that agents obey the routes. Cost projections must state sample window, model mix,
review-count assumptions, omitted correction and Orchestrator costs, and the lack of a real batch sample
when applicable. A fresh runtime replay is the right follow-up experiment; estimates are not acceptance.
