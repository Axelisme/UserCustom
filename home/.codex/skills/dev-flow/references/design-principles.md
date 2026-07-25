# Dev-flow design principles

Read at evolution time when changing the workflow; this file is not an acceptance step. Rules
1-4 are axioms; every later rule cites the failure it prevents, and one that cannot name an
incident goes on the retirement watchlist.

1. Git is the only durable workflow truth; project state is projected from commits, refs, and trailers.
2. Every handoff and gate binds to an exact clean SHA, never a summary.
3. The acceptance surface has one owner; contract tests are immutable to the implementer.
4. The spec freezes with a closed usage envelope; findings without contract basis become backlog.
5. Rigor scales with change risk, not with the number of available mechanisms. Incident: skill_feedback4 root cause.
6. Batch everything known at the same moment into one cycle. Incident: skill_feedback4 root cause.
7. Cheap machine gates run early and often; expensive judgement runs late, once, over the accumulated diff. Incident: 2026-07-24 two-level gate decision.
8. Gates migrate upstream: when a late gate catches the same defect class twice, the check moves earlier or becomes automated. Incident: skill_feedback.md §4.1/§13 candidate-specific RED.
9. The cost function is risk removed per token, not process executed. Incident: skill_feedback4 root cause.
10. Judgement stays with Root; agents get closed enums, decision flows, and hard conditions. Incident: blocking enum, mechanical enum, and checkpoint hard-condition fixes.
11. Task-level meta belongs in a ref, per-commit identity belongs in a trailer, and nothing durable lives in a reflog or a state file. Incident: the reflog-derived integration base reported another task's collects, 2026-07-24.
12. Overlap independent work; start dependent work at the intermediate artifact. Non-overlapping write scopes may run as parallel Waves from the same integration base; a downstream Wave needing only the upstream interface starts at the exact Contract merge, not implementation completion. Incident: 2026-07-24 pipeline/slice motivation.
13. Build in order: freeze the envelope, design the interface including its failure contract, implement the minimal behavior, harden last. Failure modes, idempotency, ordering guarantees, resource lifetime, and atomicity are interface decisions and cannot be deferred; input validation, retries, caches, and cases outside the envelope are hardening and must be. Incident: roles hedged with edge cases before requirements settled, 2026-07-25.
14. A mechanism enters on the same evidence that removes it: a timing, locking, retention, or replay device needs a test that is red without it, in both directions. Requiring evidence only on removal ratchets complexity upward. Incident: the v122 simplify guard, which asked for a reproduction to delete machinery that entered for free.
