---
name: simplify
description: Review the current code changes for reuse, quality, and efficiency, then apply straightforward fixes. Use when the user asks to simplify, clean up, reduce duplication, improve changed code, or review git changes with an optional focus such as performance, memory use, React rerenders, SQL queries, or other project-specific concerns.
---

# Simplify

Review the current working changes, identify avoidable complexity, and directly fix issues that are clear, low-risk, and aligned with the repository's existing style.

This skill is adapted from the `/simplify` workflow: identify changed code, run three focused reviews, then aggregate the findings into concrete edits.

## Inputs

The user may provide an additional focus after the request, for example:

```text
simplify this, focus on memory usage
simplify the changed files and pay attention to React rerenders
simplify with extra attention to SQL query efficiency
```

Treat that text as **Additional Focus**. Apply it to every review pass, but do not let it replace the core reuse, quality, and efficiency checks.

## Process

### 1. Identify Changes

Find the code under review before making any judgement.

Prefer git state:

- Use `git diff` for unstaged changes.
- Use `git diff --staged` for staged changes.
- If the user asks for a specific base, use that explicit diff range instead.
- If both staged and unstaged changes exist, inspect both and keep them conceptually separate.
- When earlier work has already passed a formal review, start from that reviewed SHA. Re-reading an accepted diff cannot find new hygiene problems and costs the same as reading new code.

If there are no git changes, fall back to recently modified files only when that is useful and safe. Tell the user that no git diff was present.

Do not review generated artifacts, dependency lock churn, vendored code, build output, or large data files unless the user explicitly asks.

### 2. Run Two Focused Reviews

Review the relevant diff from two angles. For a large diff, use parallel sub-agents if available; otherwise run both passes yourself in separate notes before editing.

Each pass receives:

- The relevant diff or changed-file set.
- The user's Additional Focus, if any.
- The repository's local instructions and conventions.

#### Shape and Reuse

Look for:

- Duplicated logic or copy-paste control flow.
- Hand-rolled helpers that duplicate existing project utilities.
- Similar functions or branches that can be collapsed without hiding important differences.
- New abstractions that are shallower than the duplication they replace.
- Redundant state, unnecessary parameters, and parameter sprawl.
- Leaky abstractions or call sites forced to know implementation details.
- Stringly typed code where a stronger local type or enum already exists.
- Unclear naming, surprising control flow, or low-value comments.
- Excessive nesting, especially JSX or UI layout nesting.
- Error handling that hides failures instead of failing fast.
- Test hygiene in the changed set: duplicated assertions, tests that cannot fail for their own specific reason, leftover tests for removed behavior, fixture sprawl, and test files whose structure no longer mirrors the production layout.

#### Efficiency

Look for:

- Avoidable repeated work, missed batching, or missed concurrency.
- Hot-path allocations or computations that can move out of loops.
- Recurring no-op updates or unnecessary rerenders.
- TOCTOU existence checks where the operation itself can report failure.
- Memory leaks, unbounded caches, or overly broad data fetches.
- Synchronous work that blocks a user-facing path without need.

### 3. Decide What To Fix

Fix issues directly when all of these are true:

- The issue is in the changed code, supported by the diff or nearby code.
- The fix is local, low-risk, and roughly 30 lines or fewer.
- An existing test already covers the behavior the fix touches.
- The repository already has a clear pattern to follow.
- The change improves simplicity without broadening scope.

Skip or report issues instead of editing when:

- The finding is subjective and the current code is defensible.
- The fix requires an architectural decision not already made.
- The fix needs product, API, schema, or compatibility judgement.
- The change would alter behavior beyond the user's request.
- The finding would remove a load-bearing mechanism — authority, lifecycle, lock ordering, retention, or cross-process sequencing — on source reading alone. Such machinery reads as accidental complexity and often is not, so removal needs a minimal executable reproduction: reading has argued for deleting timing that held the system together. Report it rather than guessing. This cuts both ways — when nobody can produce the failing test that justifies such a mechanism, record that as its own finding, because an unjustified mechanism is a defect, not a fixture.
- The change would alter a frozen public contract or an immutable acceptance surface (e.g. Oracle-owned contract tests in dev-flow): report it for routing to a contract correction or the candidate backlog. Never edit a test to match code you just changed — that silently rewrites what was accepted. Internal shape is always yours to simplify; the promised interface is not.
- The apparent problem is in generated, vendored, or intentionally duplicated code.

### 4. Apply Edits

Keep edits tight. Prefer existing helpers and local conventions over new abstractions.

When replacing duplication, preserve the visible behavior and tests. When improving efficiency, make the before/after behavior explicit enough that a reviewer can tell what changed.

Do not mix unrelated cleanup into the patch. If you notice larger cleanup opportunities, report them separately.

### 5. Verify

Run the narrowest useful verification first, then broader checks when the blast radius justifies it.

Use the repository's documented test, typecheck, lint, and formatting commands. If a command cannot be run, say why.

### 6. Summarize

Report findings in three groups so the caller triages once, not per finding:

- **Applied**: what changed and what checks ran, with results.
- **Needs a contract or a reproduction**: real but out of scope here — the danger categories above, and anything whose evidence is source reading alone.
- **Backlog**: subjective or low-priority cleanup, and false positives worth recording.

If no changes are needed, say the changed code already looks clean and mention any verification performed.

## Sub-Agent Prompt Template

When sub-agents are available, launch both in parallel with prompts shaped like this:

```text
Review the following diff for <Shape and Reuse | Efficiency>.

Additional Focus:
<user focus or "None">

Repository conventions:
<brief local instructions or paths to read>

Report only concrete findings that are supported by the diff or nearby code.
For each finding, include file/path, why it matters, and the smallest safe fix.
Skip style issues that tooling will handle.
Keep the report under 400 words.
```

Aggregate the reports before editing. Do not apply a suggested fix until you have independently confirmed it against the codebase.
