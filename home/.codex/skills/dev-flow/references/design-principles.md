# Dev-flow design principles

Read this file when evolving the workflow. `SKILL.md` owns S0 and orchestrate's
[admission](../../orchestrate/references/admission.md) owns S1–S5; these principles explain
altitude and evidence without duplicating either one's checks.

1. Git commits, refs, and trailers are durable workflow truth; prose is a pointer.
2. Every handoff and gate binds to one exact clean SHA, never to a summary.
3. The acceptance surface has one owner, and Contract tests are immutable to Implementation.
4. Freeze the usage envelope first; findings without a Contract basis are backlog.
5. Scale rigor with change risk and remove risk per token, not mechanisms per se.
6. Batch findings known at the same moment into one bounded correction cycle.
7. Run cheap machine evidence early; reserve independent judgement for the assembled exact
   candidate after the increment is bounded.
8. Keep judgement with Root and give every role closed decisions, scopes, and stop conditions.
9. Depth does not appear on its own: incremental, slice-by-slice delivery only constrains the size
   and order of each increment, and takes no position on where a seam belongs, so left unchecked it
   pulls toward one thin adapter per feature. S0's Design stage and S2's red-evidence gate exist to
   counteract that pull; see `../SKILL.md` and orchestrate's `admission.md` for the checks.
10. A timing, locking, retention, or replay device enters only with a test that is red without
    it; otherwise it is speculative complexity.
11. Production reachability is evidence, not an assumption: a green test suite cannot validate
    code no shipped entrypoint reaches.
12. Independence beats persuasive dispatch prose; reviewers receive artifacts and a fixed point.
13. Size a handoff by what the receiver must read before it can start: carry the conclusion, locate
    the rest exactly, and end every reference with the condition that discharges it.
