# Diagnose empty or partial Grove results

## Empty result

`symbols` can print `0 symbols` and exit successfully when the symbol is absent,
the extension has no registry grammar, or the grammar parses without extracting
definitions. Rule out extractor limits before claiming absence.

1. Run `grove languages` and check whether a grammar claims the file extension.
   If none does, switch to `rg` / `read` and report that Grove does not cover the
   file.
2. Run `grove registry` to locate the active registry, then inspect the target
   grammar's `tags.scm`. A missing tags query, or one explicitly marked as
   having no upstream tags, means `outline` and `symbols` cannot extract
   definitions even if `grove check` can parse the file.
3. If extraction should work, run `rg -n '<name>' <scope>`. No textual match
   supports genuine absence. A textual match with no Grove result is an
   extractor limitation; continue with text tools and report the limitation.

The diagnosis is complete only when absence is supported by both grammar
capability and repository evidence, or a specific capability limit is named.

## Partial body

If `grove source` omits code needed by the question, run
`grove outline <file> --json --detail 2`. Use the definition's `line`,
`start_byte`, and `end_byte` to derive a bounded line range, then read that range
directly. The recovery is complete when the entire relevant definition is
visible; widen to the whole file only when the reported bounds are wrong.
