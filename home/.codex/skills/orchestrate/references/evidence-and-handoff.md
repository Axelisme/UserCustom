---
orchestrate_compat: 69
---

# Evidence and handoff

Read this reference when a gate aborts/times out/crashes, a task needs durable narrative, or
the root session must hand off.

## Gate evidence scope

Every gate record states what it proves:

```text
gate_scope: affected | wave | task
target_sha: <exact commit>
target_tree: <exact tree>
covered_surface: <paths/behaviors/gate rationale>
baseline_sha: <exact immutable baseline | none>
outcome: pass | baseline-relative | unusable
invalidated_by: <later commit/change | none>
replacement_evidence: <evidence id/command | none>
```

`affected` covers a changed surface, a **wave gate is provisional** while later waves remain,
and only a usable `task` gate on the landing candidate is final. A wave boundary needs a
broader gate only when the repo/risk contract names one; it never masquerades as the final
task-scoped gate.

Evidence invalidation is **surface-scoped**: a later change invalidates only evidence whose
`covered_surface` intersects the changed paths/behaviors. Shared fixtures, config, and build
inputs count as intersecting everything they feed. Disjoint evidence stays valid — record the
non-intersection claim in `invalidated_by: none` reasoning rather than asserting it silently.
Two gates stay whole-tree regardless: any gate the repo/risk contract names as whole-tree, and
the final `task` gate, which always runs on the exact landing-candidate tree.

## Baseline-relative gates

A deterministic broad-gate failure may be `baseline-relative`, never `pass`, only when:

1. root runs the **same command on an immutable baseline SHA**;
2. the target has **no new errors or changed error families** relative to that baseline;
3. **every changed file** is covered by a **successful affected gate**;
4. all **extra warnings/errors** are explicitly classified; and
5. the failed broad command is **never called PASS**.

Record exact baseline/target counts and families plus replacement evidence. A target
regression stays blocking. If the comparison is not like-for-like, the gate is `unusable`.

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

- Decisions take effect in the in-band control plane. When cross-session durability is
  needed, persist the conclusion or ADR pointer in task_plan; the plan records the decision
  but never dispatches work or triggers a state transition.
- After semantic plan updates at checkpoint, handoff, resume, or closure boundaries, run the
  `planning-with-files` command `checkpoint <task-id>`. It validates current schemas and
  compacts only when required; `status remains read-only`, and maintenance never changes
  decision, review, or merge state.
- Cross-session, multi-round, or information-heavy tasks use `planning-with-files` at
  `.agent_state/plans/<task-id>/`; one-shot tasks create nothing.
- **task_plan is the ledger; a domain packet is its current-state cache.** The ledger holds
  active decisions and one-line pointers only; a closed decision's detail lives in its ADR or
  evidence artifact, collapsed at wave close. Only several
  concurrent domains justify `domains/<domain>.md` (owner/reviewer, current SHA, pointers and
  one-line summaries of frozen decisions, next step). Single-domain tasks use task_plan's
  Current State directly.
- **Active state and history are separate files.** Current State carries only live authority:
  current exact SHA, owner, gate state, next transition, open findings. Sealed review rounds,
  closed leases, and superseded decisions move at any checkpoint to
  `.agent_state/plans/<task-id>/history.md` or their evidence artifacts, leaving a one-line
  pointer. Move sealed detail out whenever the byte budget nears — never rewrite or truncate
  active authority narrative to fit, and never wait for a phase-count boundary to compact.
- A **domain packet** never copies decision text. Rewrite it at lease handoffs/checkpoints and
  delete it when the domain completes; task_plan retains the durable phase history. An
  immutable dispatch packet is separate frozen input and is authorized only by a direct
  message naming its path/hash.
- Reports return in-band. Messages carry milestones, findings, and decisions. Outside the
  closed spool/dispatch-packet transports, files carry evidence only: disposable bulk payloads under
  `.agent_state/artifacts/<task>/<agent>-<topic>.md`, durable investigator maps in the plan
  directory. Reports include a digest and path; root reads selectively.
- Spool/dispatch files may carry frozen work but never outcomes. No file replaces a milestone,
  infers completion, or acts as a controller. There are no mandatory per-agent report files.

## Session handoff

When root decides to hand off, stop dispatching. Use remaining context to drain:

1. Stop at a slice boundary when possible; otherwise commit the nearest coherent state.
2. Never hand off while holding the merge slot, mid-collection, or with reviewer findings
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
