# Execution operations

## Placement

Inputs are the confirmed ticket, current code knowledge, write scopes, and available runtimes. The
Orchestrator chooses the writer by handoff cost and work completeness, not line count.

Work directly when the Orchestrator already holds the relevant context and the change is located, or
when a small correction joins production and Orchestrator-owned interface or formal-test edits.
Delegate a settled, independently implementable and verifiable internal change. Investigate or align
an ambiguous problem before assigning it. Direct work keeps the same ticket, one-writer, checks, and
batch-review duties.

Stop when the contract is unclear, writer ownership overlaps, or the proposed child would need to make
a user, interface, test, or architecture decision. Placement is complete when one writer, checkout,
write scope, authority, and handoff boundary are explicit.

## Prepare

Inputs are the pending ticket, approved scope, current integration, repository bootstrap instructions,
and mutation authority. The Orchestrator prepares one safe checkout per concurrent writer. Preserve
pre-existing dirt and evidence. Run repository-declared worktree bootstrap before dispatch and retain
the environment through implementation, correction, review, and owner-decision waits.

For delegated work, read the receiver's `Dispatch contract` and `Result` sections and the selected
runtime operation. The dispatch names:

- exact checkout, branch-local commit authority, exclusive writer, and persistence/push exclusions;
- exact ticket or brief anchors and assigned criteria/checks;
- applicable repository instruction and technical skill paths with read conditions, or explicit none;
- runtime, interpreter, environment, caches, test selection, timeout, and cleanup exceptions;
- prior blockers, stop conditions, escalation owner, and profile source for reorientation;
- exceptional evidence target and exact method pointer, or none.

Stop on failed bootstrap, missing capability, ambiguous authority, or unexplained checkout changes.
Preparation is complete when the bounded brief, writer, checkout, environment, and sources are usable
without scanning INDEX or unrelated task history.

## Contract seed

For a new or changed public interface, the Orchestrator writes the confirmed interface and declaration,
result and error types, one real shipped-path caller, and formal contract tests for agreed normal,
error, and boundary scenarios. Hold write ownership, commit the seed, then transfer the checkout.

Record the seed commit, exact interface/caller/test locations, expected failures, and a short remaining
internal implementation sequence in Contract starting point. A complete existing contract needs no
seed. The implementer may choose private organization but returns interface, formal-test, public
behavior, performance, or responsibility changes to the Orchestrator.

Stop until the user confirms a material design change. The seed is complete when the public contract
and observations are explicit enough for a bounded internal implementation and independent review.

## Gate preparation

During RED or pre-implementation contract preparation, the Orchestrator assesses and prepares the
mechanical gates applicable to each ticket. Prefer existing focused behavior tests, affected regression
checks, and relevant typecheck, lint, or build commands. Add behavior tests only at confirmed seams or
contracts under [Test ownership](#test-ownership). Read the tdd skill when using red-green cycles.

In Mechanical gates, record the checked property and criterion, command/selection and working directory,
environment, timeout, execution owner, and pass condition. Verify the command and prerequisites are
usable. If no mechanical gate applies, state why and name the direct-review observation and owner.
Review prose, document wording, static content, configuration values, and repository data directly;
do not create tests of those facts to fill the gate list. A validation driver may run checks, but its
script behavior is not itself a test target.

Prepare the gate plan in RED; run the focused behavior test to establish the intended missing behavior.
Setup, import, collection, or unrelated failures are not RED evidence. Other gates need not fail or run
in RED. Keep behavior tests incremental rather than writing the entire suite before implementation.
For non-TDD work, complete the same gate preparation before implementation without inventing a RED.

At GREEN and delivery, run required ticket gates. Assign expensive or assembled-candidate checks as
batch observations during planning, with an owner and readiness condition. They run before batch
review, not as surprise replacements for ticket obligations. Missing capability or an unusable required
gate blocks implementation handoff until its owner resolves it. Preparation is complete when the gate
plan is executable or its justified direct-review alternative is recorded.

## Test ownership

Inputs are the confirmed ticket scenarios and criteria, current public interface and shipped callers,
existing formal tests, and the prepared checkout's writer authority. Read the ticket's Scenarios,
Alignment, Acceptance, and Mechanical gates plus repository test instructions named during Prepare.
The Orchestrator is the writer for formal behavior and regression tests and for public interface
changes. They exercise shipped public interfaces and observable results. Helpers receive coverage
through their contribution to that behavior.

Stop when behavior or interface ownership is unconfirmed, a proposed assertion tests prose or internal
shape instead of observable behavior, the checkout has another writer, or the required environment is
unavailable. Record the test path, covered criterion and scenario, command/selection, environment,
expected pre-fix failure when applicable, result, and limitation in Contract starting point or Progress.
Test work is complete when the agreed behavior is observable through a shipped interface, the assigned
gate is recorded, and write ownership is released or explicitly transferred.

An implementer runs assigned formal tests and may use run-owned temporary probes; remove probes before
commit and report useful scenarios for the Orchestrator to formalize. A coverage blocker names a
reachable behavior defect or agreed validation obligation and its evidence gap. Route formal-test
corrections to the Orchestrator and internal-logic corrections to the assigned writer. A mutating
checker runs only under the current writer's authority.

## Implement

Inputs are a ready ticket, prepared checkout and environment, exact dispatch, and exclusive write
ownership. The writer implements only the assigned internal logic, runs required gates in their stated
order and timeout, removes probes, inspects the diff, commits under branch-local authority, and stops
writing.

A gate timeout is incomplete, not passing. Rerun after a new change, new hypothesis, or explicit
reproduction purpose; repeated unchanged diagnostics stop with the blocker. Use the ticket gates and
batch assignments established during [Gate preparation](#gate-preparation); passing ticket gates makes
a delivery candidate, not an accepted ticket.

Completion requires a clean committed candidate and a concise handoff tying the final candidate to
each command or selection, environment, result and exit status, raw run pointer, and limitation. Keep
bulky output with the run. A blocked result aggregates known obstructions and names the next decision
or execution owner. The Orchestrator replaces the owning ticket's semantic checkpoint only when that
conclusion changes how the next owner resumes, verifies, or decides.

## Results and continuity

Role payloads retain the required `outcome` discriminator (`COMPLETED` or `BLOCKED`), optional
`message`, and required `blocker` on BLOCKED. `outcome` carries status only. A COMPLETED implementer
puts candidate and verification metadata in `message` unless dispatch named an exact durable record
that already contains every required item. If neither source contains them, the Orchestrator treats the
result as incomplete. `Residual risks:` carries non-blocking findings. Do not add a runtime result field.

A writer's COMPLETED result attests required gates passed, the checkout is clean and committed, and
assigned evidence is complete. The Orchestrator checks the actual checkout and evidence before
delivery judgement and collection. The ticket remains pending for its owning batch review. A
replacement receives the original assignment, blockers, verified and unverified work, environment,
authority, and stop conditions.

A role result owns its returned observations until the Orchestrator records the smallest durable
conclusion in the ticket or review record that owns the claim. Git and the run retain finer history.
Update INDEX's routing fields only when the conclusion creates a routing edge.

Questions use the runtime's live parent channel when available. Single-return runtimes use BLOCKED and
a fresh dispatch after the answer. An interrupted writer requires checkout and result inspection
before resume or replacement. Stop when the durable result, candidate, or writer state is uncertain;
continuity is restored only when those facts are observed.
