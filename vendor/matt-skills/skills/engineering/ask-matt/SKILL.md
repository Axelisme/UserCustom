---
name: ask-matt
description: Ask which skill or flow fits your situation. A router over the skills installed here.
disable-model-invocation: true
---

# Ask Matt

You don't remember every skill, so ask.

A **flow** is a path through the skills. Most paths run along one **main flow**, and two **on-ramps** merge onto it. Everything else is standalone, or a vocabulary layer that runs underneath.

## First fork: does this work need a durable record?

Durable task state and agent collaboration are separate choices.

- **No durable record needed**: one session, or a handful you're happy to re-orient by hand. Take the **main flow** below. Its artifacts are a spec and some tickets wherever this repo tracks work; nothing else persists.
- **Durable record needed**: the work must survive compaction and handoff. Start at **`/dev-flow`**, which owns the sole task record under `.agent_state/plans/<task-id>/` and transcribes producer artifacts into it.
- **Delegated implementation needed**: use **`/collab`** with either branch above, when the work should run with a placed writer and an independent acceptance step outside your own context; reach for **`/code-review`** directly instead when only a specialized Standards + Spec report is needed, not full delegation.

Everything below describes the main flow. `/dev-flow` documents durable state; `/collab` documents lightweight agent collaboration.

## The main flow: idea → ship

The route most work travels. You have an idea and want it built.

1. **`/grill-with-docs`** sharpens the idea by interview. Start here whenever you are **working in a working directory**: it's stateful, retaining what it learns in the repo's glossary and ADRs. (No working directory? Use `/grill-me` instead, covered under Standalone. Both run the same `/grilling` primitive; `grill-with-docs` is the one that leaves a paper trail, which makes it the better of the two whenever a repo is there to leave it in.)
2. **Branch: can you settle every question in conversation?** If a question needs a runnable answer (state, business logic, a UI you have to see), detour through a prototype, bridged by **`/handoff`** in both directions (a prototype lives in its own directory, which is exactly what `/handoff` is for; see Phase boundaries):
   - **`/handoff`** out, then open a fresh session against that file,
   - **`/prototype`** to answer the question with throwaway code,
   - **`/handoff`** back what you learned, and reference it from the original idea thread.
