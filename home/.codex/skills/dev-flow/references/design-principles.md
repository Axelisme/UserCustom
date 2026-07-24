# Dev-flow design principles

Read at evolution time when changing the workflow; this file is not an acceptance step.

1. Git is the only durable workflow truth; project state is projected from commits, refs, and trailers. Incident: v119 decision, 2026-07-24.
2. Every handoff and gate binds to an exact clean SHA, never a summary. Incident: v119 handoff rule, 2026-07-24.
3. The acceptance surface has one owner; contract tests are immutable to the implementer. Incident: v119 acceptance contract.
4. The spec freezes with a closed usage envelope; findings without contract basis become backlog. Incident: v119 frozen-spec review rule.
5. Rigor scales with change risk, not with the number of available mechanisms. Incident: skill_feedback4 root cause.
6. Batch everything known at the same moment into one cycle. Incident: skill_feedback4 root cause.
7. Cheap machine gates run early and often; expensive judgement runs late, once, over the accumulated diff. Incident: 2026-07-24 two-level gate decision.
8. Gates migrate upstream: when a late gate catches the same defect class twice, the check moves earlier or becomes automated. Incident: skill_feedback.md §4.1/§13 candidate-specific RED.
9. The cost function is risk removed per token, not process executed. Incident: skill_feedback4 root cause.
10. Every ceremony must cite the failure it prevents; rules that cannot name an incident go on the retirement watchlist. Incident: this cleanup pass, 2026-07-24.
11. Judgement stays with Root; agents get closed enums, decision flows, and hard conditions. Incident: blocking enum, mechanical enum, and checkpoint hard-condition fixes.
12. Overlap independent work; start dependent work at the intermediate artifact. Non-overlapping write scopes may run as parallel Waves from the same integration base; a downstream Wave needing only the upstream interface starts at the exact Contract merge, not implementation completion. Incident: 2026-07-24 pipeline/slice motivation.
