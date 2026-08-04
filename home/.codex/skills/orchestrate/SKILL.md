---
name: orchestrate
description: Git lanes for dispatched task work. Use when dispatching implementation to worker agents, integrating or landing completed lanes, checking task or lane state, or when a runtime binding needs the lane dispatch contract. Not for work one agent completes in a single context.
skill_version: 159
---

# Orchestrate

Orchestrate is the **Git task lane**. It owns managed lane and integration worktrees, exact
Git-backed task state, acceptance snapshots, local persistence landing, reporting, and runtime
bindings. Git commits, refs, SHAs, trailers, and worktree state are its durable inputs. It may
consume dev-flow task IDs but stores no task narrative. [Admission](references/admission.md) is the
normative S1–S5 authority for dispatched work; dev-flow owns the S0 design admission that precedes
it, and Root reads that S0 before creating the first lane.

## Minimum complete lifecycle

1. `integration create --task-id <task>` creates the append-only task integration branch and
   worktree at the current repository subject. Done when the integration branch and worktree exist.

2. `lane create --task-id <task> --lane-id <lane> [--comment <text>]` creates one managed writer
   branch and worktree at the recorded task base. A lane is a persistent writer workstation for the
   task; the ticket owns the admitted Contract and validation mode. The same lane may serve multiple
   worker calls and collect/rework cycles. The optional comment is a bounded annotation only; use
   `lane comment --task-id <task> --lane-id <lane> --text <text>` to overwrite it or `--clear` to
   remove it. Root dispatches the exact canonical cwd and Git identity and preserves primary-checkout
   dirt. Done when the lane branch and worktree exist at the recorded base.

3. Execute the admitted Contract in its recorded validation mode. Root records `Validation mode:
   TDD` when a reasonable production red oracle exists; in TDD mode the worker commits Contract tests,
   fixtures, and test adapters before implementation, records focused red evidence, and keeps
   Contract paths protected by normalized `Immutable:` trailers. Root records `Validation mode:
   direct — <specific reason>` when no reasonable production red state exists; direct mode freezes
   the acceptance surface and validates the delivery without fabricating Contract tests, fixtures,
   red evidence, or `Immutable:` trailers. File type never selects the mode, and the worker cannot
   downgrade TDD to direct; if execution changes the mode judgment, stop and return to Root for
   re-admission. Done when Root holds the mode-appropriate evidence and exact clean tip SHA.

4. If another collect advanced the integration tip, `lane sync --task-id <task> --lane-id <lane>`
   performs the writer-owned no-commit merge in that lane; the writer resolves and commits any
   conflict there. Done when the lane tip carries the merge (or is unchanged, if no sync was
   needed).

5. `integration collect --task-id <task> --lane-id <lane> --ticket <ticket>` applies the shared
   first-parent, cleanliness, topology, and declaration predicates and refuses before any repository
   change when one fails, then creates one fixed-parent no-ff collect commit with `Task:`, `Lane:`,
   and bounded `Ticket:` trailers. Collection retains the lane worktree, branch, and original base
   ref; `lane drop` remains the explicit discard operation. Done when the collect commit exists and
   the persistent lane remains available.

6. `acceptance start --task-id <task> [--sha <exact>]` checks out one managed detached acceptance
   snapshot. Omission selects the managed integration branch tip; an explicit full SHA may select
   any commit on its first-parent history. Integration worktree state is irrelevant because the
   subject is a commit. Done when the acceptance worktree holds the selected exact subject.

7. Run canonical tests and the read-only Standards/Spec ReviewGate on that managed acceptance
   checkout. `acceptance result --task-id <task> --verifier agent|user --outcome pass|fail` records
   the exact result. Agent pass moves `refs/orchestrate/<task>/accepted`; user pass moves
   `refs/orchestrate/<task>/user-accepted`, and either may move backward explicitly. Failure revokes
   only the same verifier's equal ref. User evidence does not affect landing or closeability. Done
   when the result, ref state and telemetry agree.

8. Landing requires an accepted snapshot and exactly one local checkout of the named persistence
   branch. `integration land --task-id <task> --persist <branch>` creates one canonical squash
   commit with `Task:` and `Landed:` trailers, then records the accepted subject in
   `refs/orchestrate/<task>/landed`. Orchestrate never pushes or reads remote refs. Done when the
   landed ref points at the accepted subject.

