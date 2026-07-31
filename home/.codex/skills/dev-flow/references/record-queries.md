# Task-record queries

These are queries, not validators. A record can violate what they reveal; readers bear the cost of
noticing and repairing that fact in context.

- To see the frontier, largest ticket ID, and complete dependency graph, list every ticket header in
  `tickets/*.md`.
- To see which decisions were superseded, list every `Status` cell in `decisions.md`.
- To see the complete record inventory, run `scripts/plan.py refresh <task-id>` and read the
  generated files block in `INDEX.md`.
