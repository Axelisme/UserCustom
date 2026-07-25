# Maintaining orchestrate v123

Orchestrate is a narrow Git-backed protocol, not a second workflow engine. The durable
state is the repository: commits, SHAs, trailers, branches, and live worktree status.
Task plans carry intent and decisions only.

## Public waist

The workflow has three operations: create/status/remove per-role worktrees, merge one exact
Oracle Contract into the Implementation branch, and report Git-derived profile statistics.
Release, doctor, manifest diff, and version-pin administration remain available. There is
no registry or runtime-state file. Runtime bindings own attach, restore, continuation, and
close semantics.

## Role ownership

Oracle freezes a deep public Interface and writes contract tests, fixtures, and adapters
before internal behavior. Implementation consumes the exact merged Contract and may edit
shared production paths, but never acceptance surfaces. Both roles finish with a clean
`slice-ready` commit handoff containing Slice and SHA.

## Shipping

Use the release command to bump the version, build a manifest, and run doctor atomically.
Keep Codex, Claude, and Pi profile contracts aligned where their runtime syntax permits.
The installed package must match the source package and all retained documents must fit the
single-read budget. Landing and repository persistence remain explicit user-authorized
repo actions, not orchestrate commands.
