# Dev-flow design principles

Read this file when evolving the workflow. `SKILL.md` owns S0 and the durable record; `collab`
owns lightweight implementation collaboration. These principles explain altitude and evidence
without duplicating either skill's checks.

1. Dev-flow's record is durable narrative and authority; collaboration evidence points to it rather
   than creating a competing store.
2. Every review binds to an immutable runtime handoff or one exact clean SHA and tree. A handoff
   routes to the factual owners it names rather than replacing them.
3. The Caller owns Acceptance wording and final judgement; Implement may only toggle delegated
   checkbox claims, and review verifies without mutation.
4. Freeze the usage envelope first; findings without an Envelope basis return to the Caller for
   disposition.
5. Scale rigor with change risk and remove risk per token, not mechanisms per se.
6. Batch findings known at the same moment into one bounded correction cycle.
7. Run cheap machine evidence early; reserve independent judgement for the assembled exact
   candidate after the increment is bounded.
8. Keep judgement with the Caller and give every role closed decisions, scopes, and stop conditions.
9. Depth does not appear on its own: incremental, slice-by-slice delivery only constrains the size
   and order of each increment, and takes no position on where a seam belongs, so left unchecked it
   pulls toward one thin adapter per feature. S0's Design stage counters that pull before Implement;
   independent review checks the assembled fixed subject afterward.
10. A timing, locking, retention, or replay device enters only with a test that is red without
    it; otherwise it is speculative complexity.
11. Production reachability is evidence, not an assumption: a green test suite cannot validate
    code no shipped entrypoint reaches.
12. Independence beats persuasive dispatch prose; reviewers receive artifacts and a fixed point.
13. Size a handoff by what the receiver must read before it can start: carry the conclusion, locate
    the rest exactly, and end every reference with the condition that discharges it.
