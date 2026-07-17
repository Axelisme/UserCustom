# Evidence and handoff

Read this reference when a gate aborts/times out/crashes, a task needs durable narrative, or
the root session must hand off.

## Gate evidence scope

Gate evidence has one carrier: the hand-written **gate receipt**
(`orchestrate receipt lint`) — exact subject SHA, the exact command, one status
(`passed | failed_current | failed_baseline | environment_blocked | unverified`), and an
explicit `exclusions` list; scope (`affected|wave|task`), covered surface, baseline SHA, and
invalidation notes go in `details` when they matter. Every deselected, skipped, or excluded
test carries its exact test node id, reason, baseline comparison evidence, whether it
affects acceptance, and a follow-up pointer; a receipt with an acceptance-affecting
exclusion can never report `passed`. An unclassified deselection is an anomaly, not a pass —
"169 passed, 1 deselected" is green only when that one is classified.

`affected` covers a changed surface, a **wave gate is provisional** while later waves remain,
and only a usable `task` gate on the landing candidate is final. A wave boundary needs a
broader gate only when the repo/risk contract names one; it never masquerades as the final
task-scoped gate.

Evidence invalidation is **surface-scoped**: a later change invalidates only evidence whose
covered surface intersects the changed paths/behaviors. Shared fixtures, config, and build
inputs count as intersecting everything they feed. Disjoint evidence stays valid — record the
non-intersection claim in the receipt's details rather than asserting it silently.
Two gates stay whole-tree regardless: any gate the repo/risk contract names as whole-tree, and
the final `task` gate, which always runs on the exact landing-candidate tree.

## Baseline-relative gates

A deterministic broad-gate failure may close as `failed_baseline`, never `passed`, only when:

1. root runs the **same command on an immutable baseline SHA**;
2. the target has **no new errors or changed error families** relative to that baseline;
3. **every changed file** is covered by a **successful affected gate**;
4. all **extra warnings/errors** are explicitly classified; and
5. the failed broad command is **never called PASS**.

Record exact baseline/target counts and families plus replacement evidence. A target
regression stays blocking. If the comparison is not like-for-like, the gate is `unverified`.

The per-test comparison is mechanized: summarize each side as a hand-written **gate run
summary** JSON (`{run_version: 1, subject_sha, command, results: {<test_id>:
passed|failed|error|skipped|blocked}}`), then `orchestrate gate compare --baseline <a>
--current <b> --item-id <id> [--output <receipt>]` classifies every test baseline-relatively
— a regression yields `failed_current`; baseline-equal failures, blocked, skipped, and
silently deselected tests become prefilled exclusions citing the baseline SHA — and emits a
lint-valid gate receipt draft. Drafted exclusions default to `affects_acceptance: true`;
deciding an exclusion does *not* affect acceptance stays root's judgment, recorded by editing
the draft. Different commands on the two sides Fast Fail as not like-for-like.

## Validation anomalies

An abort, signal, timeout, interpreter crash, Qt teardown/GC failure, or subprocess failure
is not an assertion failure and is not a pass. Preserve the first failure's exact command,
target SHA, exit status/signal, phase, and useful artifact. Re-run the same broad command at
most once and only for a stated diagnostic purpose; never retry until green.

Build the smallest evidence ladder that still covers the original acceptance surface:

1. deterministic non-GUI/non-subprocess tests;
2. focused GUI or subprocess tests;
3. minimal lifecycle/teardown reproducer;
4. isolated-process execution when shared interpreter state may be the harness fault.

A deterministic assertion or reproducible product behavior is an ordinary blocking failure.
If only a combined harness fails while split gates reliably cover the same surface, record the
combined command as **unusable evidence**, report the replacement evidence, and never claim
the original suite passed. If product risk and harness fault cannot be separated, keep risk
open and block collection/landing. Carry anomaly classification and the coverage gap into the
review-readiness packet.

## Durable narrative

- **One fact, one carrier.** Git carries code and exact SHAs; receipts carry
  machine-checkable authorization and gate evidence; task_plan carries active decisions,
  open findings, and the next gate. A progress log is opt-in, only for a genuine
  cross-session audit. `orchestrate slice status` rebuilds current lane state from Git plus
  receipts; never hand-copy that state into narrative.
- A task firing the task_plan trigger uses `planning-with-files` at
  `.agent_state/plans/<task-id>/`; one-shot tasks create nothing. Decisions take effect
  in-band — the plan records conclusions and ADR pointers but never dispatches work or
  triggers a state transition. After semantic plan updates at checkpoint/handoff/resume/
  closure boundaries, run `checkpoint <task-id>`; maintenance never changes decision,
  review, or merge state.
- **task_plan is the ledger**: active decisions and one-line pointers only. Sealed detail —
  closed review rounds, closed leases, superseded decisions — moves to `history.md` or its
  evidence artifact at any checkpoint, leaving a one-line pointer; never rewrite active
  authority narrative to fit a byte budget. Only several concurrent domains justify
  `domains/<domain>.md` caches (owner, current SHA, pointers, next step); a cache never
  copies decision text and is deleted when the domain completes.
- Reports return in-band; outside the closed spool/dispatch-packet transports, files carry
  evidence only — disposable bulk under `.agent_state/artifacts/<task>/<agent>-<topic>.md`,
  durable investigator maps in the plan directory — with a digest and path in the message.
  No file replaces a milestone, infers completion, or acts as a controller; there are no
  mandatory per-agent report files.

## Session handoff

When root decides to hand off, stop dispatching. Use remaining context to drain:

1. Stop at a slice boundary when possible; otherwise commit the nearest coherent state.
2. Never hand off mid-landing, mid-collection, or with reviewer findings
   trapped in agent context. Release/yield first.
3. Writers commit and report. Reviewers flush every finding with severity and evidence.
   Agent leases do not survive the session; the packet must support a new identity without
   losing findings.
4. Update only domain packet/task_plan Current State with branch topology, live worktrees,
   review debt (announced unsigned SHAs), run-ahead position, finding ledger, and unusable
   evidence anomalies. Do not create a separate orchestrate handoff document; when a generic
   handoff skill demands its own file, that file holds only a pointer to task_plan Current
   State — task_plan stays the single handoff authority and content is never duplicated.
5. Inspect every task spool generation and record only its lease/path/current item pointers in
   Current State. The spool does not auto-resume: the next root reconciles each item against
   Git, milestones, open findings, current authority, and lease generation before any wake.
6. Remove reviewer temp worktrees; keep needed lane worktrees and list them.
7. The next session first reconciles narrative and spool against `git worktree list`,
   branches, status, and exact SHAs before dispatching.
