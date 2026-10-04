# Execution operations

## Placement

From the ticket, code knowledge, write scopes, and runtime capabilities, choose a writer by handoff
cost and completeness. Work directly when context and changes are already located, or a correction
joins internal logic with Orchestrator-owned interface/tests. Delegate a settled, independently
implementable internal change; investigate ambiguity first. Direct work keeps the same ticket,
checks, and review duties.

Stop for unclear contracts, overlapping ownership, or a child assignment requiring user, interface,
formal-test, or architecture decisions. Finish with one writer, checkout, scope, and authority.

## Prepare

Use the current ticket/scope, integration, repository bootstrap instructions, and mutation authority.

1. Prepare the lane from current integration and run repository-declared worktree bootstrap.
   Keep lane/environment until closure. Stop on failed bootstrap, missing capability, ambiguous
   authority, or unexplained checkout changes.
2. Settle the contract. A new or changed public interface gets its declaration, result/error types,
   one real shipped-path caller, and formal tests under Test ownership before internal work starts.
3. Prepare gates under Gate preparation.
4. Mark doing with branch when implementation starts. To hand the work to an implementer, continue
   with [Delegate](#delegate).

Preparation finishes when contract, gates, checkout, and environment allow execution without
scanning task history. Proposed revisions return through dev-flow Plan's common change decision;
preparation does not impose its own user-approval condition.

## Gate preparation

During contract preparation, select focused behavior/regression tests and relevant typecheck, lint,
or build commands. Tests observe shipped interfaces and results; directly review prose, static
content, configuration, repository data, and responsibility placement. A validation driver may run
checks, but its script behavior is not a test target.

In Mechanical gates, list each gate as a command that runs as written from its named cwd, with the
criterion it checks. Scripts a gate needs live in the commit or the task's `scripts/`. Environment,
result, and exit status are recorded when the gate runs, in the gate summary. If no gate applies,
record why and name the direct observation and its owner. A required gate that cannot run keeps the
ticket out of ready.

For TDD, read tdd and prepare the plan during RED; the focused behavior test must fail for intended
missing behavior, not setup/import/collection errors. Add tests incrementally. Other gates need not
run or fail in RED; non-TDD work needs preparation without an invented RED.
Run required gates at GREEN and delivery. Plan expensive/assembled checks with an owner: run on the
lane before collection or assign an integration ticket. Record observations under dev-flow
[Record permissions](../../dev-flow/references/lane-authority.md).

## Test ownership

The Orchestrator writes formal behavior/regression tests and public interfaces under exclusive
checkout ownership. Use confirmed scenarios, Acceptance, Mechanical gates, shipped callers, and repo
test instructions. Observe public results; helpers receive coverage through their contribution.
Stop for unconfirmed behavior/ownership, internal-shape or prose assertions, another writer, or
missing environment. Finish with observable agreed behavior, recorded gates, and released or
transferred write ownership.

## Implement

Under the ready contract and exclusive writer assignment, implement internal logic, run assigned
gates in their order/timeouts, remove probes, inspect diff, commit, and stop writing.
A timeout is incomplete. Rerun after a change, new hypothesis, or explicit reproduction purpose;
unchanged repeated diagnostics stop with their blocker.

Completion requires a clean committed candidate and gate summary beside raw logs under
`runs/<short-sha>/summary.md`. Return commit and summary path.
A blocked result names all known obstructions and the next decision/execution owner.

## Delegate

Read this section only when an implementer will write the ticket's internal logic.

**Seed.** For a new or changed public interface, the Orchestrator holds the writer slot and commits
the declaration, result/error types, shipped caller, and formal contract tests for the agreed
normal/error/boundary scenarios, then transfers checkout ownership. Contract starting point records
the seed commit, exact interface/caller/test locations, expected failures, and the remaining internal
sequence. A complete existing contract needs no seed. The implementer chooses private organization;
interface, formal-test, public-behavior, performance, and responsibility changes return to the
Orchestrator.

**Brief.** Read the receiver's public contract and the runtime dispatch operation. Fill
`../../dev-flow/templates/ticket/brief.md` and send it as the dispatch; save the child ID. Historical
records are not a substitute for the brief.

**Tests in a delegated lane.** Implementers run assigned tests and may use temporary run-owned
probes; they remove probes before commit and report useful scenarios for formalization. A coverage
blocker names a reachable defect or agreed observation obligation and its evidence gap. Formal-test
fixes return to the Orchestrator; internal logic goes to its writer. Mutating checkers require that
writer's authority.

## Results and continuity

Role payloads keep outcome COMPLETED or BLOCKED, optional message, and required blocker on BLOCKED.
A COMPLETED implementer names commit/summary in message; an acceptor names its verdict. Missing named
files make a result incomplete. Use `Residual risks:` for non-blocking findings, not a new result field.

Inspect actual checkout and gate evidence before collecting a writer's candidate; its result
does not substitute for observation. Save new outcome facts under dev-flow record operations.
For interruption, inspect checkout, result, and executor state before resuming or replacing.
A replacement receives original assignment, blockers, verified/unverified work, environment,
authority, and stops. Uncertain writer/candidate/result state blocks continuity.

Questions use the runtime's live parent channel; single-return runtimes use BLOCKED and a fresh
dispatch after the answer. Continuity resumes only after the missing state or answer is established.
