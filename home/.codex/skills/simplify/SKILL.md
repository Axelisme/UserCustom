---
name: simplify
description: Review the changed code for reuse, simplification, efficiency, and altitude cleanups, then apply the fixes. Quality only — it does not hunt for bugs; use /code-review for that.
argument-hint: "[<target>]"
---

# Simplify

You are improving the quality of the changed code, not hunting for bugs. Review
it for reuse, simplification, efficiency, and altitude issues, then fix what you
find. Do not look for correctness bugs — that is what `/code-review` is for.

## Phase 0 — Gather the diff

Run `git diff @{upstream}...HEAD` (or `git diff main...HEAD` / `git diff HEAD~1`
if there's no upstream) to get the unified diff under review. If there are
uncommitted changes, or the range diff is empty, also run `git diff HEAD` and
include the working-tree changes in scope — the review often runs before the
commit. If a PR number, branch name, or file path was passed as an argument,
review that target instead. Treat this diff as the review scope.

**Whole-tree mode.** When the argument is a directory, the scope is everything
under it, not a diff. Use this when the cost accumulated across many changes
rather than inside one: boilerplate that grew a few lines per commit is
invisible to every diff review, because no single diff ever contained enough of
it to notice. Say in the summary that whole-tree mode ran and over what path, so
nobody reads the findings as being about recent work.

## Phase 1 — Review (4 cleanup angles in parallel)

Launch **4 independent review agents** through this harness's sub-agent tool,
all in a single message so they run concurrently. Pass each agent the diff and
one of the four angles below. Each returns its findings with `file`, `line`, a
one-line `summary`, and the concrete cost (what is duplicated, wasted, or
harder to maintain).

If no sub-agent tool is available, work through all four angles yourself, in
this same context, in one pass — do not skip an angle for lack of fan-out, and
say so in the summary. State clearly that this was a single-pass review without
the 4-agent fan-out, so whoever reads it isn't misled about what actually ran.

### Reuse

Flag new code that re-implements something the codebase already has — Grep
shared/utility modules and files adjacent to the change, and name the existing
helper to call instead. Tests count: duplicated assertions, and hand-rolled
fixtures or helpers that shadow ones the suite already provides.

In whole-tree mode, count instead of listing. A repeated sequence is worth
reporting as "this prologue appears N times, about M reclaimable lines" — a
finding a reader can decide on. A list of file/line hits for something occurring
hundreds of times is not actionable, and buries the one number that is.

### Simplification

Flag unnecessary complexity the diff adds: redundant or derivable state,
copy-paste with slight variation, deep nesting, dead code left behind. Name the
simpler form that does the same job. Tests carry their own version of this: a
test that cannot fail for its own specific reason, a test left behind for
behaviour the diff removed, fixture sprawl, and a test layout that no longer
mirrors the production one.

### Efficiency

Flag wasted work the diff introduces: redundant computation or repeated I/O,
independent operations run sequentially, blocking work added to startup or
hot paths. Also flag long-lived objects built from closures or captured
environments — they keep the entire enclosing scope alive for the object's
lifetime (a memory leak when that scope holds large values); prefer a
class/struct that copies only the fields it needs. Name the cheaper
alternative.

Disposable resources are waste when nothing reclaims them: a temp directory,
virtualenv, cache, or test basetemp created somewhere with no owner and no
removal path. `/tmp` is usually tmpfs, so what is left there is held in RAM
until reboot. Name where it should live instead — a location whose lifetime
already ends when the work does.

### Altitude

Check that each change is implemented at the right depth, not as a fragile
bandaid. Special cases layered on shared infrastructure are a sign the fix
isn't deep enough — prefer generalizing the underlying mechanism over adding
special cases.

## Phase 2 — Apply the fixes

Wait for all four agents to complete, dedup findings that point at the same
line or mechanism, and fix each remaining one directly. Skip any finding whose
fix would change intended behavior, require changes well outside the reviewed
diff, or that you judge to be a false positive — note the skip rather than
arguing with it. Finish with a brief summary of what was fixed and what was
skipped (or confirm the code was already clean).
