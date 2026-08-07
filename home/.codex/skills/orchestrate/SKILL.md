---
name: orchestrate
description: Git lanes for dispatched task work. Use when dispatching implementation to worker agents, integrating or landing completed lanes, checking task or lane state, or when a runtime binding needs the lane dispatch contract. Not for work one agent completes in a single context.
skill_version: 173
---

# Orchestrate

Orchestrate is the **Git task lane**. It owns managed lane and integration worktrees, Git-backed task
state, acceptance snapshots, local persistence landing, reports, and runtime bindings. Its durable
inputs are commits, refs, SHAs, trailers, and worktree state. It may consume dev-flow IDs but stores
no task narrative. [Admission](references/admission.md) is the normative S1–S5 authority; dev-flow
owns the preceding S0, which Root reads before creating the first lane.

## Orienting

Run `status --task-id <task>` for the exact integration SHA and pending, accepted, landed, and lane
state; when it emits `step`, open only the addresses in `step.open`. A clean response without `step`
is self-placing; use `status --task-id <task> --step` only when it is not. Run `lane check --task-id
<task> --lane-id <lane>` for one lane's exact state.

`show` is the text-stream exception: success writes only the verified section to stdout. Every
other command emits one JSON object with `orchestrate_version`: exit 0 is success, exit 1 is a
completed negative predicate on stdout, and exit 2 is an operational/usage error on stderr.
Mutations preflight package health before repository changes; read-only diagnosis remains available.
A command-bound refusal carries non-empty `repair` beside `code` and `message`; diagnostics use the
same shape, and each repair states only corrective action the command's own behavior binds.

## Minimum complete lifecycle

### Step 1 — Create integration

`integration create --task-id <task>` creates the append-only integration branch and worktree at the
current repository subject. Done when both exist.

### Step 2 — Create lane

`lane create --task-id <task> --lane-id <lane> [--comment <text>]` creates a persistent writer
branch/worktree at the recorded base. The ticket owns the admitted Contract and validation mode;
the lane may span worker calls and collect/rework cycles. `lane comment ... --text <text>` replaces
the bounded annotation and `--clear` removes it. Root dispatches the exact canonical cwd and Git
identity while preserving primary-checkout dirt. Done when branch and worktree exist at the base.
The Slice must satisfy [S1.1–S1.3](references/admission.md) together as one admission decision.

### Step 3 — Execute Contract

Execute the admitted Contract in S2's recorded `TDD` or `direct` mode. The Contract answers
S2.1–S2.3 and S2.6–S2.7; the [gate script](references/gate.md) proves S2.5 at each stop, and a
Contract over roughly 1000 test lines also owes S2.8. Author every lane commit with `lane commit
--task-id <task> --lane-id <lane> --message-file <file> [--contract | --amend-frozen]`; it computes
`Immutable:` declarations from the staged diff, including protected paths. Done when Root holds the
mode-specific evidence and exact clean tip SHA.

### Step 4 — Sync lane

When integration advanced, `lane sync --task-id <task> --lane-id <lane>` stages a writer-owned,
no-commit merge and stops. A successful envelope may warn about conflicts because even a clean Git
merge needs writer verification. The writer resolves, verifies, and commits with
`lane commit --amend-frozen`. Done after that commit, or immediately when no sync was needed.

### Step 5 — Collect lane

`integration collect --task-id <task> --lane-id <lane> --ticket <ticket>` preflights cleanliness,
first-parent topology, and declarations, refusing before repository changes when any predicate fails.
It then creates a fixed-parent no-ff commit with `Task:`, `Lane:`, and bounded `Ticket:` trailers and
retains the lane worktree, branch, and base ref; `lane drop` is explicit discard. Done when the
collect commit exists and the lane remains available. Before collect Root holds S2.5 lane-ready
proof and, for TDD, S2.4's exact bound SHA.

### Step 6 — Start acceptance

`acceptance start --task-id <task> [--sha <exact>]` creates a managed detached snapshot. Omission
selects the integration tip; a full SHA may select any commit on its first-parent history. Done when
the acceptance worktree holds that exact commit, independent of integration worktree state.

### Step 7 — Validate and accept

