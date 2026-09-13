---
name: grove
description: >
  Structural navigation for named code symbols and relationships. Use first to
  locate or read definitions, outline a code file, trace callers, resolve a
  usage, map a small dependency surface, or syntax-check an edited file.
---

# Grove

Use **Grove for structure** and `rg` / `read` / the shell for **text**. Grove
parses definitions and relationships; text tools find literals, data, paths, and
non-code.

## Navigate

1. **Classify the target.** A symbol, definition, caller, usage, or code-file
   structure is Grove work. A string, log message, config value, flag, path, or
   prose is text work. Classification is complete when the target is either a
   named code relationship or a literal/file fact.

2. **Start narrow.** Take the first matching row:

   | Goal | First move | Complete when |
   |---|---|---|
   | Read a named symbol | `grove symbols <root> --name <name>` → `grove source <id>` | The exact match's body is read |
   | Inspect an unfamiliar code file | `grove outline <file>` → `grove source <id>` for relevant entries | The relevant definitions, not the whole file, are read |
   | Find call sites | `grove callers <name> -d <root>` | Every returned site relevant to the question is accounted for |
   | Resolve an identifier at a usage | `grove definition --at <file:line:col>` | The scope-aware target is identified |
   | Find definitions by exact name | `grove definition <name> -d <root>` | Candidate definitions are identified and ambiguity is resolved |
   | Map relationships in a small area | `grove map <small-dir>`; add `--kind` or `--name` when known | The requested dependency surface is covered |
   | Syntax-check an edited file | `grove check <file>` | Grove reports no `ERROR` or `MISSING` nodes |

3. **Follow evidence.** Pass IDs from `symbols` or `outline` into `source`. If
   `rg -n` found a usage, pass its 1-based position to `definition --at`.
   Continue only through symbols or relationships needed by the question. Stop
   when every structural claim is grounded by a symbol body or file-and-line
   location.

`grove source <file> <name>` is convenient when the file and unique name are
known. Prefer `source <id>` for overloads. `--name` is exact and
case-insensitive; add `--name-contains` only for deliberate fuzzy exploration.

## Keep the query tight

- `outline` grows with the file. When a name is known, query `symbols` directly.
- `map` emits every definition and outgoing reference in its scope. Keep the
  directory small and filter known names or kinds.
- `--json` provides machine-readable output. `outline --detail 0|1|2` changes
  JSON detail only.
- A symbol ID contains a cwd-relative path. Resolve it only from the cwd that
  produced it. Across agents or worktrees, pass an absolute file path and symbol
  name instead.
- `grove check` is a parser check, not a substitute for the repository's tests.

## Branches

- **Dynamic shape:** When a Python or JavaScript value's fields must be inferred
  from construction and mutation, read [VALUE-SHAPES.md](VALUE-SHAPES.md).
- **Empty or partial result:** Before reporting a missing symbol or trusting an
  incomplete body, read [RESULT-LIMITS.md](RESULT-LIMITS.md).
- **Unavailable:** When the binary or target grammar is unavailable, read
  [SETUP.md](SETUP.md).
