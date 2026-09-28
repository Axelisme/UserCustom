# Record permissions

The Orchestrator writes INDEX, tickets, review briefs, and acceptance checkboxes. Two role writes
exist, each to one file named in the dispatch:

- The **implementer** writes the gate summary for its final commit at
  `<lane>/.agent_state/runs/<short-sha>/summary.md`, beside the raw logs: for each gate, the command
  or selection, working directory, environment, result and exit status, and limitations. The
  dispatch names the `runs/` directory; the implementer adds the commit's short SHA.
- The **acceptor** writes `review-NN.verdict.md` at the absolute path its review brief names.

The Orchestrator's own gate runs go to `orchestrator.md` in the same `runs/<short-sha>/` directory of
the checkout where they ran. A manual or external observation is recorded the same way, by whoever
performed it.

## A gate you cannot close honestly

Keep each check's required property intact. When satisfying it exceeds the assigned scope or authority,
report the check, obstruction, and decision needed. This applies to a delegated writer and to the
Orchestrator implementing directly.
