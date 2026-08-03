---
name: ask-matt
description: Ask which skill or flow fits your situation. A router over the skills installed here.
disable-model-invocation: true
---

# Ask Matt

You don't remember every skill, so ask.

A **flow** is a path through the skills. Most paths run along one **main flow**, and two **on-ramps** merge onto it. Everything else is standalone, or a vocabulary layer that runs underneath.

## First fork: does this work need a durable record?

Two workflows live here side by side, and picking the wrong one is the most expensive mistake this router can prevent.

- **No durable record needed** — one session, or a handful you're happy to re-orient by hand. Take the **main flow** below. Its artifacts are a spec and some tickets wherever this repo tracks work; nothing else persists.
- **Durable record needed** — the work must survive compaction and handoff, or it will be dispatched to worker agents in parallel. Start at **`/dev-flow`**, which owns the task record under `.agent_state/plans/<task-id>/`, and **`/orchestrate`**, which owns the Git lanes that dispatch and land it. They consume the main flow's skills as producers — `/dev-flow` transcribes a spec or a set of tickets into its record — so the two workflows compose; they don't compete.

Everything below describes the main flow. `/dev-flow` and `/orchestrate` document their own stages.

## The main flow: idea → ship

The route most work travels. You have an idea and want it built.

1. **`/grill-with-docs`** — sharpen the idea by interview. Start here when you **have a codebase**: it's stateful, retaining what it learns in the repo's glossary and ADRs. (No codebase? Use `/grill-me` — see Standalone. Both run the same `/grilling` primitive; `grill-with-docs` is the one that leaves a paper trail.)
2. **Branch — can you settle every question in conversation?** If a question needs a runnable answer (state, business logic, a UI you have to see), detour through a prototype, bridged by **`/handoff`** in both directions (see Crossing sessions):
   - **`/handoff`** out, then open a fresh session against that file,
   - **`/prototype`** to answer the question with throwaway code,
   - **`/handoff`** back what you learned, and reference it from the original idea thread.
3. **Branch — is this a multi-session build?**
   - **Yes** → **`/to-spec`** (turn the thread into a spec), then **`/to-tickets`** to split it into tracer-bullet tickets, each declaring its **blocking edges**. Where those land is repo-specific: if CLAUDE.md / AGENTS.md documents an issue tracker, the edges become native blocking links and any ticket whose blockers are done can be grabbed; otherwise they're one file per ticket under `.scratch/<feature>/issues/`, worked blockers-first by hand. Either way, kick off **`/implement`** per ticket, **clearing context between each one**.
   - **No** → **`/implement`** right here, in the same context window.

   Either way, **`/implement`** builds each ticket by driving **`/tdd`** internally — one red-green cycle at a time — then closes out by running **`/code-review`**, a two-axis review (Standards + Spec) of the diff, before committing. Reach for **`/tdd`** on its own when you just want to build a concrete behaviour test-first without a full spec, and **`/code-review`** on its own whenever you want to review a branch or PR against a fixed point.

### Context hygiene

Keep steps 1–3 in **one unbroken context window** — don't compact or clear until after `/to-tickets` — so the grilling, spec, and tickets all build on the same thinking. Each `/implement` then starts fresh, working from the ticket.

