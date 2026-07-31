---
name: orchestrate
description: Minimal Git-backed lane and task-integration workflow for a Git task.
skill_version: 138
---

# Orchestrate

Orchestrate is the **Git task lane**. It owns managed lane and integration worktrees, exact
Git-backed task state, acceptance snapshots, local persistence landing, reporting, and runtime
bindings. Git commits, refs, SHAs, trailers, and worktree state are its durable inputs. It may
consume dev-flow task IDs but stores no task narrative. The shared admission standard is the sole
normative S0–S5 authority; Root reads its current S0 before creating the first lane.

## Minimum complete lifecycle

`integration create --task-id <task>` creates the append-only task integration branch and
worktree at the current repository subject. `lane create --task-id <task> --lane-id <lane>` creates
one managed writer branch and worktree at the recorded task base. A lane is one admitted Contract,
one worktree, one branch, and one `lane-worker` call. Root dispatches the exact canonical cwd and
Git identity and preserves primary-checkout dirt.

The worker commits Contract tests before implementation and reports focused red evidence plus its
exact clean tip. Contract paths remain protected by normalized `Immutable:` trailers. Before
collection, use `lane check --task-id <task> --lane-id <lane>` to apply the shared first-parent,
cleanliness, topology, and declaration predicates without mutation. If another collect advanced the
integration tip, `lane sync --task-id <task> --lane-id <lane>` performs the writer-owned no-commit
merge in that lane; the writer resolves and commits any conflict there. Root reruns the gates and
then `integration collect --task-id <task> --lane-id <lane>` creates one fixed-parent no-ff collect
commit and removes the managed lane worktree. A clean unwanted lane is removed with `lane drop`.

When every admitted increment is collected and the required shared gates pass, `acceptance start
--task-id <task>` checks out the current integration subject in the managed detached acceptance
worktree. Acceptance evaluates that exact subject. `acceptance result --task-id <task> --outcome
pass` moves `refs/orchestrate/<task>/accepted` to it; `--outcome fail` records the failure and
revokes only an equal accepted ref. A newer start may supersede an older accepted snapshot without
deleting it until another pass establishes new authority.

Landing requires an accepted snapshot and exactly one local checkout of the named persistence
branch. `integration land --task-id <task> --persist <branch>` creates one canonical squash commit
with `Task:` and `Landed:` trailers, then records the accepted subject in
`refs/orchestrate/<task>/landed`. If persistence moved, create an admitted reconciliation lane and
run `integration reconcile --task-id <task> --lane-id <lane> --persist <branch>`; the writer owns
the resulting no-commit merge, resolution, tests, commit, and normal collection before acceptance
is repeated. Orchestrate never pushes or reads remote refs.

`integration remove --task-id <task> --output-dir <dir>` writes the final report and removes only a
closeable task's exact managed inventory. `--no-report` explicitly omits report output. Destructive
`--abandon` is exceptional current-user authority, not an automatic recovery path. It reports
unlanded and uncollected state while preserving unrelated refs, paths, and user dirt.

## Observation and timing

`status` is the only task discovery and state projection. Without a task ID it lists known tasks;
with `--task-id` it reports the exact base, integration, lanes, acceptance, accepted, landed,
telemetry, and closeability slots that exist. It does not synthesize missing authority.

`report --task-id <task> --output-dir <dir>` atomically writes the two fixed report artifacts from
Git and append-only telemetry. `timing pause --task-id <task>` closes active timing before an
external wait; `timing resume --task-id <task>` resumes it. Repeated matching transitions are
idempotent warnings. Reports and status remain read-only.

## Package administration

`doctor` verifies the executing package's current manifest, documents, profile identity/prompt
projections. v137+ profile entries contain only `agent_name` and
`prompt_sha256`; runtime, model, and configuration metadata are excluded. `doctor --path <repo>`
adds the cwd-derived repository pin projection.
`doctor diff <old> <new>` compares only bundled immutable manifests; `--runtime codex|claude|pi`
filters runtime-specific documents, profiles, and assets. `pin status` and the atomic idempotent
`pin set` derive the repository from cwd. A pin records the last manually adopted release; it never
selects the executable or blocks task work merely because it is absent or different.

`release --version <exact-next>` is the sole package publication command. It requires a healthy
current package and an exact-next migration guide, updates the source identity, writes the target
manifest, verifies the result, and restores prior bytes on failure. Apply manifest-hashed migration
guides in order before a separately authorized setup or pin change.

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