On that snapshot, run canonical tests then the read-only Standards/Spec ReviewGate. Record the exact
result with `acceptance result --task-id <task> --verifier agent|user --outcome pass|fail`. Agent
pass moves `refs/orchestrate/<task>/accepted`; user pass moves
`refs/orchestrate/<task>/user-accepted`; either may move backward explicitly, and failure revokes
only the same verifier's equal ref. User evidence does not affect landing or closeability. Done when
result, refs, and telemetry agree. S4 defines gate order, binding, and reviewer rules.

### Step 8 — Land

With an accepted snapshot and exactly one local checkout of the persistence branch, `integration
land --task-id <task> --persist <branch>` creates the canonical squash commit with `Task:` and
`Landed:` trailers and records the accepted subject at `refs/orchestrate/<task>/landed`. Orchestrate
neither pushes nor reads remote refs. Done when that ref points to the accepted subject. S5 governs
user authority and topology.

### Step 9 — Remove task

`integration remove --task-id <task> --output-dir <dir>` writes the final report, including agent and
user evidence, then removes only a closeable task's exact managed inventory; `--no-report`
explicitly omits output. Done when the report is written unless omitted and the inventory is gone.
S4 governs close-out; S5 adds final-landing requirements.

### Exceptions to the main sequence

Use `lane drop` for a clean unwanted lane.

If persistence advances before landing, create an admitted reconciliation lane and run `integration
reconcile --task-id <task> --lane-id <lane> --persist <branch>`. The writer owns the staged merge,
resolution, tests, and commit; then repeat collection and acceptance.

Acceptance failure grants no repair authority. After Root admits a bounded correction, resume the
same useful worker context for an implementation bug, preserving test correction, or additive-only
observable correction. Context debt or a wrong observable starts a fresh run in the same lane. An
additive-only observable opens a ticket and repeats S1; an unnecessary lane is dropped. The runtime
binding governs writer and reviewer context continuation.

Destructive `integration remove --abandon` requires exceptional current-user authority. It reports
unlanded/uncollected state while preserving unrelated refs, paths, and user dirt.

[Admission S2.4](references/admission.md) selects preserving versus semantic correction; S3 owns the
monotonic rework count.

## Observation and timing

`orchestrate.py --version` is the top-level version query; there is no `version` subcommand. `status`
is the only task discovery/projection: without an ID it lists tasks; with one it reports integration
SHA, active `{sha, comment?, uncollected}` lanes, top-level `pending`, accepted, `user_accepted`,
landed, and inventory warnings. `uncollected` is lane first-parent work outside integration;
`pending` counts collected lanes awaiting agent acceptance. It does not synthesize historical
lane/comments or the managed acceptance worktree.

Lane comments are mutable bounded annotations with no lifecycle, acceptance, landing, or cleanup
authority, and project only while active. The ninth and later active-lane creates warn factually
when projected `uncollected > 0` but never block creation. Agent acceptance records authority before
automatically
closing clean named lanes; anomalies retain the lane and warn Root.

`lane check` applies collection predicates without mutation and reports lane `sha`, `base`,
`protected_paths`, `contract_commits`, and uncollected `ticket_contract_commits` with their
`ticket_contract_added_lines`. Persistent lanes make the two Contract projections distinct; S2.8
measures the latter. `--expect-mode tdd|direct` refuses a frozen-Contract mismatch. A per-task gate
script adds a factual warning naming it. The check is most useful before dispatch, where it binds the
carried identity, but is optional before collection, which applies identical predicates.

`report --task-id <task> --output-dir <dir>` atomically writes two fixed artifacts from Git and
append-only telemetry. `timing pause` closes active timing before an external wait; `timing resume`
restarts it. Repeated matching transitions are idempotent warnings. Reports and status are read-only.

## Package administration

[Package administration](references/package-admin.md) covers doctor, doctor diff, pin, and release;
read it before a release or pin change.

## Runtime and authority boundaries

Before dispatch, read the matching [Codex](runtime-codex.md), [Claude](runtime-claude.md), or
[Pi](runtime-pi.md) binding. Bindings transport frozen dispatch and exact-run evidence; they grant
no admission, collection, acceptance, persistence, setup, pin, or cleanup authority. Beyond shared
[dispatch](references/dispatch.md) authority, Root owns Contract semantics, S2.5's guarantee, and
primary dirt. Semantic Contract changes require fresh admission; rework does not automatically
change lane or session. Dispatch governs provider/liveness recovery through context asset/debt.