The limit on this is the **[smart zone](https://www.aihero.dev/ai-coding-dictionary/smart-zone)**: the window (~120k tokens on state-of-the-art models) within which the model still reasons sharply. If a session approaches it before `/to-tickets`, don't push on degraded — `/handoff` and continue in a fresh thread.

## On-ramps

A starting situation that generates work, then merges onto the main flow.

- **Something's broken** → **`/diagnosing-bugs`**. For the hard ones: the bug that resists a first glance, the intermittent flake, the regression that crept in between two known-good states. It refuses to theorise until it has a **tight feedback loop** — one command that already goes red on *this* bug — then fixes with a regression test. Its post-mortem hands off to **`/improve-codebase-architecture`** when the real finding is that there's no good seam to lock the bug down.

- **A huge, foggy effort — a greenfield project or a huge feature build, too big for one session** → **`/wayfinder`**, the most cognitively demanding flow here. When the way from here to the destination isn't visible yet, it charts a **shared map** of **decision tickets** and resolves them one at a time — producing **decisions, not deliverables** — until the fog is pushed back and the way is clear. Where **`/grill-with-docs`** sharpens an idea you can hold in one session, wayfinder is for the idea you can't — and it's slower and denser, so save it for exactly that, never a well-scoped feature. It is **user-invoked only**: nothing here starts it on your behalf.

  When the map clears, **it hands off, it doesn't build**: merge onto the main flow at **`/to-spec`**, which collapses the map's linked decisions into a buildable plan, then `/to-tickets` and `/implement` as usual. Looping the map straight into `/implement` skips that collapse and throws the linked detail away — go straight to `/implement` only when the effort turned out genuinely small.

## Work you found but shouldn't do now

**`/candidate-backlog`** — an evidence-backed discovery that is real but outside the current task's acceptance. It goes to a repo-local inbox under `.agent_state/backlog/` instead of expanding the task or being forgotten. Also the thing to read when planning work in an area (check its inbox first) or when you ask "what's worth doing next".

It is the **internal** inbox — things you found while working. If this repo ever starts taking bug reports and feature requests from other people, that's a different surface with a different skill (`triage` upstream), and it isn't installed here.

## Codebase health

Not feature work — upkeep.

- **`/improve-codebase-architecture`** — run whenever you have a spare moment to keep the codebase good for agents to operate in. It surfaces **deepening opportunities**; picking one _generates an idea_ you can take into the main flow at `/grill-with-docs`. It's the survey that finds the candidates; **`/codebase-design`** (below) is the bench you design the chosen one on. Its report is written in Traditional Chinese.
- **`/simplify`** — quality pass over code you just changed: reuse, simplification, efficiency, altitude. It does not hunt for bugs; `/code-review` does that.
- **`/resolving-merge-conflicts`** — for an in-progress merge or rebase that has stopped on conflicts. Resolves from the primary sources behind each side rather than from the diff alone.

## Vocabulary underneath

Two model-invoked references that run *beneath* the other skills — each the single source of truth for its vocabulary. Reach for them directly when the **words**, not the process, are the problem; or let the skills above pull them in.

- **`/domain-modeling`** — sharpen the project's *domain* language: challenge a fuzzy term, resolve an overloaded word ("account" doing three jobs), record a hard-to-reverse decision as an ADR. It's the active discipline `/grill-with-docs` drives to keep the glossary clean. Where the glossary and ADRs live follows the repo's own documented conventions.
- **`/codebase-design`** — the deep-module vocabulary (module, interface, depth, seam, adapter, leverage, locality) for designing a module's *shape*: a lot of behaviour behind a small interface at a clean seam. `/tdd` and `/improve-codebase-architecture` both speak it.

## Crossing sessions

- **`/handoff`** — when a thread is full or you need to branch off (e.g. into a `/prototype` session), this compacts the conversation into a markdown file. You don't continue in place — you **open a new session and reference that file** to carry the context across. It's the bridge between context windows, in either direction. Use it when you want a **fresh session** but need the **current conversation preserved**.
- **`/compact`** (built-in) — stay in the **same conversation**, letting the earlier turns be summarized. Use it at **intentional breaks between phases**, when you don't mind losing the verbatim history. Don't compact mid-phase — the agent can lose its way. `/handoff` forks; `/compact` continues.

## Standalone

Off the main flow entirely.

- **`/grill-me`** — the same relentless interview as `/grill-with-docs`, but for when you have **no codebase**. Stateless: it saves nothing locally, writes no glossary. Reach for it to sharpen any plan or design that doesn't live in a repo.
- **`/prototype`** — a small, throwaway program that answers one design question: does this state model feel right, or what should this UI look like. Throwaway from day one — keep the answer, delete the code. It's the detour in step 2 of the main flow, but reach for it any time a design question is hard to settle on paper.
- **`/research`** — delegate reading legwork to a **background agent**: it investigates a question against **primary sources**, then leaves a cited Markdown file in the repo. Keep working while it reads. The file it produces is something to take *into* the main flow at `/grill-with-docs` — research feeds the thinking, it doesn't replace it.
- **`/teach`** — learn a concept over multiple sessions, using the current directory as a stateful workspace. Its lessons and reference documents are written in Traditional Chinese.
- **`/writing-great-skills`** — reference for writing and editing skills well; its `PORTING.md` covers adopting a skill written for another ecosystem.

## Not a flow — a mode

**`/dictator`** — hands the agent full implementation discretion for the current task: it decides order, tactics, and reversible architecture calls without asking per item, and reports every decision at close-out. It changes *how* any flow above is driven, not *which* one you're on.