9. `integration remove --task-id <task> --output-dir <dir>` writes the final report, including
   agent and user acceptance evidence, and removes only a closeable task's exact managed inventory. `--no-report` explicitly omits report output.
   Done when the report is written (unless `--no-report`) and the closeable managed inventory is
   removed.

### Exceptions to the main sequence

A clean unwanted lane is removed with `lane drop` instead of being collected.

If persistence moved before landing, create an admitted reconciliation lane and run `integration
reconcile --task-id <task> --lane-id <lane> --persist <branch>`; the writer owns the resulting
no-commit merge, resolution, tests, commit, and normal collection (steps 4–5) before acceptance
(steps 6–7) is repeated.

An acceptance failure grants no repair by itself. Once Root admits its bounded correction, an
implementation bug, preserving test correction, or additive-only observable correction resumes the
same worker context when it remains an asset. Context debt or a wrong observable starts a fresh worker
run in the same lane. An additive-only observable opens a new ticket and repeats S1; a lane no longer
needed uses `lane drop`. The matching runtime binding defines how writer context and reviewer context
continue.

Destructive `--abandon` on `integration remove` is exceptional current-user authority, not an
automatic recovery path. It reports unlanded and uncollected state while preserving unrelated refs,
paths, and user dirt.

## Observation and timing

`orchestrate.py --version` is the top-level version query and returns the normal JSON envelope; there
is no `version` subcommand. `status` is the only task discovery and state projection. Without a task
ID it lists known tasks; with `--task-id` it reports the exact integration SHA, active lanes as
`{sha, comment?, uncollected}` objects, top-level `pending`, accepted, `user_accepted`, landed, and
real inventory warnings. `uncollected` is the Git-derived first-parent work not reachable from
integration; `pending` independently counts collected lanes awaiting agent acceptance. The managed
acceptance worktree and historical lane/comment data are not synthesized into current status.

Lane comments are append-only annotations and never grant lifecycle, acceptance, landing, or cleanup
authority. They project only while the lane is active. After a successful create, the current
ninth-lane warning is factual: it counts only active lanes with projected `uncollected > 0`; pending
lanes with zero uncollected work do not count, and creation never blocks. Historical, closed, dropped,
and collected lanes do not count. Agent acceptance records authority first, then automatically closes
clean named lanes; anomalies retain the lane and warn Root for explicit correction or drop.

`lane check --task-id <task> --lane-id <lane>` applies the same predicates collection enforces,
without mutation, and reports the lane `sha`, `base`, `protected_paths`, and the `contract_commits`
declaring `Origin: contract`. When a per-task gate script exists it adds one factual warning naming
it. This is how Root reads a lane — most usefully to bind the identity binding a dispatch carries —
not a gate collection needs run first; a lane that fails it fails collection identically, with the
same diagnostics.

`report --task-id <task> --output-dir <dir>` atomically writes the two fixed report artifacts from
Git and append-only telemetry. `timing pause --task-id <task>` closes active timing before an
external wait; `timing resume --task-id <task>` resumes it. Repeated matching transitions are
idempotent warnings. Reports and status remain read-only.

## Package administration

Doctor, doctor diff, pin, and release are covered in [package-admin.md](references/package-admin.md); read it
before a release or pin change.

Every command prints one JSON object with `orchestrate_version`. Success is on stdout with exit 0;
a completed negative predicate uses stdout and exit 1; an operational or usage error uses stderr
and exit 2. Mutation commands fail before repository changes when the executing package is
unhealthy. Read-only diagnosis remains available.

## Runtime and authority boundaries

Read the matching [Codex runtime](runtime-codex.md), [Claude runtime](runtime-claude.md), or
[Pi runtime](runtime-pi.md) before dispatch. Runtime bindings transport the frozen dispatch and
exact-run evidence; they do not grant admission, collect, acceptance, persistence, setup, pin, or
cleanup authority. Beyond the shared authority in [dispatch.md](references/dispatch.md), Root owns Contract
semantics, the S2.5 mechanical guarantee, and primary dirt. A semantic change to the ticket's Contract requires
fresh admission; persistent-lane rework does not automatically change its lane or session. Provider
and liveness recovery follows the context asset/debt routing in dispatch.
