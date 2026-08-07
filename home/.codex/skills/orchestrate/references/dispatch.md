# Orchestrate — runtime-neutral dispatch contract

## Dispatch payload

Before dispatch Root runs `lane check --task-id <task> --lane-id <lane> --expect-mode <mode>` with
the ticket's admitted mode. The dispatch carries four things, and no obligation cache:

1. **Binding** — the check's exact `sha`, `base`, `protected_paths` and `contract_commits`, plus the
   runtime binding's canonical cwd, Git identity, branch, write scope and primary-checkout dirt.
   Values are copied from their instruments, never rebuilt.
2. **Read** — exact addresses to the ticket admission's `#Contract obligations` and `#Expected Red`.
   `#Admission reasoning` remains Root-only. The admission owns the frozen objective, validation
   mode, applicable Envelope and Standing orders, focused commands, evidence and stop conditions.
3. **Commit** — the verbatim command line below.
4. **Delta** — only facts volatile for this call, including authority issued after admission.

A dispatch that restates the addressed obligations violates this contract: the admission is their
single authority, while Binding, Commit and Delta are the information that cannot be recovered from
those two sections.

## Commit command

Root fills the values in and the dispatch carries the line whole, so the worker never rebuilds it
from the script or from this package:

    lane commit --task-id <task> --lane-id <lane> --message-file <file>

Add `--contract` when the commit freezes the Contract, `--amend-frozen` when it changes a path an
earlier commit froze, and neither flag otherwise; a direct lane never passes `--contract`. The
script reads the `Immutable:` paths off the staged diff, so no path is ever typed — a commit
touching a frozen path without `--amend-frozen` is refused before it exists, where a mistyped path
would instead leave the whole lane uncollectable.

`--contract` is what puts `Origin: contract` and the frozen paths on a commit; an implementation
commit carries neither. That pair is what lets Root read the lane's shape from Git rather than from
the worker's report, so a Contract commit missing its `Origin` trailer reads as implementation.

A dispatch naming the script path instead of the line costs the worker a read of the script and of
this package to rebuild it — measured on a lane that spent it *after* its production edits were
already written.

## Lane identity and mode

Working inside the canonical lane cwd is the only hard contract; the agent, its skills, and its context
mode are recommendations. The worker reports the cwd, Git root/common-dir, branch, HEAD, and clean state
it observes, and Root judges whether they match the admitted lane. The worker runs no mechanical
self-check and does not block itself. Every later operation is path-bound. Root verifies identity and
primary dirt, then holds the mode-appropriate pre-collect evidence [admission](admission.md) S2.5
requires. Root alone invokes `lane sync` or collection.
`lane sync` stages its merge and stops, so the worker resolves whatever it left — a conflict, or a
clean merge that is wrong for reasons only the writer sees — and signs it with `lane commit
--amend-frozen` in its lane; shared integration is never the conflict workspace.

Root invokes `acceptance start [--sha <exact>]` to create one detached snapshot from the managed
integration branch's first-parent history. Canonical tests and ReviewGate run there; Root records an
agent or current-user decision with required `acceptance result --verifier`. Agent pass establishes
landing authority in `accepted`; user pass records independent evidence in `user-accepted`. A
persistence advance routes through an admitted writer lane and `integration reconcile`; after collection
the exact snapshot must receive agent acceptance again before it can become landed. `timing pause` and `timing
resume` bracket external waits without granting lifecycle authority.

The current CLI has no lane group or consumption policy: `lane create` accepts an optional bounded
annotation, `lane comment --text|--clear` overwrites or clears it, and status projects active lanes
as `{sha, comment?, uncollected}` objects with top-level `pending` while omitting the managed
acceptance checkout field. `uncollected` is Git-derived first-parent work outside integration;
pending independently counts collected lanes awaiting agent acceptance. The ninth and later active
lane creates warn factually when projected `uncollected > 0` but remain successful.

The ticket carries the admitted Contract and validation mode. Continuation keeps the same persistent
lane: a semantic Contract change requires fresh admission, while rework does not automatically change
lane or session. Provider and liveness recovery use the worker context classification below. A first
dispatch binds the full **identity binding** above — canonical lane cwd, Git root/common-dir,
branch, HEAD and write scope, the five facts every later path-bound operation is checked against. A
continuation into a session that already attested its cwd, Git root/common-dir and branch rebinds
only the exact HEAD and the scope of this call; those attestations carry, and restating an unchanged
identity binding each time is where a hand-copied one drifts from the lane it describes. The
identity binding stays hard-bound either way, and a mismatch in it fast-fails on the next
path-bound operation.

| worker context | Root action |
| --- | --- |
| context is an asset | Resume the same session. |
| context is debt | Start a fresh run in the same lane. |
| lane is unnecessary | `lane drop`. |

The worker's terminal reports are normal runtime output. A TDD lane reports twice: first at the
frozen Contract before any production line, naming every Contract commit SHA with its exact red
command and observed red reason plus the exact clean SHA and tree it stopped at, and again at
lane-ready with the green result, changed and protected paths, and final exact clean SHA. Root
proves the Contract state and admits implementation between them; a worker does not cross that stop
on its own judgement that the Contract looks complete. A direct lane reports once at lane-ready,
naming the frozen Contract pointer, changed and protected paths, direct validation
commands/results, and final exact clean SHA. Root proves the public process-terminal result and Git
facts at every stop; no external worker artifact is required.

## Authority

Root owns status, collection, acceptance, landing, report, removal, and recovery.
