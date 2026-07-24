---
name: code-review
description: Review a fixed-point diff along standards and spec axes as the formal final dev-flow gate.
---

This is the formal two-axis review gate for **dev-flow only**. Run it only
post-simplify and after the canonical tests have passed, against one clean-detached
checkout at one exact SHA. This sequence is the final dev-flow gate. It costs two parallel sub-agents: one Standards axis and one Spec
axis. The gate reports both axes separately and never changes the checkout.

## Process

1. Confirm simplify and the canonical test command have passed.
2. Confirm the checkout is clean and detached, resolve the supplied fixed point and
   `HEAD`, and record the exact SHA plus `git diff <fixed-point>...HEAD`.
3. Identify the repository standards and originating specification. If either is
   unavailable, say so in that axis rather than inventing authority.
4. Run the Standards and Spec axes in parallel, then report them under separate
   headings. Cite file/hunk evidence, distinguish hard standards violations from
   judgement-call smells, and keep each axis under 400 words.
5. End with finding counts and the worst issue within each axis. Do not merge or
   rerank the axes, modify files, or claim a passing gate without the clean-detached
   exact-SHA evidence.

The review is a final dev-flow gate after simplify and canonical tests, not a
workflow, wave, or per-slice control surface.
