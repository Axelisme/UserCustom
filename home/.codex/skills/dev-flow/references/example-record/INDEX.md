# example-record

| Record field | Value |
|---|---|
| record_version | 2 |
| task_id | example-record |

## Goal
Converge configuration loading onto a single source: the legacy secondary loader is deleted and
every reader goes through one owner.

## Current

- **Current stage:** Contract-first implementation, dispatched but not yet lane-ready.
- **Integration:** ticket `config-single-source` is in progress; `config-single-source-validation`
  is blocked on it and further blocked on the user being present to exercise the result.
- **Completed:** none yet; this record shows a task mid-flight, not a finished one.
- **Blocking:** none recorded; see `tickets/config-single-source.md` for the active Contract Red
  scope and the named deletion it must land.

## Next

1. Land `config-single-source`'s Contract Red, then its production change, within the stated line
   ceiling.
2. Once lane-ready, hand off to `config-single-source-validation` for the user's exercise.

<!-- task-record:files:start -->
INDEX.md
README.md
artifacts/
  config-single-source-source-map.md
decisions.md
tickets/
  config-single-source-validation.md
  config-single-source.md
<!-- task-record:files:end -->
