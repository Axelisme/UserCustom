# UserCustom

Dotfiles plus the agent skills, profiles, and Pi extensions that `setup_scripts/setup_config.sh`
links into `$HOME`; `home/` mirrors `$HOME`.

## Gate

`just test` is the gate: pytest with xdist over `tests/`, then `node --test` over
`tests/*.test.mjs`. Select one test with `uv run pytest tests/<file>.py::<Class>::<test>`.

## Tests

Three kinds, told apart by location:

- `tests/test_*.py`: **behaviour tests** for Python scripts. A test loads the script with
  `_support.load_script` and calls its `main` through `_support.run_main`, passing `argv` and any
  `cwd` or `home` the script would otherwise read from the process; one test per script runs it as
  a process to cover its exit status. A script whose `main` takes no `argv` gains one before its
  tests change. Shell scripts run as processes.
- `tests/*.test.mjs`: node:test files for TypeScript modules under `home/.pi/agent/`, run
  in-process with injected dependencies such as collab-op's `GitRunner`. New collab-op tests go
  here; `tests/test_collab_*.py` drive collab-op through a node harness process and move here when
  their module changes.
- `tests/checks/check_*.py`: **repository checks**. Each asserts a structural property of tracked
  data: a pointer resolves, a paired Claude and Codex profile agree.

Every test follows these rules:

- **Hermetic.** A test touches only its own temporary directories and the program under test. A
  module that runs git or Pi sets `setUpModule = support.require_git` or `support.require_pi`; the
  guard replaces HOME, git configuration, identity, clock, and Pi network access. Check: every
  module that starts git or node assigns `setUpModule`.
- **Own fixtures.** A behaviour test builds its inputs inside a temporary directory. Check: the only
  `home/` path a test file names is the program it tests.
- **Structure, not wording.** A repository check passes or fails on references and pairings; any
  rewording of a document leaves it green.

A ticket that adds or changes behaviour delivers its red-green proof as the task-flow skill's Gates
section defines it.
