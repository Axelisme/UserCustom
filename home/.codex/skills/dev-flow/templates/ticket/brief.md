# Implement {{TICKET_ID}}

<!-- Message template: send the filled body as the implementer dispatch. No task file is required.
     Procedure: ~/.codex/skills/collab/references/execution.md#delegate -->

## Checkout
<!-- Absolute lane worktree path and branch. You are its only writer. Commit on this branch only; no
     merge into integration or persistence, no push. -->

## Contract
<!-- Exact ticket anchors: #outcome, #scope-and-assumptions, #contract-starting-point, #acceptance.
     Name the criteria this lane must satisfy. -->

## Gates
<!-- Commands from the ticket's #mechanical-gates in the order to run them, with cwd, selection, and
     timeout. -->

## Environment
<!-- Interpreter and run form, caches, and any cleanup exception; or None beyond repository defaults. -->

## Sources
<!-- Repository instruction and technical skill paths with read conditions, or None. -->

## Blockers and escalation
<!-- Known blockers, and whom to ask: the parent through contact_parent, or BLOCKED for a
     single-return runtime. -->

## Correction
<!-- For a fix: verdict path and finding IDs to address. Otherwise None. -->

## Result path
<!-- Absolute path of the task's runs/ directory. Write runs/<short-sha>/summary.md for the candidate
     commit, with raw logs beside it. -->
