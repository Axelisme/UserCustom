# Dev-flow — Collab feedback closeout

This reference owns the Orchestrator sequence when a Dev-flow task requested Collab `efficiencyFeedback` and is approaching managed integration removal or archive.

Dev-flow remains the narrative owner. Collab remains the byte-exact snapshot owner. `plan.py archive` remains an opaque directory move and gains no Collab dependency.

## Pending closeout obligation

When the Orchestrator first requests efficiency feedback for the task, record a concise pending closeout obligation in the task's current narrative. This is not a new frontmatter field or second inventory. It remains only while it changes the task's eventual closeout action.

## Snapshot and summary before retirement

Before managed integration removal and archive:

1. Before `collab_integration_remove`, choose one fresh destination under the task, `research/collab-report-<UTC timestamp>/`.
2. Call public `collab_report` with the task ID and that destination. Its existing task lock and snapshot rules remain authoritative.
3. Read the snapshot's `lane_loop_feedback` records and their workflow report context.
4. Write `research/skill-feedback.md`. Keep actionable observations with an exact raw artifact pointer. Leave receipt-only records in the snapshot. If the request produced no actionable record, say so and point to the snapshot rather than inventing a finding.
5. Remove the pending closeout obligation only after the snapshot and summary exist.
6. Continue with managed integration removal and Dev-flow archive.

If the managed state was removed before the snapshot, the Orchestrator records the missing source and does not fabricate a task-local copy from memory. Existing raw session artifacts may be cited when available, but they do not make the missed closeout successful.
