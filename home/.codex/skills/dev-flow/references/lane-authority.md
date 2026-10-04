# Record permissions

The Orchestrator writes task records and acceptance checkboxes. Delegated roles have one write each,
at the absolute path the dispatch names:

- Implementer: `runs/<short-sha>/summary.md` for its candidate commit.
- Acceptor: `runs/<head-short-sha>/review.md` for the range it reviewed.

Manual or external observations are recorded by their performer; the Orchestrator quotes user reports.

## Gate records

Whoever runs gates on a commit writes `runs/<short-sha>/summary.md`, with raw logs beside it as
`runs/<short-sha>/<gate>.log`. The summary has these fields, one entry per gate: commit, command or
selection, working directory, environment, result, exit status, raw log path, and limitations.
Rerunning gates on the same commit rewrites the summary.

Keep gate records only for a lane tip about to be collected and an integration head about to be
reviewed. Other runs, including ordinary TDD cycles, stay in stdout; do not commit a failing test
just to keep its RED run. The exception is a bug reproduction: commit the reproducing test and keep
its RED run, because it shows the defect existed.

## A gate you cannot close honestly

Preserve the required property. If a check exceeds assigned scope or authority, report the check,
obstruction, and decision needed, whether implementing directly or through a delegate.
