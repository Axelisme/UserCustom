---
name: code-review
description: "Caller-selected specialized review of one fixed Git candidate on separate Standards and Spec axes, or advisory review of dirty work in progress. Use when the Caller explicitly chooses this procedure."
---

Two-axis report over one pinned subject and one pinned comparison base:

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / spec?

Both axes run in fresh, read-only contexts so they do not pollute each other's judgement. Their
reports are findings, not an Acceptance verdict.

**Spec source.** Follow the routing and no-guess boundary in Step 2.

**Dirty WIP branch.** When the intended subject includes staged, unstaged, or non-ignored untracked
files, read [the WIP review procedure](references/wip-review.md) before pinning the subject. That
branch produces an advisory snapshot report, not a fixed-candidate report.

## Process

### 1. Pin the review subject

Whatever the user names as the fixed point — a commit SHA, branch, tag, `main`, `HEAD~5`, etc. — is
input, not identity. If they did not name one, ask. Resolve it to `fixed_sha`, resolve the intended
candidate (default `HEAD`) to `candidate_sha`, resolve its tree to `candidate_tree`, then compute
`base_sha` as their merge-base. Record all four full object IDs once.

Use only the pinned objects afterwards:

- diff: `git diff <base_sha> <candidate_sha>`
- commits: `git log <base_sha>..<candidate_sha> --oneline`

Have the caller or execution environment provide an isolated, read-only checkout at
`candidate_sha`; this skill does not create one or acquire mutation authority. Verify its `HEAD`,
cleanliness, and tree before launch. Require green evidence from the validation applicable to that
candidate before launching either post-green axis. Documentation-only candidates may use their
applicable documentation checks; do not require an irrelevant executable test. The evidence must
identify the pinned subject or be reproducible against this checkout. A bad ref, empty diff,
mismatched checkout, moving subject, or missing applicable green evidence fails here rather than
inside the reviewers.

This step is complete when the full identities, isolated path, non-empty diff, commit list, and
applicable green evidence all name or reproduce against the same `candidate_sha` and
`candidate_tree`.

### 2. Identify the spec source

Locate the originating spec in this order:

1. Use the explicit path, tracker item, URL, or contents supplied by the caller.
2. When the work belongs to a dev-flow task, run that skill's `locate` command, read the located
   `INDEX.md`, and follow its spec pointer when present.
3. Follow issue references in commit messages (`#123`, `Closes #45`, GitLab `!67`, etc.) through the
   repository's documented issue-tracker workflow.
4. Search the repository's documented spec locations, then `docs/`, `specs/`, or `.scratch/` for a
   file matching the branch name or feature.
5. If nothing is found, ask the user where the spec is. If they say there is none, omit the **Spec**
   reviewer and report "no spec available".

Do not replace an explicit source or dev-flow INDEX pointer with a lower-priority match. This step is
complete when the Spec reviewer has one exact source or is explicitly omitted.

### 3. Identify the standards sources

Anything in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below — a fixed set of code smells, Fowler's (_Refactoring_, ch.3) plus one local addition, that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation — and, like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy** — a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches** — the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change** — one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest** — a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.
- **Reinvented Wheel** (not Fowler's; local) — new code hand-builds general-purpose infrastructure (schema derivation, validation, serialization, HTTP/WebSocket transport, path resolution, file locking, retry, config parsing) that a dependency the project already declares, or one it could readily take on, already provides. → name the package and what it would replace. Raise it only where the change records no reason the package was rejected; a stated reason — security boundary, determinism, licence — settles it.

This step is complete when every applicable documented source and the fixed smell baseline are ready
for the Standards reviewer.

### 4. Run both reviewers in parallel

Launch fresh, read-only reviewers through the available execution environment. Give both the same
isolated path, `base_sha`, `candidate_sha`, candidate tree, diff command, and commit list. Require
each report to name those identities and require the checkout identity to match before and after
its review.

**Standards reviewer prompt** — include:

- The pinned diff command, commit list, identities, and isolated path.
- The list of standards-source files you found in step 3, **plus the smell baseline from step 3** pasted in full — the reviewer has no other access to it.
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Under 400 words."

**Spec reviewer prompt** — include:

- The pinned diff command, commit list, identities, and isolated path.
- The path or fetched contents of the spec.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

If the spec is missing, skip the Spec reviewer and note this in the final report.

This step is complete when every applicable report names the pinned identities and the isolated
checkout still matches them. Discard both reports if the subject moved.

### 5. Aggregate

Start with the fixed `base_sha`, `candidate_sha`, and `candidate_tree`, then present the two reports
under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank
findings — the two axes are deliberately separate (see _Why two axes_) — and do not turn the report
into PASS/FAIL or accepted/rejected language.

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes — that's the reranking the separation exists to prevent.

This step is complete when both axes remain separately attributable to the same fixed subject and
every missing axis or residual limitation is explicit.

Code-review grants no landing authority. When landing is considered after this report, read collab's
[Land](../collab/SKILL.md#land) section; it owns the authority and fallback-method rules shared by both
review procedures, and its guidance ends once integration has moved into the persistence branch.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
