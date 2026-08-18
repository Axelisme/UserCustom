# Upstream sync

Skills in this directory that come from somewhere else, plus the local changes deliberately layered
on top. Most come from [mattpocock/skills](https://github.com/mattpocock/skills); the rest are
listed under "Skills from other upstreams" with their own sync point.

`mattpocock/skills` is vendored as a git subtree under `vendor/matt-skills`, and each skill under
this directory is a symlink into it. Which skills are adopted is therefore which symlinks exist, and
the sync point is the subtree's own commit — neither is restated here, because a restated one goes
stale and this file would have no way to know.

To sync:

```sh
git subtree pull --prefix=vendor/matt-skills https://github.com/mattpocock/skills.git main --squash
```

Both flags matter: `--prefix` must be exact, and omitting `--squash` floods this repository's log
with upstream's entire history.

git then does the three-way merge, and the conflicts are the work. Resolve one in favour of the
deviation unless the reason recorded for it below has gone away — and read the reason before
deciding, because a conflict is not always a side to pick. Upstream sometimes makes a change that is
orthogonal to the deviation but lands inside the same text; there the deviation is kept **and** the
orthogonal change is absorbed. Mechanically keeping our side would drop it silently, leaving no
conflict behind to notice.

A conflict anywhere other than a recorded deviation means the local copy drifted without being
recorded here, which is the thing this file exists to prevent.

## Skills not taken from upstream

An absent symlink cannot say whether a skill was declined or merely missed, so the declines are
listed. Everything upstream ships that is neither symlinked nor listed here is unexamined, and the
next sync should classify it.

Not taken from upstream: `triage` (no external request surface here — `candidate-backlog` covers
internal discoveries), `setup-matt-pocock-skills` (its generated config is replaced by the
"repo's documented conventions win" rule below), and — both graduated out of `in-progress` at the
2026-08-05 sync but not adopted here — `to-questionnaire` (sending someone else a questionnaire) and
`wizard` (generating an interactive bash wizard for human-only setup steps).

## Skills from other upstreams

`grove` is **still a hand-ported copy**, not a subtree: it is under observation and was deliberately
left out of the migration. Adopting the mechanism for it needs one more `git subtree add` under a
second prefix and one symlink, and nothing else — the machinery is per-upstream, not global. Until
then the sync point below is a hand-maintained claim, with the staleness that implies.

`grove` — from [Entelligentsia/grove](https://github.com/Entelligentsia/grove), `skills/grove/SKILL.md`,
**synced at grove `v0.5.0`**. Ported CLI-only; the deviations below were each verified against the
0.5.0 binary, so re-check them against the new binary when taking a newer version.

1. **CLI only.** The MCP surface is dropped entirely — the `mcp__grove__*` tool list, the ToolSearch
   batch-load preamble, and `grove init` / `.mcp.json` / `CLAUDE.md` wiring. A `grove serve` root is
   bound at launch and cannot follow an agent between worktrees; the CLI takes its target as an
   argument on every call, so it stays correct wherever the agent stands.
2. **`grove init` declared unnecessary.** The CLI resolves grammars from the OS cache with no
   per-project file; upstream's setup section routes through `init` because it assumes MCP. Setup is
   now install + `grove fetch`. `grove doctor` is flagged as noise for this use — it defaults to MCP
   mode and reports the absent wiring as failures.
3. **Missing-grammar failure mode added.** No upstream equivalent. A language with no grammar makes
   `symbols` print `0 symbols` and exit 0 — indistinguishable from a symbol that does not exist.
   Recovery is `grove languages` → `grove fetch <lang>`.
4. **`--detail` corrected.** Upstream advises `--detail 0` on large files as if it shrinks output; it
   only affects `--json`, and the human table is byte-identical across 0/1/2.
5. **Trimmed:** the five-language construction-idiom table (this fleet's registry carries Python),
   the full/minimal profile-gate paragraph, and the closing "When grove, when shell" section, which
   restated the opening partners section.

## Local skills — not upstream, never overwrite

`dev-flow`, `collab`, `candidate-backlog`, `simplify`, `dictator`.

They may reference upstream skills as producers, but the reference runs **one way**: no upstream
skill mentions them. `ask-matt` is the single exception — as the router it names both workflows,
which is what keeps the coupling out of every other file.

## Deviations

1. **Documented conventions win.** Where upstream hardcodes `CONTEXT.md` and `docs/adr/`, the local
   copy reads the repo's CLAUDE.md / AGENTS.md first (`docs/glossary.md`, module READMEs, a
   topic-grouped `docs/adr/` with `ADR-NNNN` and `[[NNNN]]` interlinks) and falls back to upstream's
   layout only where nothing is documented. Affects `domain-modeling`, `diagnosing-bugs`, `tdd`,
   `improve-codebase-architecture`, `ask-matt`.
2. **Tracker by convention, not by config.** Upstream defers to `/setup-matt-pocock-skills` for
   where issues live. The local copy reads CLAUDE.md / AGENTS.md and falls back to local markdown
   under `.scratch/`. Affects `to-spec`, `to-tickets`, `wayfinder`, `code-review`, `prototype`,
   `ask-matt`. `prototype` carries it in rule 6 — where the pointer to the kept prototype branch
   goes; the `prototype/<name>` branch-naming convention itself is upstream's and stays.
   `code-review` additionally states what to do when no spec is found: run the Standards axis alone
   and say so.
3. **Traditional Chinese output** in `improve-codebase-architecture` (HTML report body, card labels,
   badges, legends — identifiers, paths, ADR ids and `/codebase-design` vocabulary stay original).
   Everything else stays English.
4. **`domain-modeling` checkpoint mode** — a calling skill may batch glossary writes to natural
   checkpoints instead of writing inline. `grill-with-docs` uses it so the interview keeps its
   rhythm.
5. **`wayfinder`'s acceptance staircase** — an added section plus a map-body field and a charting
   step: the ordered user-visible states between here and the destination, without which the map is
   not charted.
6. **`tdd` scope note** — test-first is declared not to apply at GUI/hardware edges, where the repo's
   documented test conventions are followed and named instead.
7. **`tdd` renames upstream's "One slice at a time" to "One cycle at a time"** — `slice` collides
   with `to-tickets`' tracer-bullet slices. Content unchanged.
8. **Invocation policy** — `to-spec` and `to-tickets` are model-invocable here (upstream makes them
   user-invoked) so `dev-flow` can drive them. `wayfinder` stays user-invoked deliberately: it is the
   heavyweight flow a human should choose to enter.
9. **`writing-for-agents` adds `PORTING.md`** and a `## Porting` section in `SKILL-MECHANICS.md`
   pointing at it — a checklist for adopting a skill written for another ecosystem. No upstream
   equivalent. (Upstream renamed this skill from `writing-great-skills` and dropped its
   `GLOSSARY.md` at `1fc6573`; the porting checklist moved to the skill-mechanics branch because
   that is where the skill-specific material now lives.)
10. **`wait-what` re-pitches in Traditional Chinese.** Upstream asks for ASD-STE100 Simplified
    Technical English; the local copy applies the same plain-prose discipline to Chinese, and
    reads the glossary the repo documents (deviation 1) rather than hardcoding `CONTEXT.md`.
    Identifiers, paths and commands stay in their original form.
11. **`tdd` owns test-suite contraction** — an added `## Test-suite hygiene` section plus two
    anti-patterns (Setup-heavy, Type-narrowing as assertion) and Python examples in `tests.md`,
    which upstream writes only in TypeScript. Upstream's loop has no owner for removing a test or
    for extracting test scaffolding: it routes all reshaping to `/code-review`, whose scope is one
    diff. Boilerplate that accrues a few lines per ticket across hundreds of files therefore never
    enters any review's scope. The section states the carve-out explicitly — *Refactoring is not
    part of the loop* still governs the code under test — so the two rules do not contradict.
    `simplify`'s whole-tree mode is the tool the section's first rule assumes.
12. **`code-review` adds the Reinvented Wheel smell** to the baseline. No upstream equivalent; the
    baseline covers duplication within a change but not a change that duplicates a declared
    dependency. Pairs with `dev-flow`'s S0 dependency check (local skill, v7), which is where the
    reason for rejecting a package is supposed to be recorded — this smell is what notices when
    nothing was recorded. Upstream's sentence introducing the baseline calls it "a fixed set of
    Fowler code smells (*Refactoring*, ch.3)"; since that sentence is pasted verbatim into the
    Standards sub-agent prompt, it is amended here to say Fowler's plus one local addition, and the
    entry itself is marked. Take upstream's wording again only if this smell is dropped.

13. **Upstream's `CLAUDE.md` and `AGENTS.md` are deleted inside the prefix.** They arrive with
    `subtree add` and would otherwise be the nearest — and, this repository having no root
    instruction file, the only — directory-scoped instructions for any work under `vendor/`. Nested
    instruction files are additive, so a file placed above the prefix would be read alongside them
    rather than suppressing them. Nothing in them applies here: they maintain upstream's
    `plugin.json`, bucket `README.md`s and `docs/` pages, and one line tells an agent to run
    `scripts/link-skills.sh`, which symlinks upstream skills into `~/.claude/skills` and collides
    with this repository's own overlay. **Expect a modify/delete conflict** whenever upstream edits
    them; the resolution is always to keep them deleted.

The five below were deviations all along and simply were never written down. The subtree migration's
audit surfaced them by diffing the vendored tree against pristine upstream, which is the check no
hand-maintained list could perform on itself.

14. **`implement` is rewritten to this fleet's authority model** — validation graded by whether it
    exercises the shipped entrypoint rather than always `/tdd`, review bound to a fixed subject, no
    unilateral commit or history mutation without applicable user authority, and explicit completion
    criteria. Upstream's version commits to the current branch on its own, which is incompatible with
    `collab` owning landing authority. The same validation criterion appears in `ask-matt`, in the
    one sentence the router spends on `/implement`; upstream's is concrete there too, so both files
    are kept concrete rather than trading a directive for adjectives.
15. **`handoff` is rewritten as routing rather than factual authority** — it points at each owning
    spec, ticket, task record, ADR, commit or evidence artifact instead of copying them, routes
    Dev-flow work to the active guidance, task `INDEX.md` and handed-off ticket, and covers the Pi
    `handoff_context` transition without authorizing it. A handoff that restates content becomes a
    second status store, which `dev-flow` exists to prevent.
16. **`code-review` gains `references/wip-review.md`** — the advisory procedure for reviewing dirty
    work in progress, which the skill's own description already promises and upstream has no
    equivalent of. Upstream's procedure pins a fixed candidate and has nothing to say about staged,
    unstaged, or untracked files.
17. **`tdd` gains `gate.md`, `contract-review.md` and `assets/gate.sh`** — the delegated red/green
    validation gate and the fixed red-surface contract review. `collab` points at `gate.md` for
    delegated validation needing several commands, a fixed working directory, or owned temporary
    state, so a local skill depends on this addition.
18. **`writing-for-agents` adds the load-bearing noun rule** — define the term a rule's obligation
    rests on where the rule uses it. An undefined one does not read as missing: each agent supplies
    a plausible meaning and obeys the rule it invented, so the defect surfaces as inconsistent
    behaviour rather than as a question.
