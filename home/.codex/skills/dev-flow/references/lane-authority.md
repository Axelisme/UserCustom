# Record permissions

The Orchestrator writes task records and acceptance checkboxes. Delegated roles have one evidence
write each, at the location named in dispatch:

- Implementer: `runs/<short-sha>/summary.md`, under the absolute runs path supplied by dispatch.
- Acceptor: the exact absolute `review-NN.verdict.md` path.

Gate evidence names the commit, each command/selection, working directory, environment, result,
exit status, and limitations, beside raw logs. The Orchestrator uses `orchestrator.md` in the same
commit directory. Manual/external observations are recorded by their performer; the Orchestrator
quotes user reports. Baseline observations run in the lane at its starting commit.

Only clean-commit runs become durable evidence. Uncommitted observations stay in stdout or temporary
files; commit a failing test before retaining its RED run. A summary remains usable when its commit,
environment, selection, method, result, and limitations apply; a role change alone needs no rerun.

## A gate you cannot close honestly

Preserve the required property. If a check exceeds assigned scope or authority, report the check,
obstruction, and decision needed, whether implementing directly or through a delegate.
