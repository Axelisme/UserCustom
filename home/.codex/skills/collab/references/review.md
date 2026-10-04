# Review and correction

## Range review

Review covers ranges of integration commits, not tickets. Every product-code and test change must be
read in some range review before landing. Gates and the Orchestrator check documents, prose, and
configuration directly. Fewer reviews cost less time and tokens; the price is finding defects later.

The Git ref `refs/collab/<task>/reviewed` marks the last integration commit a review has read. Before
the first review it does not exist, and the range starts at the commit integration was created from.
Commits brought in from persistence by reconciliation were reviewed there; judge only their merge
resolution.

Review a range at two points only:

- Before landing, review `reviewed..HEAD` of integration.
- Before a ticket starts using a public interface that sits in the unreviewed range, review a range
  that covers that interface. Downstream work then never builds on an interface a review may reject.

When one range is too large for a reviewer to read well, split it into consecutive commit sub-ranges,
one acceptor each. Size decides only the split, never the timing.

Run applicable gates on the head and send the filled `../../dev-flow/templates/ticket/review.md` as
the dispatch. Integration may keep moving while the acceptor reads; the review covers only the named
head. The acceptor judges the named criteria and the logic of the diff from contract, declarations,
callers, tests, and gate results. It runs no tests, imports, linters, formatters, builds, or runtime
gates, and writes only the verdict. A missing input that prevents judgement is a BLOCKED finding.

After a verdict, COMPLETED or BLOCKED, move the ref to the reviewed head with
`git update-ref refs/collab/<task>/reviewed <head>`. For a split, move it only after every sub-range
has a verdict, in order. The ref records what was read; open findings are tracked separately below.

## Correct and decide

Read the verdict and choose fix, decline with reason, or refer to a user decision for every finding.
Refer only a finding whose fix would contradict a user decision; settle the rest under dev-flow's
[Document authority](../../dev-flow/references/records.md#document-authority). Keep open findings in
tracker Plan with the verdict path.

Fix through a ticket on a lane like any other change: gates, collection, close. The next range review
covers the fix commits and names the findings they address in Prior findings. Landing needs the ref at
integration HEAD and the latest verdict COMPLETED with every prior finding resolved or declined.
