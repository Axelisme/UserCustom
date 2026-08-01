# Orchestrate — Codex runtime binding

See [dispatch.md](dispatch.md) for the runtime-neutral dispatch contract, evidence, acceptance, and
authority rules shared by every runtime. This file states only Codex's own delta.

Codex dispatches one native `lane-worker` call for the lane identity `<task-id>.<lane-id>`.

Continuation is a native follow-up call on the same worker; `dispatch.md` states when it is
admissible.
