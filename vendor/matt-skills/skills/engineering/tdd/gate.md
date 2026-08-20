# Gate mode

Gate mode is an optional task-local validation driver for a red/green loop whose repeated commands,
working directory, temporary files, or evidence are otherwise easy to vary between stops. It makes
execution reproducible; it does not decide whether a red is the right red or whether green satisfies
the behavior.

When Gate mode earns its cost, copy [`assets/gate.sh`](assets/gate.sh) as a starting point or write
the repository-native equivalent. The template is disposable: its functions, arguments, output, and
language are not an Interface.

## Set up once

1. Put the task-local driver and evidence outside the subject checkout, or in a path confirmed to
   be ignored. Give each invocation one temporary directory inside an ignored temp area.
2. Fix one subject working directory and write the applicable repository commands into the
   driver. Prefer the repository's existing commands over new wrappers.
3. Before changing production behavior, run the existing static and affected checks once when
   practical. Save that baseline with the exact base SHA, its `STOP_SECONDS`, and the commands they
   covered. When no unchanged base is available, record `BASELINE=unavailable` and a short reason
   instead of inventing one or creating a checkout.
4. Verify that the driver, logs, and invocation temp do not enter the subject's Git tree.

Setup is complete when one edited driver names its subject directory and commands, its evidence
has a durable location, and the baseline state is explicit.

## Stops

| Invocation | Mechanical observation | Suggested order |
|---|---|---|
| `baseline` | Existing checks return zero | static → affected |
| `red` | The focused command returns non-zero | focused |
| `green` | Every applicable command returns zero | static → focused → affected |

A red Gate proves only exit direction. Read the focused failure and apply the main skill's
**Right red** rule before implementation. A focused green alone is not the green stop when affected
or static checks apply.

Suggested driver exits are `0` for the requested direction, `1` for the opposite direction, and `2`
for usage, setup, or operational failure. These numbers make shell use convenient; the evidence
below carries the meaning.

## Evidence and temporary state

Write one unique log per invocation. The filename need only be unique; put identity in the content:

- mode, timestamp, subject working directory;
- full `HEAD`, `HEAD` tree, and working-tree tree;
- each actual command, exit code, and elapsed seconds;
- `STOP_SECONDS`, the whole stop's elapsed seconds;
- baseline log or unavailable reason;
- retained temporary-directory path, when any.

Compute the working-tree tree with a temporary Git index so staged, unstaged, and non-ignored
untracked files are included without changing the real index. Compute it before and after the
commands. A mismatch means the commands did not examine one state: report an operational failure
and both tree IDs, then rerun against the new state.

Remove invocation temp after the requested direction is observed. Retain it on opposite-direction or
operational failure and print its path in the log. Logs remain outside the subject so recording
evidence cannot change the subject being measured.

The stop is complete when the Orchestrator can identify one subject state, the commands and exits that
ran against it, the observed mechanical direction, `STOP_SECONDS`, and any retained diagnostic
state. At a green stop, that also covers how `STOP_SECONDS` stands against the bound below. Semantic
judgement remains with the TDD loop.

## Cost bound

A green stop runs every applicable command, so its `STOP_SECONDS` is the task's standing cost:
every remaining ticket pays it again. Keep a green stop under **two minutes**, unless the repository
documents a different bound.

The bound is absolute, so it still holds under `BASELINE=unavailable`: a suite that arrives already
slow trips it at the first green stop. A baseline, where one exists, adds the comparison. It records
the commands it ran, so a green stop that judged fewer of them applicable reads as a narrower stop
rather than as a cheaper suite.

Past the bound, report `STOP_SECONDS` and let the Orchestrator open a separate ticket for optimising the
suite. The bound is what puts that decision in front of the Orchestrator: each stop pays a little more, no
single stop looks unreasonable, and the suite arrives at ten minutes with nobody having decided that
it should.
