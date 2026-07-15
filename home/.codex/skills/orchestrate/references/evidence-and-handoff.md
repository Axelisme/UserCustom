---
orchestrate_compat: 58
---

# Evidence and handoff

Read this reference when a gate aborts/times out/crashes, a task needs durable narrative, or
the root session must hand off.

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
- **task_plan is the ledger; a domain packet is its current-state cache.** Only several
  concurrent domains justify `domains/<domain>.md` (owner/reviewer, current SHA, pointers and
  one-line summaries of frozen decisions, next step). Single-domain tasks use task_plan's
  Current State directly.
- A packet never copies decision text. Rewrite it at lease handoffs/checkpoints and delete it
  when the domain completes; task_plan retains the durable phase history.
- Reports return in-band. Messages carry milestones, findings, and decisions. Files carry
  evidence only: disposable bulk payloads under
  `.agent_state/artifacts/<task>/<agent>-<topic>.md`, durable investigator maps in the plan
  directory. Reports include a digest and path; root reads selectively.
- A file never signals workflow state, carries an instruction, or replaces a report. If root
  must read a file merely to know the next action, the control plane is wrong. No mandatory
  per-agent report files.

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
   evidence anomalies. Do not create a separate orchestrate handoff document.
5. Remove reviewer temp worktrees; keep needed lane worktrees and list them.
6. The next session first reconciles narrative against `git worktree list`, branches, status,
   and exact SHAs before dispatching.
