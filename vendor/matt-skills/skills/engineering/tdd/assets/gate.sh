#!/usr/bin/env bash
# INCOMPLETE TEMPLATE: copy this file, then freely rewrite it for the repository.
# The format is not an Interface. Keep only the useful diagnostic outcomes:
# - one Candidate cwd;
# - mechanical red/green direction, without semantic judgement;
# - actual commands, exits, per-command and per-stop seconds, and Git identity in
#   one unique log;
# - one invocation tmp directory, removed on success and retained on failure.
#
# Fill the paths and cases, then remove the two-line guard below.
echo "gate.sh is an incomplete template; adapt it before use" >&2
exit 2

candidate_cwd=${CANDIDATE_CWD:-/replace/with/candidate/checkout}
evidence_dir=${EVIDENCE_DIR:-/replace/with/durable/evidence}
baseline_note=${BASELINE_NOTE:-unavailable}
stop_started=$SECONDS # the cost bound in gate.md is a per-stop number, not a per-command one

# Example helper: include staged, unstaged, and non-ignored untracked files without
# changing the real index. The operation writes ordinary Git objects.
snapshot_tree() (
  index=$(mktemp)
  trap 'rm -f "$index"' EXIT
  rm -f "$index"
  export GIT_INDEX_FILE=$index
  git -C "$candidate_cwd" read-tree HEAD &&
    git -C "$candidate_cwd" add -A -- . &&
    git -C "$candidate_cwd" write-tree
)

# Use this wrapper, or a repository-native equivalent, to put exact commands,
# exits, and elapsed seconds in the invocation log.
gate_run() {
  local started status
  printf 'COMMAND='
  printf ' %q' "$@"
  printf '\n'
  started=$SECONDS
  "$@"
  status=$?
  printf 'COMMAND_EXIT=%s\n' "$status"
  printf 'COMMAND_SECONDS=%s\n' "$((SECONDS - started))"
  return "$status"
}

# Suggested outline only:
# 1. Fix candidate_cwd, create one unique log and run tmp, then cd to candidate_cwd.
# 2. Record timestamp, baseline_note, full HEAD, HEAD tree, and snapshot_tree.
# 3. Translate the requested direction to exit 0, its opposite to 1, and setup failure to 2.
# 4. Recompute snapshot_tree; a changed tree is setup failure. Clean or retain run tmp.
# 5. Print STOP_SECONDS=$((SECONDS - stop_started)) before exiting, on every path
#    that ran a command.
case "${1:-}" in
  baseline)
    : # TODO: existing static and affected commands expect zero.
    ;;
  red)
    : # TODO: the focused command expects non-zero; inspect why outside this script.
    ;;
  green)
    : # TODO: static, focused, then affected commands all expect zero.
    ;;
  *)
    printf 'usage: %s baseline|red|green\n' "$0" >&2
    exit 2
    ;;
esac
