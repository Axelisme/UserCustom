---
name: grove
description: >
  Structural code navigation via the grove CLI — outline a file, find a symbol,
  read one symbol's body, find callers, map a directory's dependency graph,
  go-to-def, and syntax-check after an edit. The first move for a where-is /
  what's-in / who-calls question about a named symbol, in any language grove has
  a grammar for.
---

# grove

grove is the canonical procedure for **structural** code navigation: it parses
with tree-sitter, so it answers about definitions and their relationships rather
than about text. `grep`/`rg`/`read` remain the tools for text.

## grove for structure, shell for text

They are **partners**. Combining them is often the shortest path to a grounded
answer — both use 1-based lines over the same bytes.

**Reach for grove when the target is a named symbol or a structural relationship.**
If the prompt names a file, a function / class / type, or asks "where is", "who
calls", "what's in", "how does this connect" — grove answers precisely and
token-cheap, and returns a stable id to pass forward.

**Reach for the shell when grove can't see the target — it is the right tool, not
a fallback:**

- **Text, not a symbol** — a string literal, a log or error message, a config
  key, a constant's *value*, a flag, a `TODO` → `grep -rn` / `rg`. grove finds
  named definitions; it has no text search.
- **Non-code or unparsed files** — Makefiles, `*.conf`, YAML / JSON data, docs →
  `grep` / read.
- **A quick fact** — does a path exist, list a dir, count lines, find files by
  name → shell. A grove round-trip to confirm one line is wasted motion.

**Combine:**

- `rg -n '<text>'` to find the line a call site sits on → `grove definition --at
  <file:line:col>` to resolve what it refers to.
- `grove outline <file>` for the shape → a **bounded** read to grab a run of
  small adjacent symbols when that beats N `source` calls.
- `grove symbols` / `map` to locate the subsystem → `rg` to pin a constant inside.

| ❌ Don't (when the target is a symbol) | ✅ Do |
|---|---|
| `rg -n 'cmd_struct' git.c`, then read `git.c` | `grove outline git.c` → `grove source <id>` |
| `rg -n 'refs_be_files' refs/` | `grove symbols refs/ --name refs_be_files` → `grove source <id>` |
| read a whole 1700-line file for one function | `grove outline <file>` → `grove source <id>` |
| 7× `source` calls to understand a subsystem | `grove map <dir>` — one call, definitions + references, no bodies |

Searching for the *text* `refs_be_files` — a log line, a comment, a config value
— is the opposite case, and that is what `grep` is for.

## Procedure

1. Identify the named symbol and/or file in the prompt.
2. File but no symbol → `grove outline <file>`.
3. Symbol but no file → `grove symbols <dir> --name <symbol>` (exact by default;
   `--name-contains` only for deliberate fuzzy exploration).
4. Take the id from that result: `<lang>:<path>#<name>@<line>`, line 1-based.
5. `grove source <id>` → exactly that symbol's body. `grove source <file> <name>`
   returns the same body; the id pins the exact match when a name is overloaded.
6. "Who calls" → `grove callers <name> -d <dir>`. "Where defined" → `grove
   definition <name> -d <dir>`, or `--at <file:line:col>` when you have a
   position — that mode is scope-aware and follows imports across files.
7. After an edit → `grove check <file>`.
8. Broad or architectural questions → `grove map <dir>`: every definition grouped
   by file, each with its outgoing references, in one call. Prefer it over
   fetching many sources in sequence to build the same picture.

`--json` on any verb gives machine-readable output. `--detail 0|1|2` adjusts
**JSON verbosity only** — it does not shrink the human table.

**An id is cwd-relative.** Its path is relative to the directory the query ran
in, and absolute only when the target lies outside that directory. The same id
therefore names a *different file* when resolved from a different cwd — including
another worktree of the same repo, where it resolves silently and returns that
tree's copy. Keep ids inside the session that produced them; hand another agent
an absolute `grove source <file> <name>` instead.

## Trace a value's shape (dynamically-typed code)

grove has no type system, so on Python / JS reconstruct a parameter's shape with
a short backward slice:

1. `grove symbols <dir> --name <fn>` → `grove source <id>` — read the signature
   and name the parameter of interest.
2. `grove callers <fn> -d <root>` — every call site, each with its enclosing
   function, so you don't grep for it.
3. `grove source <enclosing-id>` — read **how the argument is constructed**. When
   it comes from a constructor, factory, or import binding, resolve that name too
   (`grove symbols --name <Ctor>` → `source`) and merge its field assignments
   with any caller-side mutations.

On statically-typed code step 1 is usually the whole answer — the type is already
in the signature.

## Empty output has three causes that look identical

`symbols` prints `0 symbols` and exits 0 whether the symbol is genuinely absent,
the language has no grammar, or the grammar carries no tags query. Nothing in the
output separates them, so rule the last two out before reporting that a symbol
does not exist.

**Is the language in the registry?**

```sh
grove languages       # what the registry holds, and the extensions each claims
grove fetch <lang>    # add a missing one
```

Grammars land in the OS cache (`~/.cache/grove/grammars`), shared by every repo
and worktree on the machine, so one fetch serves all of them. The catalog does
not cover every language — Lua and TOML have no grammar in it at all.

**Does that grammar extract symbols?** Eleven of the catalog's twenty-seven
languages parse but tag nothing, so `check` passes on a file `outline` reports as
empty, and `fetch` cannot fix it. **`bash` is one of them** — along with css,
html, json, regex, jsdoc, agda, haskell, julia, verilog, and embedded_template.
Confirm rather than assume:

```sh
grep -l "^; no upstream tags query" ~/.cache/grove/grammars/*/tags.scm
```

A file in one of those languages is shell work. Reach for `rg` on the function
name; a deeper grove query has nothing to find.

Genuinely partial body → read the file with `offset` / `limit` taken from
`grove outline --detail 2 --json`.

## Setup

Two things must exist: the `grove` binary and its grammars. `grove init` wires up
an MCP server and is **not** needed for CLI use — the CLI resolves grammars from
the OS cache with no per-project file at all.

If `grove --version` fails, hand the user these to run; a global install and a
network download are their call, not the agent's:

1. `curl -fsSL https://raw.githubusercontent.com/Entelligentsia/grove/main/install.sh | sh`
   (or `npm i -g @entelligentsia/grove`)
2. `grove fetch` — every grammar in the catalog, once per machine.

In Claude Code they can run either inline by typing `! <command>`.

`grove doctor` defaults to MCP mode and reports missing `.mcp.json` / `CLAUDE.md`
/ `grove.lock` as failures. For CLI use only `registry_root` and `grammar_cache`
matter; the rest is noise.
