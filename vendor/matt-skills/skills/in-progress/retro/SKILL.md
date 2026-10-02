---
name: retro
description: "Conduct a retrospective on a coding session."
disable-model-invocation: true
---

The user has asked for a **retrospective**. You are suggesting improvements to the coding agent's **environment** to improve future runs. Present proposals; implementing them needs a separately authorized task.

## Steps

1. Call the Skill tool with `writing-for-agents` for the writing style guide.

2. Read the primary sources for the session the user specifies. Default to the current session's available evidence. For a named prior session, read its relevant log or record if accessible, rather than searching unrelated histories. State any source gap; do not reconstruct missing events. Cite relevant locations without copying secrets or raw logs.

3. Look for candidates for improvement in these categories.

- **Navigation**: how easy was it for the agent to find the right files? Are there hidden dependencies between files? Would a **navigation pointer** make it easier? _Use when_ the session took a long time to find a piece of information.
- **Automated checks**: are there automated checks that could catch errors the agent made? Read the repo's own check command first (its `package.json`/build-tool `lint`/`check` scripts, its CI workflow), so a check that already exists but sits unwired or silently broken is the finding, not a reinvention. Recommend an applicable **guardrail** when a session event shows the gap. Prose, configuration, repository data and file locations receive direct review, not tests of their wording or layout. _Use when_ the agent made a mistake an applicable check could have caught.
- **Coding standards**: should a rule be added, removed or clarified? Classify the violation first. For a **mechanical** program error, prefer an applicable deterministic check over another steering sentence. Reserve the repo's standards document for genuine **judgement calls**, such as cross-file consistency or "matches the surrounding style." Relevant rules guide implementation as well as review. _Use when_ an implementation or review missed a concrete constraint.
- **Global AGENTS.md**: are there any steering instructions that should be moved to coding standards (or automated checks) instead? _Use when_ the AGENTS.md file is particularly large - in the repo OR the user's global scope.
- **Tool economy**: did the agent make expensive tool calls that could be streamlined? Is there any custom tooling (CLI's, MCP's) that is particularly token-inefficient? _Use when_ the agent made an expensive tool call.
- **No-ops**: look for instructions in steering files that don't modify the agent's behavior. _Use when_ the steering files are large and unwieldy.
- **Information access**: look for opportunities to increase the agent's access to information. Teeing dev server logs, readonly access to third-party services. _Use when_ a crucial piece of information was not available to the agent.

4. Keep only candidates grounded in a specific session event. State the observation, source location, impact and desired outcome; rank by supported impact. The categories are prompts, not quotas. If no candidate meets that bar, say so.

5. Read `candidate-backlog` for cross-task environment candidates. It owns admission, deduplication, storage and lifecycle; use that workflow and report the resulting IDs instead of keeping a second candidate list. Current-task correctness, regression or acceptance gaps stay with that task. A candidate needing a scope or authority decision returns to the user, not to backlog as a substitute. Capturing a candidate does not authorize changing tools, hooks, permissions or instructions.

## Reference

### Implementation vs Review

Use the active role contracts to decide who explores, writes and validates. A reviewer may need declarations, callers, tests and recorded gate evidence to judge a fixed subject; a diff alone is not sufficient context. Make relevant constraints available to the implementer before work starts as well as to the reviewer.

### Files

You have access to several files in the repo:

- `CLAUDE.md`/`AGENTS.md`: preserve their governing authority and use **navigation pointers** for material needed only on a particular branch of work.
- Standards: follow the repo's documented location and read conditions, whether `CODING_STANDARDS.md`, `CONTRIBUTING.md` or a module document. Keep one owning source rather than inventing a second standards file.
- Docs: use docs as references files, pointed to by other files. Look for existing docs before writing new ones.
- Skills: use skills for docs (since their description goes into the agent's context window), or for user-invoked commands. Follow the advice in the `writing-for-agents` skill.
