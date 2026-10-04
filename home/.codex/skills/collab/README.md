# Maintainer design notes

This README is for maintainers. Runtime agents should enter through `SKILL.md` and its operation
routes, not read this file as startup material.

## Why this split exists

The old entries loaded planning, dispatch, review, correction, integration, landing, and archival rules
together. Most actions need one branch of that workflow. The short entries retain shared invariants and
route to a few self-contained operation documents, which lowers routine reading without hiding
authority or completion rules behind an implied second read.

Task records hold only what an agent needs now or later and cannot recover from code, Git, or the
collab tools. Mutable sections are rewritten whole as snapshots, so no record grows into a diary.
User decisions in `decisions/` bind; `spec/` is design reference the Orchestrator may redesign after
weighing implementation cost, so agents stop to ask only when a change would contradict a user
decision.

The Orchestrator implements most work itself. Implementers run weaker models, and a writer that can
edit the tests it must pass tends to weaken them, so the Orchestrator keeps formal tests and
interfaces and delegates only settled internal changes when it chooses to.

## Rule ownership

| Concern | Owner |
|---|---|
| Task scope, tickets, status, decisions, Notes, Resources | `dev-flow` |
| Writer placement, dispatch, tests, review procedure, correction | `collab` |
| Git integration, landing, resource cleanup | `collab` plus dev-flow custody |
| Receiver scope, inputs, authority, and results | The role profile's shared `parent` contract, retrieved through role queries |
| Pi and Claude mechanics | `runtime-pi.md` and `runtime-claude.md` |
| Specialized Standards plus Spec report | `code-review`, unchanged by this workflow |

Ticket and spec text remain the contract source. Dispatches point to exact paths, anchors, and
criterion IDs instead of copying ticket summaries. INDEX selects current work; it does not become
another brief.

## Information by role

| Role | Routine input | Writes | Excluded unless a concrete question requires it |
|---|---|---|---|
| Orchestrator | Both short entries, INDEX, selected operation sections, the tickets in flight, role summaries and the selected public contract | INDEX Goal and Standing orders, tickets including the tracker, decisions, dispatches, its own gate summaries | Other operations, private profile fields and child procedures, inactive tickets and logs |
| Implementer | Injected shared contract and child instructions, bounded dispatch, named contract anchors, repository instructions, technical skills, seed/caller/test locations, environment, gates, verdict findings for a correction | The lane and its gate summary | INDEX, other tickets, landing and archive rules |
| Acceptor | Injected shared contract and child instructions, and full dispatch: commit range, tickets and criteria, gate summary path, prior findings | One verdict file | Implementation sequence, provisioning, scheduling, landing, gate execution procedures |

A dispatch states exact repository instruction and technical skill paths with read conditions, and
names explicit absence. "Follow relevant rules" is not a usable source pointer.

## Range review

Every product-code and test change is read once in a review of an integration commit range, not once
per ticket. A ref, `refs/collab/<task>/reviewed`, marks how far review has read, so "everything was
reviewed" is a Git fact checked before landing. Merging reviews saves time and tokens; the cost is
finding defects later. The one early review guards the expensive case: a ticket about to build on a
public interface that no review has read yet. Size only splits a range among acceptors.

Tickets close on gates and collection. Findings become fix tickets, and the next range review reads
the fix commits. Review inputs are pointers, not copies, and the review checkout is not frozen; the
verdict records the head it read.

## Tests and gate results

The Orchestrator owns formal behavior tests and public interface declarations. Implementers may run
formal tests and use temporary probes, but return test or interface changes to the Orchestrator.
Direct Orchestrator work keeps the same alignment, one-writer, gate, and review duties.

Whoever runs gates on a commit writes `runs/<short-sha>/summary.md` with fixed fields beside the
raw logs, only for a lane tip about to be collected or an integration head about to be reviewed.
Ordinary TDD cycles keep nothing; a bug reproduction keeps its RED run. The dispatch points to those
summaries; nobody retypes them. Missing summaries, wrong selections, timeouts, flaky results, or
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

Maintain one Markdown profile per role. Frontmatter keeps the runtime's model lists and tools,
`description` supplies the discovery summary, and `parent` holds the shared contract. The body holds
child-only procedures. Put shared obligations in `parent` once, not in both contract and body.
The runtime injects the shared contract, child instructions, and dispatch into the child prompt.
Parents use role discovery and contract lookup without reading profile sources. Claude dispatches
the same Pi profiles through the subagent MCP, so there is no second profile set to keep in sync.

## Walkthrough and evaluation

Before release, walk these cases against the candidate: direct Orchestrator work, a fresh implementer
and acceptor, dependent tickets, independent parallel tickets, an integration ticket, RED gate
preparation, a bug reproduction, a range review before landing, an early range review before a
downstream ticket uses an unreviewed interface, a split range, findings fixed and read by the next
range, a merge conflict after collection, blocked gates, stale gate results, persistence drift, and a
profile update between old and fresh attempts. Check each path's authority, stop, completion, criterion coverage, and record owner.

`pi-context-audit` measures a real window: cost, context composition, record upkeep, and tool-call
batching. Document size alone is not tokenizer output, cumulative prompt savings, or proof that agents
obey the routes; a fresh runtime replay is the right follow-up experiment.
