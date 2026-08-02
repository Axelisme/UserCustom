---
name: orchestrate
description: Git lanes for dispatched task work. Use when dispatching implementation to worker agents, integrating or landing completed lanes, checking task or lane state, or when a runtime binding needs the lane dispatch contract. Not for work one agent completes in a single context.
skill_version: 144
---

# Orchestrate

Orchestrate is the **Git task lane**. It owns managed lane and integration worktrees, exact
Git-backed task state, acceptance snapshots, local persistence landing, reporting, and runtime
bindings. Git commits, refs, SHAs, trailers, and worktree state are its durable inputs. It may
consume dev-flow task IDs but stores no task narrative. The shared
[admission standard](../dev-flow/references/admission-standard.md) is the sole normative S0–S5
authority; Root reads its current S0 before creating the first lane.

## Minimum complete lifecycle

1. `integration create --task-id <task>` creates the append-only task integration branch and
   worktree at the current repository subject. Done when the integration branch and worktree exist.

2. `lane create --task-id <task> --lane-id <lane> --group <need>` creates one managed writer branch
   and worktree at the recorded task base. A lane is one admitted Contract, one worktree, one
   branch, and one `lane-worker` call. `--group` names the need the lane serves and is the only
   thing that survives a recut: lane ids are recreated, the group is what counts across them. Reuse
   the same group when re-cutting or re-admitting the same need, and give a new need a new one.
   Root dispatches the exact canonical cwd and Git identity and preserves primary-checkout dirt.
   Done when the lane branch and worktree exist at the recorded base.

3. The worker commits Contract tests before implementation and reports focused red evidence plus
   its exact clean tip. Contract paths remain protected by normalized `Immutable:` trailers. Done
   when Root holds the reported red evidence and the exact clean tip SHA.

4. Before collection, use `lane check --task-id <task> --lane-id <lane>` to apply the shared
   first-parent, cleanliness, topology, and declaration predicates without mutation. Done when
   `lane check` exits 0.

5. If another collect advanced the integration tip, `lane sync --task-id <task> --lane-id <lane>`
   performs the writer-owned no-commit merge in that lane; the writer resolves and commits any
   conflict there. Done when the lane tip carries the merge (or is unchanged, if no sync was
   needed).

6. Root reruns the gates (return to step 4) until `lane check` exits 0 against the current
   integration tip.

7. `integration collect --task-id <task> --lane-id <lane>` creates one fixed-parent no-ff collect
   commit and removes the managed lane worktree. Done when the collect commit exists and the lane
   worktree is gone.

8. When every admitted increment is collected and the required shared gates pass, `acceptance
   start --task-id <task>` checks out the current integration subject in the managed detached
   acceptance worktree. Acceptance evaluates that exact subject. Done when the acceptance worktree
   holds the exact integration subject.

9. `acceptance result --task-id <task> --outcome pass` moves `refs/orchestrate/<task>/accepted` to
   it; `--outcome fail` records the failure and revokes only an equal accepted ref. A newer start
   may supersede an older accepted snapshot without deleting it until another pass establishes new
   authority. Done when the result is recorded and, on pass, the accepted ref points at the
   evaluated subject.

10. Landing requires an accepted snapshot and exactly one local checkout of the named persistence
    branch. `integration land --task-id <task> --persist <branch>` creates one canonical squash
    commit with `Task:` and `Landed:` trailers, then records the accepted subject in
    `refs/orchestrate/<task>/landed`. Orchestrate never pushes or reads remote refs. Done when the
    landed ref points at the accepted subject.

11. `integration remove --task-id <task> --output-dir <dir>` writes the final report and removes
    only a closeable task's exact managed inventory. `--no-report` explicitly omits report output.
    Done when the report is written (unless `--no-report`) and the closeable managed inventory is
    removed.

### Exceptions to the main sequence

A clean unwanted lane is removed with `lane drop` instead of being collected.

If persistence moved before landing, create an admitted reconciliation lane and run `integration
reconcile --task-id <task> --lane-id <lane> --persist <branch>`; the writer owns the resulting
no-commit merge, resolution, tests, commit, and normal collection (steps 4–7) before acceptance
(steps 8–9) is repeated.

Destructive `--abandon` on `integration remove` is exceptional current-user authority, not an
automatic recovery path. It reports unlanded and uncollected state while preserving unrelated refs,
paths, and user dirt.

## Observation and timing

`status` is the only task discovery and state projection. Without a task ID it lists known tasks;
with `--task-id` it reports the exact base, integration, lanes, acceptance, accepted, landed,
telemetry, and closeability slots that exist. It does not synthesize missing authority.

`lane_consumption` is the exception to "what exists": it reports, per `--group`, every lane the need
has ever been given, including lanes already collected or dropped, and names them. A need at the
threshold is also reported on the next `lane create`, because that is the moment the number can
still change what Root does. The [admission standard](../dev-flow/references/admission-standard.md)
owns what a group at the threshold means and what to do about it.

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
cleanup authority. Root owns Contract semantics, pre-collect test review, primary dirt, collection,
acceptance coordination, landing, and recovery. A provider, cwd, lane identity, Interface, or
observable Contract change requires fresh admission rather than continuation.