3. **Branch: is this a multi-session build?**
   - **Yes** → **`/to-spec`** (turn the thread into a spec), then **`/to-tickets`** to split it into tracer-bullet tickets, each declaring its **blocking edges**. Where those land is repo-specific: if CLAUDE.md / AGENTS.md documents an issue tracker, the edges become native blocking links and any ticket whose blockers are done can be grabbed; otherwise they're one file per ticket under `.scratch/<feature>/issues/`, worked blockers-first by hand. Either way, kick off **`/implement`** per ticket, **`/clear`ing context between each one**. Each ticket is self-contained, so the last one's context is disposable.
   - **No** → **`/implement`** right here, in the same context window.

   Either way, **`/implement`** builds each ticket with validation that exercises the shipped entrypoint. Select **`/tdd`** when that check can be written before the behavior exists. For a specialized Standards + Spec report on a fixed point in history, reach for **`/code-review`** directly. Commit or landing remains subject to applicable user authority. Reach for `/tdd` or `/code-review` directly when only that procedure is needed.

   **Every ticket goes through `/collab`.** There is no task-level choice to make: `/dev-flow`'s lifecycle routes each ticket to collab at its dispatch stage, and collab's own placement decides who writes and who reviews, the Orchestrator writing the change itself being one of those placements. The routing is owned by [`/dev-flow`](../dev-flow/SKILL.md#the-lifecycle); who then writes is collab's.

### Context hygiene

Keep steps 1–3 in **one unbroken context window** (don't compact or clear until after `/to-tickets`) so the grilling, spec, and tickets all build on the same thinking. Each `/implement` then starts fresh, working from the ticket.

The limit on this is the **[smart zone](https://www.aihero.dev/ai-coding-dictionary/smart-zone)**: the window (~150k tokens on state-of-the-art models) within which the model still reasons sharply. If a session approaches it before `/to-tickets`, don't push on degraded; `/compact` at the nearest phase boundary and carry on (see Phase boundaries).

## On-ramps

A starting situation that generates work, then merges onto the main flow.

- **Something's broken** → **`/diagnosing-bugs`**. For the hard ones: the bug that resists a first glance, the intermittent flake, the regression that crept in between two known-good states. It refuses to theorise until it has a **tight feedback loop** (one command that already goes red on *this* bug), then fixes with a regression test. Its post-mortem hands off to **`/improve-codebase-architecture`** when the real finding is that there's no good seam to lock the bug down.

- **A huge, foggy effort: a greenfield project or a huge feature build, too big for one session** → **`/wayfinder`**, the most cognitively demanding flow here. When the way from here to the destination isn't visible yet, it charts a **shared map** of **decision tickets** and resolves them one at a time, producing **decisions, not deliverables**, until the fog is pushed back and the way is clear. Where **`/grill-with-docs`** sharpens an idea you can hold in one session, wayfinder is for the idea you can't, and it's slower and denser, so save it for exactly that, never a well-scoped feature. It is **user-invoked only**: nothing here starts it on your behalf.

  When the map clears, **it hands off, it doesn't build**: merge onto the main flow at **`/to-spec`**, which collapses the map's linked decisions into a buildable plan, then `/to-tickets` and `/implement` as usual. Looping the map straight into `/implement` skips that collapse and throws the linked detail away, so go straight to `/implement` only when the effort turned out genuinely small.

## Work you found but shouldn't do now

**`/candidate-backlog`** is an evidence-backed discovery that is real but outside the current task's acceptance. It goes to a repo-local inbox under `.agent_state/backlog/` instead of expanding the task or being forgotten. Also the thing to read when planning work in an area (check its inbox first) or when you ask "what's worth doing next".

It is the **internal** inbox: things you found while working. If this repo ever starts taking bug reports and feature requests from other people, that's a different surface with a different skill (`triage` upstream), and it isn't installed here.

## Codebase health

Not feature work, just upkeep.

- **`/improve-codebase-architecture`** runs whenever you have a spare moment to keep the codebase good for agents to operate in. It surfaces **deepening opportunities**; picking one _generates an idea_ you can take into the main flow at `/grill-with-docs`. It's the survey that finds the candidates; **`/codebase-design`** (below) is the bench you design the chosen one on. Its report is written in Traditional Chinese.
- **`/simplify`** is a quality pass over code you just changed: reuse, simplification, efficiency, altitude. It does not hunt for bugs; `/code-review` does that.

## Vocabulary underneath

Two model-invoked references that run *beneath* the other skills, each the single source of truth for its vocabulary. Reach for them directly when the **words**, not the process, are the problem; or let the skills above pull them in.

- **`/domain-modeling`**: sharpen the project's *domain* language: challenge a fuzzy term, resolve an overloaded word ("account" doing three jobs), record a hard-to-reverse decision as an ADR. It's the active discipline `/grill-with-docs` drives to keep the glossary clean. Where the glossary and ADRs live follows the repo's own documented conventions.
- **`/codebase-design`** is the deep-module vocabulary (module, interface, depth, seam, adapter, leverage, locality) for designing a module's *shape*: a lot of behaviour behind a small interface at a clean seam. `/tdd` and `/improve-codebase-architecture` both speak it.

## Phase boundaries

A **phase** is a chunk of work inside a session: the grilling, the implementation, the QA. At the **boundary** between two of them you have five options, and picking between them is the fuzziest decision in this whole map:

- **Continue**: stay put. Costs nothing, loses nothing.
- **`/clear`**: empty the window, when nothing here matters to what's next.
- **`/handoff`** writes a portable markdown file. Narrow: only for a **new harness**, a **new directory**, a **colleague**, or forking a side task **mid-phase**. What it buys is portability.
- **Subagent**: send a tightly-scoped task to its own window and get a report back.
- **`/compact`** compresses this context and seeds a fresh session with it. The **default**, at the bottom of the tree rather than the first reach.

Read [PHASE-BOUNDARIES.md](PHASE-BOUNDARIES.md) for the ordered tree: the five questions, the reasoning behind each branch, and why the primary-source cost makes **Continue** the one to rule out first. Make the decision **at** a boundary; mid-phase, continue or split the rest into subagents.

This is the *session-level* answer. When the work needs a record that outlives every one of these moves, that's the durable-record workflow at the top of this file; `/dev-flow` owns it, and none of the five options here replace it.

## Standalone

Off the main flow entirely.

- **`/grill-me`**: the same relentless interview as `/grill-with-docs`, but **stateless**: it saves nothing locally and writes no glossary. Reach for it when you are **not working in a working directory** (sharpening a plan, a design, a piece of writing, anything with no repo under it). If you are in a working directory, use `/grill-with-docs` instead: it runs the same interview and leaves a paper trail, so it is strictly the better one.
- **`/grilling`** is the interview primitive itself: rounds, the frontier, facts are the agent's job and decisions are yours. `/grill-me` and `/grill-with-docs` are the two named ways in, and `/wayfinder` and `/improve-codebase-architecture` both run it internally. Reach for it directly only when you want the interview with no wrapper around it.
- **`/prototype`** is a small, throwaway program that answers one design question: does this state model feel right, or what should this UI look like. Throwaway is a constraint on how the code is written, not a promise to destroy it: the answer folds into the real code, and the prototype itself is kept as a **primary source** on a `prototype/<name>` branch out of main, pointed at from wherever the work is tracked. It's the detour in step 2 of the main flow, but reach for it any time a design question is hard to settle on paper.
- **`/research`**: delegate reading legwork to a **background agent**: it investigates a question against **primary sources**, then leaves a cited Markdown file in the repo. Keep working while it reads. The file it produces is something to take *into* the main flow at `/grill-with-docs`, since research feeds the thinking, it doesn't replace it.
- **`/wait-what`** is the corrective for a message that didn't land. Use it mid-conversation, inside any other skill, and the agent re-pitches what it just said in plain Traditional Chinese, with the context you were missing and the project's own glossary vocabulary. It works after the fact; `/grill-with-docs` is the upfront cure, because a shared language agreed early is what stops the jargon arriving at all.
- **`/writing-for-agents`** is the reference for writing documents agents consume: skills, CLAUDE.md / AGENTS.md, pointed-at docs. Its `SKILL-MECHANICS.md` covers the skill-specific mechanics, including a `PORTING.md` checklist for adopting a skill written for another ecosystem.

## Not a flow: a mode

**`/dictator`** hands the agent full implementation discretion for the current task: it decides order, tactics, and reversible architecture calls without asking per item, and reports every decision at close-out. It changes *how* any flow above is driven, not *which* one you're on.
