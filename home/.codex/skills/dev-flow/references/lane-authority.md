# Record permissions

The Orchestrator writes INDEX, tickets, dispatches, and acceptance checkboxes. Two role writes
exist, each to one file named in the dispatch:

- The **implementer** writes the gate summary for its final commit at
  `runs/<short-sha>/summary.md` in the task container, beside the raw logs: for each gate, the
  command or selection, working directory, environment, result and exit status, and limitations. The
  dispatch names the absolute `runs/` path; the implementer adds the commit's short SHA.
- The **acceptor** writes `review-NN.verdict.md` at the absolute path its dispatch names.

The Orchestrator's own gate runs go to `orchestrator.md` in the same `runs/<short-sha>/` directory.
A manual or external observation is recorded the same way, by whoever performed it; for the user's
own, the Orchestrator quotes their report. Run a baseline in the lane, on its starting commit.
Only runs on a clean commit are recorded; a run on uncommitted work stays in stdout or a temporary
file, so to keep a red run, commit the failing test first.

## A gate you cannot close honestly

Keep each check's required property intact. When satisfying it exceeds the assigned scope or authority,
report the check, obstruction, and decision needed. This applies to a delegated writer and to the
Orchestrator implementing directly.
