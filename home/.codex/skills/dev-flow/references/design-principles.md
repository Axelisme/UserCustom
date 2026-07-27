# Dev-flow design principles

Read this file when evolving the workflow. The admission standard is the normative S1–S5
authority; these principles explain altitude and evidence without duplicating its checks.

1. Git commits, refs, and trailers are durable workflow truth; prose is a pointer.
2. Every handoff and gate binds to one exact clean SHA, never to a summary.
3. The acceptance surface has one owner, and Contract tests are immutable to Implementation.
4. Freeze the usage envelope first; findings without a Contract basis are backlog.
5. Scale rigor with change risk and remove risk per token, not mechanisms per se.
6. Batch findings known at the same moment into one bounded correction cycle.
7. Run cheap machine evidence early; reserve independent judgement for the assembled exact
   candidate after the increment is bounded.
8. Keep judgement with Root and give every role closed decisions, scopes, and stop conditions.
9. Design the observable interface and failure contract first, implement the smallest behavior,
   and harden only when the envelope or a red Contract test requires it.
10. A timing, locking, retention, or replay device enters only with a test that is red without
    it; otherwise it is speculative complexity.
11. Production reachability is evidence, not an assumption: a green test suite cannot validate
    code no shipped entrypoint reaches.
12. Independence beats persuasive dispatch prose; reviewers receive artifacts and a fixed point.
