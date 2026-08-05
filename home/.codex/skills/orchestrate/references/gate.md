# Orchestrate — writing a gate script

S2.5 says Root proves each stop by executing it. The gate script is where a repository writes down
*what* that execution is, once, instead of assembling it from memory at each stop. It lives at
`.agent_state/orchestrate/<task-id>/gate.sh`, is repo-local and deliberately not tracked — it is
agent scaffolding, not product — and `lane check` reports its presence as a reminder without ever
requiring it.

This file is guidance. The script's contents belong to the repository; only the exit-code direction
of each stop belongs to S2.5.

## The two stops want opposite answers

The two stops, the exit code each expects, and the state each proves are the S2.5 table in
[admission.md](admission.md#s25--roots-mechanical-guarantee). That table is the only definition;
this file states how to execute it.

A TDD lane has both. A direct lane freezes no Contract commits, so it has only the second. Take the
stop as an argument rather than writing two scripts that drift:

```bash
#!/usr/bin/env bash
set -uo pipefail
stop="${1:?usage: gate.sh contract|lane-ready}"
```

`set -e` is deliberately absent: the Contract stop *wants* a non-zero command, so a shell that exits
on the first failure cannot express it. Check exit codes explicitly instead.

## Stamp the subject before anything else

Every log opens with the SHA and tree it describes, written by the script rather than typed by the
caller:

```bash
head_sha="$(git rev-parse HEAD)"
head_tree="$(git rev-parse 'HEAD^{tree}')"
log="${LOG_DIR:?}/gate-${stop}-${head_sha}.log"
printf 'HEAD=%s\nTREE=%s\nSTOP=%s\n' "$head_sha" "$head_tree" "$stop" | tee "$log"
```

Four defects observed in hand-assembled evidence are all closed by construction here: a log with no
HEAD stamp, a SHA printed outside the pipe so it never reached the file, a status variable that
expanded to the empty string unnoticed, and a log filename typed by hand while the SHA sat in the
line above. A derived filename cannot disagree with its contents.

## The selection may be computed, never chosen

S4 refuses a result that changes when the same tree is exercised through a different selection. That
forbids a scope picked at run time; it does not forbid scope that varies. A selection derived from
the tree — `git diff --name-only "$base"...HEAD` fed into a mapping — yields the same set for the
same tree every time, so the binding holds and the scope still adapts.

Take the base from the argument list rather than inferring it, so the derivation is reproducible:

```bash
base="${2:?usage: gate.sh <stop> <base-sha>}"
changed="$(git diff --name-only "$base"...HEAD)"
```

**Derivation has a known blind spot.** One observed failure was cross-file test-state leakage in
which neither the polluting file nor the polluted file appeared in the diff: a module mutated a
test-global set in setup and only partially restored it, so an unrelated suite failed later. A
selection that follows changed paths alone would have run neither. The lane-ready stop therefore
wants breadth — the full suite, or an affected set closed over its dependents — and it is the stop
where the extra minutes are worth paying.

## Order by cost, stop at the first failure

Static checks answer in seconds and have caught defects that a fully green suite did not: a type
error on an optional dereference, an import-order violation inside a frozen Contract. Run them
first, and let the expensive step run only when they pass.

```bash
run() {  # run <label> <command...>
  printf '\n=== %s ===\n' "$1" | tee -a "$log"
  local label="$1"; shift
  "$@" >>"$log" 2>&1
  local code=$?
  printf '%s exit=%d\n' "$label" "$code" | tee -a "$log"
  return $code
}
```

A rough shape for the lane-ready stop:

1. formatter and lint over changed paths
2. type check over changed paths
3. the declared test selection

The Contract stop runs only the focused command the Contract names, and asserts it failed:

```bash
if [ "$stop" = contract ]; then
  run focused "${FOCUSED_CMD[@]}"; code=$?
  [ "$code" -ne 0 ] || { echo 'gate: contract stop is green'; exit 1; }
  exit 0
fi
```

A red result is not automatically the right red. The script cannot judge that — S2.2 asks for the
observed reason, and a collection, import, type or environment failure is red for the wrong reason.
Print enough of the failure for a reader to tell the difference, and leave the judgement to Root.

## Keep the run isolated and disposable

Give the test runner a base temporary directory inside the task's own workspace so a killed run
leaves nothing behind and parallel lanes never share a path:

```bash
--basetemp="${LOG_DIR}/pytest-tmp"
```

Never write into a shared, named `/tmp` path: it is memory on most systems, it survives until
reboot, and two lanes racing on the same name corrupt each other's evidence.

## What the script does not do

It does not decide whether a Contract is admissible, does not judge whether red is red for the right
reason, does not record anything in Git, and does not gate collection. It runs a fixed set of
checks against one tree and reports what happened. Everything downstream of that is Root's.
