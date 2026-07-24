---
name: code-review
description: Review a fixed-point diff along standards and spec axes as the formal final dev-flow gate.
---

This is the formal two-axis review gate for **dev-flow only**. Run it only
post-simplify and after the canonical tests have passed, against one clean-detached
checkout at one exact SHA. This sequence is the final dev-flow gate. It costs two parallel sub-agents: one Standards axis and one Spec
axis. The gate reports both axes separately and never changes the checkout.

## Process

1. Confirm simplify and the canonical test command have passed; otherwise no gate.
2. Confirm the checkout is clean and detached, resolve the supplied fixed point and
   `HEAD`, and record the exact SHA plus `git diff <fixed-point>...HEAD`.
3. Identify the repository standards and originating frozen specification. When dispatching
   the axes, pass the frozen spec and acceptance record as absolute paths — gitignored plan
   files are invisible from a detached checkout. If either standard is unavailable, say so
   in that axis rather than inventing authority.
4. Run the Standards and Spec axes in parallel, report separate headings, cite file/hunk
   evidence, and keep each axis under 400 words. Every finding is tagged `blocking` or
   `backlog` and includes `contract_basis` naming the exact frozen-spec clause/item;
   absent `contract_basis` means `backlog` only. If the reviewer believes the Contract is
   insufficient or wants stronger semantics than it states, the verdict is
   `blocked_on_decision`, not `needs_fix`; stronger wishes are not existing norms.
5. For mechanical small findings (naming, dead code, typo, or ≤30 lines of local logic),
   include a directly applicable unified diff patch proposal inside the finding. Stay
   read-only and never modify the checkout. After Root applies such a patch, validation is
   only: applied diff matches the proposed patch, and focused tests are green; do not open
   another two-axis review for that patch.
6. End with finding counts and the worst issue within each axis. Do not merge or rerank
   axes, modify files, or claim a passing gate without clean-detached exact-SHA evidence.

The review is a final dev-flow gate after simplify and canonical tests, not a
workflow, wave, or per-slice control surface.
