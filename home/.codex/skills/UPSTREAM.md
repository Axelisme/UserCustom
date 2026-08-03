# Upstream sync

Skills in this directory that come from [mattpocock/skills](https://github.com/mattpocock/skills),
plus the local changes deliberately layered on top.

**Synced at upstream commit `2ab9580` (2026-07-28).**

To find what changed since:

```sh
git -C <path-to-skills-repo> log 2ab9580..HEAD -- skills/
```

Then re-apply the deviations below onto whatever you take. A conflict that lands on a listed
deviation is expected — resolve it in favour of the deviation unless the reason for it has gone
away. A conflict anywhere else means the local copy drifted without being recorded here, which is
the thing this file exists to prevent.

## Skills tracking upstream

| Local | Upstream path |
| --- | --- |
| `ask-matt` | `skills/engineering/ask-matt` |
| `code-review` | `skills/engineering/code-review` |
| `codebase-design` | `skills/engineering/codebase-design` |
| `diagnosing-bugs` | `skills/engineering/diagnosing-bugs` |
| `domain-modeling` | `skills/engineering/domain-modeling` |
| `grill-me` | `skills/productivity/grill-me` |
| `grill-with-docs` | `skills/engineering/grill-with-docs` |
| `grilling` | `skills/productivity/grilling` |
| `handoff` | `skills/productivity/handoff` |
| `implement` | `skills/engineering/implement` |
| `improve-codebase-architecture` | `skills/engineering/improve-codebase-architecture` |
| `prototype` | `skills/engineering/prototype` |
| `research` | `skills/engineering/research` |
| `resolving-merge-conflicts` | `skills/engineering/resolving-merge-conflicts` |
| `tdd` | `skills/engineering/tdd` |
| `teach` | `skills/productivity/teach` |
| `to-spec` | `skills/engineering/to-spec` |
| `to-tickets` | `skills/engineering/to-tickets` |
| `wayfinder` | `skills/engineering/wayfinder` |
| `writing-great-skills` | `skills/productivity/writing-great-skills` |

Not taken from upstream: `triage` (no external request surface here — `candidate-backlog` covers
internal discoveries) and `setup-matt-pocock-skills` (its generated config is replaced by the
"repo's documented conventions win" rule below).

## Local skills — not upstream, never overwrite

`dev-flow`, `orchestrate`, `candidate-backlog`, `simplify`, `dictator`, `planning-with-files`.

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
   under `.scratch/`. Affects `to-spec`, `to-tickets`, `wayfinder`, `code-review`, `ask-matt`.
   `code-review` additionally states what to do when no spec is found: run the Standards axis alone
   and say so.
3. **Traditional Chinese output** in `improve-codebase-architecture` (HTML report body, card labels,
   badges, legends — identifiers, paths, ADR ids and `/codebase-design` vocabulary stay original) and
   `teach` (lessons, references, `MISSION.md`, learning records — code, commands, notation and
   citation titles stay original). Everything else stays English.
4. **`domain-modeling` checkpoint mode** — a calling skill may batch glossary writes to natural
   checkpoints instead of writing inline. `grill-with-docs` uses it so the interview keeps its
   rhythm.
5. **`wayfinder`'s acceptance staircase** — an added section plus a map-body field and a charting
   step: the ordered user-visible states between here and the destination, without which the map is
   not charted.
6. **`tdd` scope note** — test-first is declared not to apply at GUI/hardware edges, where the repo's
   documented test conventions are followed and named instead.
7. **`tdd` renames upstream's "One slice at a time" to "One cycle at a time"** — `slice` collides
   with `to-tickets`' tracer-bullet slices and with `orchestrate`'s Slice. Content unchanged.
8. **Invocation policy** — `to-spec` and `to-tickets` are model-invocable here (upstream makes them
   user-invoked) so `dev-flow` can drive them. `wayfinder` stays user-invoked deliberately: it is the
   heavyweight flow a human should choose to enter.
9. **`writing-great-skills` adds `PORTING.md`** and a `## Porting` section pointing at it — a
   checklist for adopting a skill written for another ecosystem. No upstream equivalent.
